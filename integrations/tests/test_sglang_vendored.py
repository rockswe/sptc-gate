"""sptc_sglang on SGLang v0.5.22's own scheduling code, run locally from the vendored
sources (tests/sglang_vendored.py: real Scheduler / PrefillAdder / PrefillBudget /
retract_decode methods, stand-in requests, KV pool and forward pass). Skipped if the
sources are missing.

The first test is the untagged differential: the same untagged workload runs on the stock
path and on the plugin, and every step must match (batch, chunk boundaries, waiting queue,
chunked request, batch_is_full, KV pages in use, client outputs). The workload is checked to
reach page rounding, truncation alignment, chunk continuations, NO_TOKEN, retraction, mixed
chunks and pause(retract), so a change to untagged behaviour in any of them fails here.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

import sglang_vendored as V
from sptc_sglang import core, plugin
from sptc_vllm.policy import SptcConfig

pytestmark = pytest.mark.skipif(not V.AVAILABLE, reason=f"SGLang sources not at {V.SRC}")


def stock(**kw):
    w = V.World()
    return w, w.build(**kw)


def sptc(cfg=SptcConfig(), **kw):
    w = V.World(retraction_hook=core.retraction_order)
    with V.fake_sglang_modules(w):
        reason = plugin.make_finish_reason()
        cls = core.make_scheduler_class(
            w.Scheduler, AddReqResult=w.AddReqResult, finish_abort=plugin.make_finish_abort(reason),
            finish_reason=reason, retract=plugin.make_retract(),
            cfg_loader=lambda: cfg, checks=plugin.checks,
        )
        s = w.build(cls, **kw)
    return w, s


# --------------------------------------------------------------------------- differential
def _workload():
    """(step, kind, request) events: arrivals, grammar-ready arrivals and one pause."""
    ev = []
    for i in range(14):
        prompt = [90, 700, 130, 1500, 260, 77, 999, 333, 40, 1201, 512, 64, 300, 850][i]
        ev.append((3 * i, "add", V.Req(f"r{i}", prompt=prompt, max_new=60 + 37 * (i % 4),
                                       logprob=i in (5, 6))))
    ev.append((10, "late", V.Req("g0", prompt=420, max_new=30)))
    ev.append((25, "late", V.Req("g1", prompt=60, max_new=30)))
    ev.append((70, "pause", None))
    return ev


def _run(w, s, steps=500):
    ev = _workload()
    trace = []
    reqs = []
    for t in range(steps):
        for when, kind, req in ev:
            if when != t:
                continue
            if kind == "pause":
                s.pause_generation(NS(mode="retract"))
                s._engine_paused = False  # continue_generation
                trace.append(("paused", [r.rid for r in s.waiting_queue]))
                continue
            reqs.append(req)
            if kind == "add":
                s._add_request_to_queue(req)
            else:
                s.late.append(req)
        out = w.step(s)
        trace.append((
            out, [r.rid for r in s.waiting_queue], s.chunked_req and s.chunked_req.rid,
            s.running_batch.batch_is_full, w.pool.used, len(w.outputs),
        ))
    return trace, list(w.outputs), reqs


CONFIGS = [  # kv sized so that every run reaches NO_TOKEN and a KV-pressure retraction
    dict(page=1, chunk=256, kv=6000),
    dict(page=16, chunk=256, align=64, kv=6400),
    dict(page=16, chunk=256, align=64, kv=4800, mixed=True),
    dict(page=4, chunk=192, kv=4000, mixed=True, slots=6),
]


def _reaches_everything(w, trace, outputs, reqs, cfg):
    """The stock run exercises what the differential is meant to cover."""
    steps = [x for x in trace if x[0] != "paused"]
    prefills = [p for x in steps if x[0] for p in x[0][1] if isinstance(p, tuple)]
    prompt = {r.rid: len(r.origin_input_ids) for r in reqs}
    assert any(a > 0 for _, a, _ in prefills), "no chunk continuation"
    assert w.retracted, "no KV-pressure retraction"
    assert any(x[3] for x in steps), "batch_is_full never set"
    assert any(x[0] == "paused" for x in trace)
    assert sorted(rid for rid, _ in outputs) == sorted(prompt), "not every request finished"
    if cfg.get("page", 1) > 1:
        assert any(b % cfg["page"] for _, _, b in prefills), "no partial last page"
    if cfg.get("align"):
        assert any(a == 0 and b < prompt[rid] and b % cfg["align"] == 0
                   and b % 256 for rid, a, b in prefills), "no first chunk cut by the alignment"
    if cfg.get("mixed"):
        assert any(x[0] and x[0][0] == "MIXED" for x in steps), "never mixed"
        assert any(x[0] and x[0][0] == "DECODE" for x in steps), "always mixed"


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda c: ",".join(f"{k}={v}" for k, v in c.items()))
@pytest.mark.parametrize("mode", ["fixed", "adaptive", "off"])
def test_untagged_traffic_identical_to_stock_sglang(cfg, mode):
    w0, s0 = stock(**cfg)
    base = _run(w0, s0)
    _reaches_everything(w0, *base, cfg)
    w1, s1 = sptc(SptcConfig(prefill_allowance=mode), **cfg)
    got = _run(w1, s1)
    for t, (a, b) in enumerate(zip(base[0], got[0])):
        assert a == b, f"step {t}: stock {a} != plugin {b}"
    assert base[1] == got[1] and w0.retracted == w1.retracted
    assert s1._sptc.counts == {"rejected": 0, "dropped": 0, "admitted": 0}


def test_plugin_checks_accept_the_harness_server():
    w = V.World()
    s = w.build()
    with V.fake_sglang_modules(w):
        assert plugin.checks(s) == ([], [])


# --------------------------------------------------------------------------- helpers
def add(s, *reqs):
    for r in reqs:
        s._add_request_to_queue(r)


def run_until(w, s, steps):
    return [w.step(s) for _ in range(steps)]


def admitted(outs, rid):
    """First step whose batch prefilled rid, or None."""
    for t, out in enumerate(outs):
        if out and any(isinstance(x, tuple) and x[0] == rid for x in out[1]):
            return t
    return None


def reasons(w):
    return {rid: fr.get("message") for rid, fr in w.outputs if fr.get("type") == "abort"}


# --------------------------------------------------------------------------- #22 alignment
def test_alignment_above_budget_still_admits_tagged_work():
    """Audit #22: deterministic inference on flashinfer aligns chunks to 4096 > budget 512.
    Short tagged prompts are admitted whole (SGLang aligns only chunks), and the budget is
    rounded up to the alignment so a long one can still be chunked."""
    w, s = sptc(page=1, chunk=8192, align=4096)
    assert s._sptc.allowance.budget == 4096
    add(s, V.Req("e1", prompt=100, cls="early"), V.Req("b1", prompt=100, cls="bet"))
    outs = run_until(w, s, 2)
    assert admitted(outs, "e1") == 0 and admitted(outs, "b1") == 0 and not w.outputs
    w, s = sptc(page=16, chunk=8192, align=4096)
    add(s, V.Req("n", prompt=50, max_new=200))
    w.step(s)  # n decodes from now on
    add(s, V.Req("long", prompt=10_000, cls="early"))
    outs = run_until(w, s, 6)
    chunks = [x for o in outs if o for x in o[1] if isinstance(x, tuple) and x[0] == "long"]
    assert chunks[:2] == [("long", 0, 4096), ("long", 4096, 8192)]
    assert [o[0] for o in outs][:4] == ["EXTEND", "DECODE", "EXTEND", "DECODE"]


def test_budget_rounded_to_page_and_alignment():
    for page, align, want in ((16, None, 512), (16, 64, 512), (16, 4096, 4096), (64, 96, 576)):
        w, s = sptc(SptcConfig(spec_prefill_budget=500), page=page, align=align, chunk=8192)
        assert s._sptc.allowance.budget == want, (page, align)


# --------------------------------------------------------------------------- #21 NO_TOKEN
def _no_token_scene(s, w, bet):
    add(s, *[V.Req(f"n{i}", prompt=100, max_new=3500) for i in range(4)])
    w.step(s)  # four long decoders: their output reservations fill SGLang's budget
    if bet:
        add(s, V.Req("bet", prompt=3000, max_new=4096, cls="bet"))
    outs = [w.step(s)]
    add(s, V.Req("normal", prompt=500, max_new=50))
    return outs + run_until(w, s, 20)


def test_bet_refused_by_sglang_reservation_does_not_block_certain_work():
    """Audit #21: SGLang's reservation check refuses the bet (NO_TOKEN). Stock SGLang would
    set batch_is_full and hold back the next request until a decoder finishes. The bet is
    skipped instead: the normal request runs at once, as if the bet had never come."""
    w0, s0 = stock(kv=20_000, new_token_ratio=1.0)
    want = admitted(_no_token_scene(s0, w0, bet=False), "normal")
    assert want == 1
    w, s = sptc(SptcConfig(bet_hold_steps=4), kv=20_000, new_token_ratio=1.0)
    outs = _no_token_scene(s, w, bet=True)
    assert admitted(outs, "normal") == want and admitted(outs, "bet") is None
    assert not s.running_batch.batch_is_full
    assert reasons(w) == {"bet": "sptc_bet_rejected: held_too_long"}  # held, then rejected


# --------------------------------------------------------------------------- #7 chunked bet
def test_chunked_bet_dropped_instead_of_retracting_a_decoder():
    """Audit #7: decoders and a 4000-token bet prefilled 512 tokens at a time, with a decode
    step forced between chunks. KV runs out in one of those decode steps. Stock retraction
    sees only the decode batch, so it would retract a normal request (n5) and the bet would
    keep its KV. The bet is dropped instead, its KV freed, and no normal request is
    retracted."""
    w, s = sptc(SptcConfig(spec_prefill_budget=512), kv=100_000, chunk=2048, new_token_ratio=0.0)
    add(s, *[V.Req(f"n{i}", prompt=100, max_new=1000) for i in range(6)])
    w.step(s)
    w.pool.pages = w.pool.used + 4030  # the bet just fits SGLang's admission check
    add(s, V.Req("bet", prompt=4000, max_new=16, cls="bet"))
    modes = [o[0] for o in run_until(w, s, 24)]
    assert modes[:15] == ["EXTEND", "DECODE"] * 7 + ["EXTEND"]
    assert w.retracted == 0 and not s.waiting_queue and s.chunked_req is None
    assert reasons(w) == {"bet": "sptc_bet_dropped: kv_pressure"}
    assert dict(w.outputs)["bet"]["matched"] == "sptc_bet_dropped"
    assert s._sptc.counts["dropped"] == 1
    assert w.pool.used == sum(r.kv.pages for r in s.running_batch.reqs)  # bet's KV freed


def _requeued_retracted(s):
    """rids SGLang (or the plugin) requeued as retracted, in order."""
    out, orig = [], s._add_request_to_queue

    def hook(req, is_retracted=False):
        if is_retracted:
            out.append(req.rid)
        return orig(req, is_retracted=is_retracted)

    s._add_request_to_queue = hook
    return out


def test_chunked_early_request_retracted_instead_of_a_decoder():
    """The #7 scene with an early request, which is never dropped. Stock SGLang runs its
    chunks back to back, then retracts in its own order, where x (long prompt, no output
    yet) goes first. In the decode step the plugin forced between chunks, x is not in the
    decode batch, so SGLang would retract n5 while x kept its KV. x is retracted instead
    (KV freed, requeued), and no decoder is."""
    def scene(w, s):
        add(s, *[V.Req(f"n{i}", prompt=100, max_new=1000) for i in range(6)])
        w.step(s)
        w.pool.pages = w.pool.used + 4030
        add(s, V.Req("x", prompt=4000, max_new=16, cls="early"))
        requeued = _requeued_retracted(s)
        return [o[0] for o in run_until(w, s, 24)], requeued

    w, s = stock(kv=100_000, chunk=2048, new_token_ratio=0.0)
    modes, requeued = scene(w, s)
    assert modes[:3] == ["EXTEND", "EXTEND", "DECODE"] and requeued[0] == "x"

    w, s = sptc(SptcConfig(spec_prefill_budget=512), kv=100_000, chunk=2048, new_token_ratio=0.0)
    modes, requeued = scene(w, s)
    assert modes[:16] == ["EXTEND", "DECODE"] * 8 and set(modes[16:]) == {"DECODE"}
    assert requeued == ["x"] and w.retracted == 0  # SGLang retracted no decoder
    assert s.chunked_req is None and [r.rid for r in s.waiting_queue] == ["x"]
    assert reasons(w) == {} and s._sptc.counts["dropped"] == 0
    assert w.pool.used == sum(r.kv.pages for r in s.running_batch.reqs)  # x's KV freed


# --------------------------------------------------------------------------- #8 mixed chunk
@pytest.mark.parametrize("logprob", [True, False])
def test_mixed_chunk_forces_a_decode_only_when_sglang_could_not_mix(logprob):
    """Audit #8: --enable-mixed-chunk, chunk 2048, budget 512, an 8192-token early prompt.
    A decoder that asked for logprobs stops SGLang from mixing, so each capped chunk is a
    prefill-only step: a decode step is forced after it, as without mixed chunks. When
    SGLang mixes, the decoder rides along in every chunk and nothing is forced."""
    w, s = sptc(chunk=2048, mixed=True)
    add(s, V.Req("d", prompt=50, max_new=300, logprob=logprob))
    w.step(s)
    add(s, V.Req("e", prompt=8192, cls="early"))
    modes = "".join(o[0][0] for o in run_until(w, s, 20))
    assert modes == ("ED" * 10 if logprob else "M" * 16 + "DDDD")


# --------------------------------------------------------------------------- #37 pause
def test_pause_retract_drops_running_bets_instead_of_regating_them():
    """Audit #37: pause_generation(mode="retract") requeues every running request with a
    bare _add_request_to_queue(req). A bet that was already streaming used to be gated
    again on resume and rejected (nonbet_waiting) after its partial output. It is dropped
    (sptc_bet_dropped) at the pause, like a bet retracted for KV, and certain work resumes."""
    w, s = sptc(chunk=2048, slots=16)
    add(s, *[V.Req(f"n{i}", prompt=1000, max_new=50) for i in range(5)])
    w.step(s)
    add(s, V.Req("bet", prompt=200, max_new=50, cls="bet"))
    run_until(w, s, 3)
    assert "bet" in [r.rid for r in s.running_batch.reqs]
    s.pause_generation(NS(mode="retract"))
    assert reasons(w) == {"bet": "sptc_bet_dropped: retracted"}
    assert [r.rid for r in s.waiting_queue] == [f"n{i}" for i in range(5)]
    s._engine_paused = False
    run_until(w, s, 80)
    assert sorted(rid for rid, fr in w.outputs if fr["type"] == "length") == [f"n{i}" for i in range(5)]
    assert s._sptc.counts["dropped"] == 1 and s._sptc.counts["rejected"] == 0


def test_pause_retract_drops_a_chunked_bet():
    w, s = sptc(SptcConfig(spec_prefill_budget=512), chunk=2048)
    add(s, V.Req("n", prompt=100, max_new=200))
    w.step(s)
    add(s, V.Req("bet", prompt=3000, cls="bet"))
    w.step(s)
    assert s.chunked_req.rid == "bet"
    s.pause_generation(NS(mode="retract"))
    assert reasons(w) == {"bet": "sptc_bet_dropped: retracted"} and s.chunked_req is None
    assert [r.rid for r in s.waiting_queue] == ["n"] and w.pool.used == 0


# --------------------------------------------------------------------------- #23 invalid bet
def test_invalid_bet_gets_sglangs_own_error():
    """Audit #23: SGLang queues a request it already failed (here a grammar that did not
    compile) with to_finish = FINISH_ABORT(..., 400): one 1-token prefill, then the error.
    Behind waiting normal work the gate used to reject it as sptc_bet_rejected instead."""
    w, s = sptc(chunk=200)
    bad = V.Req("bad", prompt=1, cls="bet")
    bad.to_finish = w.FINISH_ABORT("Failed to compile json grammar", 400, "BadRequestError")
    add(s, V.Req("n1", prompt=150), V.Req("n2", prompt=150), V.Req("n3", prompt=100), bad)
    run_until(w, s, 4)
    fr = dict(w.outputs)["bad"]
    assert fr["status_code"] == 400 and fr["message"] == "Failed to compile json grammar"
    assert "matched" not in fr and s._sptc.counts["rejected"] == 0


# --------------------------------------------------------------------------- allowance details
def _paged(n, page):
    return -(-n // page) * page


def test_continuation_and_page_rounding_share_the_allowance():
    """Audit #27: a tagged continuation is charged to the allowance. e's second chunk is
    290 tokens: the allowance is charged 290 (SGLang's KV takes 304, page-rounded), which
    leaves 222, so e2 (220) is chunked to 208 and the step's page-rounded tagged prefill
    is 512. Without the continuation charge e2 would run whole next to e.
    Audit #14: this test does not see the cap's page floor. Without it the cap is 222, and
    SGLang's own admission page-rounds e2 to 224 > 222 and chunks it to 208 anyway.
    test_cap_is_whole_pages (fakes) checks the floor directly."""
    w, s = sptc(SptcConfig(spec_prefill_budget=512), page=16, chunk=2048)
    add(s, V.Req("n", prompt=50, max_new=300))
    w.step(s)
    add(s, V.Req("e", prompt=802, cls="early"), V.Req("e2", prompt=220, cls="early"))
    outs = run_until(w, s, 4)
    assert outs[0] == ("EXTEND", [("e", 0, 512)]) and outs[1][0] == "DECODE"
    assert outs[2] == ("EXTEND", [("e", 512, 802), ("e2", 0, 208)])
    assert sum(_paged(b - a, 16) for _, a, b in outs[2][1]) <= 512


# --------------------------------------------------------------------------- retraction order
def test_retraction_order_hook_on_sglangs_sort():
    """Audit #16: the AROUND hook over SGLang's own sort (length policy: keep long outputs,
    then short prompts) moves bets to the end, which retract_decode pops first."""
    w = V.World(retraction_hook=core.retraction_order)
    reqs = [V.Req("n0", prompt=10), V.Req("b0", prompt=10, cls="bet"),
            V.Req("e0", prompt=10, cls="early"), V.Req("b1", prompt=10, cls="bet"),
            V.Req("n1", prompt=99)]
    for i, r in enumerate(reqs):
        r.output_ids = [1] * (10 - i)
    plain = V.World().Batch._get_decode_retraction_order(reqs)
    assert [reqs[i].rid for i in plain] == ["n0", "b0", "e0", "b1", "n1"]
    order = w.Batch._get_decode_retraction_order(reqs)
    assert [reqs[i].rid for i in order] == ["n0", "e0", "n1", "b0", "b1"]


# --------------------------------------------------------------------------- mixed traffic
@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda c: ",".join(f"{k}={v}" for k, v in c.items()))
def test_tagged_traffic_keeps_sglangs_invariants(cfg, seed):
    """Random normal, early and bet traffic with grammar-late arrivals and a pause, on every
    config and mode: SGLang's own asserts hold (one chunked request, KV pool never
    overrun), every request ends, every bet ends admitted-and-finished, rejected or dropped,
    and no KV page is left allocated."""
    import random

    rng = random.Random(seed)
    mode = ("fixed", "adaptive", "off")[seed % 3]
    w, s = sptc(SptcConfig(prefill_allowance=mode, spec_prefill_budget=rng.choice([128, 512]),
                           free_window=rng.choice([2, 4, 8]), bet_hold_steps=rng.choice([0, 4, 16])),
                **cfg)
    reqs = []
    for t in range(1500):  # arrivals stop at 300; the rest drains the queue
        if t < 300 and rng.random() < 0.3:
            cls = rng.choice([None, None, "early", "bet", "bet"])
            r = V.Req(f"{cls or 'n'}{t}", prompt=rng.choice([20, 90, 300, 700, 1500]),
                      max_new=rng.choice([5, 40, 200]), cls=cls, logprob=rng.random() < 0.1)
            reqs.append(r)
            (s.late.append if rng.random() < 0.2 else s._add_request_to_queue)(r)
        if t == 150:
            s.pause_generation(NS(mode="retract"))
            s._engine_paused = False
        w.step(s)
    out = dict(w.outputs)
    assert sorted(out) == sorted(r.rid for r in reqs)
    for r in reqs:
        kind = out[r.rid].get("matched") or out[r.rid]["type"]
        if r.rid.startswith("bet"):
            assert kind in ("length", "sptc_bet_rejected", "sptc_bet_dropped"), (r.rid, kind)
        else:
            assert kind == "length", (r.rid, out[r.rid])
    assert w.pool.used == 0 and not s.waiting_queue and s.chunked_req is None
    c = s._sptc.counts
    assert c["rejected"] + c["dropped"] == sum(
        1 for fr in out.values() if fr.get("matched", "").startswith("sptc_"))
