"""vLLM 0.32 KV semantics in the base server (ServerConfig.full_isl, resume_from_cache,
cache_freed_blocks; shared prefixes) and the legacy model they replace (LEGACY_KV)."""

import pytest

from sptc_sim.des import Sim
from sptc_sim.hardware import GPUS, GRAPHS, MODELS, StepCost
from sptc_sim.server import BLOCK, LEGACY_KV, Request, Server, ServerConfig

COST = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)


def _server(**kw):
    sim = Sim()
    return sim, Server(sim, COST, ServerConfig(**kw))


def _released(srv) -> bool:
    kv = srv.kv
    return (not kv.active and kv.cached == sum(e.blocks for e in kv.entries.values())
            and kv.free + kv.cached == kv.total)


def test_defaults_are_vllm_032_and_legacy_turns_them_off(monkeypatch):
    monkeypatch.delenv("SPTC_LEGACY_KV", raising=False)
    cfg = ServerConfig()
    assert cfg.full_isl and cfg.resume_from_cache and cfg.cache_freed_blocks
    legacy = ServerConfig(**LEGACY_KV)
    assert not (legacy.full_isl or legacy.resume_from_cache or legacy.cache_freed_blocks)


def test_legacy_env_switch_sets_defaults_only(monkeypatch):
    """SPTC_LEGACY_KV=1 regenerates the pre-fix results from scripts without --legacy-sim:
    ServerConfig defaults to LEGACY_KV, explicit values win, and GeneralServer keeps the
    full-ISL admission it already had before the KV fixes."""
    from sptc_sim.general import GeneralServer
    monkeypatch.setenv("SPTC_LEGACY_KV", "1")
    assert ServerConfig() == ServerConfig(**LEGACY_KV)
    assert ServerConfig(full_isl=True).full_isl
    g = GeneralServer(Sim(), COST, ServerConfig())
    assert g.full_isl and not g.cfg.resume_from_cache and not g.cfg.cache_freed_blocks
    monkeypatch.setenv("SPTC_LEGACY_KV", "0")
    assert ServerConfig().full_isl and GeneralServer(Sim(), COST, ServerConfig()).full_isl


@pytest.mark.parametrize("full", [True, False])
def test_full_isl_admits_only_when_the_whole_prompt_fits(full):
    """audit #32: vLLM 0.32 refuses a waiting request whose whole sequence does not fit
    (kv_cache_manager.py:518-538); the legacy model admitted it on its first chunk."""
    kw = {} if full else LEGACY_KV
    sim, srv = _server(kv_blocks=60, max_batched_tokens=128, **kw)
    a = Request(prompt=400, out=50)  # at most 29 blocks
    srv.submit(a)
    sim.run(until=0.02)
    b = Request(prompt=700, out=10, kind="root")  # 44 blocks: 29 + 44 > 60
    srv.submit(b)
    sim.run()
    assert a.state == b.state == "done"
    if full:
        assert b.t_sched >= a.t_done and a.preemptions + b.preemptions == 0
    else:
        assert b.t_sched < a.t_done and a.preemptions + b.preemptions >= 1


def test_full_isl_counts_evictable_cache_as_room():
    """get_num_free_blocks counts cached blocks with no reference: a request fits if
    evicting them makes room."""
    sim, srv = _server(kv_blocks=60)
    old = Request(prompt=600, out=20, kind="root", session="old")
    srv.submit(old)
    sim.run()
    assert srv.kv.cached > 30 and srv.kv.free < 30
    big = Request(prompt=800, out=10, kind="root", session="new")
    srv.submit(big)
    sim.run()
    assert big.state == "done" and big.preemptions == 0 and _released(srv)


@pytest.mark.parametrize("resume", [True, False])
def test_preempted_request_resumes_from_its_cached_blocks(resume):
    """audit #17: _preempt_request frees the blocks; their hashes stay, and the resumed
    request (num_computed_tokens 0) finds them again (scheduler.py:960-967)."""
    kw = dict(LEGACY_KV, full_isl=True, resume_from_cache=resume)
    sim, srv = _server(kv_blocks=64, **kw)
    reqs = [Request(prompt=200, out=150) for _ in range(8)]
    for r in reqs:
        srv.submit(r)
    sim.run()
    assert all(r.state == "done" and r.generated == 150 for r in reqs)
    pre = [r for r in reqs if r.preemptions]
    assert pre
    # tokens run through the model beyond the first pass (prompt + outputs - 1)
    extra = sum(r.computed_tokens - (r.prompt + r.out - 1) for r in pre)
    if resume:
        assert extra < sum((r.prompt + r.out) * r.preemptions for r in pre) / 2
    else:
        assert extra > 0
    assert _released(srv)


def test_freed_subcall_blocks_join_the_lru_queue_with_cached_contexts():
    """audit #18: one free queue (block_pool.py:774-803). A sub-call that finished after a
    root's turn is evicted after that root's context, not before it."""
    hits = {}
    for freed in (True, False):
        kw = dict(LEGACY_KV, full_isl=True, cache_freed_blocks=freed)
        sim, srv = _server(kv_blocks=100, **kw)
        t1 = Request(prompt=640, out=16, kind="root", session="a")  # 41 blocks cached
        srv.submit(t1)
        sim.run()
        sub = Request(prompt=640, out=16)  # finishes later: its blocks are newer
        srv.submit(sub)
        sim.run()
        big = Request(prompt=480, out=16)  # needs 31 of the 59 free + cached blocks
        srv.submit(big)
        sim.run()
        t2 = Request(prompt=700, out=4, kind="root", session="a")
        srv.submit(t2)
        sim.run()
        hits[freed] = t2.hit_tokens
        assert _released(srv)
    assert hits[False] == 640  # legacy: the sub-call's blocks were plain free blocks
    assert hits[True] < 640  # vLLM: the older root context is trimmed first


