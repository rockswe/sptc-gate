"""Score a measured Kaggle run against the pre-registered predictions: results/prereg_v3
(primary), results/prereg_v3b (its addendum for section B4) and results/prereg_v2 (also
reported, scored by the same code).

  python experiments/prereg_compare.py --out MEASURED_DIR [--prereg results/prereg_v3]
                                       [--also results/prereg_v3b,results/prereg_v2]

MEASURED_DIR is the notebook's output (kaggle/sptc_kaggle_v3.ipynb, or _v2):
  sweep/runs/*.json      vllm_bench.py sweep (presets ab, ab_eager, prio8, baselines, core,
                         full)
  sweep/launches.jsonl   one line per server launch (compile state, plugin log line)
  overhead/overhead_vllm.json            overhead_bench.py vllm
  general_full/general*.json, general_quick/general*.json   bench_general.py matrix
Anything missing is reported as not run. Writes MEASURED_DIR/prereg_compare.{md,json}.
Standard library only, plus kaggle/vllm_bench.py (summaries are computed by the same code
for predicted and measured runs). The verdicts follow the rules in the predictions file.
The pressure run (kaggle/sptc_kaggle_v4.ipynb) is scored with --prereg
results/prereg_v4 (or results/prereg_v4_fallback if its probe switched to the fallback
config) --also results/prereg_v4b (its step 5, the both_default preset).

Added after the pre-registration, before any run, and reported apart from the verdicts:
- the sha256 of the prediction files against the values pinned below. The pins are of
  the published files: their wording was edited after the runs, the predictions were not;
- a work check per ratio claim (added with v3b, reported, not a verdict): sub-call
  completion tokens per session, numerator over denominator. Sub-calls stop at EOS, so
  arms meant to run the same workload can differ; away from 1, read the claim as
  confounded;
- a strict verdict per ratio claim: the 95% CI of the ratio, resampling server launches,
  then runs, then sessions, must lie inside predicted +- tol (supported) or outside it
  (refuted), with at least 2 launches on each side; else unresolved. The pre-registered
  rule calls a ratio supported on its point estimate alone, which is weak evidence of "no
  gap" with 3 repeats on 2 launches;
- per-pattern ratios (median session wall per pattern, geometric mean over patterns): the
  paired quantity, as the pooled p50 jumps between pattern clusters;
- the priority claims against stock launched next to priority (fcfs-adj/*, prio8).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kaggle"))

import vllm_bench as vb  # noqa: E402

# sha256 of the prediction files as published (wording edited after the runs, predictions
# unchanged); checked, not trusted
PREREG_SHA256 = {
    "prereg_v2": {
        "predictions.json": "3d46c4ed69497c8d50f3fa4d087ba3920190333ff737d244e06e967f10c5c559",
        "predictions.md": "4a6ac0054611ef418e081fe29f951a9572edc47db92775edb5d71fd088d0a3d2",
        "general_predictions.json":
            "712d94c1c194ddde4aaf1cb3dc5ad470cce3ecd4e2aac42a3f9bc11d35646d58",
    },
    "prereg_v3": {
        "predictions.json": "32a4bffaff25188aa69959eb603fef33f99d3c77d9ec4d13df5f9297fd47e2ff",
        "predictions.md": "9ed1ae8db80fef087f219cc39fa82fbb167e3a374488ce1bcd7372f5ca19b122",
        "general_predictions.json":
            "a0d44b229594363bfb671ad682803815aa28c0abc4d2676615e6aad71376d32d",
    },
    "prereg_v3b": {
        "predictions.json": "aa53d2a55e66554353b878b9d10aee7ccbb2c2812c70da30b613932abcf4761d",
        "predictions.md": "9d2af079ec546e964c78a17b649bc45673449ba54634cafb9704d33ad8c91107",
    },
    "prereg_v4": {
        "predictions.json": "0e33be8400629800caa433937b4ff4e926cfeeeda2ff346636147b233b723f2c",
        "predictions.md": "a69beab2fc4507a2a8087c62461a994454c7c181eefd2a7db834a151ceb34f01",
    },
    "prereg_v4_fallback": {
        "predictions.json": "b73d10516b946b22f99f2111486dcda1c22f0caaecd9625abe9a5a073c062159",
        "predictions.md": "33ef1a8879505b27d457f3772883ad9c0fbdb174862086bb3f316cb45d334fdc",
    },
    "prereg_v4b": {
        "predictions.json": "8c902ab185bd97fcb4572574cee5ee00ae3bb03a1b0339e152f516a10df92a74",
        "predictions.md": "a4dd5d286a254785cbcdeb29ae7a4ba4681610d03dbab659970251a02a4764a8",
    },
}
IN_SAMPLE_ARMS = {"fcfs/nospec", "fcfs/spec", "fcfs/spec+bad", "plugin/nospec", "plugin/spec",
                  "plugin/spec+bad"}  # the October 19 rows' arms: P1's seq_cap was fit there


# ----------------------------------------------------------------------------- validity
def validity(row: dict | None) -> str:
    """ok | unchecked (no host CPU data) | missing | invalid: <why>."""
    if row is None or not row.get("reps_ok"):
        return "missing"
    if row.get("reps_other"):
        return f"invalid: runs {dict(row['reps_other'])}"
    if row.get("cpu_ok") is False:
        return "invalid: host CPU saturated"
    return "unchecked" if row.get("cpu_ok") is None else "ok"


def _overlap(a, b) -> bool:
    return a is not None and b is not None and a[0] <= b[1] and b[0] <= a[1]


# ----------------------------------------------------------------------------- claims
def check_ratio(c: dict, rows: dict) -> dict:
    num, den = rows.get(tuple(c["numerator"])), rows.get(tuple(c["denominator"]))
    v = [validity(num), validity(den)]
    out = {"validity": v}
    if "missing" in v:
        return {**out, "verdict": "not run"}
    if any(x.startswith("invalid") for x in v):
        return {**out, "verdict": "invalid"}
    m = c["metric"]
    if num.get(m) is None or not den.get(m):
        return {**out, "verdict": "not run"}
    out["work"] = vb._ratio(num.get("sub_tokens_per_session"), den.get("sub_tokens_per_session"))
    meas = num[m] / den[m]
    p = c["predicted"]
    out["measured"] = meas
    if abs(meas - p) <= c["tol"]:
        return {**out, "verdict": "supported"}
    ci_n = (num.get("ci") or {}).get(m)
    ci_d = (den.get("ci") or {}).get(m)
    scaled = [p * ci_d[0], p * ci_d[1]] if ci_d else None
    if ci_n is not None and scaled is not None and not _overlap(ci_n, scaled):
        return {**out, "verdict": "refuted"}
    return {**out, "verdict": "unresolved"}


# ----------------------------------------------------------------------------- secondary
SESSION_KEY = {"session_p50": "wall_s", "root_tpot_p50": "root_tpot_ms"}


def by_launch_values(runs: list[dict], key: str) -> list[list[list[float]]]:
    """One cell's values: per server launch, per run, per session."""
    by: dict = {}
    for r in runs:
        g = [s[key] for s in r["sessions"] if s.get(key) is not None]
        if g:
            by.setdefault(r.get("launch") or "-", []).append(g)
    return list(by.values())


