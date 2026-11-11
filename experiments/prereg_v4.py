"""Pre-registered simulator predictions for the pressure run (the
`pressure` preset of kaggle/vllm_bench.py on the T4), written before any GPU run of it.

The cells: the preset's 9 arms at 4 agents (experiments/pressure.py ARMS), on the T4
config that experiments/pressure.choose_config picks from the stock FCFS arms, and on its
fallback (half the blocks) in case the probe shows no pressure. One directory per config,
each scored on its own by experiments/prereg_compare.py (--prereg DIR --also ''):
  results/prereg_v4           the chosen config
  results/prereg_v4_fallback  the fallback config
The choice is recomputed here from the code and checked against results/pressure.

Calibration: prereg_v3's, not refit (its files are checked against their prereg commit);
sets P1 (primary), P0 and P1-alt as in v3. Simulator settings: pressure.setting. Claims in
v3's format: ratios (prereg_v2.ratio_claims, tol 0.05) and shares of decoys rejected (tol
0.10), scored by v3's rules, unchanged.

  PYTHONPATH=. .venv/bin/python experiments/prereg_v4.py
      [--out results/prereg_v4] [--out-fallback results/prereg_v4_fallback]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import pressure as PR
import prereg_compare as PC
import prereg_v2 as P2
from prereg_v2 import vb

ROOT = P2.ROOT
OUT = ROOT / "results" / "prereg_v4"
OUT_FALLBACK = ROOT / "results" / "prereg_v4_fallback"
V3 = ROOT / "results" / "prereg_v3"
N = PR.AGENTS
REF = PR.REF
GATED = ["cap-p/spec+bad", "plugin-p/spec+bad", "cap-p/both", "plugin-p/both"]


def models() -> dict:
    """prereg_v3's three sets: P1 (its seq_cap fit), P0 (no seq_cap), P1-alt (runner-up)."""
    caps = json.loads((V3 / "predictions.json").read_text())["calibration"]["seq_cap"]
    return {"P1": PR.model(caps["P1"]), "P0": PR.model(math.inf),
            "P1-alt": PR.model(caps["P1-alt"])}


def check_v3() -> dict:
    """prereg_v3's files against the sha256 of its prereg commit (prereg_compare's table)."""
    got = {k: ("match" if hashlib.sha256((V3 / k).read_bytes()).hexdigest() == want
               else "MISMATCH") for k, want in PC.PREREG_SHA256["prereg_v3"].items()}
    if "MISMATCH" in got.values():
        raise SystemExit(f"results/prereg_v3 does not match its prereg commit: {got}")
    return got


def choice() -> tuple[dict, dict, dict]:
    """pressure.py's T4 config and fallback, from the stock FCFS arms (P1), recomputed."""
    m = PR.model()
    peak = PR.simulate(m, REF, PR.DEFAULT)["max_kv_blocks"]
    configs = PR.grid_configs(peak)
    fcfs = {(PR.key(c), a): PR.simulate(m, a, c) for c in configs for a in PR.FCFS_ARMS}
    chosen, _ = PR.choose_config(fcfs, configs)
    half = math.ceil(chosen["kv_blocks"] / 2)
    fallback = {**chosen, "kv_frac": round(half / peak, 4), "kv_blocks": half}
    max_len = 128 * math.ceil(2 * max(PR.longest_request(m).values()) / 128)
    out = {"chosen": PR.t4_config(chosen, max_len), "fallback": PR.t4_config(fallback, max_len)}
    committed = ROOT / "results" / "pressure" / "choice.json"
    if committed.exists():
        c = json.loads(committed.read_text())
        if any(c[k]["flags"] != out[k]["flags"] for k in out):
            raise SystemExit(f"the choice differs from results/pressure: {out} vs {c}")
    return out["chosen"], out["fallback"], {"kv_peak_blocks": peak,
                                            "checked_against": str(committed.relative_to(ROOT))
                                            if committed.exists() else None}


