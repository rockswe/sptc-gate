"""What width bought a replay unit, and where the client was the limit (offline).

    python width.py <unit dir> [<unit dir> ...] [--out width.md]

From the events.jsonl and metrics.csv replay.py wrote for each unit:

- **the bursts:** each run of at least `--min-burst` sub-calls of one session sent less than
  `--burst-gap` seconds apart: how long it took and how many calls a second that is, how
  many calls the session had in flight, how soon 100 were in flight, and the same for the
  whole process while the burst ran (its calls in flight, and the sub-calls of any session
  that came back a second), next to what the engine counted as running and waiting;
- **the roots that waited:** every root turn whose first token took at least `--ttft`
  seconds, with the long prompts sent shortly before it, and how many of the engine's
  samples with a request waiting follow a long prompt;
- **the governor:** its cuts, the moves that gave way to another session of the process,
  how fast its windows opened, and the client's CPU share and the engine's token pace at
  its moves.

Counts and timings only.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
from collections import defaultdict
from pathlib import Path

import analyze
import long_calls
from replay_report import _num


def _pct(xs, q):
    return analyze._pct(xs, q)


def _calls(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "replay_call" and e.get("t0") is not None]


def _end(c: dict) -> float:
    return c["t0"] + c["ms"] / 1000.0


class InFlight:
    """How many of these calls are in flight at a time."""

    def __init__(self, calls: list[dict]):
        self.starts = sorted(c["t0"] for c in calls)
        self.ends = sorted(_end(c) for c in calls)

    def at(self, t: float) -> int:
        return bisect.bisect_right(self.starts, t) - bisect.bisect_right(self.ends, t)


def _unit_t0(events: list[dict]) -> float:
    return next((e["t"] for e in events if e.get("kind") == "unit_begin"),
                min((e["t"] for e in events if "t" in e), default=0.0))


def bursts(u: dict, gap_s: float = 3.0, min_calls: int = 200, grid_s: float = 0.05) -> list:
    """Runs of one session's sub-calls sent less than `gap_s` apart."""
    calls = _calls(u["events"])
    t0, everything = _unit_t0(u["events"]), InFlight(calls)

    def back(lo: float, hi: float) -> int:  # sub-calls of the process back in (lo, hi]
        return bisect.bisect_right(everything.ends, hi) - bisect.bisect_right(everything.ends, lo)

    by = defaultdict(list)
    for c in calls:
        by[c["task_id"]].append(c)
    rows = []
    for session, cs in by.items():
        cs.sort(key=lambda c: c["t0"])
        groups = [[cs[0]]]
        for c in cs[1:]:
            if c["t0"] - groups[-1][-1]["t0"] > gap_s:
                groups.append([])
            groups[-1].append(c)
        for g in groups:
            if len(g) < min_calls:
                continue
            own = InFlight(g)
            first, last = own.starts[0], own.ends[-1]
            grid = [first + i * grid_s for i in range(int((last - first) / grid_s) + 1)]
            mine, total = [own.at(t) for t in grid], [everything.at(t) for t in grid]
            ms = [c["ms"] for c in g]
            eng = long_calls.engine(u["metrics"], first, last)
            running = [float(r["running"]) for r in u["metrics"]
                       if first <= float(r["t"]) <= last and r.get("running") not in (None, "")]
            rows.append({
                "session": session, "calls": len(g), "sent_at_s": first - t0,
                "lasted_s": last - first, "calls_per_s": len(g) / (last - first),
                "in_flight_mean": statistics.fmean(mine), "in_flight_max": max(mine),
                "process_in_flight_mean": statistics.fmean(total),
                "process_in_flight_max": max(total),
                "process_calls_per_s": back(first, last) / (last - first),
                "engine_running_p50": _pct(running, 0.5),
                "engine_running_max": eng["running_max"], "engine_waiting_max": eng["waiting_max"],
                "to_100_s": next((t - first for t, k in zip(grid, mine) if k >= 100), None),
                "ms_p50": _pct(ms, 0.5), "ms_p90": _pct(ms, 0.9),
                "output_tokens_p50": _pct([c.get("ct") or 0 for c in g], 0.5)})
    return sorted(rows, key=lambda r: r["sent_at_s"])


