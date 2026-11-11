import math

import pytest

from sptc_sim import suite
from sptc_sim.agent import FixedBackend, OutputModel, PolicyCfg, ScriptedStream, ServerBackend, run_turn
from sptc_sim.calib import trace_of
from sptc_sim.des import Resource, Sim
from sptc_sim.hardware import GPUS, GRAPHS, MODELS, StepCost
from sptc_sim.server import BLOCK, Request, Server, ServerConfig

NAMES = sorted(suite.measured_medians().pattern.unique())


# ------------------------------------------------------------------ kernel
def test_des_ordering_and_all_of():
    sim = Sim()
    log = []

    def p(name, dt):
        yield sim.timeout(dt)
        log.append((name, sim.now))
        return name

    a, b = sim.process(p("a", 2)), sim.process(p("b", 1))
    both = sim.all_of([a, b])
    sim.run()
    assert log == [("b", 1), ("a", 2)]
    assert both.value == ["a", "b"]


def test_resource_fifo():
    sim = Sim()
    res = Resource(sim, 1)
    order = []

    def user(i):
        yield res.acquire()
        order.append(i)
        yield sim.timeout(1)
        res.release()

    for i in range(3):
        sim.process(user(i))
    sim.run()
    assert order == [0, 1, 2] and sim.now == 3


# ------------------------------------------------------------------ cost model
def test_model_param_counts_match_cards():
    assert abs(MODELS["Qwen3-4B"].total_params / 1e9 - 4.0) < 0.1
    moe = MODELS["Qwen3-30B-A3B"]
    assert abs(moe.total_params / 1e9 - 30.5) < 0.3
    assert abs(moe.active_params / 1e9 - 3.3) < 0.3
    assert MODELS["Qwen3-4B"].kv_bytes_per_token == 147_456
    assert moe.kv_bytes_per_token == 98_304


def test_moe_touches_more_experts_with_batch_dense_does_not():
    moe, dense = MODELS["Qwen3-30B-A3B"], MODELS["Qwen3-4B"]
    assert moe.weight_bytes_touched(64) > 5 * moe.weight_bytes_touched(1)
    assert moe.weight_bytes_touched(4096) <= moe.weight_bytes * 1.001
    assert dense.weight_bytes_touched(1) == dense.weight_bytes_touched(512)


def test_decode_is_memory_bound_at_small_batch():
    c = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)
    assert c.decode_step(8, 1000) / c.decode_step(1, 1000) < 1.15
    assert c.step_time([(1, 1000), (4096, 0)]) > 5 * c.decode_step(1, 1000)


# ------------------------------------------------------------------ server
def _server(**kw):
    sim = Sim()
    cost = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)
    return sim, Server(sim, cost, ServerConfig(**kw))


def _all_released(srv) -> bool:
    """No request holds KV: every block is free or an evictable cache entry (freed full
    blocks stay cached, as in vLLM), and the entry count matches the blocks."""
    kv = srv.kv
    return (not kv.active and kv.cached == sum(e.blocks for e in kv.entries.values())
            and kv.free + kv.cached == kv.total and kv.headroom(srv.sim.now) == kv.total)


def test_single_request_timing_is_sum_of_steps():
    sim, srv = _server()
    r = Request(prompt=100, out=5)
    srv.submit(r)
    sim.run()
    c = srv.cost
    expect = c.step_time([(100, 0)], 1) + sum(c.step_time([(1, 100 + i)]) for i in range(4))
    assert math.isclose(r.t_done, expect, rel_tol=1e-9)
    assert r.generated == 5 and _all_released(srv)


def test_kv_conserved_and_preemption_completes_everything():
    sim, srv = _server(kv_blocks=64)  # 1024 tokens: forces preemption
    reqs = [Request(prompt=200, out=150) for _ in range(8)]
    for r in reqs:
        srv.submit(r)
    max_used = [0]

    def watch():
        while any(r.state != "done" for r in reqs):
            max_used[0] = max(max_used[0], srv.kv.used)
            yield sim.timeout(0.001)

    sim.process(watch())
    sim.run()
    assert all(r.state == "done" and r.generated == 150 for r in reqs)
    assert sum(r.preemptions for r in reqs) > 0
    assert max_used[0] <= srv.kv.total
    assert _all_released(srv)


def test_abort_frees_blocks():
    sim, srv = _server()
    r = Request(prompt=1000, out=500)
    srv.submit(r)
    sim.call_at(0.05, lambda: srv.abort(r))
    sim.run()
    assert r.state == "aborted" and _all_released(srv)


