"""What a recording's sessions wrote (offline, stdlib only): PREREG_RECORD.md's census.

    python record_report.py <run dir> [--corpus <dir>] [--tag fix]

Reads what rlm_record.py left for the `nospec` units of one run (unit_stats.json,
events.jsonl, the trajectories, batch_fix.json) and the run's campaign.jsonl. Writes
census.md and census.json into the run folder: counts and timings only, no text of a
session, so both can be published.

- **A single call** is a sub-call the trajectory records alone. **A batch** is a run of
  consecutive recorded calls with one identical time (one `llm_query_batched`).
- **A loop of single calls** is a turn with at least 20 single calls, **a loop of batches**
  a turn with at least 5 batches.
- **Status.** `finished`; `timeout` (rlms stopped the task between two turns); `deadline`
  (rlm_record.py refused its sub-calls); `failed` (anything else).
- **Replay.** A finished session and one the timeout stopped can be replayed, if the
  corpus build reproduces them (`--corpus`: its manifest says so). One of them is left out
  by PREREG_RECORD.md's rule: no turn with more than one sub-call, and at least 120 s
  after its streams.

A session is named <task>.<tag><repeat>, as `replay_corpus.py build --tag` names it.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import oracle

SINGLE_LOOP_MIN = 20  # single calls in a turn
BATCH_LOOP_MIN = 5  # batches in a turn
LEFT_OUT_AFTER_S = 120.0  # PREREG_RECORD.md: one call per turn, and this long after the streams
LOOP_ERROR = "Event loop is closed"


def _f(x, nd=1) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def status_of(row: dict) -> str:
    if row.get("ok"):
        return "finished"
    err = str(row.get("error") or "")
    if err.startswith("TimeoutExceededError"):
        return "timeout"
    if err.startswith("SubcallDeadline"):
        return "deadline"
    return "failed"


def turn_shape(calls: list[dict]) -> dict:
    """One turn's recorded sub-calls, as single calls and batches."""
    groups = oracle.groups_of(calls)
    sizes = [g["n"] for g in groups if g["n"] > 1]
    singles = sum(1 for g in groups if g["n"] == 1)
    return {"calls": len(calls), "singles": singles, "batches": len(sizes),
            "batch_sizes": sizes, "call_s": sum(g["wall"] for g in groups),
            "single_loop": singles >= SINGLE_LOOP_MIN, "batch_loop": len(sizes) >= BATCH_LOOP_MIN}


def read_turns(path: Path) -> list[dict]:
    """Per turn: its recorded sub-calls (all blocks, in order), and how often the REPL's
    output holds the string rlms gives for a prompt it lost."""
    turns = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("type") != "iteration":
                continue
            blocks = d.get("code_blocks") or []
            calls = [c for b in blocks for c in (b.get("result") or {}).get("rlm_calls", [])]
            text = "".join(str((b.get("result") or {}).get(k) or "") for b in blocks
                           for k in ("stdout", "stderr"))
            turns.append({"calls": calls, "loop_error_strings": text.count(LOOP_ERROR)})
    return turns


