"""Limits that follow the load, in the replay: the arms `auto` and
`auto-past`, the fake engine's load model they are tried on, and what the report says of
them.

`auto` is the fork with its window and its KV admission governed by what the engine
reports (spec_ptc.engine.load); `auto-past` also lets the scout go on past a test on a
result that cannot leave its loop. The recorded session below has both shapes the H100
recording had: a loop of batches that tests each result, and one batch larger than any
window."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from types import SimpleNamespace

import pytest
import replay
import replay_campaign
import replay_corpus
import replay_report
import rlm.environments as rlm_envs
import rlm_campaign
import rlm_record
from fake_engine import FakeEngineServer
from fake_rlm_server import FakeRLMServer

STOCK = rlm_envs.LocalREPL
TESTS_EACH = (
    "I count the labels batch by batch, then one large batch.\n"
    "```repl\n"
    "parts = [context[i:i+5] for i in range(0, 100, 5)]\n"
    "batches = [parts[i:i+4] for i in range(0, 20, 4)]\n"
    "yes = 0\n"
    "no = 0\n"
    "for batch in batches:\n"
    "    responses = llm_query_batched(['Label: ' + p for p in batch])\n"
    "    for resp in responses:\n"
    "        label = resp.strip()\n"
    "        if label == 'label: yes':\n"  # the test: neither arm of it can leave the loop
    "            yes += 1\n"
    "        else:\n"
    "            no += 1\n"
    "print(yes, no)\n"
    "```\n"
    "And one large batch.\n"
    "```repl\n"
    "big = llm_query_batched(['Classify: ' + str(i) for i in range(70)])\n"
    "print(len(big))\n"
    "```\n"
    + "Waiting for the results now. " * 12
)
DONE = ("```repl\nanswer['content'] = str(yes + no) + ' ' + str(len(big))\n"
        "answer['ready'] = True\n```\n")
UNITS = ["stream_c2_r1", "wide_c2_r1", "auto_c2_r1", "auto-past_c2_r1"]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """Two sessions recorded with rlms' batch path fixed, as the H100 recording was."""
    root = tmp_path_factory.mktemp("govern")
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_id": f"trec-fake-{i}", "dataset": "trec_coarse_131072",
         "context": "abcdefghij" * 10, "question": "How many parts?", "hint": "Hint.",
         "answer": "['4']", "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(2)]))
    saved = (rlm_campaign.WARMUP_WAVES, rlm_record.PROBE_GAPS)
    rlm_campaign.WARMUP_WAVES, rlm_record.PROBE_GAPS = ((2, "short"),), (0.0,)
    try:
        with FakeRLMServer([TESTS_EACH, DONE], token_s=0.002, sub_s=0.02) as srv:
            rlm_record.main(["run", "--out", str(root / "runs" / "rec1"), "--tasks", str(tasks),
                             "--model", srv.model, "--base-url", srv.base_url, "--conc", "2",
                             "--repeats", "1", "--metrics-every", "0.2", "--warmup-passes", "1"])
    finally:
        rlm_campaign.WARMUP_WAVES, rlm_record.PROBE_GAPS = saved
        rlm_envs.LocalREPL = rlm_envs.local_repl.LocalREPL = STOCK
    manifest = replay_corpus.build(root / "runs", tasks, root / "corpus",
                                   tokens=replay_corpus.Tokens(False), tag="fix")
    assert all(r["replayable"] and r["errors"] == 0 for r in manifest["sessions"])
    return SimpleNamespace(root=root, dir=root / "corpus",
                           sessions=[r["session"] for r in manifest["sessions"]])


@pytest.fixture(scope="module")
def campaign(corpus):
    out = corpus.root / "replay"
    design = corpus.root / "design.json"
    first = corpus.sessions[0]
    design.write_text(json.dumps({"kind": "checks", "name": "toy", "prereg": ["PREREG_GOVERN.md"],
                                  "checks": [
        {"id": "T1", "claim": "every `auto` unit is exact", "unit": ["auto", "exact"],
         "max": 0, "digits": 0},
        {"id": "T2", "claim": "`auto` sends calls above a window of 16",
         "govern": ["auto", "calls_above_16"], "min": 1, "digits": 0},
        {"id": "T3", "claim": "session time of the first session alone: `auto-past` at most "
         "1.5 of `stream`", "ratio": ["auto-past", "stream", "wall_s"], "sessions": [first],
         "max": 1.5},
        {"id": "T4", "claim": "the turn with the loop: `auto-past` after its stream",
         "turn_s": [first, 1, "auto-past"], "max": 30, "digits": 1},
        {"id": "T5", "claim": "an arm that did not run", "ratio": ["nospec", "stream", "wall_s"],
         "max": 1.0},
        {"id": "T6", "claim": "nothing preempted in `auto`", "unit": ["auto", "preemptions"],
         "max": 0, "digits": 0}]}))
    with FakeEngineServer(step_ms=60.0) as eng:  # a sub-call of 3 tokens lasts about 0.2 s
        replay_campaign.main(["run", "--out", str(out), "--corpus", str(corpus.dir),
                              "--units", "stream:1,wide:1,auto:1,auto-past:1", "--conc", "2",
                              "--base-url", eng.base_url, "--model", eng.model,
                              "--metrics-every", "0.1", "--design-file", str(design),
                              "--warm-arm", "auto", "--warm-sessions", first])
        stats = dict(eng.engine.counters)
    return SimpleNamespace(out=out, stats=stats, summary=replay_report.summarize(out))


