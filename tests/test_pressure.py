"""The simulated pressure study (experiments/pressure.py): the simulator options it adds.
PolicyCfg.tag_early, PolicyCfg.rejected_force, ProxySim's bets mode, and
sweep_predict.sim_run's server overrides and metrics (MeteredServer)."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import sweep_predict as w2  # noqa: E402

from sptc_sim import suite  # noqa: E402
from sptc_sim.agent import (CallHandle, FixedBackend, OutputModel, PolicyCfg,  # noqa: E402
                            ScriptedStream, ServerBackend, run_turn)
from sptc_sim.calib import trace_of  # noqa: E402
from sptc_sim.des import Sim  # noqa: E402
from sptc_sim.hardware import GPUS, GRAPHS, MODELS, StepCost  # noqa: E402
from sptc_sim.server import Request, Server, ServerConfig  # noqa: E402
from sptc_sim.trace import CallInfo, compile_turn  # noqa: E402

COST = StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)


# ----------------------------------------------------------------------------- tag_early
def _requests(tag_early: bool) -> list[Request]:
    t = trace_of("map16")
    sim = Sim()
    srv = Server(sim, COST)
    be = ServerBackend(sim, srv, OutputModel(mean=30, sigma=0.3, seed=1))
    pol = PolicyCfg("shadow", waste_frac=1.0, decoys_bypass_pool=True, mark_spec="guesses",
                    tag_early=tag_early)
    sim.process(run_turn(sim, t, pol, be, ScriptedStream(sim, t, 60.0)))
    sim.run()
    return be.requests


@pytest.mark.parametrize("tag_early", [True, False])
def test_tag_early_tags_only_bets_when_off(tag_early):
    reqs = _requests(tag_early)
    real = [r for r in reqs if not r.tag.endswith("~decoy")]
    decoys = [r for r in reqs if r.tag.endswith("~decoy")]
    assert len(real) == 16 and len(decoys) == 16
    assert all(r.spec and r.early for r in decoys)  # bets keep their class either way
    assert all(not r.spec and r.early == tag_early for r in real)
    # untagged or not, a speculative call is still wasted work until the real run claims it
    assert all(not r.claimed for r in decoys) and all(r.claimed for r in real)


# ----------------------------------------------------------------------------- ProxySim
def test_proxy_spec_mode_gates_every_bet_label():
    sim = Sim()
    srv = SimpleNamespace(running=[SimpleNamespace(kind="root")] * 2, waiting=[])
    real, decoy = CallInfo("llm_query", "a", 40), CallInfo("llm_query", "a~decoy", 40)
    p = w2.ProxySim(srv, "bets:2", bets="spec")
    assert p.is_bet(real, True) and p.is_bet(decoy, True) and not p.is_bet(decoy, False)
    old = w2.ProxySim(srv, "bets:2")  # run 2's: decoys only, whatever the label
    assert old.is_bet(decoy, False) and not old.is_bet(real, True)
    live = sim.event()
    p.live = [SimpleNamespace(done=live, info=real, spec=True),
              SimpleNamespace(done=sim.event(), info=real, spec=False)]
    assert p.admit_bet()  # one bet in flight + 1 <= 2
    p.live.append(SimpleNamespace(done=sim.event(), info=decoy, spec=True))
    assert not p.admit_bet()
    live.succeed()
    assert p.admit_bet()


# ----------------------------------------------------------------------------- abort
class RefusingBackend(FixedBackend):
    """Every call sent as a bet is refused at once (a full client-side cap); the rest take
    `lat` seconds. Records every start."""

    def __init__(self, sim, lat):
        super().__init__(sim, lambda info: lat)
        self.started: list[tuple[str, bool]] = []

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        self.started.append((info.rid, spec))
        if spec:
            h = CallHandle(self.sim.event(), info, spec, self.sim.now, backend=self)
            h.rejected = True
            h.done.succeed(h)
            return h
        return super().start(info, spec, salt, prog_t, early, tag_early)


def _refused_turn(rejected_force: str, lat: float = 0.3):
    t = trace_of("two_stage")  # stage 2 dispatches after forcing stage 1's results
    sim = Sim()
    be = RefusingBackend(sim, lat)
    pol = PolicyCfg("shadow", mark_spec="all", rejected_force=rejected_force)
    p = sim.process(run_turn(sim, t, pol, be, ScriptedStream(sim, t, 60.0)))
    sim.run()
    return p.value, t, be


def test_abort_stops_the_shadow_at_the_first_rejected_force():
    r, t, be = _refused_turn("abort")
    forced = [op[1] for it in t.items for op in it.ops if op[0] == "force"]
    assert r.shadow_stop == forced[0]
    bets = [rid for rid, spec in be.started if spec]
    assert len(bets) == r.dispatched == 6  # stage 1 only: stage 2 was never dispatched
    # the real run re-runs the 6 refused calls when it claims them and runs the 6 calls
    # the shadow never dispatched as misses, one after another
    real = [rid for rid, spec in be.started if not spec]
    assert len(real) == len(set(real)) == 12
    assert r.reissued == 6 and r.misses == 12 and r.hits == 0
    assert math.isclose(r.wall, t.n_deltas * 0.1 + 12 * 0.3, rel_tol=1e-9)


def test_reissue_keeps_the_shadow_going():
    r, t, be = _refused_turn("reissue")
    assert r.shadow_stop is None
    assert len([1 for _, spec in be.started if spec]) == 12  # stage 2 dispatched too
    assert r.reissued == 12
    ab, _, _ = _refused_turn("abort")
    assert r.wall < ab.wall


def test_abort_is_a_no_op_when_nothing_is_refused():
    t = trace_of("two_stage")
    walls = []
    for mode in ("reissue", "abort"):
        sim = Sim()
        p = sim.process(run_turn(sim, t, PolicyCfg("shadow", rejected_force=mode),
                                 FixedBackend(sim, lambda info: 0.3),
                                 ScriptedStream(sim, t, 60.0)))
        sim.run()
        assert p.value.shadow_stop is None
        walls.append(p.value.wall)
    assert walls[0] == walls[1]


def test_rejected_force_values():
    with pytest.raises(ValueError):
        PolicyCfg("shadow", rejected_force="drop")
    with pytest.raises(ValueError):
        PolicyCfg("dataflow", rejected_force="abort")
    with pytest.raises(ValueError):
        PolicyCfg("shadow", decoy_at_call=True)  # needs decoys_bypass_pool


# ----------------------------------------------------------------------------- decoy order
def _gate_order(decoy_at_call: bool) -> list[str]:
    t = trace_of("map16")  # 16 loop peeks dispatched in one burst
    sim = Sim()
    be = RefusingBackend(sim, 0.3)
    pol = PolicyCfg("shadow", waste_frac=1.0, decoys_bypass_pool=True, mark_spec="guesses",
                    decoy_at_call=decoy_at_call)
    sim.process(run_turn(sim, t, pol, be, ScriptedStream(sim, t, 60.0)))
    sim.run()
    return ["d" if rid.endswith("~decoy") else "r" for rid, _ in be.started[:32]]


def test_decoys_reach_a_gate_by_pairs_when_started_by_their_call():
    assert _gate_order(False) == ["d"] * 16 + ["r"] * 16  # a burst's decoys all go first
    assert _gate_order(True) == ["d", "r"] * 16  # as the bench: decoy thread, then the call


# ----------------------------------------------------------------------------- metering
def _metered(**kw):
    sim = Sim()
    srv = w2.MeteredServer(sim, COST, ServerConfig(max_batched_tokens=2048, kv_blocks=6, **kw))
    root = Request(prompt=40, out=40, kind="root")
    bet = Request(prompt=20, out=40, spec=True, early=True, claimed=False)
    srv.submit(root)
    srv.submit(bet)
    sim.run()
    return srv, root, bet


def test_a_dropped_bet_is_not_a_preemption():
    srv, root, bet = _metered(policy="agent", reject_bets=True, plugin_semantics=True,
                              free_window=8, spec_kv_reserve=0.0)
    assert root.state == "done" and bet.state == "aborted"
    assert (srv.dropped, srv.preempted) == (1, 0)
    assert srv.peak["kv_blocks"] == 6 and srv.peak["running"] == 2


def test_fcfs_requeues_and_counts_preemptions():
    srv, root, bet = _metered()
    assert root.state == bet.state == "done"
    assert srv.dropped == 0 and srv.preempted == bet.preemptions + root.preemptions >= 1
    assert srv.peak["waiting"] >= 1 and srv.queue_any_s > 0


# ----------------------------------------------------------------------------- sim_run
@pytest.fixture(scope="module")
def calib():
    """prereg_v3's P1 (client 30 ms, seq_cap 24), without the client-overhead grid fit."""
    c = w2.t4.fit_cost(0.03)
    cost = w2.CappedStepCost(c.gpu, c.model, c.tp, c.ov, c.decode_table, seq_cap=24)
    tr: dict = {}

    def trace(n):
        if n not in tr:
            tr[n] = compile_turn(suite.response_text(n), suite.context())
        return tr[n]

    tables = w2.t4.token_tables(trace)
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4)
              for n in w2.vb.WORKLOADS["mix4"]["patterns"].split(",")}
    return cost, tables, traces


