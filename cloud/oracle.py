"""How much of an RLM task's sub-call time is serialisation? (offline, stdlib only)

    python oracle.py <run dir> [--out oracle.md]

Reads the `nospec` units' trajectories (`units/nospec_*/rlm_trajs/*.jsonl`). Only that arm
records every sub-call with its prompt, response and time: the speculative arms run calls
outside the REPL's bookkeeping. No model-written code is executed.

For each turn it rebuilds what ran and asks what the same calls would have cost if every
call had started as soon as its inputs existed:

- **Groups.** A batched call (`llm_query_batched`) shows up as consecutive calls with one
  identical time, the batch's wall time divided by its size. One group per batch, one per
  single call.
- **Dependencies.** A group depends on an earlier group of the same turn if one of the
  earlier responses (its first 48 characters, for responses of at least 24) appears in one
  of its prompts. Short answers such as labels leave no trace in a later prompt, so a
  dependency through them is missed. Results of earlier turns are already there when a
  turn starts.
- **Oracle.** Groups with no dependency between them start together. A wave of calls takes
  the longest of its groups' wall times, or its number of calls times the engine's
  per-request floor if that is longer. The floor is measured in the same run: the smallest
  time per call in batches of 50 or more.

The oracle is optimistic in one way (calls that run together are assumed no slower than
they ran alone or in their own batch) and pessimistic in another (no call starts before
the root has finished writing the turn).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

NEEDLE_MIN, NEEDLE_LEN = 24, 48
FLOOR_MIN_BATCH = 50
DEFAULT_FLOOR_S = 0.02  # used when a run has no large batch to measure it from


def _f(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def groups_of(calls: list[dict]) -> list[dict]:
    """Consecutive calls with the same reported time are one batch."""
    out: list[dict] = []
    for c in calls:
        t = float(c.get("execution_time") or 0.0)
        prompt = c.get("prompt")
        prompt = prompt if isinstance(prompt, str) else json.dumps(prompt)
        resp = str(c.get("response") or "")
        if out and math.isclose(out[-1]["per_call"], t, rel_tol=0, abs_tol=1e-9):
            g = out[-1]
        else:
            g = {"per_call": t, "prompts": [], "needles": set()}
            out.append(g)
        g["prompts"].append(prompt)
        r = resp.strip()
        if len(r) >= NEEDLE_MIN:
            g["needles"].add(r[:NEEDLE_LEN])
    for g in out:
        g["n"] = len(g["prompts"])
        g["wall"] = g["per_call"] * g["n"]
    return out


def levels_of(groups: list[dict]) -> list[int]:
    """Each group's depth in the dependency graph (0: needs nothing from this turn).

    A response only counts as an input of a later prompt if its text was not already in
    the prompts up to its own call. A label such as 'description and abstract concept' is
    in every prompt's list of categories: finding it in a later prompt proves nothing."""
    seen = ""  # every prompt so far, the group's own included
    for g in groups:
        seen += "\x00".join(g["prompts"]) + "\x00"
        g["new_needles"] = {n for n in g["needles"] if n not in seen}
    depth = []
    for i, g in enumerate(groups):
        d = 0
        for j in range(i):
            h = groups[j]
            if depth[j] + 1 > d and h["new_needles"] and any(
                    n in p for p in g["prompts"] for n in h["new_needles"]):
                d = depth[j] + 1
        depth.append(d)
    return depth


def turn_oracle(calls: list[dict], floor_s: float) -> dict:
    groups = groups_of(calls)
    depth = levels_of(groups)
    actual = sum(g["wall"] for g in groups)
    oracle = 0.0
    for lvl in sorted(set(depth)):
        gs = [g for g, d in zip(groups, depth, strict=True) if d == lvl]
        oracle += max(max(g["wall"] for g in gs), floor_s * sum(g["n"] for g in gs))
    oracle = min(oracle, actual)  # the oracle never claims to be slower than what ran
    return {"calls": sum(g["n"] for g in groups), "groups": len(groups),
            "levels": len(set(depth)), "edges": sum(1 for d in depth if d > 0),
            "singles": sum(1 for g in groups if g["n"] == 1),
            "actual_s": actual, "oracle_s": oracle}


def read_task(path: Path) -> list[list[dict]]:
    """Sub-calls per turn (all the turn's blocks together, in order)."""
    turns = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("type") != "iteration":
                continue
            calls = [c for b in d.get("code_blocks", [])
                     for c in (b.get("result") or {}).get("rlm_calls", [])]
            turns.append(calls)
    return turns


def floor_of(all_turns: list[list[dict]]) -> tuple[float, int]:
    """The engine's per-request floor in this run: the smallest time per call over batches
    of FLOOR_MIN_BATCH calls or more. Returns (seconds, batches it was taken from)."""
    per = [g["per_call"] for calls in all_turns for g in groups_of(calls)
           if g["n"] >= FLOOR_MIN_BATCH and g["per_call"] > 0]
    return (min(per), len(per)) if per else (DEFAULT_FLOOR_S, 0)