def waited(u: dict, ttft_s: float = 0.5, long_tokens: int = 5000, before_s: float = 3.0,
           after_s: float = 2.5) -> dict:
    """Root turns that waited for their first token, and the engine's queue, against the
    long prompts sent just before."""
    t0 = _unit_t0(u["events"])
    long = sorted(c["t0"] for c in _calls(u["events"]) if (c.get("pt") or 0) >= long_tokens)
    tokens = {c["t0"]: c["pt"] for c in _calls(u["events"]) if (c.get("pt") or 0) >= long_tokens}
    roots = [e for e in u["events"] if e.get("kind") == "root_stream"
             and e.get("ttft_s") is not None]
    turns = []
    for e in sorted(roots, key=lambda e: -e["ttft_s"]):
        if e["ttft_s"] < ttft_s:
            break
        near = [t for t in long if -before_s <= t - e["t_start"] <= e["ttft_s"]]
        turns.append({"session": e["task_id"], "turn": e.get("iteration"),
                      "began_at_s": e["t_start"] - t0, "ttft_s": e["ttft_s"],
                      "prompt_tokens": e.get("prompt_tokens"), "long_prompts_before": len(near),
                      "their_tokens": sum(tokens[t] for t in near),
                      "first_sent_s_before": (e["t_start"] - near[0]) if near else None})
    samples = [(float(r["t"]), float(r["waiting"])) for r in u["metrics"]
               if r.get("waiting") not in (None, "")]
    queued = [t for t, w in samples if w > 0]

    def follows(t):
        i = bisect.bisect_right(long, t) - 1
        return i >= 0 and t - long[i] <= after_s

    return {"root_turns": len(roots), "waited": turns, "samples": len(samples),
            "samples_with_a_request_waiting": len(queued),
            "of_them_after_a_long_prompt": sum(1 for t in queued if follows(t)),
            "long_prompts": len(long)}


def governor(u: dict, ramp_gap_s: float = 1.0) -> dict | None:
    """The governor's cuts and ramps, and what the client and the engine said at its moves."""
    moves = [e for e in u["events"] if e.get("kind") == "spec_govern"]
    if not moves:
        return None
    t0 = _unit_t0(u["events"])
    def move(e: dict) -> dict:
        return {"at_s": e["t"] - t0, "session": e.get("task_id"), "was": _num(e.get("was")),
                "window": _num(e.get("window")), "why": e.get("why"),
                "waiting": _num(e.get("waiting")), "running": _num(e.get("running"))}

    # a cut: the engine queued, preempted or was short of KV cache. A share: another
    # session of the process asked for its part of the process's ceiling
    cuts = [move(e) for e in moves if e.get("why") in ("queue", "kv", "preempted")]
    shares = [move(e) for e in moves if e.get("why") == "share"]
    by = defaultdict(list)
    for e in moves:
        if e.get("why") == "grow":
            by[e.get("task_id")].append(e)
    ramps = []
    for session, es in by.items():
        runs = [[es[0]]]
        for e in es[1:]:
            if e["t"] - runs[-1][-1]["t"] > ramp_gap_s:
                runs.append([])
            runs[-1].append(e)
        for r in runs:
            ramps.append({"session": session, "at_s": r[0]["t"] - t0, "from": _num(r[0].get("was")),
                          "to": _num(r[-1].get("window")), "s": r[-1]["t"] - r[0]["t"],
                          "steps": len(r)})
    cpu = [x for x in (_num(e.get("cpu")) for e in moves) if x is not None]
    tax = [x for x in (_num(e.get("tax")) for e in moves) if x is not None]
    grow_cpu = [x for x in (_num(e.get("cpu")) for e in moves if e.get("why") == "grow")
                if x is not None]
    return {"moves": len(moves), "cuts": cuts, "shares": shares,
            "ramps": sorted(ramps, key=lambda r: r["at_s"]),
            "cpu_p50": _pct(cpu, 0.5), "cpu_max": max(cpu, default=None),
            "tax_p50": _pct(tax, 0.5), "tax_max": max(tax, default=None),
            "grow_moves": len(grow_cpu), "grow_moves_cpu_090": sum(1 for x in grow_cpu if x >= 0.9)}


def unit_report(u: dict, a) -> dict:
    return {"unit": u["unit"], "bursts": bursts(u, a.burst_gap, a.min_burst),
            "waited": waited(u, a.ttft, a.long_tokens), "governor": governor(u)}


def _f(x, nd=1):
    return "-" if x is None else f"{x:,.{nd}f}"


