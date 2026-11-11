"""The replay bench, locally: record a run, build the corpus from it, replay it.

The recorded run is a real `nospec` unit of rlm_campaign.py against the scripted fake
server. Its script calls llm_query_batched three times, so stock rlms 0.1.3 loses prompts
of the second and third batch to 'Event loop is closed', as it did on the H100. The corpus
has to find those, and every arm has to give the program the same strings again."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
import replay
import replay_campaign
import replay_corpus
import replay_report
import rlm.environments as rlm_envs
import rlm_campaign
from fake_engine import FakeEngineServer
from fake_rlm_server import FakeRLMServer

STOCK = rlm_envs.LocalREPL
CONTEXT = "abcdefghij" * 10
TURN0 = (
    "I label six parts one by one, then classify sixty questions in batches.\n"
    "```repl\n"
    "parts = [context[i:i+10] for i in range(0, 100, 10)]\n"
    "labels = []\n"
    "for p in parts[:6]:\n"
    "    labels.append(llm_query('Label this: ' + p).strip())\n"  # each result is used
    "print(labels)\n"
    "```\n"
    "Now the batches.\n"
    "```repl\n"
    "qs = ['Q' + str(i % 25) for i in range(60)]\n"  # 25 distinct questions, asked again
    "out = []\n"
    "for i in range(0, 60, 20):\n"
    "    res = llm_query_batched(['Classify: ' + q for q in qs[i:i+20]])\n"
    "    out.extend(res)\n"
    "print(sum(1 for r in out if r.startswith('Error')), out[:2], out[20:22], out[40:42])\n"
    "```\n"
    + "Waiting for the results now. " * 12
)
TURN1 = (
    "```repl\n"
    "answer['content'] = str(len(labels)) + ' ' + str(len(out))\n"
    "answer['ready'] = True\n"
    "```\n"
)


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """runs/<run>/units/nospec_c1_r1 as the campaign writes it, and its tasks.json."""
    root = tmp_path_factory.mktemp("rec")
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_id": f"trec-fake-{i}", "dataset": "trec_coarse_131072", "context": CONTEXT,
         "question": "How many parts?", "hint": "Hint.", "answer": "['4']",
         "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(2)]))
    try:
        with FakeRLMServer([TURN0, TURN1], token_s=0.002, sub_s=0.02) as srv:
            rlm_campaign.main(["run", "--out", str(root / "runs" / "run1"), "--tasks", str(tasks),
                               "--model", srv.model, "--base-url", srv.base_url, "--arms",
                               "nospec", "--conc", "1", "--repeats", "1",
                               "--metrics-every", "0.2"])
    finally:
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    return SimpleNamespace(root=root, runs=root / "runs", tasks=tasks)


@pytest.fixture(scope="module")
def corpus(recorded):
    out = recorded.root / "corpus"
    manifest = replay_corpus.build(recorded.runs, recorded.tasks, out,
                                   tokens=replay_corpus.Tokens(False))
    return SimpleNamespace(dir=out, manifest=manifest)


def test_the_corpus_finds_the_prompts_rlms_lost_and_reproduces_the_run(corpus):
    rows = corpus.manifest["sessions"]
    assert [r["session"] for r in rows] == ["trec-fake-0", "trec-fake-1"]
    for r in rows:
        assert r["replayable"] and r["problems"] == []
        assert r["turns"] == 2 and r["final"] == "answer"
        assert (r["singles"], r["batches"]) == (6, 3)
        # rlms answered 20 of the first batch, 4 of the second and 16 of the third
        assert (r["calls"], r["errors"]) == (6 + 40, 20)
        assert r["prompts_with_differing_outcomes"] > 0  # a question answered once, lost once
    sess = replay_corpus.load_session(corpus.dir / "trec-fake-0.json")
    q0 = sess["calls"]["Classify: Q0"]  # in batch 1 (answered), 2 (lost) and 3 (answered)
    assert ["e" in o for o in q0] == [False, True, False]
    assert q0[1]["e"] == replay_corpus.LOOP_ERROR
    t0 = sess["turns"][0]
    assert t0["cuts"][-1] == len(t0["reply"]) and len(t0["cuts"]) == t0["n_deltas"]
    assert [b["invocations"] for b in t0["blocks"]] == [
        [["single", 1, 0]] * 6, [["batch", 20, 0], ["batch", 20, 16], ["batch", 20, 4]]]
    assert "replayable" in replay_corpus.render(corpus.manifest) or "trec-fake-0" in \
        replay_corpus.render(corpus.manifest)


def test_a_session_that_does_not_reproduce_is_left_out(recorded, tmp_path):
    """The build runs each session again and compares. Tamper with one recorded answer
    that the program prints: that session must be refused, the other kept."""
    runs = tmp_path / "runs"
    import shutil

    shutil.copytree(recorded.runs, runs)
    traj = sorted((runs / "run1" / "units" / "nospec_c1_r1" / "rlm_trajs").glob("trec-fake-0_*"))[0]
    lines = [json.loads(x) for x in traj.read_text().splitlines()]
    for d in lines:
        if d.get("type") == "iteration" and d["code_blocks"] and d["code_blocks"][0]["result"]["rlm_calls"]:
            d["code_blocks"][0]["result"]["rlm_calls"][0]["response"] = "label: tampered"
            break
    traj.write_text("\n".join(json.dumps(d) for d in lines) + "\n")
    m = replay_corpus.build(runs, recorded.tasks, tmp_path / "corpus",
                            tokens=replay_corpus.Tokens(False))
    by = {r["session"]: r for r in m["sessions"]}
    assert not by["trec-fake-0"]["replayable"] and by["trec-fake-1"]["replayable"]
    assert any("output differs" in p for p in by["trec-fake-0"]["problems"])
    assert not (tmp_path / "corpus" / "trec-fake-0.json").exists()


@pytest.fixture(scope="module")
def campaign(corpus, recorded):
    """Every arm once, each unit in its own process with its own spec-ptc."""
    out = recorded.root / "replay"
    arms = "nospec,stream,scout,wide"
    with FakeEngineServer(step_ms=6.0) as eng:
        replay_campaign.main(["run", "--out", str(out), "--corpus", str(corpus.dir), "--arms",
                              arms, "--once", "wide-threads,nospec-wide", "--repeats", "1",
                              "--conc", "2", "--base-url", eng.base_url, "--model", eng.model,
                              "--metrics-every", "0.1"])
        stats = dict(eng.engine.counters)
    return SimpleNamespace(out=out, stats=stats, summary=replay_report.summarize(out))


def unit(campaign, name):
    d = campaign.out / "units" / name
    return SimpleNamespace(
        dir=d, meta=json.loads((d / "unit.json").read_text()),
        fid=json.loads((d / "replay.json").read_text()),
        events=[json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()])


ALL = ["nospec_c2_r1", "stream_c2_r1", "scout_c2_r1", "wide_c2_r1", "wide-threads_c2_r1",
       "nospec-wide_c2_r1"]


def test_every_arm_replays_the_recorded_sessions_exactly(campaign):
    begun = [json.loads(x)["unit"] for x in (campaign.out / "campaign.jsonl").read_text()
             .splitlines() if json.loads(x)["kind"] == "unit_begin"]
    assert begun == ALL  # the repeat in the order given, then the arms that run once
    for name in ALL:
        u = unit(campaign, name)
        assert u.fid["exact"], (name, u.fid)
        for s in u.fid["sessions"]:
            assert s["ok"] and s["turns"] == s["rec_turns"] == 2
            assert s["prompt_matches"] == s["prompts"] == 2 and s["answer_match"]
            assert s["unrecorded"] == 0 and s["repeats"] == 0
            assert (s["calls"], s["errors"]) == (46, 20)  # the same requests, the same errors
            assert s["score"] == s["rec_score"]
    # 6 units x 2 sessions x (2 root turns + 46 sub-calls): nothing sent twice, nothing lost
    assert campaign.stats["requests"] == 6 * 2 * 48


def test_each_arm_runs_its_own_spec_ptc(campaign):
    for name, tree in [("nospec_c2_r1", "spec-ptc"), ("stream_c2_r1", "spec-ptc"),
                       ("scout_c2_r1", "spec-ptc-sptc-hints"), ("wide_c2_r1", "spec-ptc-sptc-hints")]:
        meta = unit(campaign, name).meta
        assert meta["spec_ptc_file"].endswith(f"/{tree}/src/__init__.py"), meta["spec_ptc_file"]
        assert meta["hash_seed"] == "0"
    begin = json.loads((campaign.out / "campaign.jsonl").read_text().splitlines()[0])
    assert begin["kind"] == "begin" and set(begin["trees"]) == {"stock", "fork"}
    assert begin["trees"]["stock"]["py_tree"] != begin["trees"]["fork"]["py_tree"]
    assert len(begin["corpus"]["manifest_sha256"]) == 64 and len(begin["corpus"]["sessions"]) == 2
    assert unit(campaign, "stream_c2_r1").meta["spec_ptc_py_tree"] == begin["trees"]["stock"]["py_tree"]


def spec_counts(u):
    out: dict = {}
    for e in u.events:
        if e["kind"].startswith("spec_"):
            out[e["kind"][5:]] = out.get(e["kind"][5:], 0) + 1
    return out


def test_the_arms_differ_in_when_calls_are_sent_not_in_what_is_sent(campaign):
    def loop_turn(name):  # the first turn of each session: the loop and the batches
        return [t for t in replay_report.unit_turns(_loaded(campaign, name)) if t["iteration"] == 1]

    nospec, stream = loop_turn("nospec_c2_r1"), loop_turn("stream_c2_r1")
    scout, wide = loop_turn("scout_c2_r1"), loop_turn("wide_c2_r1")
    assert all(t["dispatched"] == 0 for t in nospec)
    # as shipped: the loop's six calls are speculated, one after another (each result is
    # used). Then the shadow thread dies peeking a loop whose call takes a list
    # (spec-ptc shadow.py:314, TypeError), and the real run makes the 60 batch calls itself.
    assert all(t["hits"] == 6 and t["misses"] == 60 for t in stream)
    assert "unhashable type: 'list'" in (unit(campaign, "stream_c2_r1").dir / "unit.log").read_text()
    # the scout: everything known at the statement goes out at once, and is adopted
    c = spec_counts(unit(campaign, "scout_c2_r1"))
    assert c["dispatch"] == 2 * 66 and c["adopt"] == 2 * 66 and c["claim_hit"] == 2 * 66
    assert c.get("claim_miss", 0) == 0 and c.get("evict", 0) == 0
    w = unit(campaign, "wide_c2_r1")
    assert sum(1 for e in w.events if e["kind"] == "spec_dispatch" and e.get("batch")) == 2 * 60
    after = {n: sum(t["after_s"] for t in ts) for n, ts in
             [("nospec", nospec), ("stream", stream), ("scout", scout), ("wide", wide)]}
    assert after["scout"] < after["stream"] <= after["nospec"] * 1.2
    assert after["wide"] < after["nospec"]


def _loaded(campaign, name):
    return next(u for u in replay_report.load(campaign.out) if u["unit"] == name)


def test_the_report_compares_arms_turn_by_turn(campaign):
    s = campaign.summary
    assert s["arm_names"] == ["nospec", "stream", "scout", "wide", "wide-threads", "nospec-wide"]
    assert all(r["exact_units"] == r["units"] == 1 for r in s["arms"])
    rows = {r["arm"]: r for r in s["arms"]}
    assert rows["scout"]["session_ratio_vs_stream"]["sessions"] == 2
    assert rows["scout"]["after_s"] < rows["stream"]["after_s"]
    md = replay_report.render(s)
    for head in ("## Arms", "## Sessions", "## Units, in the order they ran",
                 "## What speculation did", "## Fidelity"):
        assert head in md
    assert (campaign.out / "summary.md").exists() and (campaign.out / "summary.json").exists()


# ------------------------------------------------------------------ pieces
def test_outcomes_are_handed_out_in_program_order_whatever_the_threads_do():
    calls = {"p": [{"r": "first", "n": 2}, {"e": "Error: x"}, {"r": "third", "n": 2}]}
    o = replay.Outcomes(calls)
    # three speculative launches, in program order; their threads ask in another order
    for seq in (11, 12, 13):
        o.bind(seq, "p")
    assert o.claim(13, "p")["r"] == "third"
    assert o.claim(11, "p")["r"] == "first"
    assert "e" in o.claim(12, "p")
    # a fourth call for the prompt: more than the recorded run made
    assert o.take("p")["r"] == "third" and o.repeats == 1
    assert o.take("never sent")["u"] and o.unrecorded == 1


def test_an_evicted_speculation_gives_its_outcome_back():
    o = replay.Outcomes({"p": [{"r": "a", "n": 1}, {"r": "b", "n": 1}]})
    o.bind(1, "p")
    o.bind(2, "p")
    o.release(1)  # the program never used it
    assert o.take("p")["r"] == "a"  # so the program's own call gets the first answer
    assert o.claim(2, "p")["r"] == "b"
    assert o.released == 1 and o.repeats == 0


def test_tickets_ride_in_front_of_the_prompt_and_come_off():
    assert replay.split_ticket(replay.ticket(42) + "Classify: x") == (42, "Classify: x")
    assert replay.split_ticket("Classify: x") == (None, "Classify: x")


def test_the_block_oracle_reads_a_lost_prefix_and_a_batch_lost_whole():
    def call(p, t):
        return {"prompt": p, "response": "r:" + p, "execution_time": t}

    recorded = [call("a3", 0.1), call("a4", 0.1),  # batch A: a1, a2 were lost
                call("c1", 0.3), call("c2", 0.3)]  # batch B lost whole; batch C answered
    o = replay_corpus.BlockOracle(recorded, replay_corpus.Tokens(False), [])
    assert o.batch(["a1", "a2", "a3", "a4"]) == [replay_corpus.LOOP_ERROR] * 2 + ["r:a3", "r:a4"]
    assert o.batch(["b1", "b2"]) == [replay_corpus.LOOP_ERROR] * 2
    assert o.batch(["c1", "c2"]) == ["r:c1", "r:c2"]
    assert o.p == 4 and o.problems == []


def test_plan_units_is_abba_with_the_single_units_last():
    assert replay_campaign.plan_units(["a", "b"], 2, ["x"]) == [
        ("a", 1), ("b", 1), ("b", 2), ("a", 2), ("x", 1)]


def test_the_root_is_the_recorded_reply_at_the_engines_pace():
    from rlm.clients.openai import OpenAIClient

    reply = "one two three four five six seven eight nine ten"
    words = reply.split(" ")
    cuts, n = [], 0
    for i, w in enumerate(words):
        n += len(w) + (1 if i < len(words) - 1 else 0)
        cuts.append(n)
    prompt = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    turn = {"prompt_sha": replay.sha(prompt), "reply": reply, "tokens": 11, "n_deltas": 10,
            "cuts": cuts}
    sess = replay.Session({"session": "s1", "turns": [turn], "final": {"kind": "answer",
                                                                       "text": "x"},
                           "calls": {}}, salt="[t] ")
    got: list[tuple[float, str]] = []
    with FakeEngineServer(step_ms=20.0) as eng:
        client = OpenAIClient(api_key="EMPTY", model_name=eng.model, base_url=eng.base_url)
        client.session = sess
        text, timing = replay.stream_root(client, prompt,
                                          lambda d: got.append((time.perf_counter(), d)))
        assert text == reply and "".join(d for _, d in got) == reply
        assert timing["prompt_match"] and timing["tokens"] == 11 and timing["n_deltas"] == 10
        gaps = [b[0] - a[0] for a, b in zip(got, got[1:], strict=False)]
        assert min(gaps) > 0.010 and timing["stream_s"] > 10 * 0.020  # one delta per engine token
        # a second turn the recording does not have: the replay stops there
        with pytest.raises(replay.ReplayDivergence):
            replay.stream_root(client, prompt)
        # another message history than the recorded one is reported, not hidden
        sess.k = 0
        _, timing2 = replay.stream_root(client, prompt + [{"role": "user", "content": "more"}])
        assert timing2["prompt_match"] is False


def test_a_replayed_error_comes_back_as_the_string_the_program_saw():
    """Single calls and batches reach rlms by different paths; both must rebuild the text."""
    from rlm.core.lm_handler import LMHandler
    from rlm.environments.local_repl import LocalREPL

    err = replay_corpus.LOOP_ERROR
    calls = {"lost": [{"e": err}, {"e": err}], "kept": [{"r": "fine", "n": 2}, {"r": "fine", "n": 2}]}
    sess = replay.Session({"session": "s1", "turns": [], "final": {"kind": "answer", "text": ""},
                           "calls": calls}, salt="")
    cls = replay.make_client_class()
    with FakeEngineServer(step_ms=2.0) as eng:
        client = cls(sess, api_key="EMPTY", model_name=eng.model, base_url=eng.base_url)
        with LMHandler(client) as h:
            repl = LocalREPL(lm_handler_address=h.address, context_payload="ctx")
            r = repl.execute_code("a = llm_query_batched(['lost', 'kept'])\n"
                                  "b = [llm_query('lost'), llm_query('kept')]\nprint(a == b, a)")
            repl.cleanup()
        assert r.stdout.strip() == f"True {[err, 'fine']!r}", r.stdout + r.stderr
        assert eng.engine.counters["requests"] == 2  # the lost prompts were never sent


def test_the_report_checks_the_registered_predictions(campaign):
    checks = {p["id"]: p for p in campaign.summary["prereg"]}
    assert list(checks) == [f"P{i}" for i in range(1, 11)] + ["live run"]
    assert checks["P1"]["held"] is True and checks["P1"]["measured"].startswith("6 of 6 exact")
    assert checks["P2"]["held"] is True  # nothing evicted
    assert checks["P9"]["held"] is None  # one unit per arm here: no repeat to compare
    # the named turn of the corpus is not in this toy run: reported as not testable
    assert checks["P3"]["held"] is None and checks["P3"]["measured"] == "-"
    md = replay_report.render(campaign.summary)
    assert "## The predictions" in md and "not testable" in md


def test_a_prediction_that_fails_is_shown_as_failed():
    def arm(name, wall, stream):
        return {"arm": name, "wall_s": wall, "stream_s": stream}

    s = {"arms": [arm("nospec", 100.0, 60.0), arm("stream", 99.0, 60.0),
                  arm("scout", 95.0, 60.0), arm("wide", 60.0, 80.0)],
         "units": [{"unit": "scout_c8_r1", "exact": False, "unrecorded": 2, "repeats": 0,
                    "spec": {"evict": 3}}],
         "waited": [], "noise": [{"wall_ratio": 1.2}],
         "recovery": [{"cause": "serial launches", "arms": {
             "scout": {"recovered_share": 0.4}, "wide": {"recovered_share": 0.9}}}]}
    checks = {p["id"]: p for p in replay_report.prereg(s)}
    assert checks["P1"]["held"] is False and "scout_c8_r1" in checks["P1"]["measured"]
    assert checks["P2"]["held"] is False and checks["P5"]["held"] is False
    assert checks["P7"]["held"] is False  # scout is 0.96 of stream, not 0.80
    assert checks["P8"]["held"] is False  # wide's root streams are a third longer
    assert checks["P9"]["held"] is False
    assert checks["live run"]["held"] is False  # faster, but the root paid for it
