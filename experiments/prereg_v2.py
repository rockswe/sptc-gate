"""Pre-registered simulator predictions for everything the second T4 run
(kaggle/sptc_kaggle_v2.ipynb) measures, from the merged code, written before any of it runs.

  B   regression A/B: stock vs plugin fixed / adaptive / off, 1/4/8 agents (vllm_bench
      preset ab), the same at 1 agent on --enforce-eager launches (ab_eager), and vLLM's
      priority scheduling at 8 agents (prio8)
  C1  saturation sweep (vllm_bench presets core, full)
  C2  ReAct / background workload (bench_general.py matrix, quick and full):
      experiments/general.py's predictions, regenerated
  A   scheduler overhead (overhead_bench.py vllm): no simulator prediction, a declared bound

Calibration: experiments/t4_validate.py's, as in experiments/sweep_predict.py (cost from
calib.json and concur.json M3, per-call tokens from suite.json, one client overhead fit on
the no-speculation suite medians). Sets:
  P0      that calibration alone; no load row of the October 19 run is an input
  P1      P0 plus seq_cap (per-sequence step cost stops growing past seq_cap sequences),
          fit on the October 19 run's 18 root TPOT p50s (1/4/8 agents) with this model.
          Primary. Its 1/4/8-agent points are in-sample
  P1-alt  P1 with the runner-up seq_cap of that fit (sensitivity, not a third prediction)
Plugin arms use ServerConfig.plugin_semantics (what sptc_vllm does: no promotion, FCFS
with bets last, bets gated in the waiting loop) and the arm's prefill_allowance mode.

  PYTHONPATH=. .venv/bin/python experiments/prereg_v2.py [--out results/prereg_v2]
writes predictions.json, predictions.md and general_predictions.json there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kaggle"))

import general as G  # noqa: E402
import t4_validate as t4  # noqa: E402
import vllm_bench as vb  # noqa: E402
import sweep_predict as w2  # noqa: E402

from sptc_sim import suite  # noqa: E402
from sptc_sim.trace import compile_turn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "prereg_v2"
CALIB_FILES = ["calib.json", "concur.json", "suite.json", "load.json", "load_tagged.json",
               "vllm.log"]
TOL = 0.05  # ratio claims: |measured - predicted| allowed (the T4 fit's median error 3-5%)
FRAC_TOL = 0.10  # decoy-outcome fractions: absolute


# ----------------------------------------------------------------------------- arms
def setting(arm: vb.Arm) -> dict:
    """The simulator setting of one bench arm (sweep_predict.SIM_ARMS format)."""
    base = arm.server.removesuffix("_eager")  # eager twins: same scheduling, other code
    if base.startswith("plugin") and arm.tags == "none":
        # untagged traffic: the plugin schedules exactly as stock vLLM
        # (integrations/tests_vllm/test_sptc_differential.py)
        return w2.SIM_ARMS["fcfs"]
    if base in ("fcfs", "priority"):
        return w2.SIM_ARMS[base]
    c = vb.plugin_cfg(vb.ALLOWANCE[arm.server])["sptc"]
    return dict(cfg={"policy": "agent", "reject_bets": True, "spec_max_wait": math.inf,
                     "free_window": c["free_window"], "spec_kv_reserve": c["kv_reserve"],
                     "spec_prefill_budget": c["spec_prefill_budget"],
                     "spec_prefill_mode": c["prefill_allowance"], "plugin_semantics": True},
                mark_spec="guesses", promote_early=False)


def points() -> dict[str, list[int]]:
    """arm -> loads the second run measures (compiled arms only; eager arms are scored
    as ratios to their compiled twins' predictions)."""
    pts: dict[str, set] = {}
    for preset in ("ab", "prio8", "core", "full"):
        pre = vb.PRESETS[preset]
        for name in pre["arms"]:
            loads = [int(x) for x in pre["agents"].split(",")]
            only = pre.get("only", {}).get(name)
            pts.setdefault(name, set()).update(n for n in loads if only is None or n in only)
    return {k: sorted(v) for k, v in pts.items()}


EAGER_TWIN = {x.name: x.name.replace("-eager/", "/") for x in vb.ARMS if "-eager/" in x.name}


# ----------------------------------------------------------------------------- claims
def ratio_claims(rows: dict, cid: str, section: str, pairs, metrics) -> list[dict]:
    out = []
    for num, den, n in pairs:
        for m in metrics:
            a, b = rows.get((num, n)), rows.get((den, n))
            if a is None or b is None or not b.get(m):
                continue
            out.append({"id": cid, "section": section, "kind": "ratio",
                        "numerator": [num, n], "denominator": [den, n], "metric": m,
                        "predicted": a[m] / b[m], "tol": TOL})
    return out


def claims(rows: dict, d: dict, decoys: dict) -> list[dict]:
    """The pre-registered, machine-checked claims (experiments/prereg_compare.py)."""
    c = []
    ab = [(f"{p}/{mode}", f"fcfs/{mode}", n) for p in ("plugin", "plugin-adaptive", "plugin-off")
          for mode in ("spec", "spec+bad") for n in (1, 4, 8)]
    c += ratio_claims(rows, "AB", "B: plugin vs stock, compiled", ab,
                      ("session_p50", "root_tpot_p50"))
    c += ratio_claims(rows, "UNT", "B: plugin server, untagged traffic",
                      [("plugin-untagged/spec", "fcfs/spec", 1)],
                      ("session_p50", "root_tpot_p50"))
    eager = []
    for arm, twin in EAGER_TWIN.items():
        if arm == "fcfs-eager/spec":
            continue
        ref = "plugin-eager/spec" if arm != "plugin-eager/spec" else "fcfs-eager/spec"
        for m in ("session_p50", "root_tpot_p50"):
            a, b = rows[(twin, 1)], rows[(EAGER_TWIN[ref], 1)]
            eager.append({"id": "EAG", "section": "B: eager launches "
                          "(relative only)", "kind": "ratio", "numerator": [arm, 1],
                          "denominator": [ref, 1], "metric": m, "predicted": a[m] / b[m],
                          "tol": TOL})
    c += eager
    c += ratio_claims(rows, "PRIO", "B/C1: vLLM priority vs FCFS",
                      [(f"prio/{m}", f"fcfs/{m}", n) for m in ("spec", "spec+bad")
                       for n in (8, 16, 24, 32)], ("session_p50",))
    c += ratio_claims(rows, "PLG", "C1: plugin vs FCFS with bad guesses",
                      [("plugin/spec+bad", "fcfs/spec+bad", n) for n in (16, 24, 32)],
                      ("session_p50",))
    c += ratio_claims(rows, "BAD", "C1: bad guesses under the plugin",
                      [("plugin/spec+bad", "plugin/spec", n) for n in (8, 16, 24, 32)],
                      ("session_p50",))
    for arm in ("plugin/spec+bad", "plugin-adaptive/spec+bad", "plugin-off/spec+bad"):
        for n in (1, 4, 8, 16, 24, 32):
            if (arm, n) in decoys:
                c.append({"id": "REJ", "section": "B/C1: decoys rejected",
                          "kind": "fraction", "arm": arm, "agents": n, "outcome": "rejected",
                          "predicted": decoys[(arm, n)], "tol": FRAC_TOL})
    for key in ("knee_ref", "good50", "net_loss"):
        for arm, v in d[key].items():
            if "-" in arm.split("/")[0]:
                continue  # A/B-only arms have no ladder
            c.append({"id": "THR", "section": "C1: thresholds", "kind":
                      "threshold", "key": key, "arm": arm, "predicted": v,
                      "ladder": [int(x) for x in vb.PRESETS["full"]["agents"].split(",")]})
    seen: dict[str, int] = {}
    for x in c:  # AB-1, AB-2, ..., EAG-1, ...
        seen[x["id"]] = seen.get(x["id"], 0) + 1
        x["id"] = f"{x['id']}-{seen[x['id']]}"
    return c


def decoy_rejected(runs: list[dict]) -> dict:
    out = {}
    for r in runs:
        dec = [x["outcome"] for s in r["sessions"] for x in s["decoys"]]
        if dec:
            out[(r["arm"], r["agents"])] = sum(x == "rejected" for x in dec) / len(dec)
    return out


# ----------------------------------------------------------------------------- overhead
def overhead_bounds() -> list[dict]:
    """A declared bound, not a simulator prediction: the plugin's added time per step
    (its total p50 minus stock's, same N and scheduling) at most 3x the plugin's own
    policy work measured locally (results/sweep_prep/overhead_pure.json) plus 20 us for
    calling the hooks."""
    pure = json.loads((ROOT / "results" / "sweep_prep" / "overhead_pure.json").read_text())
    out = []
    for r in pure["rows"]:
        out.append({"id": f"OVH-{len(out) + 1}", "section": "A: scheduler overhead",
                    "kind": "overhead", "n_running": r["n_running"],
                    "variant": "sptc-tagged" if r["tagged"] else "sptc-untagged",
                    "pure_p50_us": r["policy"]["p50_us"],
                    "bound_added_us": 3 * r["policy"]["p50_us"] + 20})
    return out


# ----------------------------------------------------------------------------- main
def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()

    dirty = [x for x in run("status", "--porcelain").splitlines()
             if not x[3:].startswith("results/prereg_v2")]
    return {"commit": run("rev-parse", "HEAD"), "dirty_files": dirty}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    git = git_state()
    cost0, tables, client_s = w2.calibrate()
    mix = sorted({p for x in vb.ARMS for p in vb.WORKLOADS[x.workload]["patterns"].split(",")})
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4) for n in mix}
    cap, scores = w2.fit_seq_cap(cost0, tables, traces, setting)
    ranked = sorted(scores, key=lambda x: x["tpot_mean_abs_log_err"])
    alt = ranked[1]["seq_cap"]

    def capped(c):
        return w2.CappedStepCost(cost0.gpu, cost0.model, cost0.tp, cost0.ov,
                                 cost0.decode_table, seq_cap=c)

    pts = points()
    sets = {}
    for key, cost in (("P1", capped(cap)), ("P0", cost0), ("P1-alt", capped(alt))):
        print(f"--- {key}", flush=True)
        runs = []
        for name, loads in pts.items():
            arm = vb.ARM[name]
            for n in loads:
                rec = w2.sim_run(cost, tables, arm, n, traces,
                                 vb.WORKLOADS[arm.workload]["turns"], setting)
                runs.append(rec)
                w = [x["wall_s"] for x in rec["sessions"]]
                print(f"{key:6s} {name:26s} n={n:3d} session p50 {vb.pctl(w, 0.5):6.2f} s",
                      flush=True)
        summ = vb.summarize(runs, boot=0)
        rows = {(r["arm"], r["agents"]): r for r in summ["rows"]}
        dec = decoy_rejected(runs)
        sets[key] = {"summary": summ, "known_rows_check": w2.known_rows_check(summ),
                     "decoy_rejected": [{"arm": k[0], "agents": k[1], "frac": v}
                                        for k, v in sorted(dec.items())],
                     "allowance_steps": [{"arm": r["arm"], "agents": r["agents"],
                                          "cut": r["sim_allowance_steps"],
                                          "steps": r["sim_steps"]} for r in runs],
                     "claims": claims(rows, summ["derived"], dec)}
    G.kaggle_predict(out / "general_predictions.json")
    general = json.loads((out / "general_predictions.json").read_text())
    res = {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": "PREDICTED by the simulator before any GPU run of kaggle/sptc_kaggle_v2.ipynb",
        "code": {**git, "script": "experiments/prereg_v2.py"},
        "primary": "P1",
        "calibration": {
            "inputs": {f"results/kaggle_t4/sptc_out/{f}": sha(t4.D / f) for f in CALIB_FILES},
            "cost_from": "calib.json (solo decode, solo prefill at 3 lengths) and concur.json M3 "
                         "(decode step vs concurrent decoders): experiments/t4_validate.fit_cost",
            "tokens_from": "suite.json no-speculation runs, per call by identity "
                           "(sweep_predict.TableBackend); decoys forced to max_tokens",
            "fit_on_outcomes": [
                f"client overhead {1000 * client_s:.0f} ms each way: no-speculation suite "
                "medians of the October 19 run (suite.json)",
                f"P1 seq_cap {cap}: root TPOT p50 of the October 19 run's 18 load rows "
                "(load.json, load_tagged.json; 1/4/8 agents, stock and plugin fixed). P1's "
                "1/4/8-agent points of those arms are in-sample",
            ],
            "server_facts": "KV 85,904 tokens (vllm.log), max_num_batched_tokens 2048, "
                            "max_num_seqs 256",
            "t_fixed_ms": 1000 * cost0.ov.t_fixed, "t_per_seq_ms": 1000 * cost0.ov.t_per_seq,
            "mfu": cost0.ov.mfu, "attn_mfu": cost0.ov.attn_mfu, "client_s": client_s,
            "seq_cap": {"P1": cap, "P1-alt": alt, "fit": scores},
        },
        "arms": {name: {"server": vb.ARM[name].server, "loads": loads,
                        "setting": {k: (str(v) if isinstance(v, float) and math.isinf(v)
                                        else v) for k, v in setting(vb.ARM[name])["cfg"].items()}
                        | {"mark_spec": setting(vb.ARM[name])["mark_spec"]}}
                 for name, loads in pts.items()},
        "eager": {"arms": EAGER_TWIN, "note": "no eager calibration: eager arms are predicted "
                  "only as ratios, equal to their compiled twins' ratios"},
        "sets": sets,
        "summary": sets["P1"]["summary"],  # what `vllm_bench.py plan` reads
        "overhead": overhead_bounds(),
        "general": {"file": "general_predictions.json",
                    "git_head_when_written": general["git_head_when_written"],
                    "claims": general["claims"], "quick_claims": general["quick_claims"]},
        "rules": RULES,
    }
    res["gpu_minutes"] = {}
    for preset in ("ab", "ab_eager", "prio8", "core", "full"):
        (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
        ns = argparse.Namespace(preset=preset, arms=None, agents=None, reps=None, turns=None,
                                rounds=None, warm_pass=False,
                                predictions=str(out / "predictions.json"))
        res["gpu_minutes"][preset] = {k: v for k, v in vb.plan(ns).items() if k != "rows"}
    res["wall_s"] = time.time() - t_start
    (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "predictions.md").write_text(markdown(res))
    print(f"wrote {out} in {res['wall_s']:.0f} s")


RULES = {
    "validity": "A measured point counts only if every run has status ok and its row's "
                "cpu_ok is true (whole-host CPU < 0.85 mean, < 10% of seconds >= 95% busy). "
                "Otherwise every claim using it is 'invalid'.",
    "ratio": "measured ratio m of two measured points vs predicted p: supported if |m - p| "
             "<= tol; refuted if |m - p| > tol and the numerator's 95% CI does not overlap "
             "p x the denominator's 95% CI (both from vllm_bench.summarize's bootstrap); "
             "otherwise unresolved. Eager ratios use eager points only.",
    "fraction": "measured share of decoys logged 'rejected' vs predicted: supported if within "
                "tol (absolute), otherwise refuted.",
    "threshold": "a predicted knee_ref / good50 / net_loss load is right if the measured one "
                 "is the same ladder step or the adjacent one; a prediction above the ladder "
                 "(None) is right if no measured load reaches it. Scored on the presets that "
                 "ran; a threshold beyond the loads measured is 'unchecked'.",
    "overhead": "plugin total p50 minus stock total p50 (same N, same scheduling, sync and "
                "async), from overhead_bench.py vllm: supported if <= bound_added_us.",
    "general": "experiments/general.py's claims (results/general/predictions.json, "
               "regenerated identically): supported if the measured ratio is inside the bound.",
    "points": "for every measured (arm, load), |log(predicted / measured)| of session p50 and "
              "root TPOT p50 for P1, P0 and P1-alt: median and max, P1's in-sample points "
              "(1/4/8 agents of fcfs/* and plugin/*) apart from the rest. Not pass/fail.",
}


def headline(res: dict) -> list[str]:
    """A few generated sentences; every number comes from the P1 set."""
    p1 = res["sets"]["P1"]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    vs = p1["summary"]["derived"]["vs_stock"]

    def dev(arms, loads, k="session_p50"):
        xs = [abs(vs[a][n][k] - 1) for a in arms for n in loads if n in vs.get(a, {})]
        return 100 * max(xs)

    modes = [abs(rows[(f"plugin-{m}/{c}", n)]["session_p50"]
                 / rows[(f"plugin/{c}", n)]["session_p50"] - 1)
             for m in ("adaptive", "off") for c in ("spec", "spec+bad") for n in (1, 4, 8)]
    prio = [abs(vs["prio/spec+bad"][n]["session_p50"] - 1) for n in (8, 16, 24)]
    plg = {n: vs["plugin/spec+bad"][n]["session_p50"] for n in (1, 4, 8, 16, 24, 32)}
    rej = {(x["arm"], x["agents"]): x["frac"] for x in p1["decoy_rejected"]}
    return [
        f"- Without bad guesses, every plugin arm (fixed, adaptive, off, untagged) is within "
        f"{dev(['plugin/spec', 'plugin-adaptive/spec', 'plugin-off/spec', 'plugin-untagged/spec'], (1, 4, 8)):.1f}% "
        "of stock FCFS in session p50 at 1/4/8 agents, root TPOT within "
        f"{dev(['plugin/spec', 'plugin-adaptive/spec', 'plugin-off/spec'], (1, 4, 8), 'root_tpot_p50'):.1f}%. "
        "So the October 19 1-agent gap (+13.5% session p50) is not predicted: if it repeats, "
        "claims AB-1/AB-2 are refuted.",
        f"- The three allowance modes are within {100 * max(modes):.1f}% of each other "
        "everywhere in the A/B (compiled and, as ratios, eager).",
        "- With one bad guess per call the plugin's session p50 relative to stock FCFS is "
        + ", ".join(f"{v:.2f} at {n}" for n, v in plg.items()) + "; it rejects "
        + ", ".join(f"{100 * rej[('plugin/spec+bad', n)]:.0f}% of decoys at {n}"
                    for n in (1, 4, 8)) + ".",
        f"- vLLM priority scheduling is within {100 * max(prio):.1f}% of FCFS with bad "
        "guesses at 8, 16 and 24 agents: it reorders only the waiting queue, and running bad "
        "guesses keep decoding next to the root streams.",
        f"- Stock speculation with bad guesses becomes a net loss at "
        f"{p1['summary']['derived']['net_loss']['fcfs']} agents; the plugin's never does in "
        "the ladder." if p1["summary"]["derived"]["net_loss"]["plugin"] is None else
        f"- Net-loss loads: {p1['summary']['derived']['net_loss']}.",
    ]


def markdown(res: dict) -> str:
    c = res["calibration"]
    p1 = res["sets"]["P1"]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    p0 = {(r["arm"], r["agents"]): r for r in res["sets"]["P0"]["summary"]["rows"]}
    L = ["# Pre-registered predictions for the second T4 run (v2)", "",
         f"**PREDICTED by the simulator, not measured.** Written {res['stamp_utc']} by "
         "`experiments/prereg_v2.py`, before any GPU run of `kaggle/sptc_kaggle_v2.ipynb`. "
         "These files are not edited after the run; the comparison is "
         "`experiments/prereg_compare.py`.", "",
         f"- Code: commit `{res['code']['commit']}`"
         + (" (clean tree)" if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}") + ".",
         "- Calibration inputs (sha256 prefix): " + ", ".join(
             f"`{k.split('/')[-1]}` {v}" for k, v in c["inputs"].items()) + ".",
         f"- Cost model from {c['cost_from']}: t_fixed {c['t_fixed_ms']:.2f} ms, per "
         f"sequence {c['t_per_seq_ms']:.3f} ms, GEMM efficiency {c['mfu']:.2f}, attention "
         f"efficiency {c['attn_mfu']:.3f}. Server: {c['server_facts']}.",
         f"- Tokens: {c['tokens_from']}.",
         "- Fit on outcomes (all from the October 19 T4 run, none from the second run):"]
    L += [f"  - {x}." for x in c["fit_on_outcomes"]]
    L += [f"- Sets: **P1 (primary)**, seq_cap {c['seq_cap']['P1']}; P0, no seq_cap; P1-alt, "
          f"seq_cap {c['seq_cap']['P1-alt']} (the fit's runner-up, a sensitivity set).",
          "- Plugin arms: `ServerConfig.plugin_semantics` with the arm's `prefill_allowance`; "
          "decoys tagged bet, spec-ptc dispatches early. `plugin-untagged/spec` is simulated "
          "as stock FCFS (the plugin schedules untagged traffic exactly as stock). Priority "
          "arms: `vllm-priority`, every speculative call at priority 1.",
          "- Eager arms (`--enforce-eager`) have no calibration: only their ratios are "
          "predicted, equal to the compiled twins' ratios.",
          "- One deterministic simulator run per point: no repeats, no CIs. vLLM's "
          "full-sequence admission check and CUDA-graph padding are not modeled in these "
          "(code-mode) predictions; the client's CPU is not modeled.",
          "- For scoring this run these files replace `results/t4_run1_analysis/predictions.*` and "
         "`results/sweep_prep/predictions*` (kept as written). The model differs from the sweep "
         "predictions' in one way: plugin arms use `plugin_semantics` instead of the idealized agent policy "
         "(program-level order, promotion of claimed calls). Bets are then gated after the "
         "root is admitted, so more decoys are rejected at light load than those predicted. "
         "The C2 claims are unchanged.",
         "- Known misses carried over: the simulator does not reproduce the October 19 "
          "1-agent plugin gap (3.10 vs 2.73 s, `results/t4_run1_analysis/root_cause.md`); before the seq_cap "
          "fit it over-predicted stock 8 agents with bad guesses (8.21 vs 6.62 s).", "",
          "## seq_cap fit (root TPOT p50, 18 October 19 rows)", "",
          "| seq_cap | mean abs log error |", "|---|---|"]
    L += [f"| {x['seq_cap']} | {x['tpot_mean_abs_log_err']:.4f} |" for x in c["seq_cap"]["fit"]]
    L += ["", "## GPU minutes per preset (`vllm_bench.py plan`, P1 session times)", "",
          "| preset | runs | launches | estimated minutes |", "|---|---|---|---|"]
    for k, v in res["gpu_minutes"].items():
        L.append(f"| {k} | {v['runs']} | {v['launches']} | {v['est_minutes']} |")
    L += ["", "## What the simulator predicts, in short (P1)", ""] + headline(res) + [
          "", "## B. Regression A/B (P1; P0 in brackets)", "",
          "| arm | agents | session p50 s | root TPOT p50 ms | vs stock: session p50 | root "
          "TPOT p50 | decoys rejected | steps the allowance cut |",
          "|---|---|---|---|---|---|---|---|"]
    vs = p1["summary"]["derived"]["vs_stock"]
    rej = {(x["arm"], x["agents"]): x["frac"] for x in p1["decoy_rejected"]}
    cut = {(x["arm"], x["agents"]): f"{x['cut']} of {x['steps']}" for x in p1["allowance_steps"]}
    for preset in ("ab", "prio8"):
        pre = vb.PRESETS[preset]
        for name, n in ((x, int(k)) for x in pre["arms"] for k in pre["agents"].split(",")):
            if n not in pre.get("only", {}).get(name, [n]):
                continue
            r, q = rows[(name, n)], p0[(name, n)]
            v = vs.get(name, {}).get(n, {})
            L.append(f"| {name} | {n} | {r['session_p50']:.2f} [{q['session_p50']:.2f}] | "
                     f"{r['root_tpot_p50']:.1f} [{q['root_tpot_p50']:.1f}] | "
                     f"{vb._fmt(v.get('session_p50'), 3)} | {vb._fmt(v.get('root_tpot_p50'), 3)}"
                     f" | {vb._fmt(rej.get((name, n)))} | {cut.get((name, n), '-')} |")
    L += ["", "## C1. Saturation sweep (P1)", ""]
    for title, k, nd in (("Session p50 (s)", "session_p50", 2),
                         ("Root TPOT p50 (ms)", "root_tpot_p50", 1),
                         ("Sessions per minute", "sessions_per_min", 1),
                         ("Goodput (SLO 2x / 2x)", "goodput", 2)):
        sweep_rows = [r for r in p1["summary"]["rows"]
                      if r["arm"] in vb.PRESETS["full"]["arms"]]
        L += [f"### {title}", ""] + w2.pivot(sweep_rows, k, nd) + [""]
    d = p1["summary"]["derived"]
    sw = vb.PRESETS["full"]["arms"]

    def only(key):
        return {k: v for k, v in d[key].items() if k in sw}

    L += ["### Derived answers (P1)", "",
          f"- knee_ref: {only('knee_ref')}", f"- goodput < 0.5 first at: {only('good50')}",
          f"- spec+bad no faster than nospec first at: {d['net_loss']}",
          f"- throughput peak in the ladder: {only('thr_peak')}", "",
          "## C2. ReAct / background workload", "",
          "`general_predictions.json`, regenerated by `experiments/general.py --kaggle-predict` "
          "on this code: identical cells to `results/general/predictions.json` (checked). "
          f"{len(res['general']['claims'])} claims; the quick matrix carries claims "
          f"{res['general']['quick_claims']}.", "",
          "| claim | predicted ratio | bound |", "|---|---|---|"]
    for x in res["general"]["claims"]:
        L.append(f"| {x['n']}. {x['claim']} | {x['predicted_ratio']:.3f} | {x['bound']} |")
    L += ["", "## A. Scheduler overhead (a declared bound, not a simulator prediction)", "",
          "| N running | variant | plugin policy work measured locally, p50 us | bound on added "
          "time per step, us |", "|---|---|---|---|"]
    for x in res["overhead"]:
        L.append(f"| {x['n_running']} | {x['variant']} | {x['pure_p50_us']:.1f} | "
                 f"{x['bound_added_us']:.0f} |")
    L += ["", "## Claims (P1 values; checked by `experiments/prereg_compare.py`)", "",
          "| id | section | claim | predicted | tolerance |", "|---|---|---|---|---|"]
    for x in p1["claims"]:
        if x["kind"] == "ratio":
            what = (f"{x['numerator'][0]} / {x['denominator'][0]} at {x['numerator'][1]}: "
                    f"{x['metric']}")
            pv = f"{x['predicted']:.3f}"
        elif x["kind"] == "fraction":
            what = f"{x['arm']} at {x['agents']}: share of decoys rejected"
            pv = f"{x['predicted']:.2f}"
        else:
            what = f"{x['key']} of {x['arm']}"
            pv = str(x["predicted"])
        tol = x.get("tol", "adjacent step")
        L.append(f"| {x['id']} | {x['section']} | {what} | {pv} | {tol} |")
    L += ["", "## Scoring rules (fixed now)", ""]
    L += [f"- **{k}.** {v}" for k, v in res["rules"].items()]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