@pytest.mark.parametrize("policy,hit", [("lru", True), ("none", False)])
def test_prefix_cache_across_turns(policy, hit):
    sim, srv = _server(kv_policy=policy)
    t1 = Request(prompt=3000, out=50, kind="root", session="a")
    srv.submit(t1)
    sim.run()
    t2 = Request(prompt=3000 + 50 + 100, out=10, kind="root", session="a")
    srv.submit(t2)
    sim.run()
    assert (t2.cached > 2900) == hit
    assert t2.cached % BLOCK == 0


def test_pin_survives_pressure_lru_does_not():
    for policy, survives in (("pin", True), ("lru", False)):
        sim, srv = _server(kv_policy=policy, kv_blocks=300, pin_ttl=100)
        srv.submit(Request(prompt=3000, out=10, kind="root", session="a"))
        sim.run()
        hogs = [Request(prompt=1500, out=20) for _ in range(2)]
        for h in hogs:
            srv.submit(h)
        sim.run()
        t2 = Request(prompt=3200, out=5, kind="root", session="a")
        srv.submit(t2)
        sim.run()
        assert (t2.cached > 2900) == survives, policy


def test_agent_policy_prioritizes_root_and_promotes():
    sim, srv = _server(policy="agent", spec_max_running=2)  # hard cap on running bets
    specs = [Request(prompt=50, out=100, spec=True) for _ in range(6)]
    for s in specs:
        srv.submit(s)
    root = Request(prompt=50, out=100, kind="root")
    srv.submit(root)
    sim.run(until=0.05)
    assert root.state == "running"
    assert sum(s.state == "running" for s in specs) <= 2
    srv.promote(specs[-1])
    sim.run()
    assert all(s.state == "done" for s in specs)


# ------------------------------------------------------------------ trace fidelity
@pytest.mark.parametrize("name", NAMES)
def test_trace_counts_match_measured(name):
    """Dispatch / hit / miss / evict counts equal the medians in runs.csv."""
    m = suite.measured_medians()
    row = m[(m.pattern == name) & (m["mode"] == "spec")].iloc[0]
    t = trace_of(name)
    hits = sum(1 for op in t.spec_exec if op[0] == "force")
    misses = sum(1 for op in t.spec_exec if op[0] == "run") + sum(
        len(op[1]) for op in t.spec_exec if op[0] == "batch")
    evicted = sum(1 for it in t.items for op in it.ops if op[0] == "evict") + len(t.spec_end_evict)
    assert len(t.specs) == row.dispatched
    assert hits == row.hits and misses == row.misses and evicted == row.evicted


# ------------------------------------------------------------------ agent policies
def _fixed_run(name, policy, lat=0.3):
    t = trace_of(name)
    sim = Sim()
    be = FixedBackend(sim, lambda info: lat)
    p = sim.process(run_turn(sim, t, PolicyCfg(policy), be, ScriptedStream(sim, t, 60.0)))
    sim.run()
    return p.value, t


def test_baseline_is_stream_plus_serial_calls():
    r, t = _fixed_run("serial_chain6", "baseline")
    assert math.isclose(r.wall, t.n_deltas * 0.1 + 6 * 0.3, rel_tol=1e-9)


def test_map16_spec_is_stream_plus_one_call():
    r, t = _fixed_run("map16", "shadow")
    assert r.wall <= t.n_deltas * 0.1 + 0.3 + 1e-9


@pytest.mark.parametrize("name", NAMES)
def test_speculation_never_slower_and_dataflow_never_behind_shadow(name):
    base, _ = _fixed_run(name, "baseline")
    sh, _ = _fixed_run(name, "shadow")
    df, _ = _fixed_run(name, "dataflow")
    lit, _ = _fixed_run(name, "literal")
    assert sh.wall <= base.wall + 1e-6
    assert df.wall <= sh.wall + 1e-6
    assert lit.wall <= base.wall + 1e-6


def test_server_runs_are_deterministic():
    def once():
        t = trace_of("map16")
        sim = Sim()
        srv = Server(sim, StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS))
        be = ServerBackend(sim, srv, OutputModel(mean=30, sigma=0.3, seed=1))
        p = sim.process(run_turn(sim, t, PolicyCfg("shadow"), be, ScriptedStream(sim, t, 60)))
        sim.run()
        return p.value.wall

    assert once() == once()


def test_full_preemption_step_retries_instead_of_failing():
    # two long requests in a KV that fits only one: the step that preempts
    # everything running must not be treated as a deadlock
    sim, srv = _server(kv_blocks=40)  # 640 tokens
    reqs = [Request(prompt=300, out=300) for _ in range(2)]
    for r in reqs:
        srv.submit(r)
    sim.run()
    assert all(r.state == "done" for r in reqs)