def boot_ratio(num: list, den: list, b: int = 1000, seed: int = 0, level: float = 0.95):
    """CI of p50(num) / p50(den), each side resampled in three levels (launches, runs in a
    launch, sessions in a run), the two sides independently. With one launch on a side its
    launch-to-launch spread is unknown and not in the CI."""
    if not num or not den:
        return None
    rng = random.Random(seed)

    def draw(cl):
        pool = []
        for _ in cl:
            launch = cl[rng.randrange(len(cl))]
            for _ in launch:
                g = launch[rng.randrange(len(launch))]
                pool += [g[rng.randrange(len(g))] for _ in g]
        return vb.pctl(pool, 0.5)

    vals = []
    for _ in range(b):
        x, y = draw(num), draw(den)
        if x is not None and y:
            vals.append(x / y)
    if not vals:
        return None
    vals.sort()
    return [vals[int((1 - level) / 2 * (len(vals) - 1))],
            vals[int((1 + level) / 2 * (len(vals) - 1))]]


def strict(c: dict, cells: dict, num_arm: str | None = None, den_arm: str | None = None,
           boot: int = 1000) -> dict:
    """The strict verdict of a ratio claim (module docstring)."""
    key = SESSION_KEY.get(c["metric"])
    na, nn = num_arm or c["numerator"][0], c["numerator"][1]
    da, dn = den_arm or c["denominator"][0], c["denominator"][1]
    num = by_launch_values(cells.get((na, nn), []), key) if key else []
    den = by_launch_values(cells.get((da, dn), []), key) if key else []
    out = {"launches": [len(num), len(den)]}
    ci = boot_ratio(num, den, boot)
    if ci is None:
        return {**out, "ci": None, "verdict": "not run"}
    lo, hi = c["predicted"] - c["tol"], c["predicted"] + c["tol"]
    out["ci"] = ci
    if min(len(num), len(den)) < 2:
        return {**out, "verdict": "unresolved"}
    if lo <= ci[0] and ci[1] <= hi:
        return {**out, "verdict": "supported"}
    if ci[1] < lo or ci[0] > hi:
        return {**out, "verdict": "refuted"}
    return {**out, "verdict": "unresolved"}