# ----------------------------------------------------------------------------- claims
def claims(rows: dict, dec: dict) -> list[dict]:
    c = P2.ratio_claims(rows, "PR", "each arm vs fcfs-p/spec+bad",
                        [(a, REF, N) for a in PR.ARMS if a != REF],
                        ("session_p50", "root_tpot_p50"))
    c += P2.ratio_claims(rows, "PC", "plugin vs the client-side cap (the decision rule's ratio)",
                         [("plugin-p/spec+bad", "cap-p/spec+bad", N),
                          ("plugin-p/both", "cap-p/both", N)], ("session_p50", "root_tpot_p50"))
    c += P2.ratio_claims(rows, "PP", "plugin vs vLLM priority",
                         [("plugin-p/spec+bad", "prio-p/spec+bad", N),
                          ("plugin-p/both", "prio-p/both", N)], ("session_p50",))
    for arm in GATED:
        if (arm, N) in dec:
            c.append({"id": "PF", "section": "decoys rejected", "kind": "fraction", "arm": arm,
                      "agents": N, "outcome": "rejected", "predicted": dec[(arm, N)],
                      "tol": P2.FRAC_TOL})
    seen: dict[str, int] = {}
    for x in c:
        seen[x["id"]] = seen.get(x["id"], 0) + 1
        x["id"] = f"{x['id']}-{seen[x['id']]}"
    return c


PRESSURE_KEYS = ("preemptions", "bets_dropped", "max_waiting", "max_running", "max_kv",
                 "max_kv_blocks", "queue_frac", "decoys_refused", "decoys_dropped",
                 "real_bets_refused", "real_bets_dropped", "reissued", "shadow_stops")


def predict(ms: dict, cfg: dict) -> dict:
    """Every arm on one config, per set: the summary rows, claims and pressure metrics."""
    sets = {}
    for name, m in ms.items():
        pts = {a: PR.simulate(m, a, cfg) for a in PR.ARMS}
        runs = [p["_rec"] for p in pts.values()]
        summ = vb.summarize(runs, boot=0)
        rows = {(r["arm"], r["agents"]): r for r in summ["rows"]}
        dec = P2.decoy_rejected(runs)
        sets[name] = {"seq_cap": m["seq_cap"], "summary": summ,
                      "claims": claims(rows, dec),
                      "decoy_rejected": [{"arm": k[0], "agents": k[1], "frac": v}
                                         for k, v in sorted(dec.items())],
                      "pressure": [{"arm": a, "agents": N, **{k: p[k] for k in PRESSURE_KEYS}}
                                   for a, p in pts.items()],
                      "d1": PR.d1({(PR.key(cfg), a): p for a, p in pts.items()}, cfg)}
        print(f"{name:6s} {PR.label(cfg)}: " + ", ".join(
            f"{a} {p['session_p50']:.2f}" for a, p in pts.items()), flush=True)
    return sets


