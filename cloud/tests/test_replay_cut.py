"""A session its timeout stopped is replayed up to the turn where it was stopped.

rlms checks a task's timeout between turns. The recorded run here gets a 0.5 s timeout
and a second turn that takes longer: the session is stopped before its third turn, as a
session with a long serial loop is on the engine."""

from __future__ import annotations

import json
from types import SimpleNamespace

import benchmark.oolong_campaign.runner as runner
import pytest
import record_report
import replay_campaign
import replay_corpus
import replay_report
import rlm.environments as rlm_envs
import rlm_campaign
from fake_engine import FakeEngineServer
from fake_rlm_server import FakeRLMServer

STOCK = rlm_envs.LocalREPL
QUICK = "First a look.\n```repl\nprint(len(context))\n```\n"
LOOP = (
    "I label six parts one by one.\n"
    "```repl\n"
    "import time\n"
    "labels = []\n"
    "for p in [context[i:i+10] for i in range(0, 60, 10)]:\n"
    "    labels.append(llm_query('Label this: ' + p).strip())\n"
    "time.sleep(0.8)\n"
    "print(labels)\n"
    "```\n"
    + "Waiting for the results now. " * 8
)
NEVER = "```repl\nanswer['content'] = 'never reached'\nanswer['ready'] = True\n```\n"


@pytest.fixture(scope="module")
def cut(tmp_path_factory):
    root = tmp_path_factory.mktemp("cut")
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_id": f"trec-fake-{i}", "dataset": "trec_coarse_131072",
         "context": "abcdefghij" * 10, "question": "How many parts?", "hint": "Hint.",
         "answer": "['4']", "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(2)]))
    orig = runner._run_task
    runner._run_task = lambda *a, **kw: orig(*a, **{**kw, "max_timeout": 0.5})
    try:
        with FakeRLMServer([QUICK, LOOP, NEVER], token_s=0.002, sub_s=0.02) as srv:
            rlm_campaign.main(["run", "--out", str(root / "runs" / "run1"), "--tasks", str(tasks),
                               "--model", srv.model, "--base-url", srv.base_url, "--arms",
                               "nospec", "--conc", "2", "--repeats", "1",
                               "--metrics-every", "0.2"])
    finally:
        runner._run_task = orig
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    manifest = replay_corpus.build(root / "runs", tasks, root / "corpus",
                                   tokens=replay_corpus.Tokens(False), tag="fix")
    return SimpleNamespace(root=root, manifest=manifest, corpus=root / "corpus")


def test_the_recorded_sessions_were_stopped_between_two_turns(cut):
    stats = json.loads((cut.root / "runs" / "run1" / "units" / "nospec_c2_r1" /
                        "unit_stats.json").read_text())
    for t in stats["tasks"]:
        assert t["ok"] is False and t["error"].startswith("TimeoutExceededError")
        assert replay_corpus.cut_of(t) == "timeout"
    assert replay_corpus.cut_of({"ok": False, "error": "BadRequestError: too long"}) is None
    assert replay_corpus.cut_of({"ok": True}) is None


def test_the_corpus_keeps_them_up_to_that_boundary(cut):
    rows = cut.manifest["sessions"]
    assert [r["session"] for r in rows] == ["trec-fake-0.fix1", "trec-fake-1.fix1"]
    for r in rows:
        assert r["replayable"] and r["problems"] == [] and r["cut"] == "timeout"
        assert r["turns"] == 2 and r["final"] == "timeout" and (r["calls"], r["errors"]) == (6, 0)
    sess = replay_corpus.load_session(cut.corpus / "trec-fake-0.fix1.json")
    assert sess["final"]["kind"] == "timeout" and len(sess["final"]["prompt_sha"]) == 64
    assert sess["final"]["text"] == replay_corpus.TIMEOUT_TEXT
    assert sess["task"]["task_id"] == "trec-fake-0.fix1" and sess["source"]["cut"] == "timeout"