def load(run: Path, tag: str) -> list[dict]:
    sessions = []
    for udir in sorted((run / "units").glob("nospec_c*_r*")):
        if not (udir / "DONE").exists():
            continue
        rep = re.search(r"_r(\d+)$", udir.name).group(1)
        stats = json.loads((udir / "unit_stats.json").read_text())
        events = [json.loads(x) for x in (udir / "events.jsonl").read_text().splitlines()
                  if x.strip()]
        for row in stats.get("tasks", []):
            tid = row["task_id"]
            trajs = udir / ("rlm_trajs" if (udir / "rlm_trajs").is_dir() else "trajs_compact")
            files = sorted(trajs.glob(f"{tid}_*.jsonl"))
            turns = read_turns(files[-1]) if files else []
            roots = sorted((e for e in events if e.get("kind") == "root_stream"
                            and e.get("task_id") == tid), key=lambda e: e["iteration"])
            shapes = [turn_shape(t["calls"]) for t in turns]
            for i, sh in enumerate(shapes):
                r = roots[i] if i < len(roots) else {}
                sh.update(turn=i + 1, stream_s=r.get("stream_s") or 0.0,
                          after_s=(r.get("shadow_wait_s") or 0.0) + (r.get("exec_s") or 0.0))
            sessions.append({
                "session": f"{tid}.{tag}{rep}", "task_id": tid, "unit": udir.name,
                "status": status_of(row), "error": str(row.get("error") or "")[:120],
                "wall_s": row.get("wall_s"), "score": row.get("score"),
                "turns": len(roots), "recorded_turns": len(turns),
                "stream_s": sum(r.get("stream_s") or 0.0 for r in roots),
                "after_s": sum((r.get("shadow_wait_s") or 0.0) + (r.get("exec_s") or 0.0)
                               for r in roots),
                "cut_replies": sum(1 for r in roots if r.get("truncated")),
                "calls": sum(s["calls"] for s in shapes),
                "singles": sum(s["singles"] for s in shapes),
                "batches": sum(s["batches"] for s in shapes),
                "batch_sizes": [n for s in shapes for n in s["batch_sizes"]],
                "max_calls_in_a_turn": max((s["calls"] for s in shapes), default=0),
                "single_loops": [{"turn": s["turn"], "calls": s["singles"],
                                  "after_s": round(s["after_s"], 1)}
                                 for s in shapes if s["single_loop"]],
                "batch_loops": [{"turn": s["turn"], "batches": s["batches"],
                                 "prompts": sum(s["batch_sizes"]),
                                 "after_s": round(s["after_s"], 1)}
                                for s in shapes if s["batch_loop"]],
                "loop_error_strings": sum(t["loop_error_strings"] for t in turns),
                "shapes": shapes,
            })
    return sessions


def replay_state(s: dict, manifest: dict | None) -> str:
    """Whether a session is replayed, by PREREG_RECORD.md's rules."""
    if s["status"] == "deadline":
        return "no: the deadline stopped it"
    if s["status"] == "failed":
        return f"no: failed ({s['error'].split(':')[0] or 'error'})"
    if s["cut_replies"]:
        return "no: a root reply was cut"
    if manifest is not None:
        row = next((r for r in manifest["sessions"] if r["session"] == s["session"]), None)
        if row is None or not row.get("replayable"):
            why = "; ".join((row or {}).get("problems") or ["not in the corpus"])[:80]
            return f"no: does not reproduce ({why})"
    if s["max_calls_in_a_turn"] <= 1 and s["after_s"] >= LEFT_OUT_AFTER_S:
        return "left out: one sub-call per turn"
    return "yes" if s["status"] == "finished" else f"up to turn {s['recorded_turns']}"


def predictions(sessions: list[dict], probes: list[dict], fix: list[dict]) -> list[dict]:
    out = []

    def add(pid, claim, measured, held):
        out.append({"id": pid, "claim": claim, "measured": measured, "held": held})

    n = len(sessions)
    lost = sum(int((f.get("failed") or {}).get(LOOP_ERROR, 0)) for f in fix)
    seen = sum(s["loop_error_strings"] for s in sessions)
    batched = sum(int(f.get("calls") or 0) for f in fix)
    add("R1", "the fix holds: no batched prompt comes back as `Event loop is closed`",
        f"{lost} of {batched} batched prompts; the string is in the REPL output {seen} times",
        None if not fix else lost == 0 and seen == 0)
    stock = next((p for p in probes if not p["fixed"]), None)
    fixed = next((p for p in probes if p["fixed"]), None)
    add("R2", "the probe: stock rlms loses at least 16 of 80 prompts on this engine; with the "
        "fix, none",
        "-" if not stock or not fixed else
        f"{stock['errors']} of {stock['prompts']} "
        f"({', '.join(str(b['errors']) for b in stock['batches'])} by batch); "
        f"{fixed['errors']} of {fixed['prompts']}",
        None if not stock or not fixed else stock["errors"] >= 16 and fixed["errors"] == 0)
    single = [s for s in sessions if s["single_loops"]]
    add("R3", "loops of single calls: 1 to 5 of the 16 sessions have one",
        f"{len(single)} of {n}", 1 <= len(single) <= 5)
    batch = [s for s in sessions if s["batch_loops"]]
    add("R4", "loops of batches: at least 5 of the 16 sessions have one",
        f"{len(batch)} of {n}", len(batch) >= 5)
    failed = [s for s in sessions if s["status"] != "finished"]
    add("R5", "at most 4 of the 16 sessions fail",
        f"{len(failed)} of {n}" + (f" ({dict(Counter(s['status'] for s in failed))})"
                                   if failed else ""), len(failed) <= 4)
    stopped = [s for s in sessions if s["status"] in ("timeout", "deadline")]
    with_loop = [s for s in stopped if s["single_loops"]]
    add("R6", "of the sessions the timeout or the deadline stops, at least half have a loop "
        "of single calls", "-" if not stopped else f"{len(with_loop)} of {len(stopped)}",
        None if not stopped else 2 * len(with_loop) >= len(stopped))
    return out


