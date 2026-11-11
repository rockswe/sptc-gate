"""Pre-registered simulator predictions for the follow-up T4 run (kaggle/sptc_kaggle_v3.ipynb),
from the merged code, written before any of it runs.

The same generator, calibration and scoring rules as experiments/prereg_v2.py (sections A,
B, C1, C2), plus section B4 (vllm_bench preset `baselines`): vLLM priority with only the
bets at low priority, and a client-side cap on bets (vllm_bench.ProxyGate, window and
semaphore modes, cap = the plugin's free window) on stock FCFS, next to stock FCFS and the
plugin, at 4 and 8 agents.

What differs from v2 is written into predictions.md ("Changes from v2"), computed against
results/prereg_v2 when this runs. results/prereg_v2 is never edited.

  PYTHONPATH=.:integrations .venv/bin/python experiments/prereg_v3.py [--out results/prereg_v3]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import prereg_v2 as P2
from prereg_v2 import G, t4, vb, w2

from sptc_sim import suite
from sptc_sim.trace import compile_turn

ROOT = P2.ROOT
OUT = ROOT / "results" / "prereg_v3"
V2 = ROOT / "results" / "prereg_v2"
B4_LOADS = (4, 8)


# ----------------------------------------------------------------------------- arms
def setting(arm: vb.Arm) -> dict:
    """prereg_v2.setting, plus the B4 arms."""
    if arm.tags == "priority_bets":  # vLLM priority, only the bets at priority 1
        return dict(cfg={"policy": "vllm-priority"}, mark_spec="guesses", promote_early=False)
    if arm.gate:  # stock FCFS behind a client-side cap on bets
        return {**w2.SIM_ARMS["fcfs"], "proxy": arm.gate}
    return P2.setting(arm)


def points() -> dict[str, list[int]]:
    pts = P2.points()
    pre = vb.PRESETS["baselines"]
    for name in pre["arms"]:
        pts.setdefault(name, [])
        pts[name] = sorted(set(pts[name]) | {int(x) for x in pre["agents"].split(",")})
    return pts


# ----------------------------------------------------------------------------- claims
def claims(rows: dict, d: dict, dec: dict) -> list[dict]:
    # the B4 arms have no ladder: no threshold claims, so v2's claim ids stay the same
    d = {**d, **{k: {a: v for a, v in d[k].items() if a not in vb.BASELINE_ARMS}
                 for k in ("knee_ref", "good50")}}
    c = P2.claims(rows, d, dec)
    new = []
    ref = vb.BASELINE_REF
    new += P2.ratio_claims(rows, "B4", "B4: baselines vs stock FCFS (same launches)",
                           [(arm, ref, n) for arm in vb.BASELINE_ARMS if arm != ref
                            for n in B4_LOADS], ("session_p50", "root_tpot_p50"))
    new += P2.ratio_claims(rows, "B4P", "B4: plugin vs the client-side cap",
                           [("plugin-b4/spec+bad", px, n) for px in ("proxy/spec+bad",
                                                                     "proxy-sem/spec+bad")
                            for n in B4_LOADS], ("session_p50", "root_tpot_p50"))
    for arm in ("proxy/spec+bad", "proxy-sem/spec+bad", "plugin-b4/spec+bad"):
        for n in B4_LOADS:
            if (arm, n) in dec:
                new.append({"id": "B4R", "section": "B4: decoys rejected", "kind": "fraction",
                            "arm": arm, "agents": n, "outcome": "rejected",
                            "predicted": dec[(arm, n)], "tol": P2.FRAC_TOL})
    seen: dict[str, int] = {}
    for x in new:
        seen[x["id"]] = seen.get(x["id"], 0) + 1
        x["id"] = f"{x['id']}-{seen[x['id']]}"
    return c + new


def git_state(out: Path) -> dict:
    """prereg_v2.git_state, also ignoring the output directory being written."""
    g = P2.git_state()
    try:
        rel = str(out.resolve().relative_to(ROOT))
    except ValueError:
        rel = None
    if rel:
        g["dirty_files"] = [x for x in g["dirty_files"] if not x[3:].startswith(rel)]
    return g


# ----------------------------------------------------------------------------- changes
def changes_from_v2(res: dict, v2: dict, g2: dict) -> dict:
    """Every claim of v2 whose predicted value moved by more than 5e-4 (or whose verdict
    rule changed), per set; the general claims; row counts; the new claims."""
    out: dict = {"sets": {}, "general": [], "new_claims": []}
    for key, st in res["sets"].items():
        old = {x["id"]: x for x in v2["sets"][key]["claims"]}
        moved = []
        for x in st["claims"]:
            o = old.get(x["id"])
            if o is None:
                continue
            a, b = o["predicted"], x["predicted"]
            if (a is None) != (b is None) or (isinstance(a, (int, float)) and b is not None
                                              and abs(a - b) > 5e-4) or (
                    not isinstance(a, (int, float)) and a != b):
                moved.append({"id": x["id"], "v2": a, "v3": b})
        r2 = {(r["arm"], r["agents"]): r for r in v2["sets"][key]["summary"]["rows"]}
        rows_moved = sum(
            1 for r in st["summary"]["rows"] if (r["arm"], r["agents"]) in r2 and any(
                r2[(r["arm"], r["agents"])].get(m) != r.get(m)
                for m in ("session_p50", "root_tpot_p50", "root_tpot_p99")))
        out["sets"][key] = {"claims_v2": len(old), "moved": moved,
                            "rows_compared": len(r2), "rows_moved": rows_moved}
    out["new_claims"] = [x["id"] for x in res["sets"]["P1"]["claims"]
                         if x["id"] not in {y["id"] for y in v2["sets"]["P1"]["claims"]}]
    for a, b in zip(g2["claims"], res["general"]["claims"]):
        if abs(a["predicted_ratio"] - b["predicted_ratio"]) > 5e-4:
            out["general"].append({"n": a["n"], "v2": a["predicted_ratio"],
                                   "v3": b["predicted_ratio"], "bound": a["bound"]})
    return out


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    git = git_state(out)
    cost0, tables, client_s = w2.calibrate()
    mix = sorted({p for x in vb.ARMS for p in vb.WORKLOADS[x.workload]["patterns"].split(",")})
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4) for n in mix}
    # the seq_cap fit uses the October 19 arms only (stock and plugin): as in v2
    cap, scores = w2.fit_seq_cap(cost0, tables, traces, P2.setting)
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
        dec = P2.decoy_rejected(runs)
        sets[key] = {"summary": summ, "known_rows_check": w2.known_rows_check(summ),
                     "decoy_rejected": [{"arm": k[0], "agents": k[1], "frac": v}
                                        for k, v in sorted(dec.items())],
                     "allowance_steps": [{"arm": r["arm"], "agents": r["agents"],
                                          "cut": r["sim_allowance_steps"],
                                          "steps": r["sim_steps"]} for r in runs],
                     "proxy": [{"arm": r["arm"], "agents": r["agents"], **r["proxy"]}
                               for r in runs if r.get("proxy")],
                     "claims": claims(rows, summ["derived"], dec)}
    G.kaggle_predict(out / "general_predictions.json")
    general = json.loads((out / "general_predictions.json").read_text())
    res = {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": "PREDICTED by the simulator before any GPU run of kaggle/sptc_kaggle_v3.ipynb",
        "version": "v3",
        "code": {**git, "script": "experiments/prereg_v3.py"},
        "primary": "P1",
        "calibration": {
            "inputs": {f"results/kaggle_t4/sptc_out/{f}": P2.sha(t4.D / f)
                       for f in P2.CALIB_FILES},
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
                "nothing fit for the B4 arms: bets-only priority, the client-side cap and its "
                "cap (the plugin's free window, 8) are set from the configuration",
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
                        | {"mark_spec": setting(vb.ARM[name])["mark_spec"],
                           "proxy": setting(vb.ARM[name]).get("proxy")}}
                 for name, loads in pts.items()},
        "eager": {"arms": P2.EAGER_TWIN, "note": "no eager calibration: eager arms are "
                  "predicted only as ratios, equal to their compiled twins' ratios"},
        "sets": sets,
        "summary": sets["P1"]["summary"],  # what `vllm_bench.py plan` reads
        "overhead": P2.overhead_bounds(),
        "general": {"file": "general_predictions.json",
                    "git_head_when_written": general["git_head_when_written"],
                    "claims": general["claims"], "quick_claims": general["quick_claims"]},
        "rules": {**P2.RULES,
                  "baselines": "B4 ratio and fraction claims use the ratio and fraction rules; "
                               "their denominators are fcfs-b4/spec+bad, launched in the same "
                               "rounds as the proxy arms (same server, other prompt prefix)."},
    }
    v2 = json.loads((V2 / "predictions.json").read_text())
    g2 = json.loads((V2 / "general_predictions.json").read_text())
    res["changes_from_v2"] = changes_from_v2(res, v2, g2)
    res["gpu_minutes"] = {}
    for preset in ("ab", "ab_eager", "prio8", "baselines", "core", "full"):
        (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
        ns = argparse.Namespace(preset=preset, arms=None, agents=None, reps=None, turns=None,
                                rounds=None, warm_pass=False,
                                predictions=str(out / "predictions.json"))
        res["gpu_minutes"][preset] = {k: v for k, v in vb.plan(ns).items() if k != "rows"}
    res["wall_s"] = time.time() - t_start
    (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "predictions.md").write_text(markdown(res))
    print(f"wrote {out} in {res['wall_s']:.0f} s")


# ----------------------------------------------------------------------------- markdown
WHY = [
    "**Simulator KV model (audit #17, #18, #32, #44).** vLLM 0.32's KV semantics are "
    "now the default: full-sequence admission, resume from the prefix cache after a "
    "preemption, one LRU queue for every freed block. Only the third moves anything here: "
    "the C2 ReAct cells (finished and aborted sub-calls' blocks now stay cached in free "
    "order). Sections B and C1 are unchanged.",
    "**Plugin model follows the fixed adapter (audit #2, #10, #25; ServerConfig."
    "plugin_fixes).** A running bet's prefill leaves the allowance waiting early prefill "
    "needs; a held bet's step is not counted behind another bet's prefill or in an empty "
    "step. On this workload (sub-call prompts 15-47 tokens) it changes no prediction: every "
    "B, C1 and C2 value is the same with and without it (checked by regenerating with "
    "plugin_fixes=False).",
    "**trace.py reads in sorted order.** Replays no longer depend on "
    "PYTHONHASHSEED. No B or C1 value moved.",
    "**New arms (section B4).** Bets-only priority, the client-side cap on bets in two "
    "modes, and stock FCFS and the plugin launched next to them, at 4 and 8 agents. New "
    "claims B4-*, B4P-* and B4R-*.",
    "**Not changed:** calibration inputs and their sha256, the cost fit, the client "
    "overhead, the seq_cap fit and its sets (P1 primary, P0, P1-alt), the tolerances and "
    "every scoring rule of v2.",
]


def markdown(res: dict) -> str:
    v2md = P2.markdown(res)
    body = v2md[v2md.index("## seq_cap fit"):]
    body = body.replace(
        "`general_predictions.json`, regenerated by `experiments/general.py --kaggle-predict` "
        "on this code: identical cells to `results/general/predictions.json` (checked). ",
        "`general_predictions.json`, regenerated by `experiments/general.py --kaggle-predict` "
        "on this code. Not identical to `results/general/predictions.json` any more: the "
        "ReAct cells moved with the simulator's KV fixes (Changes from v2). ")
    c = res["calibration"]
    ch = res["changes_from_v2"]
    L = ["# Pre-registered predictions for the follow-up T4 run (v3)", "",
         f"**PREDICTED by the simulator, not measured.** Written {res['stamp_utc']} by "
         "`experiments/prereg_v3.py`, before any GPU run of `kaggle/sptc_kaggle_v3.ipynb`. "
         "These files are not edited after the run. `experiments/prereg_compare.py` scores "
         "the run against these (primary) and against `results/prereg_v2` (also reported, "
         "unchanged).", "",
         f"- Code: commit `{res['code']['commit']}`"
         + (" (clean tree)" if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}") + ".",
         "- Calibration inputs (sha256 prefix): " + ", ".join(
             f"`{k.split('/')[-1]}` {v}" for k, v in c["inputs"].items()) + " (same as v2).",
         f"- Cost model from {c['cost_from']}: t_fixed {c['t_fixed_ms']:.2f} ms, per "
         f"sequence {c['t_per_seq_ms']:.3f} ms, GEMM efficiency {c['mfu']:.2f}, attention "
         f"efficiency {c['attn_mfu']:.3f}. Server: {c['server_facts']}.",
         f"- Tokens: {c['tokens_from']}.",
         "- Fit on outcomes (all from the October 19 T4 run, none from any later run):"]
    L += [f"  - {x}." for x in c["fit_on_outcomes"]]
    L += [f"- Sets: **P1 (primary)**, seq_cap {c['seq_cap']['P1']}; P0, no seq_cap; P1-alt, "
          f"seq_cap {c['seq_cap']['P1-alt']}.",
          "- B4 arms: `prio-bets/spec+bad` is `vllm-priority` with only bets at priority 1 "
          "(simulated as mark_spec 'guesses', as the plugin arms). `proxy/spec+bad` and "
          "`proxy-sem/spec+bad` are stock FCFS with a client-side cap on decoys "
          "(`sweep_predict.ProxySim`: window counts calls in flight plus roots at the server; "
          "semaphore counts decoys in flight; cap 8). `fcfs-b4` and `plugin-b4` are "
          "simulated as `fcfs` and `plugin`; in the sim they equal those arms exactly, on "
          "the GPU they are separate launches.",
          "- One deterministic simulator run per point: no repeats, no CIs. The client's CPU "
          "is not modelled.", "",
          "## Changes from v2", ""]
    L += [f"- {x}" for x in WHY]
    L += ["", "| set | v2 claims | claims moved > 5e-4 | rows compared | rows moved |",
          "|---|---|---|---|---|"]
    for key, v in ch["sets"].items():
        L.append(f"| {key} | {v['claims_v2']} | {len(v['moved'])} | {v['rows_compared']} | "
                 f"{v['rows_moved']} |")
    moved = [(k, x) for k, v in ch["sets"].items() for x in v["moved"]]
    if moved:
        L += ["", "| set | claim | v2 | v3 |", "|---|---|---|---|"]
        L += [f"| {k} | {x['id']} | {x['v2']} | {x['v3']} |" for k, x in moved]
    L += ["", "C2 claims that moved (general_predictions.json):", "",
          "| claim | v2 | v3 | bound |", "|---|---|---|---|"]
    L += [f"| {x['n']} | {x['v2']:.3f} | {x['v3']:.3f} | {x['bound']} |" for x in ch["general"]]
    L += ["", f"New claims ({len(ch['new_claims'])}): " + ", ".join(ch["new_claims"]) + ".", "",
          "## B4. Fairer baselines (P1; P0 in brackets)", "",
          "| arm | agents | session p50 s | root TPOT p50 ms | vs fcfs-b4: session p50 | "
          "root TPOT p50 | decoys rejected |", "|---|---|---|---|---|---|---|"]
    p1 = res["sets"]["P1"]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    p0 = {(r["arm"], r["agents"]): r for r in res["sets"]["P0"]["summary"]["rows"]}
    rej = {(x["arm"], x["agents"]): x["frac"] for x in p1["decoy_rejected"]}
    for name in vb.BASELINE_ARMS:
        for n in B4_LOADS:
            r, q, ref = rows[(name, n)], p0[(name, n)], rows[(vb.BASELINE_REF, n)]
            L.append(f"| {name} | {n} | {r['session_p50']:.2f} [{q['session_p50']:.2f}] | "
                     f"{r['root_tpot_p50']:.1f} [{q['root_tpot_p50']:.1f}] | "
                     f"{r['session_p50'] / ref['session_p50']:.3f} | "
                     f"{r['root_tpot_p50'] / ref['root_tpot_p50']:.3f} | "
                     f"{vb._fmt(rej.get((name, n)))} |")
    px = [x for x in p1.get("proxy", [])]
    if px:
        L += ["", "Client-side cap in the simulation (P1): " + "; ".join(
            f"{x['arm']} at {x['agents']}: {x['bets_refused']} of "
            f"{x['bets_sent'] + x['bets_refused']} decoys refused" for x in px) + "."]
    L += ["", body]
    return "\n".join(L)


if __name__ == "__main__":
    main()
