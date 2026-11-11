"""End to end: `vllm_bench.py sweep --launch` against the fake server, with spec-ptc's real
Harness driving the agents in spawned processes, exactly as on Kaggle but with
fake_openai_server.py in place of `vllm serve`. Checks the request fields each arm sends,
every decoy's logged outcome, the retry of a silently failed run, and resume.

Needs spec-ptc (found through the installed spec_ptc package, or SPTC_SPEC_PTC). About a
minute of mostly idle time; run it on its own:
  python -m pytest -q kaggle/tests/test_bench_e2e.py
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from conftest import FAKE, KAGGLE, free_port

import vllm_bench as vb


def _spec_ptc() -> str | None:
    if os.environ.get("SPTC_SPEC_PTC"):
        return os.environ["SPTC_SPEC_PTC"]
    try:
        import spec_ptc
    except ImportError:
        return None
    # the checkout the installed package comes from (benchmark/ sits next to src/)
    root = Path(spec_ptc.__file__).resolve().parents[1]
    return str(root) if (root / "benchmark" / "suite").is_dir() else None


SPEC_PTC = _spec_ptc()
pytestmark = pytest.mark.skipif(SPEC_PTC is None, reason="spec-ptc checkout not found")
ARMS = "fcfs/nospec,fcfs/spec+bad,prio/spec+bad,plugin/spec+bad"
BASELINE_ARMS = ["fcfs-b4/spec+bad", "proxy/spec+bad", "proxy-sem/spec+bad", "prio-bets/spec+bad",
                 "plugin-b4/spec+bad", "fcfs-b4/spec"]
# each fake server fails the first request of this prompt prefix once: every spec+bad arm's
# 1-agent run (the prefix names the client workload, not the arm)
FAIL_SALT = "[spec d1 n1 r0]"
FLAGS = {"fcfs": {"policy": "fcfs", "plugin": False},  # the fake server's log, per server
         "priority": {"policy": "priority", "plugin": False},
         "plugin": {"policy": "fcfs", "plugin": True}}
FLAGS.update({k + "_p": v for k, v in FLAGS.items()})


def _has_hints() -> bool:
    """spec-ptc with the sptc-hints patch (SpeculationRejected): spec_kind bet needs it."""
    try:
        import spec_ptc.contracts.hints  # noqa: F401
    except ImportError:
        return False
    return True


def sweep(out: Path, log: Path, *extra: str) -> subprocess.CompletedProcess:
    serve = (f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {{model}} --port {{port}} "
             f"--max-running 12 --log-json {shlex.quote(str(log))} "
             f"--fail-once {shlex.quote(FAIL_SALT)}")
    cmd = [sys.executable, str(KAGGLE / "vllm_bench.py"), "sweep", "--launch",
           "--serve-cmd", serve, "--base-url", f"http://127.0.0.1:{free_port()}/v1",
           "--arms", ARMS, "--agents", "1,2", "--reps", "1", "--turns", "1",
           "--spec-ptc", SPEC_PTC, "--out", str(out), "--server-gap", "0.2", "--boot", "50",
           *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r


def requests_of(log: Path, salt: str, server: str) -> list[dict]:
    return [r for r in map(json.loads, log.read_text().splitlines())
            if r["prompt_head"].startswith(salt) and r["flags"] == FLAGS[server]]


def test_sweep_end_to_end_and_resume(tmp_path):
    out, log = tmp_path / "out", tmp_path / "fake.jsonl"
    r = sweep(out, log)
    runs = {(x["arm"], x["agents"]): x for x in
            (json.loads(f.read_text()) for f in (out / "sweep" / "runs").glob("*.json"))}
    assert len(runs) == 8 and all(x["status"] == "ok" for x in runs.values()), \
        {k: (x["status"], x["errors"]) for k, x in runs.items()}

    # the injected silent failure (a root stream with no tokens) was caught and retried
    retried = {k for k, x in runs.items() if x.get("retry_of") is not None}
    assert retried == {(a, 1) for a in ("fcfs/spec+bad", "prio/spec+bad", "plugin/spec+bad")}
    for k in retried:
        assert runs[k]["retry_of"]["status"] == "invalid", runs[k].get("retry_of")
        assert "failed root stream" in runs[k]["retry_of"]["errors"][-1]
    # stock, priority and plugin arms send the same prompts
    assert runs[("fcfs/spec+bad", 2)]["salt"] == runs[("plugin/spec+bad", 2)]["salt"] \
        == runs[("prio/spec+bad", 2)]["salt"] == "[spec d1 n2 r0] "

    for (arm, n), x in runs.items():
        assert len(x["sessions"]) == n
        dec = Counter(d["outcome"] for s in x["sessions"] for d in s["decoys"])
        reqs = requests_of(log, x["salt"], x["server"])
        assert reqs, arm
        if arm == "fcfs/nospec":
            assert not dec and all(q["priority"] is None and q["vllm_xargs"] is None
                                   for q in reqs)
            continue
        # one decoy per speculation, each with a known outcome
        early = sum(c["kind"] == "early" for s in x["sessions"] for c in s["calls"])
        assert early > 0 and sum(dec.values()) == early
        assert set(dec) <= {"completed", "cancelled", "rejected", "dropped"}, dec
        roots = [q for q in reqs if "Count upward" in q["prompt_head"]]
        bets = [q for q in reqs if q["ignore_eos"] and q not in roots]  # decoys: raw, max length
        assert len(bets) == early
        assert roots and all(q["priority"] is None and q["vllm_xargs"] is None for q in roots)
        if arm.startswith("prio/"):
            assert all(q["priority"] == 1 for q in reqs if q not in roots)
            assert all(q["flags"]["policy"] == "priority" for q in reqs)
        elif arm.startswith("plugin/"):
            assert all(q["vllm_xargs"]["sptc_class"] in ("early", "bet") for q in reqs
                       if q not in roots and q["vllm_xargs"])
            assert {q["vllm_xargs"]["sptc_class"] for q in bets if q["vllm_xargs"]} == {"bet"}
            assert all(q["flags"]["plugin"] for q in reqs)
        else:
            assert all(q["priority"] is None and q["vllm_xargs"] is None for q in reqs)
            assert not dec["rejected"] and not dec["dropped"]

    s = json.loads((out / "sweep" / "summary.json").read_text())
    assert s["slo"]["refs"] and all(row["goodput"] is not None for row in s["rows"])

    # resume: nothing left to do, no server is started
    n_req = len(log.read_text().splitlines())
    r = sweep(out, log)
    assert r.stdout.count("all runs already done") == 3, r.stdout[-2000:]
    assert len(log.read_text().splitlines()) == n_req

    # a lost result file is redone, and only that one
    (out / "sweep" / "runs" / "prio__spec_plus_bad__n2__r0.json").unlink()
    r = sweep(out, log)
    assert r.stdout.count("all runs already done") == 2
    assert (out / "sweep" / "runs" / "prio__spec_plus_bad__n2__r0.json").exists()
    new = log.read_text().splitlines()[n_req:]
    assert new and all(json.loads(q)["prompt_head"].startswith(("[spec d1 n2 r0]", "[warmup"))
                       for q in new)


def test_ab_rounds_warm_pass_and_launch_records(tmp_path):
    """The A/B mechanics: two launches per server, the second round in reverse order
    (stock, plugin, plugin, stock); a launch that compiled fresh only fills the cache and is
    launched again; repeat r in launch r % 2; one throwaway warm-up pass per measured
    launch; a launch record with the server's command line; a server that fails to start
    is recorded and skipped, the others still run."""
    out, log = tmp_path / "out", tmp_path / "fake.jsonl"
    serve = (f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {{model}} --port {{port}} "
             f"--max-running 12 --log-json {shlex.quote(str(log))} "
             f"--compile-cache {shlex.quote(str(tmp_path / 'cache'))} --exit-if-config adaptive")
    cmd = [sys.executable, str(KAGGLE / "vllm_bench.py"), "sweep", "--launch", "--preset", "ab",
           "--serve-cmd", serve, "--base-url", f"http://127.0.0.1:{free_port()}/v1",
           "--arms", "fcfs/spec,plugin-adaptive/spec,plugin-off/spec", "--agents", "1",
           "--reps", "2", "--turns", "1", "--spec-ptc", SPEC_PTC, "--out", str(out),
           "--server-gap", "0.2"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert r.stdout.count("SERVER FAILED") == 2
    launches = [json.loads(x) for x in (out / "sweep" / "launches.jsonl").read_text().splitlines()]
    assert [(x["launch"], x.get("role")) for x in launches] == [
        ("fcfs#1", "cache_fill"), ("fcfs#2", "measure"), ("plugin_adaptive#failed", None),
        ("plugin_off#1", "cache_fill"), ("plugin_off#2", "measure"),
        ("plugin_off#3", "measure"), ("plugin_adaptive#failed", None), ("fcfs#3", "measure")]
    assert launches[0]["fresh_compile"] and launches[0]["aot_saved"]
    assert launches[1]["fresh_compile"] is False
    assert launches[1]["aot_loaded"] == launches[0]["aot_saved"]
    assert "refusing to start" in launches[2]["error"]
    off = launches[3]["cmd"]
    assert json.loads(off[off.index("--additional-config") + 1])["sptc"]["prefill_allowance"] \
        == "off"
    runs = {(x["arm"], x["rep"]): x for x in
            (json.loads(f.read_text()) for f in (out / "sweep" / "runs").glob("*.json"))}
    assert set(runs) == {(a, k) for a in ("fcfs/spec", "plugin-off/spec") for k in (0, 1)}
    assert runs[("fcfs/spec", 0)]["launch"] == "fcfs#2"
    assert runs[("fcfs/spec", 1)]["launch"] == "fcfs#3"
    assert runs[("plugin-off/spec", 1)]["round"] == 1
    assert runs[("fcfs/spec", 1)]["salt"] == runs[("plugin-off/spec", 1)]["salt"]
    assert len(list((out / "sweep" / "warm").glob("*.json"))) == 4
    warm = [q for q in map(json.loads, log.read_text().splitlines())
            if q["prompt_head"].startswith("[warmup-pass plugin_off#3]")]
    assert warm and all(q["vllm_xargs"] is None or q["vllm_xargs"]["sptc_class"] in
                        ("early", "bet") for q in warm)
    s = json.loads((out / "sweep" / "summary.json").read_text())
    assert {(x["arm"], x["launch"]) for x in s["by_launch"]} == {
        ("fcfs/spec", "fcfs#2"), ("fcfs/spec", "fcfs#3"),
        ("plugin-off/spec", "plugin_off#2"), ("plugin-off/spec", "plugin_off#3")}
    assert set(s["derived"]["vs_stock"]) == {"plugin-off/spec"}
    assert json.loads((out / "sweep.json").read_text())["failed_servers"] == [
        "plugin_adaptive (round 0)", "plugin_adaptive (round 1)"]


def test_baselines_preset_end_to_end(tmp_path):
    """Section B4: bets-only priority sends priority 1 on bets only; the client-side cap
    sends nothing extra to stock FCFS, accounts for every bet (sent or refused, never
    queued) and ends with nothing in flight; every arm sends the same prompts, arms that
    share the fcfs launch kept apart by cache_salt, so the sub-call work is the same; one
    run per arm at 2 agents, one round."""
    out, log = tmp_path / "out", tmp_path / "fake.jsonl"
    serve = (f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {{model}} --port {{port}} "
             f"--max-running 12 --log-json {shlex.quote(str(log))}")
    cmd = [sys.executable, str(KAGGLE / "vllm_bench.py"), "sweep", "--launch",
           "--preset", "baselines", "--serve-cmd", serve,
           "--base-url", f"http://127.0.0.1:{free_port()}/v1", "--agents", "2", "--reps", "1",
           "--rounds", "1", "--turns", "1", "--spec-ptc", SPEC_PTC, "--out", str(out),
           "--server-gap", "0.2", "--boot", "50"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    runs = {x["arm"]: x for x in
            (json.loads(f.read_text()) for f in (out / "sweep" / "runs").glob("*.json"))}
    assert set(runs) == set(BASELINE_ARMS) and all(x["status"] == "ok" for x in runs.values())
    assert {x["salt"] for x in runs.values()} == {"[spec n2 r0] "}
    salts = {a: x["cache_salt"] for a, x in runs.items()}
    assert salts == {"fcfs-b4/spec+bad": None, "proxy/spec+bad": "sptc-v1",
                     "proxy-sem/spec+bad": "sptc-v2", "fcfs-b4/spec": "sptc-v3",
                     "prio-bets/spec+bad": None, "plugin-b4/spec+bad": None}
    work = {a: sorted((s["pattern"], vb.sub_tokens(s)) for s in x["sessions"])
            for a, x in runs.items()}
    assert all(w == work["fcfs-b4/spec+bad"] for w in work.values()), work
    for arm, x in runs.items():
        reqs = [q for q in requests_of(log, x["salt"], x["server"])
                if q["cache_salt"] == x["cache_salt"]]
        assert reqs
        roots = [q for q in reqs if "Count upward" in q["prompt_head"]]
        bets = [q for q in reqs if q["ignore_eos"] and q not in roots]
        dec = Counter(d["outcome"] for s in x["sessions"] for d in s["decoys"])
        early = sum(c["kind"] == "early" for s in x["sessions"] for c in s["calls"])
        if arm == "fcfs-b4/spec":  # the no-bets reference
            assert early > 0 and not bets and not dec and "proxy" not in x
            continue
        assert early > 0 and sum(dec.values()) == early, (arm, dec)
        if arm == "prio-bets/spec+bad":
            assert bets and all(q["priority"] == 1 for q in bets)
            assert all(q["priority"] is None for q in reqs if q not in bets)
        elif arm.startswith("proxy"):
            p = x["proxy"]
            assert p["gate"].endswith(":8") and p["in_flight_end"] == 0
            assert p["bets_sent"] == len(bets) and p["bets_sent"] + p["bets_refused"] == early
            assert dec["rejected"] == p["bets_refused"]
            assert all(q["priority"] is None and q["vllm_xargs"] is None for q in reqs)
            assert all(q["flags"] == FLAGS["fcfs"] for q in reqs)
        else:
            assert "proxy" not in x
    s = json.loads((out / "sweep" / "summary.json").read_text())
    assert set(s["derived"]["baselines_vs_fcfs"]) == set(BASELINE_ARMS) - {"fcfs-b4/spec+bad"}
    assert set(s["derived"]["baselines_vs_nobets"]) == set(BASELINE_ARMS) - {"fcfs-b4/spec"}
    assert all(v["sub_tokens_per_session"] == 1.0
               for pts in s["derived"]["baselines_vs_fcfs"].values() for v in pts.values())
    assert "## Baselines (B4)" in (out / "sweep" / "summary.md").read_text()


def _pressure_sweep(out: Path, log: Path, *extra: str, check: bool = True):
    serve = (f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {{model}} --port {{port}} "
             f"--max-running 12 --log-json {shlex.quote(str(log))} --max-model-len 512")
    cmd = [sys.executable, str(KAGGLE / "vllm_bench.py"), "sweep", "--launch",
           "--serve-cmd", serve, "--base-url", f"http://127.0.0.1:{free_port()}/v1",
           "--agents", "2", "--reps", "1", "--rounds", "1", "--turns", "1",
           "--spec-ptc", SPEC_PTC, "--out", str(out), "--server-gap", "0.2", "--boot", "50",
           *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if check:
        assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r


@pytest.mark.skipif(not _has_hints(), reason="spec-ptc without the sptc-hints patch")
def test_pressure_preset_end_to_end(tmp_path):
    """The pressure preset: the pressure servers get the chosen config's flags
    (--max-model-len from --serve-cmd); every arm tags or prioritises its bets only; in
    workload both the speculative calls are bets too, and a call whose last bet was
    refused is run for real once, untagged, when the program claims it (spec-ptc may bet
    on a call again after a failed bet); a sweep into the same directory on the other
    config stops before launching; the Pressure table and the decision rule."""
    out, log = tmp_path / "out", tmp_path / "fake.jsonl"
    _pressure_sweep(out, log, "--preset", "pressure")
    runs = {x["arm"]: x for x in
            (json.loads(f.read_text()) for f in (out / "sweep" / "runs").glob("*.json"))}
    assert set(runs) == set(vb.PRESSURE_ARMS) and all(x["status"] == "ok" for x in runs.values()), \
        {k: (x["status"], x["errors"]) for k, x in runs.items()}
    launches = [json.loads(x) for x in (out / "sweep" / "launches.jsonl").read_text().splitlines()]
    assert [x["server"] for x in launches] == ["fcfs_p", "priority_p", "plugin_p"]
    for x in launches:
        c = x["cmd"]
        assert c[-4:] == vb.pressure_flags("chosen") and c[c.index("--max-model-len") + 1] == "512"
    assert json.loads((out / "sweep" / "pressure.json").read_text())["config"] == "chosen"
    assert {x["salt"] for x in runs.values()} == {"[spec n2 r0] ", "[baseline n2 r0] "}

    refused_total = {}
    for arm, x in runs.items():
        a = vb.ARM[arm]
        reqs = [q for q in requests_of(log, x["salt"], x["server"])
                if q["cache_salt"] == x["cache_salt"]]
        roots = [q for q in reqs if "Count upward" in q["prompt_head"]]
        decoys = [q for q in reqs if q["ignore_eos"] and q not in roots]
        subs = [q for q in reqs if q not in roots and q not in decoys]
        calls = [c for s in x["sessions"] for c in s["calls"]]
        kinds = Counter(c["kind"] for c in calls)
        bets = [c for c in calls if c["kind"] == "bet"]
        refused = [c for c in bets if c.get("refused")]
        reruns = [c for c in calls if c.get("at_claim")]
        dec = [d for s in x["sessions"] for d in s["decoys"]]  # sent or refused by the cap
        held = sum(c.get("stop") == "proxy_rejected" for c in dec + bets)  # never sent
        assert roots and all(q["priority"] is None and q["vllm_xargs"] is None for q in roots)
        assert len(dec) == a.decoys * (kinds["early"] + kinds["bet"])
        assert sum(len(s["real_bets"]) for s in x["sessions"]) == len(bets)
        assert sum(s["reissued"] for s in x["sessions"]) == len(reruns)
        if a.spec_kind == "early":
            assert not bets and not reruns
        else:  # both: no early calls. spec-ptc may bet on a call again after a failed
            # bet; a call whose last bet was refused is run for real once, at its claim
            assert bets and not kinds["early"]
            for s in x["sessions"]:
                last = {}
                for c in s["calls"]:
                    if c["kind"] == "bet" and c["outcome"] != "cancelled":
                        last[c["prompt_id"]] = c["outcome"]
                assert sorted(c["prompt_id"] for c in s["calls"] if c.get("at_claim")) == \
                    sorted(p for p, o in last.items() if o != "completed"), arm
                assert s["real_bet_calls"] == len({c["prompt_id"] for c in s["calls"]
                                                   if c["kind"] == "bet"})
            assert all(c["kind"] == "fallback" and c["outcome"] == "completed" for c in reruns)
        refused_total[arm] = len(refused)
        # what each request carries: bets only, by the arm's scheme
        sent_bets = decoys + [q for q in subs if q["vllm_xargs"] or q["priority"]]
        if a.tags != "none":
            assert len(sent_bets) == len(dec) + len(bets) - held, arm
        if a.tags == "sptc_bets":
            assert all(q["vllm_xargs"] == {"sptc_class": "bet"} and q["priority"] is None
                       for q in sent_bets)
            assert all(q["flags"]["plugin"] for q in reqs)
        elif a.tags == "priority_bets":
            assert all(q["priority"] == 1 and q["vllm_xargs"] is None for q in sent_bets)
            assert not refused and all(q["flags"]["policy"] == "priority" for q in reqs)
        else:  # stock FCFS, with or without the cap: nothing extra on any request
            assert all(q["priority"] is None and q["vllm_xargs"] is None for q in reqs)
            if not a.gate:
                assert not refused and not held and not x.get("proxy")
            else:  # every bet the cap let through reached the server, none other
                p = x["proxy"]
                assert p["in_flight_end"] == 0 and p["bets_refused"] == held
                assert p["bets_sent"] == len(dec) + len(bets) - held
                assert len(decoys) == len(dec) - sum(d.get("stop") == "proxy_rejected"
                                                     for d in dec)
    # map16's burst of 16 bets meets the window of 8: the cap and the plugin refuse some
    assert refused_total["cap-p/both"] and refused_total["plugin-p/both"], refused_total

    s = json.loads((out / "sweep" / "summary.json").read_text())
    assert set(s["derived"]["pressure_vs_ref"]) == set(vb.PRESSURE_ARMS)
    d1 = s["derived"]["d1"]  # the rule is read at 4 agents: no verdict from 2
    assert d1["agents"] == 4 and d1["plugin_wins"] is None
    assert all(d1["by_workload"][w]["plugin_vs_cap"] is None for w in vb.D1_RULE)
    md = (out / "sweep" / "summary.md").read_text().split("## Pressure")[1]
    md = md.split("## Baselines")[0]
    assert all(md.count(f"| {arm} | 2 |") == 1 for arm in vb.PRESSURE_ARMS)
    assert "Decision rule on these values" in md and "plugin wins: unknown" in md

    # the other config into the same directory: stopped before any launch
    n_launch = len(launches)
    r = _pressure_sweep(out, log, "--preset", "pressure", "--pressure-config", "fallback",
                        "--reps", "2", check=False)
    assert r.returncode != 0 and "chosen pressure config, not fallback" in r.stderr
    assert len((out / "sweep" / "launches.jsonl").read_text().splitlines()) == n_launch


def test_probe_end_to_end(tmp_path):
    """The probe preset, then probe_verdict on its runs: with 12 slots, stock FCFS queues
    the 2 agents' bursts, so the sweep stays on the chosen config. A --serve-cmd without
    --max-model-len 512 is refused before any launch."""
    out, log = tmp_path / "probe", tmp_path / "fake.jsonl"
    _pressure_sweep(out, log, "--preset", "probe")
    v = vb.probe_verdict(out)
    assert v["config"] == "chosen" and v["pressure"], v
    assert all(x is not None and x["max_waiting"] is not None for x in v["arms"].values())
    assert v["arms"]["fcfs-p/spec+bad"]["max_waiting"] > 0
    r = subprocess.run([sys.executable, str(KAGGLE / "vllm_bench.py"), "sweep", "--launch",
                        "--preset", "probe", "--out", str(tmp_path / "x"),
                        "--spec-ptc", SPEC_PTC], capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "need --max-model-len 512" in r.stderr