def census(run: Path, corpus: Path | None = None, tag: str = "fix") -> dict:
    run = Path(run)
    sessions = load(run, tag)
    manifest = json.loads((Path(corpus) / "manifest.json").read_text()) if corpus else None
    for s in sessions:
        s["replay"] = replay_state(s, manifest)
        if manifest is not None:
            row = next((r for r in manifest["sessions"] if r["session"] == s["session"]), None)
            s["corpus_errors"] = None if row is None else row.get("errors")
    notes = []
    if (run / "campaign.jsonl").exists():
        notes = [json.loads(x) for x in (run / "campaign.jsonl").read_text().splitlines()
                 if x.strip()]
    probes = [n for n in notes if n.get("kind") == "batch_probe"][-2:]
    fix = []
    for udir in sorted((run / "units").glob("nospec_c*_r*")):
        if (udir / "batch_fix.json").exists():
            fix.append({"unit": udir.name, **json.loads((udir / "batch_fix.json").read_text())})
    walls = [s["wall_s"] for s in sessions if s["wall_s"]]
    replayed = [s for s in sessions if s["replay"] == "yes" or s["replay"].startswith("up to")]
    totals = {
        "sessions": len(sessions), "status": dict(Counter(s["status"] for s in sessions)),
        "replayed": len(replayed),
        "left_out": {s["session"]: s["wall_s"] for s in sessions
                     if s["replay"].startswith("left out")},
        "wall_s": sum(walls), "stream_s": sum(s["stream_s"] for s in sessions),
        "after_s": sum(s["after_s"] for s in sessions),
        "calls": sum(s["calls"] for s in sessions),
        "singles": sum(s["singles"] for s in sessions),
        "batches": sum(s["batches"] for s in sessions),
        "sessions_with_no_call": sum(1 for s in sessions if not s["calls"]),
        "single_loop_sessions": sum(1 for s in sessions if s["single_loops"]),
        "batch_loop_sessions": sum(1 for s in sessions if s["batch_loops"]),
        "single_loop_after_s": sum(lp["after_s"] for s in sessions for lp in s["single_loops"]),
        "batch_loop_after_s": sum(lp["after_s"] for s in sessions for lp in s["batch_loops"]),
    }
    return {"run": run.name, "tag": tag, "totals": totals, "sessions": sessions, "probes": probes,
            "batch_fix": fix, "predictions": predictions(sessions, probes, fix)}


def design_of(c: dict) -> dict:
    """The part of a replay design that follows from the census alone (for
    replay_campaign.py --design-file): the sessions PREREG_RECORD.md's rule leaves out, with
    their recorded wall time, and the loops of the sessions that are replayed. What a loop
    of single calls does with its results (`kind`: stores or tests) is read from its code
    and filled in by hand, as are sessions dropped for the budget and numeric checks."""
    replayed = [s for s in c["sessions"] if s["replay"] == "yes" or s["replay"].startswith("up to")]
    return {"name": c["tag"], "run": c["run"],
            "sessions": [s["session"] for s in replayed],
            "left_out": dict(c["totals"]["left_out"]), "dropped": {},
            "single_loops": [{"session": s["session"], "turn": lp["turn"], "calls": lp["calls"],
                              "kind": "?"} for s in replayed for lp in s["single_loops"]],
            "batch_loops": [{"session": s["session"], "turn": lp["turn"],
                             "batches": lp["batches"], "prompts": lp["prompts"]}
                            for s in replayed for lp in s["batch_loops"]],
            "checks": []}


