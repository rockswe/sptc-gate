"""What an RLM campaign's logs say beyond summary.md (offline, stdlib only).

    python analyze.py <run dir> [--out analysis.md]

Reads the unit folders `rlm_campaign.py run` wrote (events.jsonl, unit_stats.json,
unit.json) and reports, per arm and concurrency:

- the time budget of a finished task: the root's streams, the time after them, the rest;
- the sub-call work: calls per task, their wall time, and the root's output tokens;
- root stalls: gaps between the root's tokens far above that stream's usual gap, from the
  per-delta arrival times;
- what speculation did: dispatches by source, hits, misses, evictions, shadow stops;
- the noise floor: how much the same arm's two repeats of one task differ, next to the
  difference between arms.

Everything is measured. Nothing here re-runs model-written code.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ("nospec", "fanout", "stream")
STALL_FACTOR = 4.0  # a gap is a stall above this many times the stream's median gap ...
STALL_MIN_MS = 200.0  # ... and above this floor


def _pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _f(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


_USAGE = re.compile(r"total_calls=(\d+), total_input_tokens=(\d+), total_output_tokens=(\d+)")


def sub_usage(task: dict) -> dict:
    """Sub-call totals from a task's usage summary: calls, prompt tokens, output tokens.

    rlms keys its usage summary by model name. Root and sub-calls use the same model here
    and the sub-call client's entry is the one that survives, so these are the sub-calls
    alone, speculative ones that were never claimed included. The root's tokens come from
    the root_stream records."""
    m = _USAGE.search(str(task.get("usage") or ""))
    if not m:
        return {"sub_calls": None, "sub_in_tokens": None, "sub_out_tokens": None}
    calls, tin, tout = (int(x) for x in m.groups())
    return {"sub_calls": calls, "sub_in_tokens": tin, "sub_out_tokens": tout}


def load(run: Path) -> list[dict]:
    """One record per finished unit: its tasks, root streams and speculation events."""
    units = []
    for udir in sorted((run / "units").glob("*_c*_r*")):
        if not (udir / "DONE").exists():
            continue
        meta = json.loads((udir / "unit.json").read_text())
        stats = json.loads((udir / "unit_stats.json").read_text())
        events = [json.loads(x) for x in (udir / "events.jsonl").read_text().splitlines()
                  if x.strip()]
        units.append({**meta, "unit": udir.name, "tasks": stats.get("tasks", []),
                      "events": events})
    return units


def stalls(root: dict) -> dict:
    """Gaps between one root stream's deltas: the usual gap, and the time lost in stalls
    (the part of each long gap above the usual one)."""
    arr = root.get("arrivals") or []
    gaps = [b[0] - a[0] for a, b in zip(arr, arr[1:], strict=False)]
    if len(gaps) < 8:
        return {"gaps": gaps, "median_ms": None, "stall_s": 0.0, "n_stalls": 0, "max_ms": None}
    med = statistics.median(gaps)
    cut = max(STALL_FACTOR * med, STALL_MIN_MS)
    long = [g for g in gaps if g > cut]
    return {"gaps": gaps, "median_ms": med, "max_ms": max(gaps), "n_stalls": len(long),
            "stall_s": sum(g - med for g in long) / 1000.0}


def task_rows(units: list[dict]) -> list[dict]:
    """One row per task run: where its time went and what its sub-calls were."""
    rows = []
    for u in units:
        by_task: dict = defaultdict(list)
        for e in u["events"]:
            if e.get("task_id") is not None:
                by_task[e["task_id"]].append(e)
        for t in u["tasks"]:
            ev = by_task.get(t["task_id"], [])
            roots = [e for e in ev if e["kind"] == "root_stream"]
            spec = Counter(e["kind"][5:] for e in ev if e["kind"].startswith("spec_"))
            src = Counter(e.get("source") for e in ev if e["kind"] == "spec_dispatch")
            st = [stalls(r) for r in roots]
            wall = t.get("wall_s") or 0.0
            stream_s = sum(r.get("stream_s") or 0.0 for r in roots)
            after_s = sum((r.get("shadow_wait_s") or 0.0) + (r.get("exec_s") or 0.0)
                          for r in roots)
            ready_ms = [float(e["ms"]) for e in ev if e["kind"] == "spec_ready" and "ms" in e]
            rows.append({
                "arm": u["arm"], "conc": u["conc"], "rep": u["rep"], "task_id": t["task_id"],
                "dataset": t.get("dataset"), "ok": bool(t.get("ok")), "score": t.get("score"),
                "error": (t.get("error") or "")[:120], "wall_s": wall, "turns": len(roots),
                "stream_s": stream_s, "after_s": after_s,
                "other_s": max(0.0, wall - stream_s - after_s),
                "root_out_tokens": sum(r.get("tokens") or 0 for r in roots),
                "root_prompt_tokens_last": max((r.get("prompt_tokens") or 0 for r in roots),
                                               default=0),
                "gaps": [g for s in st for g in s["gaps"]],
                "stall_s": sum(s["stall_s"] for s in st),
                "n_stalls": sum(s["n_stalls"] for s in st),
                # sub-calls: nospec records them in the trajectory; the others on the bus
                "subcalls": (t.get("n_subcalls") if u["arm"] == "nospec"
                             else spec.get("dispatch", 0) + spec.get("claim_miss", 0)),
                "subcall_sum_s": t.get("subcall_time_sum_s") if u["arm"] == "nospec" else None,
                "spec": dict(spec), "dispatch_source": dict(src),
                "spec_call_ms_p50": _pct(ready_ms, 0.5),
                "shadow_stops": [e.get("reason", "")[:60] for e in ev
                                 if e["kind"] == "spec_shadow_stop"],
                **sub_usage(t),
            })
    return rows


CAP = 16  # spec-ptc's calls in flight (SpeculativeLocalREPL spec_max_inflight)
CAUSES = ("not speculated", "partly speculated", "serial launches", "burst over the cap",
          "still running at stream end", "not on the bus")


def turn_cause(t: dict) -> str:
    """Why a speculative arm's turn still waited after its stream, from its events.

    not speculated: the real run made the turn's calls itself (the shadow stopped, its
      thread ended, or it never reached them).
    partly speculated: some calls were claimed, some were not.
    serial launches: every call was claimed, but the shadow launched them one after
      another, each after the one before had answered (it stalls where a result is used).
    burst over the cap: every call was claimed and more than CAP were launched at once,
      so they queued inside spec-ptc.
    still running at stream end: every call was claimed, CAP or fewer, launched together.
    not on the bus: no call of this turn went through spec-ptc's hooks (rlm_query and
      rlm_query_batched are never speculated; or the time is plain code)."""
    if t["misses"] and not t["hits"]:
        return "not speculated"
    if t["misses"]:
        return "partly speculated"
    if not t["hits"]:
        return "not on the bus"
    if t["dispatch_span_s"] > 0.5 * t["after_s"] and t["dispatched"] >= 3:
        return "serial launches"
    if t["dispatched"] > CAP:
        return "burst over the cap"
    return "still running at stream end"


def turn_rows(units: list[dict], min_after_s: float = 1.0) -> list[dict]:
    """One row per turn of a speculative arm that waited at least min_after_s after its
    stream. Turns of failed tasks count too: a task that timed out waited the longest."""
    rows = []
    for u in units:
        if u["arm"] == "nospec":
            continue
        by_task: dict = defaultdict(list)
        for e in u["events"]:
            if e.get("task_id") is not None:
                by_task[e["task_id"]].append(e)
        ok = {t["task_id"]: bool(t.get("ok")) for t in u["tasks"]}
        for tid, ev in by_task.items():
            for r in (e for e in ev if e["kind"] == "root_stream"):
                after = (r.get("shadow_wait_s") or 0.0) + (r.get("exec_s") or 0.0)
                if after < min_after_s:
                    continue
                t0 = r["t_start"]
                t1 = t0 + (r.get("stream_s") or 0.0)
                t2 = t1 + after + 0.5
                inturn = [e for e in ev if t0 <= e["t"] <= t2]
                disp = sorted(e["t"] for e in inturn if e["kind"] == "spec_dispatch")
                row = {
                    "arm": u["arm"], "conc": u["conc"], "unit": u["unit"], "task_id": tid,
                    "ok": ok.get(tid, False), "iteration": r.get("iteration"),
                    "stream_s": r.get("stream_s") or 0.0, "after_s": after,
                    "shadow_wait_s": r.get("shadow_wait_s") or 0.0,
                    "dispatched": len(disp),
                    "dispatched_in_stream": sum(1 for x in disp if x <= t1),
                    "dispatch_span_s": (disp[-1] - disp[0]) if len(disp) > 1 else 0.0,
                    "head_start_s": (t1 - disp[0]) if disp else None,
                    "hits": sum(1 for e in inturn if e["kind"] == "spec_claim_hit"),
                    "misses": sum(1 for e in inturn if e["kind"] == "spec_claim_miss"),
                    "stops": [e.get("reason", "")[:50] for e in inturn
                              if e["kind"] == "spec_shadow_stop"],
                }
                row["cause"] = turn_cause(row)
                rows.append(row)
    return rows


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def _geo_sd(logs: list[float]) -> float | None:
    """Typical multiplicative difference of a pair: exp(sqrt(mean(log ratio squared)))."""
    return math.exp(math.sqrt(statistics.fmean(x * x for x in logs))) if logs else None


def noise(rows: list[dict]) -> dict:
    """Task wall time, same arm and task, repeat 1 against repeat 2: the noise floor.
    And arm against arm at the same repeat, for comparison."""
    wall = {(r["arm"], r["conc"], r["rep"], r["task_id"]): r["wall_s"] for r in rows if r["ok"]}
    out = {}
    for conc in sorted({r["conc"] for r in rows}, reverse=True):
        same = [math.log(w / wall[(a, c, 2, t)]) for (a, c, rep, t), w in wall.items()
                if c == conc and rep == 1 and (a, c, 2, t) in wall]
        cell = {"same_arm_pairs": len(same), "same_arm_geo_sd": _geo_sd(same)}
        for a, b in (("stream", "nospec"), ("fanout", "nospec"), ("stream", "fanout")):
            logs = [math.log(w / wall[(b, c, rep, t)]) for (x, c, rep, t), w in wall.items()
                    if x == a and c == conc and (b, c, rep, t) in wall]
            cell[f"{a}_vs_{b}"] = {"pairs": len(logs), "geo_sd": _geo_sd(logs),
                                   "geo_mean": math.exp(statistics.fmean(logs)) if logs else None}
        out[conc] = cell
    return out


def warmup_waves(run: Path) -> list[dict]:
    """The warm-up's waves, first pass next to second: what the engine's first sight of a
    batch shape costs, and what the same wave costs once warm."""
    f = run / "campaign.jsonl"
    if not f.exists():
        return []
    ev = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    by: dict = defaultdict(dict)
    for e in ev:
        if e.get("kind") == "warmup_wave":
            by[(e["n"], e["prompt"])][e["pass"]] = e
    return [{"n": n, "prompt": kind, "passes": passes} for (n, kind), passes in by.items()]


def analyze(run: Path) -> dict:
    units = load(run)
    rows = task_rows(units)
    turns = turn_rows(units)
    causes = []
    for conc in sorted({t["conc"] for t in turns}, reverse=True):
        for arm in ARMS[1:]:
            ts = [t for t in turns if t["arm"] == arm and t["conc"] == conc]
            total = sum(t["after_s"] for t in ts)
            if ts:
                causes.append({"arm": arm, "conc": conc, "turns": len(ts), "after_s": total,
                               "by_cause": {c: {"turns": sum(1 for t in ts if t["cause"] == c),
                                                "s": sum(t["after_s"] for t in ts
                                                         if t["cause"] == c)}
                                            for c in CAUSES}})
    cells = []
    for conc in sorted({r["conc"] for r in rows}, reverse=True):
        for arm in ARMS:
            rs = [r for r in rows if r["arm"] == arm and r["conc"] == conc]
            ok = [r for r in rs if r["ok"]]
            if not rs:
                continue
            wall = sum(r["wall_s"] for r in ok)
            gaps = [g for r in ok for g in r["gaps"]]
            stream = sum(r["stream_s"] for r in ok)
            spec = Counter()
            src = Counter()
            for r in rs:
                spec.update(r["spec"])
                src.update(r["dispatch_source"])
            cells.append({
                "arm": arm, "conc": conc, "tasks": len(rs), "ok": len(ok),
                "wall_p50": _pct([r["wall_s"] for r in ok], 0.5),
                "turns_mean": statistics.fmean(r["turns"] for r in ok) if ok else None,
                "share_stream": stream / wall if wall else None,
                "share_after": sum(r["after_s"] for r in ok) / wall if wall else None,
                "share_other": sum(r["other_s"] for r in ok) / wall if wall else None,
                "root_out_tokens_p50": _pct([r["root_out_tokens"] for r in ok], 0.5),
                "subcalls_p50": _pct([r["subcalls"] for r in ok], 0.5),
                "subcalls_max": max((r["subcalls"] or 0 for r in ok), default=None),
                "subcall_sum_p50": _pct([r["subcall_sum_s"] for r in ok], 0.5),
                "sub_calls_p50": _pct([r["sub_calls"] for r in ok], 0.5),
                "sub_in_tokens_p50": _pct([r["sub_in_tokens"] for r in ok], 0.5),
                "sub_out_tokens_p50": _pct([r["sub_out_tokens"] for r in ok], 0.5),
                "sub_out_token_share": _ratio(sum(r["sub_out_tokens"] or 0 for r in ok),
                                              sum((r["sub_out_tokens"] or 0)
                                                  + r["root_out_tokens"] for r in ok)),
                "gap_p50": _pct(gaps, 0.5), "gap_p99": _pct(gaps, 0.99),
                "gap_max": max(gaps, default=None),
                "stall_share": sum(r["stall_s"] for r in ok) / stream if stream else None,
                "stalls_per_task": statistics.fmean(r["n_stalls"] for r in ok) if ok else None,
                "spec": dict(spec), "dispatch_source": dict(src),
                "shadow_stops": Counter(s for r in rs for s in r["shadow_stops"]).most_common(6),
                "errors": Counter(r["error"][:70] for r in rs if not r["ok"]).most_common(4),
            })
    by_task = []
    for tid in sorted({r["task_id"] for r in rows}):
        rec = {"task_id": tid}
        for arm in ARMS:
            ok = [r for r in rows if r["task_id"] == tid and r["arm"] == arm and r["ok"]]
            w = sum(r["wall_s"] for r in ok)
            rec[arm] = {"runs": len(ok), "wall_p50": _pct([r["wall_s"] for r in ok], 0.5),
                        "after_share": sum(r["after_s"] for r in ok) / w if w else None,
                        "subcalls_p50": _pct([r["subcalls"] for r in ok], 0.5),
                        "score": statistics.fmean(r["score"] or 0 for r in ok) if ok else None}
        by_task.append(rec)
    for r in rows:
        r.pop("gaps")
    return {"cells": cells, "by_task": by_task, "noise": noise(rows), "tasks": rows,
            "warmup": warmup_waves(run), "causes": causes,
            "turns": sorted(turns, key=lambda t: -t["after_s"])}


def render(a: dict) -> str:
    out = ["# RLM campaign analysis (measured)", "",
           "## Time budget of a finished task", "",
           "Pooled shares of task wall time. Stream: the root's completions. After: from the "
           "end of each stream until that turn's code has run. Other: everything else "
           "(prompt building, REPL start, the final-answer call).", "",
           "| arm | conc | finished / tasks | wall p50 s | turns | stream | after | other "
           "| root output tokens p50 | sub-calls p50 (max) | sub-call time p50 s (nospec) |",
           "|" + "---|" * 11]
    for c in a["cells"]:
        out.append(
            f"| {c['arm']} | {c['conc']} | {c['ok']} / {c['tasks']} | {_f(c['wall_p50'], 1)} "
            f"| {_f(c['turns_mean'], 1)} | {_f(c['share_stream'], 3)} | {_f(c['share_after'], 3)} "
            f"| {_f(c['share_other'], 3)} | {_f(c['root_out_tokens_p50'], 0)} "
            f"| {_f(c['subcalls_p50'], 0)} ({_f(c['subcalls_max'], 0)}) "
            f"| {_f(c['subcall_sum_p50'], 2)} |")
    out += ["", "## Sub-call work", "",
            "From each task's usage summary: sub-calls the engine received (speculative "
            "ones that were never claimed included), their prompt and output tokens, and "
            "the sub-calls' share of all output tokens (root plus sub-calls).", "",
            "| arm | conc | sub-calls p50 | prompt tokens p50 | output tokens p50 "
            "| share of output tokens |", "|" + "---|" * 6]
    for c in a["cells"]:
        out.append(f"| {c['arm']} | {c['conc']} | {_f(c['sub_calls_p50'], 0)} "
                   f"| {_f(c['sub_in_tokens_p50'], 0)} | {_f(c['sub_out_tokens_p50'], 0)} "
                   f"| {_f(c['sub_out_token_share'], 3)} |")
    out += ["", "## Root stalls", "",
            f"Gaps between the root's deltas. A stall is a gap above {STALL_FACTOR:g} times its "
            f"stream's median gap and above {STALL_MIN_MS:g} ms; stall share is the time lost "
            "in stalls over the root's total stream time.", "",
            "| arm | conc | gap p50 ms | gap p99 ms | gap max ms | stalls per task | stall share |",
            "|" + "---|" * 7]
    for c in a["cells"]:
        out.append(f"| {c['arm']} | {c['conc']} | {_f(c['gap_p50'], 1)} | {_f(c['gap_p99'], 1)} "
                   f"| {_f(c['gap_max'], 0)} | {_f(c['stalls_per_task'], 1)} "
                   f"| {_f(c['stall_share'], 3)} |")
    out += ["", "## What speculation did", "",
            "| arm | conc | dispatched (peek / shadow) | hits | misses | evicted | shadow stops |",
            "|" + "---|" * 7]
    for c in a["cells"]:
        if c["arm"] == "nospec":
            continue
        s, src = c["spec"], c["dispatch_source"]
        stops = "; ".join(f"{n}x {why}" for why, n in c["shadow_stops"]) or "-"
        out.append(f"| {c['arm']} | {c['conc']} | {s.get('dispatch', 0)} "
                   f"({src.get('peek', 0)} / {src.get('shadow', 0)}) | {s.get('claim_hit', 0)} "
                   f"| {s.get('claim_miss', 0)} | {s.get('evict', 0)} | {stops} |")
    if a.get("causes"):
        out += ["", "## Why the speculative arms still waited", "",
                "Turns that waited at least 1 s after their stream, failed tasks' turns "
                "included, and the seconds waited, by cause (from each turn's events):", "",
                "- **not speculated:** the real run made the calls itself. The shadow had "
                "stopped, its thread had ended, or it never reached them.",
                "- **partly speculated:** some calls were claimed, some were not.",
                "- **serial launches:** every call was claimed, but they were launched one "
                "after another: the shadow stalls wherever a result is used.",
                f"- **burst over the cap:** more than {CAP} calls launched at once, so they "
                "queued inside spec-ptc.",
                "- **still running at stream end:** launched together, within the cap.",
                "- **not on the bus:** no call went through spec-ptc's hooks "
                "(`rlm_query*` is never speculated), or the time is plain code.", "",
                "| arm | conc | turns | seconds waited | " + " | ".join(CAUSES) + " |",
                "|" + "---|" * (4 + len(CAUSES))]
        for c in a["causes"]:
            cells = " | ".join(f"{c['by_cause'][k]['s']:.0f} s ({c['by_cause'][k]['turns']})"
                               for k in CAUSES)
            out.append(f"| {c['arm']} | {c['conc']} | {c['turns']} | {c['after_s']:.0f} "
                       f"| {cells} |")
        out += ["", "The longest waits:", "",
                "| unit | task | turn | waited s (shadow wait) | launched (in stream) "
                "| head start s | hits / misses | cause | shadow stop |", "|" + "---|" * 9]
        for t in a["turns"][:14]:
            out.append(
                f"| {t['unit']} | {t['task_id']}{'' if t['ok'] else ' (failed)'} "
                f"| {t['iteration']} | {t['after_s']:.1f} ({t['shadow_wait_s']:.1f}) "
                f"| {t['dispatched']} ({t['dispatched_in_stream']}) | {_f(t['head_start_s'], 1)} "
                f"| {t['hits']} / {t['misses']} | {t['cause']} "
                f"| {'; '.join(t['stops']) or '-'} |")
    out += ["", "## Noise floor", "",
            "Typical multiplicative difference in task wall time (the root mean square of "
            "the log ratio, as a factor). Same arm: one task's repeat 1 against its repeat 2. "
            "Between arms: the same task and repeat.", "",
            "| conc | same arm, repeat 1 vs 2 (pairs) | stream vs nospec: mean, spread (pairs) "
            "| fanout vs nospec | stream vs fanout |", "|" + "---|" * 5]
    for conc, n in a["noise"].items():
        def arm(k, n=n):
            v = n[k]
            return f"{_f(v['geo_mean'], 3)}, x{_f(v['geo_sd'], 2)} ({v['pairs']})"
        out.append(f"| {conc} | x{_f(n['same_arm_geo_sd'], 2)} ({n['same_arm_pairs']}) "
                   f"| {arm('stream_vs_nospec')} | {arm('fanout_vs_nospec')} "
                   f"| {arm('stream_vs_fanout')} |")
    out += ["", "## By task", "",
            "| task | nospec: runs, wall p50 s, after share, sub-calls p50, score "
            "| fanout | stream |", "|" + "---|" * 4]
    for t in a["by_task"]:
        def cell(v):
            return (f"{v['runs']}, {_f(v['wall_p50'], 1)}, {_f(v['after_share'], 3)}, "
                    f"{_f(v['subcalls_p50'], 0)}, {_f(v['score'], 2)}")
        out.append(f"| {t['task_id']} | {cell(t['nospec'])} | {cell(t['fanout'])} "
                   f"| {cell(t['stream'])} |")
    if a.get("warmup"):
        out += ["", "## Warm-up waves", "",
                "One streamed request with n concurrent short-output requests next to it. "
                "Wall time of the wave and the stream's longest token gap, first pass and "
                "second.", "",
                "| n | prompts | pass 1: wall s, longest gap ms | pass 2: wall s, longest gap ms |",
                "|" + "---|" * 4]
        for w in a["warmup"]:
            def one(k, w=w):
                p = w["passes"].get(k)
                return "-" if not p else f"{_f(p['wall_s'], 2)}, {_f(p['stream_max_gap_ms'], 0)}"
            out.append(f"| {w['n']} | {w['prompt']} | {one(1)} | {one(2)} |")
    errs = [(c["arm"], c["conc"], c["errors"]) for c in a["cells"] if c["errors"]]
    if errs:
        out += ["", "## Failed tasks", ""]
        out += [f"- {arm}, concurrency {conc}: " + "; ".join(f"{n}x {e}" for e, n in es)
                for arm, conc, es in errs]
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="default: <run>/analysis.md")
    a = ap.parse_args(argv)
    res = analyze(a.run)
    md = render(res)
    out = a.out or a.run / "analysis.md"
    out.write_text(md)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    print(md)


if __name__ == "__main__":
    main()