def test_agent_policy_admits_spec_when_cache_holds_kv():
    sim, srv = _server(policy="agent", kv_blocks=200)
    srv.submit(Request(prompt=3000, out=5, kind="root", session="a"))
    sim.run()  # root prefix now parked in the cache, free blocks low
    s = Request(prompt=200, out=5, spec=True)
    srv.submit(s)
    sim.run()
    assert s.state == "done"


def test_agent_preempts_spec_for_normal_work_without_corrupting_queues():
    sim, srv = _server(policy="agent", kv_blocks=60, spec_max_running=8)  # 960 tokens
    specs = [Request(prompt=300, out=200, spec=True) for _ in range(3)]
    for s in specs:
        srv.submit(s)
    sim.run(until=0.02)
    normal = [Request(prompt=400, out=50) for _ in range(2)]
    for r in normal:
        srv.submit(r)
    sim.run()
    assert all(r.state == "done" for r in specs + normal)
    assert sum(s.preemptions for s in specs) > 0
    assert _all_released(srv)


# ------------------------------------------------------------------ vllm-priority
def test_vllm_priority_waiting_order_is_value_then_arrival():
    # max_num_seqs=1: requests run one at a time, in waiting-queue order
    order = {}
    for policy in ("vllm-priority", "priority"):
        sim, srv = _server(policy=policy, max_num_seqs=1)
        reqs = {"spec": Request(prompt=50, out=3, spec=True), "normal": Request(prompt=50, out=3),
                "root": Request(prompt=50, out=3, kind="root")}
        for r in reqs.values():
            srv.submit(r)
        sim.run()
        order[policy] = sorted(reqs, key=lambda k: reqs[k].t_sched)
    # vLLM: root and normal both send priority 0, so arrival breaks the tie
    assert order["vllm-priority"] == ["normal", "root", "spec"]
    assert order["priority"] == ["root", "normal", "spec"]


def test_vllm_priority_keeps_running_in_admission_order():
    for policy, first in (("vllm-priority", "spec"), ("priority", "root")):
        sim, srv = _server(policy=policy)
        spec = Request(prompt=300, out=200, spec=True)
        srv.submit(spec)
        sim.run(until=0.01)
        root = Request(prompt=300, out=200, kind="root")
        srv.submit(root)
        sim.run(until=0.1)
        assert {spec.state, root.state} == {"running"}
        assert srv.running[0] is (spec if first == "spec" else root), policy


def test_vllm_priority_victim_is_lowest_priority_not_newest():
    for policy, victim in (("vllm-priority", "spec"), ("fcfs", "root")):
        sim, srv = _server(policy=policy, kv_blocks=40)  # 640 tokens: both cannot finish
        spec = Request(prompt=200, out=300, spec=True)
        srv.submit(spec)
        sim.run(until=0.005)
        root = Request(prompt=200, out=300, kind="root")
        srv.submit(root)
        sim.run()
        assert spec.state == root.state == "done"
        pre = {"spec": spec.preemptions, "root": root.preemptions}
        assert pre[victim] > 0 and pre["root" if victim == "spec" else "spec"] == 0, policy


def test_vllm_priority_self_preemption_ends_the_running_loop():
    # vLLM 0.32 scheduler.py: "if preempted_req == request: break", then "if new_blocks is
    # None: break". A spec admitted before the root is its own victim; the root behind it
    # is not scheduled in that step.
    sim, srv = _server(policy="vllm-priority", kv_blocks=400)
    spec = Request(prompt=300, out=500, spec=True)
    srv.submit(spec)
    sim.run(until=0.01)
    root = Request(prompt=300, out=500, kind="root")
    srv.submit(root)
    sim.run(until=0.1)
    assert srv.running == [spec, root] and spec.need_prefill == root.need_prefill == 0
    spec.ctx = spec.blocks * BLOCK  # its next token needs a new block
    root.ctx = root.blocks * BLOCK - 2  # its next token fits
    srv.kv.free = 0
    assert srv._schedule() == []
    assert spec.state == "waiting" and spec.preemptions == 1 and srv.running == [root]


def test_vllm_priority_waiting_request_never_preempts_and_no_promotion():
    sim, srv = _server(policy="vllm-priority", kv_blocks=40)
    spec = Request(prompt=500, out=100, spec=True)
    srv.submit(spec)
    sim.run(until=0.01)
    root = Request(prompt=300, out=5, kind="root")
    srv.submit(root)
    srv.promote(spec)  # no API for this in vLLM: a no-op
    sim.run()
    assert spec.priority == 2 and spec.spec
    assert spec.preemptions == 0
    assert root.t_sched >= spec.t_done