def pattern_ratios(c: dict, cells: dict) -> dict | None:
    """Per pattern: median session wall of the numerator over the denominator's (same
    pattern, so the same deterministic workload), and their geometric mean."""
    if c["metric"] != "session_p50":
        return None

    def med(arm, n):
        by: dict = {}
        for r in cells.get((arm, n), []):
            for s in r["sessions"]:
                by.setdefault(s.get("pattern"), []).append(s["wall_s"])
        return {k: statistics.median(v) for k, v in by.items()}

    a, b = med(*c["numerator"]), med(*c["denominator"])
    r = {k: a[k] / b[k] for k in sorted(set(a) & set(b), key=str) if b[k]}
    if not r:
        return None
    return {"per_pattern": r, "gmean": math.exp(statistics.mean(math.log(x) for x in r.values()))}


def adjacent(c: dict, rows: dict, cells: dict, boot: int) -> dict | None:
    """A priority claim against stock launched next to priority (prio8's fcfs-adj arms)."""
    num, den = c["numerator"][0], c["denominator"][0]
    if not (num.startswith("prio/") and den.startswith("fcfs/")):
        return None
    adj = "fcfs-adj/" + den.split("/", 1)[1]
    v = check_ratio({**c, "denominator": [adj, c["denominator"][1]]}, rows)
    return {"denominator": adj, "measured": v.get("measured"), "verdict": v["verdict"],
            "strict": strict(c, cells, den_arm=adj, boot=boot)}


def prereg_files(pre: Path, version: str | None = None) -> dict:
    """sha256 of each prediction file against its pinned value; version: a key of
    PREREG_SHA256 (default: the directory's name)."""
    table = PREREG_SHA256.get(version or pre.name)
    if table is None:
        return {"(all)": f"unknown version {version or pre.name}"}
    out = {}
    for name, want in table.items():
        f = pre / name
        out[name] = ("missing" if not f.exists() else "match"
                     if hashlib.sha256(f.read_bytes()).hexdigest() == want else "MISMATCH")
    return out


def check_fraction(c: dict, rows: dict) -> dict:
    row = rows.get((c["arm"], c["agents"]))
    v = validity(row)
    if v == "missing":
        return {"validity": [v], "verdict": "not run"}
    if v.startswith("invalid"):
        return {"validity": [v], "verdict": "invalid"}
    dec = row.get("decoy_outcomes") or {}
    n = sum(dec.values())
    if not n:
        return {"validity": [v], "verdict": "not run"}
    meas = dec.get(c["outcome"], 0) / n
    return {"validity": [v], "measured": meas,
            "verdict": "supported" if abs(meas - c["predicted"]) <= c["tol"] else "refuted"}


def check_threshold(c: dict, rows: dict, derived: dict) -> dict:
    ladder = c["ladder"]
    key, arm = c["key"], c["arm"]
    if key == "net_loss":
        arms = [f"{arm}/spec+bad", f"{arm}/nospec"]
    else:
        arms = [arm] + ([vb.stock_of(arm)] if key == "knee_ref" else [])
    loads = [sorted(n for (a, n), r in rows.items() if a == x and validity(r) in ("ok", "unchecked"))
             for x in arms]
    if not all(loads):
        return {"verdict": "not run"}
    measured_top = min(max(x) for x in loads)
    q = derived.get(key, {}).get(arm)
    p = c["predicted"]
    out = {"measured": q, "measured_top": measured_top}

    def idx(n):
        return ladder.index(n) if n in ladder else None

    if p is not None and q is not None:
        ok = idx(p) is not None and idx(q) is not None and abs(idx(p) - idx(q)) <= 1
        return {**out, "verdict": "supported" if ok else "refuted"}
    if p is None and q is None:
        return {**out, "verdict": "supported" if measured_top >= ladder[-1] else "unchecked"}
    if p is None:  # predicted above the ladder, measured inside it
        return {**out, "verdict": "refuted"}
    # predicted inside the ladder, not reached: wrong once the step after p was measured
    nxt = ladder[min(len(ladder) - 1, idx(p) + 1)] if idx(p) is not None else p
    return {**out, "verdict": "refuted" if measured_top >= nxt else "unchecked"}


