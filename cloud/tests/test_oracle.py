"""cloud/oracle.py on synthetic sub-call records (no model, no server)."""

from __future__ import annotations

import oracle


def call(prompt: str, response: str, t: float) -> dict:
    return {"prompt": prompt, "response": response, "execution_time": t}


LONG = "Question: What is a tonne ? -> Label: description and abstract concept"


def test_a_batch_is_one_group_and_single_calls_are_their_own():
    calls = [call(f"label {i}", "entity", 0.02) for i in range(60)]  # one batch of 60
    calls += [call("summarize a", LONG + " A", 3.0), call("summarize b", LONG + " B", 4.0)]
    gs = oracle.groups_of(calls)
    assert [g["n"] for g in gs] == [60, 1, 1]
    assert abs(gs[0]["wall"] - 1.2) < 1e-9 and gs[1]["wall"] == 3.0
    assert gs[0]["needles"] == set()  # short labels leave no trace to look for
    assert len(gs[1]["needles"]) == 1


def test_independent_single_calls_collapse_to_the_slowest_one():
    # a model-written loop: ten unrelated 10 s calls, one after another
    calls = [call(f"classify batch {i}", f"{LONG} #{i}", 10.0 + i / 100) for i in range(10)]
    r = oracle.turn_oracle(calls, floor_s=0.02)
    assert r["groups"] == 10 and r["singles"] == 10 and r["edges"] == 0 and r["levels"] == 1
    assert abs(r["actual_s"] - 100.45) < 1e-6 and abs(r["oracle_s"] - 10.09) < 1e-6


def test_a_call_that_quotes_an_earlier_response_waits_for_it():
    a = call("triage the doc", "TRIAGE: the document is about quarterly revenue", 5.0)
    b = call("unrelated side question", "SIDE: an unrelated answer of some length", 2.0)
    c = call("summarize: TRIAGE: the document is about quarterly revenue", "ok " * 10, 3.0)
    r = oracle.turn_oracle([a, b, c], floor_s=0.02)
    assert r["edges"] == 1 and r["levels"] == 2
    assert r["actual_s"] == 10.0 and r["oracle_s"] == 8.0  # max(5, 2), then 3


def test_many_small_calls_cannot_beat_the_per_request_floor():
    # 40 batches of 20 calls, 0.4 s each: 16 s. All together: 800 calls x 20 ms = 16 s
    calls = []
    for b in range(40):
        calls += [call(f"q{b}-{i}", "entity", 0.02 + b * 1e-6) for i in range(20)]
    r = oracle.turn_oracle(calls, floor_s=0.02)
    assert r["groups"] == 40 and r["levels"] == 1
    assert abs(r["oracle_s"] - 16.0) < 0.05 and r["oracle_s"] <= r["actual_s"]
    # with a lower floor the same wave would be faster
    assert oracle.turn_oracle(calls, floor_s=0.005)["oracle_s"] < 5.0


def test_floor_is_the_fastest_large_batch():
    turns = [[call(f"a{i}", "x", 0.030) for i in range(100)],
             [call(f"b{i}", "x", 0.018) for i in range(60)],
             [call(f"c{i}", "x", 0.001) for i in range(10)]]  # too small to count
    assert oracle.floor_of(turns) == (0.018, 2)
    assert oracle.floor_of([[call("solo", "x", 1.0)]]) == (oracle.DEFAULT_FLOOR_S, 0)


def test_a_label_that_every_prompt_already_lists_is_not_a_dependency():
    label = "description and abstract concept"  # long enough to be searched for
    ask = f"Classify into one of: 'entity', '{label}'. Question: "
    calls = []
    for b in range(5):  # five batches of four, one after another, as a model's loop
        calls += [call(ask + f"q{b}-{i}", label, 0.3 + b * 1e-6) for i in range(4)]
    r = oracle.turn_oracle(calls, floor_s=0.02)
    assert r["groups"] == 5 and r["edges"] == 0 and r["levels"] == 1
    assert abs(r["oracle_s"] - 1.2) < 0.01  # one wave: the slowest batch (4 x 0.3 s)