def events(campaign, name):
    d = campaign.out / "units" / name
    return [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]


def test_the_governed_arms_replay_the_recorded_sessions_exactly(campaign):
    for name in UNITS:
        fid = json.loads((campaign.out / "units" / name / "replay.json").read_text())
        assert fid["exact"], (name, fid)
        for s in fid["sessions"]:
            assert (s["calls"], s["errors"], s["unrecorded"], s["repeats"]) == (90, 0, 0, 0)
    # 4 units x 2 sessions x (2 root turns + 90 sub-calls), and the thrown-away unit's one
    # session: nothing sent twice, nothing lost
    assert campaign.stats["requests"] == 4 * 2 * 92 + 92
    assert campaign.stats["preemptions"] == 0


def test_the_thrown_away_unit_has_its_own_sessions(campaign, corpus):
    warm = campaign.out / "warm" / "auto_c2_r0"
    fid = json.loads((warm / "replay.json").read_text())
    assert fid["exact"] and [s["session"] for s in fid["sessions"]] == [corpus.sessions[0]]
    begin = json.loads((campaign.out / "campaign.jsonl").read_text().splitlines()[0])
    assert begin["warm_arm"] == "auto" and begin["warm_sessions"] == [corpus.sessions[0]]
    assert not (campaign.out / "units" / "auto_c2_r0").exists()  # it is in no table


def test_a_governed_unit_is_given_the_engines_metrics_and_runs_the_fork(campaign):
    begin = json.loads((campaign.out / "campaign.jsonl").read_text().splitlines()[0])
    assert begin["arm_config"]["auto"]["govern"] is True
    assert begin["arm_config"]["auto"]["kwargs"]["spec_govern"] is True
    assert begin["arm_config"]["auto-past"]["kwargs"]["spec_scout"] == "past"
    meta = json.loads((campaign.out / "units" / "auto_c2_r1" / "unit.json").read_text())
    assert meta["spec_ptc_file"].endswith("/spec-ptc-sptc-hints/src/__init__.py")
    moves = [e for e in events(campaign, "auto_c2_r1") if e["kind"] == "spec_govern"]
    assert moves, "the window never moved"
    assert moves[0]["was"] == "16" and moves[0]["why"] == "grow"
    # the client worked out the engine's free KV cache from its /metrics
    assert all(float(e["pool"]) > 100_000 for e in moves)
    assert not [e for e in events(campaign, "wide_c2_r1") if e["kind"] == "spec_govern"]


def test_the_large_batch_goes_out_in_chunks_of_at_most_32(campaign):
    ev = events(campaign, "auto_c2_r1")
    sizes = sorted({int(e["batch"]) for e in ev if e["kind"] == "spec_dispatch"})
    assert sizes == [4, 70]  # what the program wrote; the chunks are how it was sent
    by_task: dict = {}
    for e in ev:
        if e["kind"] == "replay_call" and e.get("path") == "batch":
            by_task.setdefault(e["task_id"], []).append(e)
    for calls in by_task.values():
        assert len(calls) == 90
    assert not any(e["kind"] in ("spec_claim_miss", "spec_evict") for e in ev)


def launched_before_first_answer(ev, task) -> int:
    n = 0
    for e in ev:
        if e.get("task_id") != task:
            continue
        if e["kind"] == "spec_ready":
            break
        n += e["kind"] == "spec_dispatch"
    return n


def test_past_a_test_every_batch_of_the_loop_is_launched_ahead(campaign, corpus):
    first = corpus.sessions[0]
    past, plain = events(campaign, "auto-past_c2_r1"), events(campaign, "auto_c2_r1")
    assert launched_before_first_answer(past, first) >= 20  # the five batches of four
    assert launched_before_first_answer(plain, first) == 4  # the scout stopped at the test
    went = [int(e["past"]) for e in past if e["kind"] == "spec_scout_exec" and e.get("past")]
    assert went == [20, 20]  # once per result, in each session
    units = {u["unit"]: u for u in campaign.summary["units"]}
    assert units["auto-past_c2_r1"]["scout_past"] == 40 and units["auto_c2_r1"]["scout_past"] == 0