def check_overhead(bounds: list[dict], res: dict | None) -> list[dict]:
    if res is None:
        return [{**b, "verdict": "not run"} for b in bounds]
    stock = {(r["scheduling"], r["n_running"]): r["total_p50_us"] for r in res["rows"]
             if r["variant"] == "stock"}
    out = []
    for b in bounds:
        for sched in ("sync", "async"):
            r = next((r for r in res["rows"] if r["variant"] == b["variant"]
                      and r["n_running"] == b["n_running"] and r["scheduling"] == sched), None)
            if r is None or (sched, b["n_running"]) not in stock:
                out.append({**b, "scheduling": sched, "verdict": "not run"})
                continue
            added = r["total_p50_us"] - stock[(sched, b["n_running"])]
            out.append({**b, "scheduling": sched, "added_us": added,
                        "verdict": "supported" if added <= b["bound_added_us"] else "refuted"})
    return out


def general_rows(out: Path) -> tuple[list[dict], str | None]:
    """Measured bench_general cells: those of the full matrix (finished or partial), and
    the quick matrix's for cells the full one has not reached (same cells, same keys)."""
    rows: dict = {}
    src = []
    for d in ("general_quick", "general_full"):  # full last: it wins where both ran
        for name in ("general.json", "general_partial.json"):
            f = out / d / name
            if f.exists():
                for r in json.loads(f.read_text())["react"]:
                    rows[(r["arm"], r["mode"], r["agents"], r["batch_workers"])] = r
                src.append(str(f.relative_to(out)))
                break
    return list(rows.values()), (" + ".join(src) or None)


def check_general(claims: list[dict], rows: list[dict]) -> list[dict]:
    """One run per cell and one launch per arm: verdicts are single-run and indicative.
    A cell whose host CPU was saturated (cpu_ok false) makes the claim invalid."""
    by = {(r["arm"], r["mode"], r["agents"], r["batch_workers"]): r for r in rows}
    out = []
    for c in claims:
        a, b = by.get(tuple(c["numerator"])), by.get(tuple(c["denominator"]))
        if a is None or b is None or not b.get(c["metric"]):
            out.append({**c, "verdict": "not run"})
            continue
        if a.get("cpu_ok") is False or b.get("cpu_ok") is False:
            out.append({**c, "verdict": "invalid"})
            continue
        m = a[c["metric"]] / b[c["metric"]]
        lo, hi = c["bound"]
        ok = (lo is None or m >= lo) and (hi is None or m <= hi)
        out.append({**c, "measured_ratio": m, "verdict": "supported" if ok else "refuted",
                    "cpu_checked": a.get("cpu_ok") is not None and b.get("cpu_ok") is not None})
    return out


# ----------------------------------------------------------------------------- points
def point_errors(pred_sets: dict, rows: dict) -> dict:
    """|log(pred / meas)| per (arm, load) and metric, per set; eager arms excluded."""
    res = {}
    for key, st in pred_sets.items():
        pred = {(r["arm"], r["agents"]): r for r in st["summary"]["rows"]}
        pts = []
        for k, m in rows.items():
            p = pred.get(k)
            if p is None or validity(m) not in ("ok", "unchecked"):
                continue
            e = {"arm": k[0], "agents": k[1],
                 "in_sample": key != "P0" and k[0] in IN_SAMPLE_ARMS and k[1] in (1, 4, 8)}
            for metric in ("session_p50", "root_tpot_p50"):
                if p.get(metric) and m.get(metric):
                    e[metric] = {"pred": p[metric], "meas": m[metric],
                                 "abs_log_err": abs(math.log(p[metric] / m[metric]))}
            pts.append(e)
        agg = {}
        for part in ("in_sample", "out_of_sample"):
            sel = [e for e in pts if e["in_sample"] == (part == "in_sample")]
            for metric in ("session_p50", "root_tpot_p50"):
                errs = [e[metric]["abs_log_err"] for e in sel if metric in e]
                agg[f"{part}/{metric}"] = ({"n": len(errs), "median": statistics.median(errs),
                                           "max": max(errs)} if errs else None)
        res[key] = {"points": pts, "summary": agg}
    return res


