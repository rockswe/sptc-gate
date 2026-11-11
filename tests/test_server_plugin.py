"""The simulator's model of the sptc plugin: ServerConfig.plugin_semantics and the prefill
allowance modes (spec_prefill_mode fixed | adaptive | off). Mirrors the behaviour the
plugin tests check on vLLM (integrations/tests_vllm/test_sptc_scheduler.py)."""

import pytest

from sptc_sim.des import Sim
from sptc_sim.hardware import GPUS, GRAPHS, MODELS, StepCost
from sptc_sim.server import PRIO_SPEC, Request, Server, ServerConfig


def _plugin(**kw):
    sim = Sim()
    cost = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)
    cfg = dict(policy="agent", plugin_semantics=True, reject_bets=True,
               spec_max_wait=float("inf"), free_window=8)
    srv = Server(sim, cost, ServerConfig(**{**cfg, **kw}))
    srv.log_steps = True
    return sim, srv


def _decoding(sim, srv, **kw):
    r = Request(prompt=50, out=10_000, **kw)
    srv.submit(r)
    sim.run(until=sim.now + 0.02)
    assert r.state == "running" and r.need_prefill <= 0
    return r


def _tokens_after(sim, srv, reqs, steps=1):
    """Tokens scheduled in each of the first `steps` steps that start after reqs arrive
    (the step already running when they arrive does not see them)."""
    t_sub = sim.now
    for r in reqs:
        srv.submit(r)

    def later():
        return [t for t0, _, _, t, _ in srv.step_log if t0 >= t_sub]

    while len(later()) < steps:
        sim.run(until=sim.now + 0.001)
    return later()[:steps]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        ServerConfig(spec_prefill_mode="sometimes")


@pytest.mark.parametrize("mode,first", [("fixed", 513), ("adaptive", 513), ("off", 3001)])
def test_allowance_with_an_untagged_stream_decoding(mode, first):
    sim, srv = _plugin(spec_prefill_mode=mode)
    _decoding(sim, srv, kind="root")
    assert _tokens_after(sim, srv, [Request(prompt=3000, out=5, early=True)]) == [first]


@pytest.mark.parametrize("mode,early,bet", [("fixed", 513, 513), ("adaptive", 3001, 513)])
def test_adaptive_early_decoder_protects_only_against_bets(mode, early, bet):
    sim, srv = _plugin(spec_prefill_mode=mode)
    _decoding(sim, srv, early=True)
    assert _tokens_after(sim, srv, [Request(prompt=3000, out=5, early=True)]) == [early]
    sim2, srv2 = _plugin(spec_prefill_mode=mode)
    _decoding(sim2, srv2, early=True)
    b = Request(prompt=3000, out=5, spec=True)
    assert _tokens_after(sim2, srv2, [b]) == [bet]
    assert b.priority == PRIO_SPEC and b.state == "running"


def test_adaptive_uncapped_early_prefill_does_not_spend_the_bets_allowance():
    # An early decoder protects only against bets: the early prefill runs uncapped and,
    # as in the plugin, is not charged, so the bet still gets the full 512 tokens.
    sim, srv = _plugin(spec_prefill_mode="adaptive")
    _decoding(sim, srv, early=True)
    e, b = Request(prompt=3000, out=5, early=True), Request(prompt=3000, out=5, spec=True)
    assert _tokens_after(sim, srv, [e, b]) == [1 + 3000 + 512]
    assert b.computed_tokens == 512


def test_adaptive_nothing_decoding_nothing_to_protect():
    sim, srv = _plugin(spec_prefill_mode="adaptive")
    reqs = [Request(prompt=3000, out=5, early=True), Request(prompt=3000, out=5, spec=True)]
    assert _tokens_after(sim, srv, reqs) == [6000]


def test_bet_rejected_outside_the_free_window():
    sim, srv = _plugin(free_window=2)
    _decoding(sim, srv, kind="root")
    b1, b2 = Request(prompt=50, out=100, spec=True), Request(prompt=50, out=100, spec=True)
    _tokens_after(sim, srv, [b1, b2])
    assert b1.state == "running" and b2.state == "aborted" and srv.bets_rejected == 1