def test_the_report_says_what_the_limits_did(campaign):
    units = {u["unit"]: u for u in campaign.summary["units"]}
    g = units["auto_c2_r1"]["govern"]
    assert g["calls"] == 180 and g["moves"] >= 1 and g["why"].get("grow", 0) >= 1
    assert g["window_max"] > 16 and g["calls_above_16"] > 0
    # a cut: a move down because the engine queued, preempted or was short of KV cache. A
    # busy machine can make the fake engine queue, so the count is checked, not assumed 0
    assert g["cuts"] == sum(g["why"].get(why, 0) for why in ("queue", "kv", "preempted"))
    assert g["pool_max"] > 100_000
    assert units["stream_c2_r1"]["govern"] is None and units["wide_c2_r1"]["govern"] is None
    md = replay_report.render(campaign.summary)
    assert "## Limits that followed the load" in md
    assert "| auto_c2_r1 |" in md.split("## Limits that followed the load")[1]


def test_a_design_of_checks_is_scored_and_shown(campaign):
    checks = {c["id"]: c for c in campaign.summary["checks"]}
    assert list(checks) == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert checks["T1"]["held"] is True and checks["T1"]["measured"] == "0"
    assert checks["T2"]["held"] is True
    assert checks["T3"]["held"] is True and 0 < checks["T3"]["value"] <= 1.5
    assert checks["T4"]["held"] is True
    assert checks["T5"]["held"] is None and checks["T5"]["measured"] == "-"
    assert checks["T6"]["held"] is True
    md = replay_report.render(campaign.summary)
    assert "## The predictions (cloud/PREREG_GOVERN.md, fixed before the run)" in md
    assert "not testable" in md
    begin = json.loads((campaign.out / "campaign.jsonl").read_text().splitlines()[0])
    assert len(begin["design"]["sha256"]) == 64  # hashed before the first unit


def test_a_check_that_fails_is_shown_as_failed():
    s = {"arms": [{"arm": "stream", "wall_s": 100.0, "stream_s": 60.0},
                  {"arm": "auto", "wall_s": 95.0, "stream_s": 70.0}],
         "all_turns": [{"session": "a", "iteration": 3, "after": {"stream": 10.0, "auto": 9.0}}],
         "sessions": [{"session": "a", "wall": {"stream": 50.0, "auto": 60.0},
                       "stream": {"stream": 30.0, "auto": 30.0}, "after": {}}],
         "units": [{"unit": "auto_c8_r1", "arm": "auto", "exact": True, "preemptions": 2.0,
                    "kv_peak": 0.99, "govern": {"window_max": 64.0, "window_min": 3.0}}]}
    design = {"checks": [
        {"id": "a", "claim": "", "ratio": ["auto", "stream", "wall_s"], "max": 0.9},
        {"id": "b", "claim": "", "ratio": ["auto", "stream", "stream_s"], "max": 1.05},
        {"id": "c", "claim": "", "ratio": ["auto", "stream", "wall_s"], "sessions": ["a"],
         "max": 1.0},
        {"id": "d", "claim": "", "turn": ["a", 3, "auto", "stream"], "max": 0.5},
        {"id": "e", "claim": "", "unit": ["auto", "preemptions"], "max": 0},
        {"id": "f", "claim": "", "govern": ["auto", "window_max"], "min": 129},
        {"id": "g", "claim": "", "govern": ["auto", "window_min"], "min": 16},
        {"id": "h", "claim": "", "ratio": ["auto", "stream", "wall_s"], "sessions": ["a", "b"],
         "max": 1.0},
        {"id": "i", "claim": "", "turn_s": ["a", 3, "auto"], "max": 9.5},
        {"id": "j", "claim": "", "unit_ratio": ["auto", "stream", "ttft_p99"], "max": 1.5},
        {"id": "k", "claim": "", "unit_ratio": ["auto", "nospec", "ttft_p99"], "max": 1.5},
        {"id": "l", "claim": "", "unit": ["*", "exact"], "max": 0},
        {"id": "m", "claim": "", "unit": ["*", "evicted"], "max": 0}]}
    s["units"].append({"unit": "stream_c8_r1", "arm": "stream", "exact": False, "ttft_p99": 0.5,
                       "evicted": 0})
    s["units"][0].update(ttft_p99=2.0, evicted=0)
    got = {c["id"]: c["held"] for c in replay_report.score_checks(s, design)}
    assert got == {"a": False, "b": False, "c": False, "d": False, "e": False, "f": False,
                   "g": False, "h": None, "i": True, "j": False, "k": None, "l": False,
                   "m": True}