def _run(calib, arm, cfg, **extra):
    cost, tables, traces = calib
    setting = lambda a: {**w2.SIM_ARMS["fcfs"], "cfg": cfg, **extra}  # noqa: E731
    return w2.sim_run(cost, tables, w2.vb.ARM[arm], 4, traces, 2, setting)


def test_sim_run_server_overrides_and_metrics(calib):
    rec = _run(calib, "fcfs/spec+bad", {"kv_blocks": 120, "max_num_seqs": 16})
    assert rec["sim_kv_blocks"] == 120 and rec["sim_max_num_seqs"] == 16
    m = rec["server_metrics"]
    assert m["max_running"] <= 16 and m["max_waiting"] > 0 and m["preemptions"] > 0
    assert 0 < m["max_kv"] <= 1 and rec["sim_max_kv_blocks"] <= 120
    assert 0 < rec["sim_queue_frac"] <= 1 and rec["sim_queue_mean"] > 0
    base = _run(calib, "fcfs/spec+bad", {})
    assert base["sim_kv_blocks"] == w2.KV_TOKENS // w2.BLOCK and base["sim_max_num_seqs"] == 256
    assert base["server_metrics"]["preemptions"] == 0


def test_sim_run_cap_on_every_bet(calib):
    """mark_spec all + proxy_bets spec: the cap refuses real speculative calls too, the
    real run re-runs them, and the abort stops the shadow."""
    rec = _run(calib, "fcfs/spec+bad", {}, proxy="window:8", proxy_bets="spec",
               rejected_force="abort")
    ses = rec["sessions"]
    refused = sum(b["outcome"] == "rejected" for s in ses for b in s["real_bets"])
    assert refused > 0 and sum(s["reissued"] for s in ses) == refused
    assert any(s["shadow_stopped"] for s in ses)
    old = _run(calib, "fcfs/spec+bad", {}, proxy="window:8")  # decoys only, as run 2
    assert not any(s["reissued"] or s["shadow_stopped"] for s in old["sessions"])
    assert not any(b["outcome"] == "rejected" for s in old["sessions"] for b in s["real_bets"])
    assert sum(d["outcome"] == "rejected" for s in old["sessions"] for d in s["decoys"]) > 0