def test_bet_rejected_while_early_work_waits_on_the_allowance():
    sim, srv = _plugin()
    _decoding(sim, srv, kind="root")
    e1, e2 = Request(prompt=3000, out=5, early=True), Request(prompt=3000, out=5, early=True)
    b = Request(prompt=100, out=5, spec=True)
    _tokens_after(sim, srv, [e1, e2, b])
    assert e2.state == "waiting" and b.state == "aborted"


@pytest.mark.parametrize("hold,admitted", [(16, True), (3, False)])
def test_bet_held_behind_the_allowance_then_admitted_or_rejected(hold, admitted):
    # e1 uses the whole allowance for 6 steps (3000 = 5 x 512 + 440); the bet passes the
    # gate but gets no prefill until the 6th step, when 72 tokens are left for it
    sim, srv = _plugin(bet_hold_steps=hold)
    _decoding(sim, srv, kind="root")
    b = Request(prompt=600, out=5, spec=True)
    toks = _tokens_after(sim, srv, [Request(prompt=3000, out=5, early=True), b], steps=6)
    if admitted:
        assert toks == [513] * 5 + [1 + 440 + 72] and b.state == "running"
    else:
        assert b.state == "aborted" and srv.bets_rejected == 1


def test_held_bet_that_never_fits_is_rejected_not_a_deadlock():
    # gate passes (KV headroom over the reserve) but the prompt can never be allocated
    # (vLLM refuses such a prompt when it is added): rejected; the simulator must not
    # stall or raise. Holds in empty steps are not counted since audit #25, so this is
    # the only bet an empty step still rejects.
    sim, srv = _plugin(spec_prefill_mode="off", kv_blocks=100)
    b = Request(prompt=2000, out=5, spec=True)
    srv.submit(b)
    sim.run()
    assert b.state == "aborted" and srv.bets_rejected == 1


def test_no_promotion_and_fcfs_with_bets_last():
    sim, srv = _plugin()
    b = Request(prompt=50, out=5, spec=True)
    n = Request(prompt=50, out=5)
    srv.submit(b)
    srv.submit(n)
    srv.promote(b)  # the plugin has no promotion
    assert b.priority == PRIO_SPEC
    assert sorted([b, n], key=srv._order) == [n, b]
    early_prog = Request(prompt=50, out=5, prog_t=-5.0)  # program order is not used
    srv.submit(early_prog)
    assert sorted([early_prog, n], key=srv._order) == [n, early_prog]


# ---- the vLLM adapter's audit fixes (ServerConfig.plugin_fixes; audit #2, #10)
@pytest.mark.parametrize("fixes", [True, False])
def test_running_bet_prefill_leaves_the_allowance_waiting_early_work_needs(fixes):
    # audit #2: b is mid-prefill (3000 tokens, 512 per step); an early request arrives.
    # Fixed adapter: b's chunk leaves e's 200 tokens, so e starts in the next step.
    # Unfixed adapter: b takes the whole allowance and e waits until b's prompt is done.
    sim, srv = _plugin(plugin_fixes=fixes)
    _decoding(sim, srv, kind="root")
    b = Request(prompt=3000, out=5, spec=True)
    _tokens_after(sim, srv, [b])
    assert b.state == "running" and b.need_prefill > 0
    e = Request(prompt=200, out=5, early=True)
    done = b.computed_tokens  # a step is in flight: it adds 512 more
    assert _tokens_after(sim, srv, [e]) == [513]
    if fixes:
        assert e.state == "running" and b.computed_tokens - done == 512 + 312
    else:
        assert e.state == "waiting" and b.computed_tokens - done == 512 + 512


@pytest.mark.parametrize("fixes", [True, False])
def test_hold_not_counted_while_another_bets_prefill_takes_the_allowance(fixes):
    # audit #10: b2 passes the gate every step but b1's prefill takes the allowance for
    # 6 steps. Fixed adapter: those steps do not count, b2 runs once b1 is done.
    # Unfixed adapter: b2 is rejected held_too_long after 3 steps.
    sim, srv = _plugin(plugin_fixes=fixes, bet_hold_steps=3)
    _decoding(sim, srv, kind="root")
    b1, b2 = Request(prompt=3000, out=5, spec=True), Request(prompt=100, out=5, spec=True)
    _tokens_after(sim, srv, [b1, b2], steps=8)
    if fixes:
        assert b2.state in ("running", "done") and srv.bets_rejected == 0
    else:
        assert b2.state == "aborted" and srv.bets_rejected == 1
