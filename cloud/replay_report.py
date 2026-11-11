"""What a replay campaign measured (offline, stdlib only).

    python replay_report.py <run dir>

Reads the unit folders replay_campaign.py wrote and writes summary.md and summary.json.
In a replay every arm runs the same sessions turn for turn, so arms are compared per turn:
the same turn's time after its stream, in each arm.

- **after-stream seconds:** from the end of a turn's root stream until its code has run
  (the shadow's wait plus the real run). What speculation is there to remove.
- **cause** (analyze.turn_cause, on the `stream` arm's events): why spec-ptc as shipped
  still waited in that turn. `serial launches` and `burst over the cap` are the two the
  fork is built for.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import analyze

REF_ARMS = ("nospec", "stream")
ARM_ORDER = ("nospec", "stream", "stream-open", "scout", "wide", "auto", "auto-past",
             "wide-past", "wide-open", "wide-threads", "nospec-wide")
# the arms that run the patched client
FORK_ARMS = ("scout", "wide", "wide-threads", "auto", "auto-past", "wide-past", "wide-open")
GOVERNED_ARMS = ("auto", "auto-past")  # their limits follow the load
MIN_AFTER_S = 1.0  # a turn "waited" if spec-ptc as shipped spent this long after its stream


def _f(x, nd=1) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _pct(xs, q):
    return analyze._pct(xs, q)


def _arm_key(arm: str):
    return (ARM_ORDER.index(arm) if arm in ARM_ORDER else len(ARM_ORDER), arm)


# --------------------------------------------------------------------------- loading
def load(run: Path) -> list[dict]:
    units = []
    for udir in sorted((run / "units").glob("*_c*_r*")):
        if not (udir / "DONE").exists():
            continue
        meta = json.loads((udir / "unit.json").read_text())
        stats = json.loads((udir / "unit_stats.json").read_text())
        fid = json.loads((udir / "replay.json").read_text())
        events = [json.loads(x) for x in (udir / "events.jsonl").read_text().splitlines()
                  if x.strip()]
        rows = []
        mpath = udir / "metrics.csv"
        if mpath.exists():
            with open(mpath) as f:
                rows = list(csv.DictReader(f))
        units.append({**meta, "unit": udir.name, "tasks": stats.get("tasks", []),
                      "events": events, "fidelity": fid, "metrics": rows})
    return units


def unit_turns(u: dict) -> list[dict]:
    """One row per (session, turn) of a unit, with what happened in its time window."""
    by: dict = defaultdict(list)
    for e in u["events"]:
        if e.get("task_id") is not None:
            by[e["task_id"]].append(e)
    out = []
    for sid, ev in by.items():
        # `synthetic`: the step that ends a session its timeout stopped (replay.py)
        roots = sorted((e for e in ev if e["kind"] == "root_stream" and not e.get("synthetic")),
                       key=lambda e: e["iteration"])
        for i, r in enumerate(roots):
            after = (r.get("shadow_wait_s") or 0.0) + (r.get("exec_s") or 0.0)
            t0 = r["t_start"]
            t1 = t0 + (r.get("stream_s") or 0.0)
            # up to the next turn's start: events are stamped when logged
            t2 = roots[i + 1]["t_start"] if i + 1 < len(roots) else t1 + after + 0.5
            inturn = [e for e in ev if t0 <= e["t"] < t2]
            disp = sorted(e["t"] for e in inturn if e["kind"] == "spec_dispatch")
            calls = [e for e in inturn if e["kind"] == "replay_call"]
            sent = [c for c in calls if not c.get("err")]
            st = analyze.stalls(r)
            row = {
                "session": sid, "iteration": r["iteration"],
                "stream_s": r.get("stream_s") or 0.0, "after_s": after,
                "shadow_wait_s": r.get("shadow_wait_s") or 0.0, "exec_s": r.get("exec_s") or 0.0,
                "ttft_s": r.get("ttft_s"), "tokens": r.get("tokens") or 0,
                "prompt_match": r.get("prompt_match"),
                "gaps": st["gaps"], "stall_s": st["stall_s"],
                "dispatched": len(disp),
                "dispatched_in_stream": sum(1 for x in disp if x <= t1),
                "dispatch_span_s": (disp[-1] - disp[0]) if len(disp) > 1 else 0.0,
                "head_start_s": (t1 - disp[0]) if disp else None,
                "hits": sum(1 for e in inturn if e["kind"] == "spec_claim_hit"),
                "misses": sum(1 for e in inturn if e["kind"] == "spec_claim_miss"),
                "evicted": sum(1 for e in inturn if e["kind"] == "spec_evict"),
                "stops": [str(e.get("reason", ""))[:60] for e in inturn
                          if e["kind"] == "spec_shadow_stop"],
                "calls": len(sent), "call_errors": len(calls) - len(sent),
                "call_ms": [float(c["ms"]) for c in sent],
            }
            row["cause"] = analyze.turn_cause(row) if u["arm"] not in ("nospec", "nospec-wide") \
                else None
            out.append(row)
    return out


def engine(u: dict) -> dict:
    def col(k):
        return [float(r[k]) for r in u["metrics"] if r.get(k) not in (None, "")]

    running, waiting, kv, pre = col("running"), col("waiting"), col("kv"), col("preemptions")
    return {"running_mean": statistics.fmean(running) if running else None,
            "running_max": max(running) if running else None,
            "waiting_max": max(waiting) if waiting else None,
            "queue_share": (sum(1 for w in waiting if w > 0) / len(waiting)) if waiting else None,
            "kv_peak": max(kv) if kv else None,
            "preemptions": (pre[-1] - pre[0]) if len(pre) > 1 else None}


def _num(x):
    """A number the runner logged as text (spec-ptc's bus events are stringified)."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def govern(u: dict) -> dict | None:
    """What a governed unit's limits did (spec_ptc.engine.load): every move of a session's
    window is a `spec_govern` event with its reason and the signals it was made on.

    `at_call`: the window of its session when each sub-call was sent. A session starts at
    spec-ptc's 16."""
    moves = [e for e in u["events"] if e["kind"] == "spec_govern"]
    if not moves and u["arm"] not in GOVERNED_ARMS:
        return None
    by: dict = defaultdict(list)
    for e in moves:
        w = _num(e.get("window"))
        if w is not None:
            by[e.get("task_id")].append((e["t"], w))
    at_call = []
    for c in u["events"]:
        if c["kind"] != "replay_call" or c.get("err"):
            continue
        steps = by.get(c.get("task_id")) or []
        w = 16.0
        for t, win in steps:  # few moves per session: a scan is enough
            if t > c["t0"]:
                break
            w = win
        at_call.append(w)
    windows = [w for steps in by.values() for _, w in steps]
    pools = [v for v in (_num(e.get("pool")) for e in moves) if v is not None]
    cuts = [e for e in moves if e.get("why") in ("queue", "kv", "preempted")]
    return {"moves": len(moves), "why": dict(Counter(str(e.get("why")) for e in moves)),
            "sessions_moved": len(by),
            "window_max": max(windows, default=16.0), "window_min": min(windows, default=16.0),
            "at_call_p50": _pct(at_call, 0.5), "at_call_p90": _pct(at_call, 0.9),
            "at_call_mean": statistics.fmean(at_call) if at_call else None,
            "calls_above_16": sum(1 for w in at_call if w > 16),
            "calls_above_128": sum(1 for w in at_call if w > 128),
            "calls_below_16": sum(1 for w in at_call if w < 16), "calls": len(at_call),
            "share_above_16": (sum(1 for w in at_call if w > 16) / len(at_call)
                               if at_call else None),
            "share_above_128": (sum(1 for w in at_call if w > 128) / len(at_call)
                                if at_call else None),
            "share_below_16": (sum(1 for w in at_call if w < 16) / len(at_call)
                               if at_call else None),
            "cuts": len(cuts), "pool_min": min(pools, default=None),
            "pool_max": max(pools, default=None)}


# --------------------------------------------------------------------------- summary
def _geo_ci(logs: list[float], n_boot: int = 4000, seed: int = 0):
    if not logs:
        return None, None, None
    rng = random.Random(seed)
    boots = sorted(statistics.fmean(rng.choices(logs, k=len(logs))) for _ in range(n_boot))
    return (math.exp(statistics.fmean(logs)), math.exp(boots[int(0.025 * n_boot)]),
            math.exp(boots[int(0.975 * n_boot) - 1]))


def summarize(run: Path) -> dict:
    units = load(run)
    for u in units:
        u["turns"] = unit_turns(u)
        u["engine"] = engine(u)
        u["govern"] = govern(u)
        u["wall"] = {t["task_id"]: t.get("wall_s") for t in u["tasks"] if t.get("ok")}
    arms = sorted({u["arm"] for u in units}, key=_arm_key)
    by_arm = {a: [u for u in units if u["arm"] == a] for a in arms}

    # ---- units
    unit_rows = []
    for u in sorted(units, key=lambda u: u["t0"]):
        ts = u["turns"]
        gaps = [g for t in ts for g in t["gaps"]]
        spec = Counter(e["kind"][5:] for e in u["events"] if str(e["kind"]).startswith("spec_"))
        src = Counter(e.get("source") for e in u["events"] if e["kind"] == "spec_dispatch")
        batch = sum(1 for e in u["events"] if e["kind"] == "spec_dispatch" and e.get("batch"))
        fid = u["fidelity"]["sessions"]
        ms = [m for t in ts for m in t["call_ms"]]
        unit_rows.append({
            "unit": u["unit"], "arm": u["arm"], "rep": u["rep"], "t0": u["t0"],
            "unit_wall_s": u["t1"] - u["t0"], "sessions": len(u["tasks"]),
            "ok": sum(1 for t in u["tasks"] if t.get("ok")),
            "exact": bool(u["fidelity"].get("exact")),
            "wall_s": sum(v for v in u["wall"].values() if v),
            "stream_s": sum(t["stream_s"] for t in ts), "after_s": sum(t["after_s"] for t in ts),
            "turns": len(ts), "prompt_matches": sum(f["prompt_matches"] for f in fid),
            "prompts": sum(f["prompts"] for f in fid),
            "answer_matches": sum(1 for f in fid if f["answer_match"]),
            "unrecorded": sum(f["unrecorded"] for f in fid),
            "repeats": sum(f["repeats"] for f in fid),
            "released": sum(f["released"] for f in fid),
            "calls": sum(t["calls"] for t in ts), "call_errors": sum(t["call_errors"] for t in ts),
            "call_ms_p50": _pct(ms, 0.5), "call_ms_p90": _pct(ms, 0.9),
            "call_ms_max": max(ms, default=None),
            "gap_p50": _pct(gaps, 0.5), "gap_p99": _pct(gaps, 0.99),
            "gap_max": max(gaps, default=None),
            "stall_s": sum(t["stall_s"] for t in ts),
            "ttft_p50": _pct([t["ttft_s"] for t in ts], 0.5),
            "ttft_p90": _pct([t["ttft_s"] for t in ts], 0.9),
            "ttft_sum": sum(t["ttft_s"] for t in ts if t["ttft_s"] is not None),
            "ttft_p99": _pct([t["ttft_s"] for t in ts], 0.99),
            "ttft_max": max((t["ttft_s"] for t in ts if t["ttft_s"] is not None), default=None),
            "spec": dict(spec), "dispatch_source": dict(src), "batch_dispatches": batch,
            # a call that is not the recorded one, one nobody used, one not speculated
            "stray": sum(f["unrecorded"] + f["repeats"] for f in fid),
            "evicted": spec.get("evict", 0), "missed": spec.get("claim_miss", 0),
            "shadow_stops": Counter(s for t in ts for s in t["stops"]).most_common(5),
            "scout_skips": Counter(str(e.get("reason", ""))[:40] for e in u["events"]
                                   if e["kind"] == "spec_scout_skip").most_common(5),
            "scout_past": sum(int(_num(e.get("past")) or 0) for e in u["events"]
                              if e["kind"] in ("spec_scout_exec", "spec_scout_skip")),
            "govern": u["govern"],
            **u["engine"]})

    # ---- per (arm, session, turn): mean over the arm's repeats
    turn: dict = defaultdict(lambda: defaultdict(list))
    sess_wall: dict = defaultdict(lambda: defaultdict(list))
    for u in units:
        for t in u["turns"]:
            turn[(t["session"], t["iteration"])][u["arm"]].append(t)
        for sid, w in u["wall"].items():
            if w:
                sess_wall[sid][u["arm"]].append(w)
    sessions = sorted(sess_wall)

    def mean_after(key, arm):
        ts = turn[key].get(arm)
        return statistics.fmean(t["after_s"] for t in ts) if ts else None

    # ---- turns that waited in the stream arm, and their cause there
    waited = []
    for key in sorted(turn):
        st = turn[key].get("stream")
        if not st:
            continue
        after = statistics.fmean(t["after_s"] for t in st)
        if after < MIN_AFTER_S:
            continue
        causes = Counter(t["cause"] for t in st)
        any_arm = next(iter(turn[key].values()))[0]
        waited.append({"session": key[0], "iteration": key[1],
                       "cause": causes.most_common(1)[0][0], "causes": dict(causes),
                       "calls": max(t["calls"] for ts in turn[key].values() for t in ts),
                       "call_errors": any_arm["call_errors"],
                       "after": {a: mean_after(key, a) for a in arms}})
    recovery = []
    for cause in analyze.CAUSES:
        rows = [w for w in waited if w["cause"] == cause]
        if not rows:
            continue
        base = sum(w["after"]["stream"] for w in rows)
        rec = {"cause": cause, "turns": len(rows), "stream_s": base, "arms": {}}
        for a in arms:
            if all(w["after"].get(a) is not None for w in rows):
                s = sum(w["after"][a] for w in rows)
                rec["arms"][a] = {"after_s": s, "recovered_s": base - s,
                                  "recovered_share": (base - s) / base if base else None}
        recovery.append(rec)

    # ---- arms
    arm_rows = []
    for a in arms:
        us = by_arm[a]
        rows = [r for r in unit_rows if r["arm"] == a]
        row = {"arm": a, "units": len(us),
               **{k: statistics.fmean(r[k] for r in rows)
                  for k in ("wall_s", "stream_s", "after_s", "unit_wall_s")},
               "after_share": (statistics.fmean(r["after_s"] for r in rows)
                               / statistics.fmean(r["wall_s"] for r in rows)),
               "exact_units": sum(1 for r in rows if r["exact"])}
        for ref in REF_ARMS:
            if ref == a or ref not in by_arm:
                continue
            ref_rows = [r for r in unit_rows if r["arm"] == ref]
            row[f"wall_vs_{ref}"] = row["wall_s"] / statistics.fmean(r["wall_s"] for r in ref_rows)
            ref_after = statistics.fmean(r["after_s"] for r in ref_rows)
            row[f"after_vs_{ref}"] = row["after_s"] / ref_after if ref_after else None
            logs = [math.log(statistics.fmean(sess_wall[s][a]) / statistics.fmean(sess_wall[s][ref]))
                    for s in sessions if sess_wall[s].get(a) and sess_wall[s].get(ref)]
            g, lo, hi = _geo_ci(logs)
            row[f"session_ratio_vs_{ref}"] = {"geo": g, "ci": [lo, hi], "sessions": len(logs)}
        arm_rows.append(row)

    # ---- noise: one arm's two repeats
    noise = []
    for a in arms:
        reps = {u["rep"]: u for u in by_arm[a]}
        if len(reps) < 2:
            continue
        u1, u2 = reps[min(reps)], reps[max(reps)]
        logs = [math.log(u1["wall"][s] / u2["wall"][s]) for s in u1["wall"]
                if u1["wall"].get(s) and u2["wall"].get(s)]
        a1 = sum(t["after_s"] for t in u1["turns"])
        a2 = sum(t["after_s"] for t in u2["turns"])
        noise.append({"arm": a, "sessions": len(logs), "session_geo_sd": analyze._geo_sd(logs),
                      "wall_ratio": (sum(u1["wall"].values()) / sum(u2["wall"].values())
                                     if sum(u2["wall"].values()) else None),
                      "after_r1": a1, "after_r2": a2,
                      "stream_r1": sum(t["stream_s"] for t in u1["turns"]),
                      "stream_r2": sum(t["stream_s"] for t in u2["turns"])})

    def mean_stream(key, arm):
        ts = turn[key].get(arm)
        return statistics.fmean(t["stream_s"] for t in ts) if ts else None

    session_rows = [{"session": s,
                     "wall": {a: (statistics.fmean(sess_wall[s][a]) if sess_wall[s].get(a)
                                  else None) for a in arms},
                     "stream": {a: (sum(v for v in (mean_stream(k, a) for k in turn if k[0] == s)
                                        if v is not None) if any(turn[k].get(a) for k in turn
                                                                 if k[0] == s) else None)
                                for a in arms},
                     "after": {a: (sum(v for v in (mean_after(k, a) for k in turn if k[0] == s)
                                       if v is not None) if any(turn[k].get(a) for k in turn
                                                                if k[0] == s) else None)
                               for a in arms}}
                    for s in sessions]
    all_turns = [{"session": key[0], "iteration": key[1],
                  "calls": max(t["calls"] for ts in turn[key].values() for t in ts),
                  "after": {a: mean_after(key, a) for a in arms}} for key in sorted(turn)]
    summary = {"arms": arm_rows, "units": unit_rows, "sessions": session_rows,
               "waited": waited, "recovery": recovery, "noise": noise, "arm_names": arms,
               "all_turns": all_turns}
    design_file = run / "design.json"
    if design_file.exists():  # a design fixed before the run (replay_campaign --design-file)
        design = json.loads(design_file.read_text())
        summary["design"] = design
        if design.get("kind") == "checks":  # a design that is its checks and nothing else
            summary["checks"] = score_checks(summary, design)
        elif design.get("predictions", True):  # extra units carry none (replay_campaign.py)
            summary["first"] = first_number(summary, design)
            summary["prereg_fixed"] = prereg_fixed(summary, design)
    elif "nospec" in arms:  # the registered design
        summary["prereg"] = prereg(summary)
    else:  # the follow-up: the fork's wide arms against `stream`
        summary["addendum"] = prereg_addendum(summary)
    return summary


# --------------------------------------------------------------------------- predictions
LOOP_TURN = ("trec132k-17000222", 7)  # 319 single calls, each result used


def prereg(s: dict) -> list[dict]:
    """PREREG_REPLAY.md's predictions against this run. `held` is None where the run has
    nothing to test a prediction on (an arm that did not run, a cause with no turn)."""
    arms = {r["arm"]: r for r in s["arms"]}
    rec = {r["cause"]: r for r in s["recovery"]}
    out: list[dict] = []

    def add(pid: str, claim: str, measured: str, held) -> None:
        out.append({"id": pid, "claim": claim, "measured": measured, "held": held})

    def share(cause: str, arm: str):
        r = rec.get(cause)
        return None if r is None or arm not in r["arms"] else r["arms"][arm]["recovered_share"]

    def ratio(arm: str, ref: str, key: str):
        if arm not in arms or ref not in arms or not arms[ref][key]:
            return None
        return arms[arm][key] / arms[ref][key]

    def pct(x):
        return "-" if x is None else f"{100 * x:.0f}%"

    def r3(x):
        return "-" if x is None else f"{x:.3f}"

    units = s["units"]
    bad = [u["unit"] for u in units if not u["exact"]]
    stray = sum(u["unrecorded"] + u["repeats"] for u in units)
    add("P1", "every unit exact; no unrecorded call, no repeat",
        f"{len(units) - len(bad)} of {len(units)} exact; {stray} stray calls"
        + (f" ({', '.join(bad)})" if bad else ""), not bad and stray == 0)
    evicted = sum(u["spec"].get("evict", 0) for u in units)
    add("P2", "nothing evicted", f"{evicted} evicted", evicted == 0)

    turn = next((w for w in s["waited"] if (w["session"], w["iteration"]) == LOOP_TURN), None)
    a = turn["after"] if turn else {}
    v = a["stream"] / a["nospec"] if a.get("stream") and a.get("nospec") else None
    add("P3", "the loop of 319 single calls: `stream` at least 0.90 of `nospec`", r3(v),
        None if v is None else v >= 0.90)
    v = a["scout"] / a["stream"] if a.get("scout") is not None and a.get("stream") else None
    add("P4", "the same turn: `scout` at most 0.15 of `stream`", r3(v),
        None if v is None else v <= 0.15)

    sc, wd = share("serial launches", "scout"), share("serial launches", "wide")
    add("P5", "serial launches: `scout` recovers at least 75%, `wide` at least 85%",
        f"{pct(sc)}, {pct(wd)}",
        None if sc is None or wd is None else sc >= 0.75 and wd >= 0.85)
    sc, wd = share("burst over the cap", "scout"), share("burst over the cap", "wide")
    add("P6", "the cap: `scout` recovers between -15% and +15%, `wide` at least 50%",
        f"{pct(sc)}, {pct(wd)}",
        None if sc is None or wd is None else abs(sc) <= 0.15 and wd >= 0.50)

    a1, a2, a3 = (ratio("stream", "nospec", "wall_s"), ratio("scout", "stream", "wall_s"),
                  ratio("wide", "stream", "wall_s"))
    add("P7", "session time: `stream` 0.93–1.02 of `nospec`; `scout` at most 0.80 of `stream`; "
        "`wide` at most 0.75", f"{r3(a1)}, {r3(a2)}, {r3(a3)}",
        None if None in (a1, a2, a3) else 0.93 <= a1 <= 1.02 and a2 <= 0.80 and a3 <= 0.75)
    b1, b2 = ratio("scout", "stream", "stream_s"), ratio("wide", "stream", "stream_s")
    add("P8", "root stream seconds: `scout` within 5% of `stream`, `wide` within 10%",
        f"{r3(b1)}, {r3(b2)}",
        None if None in (b1, b2) else abs(b1 - 1) <= 0.05 and abs(b2 - 1) <= 0.10)
    worst = max((abs(n["wall_ratio"] - 1) for n in s["noise"] if n["wall_ratio"]), default=None)
    add("P9", "an arm's two units differ by less than 5% in session time",
        "-" if worst is None else f"largest difference {100 * worst:.1f}% "
        f"({len(s['noise'])} arms with two units)", None if worst is None else worst < 0.05)
    c1 = ratio("wide-threads", "wide", "wall_s")
    c2 = share("serial launches", "nospec-wide")
    c3 = ratio("nospec-wide", "nospec", "wall_s")
    add("P10", "controls: `wide-threads` within 25% of `wide`; `nospec-wide` recovers at most "
        "10% of the serial-launch seconds and is at least 0.90 of `nospec`",
        f"{r3(c1)}, {pct(c2)}, {r3(c3)}",
        None if None in (c1, c2, c3) else abs(c1 - 1) <= 0.25 and c2 <= 0.10 and c3 >= 0.90)

    fork = [x for x in ("scout", "wide") if x in arms and "stream" in arms]
    if fork:
        best = min(fork, key=lambda x: arms[x]["wall_s"])
        w, st = ratio(best, "stream", "wall_s"), ratio(best, "stream", "stream_s")
        add("live run", "worth it if the better fork arm is at most 0.85 of `stream` in "
            "session time and its root streams at most 10% longer",
            f"`{best}`: {r3(w)}, root streams {r3(st)}", w <= 0.85 and st <= 1.10)
    return out


BURST_TURN = ("trec132k-17000241", 12)  # one batch of 3,182 prompts


def prereg_addendum(s: dict) -> list[dict]:
    """PREREG_REPLAY_ADDENDUM.md's predictions: the follow-up run of the fork with the
    scout-to-shadow handoff fixed (`wide`, `wide-threads`, and `stream` as the reference)."""
    arms = {r["arm"]: r for r in s["arms"]}
    rec = {r["cause"]: r for r in s["recovery"]}
    out: list[dict] = []

    def add(pid, claim, measured, held):
        out.append({"id": pid, "claim": claim, "measured": measured, "held": held})

    def share(cause, arm):
        r = rec.get(cause)
        return None if r is None or arm not in r["arms"] else r["arms"][arm]["recovered_share"]

    def ratio(arm, ref, key):
        if arm not in arms or ref not in arms or not arms[ref][key]:
            return None
        return arms[arm][key] / arms[ref][key]

    def pct(x):
        return "-" if x is None else f"{100 * x:.0f}%"

    def r3(x):
        return "-" if x is None else f"{x:.3f}"

    units = s["units"]
    bad = [u["unit"] for u in units if not u["exact"]]
    stray = sum(u["unrecorded"] + u["repeats"] for u in units)
    evicted = sum(u["spec"].get("evict", 0) for u in units)
    missed = sum(u["spec"].get("claim_miss", 0) for u in units if u["arm"] != "stream")
    add("A1", "every unit exact; no call launched twice, none evicted, none left to the real run "
        "in the fork's arms",
        f"{len(units) - len(bad)} of {len(units)} exact; {stray} stray, {evicted} evicted, "
        f"{missed} not speculated", not bad and stray == 0 and evicted == 0 and missed == 0)
    turn = next((w for w in s["waited"] if (w["session"], w["iteration"]) == BURST_TURN), None)
    a = turn["after"] if turn else {}
    v = a["wide"] / a["stream"] if a.get("wide") is not None and a.get("stream") else None
    add("A2", "the batch of 3,182: `wide` at most 0.45 of `stream`", r3(v),
        None if v is None else v <= 0.45)
    v = share("burst over the cap", "wide")
    add("A3", "the cap: `wide` recovers at least 50%", pct(v), None if v is None else v >= 0.50)
    v = share("serial launches", "wide")
    add("A4", "serial launches: `wide` recovers at least 85%", pct(v),
        None if v is None else v >= 0.85)
    w, st = ratio("wide", "stream", "wall_s"), ratio("wide", "stream", "stream_s")
    add("A5", "session time: `wide` at most 0.75 of `stream`; root stream seconds within 10%",
        f"{r3(w)}, {r3(st)}", None if None in (w, st) else w <= 0.75 and abs(st - 1) <= 0.10)
    c = ratio("wide-threads", "wide", "wall_s")
    add("A6", "`wide-threads` within 25% of `wide` in session time", r3(c),
        None if c is None else abs(c - 1) <= 0.25)
    worst = max((abs(n["wall_ratio"] - 1) for n in s["noise"] if n["wall_ratio"]), default=None)
    add("A7", "`wide`'s two units differ by less than 5% in session time",
        "-" if worst is None else f"{100 * worst:.1f}%", None if worst is None else worst < 0.05)
    cut = sum(n for u in units if u["arm"] != "stream"
              for why, n in u["shadow_stops"] if str(why).startswith("ShadowAborted"))
    add("A8", "the runaway guard cuts no shadow statement in the fork's arms",
        f"{cut} cut", cut == 0)
    return out


# --------------------------------------------------------------------------- a design file
def first_number(s: dict, design: dict) -> dict | None:
    """PREREG_RECORD.md's number: `scout` over `stream` in summed session time, over every
    replayable session. A session the design left out or dropped is not recovered by
    definition: its recorded wall time is added to both sums."""
    arms = {r["arm"]: r for r in s["arms"]}
    if "scout" not in arms or "stream" not in arms:
        return None
    extra = {**(design.get("left_out") or {}), **(design.get("dropped") or {})}
    added = sum(float(v) for v in extra.values())
    w_scout, w_stream = arms["scout"]["wall_s"], arms["stream"]["wall_s"]
    saved = {r["session"]: r["wall"]["stream"] - r["wall"]["scout"] for r in s["sessions"]
             if r["wall"].get("stream") is not None and r["wall"].get("scout") is not None}
    total = sum(saved.values())
    carriers = sorted((k for k, v in saved.items() if total > 0 and v >= 0.1 * total),
                      key=lambda k: -saved[k])
    out = {"all": (w_scout + added) / (w_stream + added), "replayed": w_scout / w_stream,
           "sessions_replayed": len(saved), "sessions_added": len(extra), "added_s": added,
           "saved_s": total, "carriers": carriers}
    if "wide" in arms:
        out["wide_all"] = (arms["wide"]["wall_s"] + added) / (w_stream + added)
        out["wide_replayed"] = arms["wide"]["wall_s"] / w_stream
    return out


def prereg_fixed(s: dict, design: dict) -> list[dict]:
    """PREREG_RECORD.md's predictions for the replay (M1 to M7) and the numbers its addendum
    adds (`checks` in the design file), against this run. `held` is None where the run has
    nothing to test a prediction on."""
    after = {(t["session"], t["iteration"]): t["after"] for t in s["all_turns"]}
    out: list[dict] = []

    def add(pid, claim, measured, held):
        out.append({"id": pid, "claim": claim, "measured": measured, "held": held})

    def r3(x):
        return "-" if x is None else f"{x:.3f}"

    def turn_ratio(loop: dict, arm: str, ref: str):
        a = after.get((loop["session"], int(loop["turn"])), {})
        return a[arm] / a[ref] if a.get(arm) is not None and a.get(ref) else None

    def each(loops: list[dict], arm: str, ref: str, ok) -> tuple[str, bool | None]:
        vals = [turn_ratio(lp, arm, ref) for lp in loops]
        vals = [v for v in vals if v is not None]
        if not vals:
            return "-", None
        return ", ".join(r3(v) for v in vals), all(ok(v) for v in vals)

    units = s["units"]
    bad = [u["unit"] for u in units if not u["exact"]]
    add("M1", "every unit exact", f"{len(units) - len(bad)} of {len(units)} exact"
        + (f" ({', '.join(bad)})" if bad else ""), not bad)
    fork = [u for u in units if u["arm"] in FORK_ARMS]
    twice = sum(u["unrecorded"] + u["repeats"] for u in fork)
    evicted = sum(u["spec"].get("evict", 0) for u in fork)
    add("M2", "in the fork's arms no call is sent twice and none is evicted",
        f"{twice} sent twice or unrecorded, {evicted} evicted",
        None if not fork else twice == 0 and evicted == 0)

    singles = design.get("single_loops") or []
    m, h = each(singles, "stream", "nospec", lambda v: v >= 0.90)
    add("M3", "a loop of single calls stays serial as shipped: `stream` at least 0.90 of "
        "`nospec` on each such turn", m, h)
    m, h = each([lp for lp in singles if lp.get("kind") == "stores"], "scout", "stream",
                lambda v: v <= 0.25)
    add("M4", "where the loop only stores or prints each result, `scout` at most 0.25 of "
        "`stream` on that turn", m, h)
    m, h = each([lp for lp in singles if lp.get("kind") == "tests"], "scout", "stream",
                lambda v: v >= 0.85)
    add("M5", "where the loop tests each result, `scout` at least 0.85 of `stream` on that "
        "turn", m, h)

    def pooled(loops: list[dict], arm: str):
        rows = [after.get((lp["session"], int(lp["turn"])), {}) for lp in loops]
        rows = [a for a in rows if a.get(arm) is not None and a.get("stream")]
        if not rows:
            return None
        return sum(a[arm] for a in rows) / sum(a["stream"] for a in rows)

    batches = design.get("batch_loops") or []
    sc, wd = pooled(batches, "scout"), pooled(batches, "wide")
    add("M6", "loops of batches: `scout` at 0.55 to 0.95 of `stream` over those turns, `wide` "
        "at most 0.45", f"{r3(sc)}, {r3(wd)}",
        None if sc is None or wd is None else 0.55 <= sc <= 0.95 and wd <= 0.45)
    first = s.get("first")
    add("M7", "the number reported first (`scout` over `stream`, all replayable sessions) is "
        "at least 0.78",
        "-" if not first else f"{r3(first['all'])} ({r3(first['replayed'])} over the "
        f"{first['sessions_replayed']} replayed sessions alone)",
        None if not first else first["all"] >= 0.78)

    for c in design.get("checks") or []:  # the addendum's numbers
        v = check_value(s, c)
        held = None if v is None else (c.get("min", float("-inf")) <= v <= c.get("max", float("inf")))
        add(c["id"], c["claim"], r3(v), held)
    return out


def check_value(s: dict, c: dict):
    """The number one check of a design file is about, or None if this run does not have it.

    - `ratio: [arm, ref, key]`: the two arms' sums of `key` (wall_s, stream_s, after_s). With
      `sessions`, over those sessions only.
    - `turn: [session, turn, arm, ref]`: that turn's seconds after its stream, arm over ref.
    - `turn_s: [session, turn, arm]`: the same seconds in one arm.
    - `unit: [arm, stat]`: a number of the arm's units (the units table), the largest of them.
      `exact` counts the units that are not exact. The arm `*` is every unit of the run.
    - `unit_ratio: [arm, ref, stat]`: that number of the arm over the same number of `ref`.
    - `govern: [arm, stat]`: a number of what the arm's limits did (govern()); the largest
      over its units, the smallest for `window_min` and `pool_min`.
    - `first`: a key of the number PREREG_RECORD.md reports first."""
    arms = {r["arm"]: r for r in s["arms"]}
    after = {(t["session"], t["iteration"]): t["after"] for t in s["all_turns"]}
    if c.get("first"):
        return (s.get("first") or {}).get(c["first"])
    if c.get("ratio"):
        arm, ref, key = c["ratio"]
        if c.get("sessions"):
            col = {"wall_s": "wall", "stream_s": "stream", "after_s": "after"}[key]
            rows = [r for r in s["sessions"] if r["session"] in c["sessions"]]
            if (len(rows) != len(c["sessions"])
                    or any(r[col].get(arm) is None or r[col].get(ref) is None for r in rows)):
                return None
            den = sum(r[col][ref] for r in rows)
            return sum(r[col][arm] for r in rows) / den if den else None
        if arm in arms and ref in arms and arms[ref].get(key):
            return arms[arm][key] / arms[ref][key]
        return None
    if c.get("turn"):
        session, it, arm, ref = c["turn"]
        a = after.get((session, int(it)), {})
        return a[arm] / a[ref] if a.get(arm) is not None and a.get(ref) else None
    if c.get("turn_s"):
        session, it, arm = c["turn_s"]
        return after.get((session, int(it)), {}).get(arm)
    def unit_stat(arm: str, stat: str):
        rows = [u for u in s["units"] if arm in ("*", u["arm"])]
        if stat == "exact":
            return float(sum(1 for u in rows if not u["exact"])) if rows else None
        vals = [u.get(stat) for u in rows if u.get(stat) is not None]
        return max(vals) if vals else None

    if c.get("unit"):
        return unit_stat(*c["unit"])
    if c.get("unit_ratio"):
        arm, ref, stat = c["unit_ratio"]
        a, b = unit_stat(arm, stat), unit_stat(ref, stat)
        return a / b if a is not None and b else None
    if c.get("govern"):
        arm, stat = c["govern"]
        vals = [u["govern"].get(stat) for u in s["units"] if u["arm"] == arm and u.get("govern")]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return min(vals) if stat in ("window_min", "pool_min") else max(vals)
    return None


def score_checks(s: dict, design: dict) -> list[dict]:
    """A design's `checks` against this run: each a claim, a number and its bounds. `held`
    is None where the run has nothing to test the check on."""
    out = []
    for c in design.get("checks") or []:
        v = check_value(s, c)
        held = None if v is None else (c.get("min", float("-inf")) <= v
                                       <= c.get("max", float("inf")))
        nd = c.get("digits", 3)
        out.append({"id": c["id"], "claim": c["claim"],
                    "measured": "-" if v is None else f"{v:.{nd}f}", "held": held,
                    "value": v})
    return out


def readme_rule(first: dict | None) -> str | None:
    """PREREG_RECORD.md, "What the result changes in the README"."""
    if not first:
        return None
    x, n = first["all"], len(first["carriers"])
    if x <= 0.80 and n >= 2:
        return (f"at most 0.80 ({x:.3f}), with {n} sessions each giving a tenth of the saving "
                "or more: the gain holds on unprovoked code")
    if x <= 0.80:
        return (f"at most 0.80 ({x:.3f}), with {n} session giving a tenth of the saving or "
                "more: the README gives the number and says that one session carries it")
    if x <= 0.95:
        return (f"between 0.80 and 0.95 ({x:.3f}): the README says what the scout gives on "
                "unprovoked code, and that the registered 0.72 was mostly the bug's")
    return (f"above 0.95 ({x:.3f}): on unprovoked code the scout as built gains little at the "
            "shipped window")


# --------------------------------------------------------------------------- rendering
def render(s: dict) -> str:
    arms = s["arm_names"]
    out = ["# Replay campaign summary (measured)", "",
           "Every arm replays the same recorded sessions: same code, same sub-calls, same "
           "answers. Times are seconds on this run's engine. An arm's numbers are the mean of "
           "its units.", "",
           "## Arms", "",
           "Session time: the sum of the sessions' wall times. After-stream: from the end of "
           "each root stream until that turn's code has run. Ratios below 1 are faster. The "
           "per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.", "",
           "| arm | units (exact) | session time s | root streams s | after-stream s "
           "| after-stream share | session time vs nospec | vs stream "
           "| per session vs nospec [CI] | per session vs stream [CI] |",
           "|" + "---|" * 10]

    def ratio(r, k):
        v = r.get(k)
        if not v or v["geo"] is None:
            return "-"
        return f"{v['geo']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]"

    for r in s["arms"]:
        out.append(
            f"| {r['arm']} | {r['units']} ({r['exact_units']}) | {_f(r['wall_s'])} "
            f"| {_f(r['stream_s'])} | {_f(r['after_s'])} | {_f(r['after_share'], 3)} "
            f"| {_f(r.get('wall_vs_nospec'), 3)} | {_f(r.get('wall_vs_stream'), 3)} "
            f"| {ratio(r, 'session_ratio_vs_nospec')} | {ratio(r, 'session_ratio_vs_stream')} |")

    mark = {True: "held", False: "**did not hold**", None: "not testable"}
    if s.get("prereg"):
        out += ["", "## The predictions (cloud/PREREG_REPLAY.md, fixed before the run)", "",
                "| | prediction | measured | |", "|---|---|---|---|"]
        out += [f"| {p['id']} | {p['claim']} | {p['measured']} | {mark[p['held']]} |"
                for p in s["prereg"]]
    if s.get("addendum"):
        out += ["", "## The predictions (cloud/PREREG_REPLAY_ADDENDUM.md, fixed before the "
                "follow-up run)", "", "| | prediction | measured | |", "|---|---|---|---|"]
        out += [f"| {p['id']} | {p['claim']} | {p['measured']} | {mark[p['held']]} |"
                for p in s["addendum"]]
    if s.get("prereg_fixed"):
        f, d = s.get("first"), s.get("design") or {}
        out += ["", "## The number reported first (cloud/PREREG_RECORD.md)", ""]
        if f:
            extra = {**(d.get("left_out") or {}), **(d.get("dropped") or {})}
            out += [f"- **`scout` over `stream`, summed session time, every replayable session: "
                    f"{f['all']:.3f}.** Over the {f['sessions_replayed']} replayed sessions "
                    f"alone: {f['replayed']:.3f}.",
                    f"- {f['sessions_added']} session(s) left out or dropped count as not "
                    f"recovered: {f['added_s']:.0f} s added to both sums"
                    + (f" ({', '.join(sorted(extra))})." if extra else "."),
                    f"- The scout saves {f['saved_s']:.0f} s over the replayed sessions. "
                    f"Sessions giving a tenth of that or more: "
                    f"{', '.join(f['carriers']) or 'none'}."]
            if "wide_all" in f:
                out.append(f"- `wide` over `stream`: {f['wide_all']:.3f} "
                           f"({f['wide_replayed']:.3f} over the replayed sessions alone).")
            out.append(f"- By the rule fixed beforehand: {readme_rule(f)}.")
        out += ["", "## The predictions (cloud/PREREG_RECORD.md and its addendum, fixed before "
                "the replay)", "", "| | prediction | measured | |", "|---|---|---|---|"]
        out += [f"| {p['id']} | {p['claim']} | {p['measured']} | {mark[p['held']]} |"
                for p in s["prereg_fixed"]]
    if s.get("checks"):
        d = s.get("design") or {}
        files = " and ".join(f"cloud/{f}" for f in d.get("prereg") or []) or "the design file"
        out += ["", f"## The predictions ({files}, fixed before the run)", "",
                "| | prediction | measured | |", "|---|---|---|---|"]
        out += [f"| {p['id']} | {p['claim']} | {p['measured']} | {mark[p['held']]} |"
                for p in s["checks"]]
    governed = [r for r in s["units"] if r.get("govern")]
    if governed:
        out += ["", "## Limits that followed the load", "",
                "A governed session's window starts at spec-ptc's 16 and moves with what the "
                "engine and the client report. Window at a call: the window of its session "
                "when the sub-call was sent. Cuts: moves down because the engine queued, "
                "preempted or was short of KV cache. KV pool: the tokens of KV cache the "
                "engine had free for speculative calls, as the client worked it out.", "",
                "| unit | moves (by reason) | window at a call, median / 90th / mean "
                "| calls sent above 16 / above 128 / below 16 | widest / narrowest window "
                "| cuts | KV pool, smallest / largest (tokens) |", "|" + "---|" * 7]
        for r in governed:
            g = r["govern"]
            why = ", ".join(f"{n} {k}" for k, n in sorted(g["why"].items(),
                                                         key=lambda kv: -kv[1])) or "-"
            out.append(
                f"| {r['unit']} | {g['moves']} ({why}) | {_f(g['at_call_p50'], 0)} / "
                f"{_f(g['at_call_p90'], 0)} / {_f(g['at_call_mean'], 0)} "
                f"| {g['calls_above_16']} / {g['calls_above_128']} / {g['calls_below_16']} "
                f"of {g['calls']} | {_f(g['window_max'], 0)} / {_f(g['window_min'], 0)} "
                f"| {g['cuts']} | {_f(g['pool_min'], 0)} / {_f(g['pool_max'], 0)} |")
    if s["recovery"]:
        out += ["", "## What each arm leaves of the time spec-ptc as shipped still waited", "",
                f"Turns in which the `stream` arm spent at least {MIN_AFTER_S:g} s after the "
                "stream, grouped by why (its own events). Seconds after the stream in the same "
                "turns, per arm, and the share of the `stream` arm's seconds that is gone.", "",
                "| cause in `stream` | turns | " + " | ".join(f"{a} s" for a in arms) + " | "
                + " | ".join(f"{a} recovers" for a in arms if a != "stream") + " |",
                "|" + "---|" * (2 + len(arms) + len([a for a in arms if a != "stream"]))]
        for r in s["recovery"]:
            cells = [(_f(r["arms"][a]["after_s"]) if a in r["arms"] else "-") for a in arms]
            rec = [(f"{100 * r['arms'][a]['recovered_share']:.0f}%" if a in r["arms"]
                    and r["arms"][a]["recovered_share"] is not None else "-")
                   for a in arms if a != "stream"]
            out.append(f"| {r['cause']} | {r['turns']} | " + " | ".join(cells) + " | "
                       + " | ".join(rec) + " |")
        out += ["", "The turns:", "",
                "| session | turn | sub-calls sent (errors returned) | cause in `stream` | "
                + " | ".join(f"{a} s" for a in arms) + " |", "|" + "---|" * (4 + len(arms))]
        for w in sorted(s["waited"], key=lambda w: -w["after"]["stream"]):
            out.append(f"| {w['session']} | {w['iteration']} | {w['calls']} ({w['call_errors']}) "
                       f"| {w['cause']} | "
                       + " | ".join(_f(w["after"].get(a)) for a in arms) + " |")

    out += ["", "## Sessions", "", "Wall time of each session, seconds (after-stream seconds).",
            "", "| session | " + " | ".join(arms) + " |", "|" + "---|" * (1 + len(arms))]
    for r in s["sessions"]:
        out.append(f"| {r['session']} | " + " | ".join(
            f"{_f(r['wall'].get(a))} ({_f(r['after'].get(a))})" for a in arms) + " |")

    out += ["", "## Units, in the order they ran", "",
            "| unit | wall s | sessions ok | exact | session time s | root streams s "
            "| after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s "
            "| sub-calls sent (errors returned) | call p50 / p90 / max ms "
            "| running mean / max | waiting max (share of samples with a request waiting) "
            "| KV peak | preempt |", "|" + "---|" * 16]
    for r in s["units"]:
        out.append(
            f"| {r['unit']} | {_f(r['unit_wall_s'], 0)} | {r['ok']} / {r['sessions']} "
            f"| {'yes' if r['exact'] else 'NO'} | {_f(r['wall_s'])} | {_f(r['stream_s'])} "
            f"| {_f(r['after_s'])} | {_f(r['gap_p50'])} / {_f(r['gap_p99'])} / {_f(r['gap_max'], 0)} "
            f"| {_f(r['stall_s'])} | {_f(r['ttft_p50'], 2)} / {_f(r['ttft_p99'], 2)} / "
            f"{_f(r['ttft_max'], 2)} | {r['calls']} ({r['call_errors']}) "
            f"| {_f(r['call_ms_p50'], 0)} / {_f(r['call_ms_p90'], 0)} / {_f(r['call_ms_max'], 0)} "
            f"| {_f(r['running_mean'])} / {_f(r['running_max'], 0)} | {_f(r['waiting_max'], 0)} "
            f"({_f(r.get('queue_share'), 2)}) "
            f"| {_f(r['kv_peak'], 2)} | {_f(r['preemptions'], 0)} |")

    out += ["", "## What speculation did", "",
            "| unit | launched (by the scout or a peek / by the shadow) | of them in a batch "
            "launch | adopted | claimed | not speculated | evicted | shadow stops "
            "| scout statements cut short |", "|" + "---|" * 9]
    for r in s["units"]:
        if r["arm"] in ("nospec", "nospec-wide"):
            continue
        sp, src = r["spec"], r["dispatch_source"]
        stops = "; ".join(f"{n}x {why}" for why, n in r["shadow_stops"]) or "-"
        skips = "; ".join(f"{n}x {why}" for why, n in r["scout_skips"]) or "-"
        out.append(f"| {r['unit']} | {sp.get('dispatch', 0)} ({src.get('peek', 0)} / "
                   f"{src.get('shadow', 0)}) | {r['batch_dispatches']} | {sp.get('adopt', 0)} "
                   f"| {sp.get('claim_hit', 0)} | {sp.get('claim_miss', 0)} "
                   f"| {sp.get('evict', 0)} | {stops} | {skips} |")

    out += ["", "## Fidelity", "",
            "A unit is exact if every session finished, ran the recorded number of turns, "
            "sent the root the recorded message history in every turn (sha256), and ended "
            "with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run "
            "never sent. Repeats: sub-calls beyond the number recorded for their prompt.", "",
            "| unit | exact | turns with the recorded history | sessions with the recorded "
            "answer | unrecorded calls | repeats | answers given back by evictions |",
            "|" + "---|" * 7]
    for r in s["units"]:
        out.append(f"| {r['unit']} | {'yes' if r['exact'] else 'NO'} | {r['prompt_matches']} / "
                   f"{r['prompts']} | {r['answer_matches']} / {r['sessions']} "
                   f"| {r['unrecorded']} | {r['repeats']} | {r['released']} |")

    if s["noise"]:
        out += ["", "## Noise: one arm's two units", "",
                "| arm | session time, unit 1 / unit 2 | per-session spread (factor) "
                "| after-stream s, unit 1 / unit 2 | root streams s, unit 1 / unit 2 |",
                "|" + "---|" * 5]
        for n in s["noise"]:
            out.append(f"| {n['arm']} | {_f(n['wall_ratio'], 3)} | x{_f(n['session_geo_sd'], 3)} "
                       f"| {_f(n['after_r1'])} / {_f(n['after_r2'])} "
                       f"| {_f(n['stream_r1'])} / {_f(n['stream_r2'])} |")
    return "\n".join(out) + "\n"


def write(run: Path) -> str:
    s = summarize(run)
    md = render(s)
    (run / "summary.md").write_text(md)
    (run / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    return md


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", type=Path)
    a = ap.parse_args(argv)
    print(write(a.run))


if __name__ == "__main__":
    main()
