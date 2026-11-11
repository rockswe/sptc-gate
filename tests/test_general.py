"""sptc_sim/general.py: the plugin-faithful server, the ReAct/branch/batch workloads."""

import math

from sptc_sim.des import Sim
from sptc_sim.general import (REACT_MODES, BatchCfg, BatchStats, Call, GeneralServer, GRequest,
                              ReactCfg, batch_worker, branch_turns, plugin_config, react_plan,
                              react_session)
from sptc_sim.hardware import GPUS, GRAPHS, MODELS, StepCost
from sptc_sim.server import BLOCK, PRIO_NORMAL, PRIO_SPEC, ServerConfig

COST = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)


def srv(sim, sched="plugin", **kw):
    if sched == "plugin":
        cfg = ServerConfig(**plugin_config(kw.pop("free_window", 8)), **kw)
    else:
        cfg = ServerConfig(policy=sched, **kw)
    return GeneralServer(sim, COST, cfg)


def react_lat(sched, mode="none", n=12, rate=2.0):
    sim = Sim()
    s = srv(sim, sched)
    calls, procs = [], []

    def arrivals():
        for i in range(n):
            yield sim.timeout(1.0 / rate)
            procs.append(sim.process(react_session(sim, s, ReactCfg(**REACT_MODES[mode]), i, 0,
                                                   0.004, calls)))

    sim.process(arrivals())
    sim.run()
    return [p.value.latency for p in procs], calls


def test_untagged_traffic_is_fcfs_under_every_scheduler():
    base, _ = react_lat("fcfs")
    assert react_lat("priority")[0] == base
    assert react_lat("plugin")[0] == base