def render(c: dict) -> str:
    t = c["totals"]
    out = [f"# What the recording's sessions wrote: {c['run']} (measured)", "",
           "`nospec`, rlms' batch path fixed (cloud/PREREG_RECORD.md). A single call is a "
           "sub-call recorded alone; a batch is one `llm_query_batched`. A loop of single calls "
           f"is a turn with at least {SINGLE_LOOP_MIN} of them, a loop of batches a turn with "
           f"at least {BATCH_LOOP_MIN} batches. After-stream seconds: from the end of each "
           "root stream until that turn's code has run.", "",
           f"- **{t['sessions']} sessions:** " + ", ".join(
               f"{n} {k}" for k, n in sorted(t["status"].items())) + ".",
           f"- **{t['single_loop_sessions']} with a loop of single calls** "
           f"({t['single_loop_after_s']:.0f} s after the streams in those turns), "
           f"**{t['batch_loop_sessions']} with a loop of batches** "
           f"({t['batch_loop_after_s']:.0f} s), {t['sessions_with_no_call']} with no sub-call.",
           f"- **{t['calls']} sub-calls recorded:** {t['singles']} single calls and "
           f"{t['batches']} batches.",
           f"- **Time:** {t['wall_s']:.0f} s of sessions, {t['stream_s']:.0f} s of root streams, "
           f"{t['after_s']:.0f} s after them.",
           f"- **Replayed:** {t['replayed']} sessions."
           + (f" Left out by the rule: {', '.join(sorted(t['left_out']))}." if t["left_out"]
              else "")]
    mark = {True: "held", False: "**did not hold**", None: "not testable"}
    out += ["", "## The predictions (cloud/PREREG_RECORD.md, fixed before the recording)", "",
            "| | prediction | measured | |", "|---|---|---|---|"]
    out += [f"| {p['id']} | {p['claim']} | {p['measured']} | {mark[p['held']]} |"
            for p in c["predictions"]]
    out += ["", "## Sessions", "",
            "| session | status | wall s | turns | root streams s | after-stream s | sub-calls "
            "| single calls | batches (median size) | loops of single calls: turn (calls, s) "
            "| loops of batches: turn (batches, prompts, s) | most calls in a turn | replayed |",
            "|" + "---|" * 13]
    for s in c["sessions"]:
        med = statistics.median(s["batch_sizes"]) if s["batch_sizes"] else None
        sl = "; ".join(f"{lp['turn']} ({lp['calls']}, {lp['after_s']:.0f})"
                       for lp in s["single_loops"]) or "-"
        bl = "; ".join(f"{lp['turn']} ({lp['batches']}, {lp['prompts']}, {lp['after_s']:.0f})"
                       for lp in s["batch_loops"]) or "-"
        out.append(f"| {s['session']} | {s['status']} | {_f(s['wall_s'])} | {s['turns']} "
                   f"| {_f(s['stream_s'])} | {_f(s['after_s'])} | {s['calls']} | {s['singles']} "
                   f"| {s['batches']} ({_f(med, 0)}) | {sl} | {bl} "
                   f"| {s['max_calls_in_a_turn']} | {s['replay']} |")
    if c["probes"]:
        out += ["", "## The probe before the first unit", "",
                "Batches of 20 prompts through rlms' own path; the last one after 6 s without "
                "a request.", "", "| rlms | prompts lost, by batch | of |", "|---|---|---|"]
        for p in c["probes"]:
            out.append(f"| {'with the fix' if p['fixed'] else 'stock 0.1.3'} "
                       f"| {', '.join(str(b['errors']) for b in p['batches'])} "
                       f"| {p['errors']} of {p['prompts']} |")
    if c["batch_fix"]:
        out += ["", "## Batched prompts, by unit", "",
                "| unit | sent through the fix | failed, by cause | tasks the deadline stopped |",
                "|---|---|---|---|"]
        for f in c["batch_fix"]:
            failed = ", ".join(f"{n} {k}" for k, n in sorted((f.get("failed") or {}).items()))
            out.append(f"| {f['unit']} | {f.get('calls')} | {failed or 'none'} "
                       f"| {', '.join(f.get('deadline_tasks') or []) or 'none'} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("--corpus", type=Path, default=None,
                    help="the corpus built from this run (its manifest says what reproduces)")
    ap.add_argument("--tag", default="fix")
    ap.add_argument("--design-out", type=Path, default=None,
                    help="write the start of a replay design here (see design_of)")
    a = ap.parse_args(argv)
    c = census(a.run, a.corpus, a.tag)
    if a.design_out:
        a.design_out.write_text(json.dumps(design_of(c), indent=1) + "\n")
    md = render(c)
    (a.run / "census.md").write_text(md)
    for s in c["sessions"]:
        s.pop("shapes", None)  # per turn detail stays out of the file; the table has the loops
    (a.run / "census.json").write_text(json.dumps(c, indent=1, default=str))
    print(md)


if __name__ == "__main__":
    main()