def test_shared_prefix_is_one_copy_and_hits_across_sessions():
    """audit #44: the prefix cache is content-addressed (kv_cache_manager.py:295-299), so
    roots of different sessions that start with the same system prompt share its blocks."""
    sim, srv = _server()
    pre = ("sys", "p")
    a = Request(prompt=2000, out=200, kind="root", session="a", prefix_key=pre,
                prefix_tokens=1984)
    srv.submit(a)
    sim.run(until=0.05)
    assert a.shared_blocks == 124 and srv.kv.active[pre][:2] == [124, 1]
    b = Request(prompt=2000, out=200, kind="root", session="b", prefix_key=pre,
                prefix_tokens=1984)
    srv.submit(b)
    sim.run(until=0.1)
    assert b.hit_tokens == 1984 and srv.kv.active[pre][:2] == [124, 2]
    # two running roots hold one copy of the prefix plus their own blocks
    assert srv.kv.used == 124 + a.blocks + b.blocks
    sim.run()
    assert not srv.kv.active and srv.kv.entries[("prefix", pre)].blocks == 124
    # next turn: the shared prefix, then the session's own blocks
    a2 = Request(prompt=2000 + 200 + 50, out=5, kind="root", session="a", prefix_key=pre,
                 prefix_tokens=1984)
    srv.submit(a2)
    sim.run()
    assert a2.hit_tokens == (2000 + 200) // BLOCK * BLOCK
    assert _released(srv)


def test_shared_prefix_evicted_breaks_the_chain():
    """When the shared prefix's tail is evicted, a session's own cached blocks behind it
    no longer match (vLLM's hash chain), and nothing leaks."""
    sim, srv = _server(kv_blocks=300)
    pre = ("sys",)
    a = Request(prompt=2000, out=50, kind="root", session="a", prefix_key=pre,
                prefix_tokens=1984)
    srv.submit(a)
    sim.run()
    filler = Request(prompt=4000, out=10)  # 251 blocks, 172 free: evicts 79 cached ones
    srv.submit(filler)
    sim.run()
    assert srv.kv.prefix_blocks(pre) < 124
    a2 = Request(prompt=2100, out=5, kind="root", session="a", prefix_key=pre,
                 prefix_tokens=1984)
    srv.submit(a2)
    sim.run()
    assert a2.hit_tokens < 1984 and a2.state == "done"
    assert _released(srv)


def test_no_leak_under_pressure_with_every_option():
    """Preemption, resume, abort and shared prefixes together leave every block free or
    cached."""
    sim, srv = _server(kv_blocks=200, max_batched_tokens=512)
    pre = ("sys",)
    reqs = [Request(prompt=600 + 37 * i, out=120, kind="root", session=i, prefix_key=pre,
                    prefix_tokens=592) for i in range(6)]
    reqs += [Request(prompt=300, out=900) for _ in range(4)]
    for r in reqs:
        srv.submit(r)
    sim.call_at(0.2, lambda: srv.abort(reqs[-1]))
    bad = []

    def watch():  # every block is free, cached, in a shared prefix or a request's own
        while any(r.state in ("waiting", "running") for r in reqs):
            kv = srv.kv
            held = sum(r.blocks for r in srv.running + srv.waiting)
            shared = sum(a[0] for a in kv.active.values())
            refs = sum(a[1] for a in kv.active.values())
            if kv.free + kv.cached + shared + held != kv.total or refs != sum(
                    r.shared_blocks > 0 for r in srv.running + srv.waiting):
                bad.append(sim.now)
            yield sim.timeout(0.0005)

    sim.process(watch())
    sim.run()
    assert not bad
    assert sum(r.preemptions for r in reqs) > 0
    assert all(r.state == "done" for r in reqs[:-1])
    assert _released(srv)


def test_ttl_pin_covers_the_shared_prefix_of_a_pinned_context():
    """kv_policy pin (Continuum): a pinned context is useless without the shared prefix it
    starts with, so the prefix is pinned as long as the context."""
    sim, srv = _server(kv_policy="pin", pin_ttl=5.0, kv_blocks=300)
    pre = ("sys",)
    a = Request(prompt=2000, out=50, kind="root", session="a", prefix_key=pre,
                prefix_tokens=1984)
    srv.submit(a)
    sim.run()
    e = srv.kv.entries[("prefix", pre)]
    assert e.pinned_until == srv.kv.entries["a"].pinned_until > sim.now
    filler = Request(prompt=4000, out=10)  # does not fit while the pins hold
    srv.submit(filler)
    sim.run()
    assert filler.t_sched >= e.pinned_until and filler.state == "done"
    assert _released(srv)


@pytest.mark.parametrize("gate", ["submit", "schedule"])
def test_bet_gate_at_schedule_lets_a_decoy_run_beside_its_real_call(gate):
    """audit #45: gated at submit, a bet issued with its real call is refused because that
    call is still waiting; gated in the waiting loop (as the plugin) it is admitted after
    it, inside the free window."""
    sim, srv = _server(policy="agent", reject_bets=True, spec_max_wait=float("inf"),
                       bet_gate=gate)
    real = Request(prompt=300, out=20)
    srv.submit(real)
    if gate == "submit":
        assert not srv.admits_bet_now()  # the client would refuse the decoy here
        return
    assert srv.admits_bet_now()
    bet = Request(prompt=300, out=20, spec=True, claimed=False)
    srv.submit(bet)
    sim.run()
    assert real.state == bet.state == "done" and bet.t_sched == real.t_sched
    assert srv.bets_rejected == 0