def test_the_new_arms_are_what_the_plan_says():
    arms = replay.ARMS
    assert arms["auto"]["kwargs"] == {"spec_scout": True, "spec_rlm_query": True,
                                      "spec_batch_launch": True, "spec_batch_chunk": 32,
                                      "spec_govern": True}
    assert arms["auto-past"]["kwargs"] == {**arms["auto"]["kwargs"], "spec_scout": "past"}
    assert arms["wide-past"]["kwargs"] == {**arms["wide"]["kwargs"], "spec_scout": "past"}
    assert arms["wide-open"]["inflight_chars"] == 10**9
    assert arms["wide-open"]["kwargs"] == arms["wide"]["kwargs"]
    assert "govern" not in arms["wide"] and "govern" not in arms["stream"]


# ------------------------------------------------------------------ the fake engine's load
def ask(base_url, text, n, out, i):
    body = json.dumps({"model": "fake-model", "max_completion_tokens": n, "ignore_eos": True,
                       "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(base_url + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    urllib.request.urlopen(req, timeout=60).read()
    out[i] = time.perf_counter() - t0


def burst(eng, prompts, n=4):
    out = [None] * len(prompts)
    threads = [threading.Thread(target=ask, args=(eng.base_url, p, n, out, i))
               for i, p in enumerate(prompts)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return time.perf_counter() - t0, out


def metric(eng, name):
    text = urllib.request.urlopen(eng.base_url[:-3] + "/metrics", timeout=5).read().decode()
    return rlm_campaign.parse_metric(text, (name,))


def test_a_batch_costs_time_when_alpha_says_so():
    """The engine's own time per step, so that a busy machine does not blur it: the sum of
    the times between tokens over their count."""
    prompts = [f"q{i}" for i in range(40)]

    def step_ms(eng) -> float:
        burst(eng, prompts, n=6)
        c = eng.engine.counters
        return 1000.0 * c["itl_sum"] / c["itl_count"]

    with FakeEngineServer(step_ms=20.0, alpha=0.0) as free:
        t_free = step_ms(free)
    with FakeEngineServer(step_ms=20.0, alpha=0.05) as dear:  # 40 running: steps 3 times as long
        t_dear = step_ms(dear)
    assert t_dear > 2.0 * t_free


def test_requests_beyond_the_engines_places_wait():
    prompts = [f"q{i}" for i in range(24)]
    with FakeEngineServer(step_ms=10.0, max_seqs=8) as eng:
        wall, _ = burst(eng, prompts)
        assert eng.engine.counters["max_running"] == 8
        assert eng.engine.counters["max_waiting"] >= 8
    assert wall > 3 * 4 * 0.010 * 0.8  # three rounds of four tokens


def test_a_prompt_that_does_not_fit_the_kv_cache_waits_and_holds_up_the_queue():
    long = "x" * 3300  # about 1,000 tokens
    with FakeEngineServer(step_ms=10.0, kv_tokens=2500) as eng:
        wall, took = burst(eng, [long + str(i) for i in range(4)], n=20)
        c = eng.engine.counters
        assert c["max_running"] == 2 and c["max_waiting"] >= 2  # two fit, two wait
        assert c["kv_peak"] <= 1.0 and c["preemptions"] == 0
        assert metric(eng, "cache_config_info") == 1.0
    assert max(took) > 1.5 * min(took)


def test_a_full_kv_cache_preempts_the_request_admitted_last():
    """Two prompts fit when they are admitted. Their answers do not: the one admitted
    last is preempted, prefilled again, and still answers."""
    long = "y" * 3300
    with FakeEngineServer(step_ms=5.0, kv_tokens=2060) as eng:
        wall, took = burst(eng, [long + "a", long + "b"], n=60)
        c = eng.engine.counters
        assert c["preemptions"] >= 1
        assert metric(eng, "num_preemptions_total") == c["preemptions"]
        assert all(t is not None for t in took)
        assert c["gen_tokens"] >= 120


def test_the_engine_reports_the_time_between_tokens():
    with FakeEngineServer(step_ms=20.0) as eng:
        burst(eng, ["one", "two"], n=10)
        n = metric(eng, "inter_token_latency_seconds_count")
        s = metric(eng, "inter_token_latency_seconds_sum")
        assert n == 2 * 9 and 0.015 < s / n < 0.040


def test_long_context_prompts_can_be_counted_at_their_own_rate():
    """OOLONG's context text runs at 2.8 characters a token, the prompts around it at 3.3
    and more. The KV cache is what long prompts fill, so their size has to be right."""
    with FakeEngineServer(step_ms=2.0) as eng:
        eng.engine.long_chars_per_token = 2.8
        assert eng.engine.uncached_tokens("a" * 28_000)[0] == 10_000
        assert eng.engine.uncached_tokens("b" * 3_300)[0] == 1_000  # short: as before
    with FakeEngineServer(step_ms=2.0) as eng:  # unless told: every prompt at 3.3
        assert eng.engine.uncached_tokens("c" * 33_000)[0] == 10_000
