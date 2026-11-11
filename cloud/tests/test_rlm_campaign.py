"""cloud/rlm_campaign.py end to end against the fake server (the campaign's runner, unmodified)."""

from __future__ import annotations

import hashlib
import json

import rlm.environments as rlm_envs
from fake_rlm_server import FakeRLMServer
from test_rlm_stream import ITER0, ITER1

import analyze
import rlm_campaign

STOCK = rlm_envs.LocalREPL


def tasks_file(tmp_path, n=2):
    rows = [{"task_id": f"trec-fake-{i}", "dataset": "trec_coarse_131072",
             "context": "abcdefghij" * 10, "question": "How many parts?", "hint": "Hint.",
             "answer": "['4']", "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(n)]
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps(rows))
    return p


def campaign(tmp_path, srv, *extra):
    out = tmp_path / "out"
    rlm_campaign.main(["run", "--out", str(out), "--tasks", str(tasks_file(tmp_path)),
                       "--model", srv.model, "--base-url", srv.base_url,
                       "--conc", "2", "--repeats", "2", "--metrics-every", "0.1", *extra])
    return out


def events(out, kind):
    return [json.loads(x) for x in (out / "campaign.jsonl").read_text().splitlines()
            if json.loads(x)["kind"] == kind]


def test_campaign_runs_every_arm_in_abba_order_and_summarizes(tmp_path):
    try:
        with FakeRLMServer([ITER0, ITER1], token_s=0.005, sub_s=0.05) as srv:
            out = campaign(tmp_path, srv)
            begun = [e["unit"] for e in events(out, "unit_begin")]
            assert begun == ["nospec_c2_r1", "fanout_c2_r1", "stream_c2_r1",
                             "stream_c2_r2", "fanout_c2_r2", "nospec_c2_r2"]
            # resume: a second run starts nothing
            campaign(tmp_path, srv)
            assert len(events(out, "unit_begin")) == 6
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK

    for u in begun:
        d = out / "units" / u
        assert (d / "DONE").exists() and (d / "events.jsonl").exists()
        assert (d / "unit_stats.json").exists() and (d / "rlm_trajs").is_dir()
        lines = (d / "metrics.csv").read_text().splitlines()
        assert lines[0].startswith("t,running,waiting,kv") and len(lines) > 1
        # each unit also leaves compact trajectories: no REPL locals, no message history
        raw = sorted((d / "rlm_trajs").glob("*.jsonl"))
        small = sorted((d / "trajs_compact").glob("*.jsonl"))
        assert [f.name for f in small] == [f.name for f in raw] and len(small) == 2
        its = [json.loads(x) for x in small[0].read_text().splitlines()]
        its = [x for x in its if x.get("type") == "iteration"]
        assert its and all("prompt" not in x and x["response"] for x in its)
        results = [b["result"] for x in its for b in x["code_blocks"]]
        assert results and all("locals" not in r and "rlm_calls" in r for r in results)
        assert small[0].stat().st_size < raw[0].stat().st_size

    rows = {r["arm"]: r for r in json.loads((out / "summary.json").read_text())["rows"]}
    assert set(rows) == {"nospec", "fanout", "stream"}
    assert all(r["errors"] == 0 and r["tasks"] == 4 for r in rows.values())
    assert rows["stream"]["vs_nospec"]["pairs"] == 4 and rows["stream"]["vs_fanout"]["pairs"] == 4
    spec = rows["stream"]["spec"]
    assert spec["claim_hit"] == 4 * 5 and spec["claim_miss"] == 0
    assert rows["nospec"]["spec"]["dispatch"] == 0
    assert rows["stream"]["root_tpot_p50"] is not None
    assert rows["stream"]["shadow_wait_p50"] is not None
    assert rows["stream"]["vs_nospec"]["ratio"] < 1.0  # sub-calls overlap the root's stream
    md = (out / "summary.md").read_text()
    assert "| stream | 2 |" in md

    # where the time goes: nospec waits for its calls after the stream, stream hides them
    shares = {arm: r["after_share"]["p50"] for arm, r in rows.items()}
    assert all(r["ok_tasks"] == 4 and r["turns_mean"] == 2 for r in rows.values())
    assert shares["nospec"] > shares["fanout"] > shares["stream"] >= 0
    assert 0 < rows["stream"]["stream_share"]["pooled"] <= 1
    # the gate is computed, and unresolved here: no cell at concurrency 8 or 4
    g = json.loads((out / "summary.json").read_text())["gate"]
    assert g["verdict"] == "unresolved" and g["cells"][0]["conc"] == 2
    assert "## Where the time goes" in md and "**Gate: UNRESOLVED.**" in md

    # the run recorded what defined it before its first unit
    begin = events(out, "begin")[0]
    assert set(begin["files"]) == set(rlm_campaign.PROVENANCE_FILES)
    assert begin["files"]["GATE.md"] == hashlib.sha256(
        (rlm_campaign.HERE / "GATE.md").read_bytes()).hexdigest()
    assert len(begin["spec_ptc_py_tree"]) == 64 and begin["spec_ptc_py_files"] > 20

    # analyze.py reads the same folders
    a = analyze.analyze(out)
    cells = {c["arm"]: c for c in a["cells"]}
    assert all(c["ok"] == 4 and c["conc"] == 2 for c in cells.values())
    assert cells["nospec"]["subcalls_p50"] == 5 and cells["stream"]["subcalls_p50"] == 5
    assert cells["stream"]["spec"]["claim_hit"] == 20 and cells["nospec"]["spec"] == {}
    assert cells["nospec"]["share_after"] > cells["stream"]["share_after"]
    assert abs(sum(cells["nospec"][k] for k in ("share_stream", "share_after", "share_other"))
               - 1) < 1e-6
    assert cells["nospec"]["gap_p50"] > 0 and cells["nospec"]["root_out_tokens_p50"] > 50
    assert a["noise"][2]["same_arm_pairs"] == 6  # 2 tasks x 3 arms, repeat 1 against 2
    assert a["noise"][2]["stream_vs_nospec"]["pairs"] == 4
    assert [t["task_id"] for t in a["by_task"]] == ["trec-fake-0", "trec-fake-1"]
    md_a = analyze.render(a)
    assert "## Root stalls" in md_a and "## Noise floor" in md_a


def test_stalls_counts_only_gaps_far_above_the_usual_one():
    arr, t = [], 0.0
    for i in range(40):
        t += 5000.0 if i == 20 else 50.0  # one 5 s stall in a 50 ms stream
        arr.append([t, i + 1])
    s = analyze.stalls({"arrivals": arr})
    assert s["median_ms"] == 50.0 and s["n_stalls"] == 1 and s["max_ms"] == 5000.0
    assert abs(s["stall_s"] - 4.95) < 1e-9
    assert analyze.stalls({"arrivals": arr[:5]})["n_stalls"] == 0  # too short to judge


def test_budget_stops_before_a_unit_that_would_overrun(tmp_path):
    try:
        with FakeRLMServer([ITER0, ITER1], token_s=0.005, sub_s=0.05) as srv:
            out = campaign(tmp_path, srv, "--max-minutes", "0.01", "--unit-estimate-min", "5")
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    assert events(out, "budget_stop")[0]["unit"] == "nospec_c2_r1"
    assert not events(out, "unit_begin")


def test_warmup_runs_before_the_first_unit_and_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(rlm_campaign, "WARMUP_WAVES", ((1, "short"), (3, "short"), (2, "long")))
    try:
        with FakeRLMServer([ITER0, ITER1], token_s=0.002, sub_s=0.02) as srv:
            out = tmp_path / "out"
            rlm_campaign.main(["run", "--out", str(out), "--tasks", str(tasks_file(tmp_path)),
                               "--model", srv.model, "--base-url", srv.base_url,
                               "--arms", "nospec", "--conc", "2", "--repeats", "1",
                               "--metrics-every", "0.1", "--warmup-passes", "2"])
            n_requests = len(srv.log)
            # resume with every unit done: no second warm-up
            rlm_campaign.main(["run", "--out", str(out), "--tasks", str(tasks_file(tmp_path)),
                               "--model", srv.model, "--base-url", srv.base_url,
                               "--arms", "nospec", "--conc", "2", "--repeats", "1",
                               "--metrics-every", "0.1", "--warmup-passes", "2"])
            assert len(srv.log) == n_requests
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    kinds = [json.loads(x)["kind"] for x in (out / "campaign.jsonl").read_text().splitlines()]
    assert kinds.index("warmup_done") < kinds.index("unit_begin")
    waves = events(out, "warmup_wave")
    assert [(w["pass"], w["n"], w["prompt"]) for w in waves] == [
        (1, 1, "short"), (1, 3, "short"), (1, 2, "long"),
        (2, 1, "short"), (2, 3, "short"), (2, 2, "long")]
    assert all(w["errors"] == 0 and w["wall_s"] > 0 for w in waves)
    assert all(w["stream_max_gap_ms"] is not None for w in waves)
    done = events(out, "warmup_done")
    assert len(done) == 1 and done[0]["waves"] == 6 and done[0]["errors"] == 0


def gate_row(conc, share, ok_tasks=16, arm="stream"):
    return {"arm": arm, "conc": conc, "ok_tasks": ok_tasks,
            "after_share": {"p50": share, "ci": [share, share], "pooled": share}}


def test_gate_follows_the_rule_in_gate_md():
    gate = rlm_campaign.gate
    # go: one valid cell at the threshold is enough
    assert gate([gate_row(8, 0.15), gate_row(4, 0.02)])["verdict"] == "go"
    assert gate([gate_row(8, 0.40, ok_tasks=12)])["verdict"] == "go"
    # no-go: both cells valid and both below
    assert gate([gate_row(8, 0.149), gate_row(4, 0.10)])["verdict"] == "no-go"
    # unresolved: a cell missing, or too few finished tasks
    assert gate([gate_row(8, 0.10)])["verdict"] == "unresolved"
    assert gate([gate_row(8, 0.10), gate_row(4, 0.10, ok_tasks=11)])["verdict"] == "unresolved"
    assert gate([gate_row(8, 0.90, ok_tasks=11), gate_row(4, 0.10)])["verdict"] == "unresolved"
    # only the stream arm counts
    assert gate([gate_row(8, 0.9, arm="nospec"), gate_row(4, 0.9, arm="fanout")])["cells"] == []


def test_task_shares_add_up_per_task_and_skip_failed_tasks():
    roots = [
        {"task_id": "a", "stream_s": 10.0, "shadow_wait_s": 2.0, "exec_s": 3.0},
        {"task_id": "a", "stream_s": 5.0, "shadow_wait_s": 0.0, "exec_s": 5.0},
        {"task_id": "b", "stream_s": 4.0, "shadow_wait_s": 1.0, "exec_s": 1.0},
    ]
    tasks = [{"task_id": "a", "ok": True, "wall_s": 40.0},
             {"task_id": "b", "ok": False, "wall_s": 9.0}]
    (s,) = rlm_campaign.task_shares([{"unit": "stream_c8_r1", "roots": roots, "tasks": tasks}])
    assert s["task_id"] == "a" and s["turns"] == 2
    assert s["after_s"] == 10.0 and s["after_share"] == 0.25 and s["stream_share"] == 0.375


def test_plan_units_is_abba_per_concurrency():
    assert rlm_campaign.plan_units(("a", "b"), [8, 4], 2) == [
        ("a", 8, 1), ("b", 8, 1), ("b", 8, 2), ("a", 8, 2),
        ("a", 4, 1), ("b", 4, 1), ("b", 4, 2), ("a", 4, 2)]


def test_parse_metric_sums_label_sets_and_takes_the_first_name():
    text = ('vllm:num_requests_running{model_name="m",engine="0"} 3\n'
            'vllm:num_requests_running{model_name="m",engine="1"} 2\n'
            "# HELP x\nvllm:gpu_cache_usage_perc 0.5\n")
    assert rlm_campaign.parse_metric(text, ("num_requests_running",)) == 5
    assert rlm_campaign.parse_metric(text, ("kv_cache_usage_perc", "gpu_cache_usage_perc")) == 0.5
    assert rlm_campaign.parse_metric(text, ("num_preemptions_total",)) is None
