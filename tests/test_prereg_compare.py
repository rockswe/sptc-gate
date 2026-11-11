"""experiments/prereg_compare.py: the scoring rules on hand-made rows, and a smoke run of the
whole comparison on a tiny measured directory."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import prereg_compare as pc  # noqa: E402

LADDER = [1, 2, 4, 8, 12, 16, 24, 32]


def row(arm, n, p50, ci=None, tpot=20.0, **kw):
    return {"arm": arm, "agents": n, "reps_ok": 3, "reps_other": {}, "cpu_ok": True,
            "session_p50": p50, "root_tpot_p50": tpot,
            "ci": {"session_p50": ci, "root_tpot_p50": None}, **kw}


def ratio(p, tol=0.05):
    return {"kind": "ratio", "numerator": ["plugin/spec", 1], "denominator": ["fcfs/spec", 1],
            "metric": "session_p50", "predicted": p, "tol": tol}


def test_ratio_rule():
    rows = {("fcfs/spec", 1): row("fcfs/spec", 1, 2.7, [2.6, 2.8]),
            ("plugin/spec", 1): row("plugin/spec", 1, 3.1, [3.0, 3.2])}
    v = pc.check_ratio(ratio(1.0), rows)
    assert v["verdict"] == "refuted" and v["measured"] == pytest.approx(3.1 / 2.7)
    rows[("plugin/spec", 1)]["ci"]["session_p50"] = [2.7, 3.3]  # overlaps 1.0 x [2.6, 2.8]
    assert pc.check_ratio(ratio(1.0), rows)["verdict"] == "unresolved"
    assert pc.check_ratio(ratio(1.12), rows)["verdict"] == "supported"
    rows[("fcfs/spec", 1)]["cpu_ok"] = False
    assert pc.check_ratio(ratio(1.0), rows)["verdict"] == "invalid"
    del rows[("fcfs/spec", 1)]
    assert pc.check_ratio(ratio(1.0), rows)["verdict"] == "not run"


def test_work_check_beside_a_ratio():
    rows = {("fcfs/spec", 1): row("fcfs/spec", 1, 2.7, sub_tokens_per_session=100.0),
            ("plugin/spec", 1): row("plugin/spec", 1, 2.8, sub_tokens_per_session=108.0)}
    v = pc.check_ratio(ratio(1.0), rows)
    assert v["verdict"] == "supported" and v["work"] == pytest.approx(1.08)
    del rows[("fcfs/spec", 1)]["sub_tokens_per_session"]
    assert pc.check_ratio(ratio(1.0), rows)["work"] is None


def test_fraction_rule():
    rows = {("plugin/spec+bad", 8): row("plugin/spec+bad", 8, 4.4,
                                        decoy_outcomes={"rejected": 90, "completed": 10})}
    c = {"kind": "fraction", "arm": "plugin/spec+bad", "agents": 8, "outcome": "rejected",
         "tol": 0.1}
    assert pc.check_fraction({**c, "predicted": 1.0}, rows)["verdict"] == "supported"
    assert pc.check_fraction({**c, "predicted": 0.7}, rows)["verdict"] == "refuted"


@pytest.mark.parametrize("pred, meas, top, want", [
    (16, 16, 32, "supported"), (16, 24, 32, "supported"), (16, 32, 32, "refuted"),
    (None, None, 32, "supported"), (None, None, 16, "unchecked"), (None, 24, 32, "refuted"),
    (16, None, 24, "refuted"), (16, None, 16, "unchecked")])
def test_threshold_rule(pred, meas, top, want):
    rows = {(a, n): row(a, n, 3.0) for a in ("fcfs/spec", "plugin/spec")
            for n in LADDER if n <= top}
    c = {"kind": "threshold", "key": "knee_ref", "arm": "plugin/spec", "predicted": pred,
         "ladder": LADDER}
    assert pc.check_threshold(c, rows, {"knee_ref": {"plugin/spec": meas}})["verdict"] == want


def test_overhead_and_general_rules():
    bounds = [{"n_running": 8, "variant": "sptc-tagged", "bound_added_us": 40}]
    res = {"rows": [{"scheduling": s, "n_running": 8, "variant": v, "total_p50_us": t}
                    for s in ("sync", "async")
                    for v, t in (("stock", 100.0), ("sptc-tagged", 130.0 if s == "sync" else 150.0))]}
    v = {x["scheduling"]: x["verdict"] for x in pc.check_overhead(bounds, res)}
    assert v == {"sync": "supported", "async": "refuted"}
    assert pc.check_overhead(bounds, None)[0]["verdict"] == "not run"
    claims = [{"n": 3, "claim": "x", "numerator": ["priority", "next3", 8, 0],
               "denominator": ["fcfs", "next3", 8, 0], "metric": "lat_p50",
               "bound": [0.9, 1.1], "predicted_ratio": 1.0}]
    rows = [{"arm": a, "mode": "next3", "agents": 8, "batch_workers": 0, "lat_p50": t}
            for a, t in (("priority", 30.0), ("fcfs", 31.0))]
    assert pc.check_general(claims, rows)[0]["verdict"] == "supported"
    assert pc.check_general(claims, rows[:1])[0]["verdict"] == "not run"


def test_smoke_on_a_tiny_measured_dir(tmp_path, monkeypatch):
    pre = ROOT / "results" / "prereg_v3" / "predictions.json"
    if not pre.exists():
        pytest.skip("no results/prereg_v3 yet")
    runs = tmp_path / "sweep" / "runs"
    runs.mkdir(parents=True)
    for arm, wall in (("fcfs/spec", 2.7), ("plugin/spec", 3.1)):
        for rep in range(3):
            ses = [{"pattern": "map16", "wall_s": wall + 0.01 * k, "root_tpot_ms": 17.0,
                    "decoys": [], "calls": []} for k in range(4)]
            (runs / f"{arm.replace('/', '__')}__n1__r{rep}.json").write_text(json.dumps(
                {"arm": arm, "server": arm.split("/")[0], "agents": 1, "rep": rep,
                 "status": "ok", "sessions": ses, "makespan_s": 12.0, "launch": f"x#{rep}",
                 "host_cpu_util": 0.3, "host_cpu_sat_frac": 0.0, "server_metrics": {}}))
    monkeypatch.setattr(sys, "argv", ["prereg_compare.py", "--out", str(tmp_path), "--boot", "50"])
    pc.main()
    res = json.loads((tmp_path / "prereg_compare.json").read_text())
    assert res["prereg"] == "prereg_v3"
    assert [x["prereg"] for x in res["also"]] == ["prereg_v3b", "prereg_v2"]
    v3b = res["also"][0]  # the B4 addendum: B4 claims only, nothing measured here
    assert set(v3b["prereg_files"].values()) == {"match"}
    assert {c["id"].split("-")[0] for c in v3b["claims"]} == {"B4C", "B4N"}
    assert {c["verdict"] for c in v3b["claims"]} == {"not run"}
    for r in (res, res["also"][1]):  # v3 primary, v2 also scored; AB-1 is the same claim
        ab1 = next(c for c in r["claims"] if c["id"] == "AB-1")
        assert ab1["verdict"] == "refuted"
        assert ab1["measured"] == pytest.approx(3.1 / 2.7, rel=0.01)
        assert {c["verdict"] for c in r["claims"] if c["id"].startswith("PRIO")} == {"not run"}
        assert set(r["prereg_files"].values()) == {"match"}
    assert {c["verdict"] for c in res["claims"] if c["id"].startswith("B4")} == {"not run"}
    md = (tmp_path / "prereg_compare.md").read_text()
    assert md.startswith("# Measured vs pre-registered (prereg_v3)")
    assert "# Measured vs pre-registered (prereg_v2) (also reported)" in md
    assert "# Measured vs pre-registered (prereg_v3b) (also reported)" in md


def _runs(arm, walls_by_launch, pattern="map16"):
    """One run per (launch, list of session walls)."""
    return [{"arm": arm, "agents": 1, "status": "ok", "launch": la,
             "sessions": [{"pattern": pattern, "wall_s": w, "root_tpot_ms": 17.0} for w in ws]}
            for la, ws in walls_by_launch]


def test_strict_verdict_needs_a_tight_ci_and_two_launches():
    c = ratio(1.0)
    tight = [("a#1", [2.70, 2.71, 2.72]), ("a#2", [2.70, 2.71, 2.69])]
    cells = {("fcfs/spec", 1): _runs("fcfs/spec", tight),
             ("plugin/spec", 1): _runs("plugin/spec", [("b#1", [2.71, 2.72, 2.70]),
                                                       ("b#2", [2.70, 2.69, 2.71])])}
    v = pc.strict(c, cells, boot=200)
    assert v["verdict"] == "supported" and v["launches"] == [2, 2]
    # one plugin launch 20% slower: the point estimate may pass, the launch CI does not
    cells[("plugin/spec", 1)] = _runs("plugin/spec", [("b#1", [2.71, 2.72, 2.70]),
                                                      ("b#2", [3.25, 3.26, 3.24])])
    assert pc.strict(c, cells, boot=200)["verdict"] == "unresolved"
    cells[("plugin/spec", 1)] = _runs("plugin/spec", [("b#1", [3.10, 3.11, 3.12]),
                                                      ("b#2", [3.11, 3.10, 3.12])])
    assert pc.strict(c, cells, boot=200)["verdict"] == "refuted"
    cells[("plugin/spec", 1)] = _runs("plugin/spec", [("b#1", [2.71, 2.72, 2.70])])
    assert pc.strict(c, cells, boot=200)["verdict"] == "unresolved"  # one launch
    assert pc.strict(c, {}, boot=50)["verdict"] == "not run"


def test_pattern_ratios_pair_patterns():
    cells = {("fcfs/spec", 1): _runs("fcfs/spec", [("a", [1.0])], "map16")
             + _runs("fcfs/spec", [("a", [3.0])], "map_reduce"),
             ("plugin/spec", 1): _runs("plugin/spec", [("b", [1.1])], "map16")
             + _runs("plugin/spec", [("b", [3.0])], "map_reduce")}
    r = pc.pattern_ratios(ratio(1.0), cells)
    assert r["per_pattern"] == pytest.approx({"map16": 1.1, "map_reduce": 1.0})
    assert r["gmean"] == pytest.approx(1.1 ** 0.5)


def test_general_rows_merge_quick_and_partial_full(tmp_path):
    cell = lambda arm, mode, lat: {"arm": arm, "mode": mode, "agents": 8,  # noqa: E731
                                   "batch_workers": 0, "lat_p50": lat}
    (tmp_path / "general_quick").mkdir()
    (tmp_path / "general_full").mkdir()
    (tmp_path / "general_quick" / "general.json").write_text(json.dumps({"react": [
        cell("fcfs", "next3", 30.0), cell("priority", "next3", 31.0)]}))
    (tmp_path / "general_full" / "general_partial.json").write_text(json.dumps({"react": [
        cell("fcfs", "next3", 33.0)]}))
    rows, src = pc.general_rows(tmp_path)
    by = {r["arm"]: r["lat_p50"] for r in rows}
    assert by == {"fcfs": 33.0, "priority": 31.0}  # full wins where both ran
    assert src == "general_quick/general.json + general_full/general_partial.json"
    claims = [{"n": 3, "claim": "x", "numerator": ["priority", "next3", 8, 0],
               "denominator": ["fcfs", "next3", 8, 0], "metric": "lat_p50",
               "bound": [0.9, 1.1], "predicted_ratio": 1.0}]
    rows[0]["cpu_ok"] = False
    assert pc.check_general(claims, rows)[0]["verdict"] == "invalid"


@pytest.mark.parametrize("version", ["prereg_v2", "prereg_v3", "prereg_v3b"])
def test_prereg_files_are_checked(tmp_path, version):
    pre = ROOT / "results" / version
    assert set(pc.prereg_files(pre).values()) == {"match"}
    (tmp_path / "predictions.json").write_text((pre / "predictions.json").read_text() + " ")
    v = pc.prereg_files(tmp_path, version)
    assert v["predictions.json"] == "MISMATCH" and v["predictions.md"] == "missing"
    assert "unknown version" in pc.prereg_files(tmp_path)["(all)"]