def test_the_census_says_how_far_they_are_replayed(cut):
    c = record_report.census(cut.root / "runs" / "run1", cut.corpus)
    for s in c["sessions"]:
        assert s["status"] == "timeout" and s["replay"] == "up to turn 2"
        assert (s["calls"], s["singles"], s["batches"]) == (6, 6, 0)
    checks = {p["id"]: p for p in c["predictions"]}
    # both were stopped, and six calls are no loop of single calls: R6 fails here
    assert checks["R5"]["held"] is True and checks["R6"]["held"] is False
    assert checks["R6"]["measured"] == "0 of 2"


@pytest.fixture(scope="module")
def replayed(cut):
    out = cut.root / "replay"
    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(out), "--corpus", str(cut.corpus), "--arms",
                              "nospec,stream,scout", "--repeats", "1", "--conc", "2",
                              "--base-url", eng.base_url, "--model", eng.model,
                              "--metrics-every", "0.1"])
        requests = eng.engine.counters["requests"]
    return SimpleNamespace(out=out, requests=requests, summary=replay_report.summarize(out))


def test_every_arm_replays_them_exactly_and_ends_where_the_recording_did(replayed):
    for name in ("nospec_c2_r1", "stream_c2_r1", "scout_c2_r1"):
        d = replayed.out / "units" / name
        fid = json.loads((d / "replay.json").read_text())
        assert fid["exact"], (name, fid)
        for s in fid["sessions"]:
            assert s["ok"] and s["cut"] and s["turns"] == s["rec_turns"] == 2
            # both turns and the step that ends the session were sent the recorded history
            assert s["prompt_matches"] == s["prompts"] == 3 and s["answer_match"]
            assert (s["calls"], s["errors"], s["unrecorded"], s["repeats"]) == (6, 0, 0, 0)
        stats = json.loads((d / "unit_stats.json").read_text())
        assert all(t["final_answer"] == replay_corpus.TIMEOUT_TEXT for t in stats["tasks"])
    # 3 units x 2 sessions x (2 root turns + 6 sub-calls): the last step sends nothing
    assert replayed.requests == 3 * 2 * 8


def test_the_report_counts_their_turns_and_their_time(replayed):
    s = replayed.summary
    assert all(r["exact_units"] == 1 for r in s["arms"])
    for u in s["units"]:
        assert u["turns"] == 4 and u["ok"] == 2  # the ending step is not a turn
    assert {r["session"] for r in s["sessions"]} == {"trec-fake-0.fix1", "trec-fake-1.fix1"}
    rows = {r["arm"]: r for r in s["arms"]}
    assert all(rows[a]["wall_s"] > 2 * 0.8 for a in rows)  # the code's own 0.8 s, per session
    # the loop of six calls: serial as shipped, launched at once by the scout
    assert rows["scout"]["after_s"] < rows["stream"]["after_s"]


def test_names_with_a_tag_are_the_task_and_its_repeat():
    found = [{"task_id": "a", "unit": "nospec_c8_r1", "window": 65536, "run": "x"},
             {"task_id": "a", "unit": "nospec_c8_r2", "window": 65536, "run": "x"},
             {"task_id": "b", "unit": "nospec_c8_r2", "window": 65536, "run": "x"}]
    replay_corpus.session_names(found, "fix")
    assert [f["session"] for f in found] == ["a.fix1", "a.fix2", "b.fix2"]
    with pytest.raises(SystemExit, match="one repeat number in two runs"):
        replay_corpus.session_names(found + [dict(found[0], run="y")], "fix")
    replay_corpus.session_names(found)  # without a tag: as before
    assert [f["session"] for f in found] == ["a", "a.w64k-c8", "b"]


# ------------------------------------------------------------------ a design fixed beforehand
DESIGN = {
    "name": "test",
    "left_out": {"some-session.fix2": 40.0},
    "dropped": {"another.fix1": 60.0},
    "single_loops": [{"session": "trec-fake-0.fix1", "turn": 2, "kind": "stores"},
                     {"session": "trec-fake-1.fix1", "turn": 2, "kind": "stores"}],
    "batch_loops": [],
    "checks": [
        {"id": "D1", "claim": "`scout` below `stream` in session time",
         "ratio": ["scout", "stream", "wall_s"], "max": 1.0},
        {"id": "D2", "claim": "the first number is above 2", "first": "all", "min": 2.0},
        {"id": "D3", "claim": "one turn: `scout` at most 1.0 of `stream`",
         "turn": ["trec-fake-0.fix1", 2, "scout", "stream"], "max": 1.0},
    ],
}


