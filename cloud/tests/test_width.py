"""cloud/width.py on made-up events: a burst, a root that waited, the governor."""

from __future__ import annotations

import pytest

import width


def call(task, t0, s, pt=70, ct=3):
    return {"kind": "replay_call", "task_id": task, "t0": t0, "ms": 1000.0 * s, "pt": pt,
            "ct": ct, "spec": 1, "err": False}


def unit(events, metrics=()):
    return {"unit": "u", "events": [{"kind": "unit_begin", "t": 100.0}, *events],
            "metrics": [dict(m) for m in metrics]}


def test_a_burst_is_one_sessions_calls_sent_close_together():
    # session a: 300 calls of 1 s, 150 sent at once and 150 a second later; then one call
    # 10 s on, which is not part of the burst. Session b has 300 in flight at the same time.
    a = [call("a", 110.0, 1.0) for _ in range(150)] + [call("a", 111.0, 1.0) for _ in range(150)]
    b = [call("b", 110.0, 2.0) for _ in range(300)]
    metrics = [{"t": "110.5", "running": "40", "waiting": "0"},
               {"t": "111.5", "running": "60", "waiting": "2"},
               {"t": "120.0", "running": "300", "waiting": "9"}]  # after the burst
    u = unit([*a, call("a", 125.0, 1.0), *b], metrics)
    rows = width.bursts(u, min_calls=200)
    mine = next(r for r in rows if r["session"] == "a")
    assert mine["calls"] == 300 and mine["sent_at_s"] == pytest.approx(10.0)
    assert mine["lasted_s"] == pytest.approx(2.0)
    assert mine["calls_per_s"] == pytest.approx(150.0)
    assert mine["in_flight_max"] == 150 and mine["process_in_flight_max"] == 450
    # while it ran (2 s), 300 of its own calls and 300 of b's came back
    assert mine["process_calls_per_s"] == pytest.approx(300.0)
    assert mine["process_in_flight_mean"] == pytest.approx(450.0, rel=0.05)
    assert (mine["engine_running_p50"], mine["engine_running_max"]) == (50.0, 60.0)
    assert mine["engine_waiting_max"] == 2.0
    assert mine["to_100_s"] == pytest.approx(0.0, abs=0.06)
    assert [r["session"] for r in rows] == ["a", "b"] or [r["session"] for r in rows] == ["b", "a"]
    assert width.bursts(u, min_calls=301) == []


def root(task, turn, t_start, ttft):
    return {"kind": "root_stream", "task_id": task, "iteration": turn, "t_start": t_start,
            "ttft_s": ttft, "prompt_tokens": 1500}


def test_a_root_turn_that_waited_is_set_next_to_the_long_prompts_before_it():
    events = [
        call("long", 150.0, 180.0, pt=36000, ct=4096), call("long", 150.1, 180.0, pt=36000, ct=4096),
        root("r", 1, 150.3, 2.7),  # began 0.3 s after the first long prompt
        root("r", 2, 400.0, 0.14),  # a quick turn
        root("s", 1, 120.0, 0.9),  # waited, with no long prompt near it
    ]
    metrics = [{"t": "151.0", "running": "10", "waiting": "3"},  # 1 s after a long prompt
               {"t": "152.0", "running": "10", "waiting": "2"},
               {"t": "300.0", "running": "10", "waiting": "5"},  # a queue of its own
               {"t": "310.0", "running": "10", "waiting": "0"}]
    w = width.waited(unit(events, metrics))
    assert w["root_turns"] == 3 and [t["session"] for t in w["waited"]] == ["r", "s"]
    first, second = w["waited"]
    assert first["long_prompts_before"] == 2 and first["their_tokens"] == 72000
    assert first["first_sent_s_before"] == pytest.approx(0.3)
    assert first["began_at_s"] == pytest.approx(50.3)
    assert second["long_prompts_before"] == 0 and second["first_sent_s_before"] is None
    assert (w["samples"], w["samples_with_a_request_waiting"]) == (4, 3)
    assert w["of_them_after_a_long_prompt"] == 2


def gov(t, task, was, window, why, cpu="0.5", tax="0.05", waiting="0.0", running="20.0"):
    return {"kind": "spec_govern", "t": t, "task_id": task, "was": str(was),
            "window": str(window), "why": why, "cpu": cpu, "tax": tax, "waiting": waiting,
            "running": running}


def test_the_governors_cuts_and_ramps():
    steps = [(16, 24), (24, 36), (36, 54), (54, 81), (81, 121), (121, 181), (181, 256)]
    events = [gov(110.0 + 0.25 * i, "a", w0, w1, "grow", cpu="1.1" if i >= 4 else "0.5")
              for i, (w0, w1) in enumerate(steps)]
    events += [gov(120.0, "a", 256, 179, "queue", waiting="40.0", running="151.0", tax="0.19"),
               gov(125.0, "a", 179, 128, "share"),  # another session asked for its part
               gov(130.0, "a", 128, 16, "idle"), gov(140.0, "a", 16, 24, "grow")]
    g = width.governor(unit(events))
    assert g["moves"] == 11 and len(g["cuts"]) == 1
    assert [(s["was"], s["window"]) for s in g["shares"]] == [(179.0, 128.0)]
    cut = g["cuts"][0]
    assert (cut["was"], cut["window"], cut["why"], cut["waiting"]) == (256.0, 179.0, "queue", 40.0)
    assert cut["at_s"] == pytest.approx(20.0)
    ramp, late = g["ramps"]
    assert (ramp["from"], ramp["to"], ramp["steps"]) == (16.0, 256.0, 7)
    assert ramp["s"] == pytest.approx(1.5) and late["steps"] == 1
    assert g["cpu_max"] == 1.1 and g["tax_max"] == 0.19
    assert (g["grow_moves"], g["grow_moves_cpu_090"]) == (8, 3)
    assert width.governor(unit([call("a", 100.0, 1.0)])) is None


def test_the_tables_render(tmp_path):
    events = [call("a", 100.0 + 0.01 * i, 1.0) for i in range(250)]
    events += [root("r", 1, 100.2, 0.8), gov(100.5, "a", 16, 24, "grow")]
    u = unit(events, [{"t": "100.5", "running": "30", "waiting": "1"}])
    (tmp_path / "u").mkdir()
    import json
    (tmp_path / "u" / "events.jsonl").write_text("\n".join(json.dumps(e) for e in u["events"]))
    (tmp_path / "u" / "metrics.csv").write_text("t,running,waiting\n100.5,30,1\n")
    out = tmp_path / "width.md"
    width.main([str(tmp_path / "u"), "--out", str(out)])
    text = out.read_text()
    assert "## Bursts" in text and "| u | a | 250 |" in text
    assert "## The governor" in text
    saved = json.loads(out.with_suffix(".json").read_text())
    assert saved[0]["bursts"][0]["calls"] == 250
