"""cloud/long_calls.py on made-up events: the window of the long calls, and who paid."""

from __future__ import annotations

import long_calls


def call(task, t0, s, pt, spec=1):
    return {"kind": "replay_call", "task_id": task, "t0": t0, "ms": 1000.0 * s, "pt": pt,
            "ct": 4096, "spec": spec, "err": False}


def root(task, t_start, gaps_ms):
    at, arr = 0.0, []
    for i, g in enumerate([0.0, *gaps_ms]):
        at += g
        arr.append([at, i + 1])
    return {"kind": "root_stream", "task_id": task, "t_start": t_start, "arrivals": arr}


def test_the_window_is_the_long_calls_and_the_other_sessions_roots_are_split_by_it():
    events = [
        call("long", 100.0, 50.0, 36000), call("long", 101.0, 60.0, 36000),  # together
        call("long", 100.5, 1.0, 900),  # a short one: not a long call
        call("other", 10.0, 2.0, 30000, spec=None),  # another session's, left out by --session
        # another session's root: ten gaps of 40 ms before the window, then, inside it,
        # eight of 40 ms and two stalls of 3 s
        root("other", 50.0, [40.0] * 10),
        root("other", 110.0, [40.0] * 4 + [3000.0] + [40.0] * 4 + [3000.0]),
        root("long", 120.0, [500.0] * 5),  # the long calls' own session does not count
    ]
    metrics = [{"t": str(t), "kv": str(kv), "running": "3", "waiting": str(w),
                "preemptions": str(p)}
               for t, kv, w, p in [(60, 0.2, 0, 0), (105, 0.9, 1, 0), (150, 0.97, 4, 2),
                                   (200, 0.3, 0, 2)]]
    r = long_calls.unit_report({"unit": "u", "events": events, "metrics": metrics}, 20000,
                               ["long"])
    assert len(r["long_calls"]) == 2 and all(c["speculative"] for c in r["long_calls"])
    w = r["window"]
    assert w["sent_within_s"] == 1.0 and w["in_flight_max"] == 2 and w["s"] == 61.0
    assert r["engine_in_window"]["kv_peak"] == 0.97 and r["engine_in_window"]["preemptions"] == 2
    assert r["engine_in_window"]["waiting_max"] == 4 and r["engine_unit"]["kv_peak"] == 0.97
    inside, outside = r["other_roots"]["inside"], r["other_roots"]["outside"]
    assert inside["gaps"] == 10 and inside["p50_ms"] == 40.0 and inside["max_ms"] == 3000.0
    assert abs(inside["stall_s"] - 2 * 2.96) < 1e-9  # two stalls, each 2.96 s over the usual gap
    assert outside["gaps"] == 10 and outside["stall_s"] == 0.0
    md = long_calls.render([r], 20000)
    assert "| u | 2 | 1.0 | 2 | 61 |" in md and "## u: the long calls" in md

    # without --session the other session's long call opens the window much earlier
    r2 = long_calls.unit_report({"unit": "u", "events": events, "metrics": metrics}, 20000)
    assert len(r2["long_calls"]) == 3 and r2["window"]["s"] == 151.0

    # a unit with no long call: one row for the whole unit, nothing inside
    r3 = long_calls.unit_report({"unit": "v", "events": events[4:5], "metrics": metrics}, 20000)
    assert r3["long_calls"] == [] and "window" not in r3
    assert r3["other_roots"]["inside"] is None and r3["other_roots"]["outside"]["gaps"] == 10
    assert "| v | 0 | - | - | - |" in long_calls.render([r3], 20000)
