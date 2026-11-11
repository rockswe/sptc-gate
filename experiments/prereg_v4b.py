"""Addendum to results/prereg_v4 for step 5 of the pressure run, written before any GPU run of
it: the `both` workload on the default servers (kaggle/vllm_bench.py preset both_default),
where the window cap and the plugin meet bets that are often needed, without KV pressure.
The simulated study predicted a 47% effect there (results/pressure, '`both` without pressure'), over
the 5% set for running the step.

The arms are the pressure arms on the default servers: fcfs-d/X is fcfs-p/X on the default
config (the T4's 85,904 KV tokens, 256 sequences). Their rows are results/pressure's
default-config rows: simulated again here for prereg_v4's three calibration sets (P1, P0,
P1-alt), with P1 checked against results/pressure/grid.json. prereg_v4 is not edited; its
files are checked against their prereg commit 4d87117. Claims in v4's format, scored by
experiments/prereg_compare.py (--also results/prereg_v4b).

  PYTHONPATH=. .venv/bin/python experiments/prereg_v4b.py [--out results/prereg_v4b]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

import pressure as PR
import prereg_compare as PC
import prereg_v2 as P2
import prereg_v4 as V4
from prereg_v2 import vb

ROOT = P2.ROOT
OUT = ROOT / "results" / "prereg_v4b"
GRID = ROOT / "results" / "pressure" / "grid.json"
N = PR.AGENTS
REF = vb.BOTH_DEFAULT_REF
METRICS = ("session_p50", "root_tpot_p50", "root_tpot_p99")
GATED = ["cap-d/both", "plugin-d/both"]

FOUND = [
    "**spec-ptc bets again on a call whose bet failed.** Seen while testing the bench on "
    "the fake server (kaggle/fake_openai_server.py), after prereg_v4 and before any GPU "
    "run. A speculation that raised SpeculationRejected is invisible to spec-ptc's store "
    "(SpecStore.existing), so the shadow peeks the call again and then dispatches it from "
    "its statement. In one traced map16 turn behind the window cap (1 agent), 16 calls got "
    "32 bets (29 refused), and the 13 calls whose bets were all refused ran for real at "
    "their claim. The simulator sends one bet per "
    "call. So where bets are refused (the cap and the plugin in `both`), the T4 arms send "
    "more bets, and more decoys (one per bet), than simulated. This bears on v4's PR-13..16, "
    "PC-3/4, PP-2 and PF-3/4, and here on every claim with cap-d/both or plugin-d/both. "
    "The predictions stay as simulated; the bench reports bets per call (sweep/summary.md, "
    "Pressure table): read those claims next to it.",
]

READING = [
    "**Not part of the decision rule.** Step 5 has no KV pressure, and the rule needs "
    "the pressure check. It shows what a fixed window of 8 costs when half the bets are "
    "needed: on stock FCFS nothing is refused, so fcfs-d/spec+bad is `both` with every bet "
    "admitted, and fcfs-d/spec sends only the needed bets (the oracle).",
    "**Why cap and plugin lose here** (v4's reading rule, unchanged): in mix4 the shadow "
    "forces nearly every speculation, and spec-ptc's shadow stops for the rest of the turn "
    "when it forces a refused bet. The window of 8 refuses most real bets at 4 agents, so "
    "these arms run close to no speculation (fcfs-d/nospec).",
    "**Pooled p50s sit on pattern clusters** (v4's): read every session_p50 claim with "
    "prereg_compare.py's per-pattern ratios.",
]


def check_v4() -> dict:
    """prereg_v4's files against the sha256 of their prereg commit (prereg_compare's table)."""
    got = {}
    for v in ("prereg_v4", "prereg_v4_fallback"):
        for k, want in PC.PREREG_SHA256[v].items():
            have = hashlib.sha256((ROOT / "results" / v / k).read_bytes()).hexdigest()
            got[f"{v}/{k}"] = "match" if have == want else "MISMATCH"
    if "MISMATCH" in got.values():
        raise SystemExit(f"results/prereg_v4 does not match its prereg commit: {got}")
    return got


def pressure_arm(name: str) -> str:
    return name.replace("-d/", "-p/")


def simulate(m: dict) -> dict:
    """Every step-5 arm on the default config: {name: point}, records renamed."""
    pts = {}
    for name in vb.BOTH_DEFAULT_ARMS:
        p = PR.simulate(m, pressure_arm(name), PR.DEFAULT)
        p["_rec"] = {**p["_rec"], "arm": name, "server": vb.ARM[name].server}
        pts[name] = p
    return pts


def check_grid(pts: dict) -> dict:
    """P1's points against results/pressure/grid.json's default-config rows: equal."""
    grid = json.loads(GRID.read_text())["points"]
    out = {}
    for name, p in pts.items():
        g = grid[f"{PR.key(PR.DEFAULT)}|{pressure_arm(name)}"]
        keys = ("session_p50", "session_p99", "root_tpot_p50", "root_tpot_p99",
                "decoys_refused", "real_bets_refused", "shadow_stops")
        out[name] = "equal" if all(p[k] == g[k] for k in keys) else "DIFFERENT"
    if "DIFFERENT" in out.values():
        raise SystemExit(f"P1 differs from results/pressure's default rows: {out}")
    return out


def claims(rows: dict, dec: dict) -> list[dict]:
    c = P2.ratio_claims(rows, "DB", "each arm vs fcfs-d/spec+bad (default servers)",
                        [(a, REF, N) for a in vb.BOTH_DEFAULT_ARMS if a != REF],
                        ("session_p50", "root_tpot_p50"))
    c += P2.ratio_claims(rows, "DC", "plugin vs the client-side cap, default servers",
                         [("plugin-d/both", "cap-d/both", N)], ("session_p50", "root_tpot_p50"))
    c += P2.ratio_claims(rows, "DP", "plugin vs vLLM priority, default servers",
                         [("plugin-d/both", "prio-d/both", N)], ("session_p50",))
    for arm in GATED:
        if (arm, N) in dec:
            c.append({"id": "DF", "section": "decoys rejected", "kind": "fraction", "arm": arm,
                      "agents": N, "outcome": "rejected", "predicted": dec[(arm, N)],
                      "tol": P2.FRAC_TOL})
    seen: dict[str, int] = {}
    for x in c:
        seen[x["id"]] = seen.get(x["id"], 0) + 1
        x["id"] = f"{x['id']}-{seen[x['id']]}"
    return c


def gpu_minutes(summary: dict) -> dict:
    """vllm_bench.plan for preset both_default, session times from P1."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "predictions.json"
        f.write_text(json.dumps({"summary": summary}, default=str))
        ns = argparse.Namespace(preset="both_default", arms=None, agents=None, reps=None,
                                turns=None, rounds=None, warm_pass=False, predictions=str(f))
        return {k: v for k, v in vb.plan(ns).items() if k != "rows"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    v4_files = check_v4()
    v4 = json.loads((ROOT / "results" / "prereg_v4" / "predictions.json").read_text())
    git = P2.git_state()
    git["dirty_files"] = [x for x in git["dirty_files"] if "results/prereg_v4b" not in x]
    sets, grid_check = {}, None
    for name, m in V4.models().items():
        pts = simulate(m)
        if name == "P1":
            grid_check = check_grid(pts)
        runs = [p["_rec"] for p in pts.values()]
        summ = vb.summarize(runs, boot=0)
        rows = {(r["arm"], r["agents"]): r for r in summ["rows"]}
        dec = P2.decoy_rejected(runs)
        sets[name] = {"seq_cap": m["seq_cap"], "summary": summ, "claims": claims(rows, dec),
                      "decoy_rejected": [{"arm": k[0], "agents": k[1], "frac": v}
                                         for k, v in sorted(dec.items())],
                      "pressure": [{"arm": x, "agents": N, **{k: p[k] for k in V4.PRESSURE_KEYS}}
                                   for x, p in pts.items()]}
        print(f"{name:6s}: " + ", ".join(f"{x} {p['session_p50']:.2f}" for x, p in pts.items()),
              flush=True)
    res = {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": "PREDICTED by the simulator before any GPU run of the both_default preset "
                 "(addendum to prereg_v4: step 5 of the pressure run)",
        "version": "v4b",
        "code": {**git, "script": "experiments/prereg_v4b.py"},
        "primary": "P1",
        "based_on": {"prereg_v4_commit": "4d87117", "prereg_v4_files": v4_files,
                     "prereg_v4_stamp": v4["stamp_utc"], "grid": str(GRID.relative_to(ROOT)),
                     "grid_check_P1": grid_check},
        "config": {**PR.DEFAULT, "server": "default (vllm_bench SERVERS fcfs, priority, plugin)"},
        "arms": {n: {"server": x.server, "mode": x.mode, "decoys": x.decoys, "tags": x.tags,
                     "gate": x.gate or None, "spec_kind": x.spec_kind,
                     "simulated_as": pressure_arm(n)}
                 for n, x in ((n, vb.ARM[n]) for n in vb.BOTH_DEFAULT_ARMS)},
        "sets": sets,
        "summary": sets["P1"]["summary"],
        "overhead": [],
        "general": {"claims": [], "quick_claims": []},
        "rules": {k: v4["rules"][k] for k in ("validity", "ratio", "fraction", "points")}
        | {"step5": "Claims DB, DC, DP use v3's ratio rule and DF v3's fraction rule. The "
                    f"denominators are {REF} (DB), cap-d/both (DC) and prio-d/both (DP), all "
                    f"at {N} agents on the default servers' launches."},
        "found_after_v4": FOUND,
        "reading_rules": READING,
    }
    res["gpu_minutes"] = gpu_minutes(res["summary"])
    res["wall_s"] = time.time() - t0
    (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "predictions.md").write_text(markdown(res))
    print(f"wrote {out}", flush=True)


def markdown(res: dict) -> str:
    p1 = res["sets"]["P1"]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    p0 = {(r["arm"], r["agents"]): r for r in res["sets"]["P0"]["summary"]["rows"]}
    pres = {x["arm"]: x for x in p1["pressure"]}
    ref = rows[(REF, N)]
    L = ["# Pre-registered predictions, addendum v4b: `both` on the default servers", "",
         f"**PREDICTED by the simulator, not measured.** Written {res['stamp_utc']} by "
         "`experiments/prereg_v4b.py`, before any GPU run of the `both_default` preset "
         "(step 5 of the pressure run). Not edited after the run; `experiments/prereg_compare.py "
         "--prereg results/prereg_v4 --also results/prereg_v4b` scores it next to v4.", "",
         f"- Code: commit `{res['code']['commit']}`"
         + (" (clean tree)" if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}") + ".",
         f"- Based on `results/prereg_v4` (prereg commit 4d87117, written "
         f"{res['based_on']['prereg_v4_stamp']}), whose files match that commit's sha256: "
         f"{res['based_on']['prereg_v4_files']}. Nothing in prereg_v4 changes.",
         "- The rows are `results/pressure`'s default-config rows: each arm is the pressure "
         "arm of the same name (fcfs-d/X is fcfs-p/X) on the default config, simulated for "
         "v4's three sets; P1 equals `results/pressure/grid.json` "
         f"({res['based_on']['grid_check_P1']}). Nothing fit.", "",
         "## Arms (preset `both_default`, 4 agents, 3 repeats, 2 launches per server)", "",
         "| arm | server | tags | client cap | speculative calls | simulated as |",
         "|---|---|---|---|---|---|"]
    for n, x in res["arms"].items():
        L.append(f"| {n} | {x['server']} | {x['tags']} | {x['gate'] or '-'} | "
                 f"{'bets' if x['spec_kind'] == 'bet' else 'early (untagged)'} | "
                 f"{x['simulated_as']}, default config |")
    L += ["", "## Found after prereg_v4, before any GPU run", ""]
    L += [f"- {x}" for x in res["found_after_v4"]]
    L += ["", "## Rows (P1; P0 in brackets)", "",
          f"| arm | session p50 s | vs {REF} | root TPOT p50 ms | decoys rejected | real bets "
          "refused | shadow stops | preemptions | KV peak blocks |",
          "|---|---|---|---|---|---|---|---|---|"]
    for a in vb.BOTH_DEFAULT_ARMS:
        r, q, x = rows[(a, N)], p0[(a, N)], pres[a]
        L.append(f"| {a} | {r['session_p50']:.2f} [{q['session_p50']:.2f}] | "
                 f"{r['session_p50'] / ref['session_p50']:.3f} | {r['root_tpot_p50']:.1f} "
                 f"[{q['root_tpot_p50']:.1f}] | {vb._fmt(x['decoys_refused'])} | "
                 f"{vb._fmt(x['real_bets_refused'])} | {x['shadow_stops']} | "
                 f"{x['preemptions']:.0f} | {x['max_kv_blocks']} |")
    L += ["", "## Claims (P1 predicted; P0, P1-alt in brackets)", "",
          "| id | section | claim | predicted | tol |", "|---|---|---|---|---|"]
    alts = {k: {x["id"]: x["predicted"] for x in st["claims"]}
            for k, st in res["sets"].items() if k != "P1"}
    for x in p1["claims"]:
        alt = ", ".join(f"{alts[k][x['id']]:.3f}" for k in alts)
        what = (f"{x['numerator'][0]} / {x['denominator'][0]} at {x['numerator'][1]}: "
                f"{x['metric']}" if x["kind"] == "ratio" else
                f"{x['arm']} at {x['agents']}: share of decoys rejected")
        L.append(f"| {x['id']} | {x['section']} | {what} | {x['predicted']:.3f} [{alt}] | "
                 f"{x['tol']} |")
    L += ["", "## Rules (v4's, unchanged)", ""]
    L += [f"- **{k}.** {v}" for k, v in res["rules"].items()]
    L += ["", "## How to read these (fixed before the run)", ""]
    L += [f"- {x}" for x in res["reading_rules"]]
    g = res["gpu_minutes"]
    L += ["", "## GPU time (estimate)", "",
          f"Preset `both_default`: {g['runs']} runs on {g['launches']} launches (plus up to "
          f"{g['cache_fill_launches_max']} cache-filling), about {g['est_minutes']} min with "
          "`vllm_bench.plan`'s constants and P1's session times.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