@pytest.fixture(scope="module")
def designed(cut):
    out = cut.root / "designed"
    design = cut.root / "design_test.json"
    design.write_text(json.dumps(DESIGN))
    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(out), "--corpus", str(cut.corpus),
                              "--units", "stream:1,scout:1", "--warm-arm", "scout",
                              "--design-file", str(design), "--estimates", "stream=5,scout=4",
                              "--extra-units", "nospec:1,stream:1",
                              "--extra-sessions", "trec-fake-1.fix1",
                              "--conc", "2", "--base-url", eng.base_url, "--model", eng.model,
                              "--metrics-every", "0.1"])
    notes = [json.loads(x) for x in (out / "campaign.jsonl").read_text().splitlines()]
    return SimpleNamespace(out=out, notes=notes, summary=replay_report.summarize(out))


def test_units_run_in_the_order_given_after_a_unit_that_is_thrown_away(designed):
    kinds = [(n["kind"], n.get("unit")) for n in designed.notes if n["kind"].endswith("_begin")]
    assert kinds == [("warm_unit_begin", "scout_c2_r0"), ("unit_begin", "stream_c2_r1"),
                     ("unit_begin", "scout_c2_r1"), ("extra_unit_begin", "nospec_c2_r1"),
                     ("extra_unit_begin", "stream_c2_r1")]
    begin = designed.notes[0]
    assert begin["units"] == ["stream_c2_r1", "scout_c2_r1"] and begin["warm_arm"] == "scout"
    assert begin["estimates_s"] == {"stream": "5", "scout": "4"}
    for name in ("PREREG_RECORD.md", "PREREG_REPLAY.md", "replay.py"):
        assert name in begin["files"]
    # the thrown-away unit is a whole, exact unit, kept apart: no table counts it
    warm = designed.out / "warm" / "scout_c2_r0"
    assert (warm / "DONE").exists() and json.loads((warm / "replay.json").read_text())["exact"]
    s = designed.summary
    assert s["arm_names"] == ["stream", "scout"]
    assert [(r["arm"], r["units"], r["exact_units"]) for r in s["arms"]] == [
        ("stream", 1, 1), ("scout", 1, 1)]


def test_the_design_is_hashed_at_the_start_and_its_predictions_are_scored(designed):
    import hashlib

    begin = designed.notes[0]
    text = (designed.out / "design.json").read_text()
    assert json.loads(text) == DESIGN
    assert begin["design"] == {"file": "design_test.json",
                               "sha256": hashlib.sha256(text.encode()).hexdigest()}
    s = designed.summary
    arms = {r["arm"]: r for r in s["arms"]}
    f = s["first"]
    # sessions left out or dropped are added to both sums: not recovered, by definition
    assert f["added_s"] == 100.0 and f["sessions_added"] == 2 and f["sessions_replayed"] == 2
    assert f["replayed"] == pytest.approx(arms["scout"]["wall_s"] / arms["stream"]["wall_s"])
    assert f["all"] == pytest.approx((arms["scout"]["wall_s"] + 100) / (arms["stream"]["wall_s"] + 100))
    assert abs(f["all"] - 1) < abs(f["replayed"] - 1)  # the added seconds pull it towards 1
    checks = {p["id"]: p for p in s["prereg_fixed"]}
    assert list(checks) == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "D1", "D2", "D3"]
    assert checks["M1"]["held"] is True and checks["M1"]["measured"] == "2 of 2 exact"
    assert checks["M2"]["held"] is True  # the fork's unit: nothing twice, nothing evicted
    assert checks["M3"]["held"] is None  # no `nospec` unit in this run: not testable
    assert checks["M4"]["held"] is False  # each turn sleeps 0.8 s of its own: far above 0.25
    assert checks["M4"]["measured"].count(",") == 1  # one ratio per named turn
    assert checks["M5"]["held"] is None and checks["M6"]["held"] is None  # no such turn
    assert checks["M7"]["held"] is True  # at least 0.78
    # these sessions last a second: their summed time says nothing, the check is the arithmetic
    assert checks["D1"]["held"] is (f["replayed"] <= 1.0) and checks["D2"]["held"] is False
    assert checks["D1"]["measured"] == f"{f['replayed']:.3f}"
    assert checks["D3"]["held"] is True  # the loop's turn: launched at once by the scout
    md = replay_report.render(s)
    assert "## The number reported first (cloud/PREREG_RECORD.md)" in md
    assert "another.fix1, some-session.fix2" in md and "| D2 |" in md
    assert "By the rule fixed beforehand: " in md
    assert "## The predictions (cloud/PREREG_REPLAY.md" not in md  # the other run's