def gpu_minutes(summ: dict) -> dict:
    """vllm_bench.plan's estimate for the pressure preset as planned (9 arms
    at 4 agents, 3 repeats, 2 launches per server, a warm pass per launch; the preset
    itself is added with the run). Session times from P1; the warm pass at the 4-agent time."""
    p50 = {r["arm"]: r["session_p50"] for r in summ["rows"]}
    turns = vb.WORKLOADS["mix4"]["turns"]
    run = {a: turns * p50[a] * vb.TAIL + vb.RUN_OVERHEAD_S for a in PR.ARMS}
    servers: dict = {}
    for a, (_, _, arm) in PR.ARMS.items():
        servers.setdefault(arm.server, []).append(a)
    total = sum(3 * run[a] for a in PR.ARMS)
    total += 2 * len(servers) * vb.SERVER_START_S + vb.SERVER_START_S  # + one cache fill
    total += sum(2 * run[arms[0]] for arms in servers.values())  # warm passes
    return {"runs": 3 * len(PR.ARMS), "launches": 2 * len(servers),
            "est_minutes": round(total / 60), "servers": servers}


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--out-fallback", default=str(OUT_FALLBACK))
    a = ap.parse_args()
    t0 = time.time()
    v3_files = check_v3()
    git = P2.git_state()
    git["dirty_files"] = [x for x in git["dirty_files"] if "results/prereg_v4" not in x]
    chosen, fallback, how = choice()
    v3 = json.loads((V3 / "predictions.json").read_text())
    ms = models()
    for which, cfg, other, out in (("chosen", chosen, fallback, Path(a.out)),
                                   ("fallback", fallback, chosen, Path(a.out_fallback))):
        out.mkdir(parents=True, exist_ok=True)
        sets = predict(ms, cfg)
        res = {
            "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": "PREDICTED by the simulator before any GPU run of the pressure preset, "
                     f"on the {which} T4 config",
            "version": "v4" if which == "chosen" else "v4-fallback",
            "code": {**git, "script": "experiments/prereg_v4.py"},
            "primary": "P1",
            "config": {**cfg, "role": which}, "other_config": {**other},
            "choice": {**how, "rule": "experiments/pressure.choose_config, stock FCFS arms only"},
            "probe": PROBE,
            "decision_rule": DECISION,
            "based_on": {"prereg_v3_commit": "2e39a4d", "prereg_v3_files": v3_files,
                         "prereg_v3_stamp": v3["stamp_utc"]},
            "calibration": {k: v3["calibration"][k] for k in
                            ("inputs", "cost_from", "tokens_from", "server_facts", "t_fixed_ms",
                             "t_per_seq_ms", "mfu", "attn_mfu", "client_s", "seq_cap")},
            "arms": {n: {"server": arm.server, "mode": arm.mode, "decoys": arm.decoys,
                         "tags": arm.tags, "gate": arm.gate or None, "workload": wl or "-",
                         "setting": _jsonable(PR.setting(n, cfg))}
                     for n, (_, wl, arm) in PR.ARMS.items()},
            "sets": sets,
            "summary": sets["P1"]["summary"],
            "overhead": [],
            "general": {"claims": [], "quick_claims": []},
            "rules": {k: v3["rules"][k] for k in ("validity", "ratio", "fraction", "points")}
            | {"pressure": RULE_PRESSURE},
            "reading_rules": READING,
            "gpu_minutes": gpu_minutes(sets["P1"]["summary"]),
        }
        res["wall_s"] = time.time() - t0
        (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
        (out / "predictions.md").write_text(markdown(res))
        print(f"wrote {out}", flush=True)


def _jsonable(s: dict) -> dict:
    return {k: (_jsonable(v) if isinstance(v, dict) else
                str(v) if isinstance(v, float) and math.isinf(v) else v) for k, v in s.items()}


PROBE = ("Before the main sweep: one launch of the fcfs_p server on the chosen config, then "
         "fcfs-p/spec and fcfs-p/spec+bad at 4 agents, once each. If fcfs-p/spec+bad shows "
         "neither a preemption (vllm:num_preemptions) nor a queue (vllm:num_requests_waiting "
         "> 0 in any 1-second sample), the sweep runs on the fallback config and is scored "
         "against results/prereg_v4_fallback; otherwise on the chosen config, scored against "
         "results/prereg_v4. The predicted probe values are each set's `pressure` rows.")
DECISION = ("The rule: the plugin wins if its session p50 is at least 5% below the cap's at 4 "
            "agents, in either workload (plugin-p/spec+bad vs cap-p/spec+bad, or "
            "plugin-p/both vs cap-p/both), with the pressure check passed. Decided on the "
            "measured values, not on these claims' verdicts. Each set's `d1` is the "
            "simulated answer.")
RULE_PRESSURE = ("Claims PR, PC, PP use v3's ratio rule and PF v3's fraction rule (decoys "
                 "logged rejected, which includes a bet dropped before its first token). The "
                 "denominators are fcfs-p/spec+bad (PR), cap (PC) and priority (PP), all at 4 "
                 "agents on the same config. No point here is in-sample for P1: its seq_cap "
                 "was fit on the October 19 rows, none of them a pressure arm.")
READING = [
    "**Pooled p50s sit on pattern clusters.** The 16 sessions of a run are 4 of each mix4 "
    "pattern, and patterns differ by up to 3x in session time. The pooled p50 is the "
    "lowest session of the third-fastest pattern, so a small change in one pattern can "
    "move it a lot. Read every session_p50 claim with `prereg_compare.py`'s per-pattern "
    "ratios (geometric mean over patterns).",
    "**Why cap and plugin lose in `both`.** In mix4 the shadow forces nearly every "
    "speculation, and spec-ptc's shadow stops for the rest of the turn when it forces a "
    "refused bet (shadow.py _abort('force-failed')). The window of 8 refuses most real bets "
    "at 4 agents, so these arms run close to no speculation: the claims predict "
    "cap-p/both and plugin-p/both well above fcfs-p/spec+bad (PR) and the plugin well "
    "above priority (PP-2). Simulated with the shadow re-running a refused call instead, "
    "the loss would be far smaller (results/pressure README, sensitivity 'reissue').",
    "**What the claims cannot show.** PC-1..4 test the decision rule's ratios, but the "
    "rule is applied to the measured values. A claim refuted in the plugin's favour can "
    "still leave the rule unmet, and the reverse.",
    "**The sim's KV model under heavy preemption is unchecked** (a known risk): "
    "the probe values (preemptions, queue, KV peak) are predictions too, not inputs.",
]


# ----------------------------------------------------------------------------- markdown
def markdown(res: dict) -> str:
    c = res["config"]
    p1 = res["sets"]["P1"]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    other = {k: {(r["arm"], r["agents"]): r for r in st["summary"]["rows"]}
             for k, st in res["sets"].items() if k != "P1"}
    pres = {x["arm"]: x for x in p1["pressure"]}
    d = p1["d1"]
    L = [f"# Pre-registered predictions for the pressure run ({res['version']})", "",
         f"**PREDICTED by the simulator, not measured.** Written {res['stamp_utc']} by "
         "`experiments/prereg_v4.py`, before any GPU run of the pressure preset. "
         "Not edited after the run; `experiments/prereg_compare.py --prereg "
         f"results/prereg_{res['version'].replace('-', '_')} --also ''` scores it.", "",
         f"- Code: commit `{res['code']['commit']}`"
         + (" (clean tree)" if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}") + ".",
         f"- **T4 config ({c['role']}): `{c['flags']}`** ({PR.label(c)}). "
         + ("The fallback, used only if the probe shows no pressure: "
            f"`{res['other_config']['flags']}`." if c["role"] == "chosen" else
            f"Used only if the probe on the chosen config (`{res['other_config']['flags']}`) "
            "shows no pressure."),
         f"- Chosen by {res['choice']['rule']} (fcfs-p/spec+bad's simulated KV peak on the "
         f"default server: {res['choice']['kv_peak_blocks']} blocks); "
         + (f"same as `{res['choice']['checked_against']}`." if res['choice']['checked_against']
            else "results/pressure not written yet."),
         f"- Calibration: prereg_v3's, not refit (its files match their prereg commit "
         f"{res['based_on']['prereg_v3_commit']}: {res['based_on']['prereg_v3_files']}). "
         "Sets: **P1 (primary)**, seq_cap " + ", ".join(
             f"{k} {st['seq_cap']}" for k, st in res["sets"].items()) + ".",
         "- One deterministic simulator run per point: no repeats, no CIs. The client's CPU "
         "is not modelled.", "",
         "## Arms", "",
         "| arm | server | tags | client cap | workload | simulator |", "|---|---|---|---|---|---|"]
    for n, x in res["arms"].items():
        s = x["setting"]
        sim = (s["cfg"].get("policy", "fcfs") + (" + plugin_semantics" if
                                                  s["cfg"].get("plugin_semantics") else ""))
        if x["workload"] != "-":
            sim += (f", bets: {'every speculative call' if s['mark_spec'] == 'all' else 'decoys'}"
                    + (f", proxy bets {s['proxy_bets']}" if s.get("proxy") else ""))
        L.append(f"| {n} | {x['server']} | {x['tags']} | {x['gate'] or '-'} | {x['workload']} "
                 f"| {sim} |")
    L += ["", "Every arm: only bets tagged (tag_early False), a decoy started by its real call "
          "(decoy_at_call), and a forced refused bet stops the shadow (rejected_force abort).",
          "", "## Probe", "", res["probe"], "",
          "| arm | preemptions | max waiting | KV peak (share) | queue (time) |",
          "|---|---|---|---|---|"]
    for a in ("fcfs-p/spec", "fcfs-p/spec+bad"):
        x = pres[a]
        L.append(f"| {a} | {x['preemptions']:.0f} | {x['max_waiting']:.0f} | "
                 f"{x['max_kv']:.2f} | {100 * x['queue_frac']:.0f}% |")
    L += ["", "## The decision (simulated)", "", res["decision_rule"], "",
          "| workload | plugin vs cap | plugin vs priority |", "|---|---|---|"]
    for wl, v in d["by_workload"].items():
        L.append(f"| {wl} | {v['plugin_vs_cap']:.3f} | {v['plugin_vs_prio']:.3f} |")
    L += ["", "Simulated: " + ("**the plugin wins** (" + ", ".join(d["won_in"]) + ")."
                               if d["plugin_wins"] else "**the plugin does not win**.") + " "
          + "P0 / P1-alt: " + "; ".join(
              f"{k} " + " / ".join(f"{v['plugin_vs_cap']:.3f}"
                                   for v in st["d1"]["by_workload"].values())
              for k, st in res["sets"].items() if k != "P1") + " (plugin vs cap, decoys / both).",
          "", "## Rows (P1; P0 in brackets)", "",
          "| arm | session p50 s | vs fcfs-p/spec+bad | root TPOT p50 ms | decoys rejected | "
          "real bets refused | preemptions | bets dropped | max waiting | KV peak blocks |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    ref = rows[(REF, N)]
    for a in PR.ARMS:
        r, q, x = rows[(a, N)], other["P0"][(a, N)], pres[a]
        L.append(f"| {a} | {r['session_p50']:.2f} [{q['session_p50']:.2f}] | "
                 f"{r['session_p50'] / ref['session_p50']:.3f} | {r['root_tpot_p50']:.1f} "
                 f"[{q['root_tpot_p50']:.1f}] | {vb._fmt(x['decoys_refused'])} | "
                 f"{vb._fmt(x['real_bets_refused'])} | {x['preemptions']:.0f} | "
                 f"{x['bets_dropped']} | {x['max_waiting']:.0f} | {x['max_kv_blocks']} |")
    L += ["", "## Claims (P1 predicted; P0, P1-alt in brackets)", "",
          "| id | section | claim | predicted | tol |", "|---|---|---|---|---|"]
    alts = {k: {x["id"]: x["predicted"] for x in st["claims"]}
            for k, st in res["sets"].items() if k != "P1"}
    for x in p1["claims"]:
        alt = ", ".join(f"{alts[k][x['id']]:.3f}" for k in alts)
        if x["kind"] == "ratio":
            what = (f"{x['numerator'][0]} / {x['denominator'][0]} at {x['numerator'][1]}: "
                    f"{x['metric']}")
        else:
            what = f"{x['arm']} at {x['agents']}: share of decoys rejected"
        L.append(f"| {x['id']} | {x['section']} | {what} | {x['predicted']:.3f} [{alt}] | "
                 f"{x['tol']} |")
    g = res["gpu_minutes"]
    L += ["", "## Rules (v3's, unchanged)", ""]
    L += [f"- **{k}.** {v}" for k, v in res["rules"].items()]
    L += ["", "## How to read these (fixed before the run)", ""]
    L += [f"- {x}" for x in res["reading_rules"]]
    L += ["", "## GPU time (estimate)", "",
          f"{g['runs']} runs on {g['launches']} launches, about {g['est_minutes']} min with "
          "`vllm_bench.plan`'s constants (warm passes and one cache-filling launch included; "
          "the probe not).", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