def launch_noise(summ: dict) -> list[dict]:
    """Per arm and load with >= 2 launches: session p50 of each launch, and the spread."""
    by: dict = {}
    for r in summ.get("by_launch", []):
        by.setdefault((r["arm"], r["agents"]), []).append(r)
    out = []
    for (arm, n), rs in sorted(by.items()):
        vals = [r["session_p50"] for r in rs if r["session_p50"]]
        if len(vals) >= 2:
            out.append({"arm": arm, "agents": n, "launches": [r["launch"] for r in rs],
                        "session_p50": vals, "spread": max(vals) / min(vals) - 1})
    return out


# ----------------------------------------------------------------------------- report
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="the measured run's output directory")
    ap.add_argument("--prereg", default=str(ROOT / "results" / "prereg_v3"),
                    help="the primary predictions")
    ap.add_argument("--also", default=",".join(str(ROOT / "results" / v)
                                               for v in ("prereg_v3b", "prereg_v2")),
                    help="comma list of other prediction directories to report ('' for none)")
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    out = Path(a.out)
    runs = vb.load_runs(out)
    summ = vb.summarize(runs, boot=a.boot) if runs else {"rows": [], "derived": {},
                                                         "by_launch": []}
    res = score(Path(a.prereg), out, runs, summ, a.boot)
    res["also"] = [score(Path(x), out, runs, summ, a.boot) for x in a.also.split(",") if x]
    (out / "prereg_compare.json").write_text(json.dumps(res, indent=1, default=str))
    md = markdown(res)
    for x in res["also"]:
        md += "\n\n" + markdown(x, secondary=True)
    (out / "prereg_compare.md").write_text(md)
    print(md[:6000])


def score(pre: Path, out: Path, runs: list[dict], summ: dict, boot: int) -> dict:
    """Every claim of one prediction directory against the measured run."""
    P = json.loads((pre / "predictions.json").read_text())
    rows = {(r["arm"], r["agents"]): r for r in summ["rows"]}
    cells: dict = {}
    for r in runs:
        if r["status"] == "ok":
            cells.setdefault((r["arm"], r["agents"]), []).append(r)
    primary = P["primary"]
    verdicts = []
    for c in P["sets"][primary]["claims"]:
        if c["kind"] == "ratio":
            v = check_ratio(c, rows)
            if v["verdict"] not in ("not run", "invalid"):
                v["strict"] = strict(c, cells, boot=boot)
                v["patterns"] = pattern_ratios(c, cells)
            v["adjacent"] = adjacent(c, rows, cells, boot)
        elif c["kind"] == "fraction":
            v = check_fraction(c, rows)
        else:
            v = check_threshold(c, rows, summ["derived"])
        alt = {k: next((x["predicted"] for x in st["claims"] if x["id"] == c["id"]), None)
               for k, st in P["sets"].items() if k != primary}
        verdicts.append({**c, **v, "predicted_other_sets": alt})
    ovh_file = out / "overhead" / "overhead_vllm.json"
    ovh = check_overhead(P["overhead"], json.loads(ovh_file.read_text())
                         if ovh_file.exists() else None)
    grows, gsrc = general_rows(out)
    gen = check_general(P["general"]["claims"], grows)
    launches = []
    lf = out / "sweep" / "launches.jsonl"
    if lf.exists():
        launches = [json.loads(x) for x in lf.read_text().splitlines() if x.strip()]
    return {"prereg": pre.name, "prereg_commit": P["code"]["commit"],
            "prereg_stamp": P["stamp_utc"], "prereg_files": prereg_files(pre),
            "measured_runs": len(runs), "claims": verdicts, "overhead": ovh, "general": gen,
            "general_source": gsrc, "points": point_errors(P["sets"], rows),
            "launch_noise": launch_noise(summ), "launches": launches}


