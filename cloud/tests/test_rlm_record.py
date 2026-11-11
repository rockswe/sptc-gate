"""cloud/rlm_record.py against the fake server: the campaign with rlms' batch path fixed.

The script is test_replay's: six single calls in a loop, then three batches of 20. Stock
rlms loses 20 of the 60 batch prompts there (test_replay.py records exactly that)."""

from __future__ import annotations

import hashlib
import json

import batch_fix
import pytest
import record_report
import replay_campaign
import replay_corpus
import rlm.environments as rlm_envs
import rlm_campaign
import rlm_record
from fake_engine import FakeEngineServer
from fake_rlm_server import FakeRLMServer
from rlm.core.lm_handler import LMHandler
from test_replay import TURN0, TURN1

STOCK = rlm_envs.LocalREPL


def tasks_file(tmp_path, n=2):
    rows = [{"task_id": f"trec-fake-{i}", "dataset": "trec_coarse_131072",
             "context": "abcdefghij" * 10, "question": "How many parts?", "hint": "Hint.",
             "answer": "['4']", "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(n)]
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps(rows))
    return p


def notes(out, kind=None):
    rows = [json.loads(x) for x in (out / "campaign.jsonl").read_text().splitlines()]
    return rows if kind is None else [r for r in rows if r["kind"] == kind]


def record(tmp_path, srv, *extra, n=2):
    out = tmp_path / "runs" / "rec1"
    try:
        rlm_record.main(["run", "--out", str(out), "--tasks", str(tasks_file(tmp_path, n)),
                         "--model", srv.model, "--base-url", srv.base_url, "--conc", "2",
                         "--repeats", "1", "--metrics-every", "0.2", "--warmup-passes", "1",
                         *extra])
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    return out


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(rlm_campaign, "WARMUP_WAVES", ((2, "short"),))
    monkeypatch.setattr(rlm_record, "PROBE_GAPS", (0.0,))


def blocks(out, unit, task):
    f = sorted((out / "units" / unit / "rlm_trajs").glob(f"{task}_*.jsonl"))[-1]
    its = [json.loads(x) for x in f.read_text().splitlines()]
    return [b for it in its if it.get("type") == "iteration" for b in it["code_blocks"]]


def test_a_recording_probes_the_engine_then_loses_no_prompt_in_any_arm(tmp_path, quick):
    before = (rlm_campaign.warmup, rlm_campaign.PROVENANCE_FILES, LMHandler.get_client)
    with FakeRLMServer([TURN0, TURN1], token_s=0.002, sub_s=0.02) as srv:
        out = record(tmp_path, srv, "--arms", "nospec,stream")

    # the probes come after the warm-up's waves and before the first unit
    kinds = [r["kind"] for r in notes(out)]
    assert kinds.index("warmup_wave") < kinds.index("batch_probe") < kinds.index("unit_begin")
    stock, fixed = notes(out, "batch_probe")
    assert stock["fixed"] is False and [b["errors"] for b in stock["batches"]] == [0, 16, 4, 16]
    assert fixed["fixed"] is True and fixed["errors"] == 0 and fixed["prompts"] == 80

    # what defined the run is hashed before its first unit, the fix and the plan included
    begin = notes(out, "begin")[0]
    assert begin["arms"] == ["nospec", "stream"]
    assert set(rlm_record.EXTRA_PROVENANCE) <= set(begin["files"])
    assert begin["files"]["batch_fix.py"] == hashlib.sha256(
        (rlm_campaign.HERE / "batch_fix.py").read_bytes()).hexdigest()

    for unit in ("nospec_c2_r1", "stream_c2_r1"):
        for task in ("trec-fake-0", "trec-fake-1"):
            loop, batches = blocks(out, unit, task)[:2]
            # the program counted its error strings: none, where stock rlms gives 20
            assert batches["result"]["stdout"].startswith("0 "), batches["result"]["stdout"]
        fix = json.loads((out / "units" / unit / "batch_fix.json").read_text())
        assert fix["applied"] is True and fix["failed"] == {} and fix["deadline_tasks"] == []
        assert fix["subcall_deadline_s"] == rlm_record.DEADLINE_S
    # nospec sends its batches itself. The shipped client's shadow dies on the batch peek
    # (shadow.py:314), so its real run sends them too: both go through the fix.
    for unit in ("nospec_c2_r1", "stream_c2_r1"):
        fix = json.loads((out / "units" / unit / "batch_fix.json").read_text())
        assert fix["calls"] == 2 * 60
    loop, batches = blocks(out, "nospec_c2_r1", "trec-fake-0")[:2]
    assert len(loop["result"]["rlm_calls"]) == 6 and len(batches["result"]["rlm_calls"]) == 60
    assert not any(e["kind"] == "subcall_deadline" for e in map(
        json.loads, (out / "units" / "nospec_c2_r1" / "events.jsonl").read_text().splitlines()))

    # the corpus built from it has no error outcome: the replay will send every prompt
    m = replay_corpus.build(tmp_path / "runs", tmp_path / "tasks.json", tmp_path / "corpus",
                            tokens=replay_corpus.Tokens(False))
    rows = {r["session"]: r for r in m["sessions"]}
    assert set(rows) == {"trec-fake-0", "trec-fake-1"}
    for r in rows.values():
        assert r["replayable"] and (r["calls"], r["errors"]) == (66, 0)
        assert (r["singles"], r["batches"]) == (6, 3)

    # nothing stays patched once the run is over
    assert (rlm_campaign.warmup, rlm_campaign.PROVENANCE_FILES, LMHandler.get_client) == before
    assert not batch_fix.applied()

    # the census of the same run: what each session wrote, and the recording's predictions
    replay_corpus.build(tmp_path / "runs", tmp_path / "tasks.json", tmp_path / "corpus_fix",
                        tokens=replay_corpus.Tokens(False), tag="fix")
    c = record_report.census(out, tmp_path / "corpus_fix")
    assert [s["session"] for s in c["sessions"]] == ["trec-fake-0.fix1", "trec-fake-1.fix1"]
    for s in c["sessions"]:
        assert s["status"] == "finished" and s["replay"] == "yes" and s["corpus_errors"] == 0
        assert (s["calls"], s["singles"], s["batches"]) == (66, 6, 3)
        assert s["batch_sizes"] == [20, 20, 20] and s["max_calls_in_a_turn"] == 66
        assert s["single_loops"] == [] and s["batch_loops"] == []  # 6 calls, 3 batches: no loop
        assert s["loop_error_strings"] == 0 and s["turns"] == 2
    checks = {p["id"]: p for p in c["predictions"]}
    assert checks["R1"]["held"] is True and checks["R1"]["measured"].startswith("0 of 120")
    assert checks["R2"]["held"] is True and checks["R2"]["measured"].startswith("36 of 80")
    assert checks["R3"]["held"] is False and checks["R4"]["held"] is False  # no loop here
    assert checks["R5"]["held"] is True and checks["R6"]["held"] is None  # none was stopped
    md = record_report.render(c)
    for head in ("## The predictions", "## Sessions", "## The probe before the first unit",
                 "## Batched prompts, by unit"):
        assert head in md
    d = record_report.design_of(c)  # what a replay design takes from the census
    assert d["sessions"] == ["trec-fake-0.fix1", "trec-fake-1.fix1"] and d["left_out"] == {}
    assert d["single_loops"] == [] and d["batch_loops"] == [] and d["checks"] == []
    assert "Classify" not in md and "Label this" not in md  # no text of a session


def test_the_census_names_loops_and_applies_the_rule_for_leaving_a_session_out(monkeypatch):
    def call(t, n=1):
        return [{"prompt": "p", "response": "r", "execution_time": t}] * n

    loop = [c for i in range(25) for c in call(0.1 + i * 1e-3)]  # 25 calls, one at a time
    batches = [c for i in range(6) for c in call(0.2 + i * 1e-3, 20)]  # 6 batches of 20
    a, b = record_report.turn_shape(loop), record_report.turn_shape(batches)
    assert (a["singles"], a["batches"], a["single_loop"], a["batch_loop"]) == (25, 0, True, False)
    assert (b["singles"], b["batches"], b["single_loop"], b["batch_loop"]) == (0, 6, False, True)
    assert b["batch_sizes"] == [20] * 6 and b["calls"] == 120
    few = record_report.turn_shape(call(0.1) + call(0.3, 4))
    assert (few["singles"], few["batches"], few["single_loop"], few["batch_loop"]) == (
        1, 1, False, False)

    base = {"session": "t.fix1", "status": "finished", "error": "", "cut_replies": 0,
            "turns": 9, "recorded_turns": 9}
    state = record_report.replay_state
    assert state({**base, "max_calls_in_a_turn": 40, "after_s": 500.0}, None) == "yes"
    # four long calls, one per turn: nothing within a turn can overlap them
    assert state({**base, "max_calls_in_a_turn": 1, "after_s": 500.0}, None).startswith("left out")
    assert state({**base, "max_calls_in_a_turn": 1, "after_s": 30.0}, None) == "yes"
    assert state({**base, "max_calls_in_a_turn": 0, "after_s": 0.0}, None) == "yes"
    cut = {**base, "status": "timeout", "max_calls_in_a_turn": 160, "after_s": 800.0}
    assert state(cut, None) == "up to turn 9"
    assert state({**cut, "status": "deadline"}, None).startswith("no: the deadline")
    assert state({**base, "status": "failed", "error": "BadRequestError: too long",
                  "max_calls_in_a_turn": 3, "after_s": 1.0}, None) == "no: failed (BadRequestError)"
    assert state({**base, "cut_replies": 1, "max_calls_in_a_turn": 3, "after_s": 1.0},
                 None) == "no: a root reply was cut"
    manifest = {"sessions": [{"session": "t.fix1", "replayable": False,
                              "problems": ["turn 3 block 1: output differs"]}]}
    assert state({**base, "max_calls_in_a_turn": 3, "after_s": 1.0}, manifest).startswith(
        "no: does not reproduce (turn 3")
    stopped = [{"status": "timeout", "single_loops": [{"turn": 7}], "batch_loops": [],
                "loop_error_strings": 0},
               {"status": "deadline", "single_loops": [], "batch_loops": [],
                "loop_error_strings": 0}]
    checks = {p["id"]: p for p in record_report.predictions(stopped, [], [])}
    assert checks["R6"]["held"] is True and checks["R6"]["measured"] == "1 of 2"
    assert checks["R1"]["held"] is None and checks["R2"]["held"] is None  # nothing to read


def test_no_unit_runs_if_the_engine_loses_a_prompt_with_the_fix_on(tmp_path, quick, monkeypatch):
    real = batch_fix.probe

    def probe(base_url, model, **kw):
        p = real(base_url, model, **kw)
        if p["fixed"]:  # as if one connection had failed on this engine
            p["batches"][1]["errors"] = p["errors"] = 1
        return p

    monkeypatch.setattr(batch_fix, "probe", probe)
    with FakeRLMServer([TURN0, TURN1], token_s=0.002, sub_s=0.02) as srv:
        with pytest.raises(rlm_record.ProbeFailed, match="1 of 80 probe prompts"):
            record(tmp_path, srv)
    out = tmp_path / "runs" / "rec1"
    kinds = [r["kind"] for r in notes(out)]
    assert "unit_begin" not in kinds and kinds[-1] == "end"
    assert [p["fixed"] for p in notes(out, "batch_probe")] == [False, True]
    assert not batch_fix.applied()


SLOW = (
    "One call, a pause, then more calls.\n"
    "```repl\n"
    "import time\n"
    "a = llm_query('first')\n"
    "time.sleep(1.2)\n"
    "b = llm_query('second')\n"
    "c = llm_query_batched(['third', 'fourth'])\n"
    "print(a.startswith('label'), b, c)\n"
    "```\n"
)
DONE = "```repl\nanswer['content'] = 'done'\nanswer['ready'] = True\n```\n"


def test_a_task_past_its_deadline_gets_error_strings_and_is_marked_failed(tmp_path, quick,
                                                                          monkeypatch):
    monkeypatch.setattr(rlm_record, "DEADLINE_S", 0.6)
    with FakeRLMServer([SLOW, DONE], token_s=0.002, sub_s=0.02) as srv:
        out = record(tmp_path, srv, n=1)
        subs = [r["head"] for r in srv.log if r["kind"] == "sub" and "Reply with" not in r["head"]
                and "Classify the following" not in r["head"]]
    refused = "Error: sub-call refused: this task passed its deadline of 1 s"
    (block,) = blocks(out, "nospec_c2_r1", "trec-fake-0")[:1]
    assert block["result"]["stdout"].strip() == f"True {refused} {[refused, refused]!r}"
    assert subs == ["first"]  # nothing of the task reached the engine after the deadline
    stats = json.loads((out / "units" / "nospec_c2_r1" / "unit_stats.json").read_text())
    (row,) = stats["tasks"]
    # the session went on and answered; it is failed all the same, and so not a corpus session
    assert row["ok"] is False and row["final_answer"] == "done"
    assert row["error"] == "SubcallDeadline: 2 sub-call requests refused after 1 s"
    ev = [json.loads(x) for x in (out / "units" / "nospec_c2_r1" / "events.jsonl")
          .read_text().splitlines()]
    (hit,) = [e for e in ev if e["kind"] == "subcall_deadline"]
    assert hit["task_id"] == "trec-fake-0" and hit["refused"] == 2 and hit["ok_before"] is True
    fix = json.loads((out / "units" / "nospec_c2_r1" / "batch_fix.json").read_text())
    assert fix["deadline_tasks"] == ["trec-fake-0"]
    (s,) = record_report.census(out)["sessions"]
    assert s["status"] == "deadline" and s["replay"] == "no: the deadline stopped it"
    # the deadline struck in its first turn: no turn of its own is left for a replay
    (found,) = replay_corpus.discover(tmp_path / "runs")
    assert found["cut"] == "deadline"
    m = replay_corpus.build(tmp_path / "runs", tmp_path / "tasks.json", tmp_path / "corpus",
                            tokens=replay_corpus.Tokens(False), tag="fix")
    (row,) = m["sessions"]
    assert row["turns_kept"] == 0 and not row["replayable"]


FIRST = "Two calls first.\n```repl\nfirst = [llm_query('a'), llm_query('b')]\nprint(first)\n```\n"


def test_a_session_the_deadline_stopped_can_be_replayed_up_to_the_turn_before(tmp_path, quick,
                                                                              monkeypatch):
    """The turn in which the deadline struck got error strings: it is not the session's
    own. The turns before it are, and the session ends there in a replay."""
    monkeypatch.setattr(rlm_record, "DEADLINE_S", 0.6)
    with FakeRLMServer([FIRST, SLOW, DONE], token_s=0.002, sub_s=0.02) as srv:
        out = record(tmp_path, srv, n=1)
    (s,) = record_report.census(out)["sessions"]
    assert s["status"] == "deadline" and s["recorded_turns"] == 3
    m = replay_corpus.build(tmp_path / "runs", tmp_path / "tasks.json", tmp_path / "corpus",
                            tokens=replay_corpus.Tokens(False), tag="fix")
    (row,) = m["sessions"]
    assert row["cut"] == "deadline" and row["turns_kept"] == 1 and row["replayable"]
    assert row["turns"] == 1 and row["final"] == "deadline" and row["problems"] == []
    assert (row["calls"], row["errors"], row["singles"]) == (2, 0, 2)  # the first turn's only
    sess = replay_corpus.load_session(tmp_path / "corpus" / "trec-fake-0.fix1.json")
    assert sess["final"]["kind"] == "deadline"
    assert sess["final"]["text"] == replay_corpus.DEADLINE_TEXT and len(sess["turns"]) == 1
    # by PREREG_RECORD.md's rule the census still counts it as not replayed
    (s,) = record_report.census(out, tmp_path / "corpus")["sessions"]
    assert s["replay"] == "no: the deadline stopped it"

    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(tmp_path / "replay"), "--corpus",
                              str(tmp_path / "corpus"), "--units", "nospec:1,stream:1",
                              "--conc", "1", "--base-url", eng.base_url, "--model", eng.model,
                              "--metrics-every", "0.1"])
        requests = eng.engine.counters["requests"]
    for name in ("nospec_c1_r1", "stream_c1_r1"):
        fid = json.loads((tmp_path / "replay" / "units" / name / "replay.json").read_text())
        (f,) = fid["sessions"]
        assert fid["exact"] and f["cut"] and f["turns"] == f["rec_turns"] == 1
        assert f["prompt_matches"] == f["prompts"] == 2 and f["calls"] == 2
    assert requests == 2 * (1 + 2)  # one root turn and two sub-calls per unit, nothing after


def test_the_arm_defaults_to_nospec_and_a_warm_up_is_required(tmp_path):
    a = rlm_record.parse(["run", "--out", str(tmp_path), "--tasks", "t.json"])
    assert a.arms == ["nospec"]
    assert rlm_record.parse(["run", "--out", "o", "--tasks", "t", "--arms", "stream"]).arms == [
        "stream"]
    with pytest.raises(SystemExit, match="one subcommand"):
        rlm_record.parse(["summarize", "--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="warm-up"):
        rlm_record.run(a)  # --warmup-passes 0: the probe would never run