def render(reports: list[dict]) -> str:
    out = ["# What width bought, and where the client was the limit (measured)"]
    note = ("A burst: sub-calls of one session sent less than 3 s apart. In flight: sent and "
            "not yet back, by the client's clock. Whole process: the sub-calls of every "
            "session while the burst ran. Engine: its own count of requests, roots included "
            "(`/metrics`, two samples a second).")
    head = ("| unit | session | calls | tokens written, median | sent at s | lasted s | calls a "
            "second | in flight, mean / most | 100 in flight after s | sub-call ms, median / "
            "90th | whole process: in flight, mean / most | whole process: calls a second | "
            "engine: running, median / most; waiting, most |")
    out += ["", "## Bursts", "", note, "", head,
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        for b in r["bursts"]:
            out.append(
                f"| {r['unit']} | {b['session']} | {b['calls']:,} "
                f"| {_f(b['output_tokens_p50'], 0)} | {_f(b['sent_at_s'])} | {_f(b['lasted_s'])} "
                f"| {_f(b['calls_per_s'], 0)} | {_f(b['in_flight_mean'], 0)} / {b['in_flight_max']} "
                f"| {_f(b['to_100_s'], 2)} | {_f(b['ms_p50'], 0)} / {_f(b['ms_p90'], 0)} "
                f"| {_f(b['process_in_flight_mean'], 0)} / {b['process_in_flight_max']} "
                f"| {_f(b['process_calls_per_s'], 0)} "
                f"| {_f(b['engine_running_p50'], 0)} / {_f(b['engine_running_max'], 0)}; "
                f"{_f(b['engine_waiting_max'], 0)} |")
    head = ("| unit | root turns | waited 0.5 s or more | session, turn | began at s | TTFT s | "
            "long prompts sent in the 3 s before or while it waited: number, tokens | samples "
            "with a request waiting | of them within 2.5 s after a long prompt was sent |")
    out += ["", "## Root turns that waited for their first token, and the engine's queue", "",
            head, "|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        w = r["waited"]
        first = w["waited"][0] if w["waited"] else None
        if first:
            turn = (f"{first['session']}, {first['turn']} | {_f(first['began_at_s'])} "
                    f"| {_f(first['ttft_s'], 2)} "
                    f"| {first['long_prompts_before']}, {first['their_tokens']:,}")
        else:
            turn = "- | - | - | -"
        out.append(f"| {r['unit']} | {w['root_turns']} | {len(w['waited'])} | {turn} "
                   f"| {w['samples_with_a_request_waiting']} of {w['samples']} "
                   f"| {w['of_them_after_a_long_prompt']} |")
    gov = [r for r in reports if r["governor"]]
    if gov:
        head = ("| unit | moves | cuts: at s, session, window, engine waiting / running | "
                "moves down to a share of the process's ceiling | "
                "windows opened: number, from, to, seconds, steps (medians) | client CPU share "
                "at its moves, median / most | growth moves at 0.9 of a core or more | engine "
                "token pace above quiet at its moves, median / most |")
        out += ["", "## The governor", "", head, "|---|---|---|---|---|---|---|---|"]
        for r in gov:
            g = r["governor"]
            cuts = "; ".join(f"{_f(c['at_s'])} {c['session']} {_f(c['was'], 0)} to "
                             f"{_f(c['window'], 0)} ({_f(c['waiting'], 0)} / {_f(c['running'], 0)})"
                             for c in g["cuts"]) or "-"
            big = [x for x in g["ramps"] if x["steps"] >= 3]
            ramp = (f"{len(big)} of 3 steps or more: {_f(_pct([x['from'] for x in big], 0.5), 0)} "
                    f"to {_f(_pct([x['to'] for x in big], 0.5), 0)} in "
                    f"{_f(_pct([x['s'] for x in big], 0.5), 2)} s, "
                    f"{_f(_pct([x['steps'] for x in big], 0.5), 0)} steps") if big else "-"
            out.append(f"| {r['unit']} | {g['moves']} | {cuts} | {len(g['shares'])} | {ramp} "
                       f"| {_f(g['cpu_p50'], 2)} / {_f(g['cpu_max'], 2)} "
                       f"| {g['grow_moves_cpu_090']} of {g['grow_moves']} "
                       f"| {_f(g['tax_p50'], 2)} / {_f(g['tax_max'], 2)} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("units", type=Path, nargs="+")
    ap.add_argument("--min-burst", type=int, default=200)
    ap.add_argument("--burst-gap", type=float, default=3.0)
    ap.add_argument("--ttft", type=float, default=0.5)
    ap.add_argument("--long-tokens", type=int, default=5000)
    ap.add_argument("--out", type=Path, default=None, help="write the tables here as well")
    a = ap.parse_args(argv)
    units = [long_calls.load(u) for u in a.units]
    reports = [unit_report(u, a) for u in units]
    md = render(reports)
    if a.out:
        a.out.write_text(md)
        a.out.with_suffix(".json").write_text(json.dumps(reports, indent=1))
    print(md)


if __name__ == "__main__":
    main()