def analyze(run: Path) -> dict:
    tasks = []
    for udir in sorted((run / "units").glob("nospec_c*_r*")):
        if not (udir / "DONE").exists():
            continue
        meta = json.loads((udir / "unit.json").read_text())
        stats = {t["task_id"]: t for t in
                 json.loads((udir / "unit_stats.json").read_text()).get("tasks", [])}
        events = [json.loads(x) for x in (udir / "events.jsonl").read_text().splitlines()
                  if x.strip()]
        for tid, t in stats.items():
            files = (sorted((udir / "trajs_compact").glob(f"{tid}_*.jsonl"))
                     or sorted((udir / "rlm_trajs").glob(f"{tid}_*.jsonl")))
            if not t.get("ok") or not files:
                continue
            roots = [e for e in events if e["kind"] == "root_stream" and e.get("task_id") == tid]
            tasks.append({"task_id": tid, "unit": udir.name, "conc": meta["conc"],
                          "wall_s": t["wall_s"], "turns": read_task(files[-1]),
                          "stream_s": sum(r.get("stream_s") or 0.0 for r in roots),
                          "exec_s": sum(r.get("exec_s") or 0.0 for r in roots)})
    floor_s, floor_n = floor_of([calls for t in tasks for calls in t["turns"]])
    rows = []
    for t in tasks:
        per_turn = [turn_oracle(calls, floor_s) for calls in t["turns"] if calls]
        rows.append({
            "task_id": t["task_id"], "unit": t["unit"], "conc": t["conc"],
            "wall_s": t["wall_s"], "stream_s": t["stream_s"], "exec_s": t["exec_s"],
            "turns_with_calls": len(per_turn),
            **{k: sum(p[k] for p in per_turn)
               for k in ("calls", "groups", "singles", "edges", "actual_s", "oracle_s")},
            "max_levels": max((p["levels"] for p in per_turn), default=0),
        })
    cells = []
    for conc in sorted({r["conc"] for r in rows}, reverse=True):
        rs = [r for r in rows if r["conc"] == conc]
        wall = sum(r["wall_s"] for r in rs)
        cells.append({
            "conc": conc, "tasks": len(rs),
            "tool_share": sum(r["actual_s"] for r in rs) / wall,
            "oracle_share": sum(r["oracle_s"] for r in rs) / wall,
            "serial_share": sum(r["actual_s"] - r["oracle_s"] for r in rs) / wall,
            "serial_share_p50": statistics.median(
                (r["actual_s"] - r["oracle_s"]) / r["wall_s"] for r in rs),
            "calls": sum(r["calls"] for r in rs), "singles": sum(r["singles"] for r in rs),
            "edges": sum(r["edges"] for r in rs),
        })
    return {"floor_s": floor_s, "floor_batches": floor_n, "cells": cells, "tasks": rows}


def render(a: dict) -> str:
    out = ["# Sub-call time and its serialisation, `nospec` arm (measured, with one model)", "",
           f"Per-request floor of the engine in this run: {1000 * a['floor_s']:.1f} ms per call "
           f"(the smallest in {a['floor_batches']} batches of {FLOOR_MIN_BATCH} calls or more"
           + ("" if a["floor_batches"] else "; none found, so the default is used") + ").", "",
           "Tool share: sub-call wall time over task wall time. Oracle: the same calls if "
           "every group with no dependency on another started together. Serialisation: the "
           "difference, the share of the session spent on calls waiting for unrelated calls.",
           "",
           "| conc | finished tasks | sub-calls (single calls) | dependencies found "
           "| tool share | oracle | serialisation, pooled | per task p50 |",
           "|" + "---|" * 8]
    for c in a["cells"]:
        out.append(f"| {c['conc']} | {c['tasks']} | {c['calls']} ({c['singles']}) | {c['edges']} "
                   f"| {_f(c['tool_share'], 3)} | {_f(c['oracle_share'], 3)} "
                   f"| {_f(c['serial_share'], 3)} | {_f(c['serial_share_p50'], 3)} |")
    out += ["", "## By task", "",
            "| unit | task | wall s | root stream s | sub-calls (single) | groups | deepest chain "
            "| sub-call time s | oracle s | serialisation share |", "|" + "---|" * 10]
    for r in a["tasks"]:
        out.append(
            f"| {r['unit']} | {r['task_id']} | {_f(r['wall_s'], 1)} | {_f(r['stream_s'], 1)} "
            f"| {r['calls']} ({r['singles']}) | {r['groups']} | {r['max_levels']} "
            f"| {_f(r['actual_s'], 1)} | {_f(r['oracle_s'], 1)} "
            f"| {_f((r['actual_s'] - r['oracle_s']) / r['wall_s'], 3)} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="default: <run>/oracle.md")
    a = ap.parse_args(argv)
    res = analyze(a.run)
    md = render(res)
    out = a.out or a.run / "oracle.md"
    out.write_text(md)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    print(md)


if __name__ == "__main__":
    main()
