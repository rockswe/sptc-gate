"""spec-ptc's character budget, and the arm that lifts it.

As shipped, spec-ptc keeps at most 120,000 characters of speculative prompts in flight per
session (Budget.max_inflight_chars). A loop that only stores its results is launched whole
by the shadow, but of three 50,000-character calls only two then run together. The
`stream-open` arm sets the budget aside."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import replay_campaign
import replay_corpus
import rlm.environments as rlm_envs
import rlm_campaign
from fake_engine import FakeEngineServer
from fake_rlm_server import FakeRLMServer

STOCK = rlm_envs.LocalREPL
LONG = (
    "Three long chunks, one call each.\n"
    "```repl\n"
    "chunks = [str(i) * 50000 for i in range(3)]\n"
    "results = []\n"
    "for chunk in chunks:\n"
    "    results.append(llm_query('Classify every line of: ' + chunk))\n"  # stored, not used
    "print(len(results))\n"
    "```\n"
    + "Waiting for the results now. " * 12
)
DONE = "```repl\nanswer['content'] = str(len(results))\nanswer['ready'] = True\n```\n"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("chars")
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_id": "trec-fake-0", "dataset": "trec_coarse_131072", "context": "abcdefghij" * 10,
         "question": "How many parts?", "hint": "Hint.", "answer": "['4']",
         "answer_type": "ANSWER_TYPE.NUMERIC"}]))
    try:
        with FakeRLMServer([LONG, DONE], token_s=0.002, sub_s=0.02) as srv:
            rlm_campaign.main(["run", "--out", str(root / "runs" / "run1"), "--tasks", str(tasks),
                               "--model", srv.model, "--base-url", srv.base_url, "--arms",
                               "nospec", "--conc", "1", "--repeats", "1",
                               "--metrics-every", "0.2"])
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    replay_corpus.build(root / "runs", tasks, root / "corpus", tokens=replay_corpus.Tokens(False))
    return SimpleNamespace(root=root, dir=root / "corpus")


def replay_arm(corpus, arm):
    out = corpus.root / f"replay-{arm}"
    with FakeEngineServer(step_ms=40.0) as eng:  # a sub-call of 4 tokens lasts 160 ms
        replay_campaign.main(["run", "--out", str(out), "--corpus", str(corpus.dir), "--units",
                              f"{arm}:1", "--conc", "1", "--base-url", eng.base_url,
                              "--model", eng.model, "--metrics-every", "0.1"])
    d = out / "units" / f"{arm}_c1_r1"
    assert json.loads((d / "replay.json").read_text())["exact"]
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]
    return SimpleNamespace(
        dispatch=sorted(float(e["t"]) for e in ev if e["kind"] == "spec_dispatch"),
        # when each request left for the engine, and how long it then took
        sent=sorted(float(e["t0"]) for e in ev if e["kind"] == "replay_call"),
        took=sorted(float(e["ms"]) / 1000 for e in ev if e["kind"] == "replay_call"))


def test_as_shipped_the_calls_are_launched_together_and_one_waits_for_room(corpus):
    r = replay_arm(corpus, "stream")
    assert len(r.dispatch) == 3 and r.dispatch[-1] - r.dispatch[0] < 0.05  # launched as one
    # two requests leave at once; the third is held until one of them is back: 150,000
    # characters do not fit a budget of 120,000
    assert r.sent[1] - r.sent[0] < 0.05
    assert r.sent[2] - r.sent[0] > 0.8 * r.took[0]


def test_with_the_budget_lifted_all_three_leave_at_once(corpus):
    r = replay_arm(corpus, "stream-open")
    assert len(r.dispatch) == 3 and r.dispatch[-1] - r.dispatch[0] < 0.05
    assert r.sent[2] - r.sent[0] < 0.05