def test_extra_units_run_last_on_their_own_sessions_and_are_kept_apart(designed):
    begin = designed.notes[0]
    assert begin["extra_units"] == ["nospec_c2_r1", "stream_c2_r1"]
    assert begin["extra_sessions"] == ["trec-fake-1.fix1"]
    assert set(begin["arm_config"]) == {"stream", "scout", "nospec"}
    for name in ("nospec_c2_r1", "stream_c2_r1"):
        fid = json.loads((designed.out / "extra" / "units" / name / "replay.json").read_text())
        assert fid["exact"] and [f["session"] for f in fid["sessions"]] == ["trec-fake-1.fix1"]
    # the registered units are as they were: no `nospec` among them, two sessions each
    assert not (designed.out / "units" / "nospec_c2_r1").exists()
    assert designed.summary["arm_names"] == ["stream", "scout"]
    assert all(u["sessions"] == 2 for u in designed.summary["units"])
    # a summary of their own, with no prediction of any pre-registration in it
    extra = replay_report.summarize(designed.out / "extra")
    assert extra["arm_names"] == ["nospec", "stream"] and extra["design"]["predictions"] is False
    assert not any(k in extra for k in ("prereg", "addendum", "prereg_fixed", "first"))
    md = (designed.out / "extra" / "summary.md").read_text()
    assert "## Arms" in md and "## The predictions" not in md


def test_the_budget_stop_reaches_extra_units_too(cut, tmp_path):
    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(tmp_path / "o"), "--corpus", str(cut.corpus),
                              "--units", "scout:1", "--extra-units", "stream:1",
                              "--estimates", "scout=1,extra-stream=600", "--max-minutes", "5",
                              "--conc", "2", "--base-url", eng.base_url, "--model", eng.model])
    notes = [json.loads(x) for x in (tmp_path / "o" / "campaign.jsonl").read_text().splitlines()]
    (stop,) = [n for n in notes if n["kind"] == "budget_stop"]
    assert stop["unit"] == "extra/stream_c2_r1" and stop["estimate_s"] == 600
    assert [n["unit"] for n in notes if n["kind"] == "unit_begin"] == ["scout_c2_r1"]
    assert not (tmp_path / "o" / "extra").exists()


def test_the_budget_stop_uses_the_estimate_of_an_arm_that_has_not_run(cut, tmp_path):
    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(tmp_path / "o"), "--corpus", str(cut.corpus),
                              "--units", "stream:1,scout:1", "--estimates", "stream=600",
                              "--max-minutes", "5", "--conc", "2", "--base-url", eng.base_url,
                              "--model", eng.model])
    notes = [json.loads(x) for x in (tmp_path / "o" / "campaign.jsonl").read_text().splitlines()]
    (stop,) = [n for n in notes if n["kind"] == "budget_stop"]
    assert stop["unit"] == "stream_c2_r1" and stop["estimate_s"] == 600
    assert not [n for n in notes if n["kind"] == "unit_begin"]


def test_the_rule_for_the_readme():
    rule = replay_report.readme_rule
    assert "the gain holds" in rule({"all": 0.75, "carriers": ["a", "b"]})
    assert "one session carries it" in rule({"all": 0.75, "carriers": ["a"]})
    assert "mostly the bug's" in rule({"all": 0.90, "carriers": ["a", "b"]})
    assert "gains little" in rule({"all": 0.97, "carriers": []})
    assert rule(None) is None