def test_react_plan_is_deterministic_and_cited_defaults():
    cfg = ReactCfg(**REACT_MODES["action"])
    assert react_plan(cfg, 0, 3) == react_plan(cfg, 0, 3)
    assert react_plan(cfg, 0, 3) != react_plan(cfg, 0, 4)
    assert (cfg.k, cfg.hit, cfg.tool_p50) == (3, 0.40, 1.5)  # SPAgent
    plan = [x for s in range(400) for x in react_plan(cfg, 1, s)]
    assert abs(sum(h for _, _, h in plan) / len(plan) - 0.40) < 0.03
    tools = sorted(t for _, t, _ in plan)
    assert abs(tools[len(tools) // 2] - 1.5) < 0.1


def test_bet_rejected_when_window_full_admitted_when_idle():
    sim = Sim()
    s = srv(sim, free_window=1)
    root = Call(sim, s, GRequest(prompt=100, out=50, kind="root"), 0.0)
    sim.run(until=0.05)  # root running: one sequence fills the window
    bet = Call(sim, s, GRequest(prompt=50, out=5, spec=True, claimed=False), 0.0)
    sim.run(until=root.done)
    assert bet.done.value == "rejected"
    later = Call(sim, s, GRequest(prompt=50, out=5, spec=True, claimed=False), 0.0)
    sim.run()
    assert later.done.value == "ok"


def test_bet_sent_with_its_root_is_gated_after_the_root():
    """The plugin gates at admission, after the step's normal work: a candidate sent
    in the same instant as its root is admitted when the window has room."""
    sim = Sim()
    s = srv(sim)
    Call(sim, s, GRequest(prompt=100, out=20, kind="root"), 0.0)
    bet = Call(sim, s, GRequest(prompt=50, out=5, spec=True, claimed=False), 0.0)
    sim.run()
    assert bet.done.value == "ok"


def test_kv_pressure_drops_bets_but_requeues_background():
    for bg, want in ((False, "dropped"), (True, "ok")):
        sim = Sim()
        s = srv(sim, kv_blocks=60)  # 960 tokens of KV
        victim = Call(sim, s, GRequest(prompt=16, out=900, spec=True, bg=bg, claimed=False), 0.0)
        sim.run(until=0.02)
        root = Call(sim, s, GRequest(prompt=16, out=700, kind="root"), 0.0)
        sim.run()
        assert root.done.value == "ok"
        assert victim.done.value == want
        assert victim.req.preemptions >= 1


def test_no_promotion_and_two_level_priority():
    sim = Sim()
    s = srv(sim, "priority")
    root = GRequest(prompt=10, out=2, kind="root")
    sub = GRequest(prompt=10, out=2)
    bet = GRequest(prompt=10, out=2, spec=True)
    for r in (root, sub, bet):
        s.submit(r)
    assert (root.priority, sub.priority, bet.priority) == (PRIO_NORMAL, PRIO_NORMAL, PRIO_SPEC)
    s.promote(bet)
    assert bet.priority == PRIO_SPEC and bet.spec  # vLLM cannot reclass a request
    sim.run()


def test_right_guess_extends_the_session_prefix_cache():
    sim = Sim()
    s = srv(sim, "fcfs")
    sess = ("agent", 0)
    r1 = GRequest(prompt=1000, out=100, kind="root", session=sess)
    s.submit(r1)
    sim.run()
    cached = s.kv.entries[sess].tokens
    g = GRequest(prompt=300, out=100, shared=1100, cache_as=sess)
    s.submit(g)
    sim.run()
    assert s.kv.entries[sess].tokens > cached + 300
    r2 = GRequest(prompt=1500, out=10, kind="root", session=sess)
    s.submit(r2)
    sim.run()
    assert r2.hit_tokens >= 1300 // BLOCK * BLOCK


def test_react_next_saves_time_when_idle_and_wastes_misses():
    none, _ = react_lat("fcfs", "none", n=6, rate=0.05)
    nxt, calls = react_lat("fcfs", "next3", n=6, rate=0.05)
    assert sum(nxt) < sum(none)
    lost = [c.req for c in calls if c.submitted and not c.req.claimed]
    assert lost and all(r.kind == "sub" for r in lost)


def test_branch_literal_launches_both_arms():
    t = branch_turns()[1].trace
    assert len(t.literal_specs) == 6 and len(t.literal_end_evict) == 3


def test_batch_reissue_turns_a_refused_bet_into_normal_work():
    sim = Sim()
    s = srv(sim, free_window=0)  # every bet refused
    stop = sim.event()
    stats = BatchStats()
    log = []
    sim.process(batch_worker(sim, s, BatchCfg(tag="reissue", prompt=100, out=10), 0, 0, 0.0,
                             stop, stats, log))
    sim.call_at(2.0, stop.succeed)
    sim.run()
    assert stats.rejected >= 1 and stats.jobs >= 1
    assert log[0].req.spec and not log[1].req.spec
    assert math.isclose(stats.rejected, sum(c.done.value == "rejected" for c in log))


def test_action_candidates_prefill_only_their_suffix():
    """vLLM caches the root's blocks when it is scheduled, so a candidate sent with its
    root hits ctx (observation included) up to the last full block."""
    _, calls = react_lat("fcfs", "action", n=3, rate=0.5)
    cfg = ReactCfg(**REACT_MODES["action"])
    cands = [c.req for c in calls if c.req.tag.startswith("cand:")]
    assert cands
    for r in cands:
        assert cfg.cand_suffix <= r.prompt < cfg.cand_suffix + BLOCK
        assert r.shared % BLOCK == 0


def test_priority_running_keeps_admission_order_and_victim_is_lowest_priority():
    """vLLM priority never sorts `running`; under KV pressure the victim is
    max(running, (priority, arrival)), even if it was scheduled earlier in the step."""
    sim = Sim()
    s = srv(sim, "priority", kv_blocks=60)  # 960 tokens of KV
    bet = Call(sim, s, GRequest(prompt=16, out=900, spec=True), 0.0)
    sim.run(until=0.02)
    root = Call(sim, s, GRequest(prompt=16, out=700, kind="root"), 0.0)
    sim.run(until=0.05)
    assert s.running == [bet.req, root.req]  # the bet keeps its place ahead of the root
    sim.run()
    assert root.done.value == bet.done.value == "ok"
    assert bet.req.preemptions >= 1 and root.req.preemptions == 0
    assert root.req.t_done < bet.req.t_done


def test_waste_counts_recompute_and_skips_jobs_cut_at_the_end():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "experiments" / "general.py"
    spec = importlib.util.spec_from_file_location("exp_general", path)
    G = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(G)
    sim = Sim()
    s = srv(sim, "fcfs", kv_blocks=60)
    log = []
    a = Call(sim, s, GRequest(prompt=16, out=900), 0.0, log)
    sim.run(until=0.02)
    b = Call(sim, s, GRequest(prompt=16, out=700, kind="root"), 0.0, log)
    sim.run()
    assert a.done.value == b.done.value == "ok"
    assert sum(c.req.preemptions for c in log) >= 1
    w = G.waste(log)
    assert w["unused_frac"] == 0 and w["redone_frac"] > 0 and w["wasted_frac"] == w["redone_frac"]
    for c in log:
        if c.req.preemptions == 0:
            assert G.redone(c.req) == 0

    sim = Sim()
    s = srv(sim, "fcfs")
    stop, stats, log = sim.event(), BatchStats(), []
    sim.process(batch_worker(sim, s, BatchCfg(prompt=100, out=400), 0, 0, 0.0, stop, stats,
                             log))
    sim.call_at(0.5, stop.succeed)
    sim.run()
    assert log[-1].req.cut and log[-1].req.claimed
    w = G.waste(log)
    assert w["wasted_frac"] == 0 and w["cut_frac"] > 0


def test_full_isl_admission_waits_for_the_whole_prompt_to_fit():
    """vLLM 0.32 scheduler_reserve_full_isl (default True): a waiting request is admitted
    only when its whole sequence fits in KV, not just its first chunk."""
    out = {}
    for full in (True, False):
        sim = Sim()
        cfg = ServerConfig(policy="fcfs", kv_blocks=60, max_batched_tokens=128)
        s = GeneralServer(sim, COST, cfg, reserve_full_isl=full)
        a = Call(sim, s, GRequest(prompt=400, out=50), 0.0)  # at most 29 blocks
        sim.run(until=0.02)
        b = Call(sim, s, GRequest(prompt=700, out=10, kind="root"), 0.0)  # 44 blocks
        sim.run()
        assert a.done.value == b.done.value == "ok"
        out[full] = (b.req.t_sched >= a.req.t_done, a.req.preemptions + b.req.preemptions)
    assert out[True] == (True, 0)  # waits for the room, no thrash
    assert out[False][0] is False and out[False][1] >= 1  # first chunk only: over-admits
