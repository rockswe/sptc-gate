"""kaggle/bench_general.py against a trivial fake streaming server (no GPU, no vLLM)."""

import argparse
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

from sptc_sim.general import REACT_MODES, ReactCfg, react_plan

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "kaggle" / "fake_openai_server.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("bench_general", ROOT / "kaggle" / "bench_general.py")
serve = _load("fake_openai_server", FAKE).serve
REJECT_BETS = ("--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler",
               "--additional-config", json.dumps({"sptc": {"free_window": 0}}))

FAST = dict(steps=3, tool_p50=0.02, tool_p99=0.05, step_out=12.0, answer_out=6.0)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(B, "BASE", {**B.BASE, **FAST})
    monkeypatch.setattr(B, "BATCH", {**B.BATCH, "prompt": 50, "out": 10.0})


def args(port_, **kw):
    return argparse.Namespace(base_url=f"http://127.0.0.1:{port_}/v1", model="fake",
                              run_id="t", **kw)


@pytest.mark.parametrize("mode", list(REACT_MODES))
def test_plan_matches_the_simulator(mode):
    cfg = ReactCfg(**REACT_MODES[mode])
    for sid in (0, 1, 1000, 7003):
        assert B.react_plan(B.cfg_for(mode), 0, sid) == react_plan(cfg, 0, sid)
    sim_defaults = {k: getattr(ReactCfg(), k) for k in B.BASE}
    assert sim_defaults == B.BASE


def test_stream_counts_tokens_and_cancels():
    port = free_port()
    srv, seen = serve(port, "--step-ms", "1")
    s = B.Stream(f"http://127.0.0.1:{port}/v1", "fake", "hello", 20)
    s.done.wait(10)
    assert s.ok and len(s.times) == 20 and s.finish == "length" and s.tpot is not None
    assert seen[0]["ignore_eos"] and seen[0]["stream"]
    slow = B.Stream(f"http://127.0.0.1:{port}/v1", "fake", "hello", 5000)
    while len(slow.times) < 3:
        slow.done.wait(0.01)
    slow.cancel()
    assert slow.done.wait(5) and not slow.ok and slow.finish == "client_abort"
    srv.shutdown()


@pytest.mark.parametrize("arm", ["fcfs", "priority", "plugin"])
def test_session_tags_bets_per_arm(fast, arm):
    port = free_port()
    srv, seen = serve(port, "--step-ms", "0.5")
    rec = B.react_session(args(port), arm, "next3", sid=2)
    srv.shutdown()
    assert rec["bets"] == 3 * (FAST["steps"] - 1)
    bets = [r for r in seen if r.get("priority") or r.get("vllm_xargs")]
    want = {"fcfs": 0, "priority": rec["bets"], "plugin": rec["bets"]}[arm]
    assert len(bets) == want
    if arm == "priority":
        assert all(r["priority"] == 1 for r in bets)
    if arm == "plugin":
        assert all(r["vllm_xargs"] == {"sptc_class": "bet"} for r in bets)
    assert rec["used"] == rec["hits"]  # nothing refused, nothing stalled on a fast server
    assert 0 < rec["wasted_tokens"] < rec["tokens"]


def test_refused_guess_is_reissued_untagged(fast):
    port = free_port()
    srv, seen = serve(port, "--step-ms", "0.5", *REJECT_BETS)
    rec = B.react_session(args(port), "plugin", "next3", sid=2)
    srv.shutdown()
    assert rec["rejected"] == rec["bets"] and rec["used"] == 0
    roots = [r for r in seen if not r.get("vllm_xargs")]
    assert len(roots) == FAST["steps"]  # every step ran as normal work
    assert rec["wasted_tokens"] == 0


def test_matrix_runs_every_arm_with_a_fake_server(fast, tmp_path):
    port = free_port()
    cmd = f"{sys.executable} {FAKE} {{model}} --port {{port}} --step-ms 0.5 --max-running 64"
    a = args(port, out=str(tmp_path), quick=True, modes="none,action", agents="1,2",
             sessions=1, batch_workers=2, arms="fcfs,priority,plugin", serve_cmd=cmd,
             port=port, settle_s=0.0)
    res = B.matrix(a)
    rows = res["react"]
    assert {(r["arm"], r["mode"], r["agents"]) for r in rows if not r["batch_workers"]} == {
        (arm, m, n) for arm in ("fcfs", "priority", "plugin") for m in ("none", "action")
        for n in (1, 2)}
    batch = [r for r in rows if r["batch_workers"]]
    assert len(batch) == 3
    # the fake server now gets each arm's flags: under the plugin a short cell may refuse
    # every background bet (the worker backs off 1 s), so only stock must finish jobs
    for r in batch:
        assert r["batch_jobs_s"] > 0 or (r["arm"] == "plugin" and r["batch_refused"] > 0), r
    assert json.loads((tmp_path / "general_partial.json").read_text())["react"]
    log = (tmp_path / "vllm_general_plugin.log").read_text()
    assert "'plugin': True" in log  # the arm's flags reached the (fake) server
    assert "'policy': 'priority'" in (tmp_path / "vllm_general_priority.log").read_text()
    assert all("host_cpu_util" in r and "gpu" in r for r in rows)
    # resume: a rerun keeps the finished cells and starts no server; a lost cell is redone
    again = B.matrix(a)
    assert again["react"] == rows and log == (tmp_path / "vllm_general_plugin.log").read_text()
    part = tmp_path / "general_partial.json"
    kept = [r for r in rows if not (r["arm"] == "priority" and r["mode"] == "action"
                                    and r["agents"] == 2)]
    part.write_text(json.dumps({"react": kept}))
    redo = B.matrix(a)["react"]
    assert redo[:-1] == kept and (redo[-1]["arm"], redo[-1]["mode"], redo[-1]["agents"]) == (
        "priority", "action", 2)
    # a server already on the port: the arm is skipped, nothing runs against it
    srv, _ = serve(port, "--step-ms", "0.5")
    part.unlink()
    try:
        assert B.matrix(a)["react"] == []
    finally:
        srv.shutdown()


def test_estimate_quick_is_small():
    a = argparse.Namespace(quick=True, arms="fcfs,priority,plugin")
    e = B.estimate(a)
    assert 10 < e["gpu_min"] < 60


def test_quick_is_a_subset_of_full_with_pre_registered_claims():
    """The quick matrix runs some of the full matrix's cells with the same sessions, so
    the claims on those cells apply to it unchanged."""
    q, f = B.QUICK, B.FULL
    assert set(q["modes"].split(",")) <= set(f["modes"].split(","))
    assert set(q["agents"].split(",")) <= set(f["agents"].split(","))
    assert q["sessions"] == f["sessions"]
    pred = json.loads((ROOT / "results" / "general" / "predictions.json").read_text())
    assert pred["quick_claims"]
    quick = {(c["arm"], c["mode"], c["agents"]) for c in pred["quick_cells"]}
    assert quick == {(arm, m, int(n)) for arm in ("fcfs", "priority", "plugin")
                     for m in q["modes"].split(",") for n in q["agents"].split(",")}