def _tally(xs: list[dict]) -> str:
    from collections import Counter

    c = Counter(x["verdict"] for x in xs)
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "none"


def markdown(res: dict, secondary: bool = False) -> str:
    """The report for one prediction directory. secondary: an older set, reported after
    the primary one (its claims and verdicts only; the launch and overhead tables are the
    primary's)."""
    f = vb._fmt
    name = res.get("prereg", "prereg_v2")
    L = [f"# Measured vs pre-registered ({name})" + (" (also reported)" if secondary else ""),
         "",
         f"Predictions: commit `{res['prereg_commit'][:10]}`, written {res['prereg_stamp']}. "
         f"Measured runs found: {res['measured_runs']}. Verdicts follow the rules in "
         f"`results/{name}/predictions.md`; 'not run' means the cell was not measured.", "",
         "Prediction files vs the prereg commit (sha256): " + ", ".join(
             f"{k} {v}" for k, v in res.get("prereg_files", {}).items()) + ".", "",
         f"- Simulator claims (P1): {_tally(res['claims'])}",
         f"- Ratio claims, strict (launch-level CI, added before the run): "
         f"{_tally([c['strict'] for c in res['claims'] if c.get('strict')])}",
         f"- Scheduler overhead bounds: {_tally(res['overhead'])}",
         f"- General workload claims ({res['general_source'] or 'not run'}; one run per cell, "
         f"indicative): {_tally(res['general'])}", "",
         "## Claims", "",
         "'verdict' is the pre-registered rule: a ratio is supported when its point estimate "
         "is within the tolerance, however wide its CI. That alone does not show equivalence "
         "(for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, "
         "resampling server launches, then runs, then sessions, inside predicted +- tol "
         "(supported) or outside it (refuted), with >= 2 launches per side "
         "(launches: numerator/denominator). Read a ratio as shown only where both agree. "
         "'work': sub-call tokens per session, numerator over denominator (not a verdict); "
         "away from 1 by more than the tolerance, the two sides did not run the same "
         "workload.", "",
         "| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches "
         "| work | validity |",
         "|---|---|---|---|---|---|---|---|"]
    for c in res["claims"]:
        if c["kind"] == "ratio":
            what = (f"{c['numerator'][0]} / {c['denominator'][0]} at {c['numerator'][1]}: "
                    f"{c['metric']}")
            fmt = lambda x: f(x, 3)  # noqa: E731
        elif c["kind"] == "fraction":
            what = f"{c['arm']} at {c['agents']}: decoys rejected"
            fmt = lambda x: f(x, 2)  # noqa: E731
        else:
            what = f"{c['key']} of {c['arm']}"
            fmt = str
        other = ", ".join(fmt(v) if v is not None else "None"
                          for v in c["predicted_other_sets"].values())
        pv = fmt(c["predicted"]) if c["predicted"] is not None else "None"
        mv = c.get("measured")
        st = c.get("strict")
        sv = "-" if not st else (f"{st['verdict']} [{f(st['ci'][0], 3)}, {f(st['ci'][1], 3)}] "
                                 if st.get("ci") else f"{st['verdict']} ") + \
            "{}/{}".format(*st["launches"])
        L.append(f"| {c['id']} | {what} | {pv} ({other}) | "
                 f"{'-' if mv is None and 'measured' not in c else fmt(mv)} | {c['verdict']} | "
                 f"{sv} | {f(c.get('work'), 3)} | {', '.join(c.get('validity', [])) or '-'} |")
    pats = [c for c in res["claims"] if c.get("patterns")]
    if pats:
        names = sorted({k for c in pats for k in c["patterns"]["per_pattern"]}, key=str)
        L += ["", "## Per-pattern ratios (secondary; session_p50 claims)", "",
              "Median session wall per pattern, numerator over denominator: the same "
              "deterministic workload on both sides. The pooled p50 above can jump between "
              "pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.", "",
              "| id | predicted | pooled | " + " | ".join(map(str, names)) + " | geo mean |",
              "|---|---|---|" + "---|" * len(names) + "---|"]
        for c in pats:
            pp = c["patterns"]["per_pattern"]
            L.append(f"| {c['id']} | {f(c['predicted'], 3)} | {f(c.get('measured'), 3)} | "
                     + " | ".join(f(pp.get(k), 3) for k in names)
                     + f" | {f(c['patterns']['gmean'], 3)} |")
    adj = [c for c in res["claims"] if c.get("adjacent")]
    if adj:
        L += ["", "## Priority against stock launched next to it (secondary)", "",
              "The priority claims' denominators are B1's stock launches, hours earlier. "
              "Here the same ratios use stock FCFS from prio8 (fcfs-adj, launched in turn "
              "with priority: priority, stock, stock, priority).", "",
              "| id | metric | predicted | vs B1 stock | vs adjacent stock | verdict | strict |",
              "|---|---|---|---|---|---|---|"]
        for c in adj:
            x = c["adjacent"]
            L.append(f"| {c['id']} | {c['metric']} | {f(c['predicted'], 3)} | "
                     f"{f(c.get('measured'), 3)} | {f(x.get('measured'), 3)} | {x['verdict']} | "
                     f"{x['strict']['verdict']} |")
    if secondary:
        if not res["general"]:
            return "\n".join(L) + "\n"
        L += ["", "## General workload claims", "", "| claim | predicted | bound | measured "
              "| verdict |", "|---|---|---|---|---|"]
        L += [f"| {x['n']}. {x['claim'][:90]} | {x['predicted_ratio']:.3f} | {x['bound']} | "
              f"{f(x.get('measured_ratio'), 3)} | {x['verdict']} |" for x in res["general"]]
        return "\n".join(L) + "\n"
    L += ["", "## Point accuracy (|log(pred / meas)|; not pass/fail)", "",
          "| set | part | metric | points | median | max |", "|---|---|---|---|---|---|"]
    for key, st in res["points"].items():
        for k, v in st["summary"].items():
            part, metric = k.split("/")
            if v:
                L.append(f"| {key} | {part} | {metric} | {v['n']} | {v['median']:.3f} | "
                         f"{v['max']:.3f} |")
    L += ["", "## Launch-to-launch spread (same arm and load, different server launches)", "",
          "| arm | agents | launches | session p50 per launch | spread |", "|---|---|---|---|---|"]
    for r in res["launch_noise"]:
        L.append(f"| {r['arm']} | {r['agents']} | {', '.join(r['launches'])} | "
                 f"{', '.join(f(x) for x in r['session_p50'])} | {100 * r['spread']:.1f}% |")
    L += ["", "## Server launches (compile state)", "",
          "A fresh compile saves an artifact (AOT saved); a cached launch loads one (AOT "
          "loaded). Launches that ran the same code show the same artifact path in one of "
          "the two columns. Role cache_fill: compiled fresh, stopped unmeasured.", "",
          "| launch | status | role | startup s | eager | fresh | AOT saved | AOT loaded | "
          "GPU C / SM MHz | plugin line |", "|---|---|---|---|---|---|---|---|---|---|"]
    for x in res["launches"]:
        g = x.get("gpu") or {}
        L.append(f"| {x['launch']} | {x.get('status', 'up')} | {x.get('role', '-')} | "
                 f"{x.get('startup_s')} | {x.get('enforce_eager')} | "
                 f"{x.get('fresh_compile')} | {x.get('aot_saved') or '-'} | "
                 f"{x.get('aot_loaded') or '-'} | {f(g.get('temp_c'), 0)} / "
                 f"{f(g.get('sm_mhz'), 0)} | "
                 f"{x.get('sptc_line') or (x.get('error') or '-')[:80].replace(chr(10), ' ')} |")
    L += ["", "## Scheduler overhead (added time per step vs stock)", "",
          "| N | variant | scheduling | added us | bound us | verdict |", "|---|---|---|---|---|---|"]
    for x in res["overhead"]:
        L.append(f"| {x['n_running']} | {x['variant']} | {x.get('scheduling', '-')} | "
                 f"{f(x.get('added_us'), 1)} | {x['bound_added_us']:.0f} | {x['verdict']} |")
    L += ["", "## General workload claims", "",
          "One run per cell and one server launch per arm (fcfs, priority, plugin in that "
          "order): no CI, no launch-to-launch noise floor. Single-run, indicative verdicts.", "",
          "| claim | predicted | bound | measured | verdict |", "|---|---|---|---|---|"]
    for x in res["general"]:
        L.append(f"| {x['n']}. {x['claim'][:90]} | {x['predicted_ratio']:.3f} | {x['bound']} | "
                 f"{f(x.get('measured_ratio'), 3)} | {x['verdict']} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
