"""What long sub-calls did to a replay unit, and to the sessions next to them (offline).

    python long_calls.py <unit dir> [<unit dir> ...] [--min-prompt-tokens 20000]
        [--session <name>]

For each unit folder replay.py wrote (events.jsonl, metrics.csv):

- every sub-call whose prompt has at least `--min-prompt-tokens` tokens (of the sessions
  named with `--session`, or of any): when its request left, how long it took, its sizes;
- the window from the first of them leaving to the last one coming back, and in it the
  engine's KV usage, requests running and waiting, and preemptions (vLLM's /metrics, one
  sample every 0.5 s);
- the gaps between root tokens of every other session, inside that window and outside it.

A unit without such a call gets the same root-gap and engine rows for the whole unit, so
that it can stand next to one that has them. Counts and timings only.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

import analyze


def _pct(xs, q):
    return analyze._pct(xs, q)


def load(udir: Path) -> dict:
    events = [json.loads(x) for x in (udir / "events.jsonl").read_text().splitlines() if x.strip()]
    rows = []
    if (udir / "metrics.csv").exists():
        with open(udir / "metrics.csv") as f:
            rows = list(csv.DictReader(f))
    return {"unit": udir.name, "events": events, "metrics": rows}


def engine(rows: list[dict], t0: float | None = None, t1: float | None = None) -> dict:
    """The engine between t0 and t1 (the whole unit if None)."""
    def keep(r):
        t = float(r["t"])
        return (t0 is None or t >= t0) and (t1 is None or t <= t1)

    sel = [r for r in rows if keep(r)]

    def col(k):
        return [float(r[k]) for r in sel if r.get(k) not in (None, "")]

    kv, run, wait, pre = col("kv"), col("running"), col("waiting"), col("preemptions")
    return {"samples": len(sel), "kv_peak": max(kv, default=None),
            "kv_mean": statistics.fmean(kv) if kv else None,
            "running_max": max(run, default=None), "waiting_max": max(wait, default=None),
            "waiting_share": (sum(1 for w in wait if w > 0) / len(wait)) if wait else None,
            "preemptions": (pre[-1] - pre[0]) if len(pre) > 1 else None}


def root_gaps(events: list[dict], skip: set[str], t0: float | None, t1: float | None) -> dict:
    """Gaps between root tokens of the sessions not in `skip`: those that end inside
    [t0, t1], and the others."""
    inside: list[float] = []
    outside: list[float] = []
    for e in events:
        if e.get("kind") != "root_stream" or e.get("synthetic") or e.get("task_id") in skip:
            continue
        arr = e.get("arrivals") or []
        start = float(e["t_start"])
        for a, b in zip(arr, arr[1:], strict=False):
            at = start + b[0] / 1000.0
            gap = b[0] - a[0]
            (inside if t0 is not None and t0 <= at <= t1 else outside).append(gap)

    def summary(xs):
        if not xs:
            return None
        med = statistics.median(xs)
        return {"gaps": len(xs), "p50_ms": med, "p99_ms": _pct(xs, 0.99), "max_ms": max(xs),
                # time lost in gaps far above the usual one, as analyze.stalls counts it
                "stall_s": sum(g - med for g in xs
                               if g > max(analyze.STALL_FACTOR * med, analyze.STALL_MIN_MS)) / 1000.0}

    return {"inside": summary(inside), "outside": summary(outside)}


def unit_report(u: dict, min_prompt_tokens: int, sessions: list[str] | None = None) -> dict:
    calls = [e for e in u["events"] if e.get("kind") == "replay_call" and not e.get("err")
             and (e.get("pt") or 0) >= min_prompt_tokens
             and (not sessions or e.get("task_id") in sessions)]
    calls.sort(key=lambda e: e["t0"])
    out = {"unit": u["unit"], "long_calls": [
        {"session": c["task_id"], "sent_at": c["t0"], "took_s": c["ms"] / 1000.0,
         "prompt_tokens": c.get("pt"), "output_tokens": c.get("ct"),
         "speculative": c.get("spec") is not None} for c in calls]}
    t0 = t1 = None
    skip: set[str] = set()
    if calls:
        t0 = min(c["t0"] for c in calls)
        t1 = max(c["t0"] + c["ms"] / 1000.0 for c in calls)
        skip = {c["task_id"] for c in calls}
        out["window"] = {"s": t1 - t0, "sent_within_s": max(c["t0"] for c in calls) - t0,
                         "in_flight_max": max(
                             sum(1 for d in calls if d["t0"] <= c["t0"] < d["t0"] + d["ms"] / 1000.0)
                             for c in calls)}
        out["engine_in_window"] = engine(u["metrics"], t0, t1)
    out["engine_unit"] = engine(u["metrics"])
    out["other_roots"] = root_gaps(u["events"], skip, t0, t1)
    return out


def _f(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}"


def render(reports: list[dict], min_prompt_tokens: int) -> str:
    out = ["# Long sub-calls and the sessions next to them (measured)", "",
           f"A long sub-call: a prompt of at least {min_prompt_tokens:,} tokens. The window "
           "runs from the first of them leaving to the last one coming back. Root gaps are "
           "those of the other sessions; a stall is a gap far above the usual one "
           "(analyze.stalls).", "",
           "| unit | long calls | sent within s | in flight at once | window s | KV peak in window "
           "(unit) | preemptions in window (unit) | waiting max in window (unit) "
           "| other roots in window: gap p50 / p99 / max ms, stall s | outside it |",
           "|" + "---|" * 10]

    def gaps(g):
        if not g:
            return "-"
        return (f"{_f(g['p50_ms'])} / {_f(g['p99_ms'])} / {_f(g['max_ms'], 0)}, "
                f"{_f(g['stall_s'])} s")

    for r in reports:
        w, ew, eu = r.get("window"), r.get("engine_in_window") or {}, r["engine_unit"]
        out.append(
            f"| {r['unit']} | {len(r['long_calls'])} | {_f(w['sent_within_s']) if w else '-'} "
            f"| {w['in_flight_max'] if w else '-'} | {_f(w['s'], 0) if w else '-'} "
            f"| {_f(ew.get('kv_peak'), 2)} ({_f(eu['kv_peak'], 2)}) "
            f"| {_f(ew.get('preemptions'), 0)} ({_f(eu['preemptions'], 0)}) "
            f"| {_f(ew.get('waiting_max'), 0)} ({_f(eu['waiting_max'], 0)}) "
            f"| {gaps(r['other_roots']['inside'])} | {gaps(r['other_roots']['outside'])} |")
    for r in reports:
        if not r["long_calls"]:
            continue
        t0 = r["long_calls"][0]["sent_at"]
        out += ["", f"## {r['unit']}: the long calls", "",
                "| session | sent at s | took s | prompt tokens | output tokens | speculative |",
                "|---|---|---|---|---|---|"]
        for c in r["long_calls"]:
            out.append(f"| {c['session']} | {c['sent_at'] - t0:.1f} | {c['took_s']:.1f} "
                       f"| {c['prompt_tokens']:,} | {c['output_tokens']:,} "
                       f"| {'yes' if c['speculative'] else 'no'} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("units", type=Path, nargs="+")
    ap.add_argument("--min-prompt-tokens", type=int, default=20000)
    ap.add_argument("--session", action="append", default=None,
                    help="only this session's long calls (may be given more than once)")
    ap.add_argument("--out", type=Path, default=None, help="write the table here as well")
    a = ap.parse_args(argv)
    reports = [unit_report(load(u), a.min_prompt_tokens, a.session) for u in a.units]
    md = render(reports, a.min_prompt_tokens)
    if a.out:
        a.out.write_text(md)
        a.out.with_suffix(".json").write_text(json.dumps(reports, indent=1))
    print(md)


if __name__ == "__main__":
    main()