# ----------------------------------------------------------------------------- the bench
def test_bench_runs_the_simulated_pressure_arms():
    """kaggle/vllm_bench.py's pressure preset runs pressure.py's arms,
    the speculative calls sent as bets exactly in workload both, and reads the decision
    rule with pressure.py's thresholds; step 5's arms are the same on the default servers."""
    import pressure as PR

    vb = w2.vb
    assert vb.PRESSURE_ARMS == list(PR.ARMS) and vb.PRESSURE_REF == PR.REF
    for name, (_, wl, arm) in PR.ARMS.items():
        x = vb.ARM[name]
        assert (x.server, x.mode, x.decoys, x.tags, x.gate, x.workload) == (
            arm.server, arm.mode, arm.decoys, arm.tags, arm.gate, arm.workload)
        assert x.spec_kind == ("bet" if wl == "both" else "early")
    assert (vb.PRESSURE_CLEAR, vb.PRESSURE_QUIET) == (PR.CLEAR, PR.QUIET)
    assert (vb.D1_MARGIN, vb.D1_AGENTS, vb.WINDOW_CAP) == (PR.RULE_MARGIN, PR.AGENTS, PR.CAP)
    assert {k: vb.D1_ARMS[k] for k in vb.D1_RULE} == PR.D1_ARMS
    assert all(n.replace("-d/", "-p/") in PR.ARMS for n in vb.BOTH_DEFAULT_ARMS)
