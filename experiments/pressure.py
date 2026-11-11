"""The simulated pressure study: under KV pressure and a real queue, with bets that
are sometimes needed, does the sptc plugin beat a client-side cap and vLLM priority?
SIMULATED, before any GPU run of the pressure preset. Also picks that run's T4 config,
from the stock FCFS arms only.

Calibration: prereg_v3's P1 as it is, nothing refit: sweep_predict.calibrate (cost model
and client overhead, checked against results/prereg_v3/predictions.json), the per-call
token tables and traces, and P1's seq_cap read from prereg_v3.

Arms, 4 agents, mix4, 4 turns (named as the bench's pressure preset will name them):
  fcfs    stock vLLM FCFS
  prio    vLLM priority scheduling, only the bets at priority 1 (tag scheme priority_bets)
  cap     stock FCFS behind run 2's client-side window cap of 8 (sweep_predict.ProxySim)
  plugin  prereg_v3's plugin setting, only the bets tagged (PolicyCfg.tag_early False: the
          class as the drafted RFC had it, tag scheme sptc_bets)
  references on stock FCFS: nospec (no speculation) and spec (speculation, no decoys)
Workloads:
  decoys  run 2's: one decoy per real speculative call, forced to max length, never used.
          The real speculative calls are not bets and go untagged
  both    the real speculative calls are bets too, each with one decoy: both arms of a
          branch launched, one used (a 50% bet hit rate). A refused or dropped real bet is
          re-run when the real run claims it; if the shadow forces it first, the shadow
          stops for the rest of the turn (spec-ptc with the sptc-hints patch:
          PolicyCfg.rejected_force abort). On stock FCFS `both` is `decoys` (tags are
          ignored and nothing is refused), so there is no fcfs-p/both arm (checked)
Grid: KV blocks 1x, 0.75x and 0.5x of fcfs-p/spec+bad's simulated KV peak at 4 agents on
the default server, plus the default (85,904 tokens); max_num_seqs 256, 32, 16.

The T4 config (choose_config) is decided from the fcfs arms and written to the output
before any other arm is simulated under pressure. Fallback: the same with half the blocks.

  PYTHONPATH=. .venv/bin/python experiments/pressure.py [--out results/pressure] [--fcfs-only]
writes choice.json, then grid.csv, grid.json and README.md (--fcfs-only: choice.json only).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

import prereg_v2 as P2
from prereg_v2 import t4, vb, w2

from sptc_sim import suite
from sptc_sim.trace import compile_turn

ROOT = P2.ROOT
OUT = ROOT / "results" / "pressure"
V3 = ROOT / "results" / "prereg_v3"
AGENTS = 4
CAP = f"window:{vb.PLUGIN_CFG['sptc']['free_window']}"  # run 2's cap, fixed in advance
KV_FRACS = (1.0, 0.75, 0.5)
SEQS = (256, 32, 16)
DEFAULT = {"kv_frac": None, "kv_blocks": w2.KV_TOKENS // w2.BLOCK, "max_num_seqs": t4.SEQS}
RULE_MARGIN = 0.05  # the rule: the plugin wins if its session p50 is >= 5% below the cap's
# choose_config's thresholds (per run of 16 sessions; queue: share of the run's time)
CLEAR = {"preemptions": 16, "queue_frac": 0.25}
QUIET = {"preemptions": 2, "queue_frac": 0.05}

# name -> (kind, workload, the bench arm). kaggle/vllm_bench.py runs them on the GPU.
ARMS = {
    "fcfs-p/nospec": ("fcfs", None, vb.Arm("fcfs-p/nospec", "fcfs_p", "baseline", 0, "none")),
    "fcfs-p/spec": ("fcfs", None, vb.Arm("fcfs-p/spec", "fcfs_p", "spec", 0, "none")),
    "fcfs-p/spec+bad": ("fcfs", "decoys", vb.Arm("fcfs-p/spec+bad", "fcfs_p", "spec", 1, "none")),
    "prio-p/spec+bad": ("prio", "decoys", vb.Arm("prio-p/spec+bad", "priority_p", "spec", 1,
                                                 "priority_bets")),
    "cap-p/spec+bad": ("cap", "decoys", vb.Arm("cap-p/spec+bad", "fcfs_p", "spec", 1, "none",
                                               gate=CAP)),
    "plugin-p/spec+bad": ("plugin", "decoys", vb.Arm("plugin-p/spec+bad", "plugin_p", "spec", 1,
                                                     "sptc_bets")),
    "prio-p/both": ("prio", "both", vb.Arm("prio-p/both", "priority_p", "spec", 1,
                                           "priority_bets")),
    "cap-p/both": ("cap", "both", vb.Arm("cap-p/both", "fcfs_p", "spec", 1, "none", gate=CAP)),
    "plugin-p/both": ("plugin", "both", vb.Arm("plugin-p/both", "plugin_p", "spec", 1,
                                               "sptc_bets")),
}
FCFS_ARMS = ["fcfs-p/nospec", "fcfs-p/spec", "fcfs-p/spec+bad"]
REF = "fcfs-p/spec+bad"  # every ratio's denominator, as the bench's Pressure table
D1_ARMS = {"decoys": ("plugin-p/spec+bad", "cap-p/spec+bad", "prio-p/spec+bad"),
           "both": ("plugin-p/both", "cap-p/both", "prio-p/both")}


# ----------------------------------------------------------------------------- simulation
def setting(name: str, cfg: dict, **over) -> dict:
    """The simulator setting of a pressure arm on one server config (sweep_predict.sim_run).
    In `both` every speculative call is a bet (mark_spec all), else only the decoys."""
    kind, workload, _ = ARMS[name]
    both = workload == "both"
    s = {"cfg": {k: cfg[k] for k in ("kv_blocks", "max_num_seqs")},
         "mark_spec": "all" if both else "guesses", "promote_early": False,
         "tag_early": False, "rejected_force": "abort", "decoy_at_call": True}
    if kind == "prio":
        s["cfg"]["policy"] = "vllm-priority"
    elif kind == "cap":
        s |= {"proxy": CAP, "proxy_bets": "spec" if both else "decoys"}
    elif kind == "plugin":
        s["cfg"] = P2.setting(vb.ARM["plugin/spec+bad"])["cfg"] | s["cfg"]
    return s | over


def simulate(model: dict, name: str, cfg: dict, **over) -> dict:
    arm = ARMS[name][2]
    rec = w2.sim_run(model["cost"], model["tables"], arm, AGENTS, model["traces"],
                     vb.WORKLOADS[arm.workload]["turns"], lambda a: setting(name, cfg, **over))
    return point(rec)


def _share(xs: list[str], what: str) -> float | None:
    return sum(x == what for x in xs) / len(xs) if xs else None


def point(rec: dict) -> dict:
    """One simulated run: the bench's summary row, and the pressure it saw."""
    row = vb.summarize([rec], boot=0)["rows"][0]
    ses = rec["sessions"]
    dec = [d["outcome"] for s in ses for d in s["decoys"]]
    real = [b["outcome"] for s in ses for b in s["real_bets"]]
    m = rec["server_metrics"]
    return {**{k: row[k] for k in ("session_p50", "session_p99", "root_tpot_p50",
                                   "root_tpot_p99", "decoy_outcomes")},
            "decoys": len(dec), "decoys_refused": _share(dec, "rejected"),
            "decoys_dropped": _share(dec, "dropped"), "real_bets": len(real),
            "real_bets_refused": _share(real, "rejected"),
            "real_bets_dropped": _share(real, "dropped"),
            "reissued": sum(s["reissued"] for s in ses),
            "shadow_stops": sum(s["shadow_stopped"] for s in ses),
            "preemptions": m["preemptions"], "bets_dropped": rec["sim_bets_dropped"],
            "max_waiting": m["max_waiting"], "max_running": m["max_running"],
            "max_kv_blocks": rec["sim_max_kv_blocks"], "max_kv": m["max_kv"],
            "queue_frac": rec["sim_queue_frac"], "queue_mean": rec["sim_queue_mean"],
            "makespan_s": rec["makespan_s"], "session_walls": [s["wall_s"] for s in ses],
            "_rec": rec}


def model(seq_cap: float | None = None) -> dict:
    """prereg_v3's calibration, checked against its predictions.json, with P1's seq_cap
    (or the one given: P0 is math.inf, P1-alt prereg_v3's runner-up)."""
    v3 = json.loads((V3 / "predictions.json").read_text())["calibration"]
    cost0, tables, client_s = w2.calibrate()
    got = {"t_fixed_ms": 1000 * cost0.ov.t_fixed, "t_per_seq_ms": 1000 * cost0.ov.t_per_seq,
           "mfu": cost0.ov.mfu, "attn_mfu": cost0.ov.attn_mfu, "client_s": client_s}
    if any(got[k] != v3[k] for k in got):
        raise SystemExit(f"calibration differs from prereg_v3: {got} vs "
                         f"{ {k: v3[k] for k in got} }")
    cap = v3["seq_cap"]["P1"] if seq_cap is None else seq_cap
    cost = w2.CappedStepCost(cost0.gpu, cost0.model, cost0.tp, cost0.ov, cost0.decode_table,
                             seq_cap=cap)
    mix = vb.WORKLOADS["mix4"]["patterns"].split(",")
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4) for n in mix}
    return {"cost": cost, "tables": tables, "traces": traces, "seq_cap": cap,
            "calibration": got, "seq_caps_v3": {k: v3["seq_cap"][k] for k in ("P1", "P1-alt")}}


# ----------------------------------------------------------------------------- configs
def key(cfg: dict) -> str:
    return f"kv{cfg['kv_blocks']}/seqs{cfg['max_num_seqs']}"


def label(cfg: dict) -> str:
    kv = "default KV" if cfg["kv_frac"] is None else f"{cfg['kv_frac']:g}x peak"
    return f"{kv} ({cfg['kv_blocks']} blocks), {cfg['max_num_seqs']} seqs"


def grid_configs(peak: int) -> list[dict]:
    """Mildest first: the default KV, then 1x, 0.75x, 0.5x of the peak; seqs 256, 32, 16."""
    kvs = [DEFAULT] + [{"kv_frac": f, "kv_blocks": round(f * peak)} for f in KV_FRACS]
    return [{**kv, "max_num_seqs": s} for kv in kvs for s in SEQS]


def longest_request(m: dict) -> dict:
    """The bench's longest request, prompt + max_tokens: a root (COUNT prompt with the
    run prefix, max_tokens the response's tokens) or a sub-call (measured prompt with the
    prefix, max_tokens the pattern's sub_max_tokens; a decoy adds ' [alt 0]')."""
    pats = vb.WORKLOADS["mix4"]["patterns"].split(",")
    root = max(w2.ROOT_PROMPT + math.ceil(len(suite.response_text(n)) / 4) for n in pats)
    sub = max(p + w2.SALT_TOKENS + suite.patterns()[n].sub_max_tokens
              for n in pats for p, _ in m["tables"][n].values())
    return {"root": root, "sub_call": sub, "decoy": sub + 3}


def t4_config(cfg: dict, max_len: int) -> dict:
    """vLLM flags. vLLM keeps one of the --num-gpu-blocks-override blocks as its null
    block (block_pool.py get_usage), so the override is the simulated blocks + 1."""
    blocks = cfg["kv_blocks"] + 1
    if blocks * w2.BLOCK < max_len:
        raise SystemExit(f"{blocks} blocks hold less than --max-model-len {max_len}")
    return {**cfg, "num_gpu_blocks_override": blocks, "max_model_len": max_len,
            "flags": f"--num-gpu-blocks-override {blocks} --max-num-seqs "
                     f"{cfg['max_num_seqs']} --max-model-len {max_len}"}


def choose_config(fcfs: dict, configs: list[dict]) -> tuple[dict, list[dict]]:
    """The T4 config, from the stock FCFS arms only: the mildest
    config where fcfs-p/spec+bad preempts or queues clearly and fcfs-p/spec barely does,
    so that wasted speculation creates the pressure.
      clearly  >= CLEAR preemptions per run, or a queue >= CLEAR queue_frac of the run's time
      barely   <= QUIET preemptions and a queue <= QUIET queue_frac of the time
      mildest  the smallest fcfs-p/spec+bad slowdown against the default server (to 0.1%);
               then the most blocks, then the most seqs
    fcfs: {(config key, arm): point}. Returns the chosen config and the table behind it."""
    d = key(DEFAULT)
    table = []
    for cfg in configs:
        bad, spec = fcfs[(key(cfg), REF)], fcfs[(key(cfg), "fcfs-p/spec")]
        sb = bad["session_p50"] / fcfs[(d, REF)]["session_p50"]
        ss = spec["session_p50"] / fcfs[(d, "fcfs-p/spec")]["session_p50"]
        clear = (bad["preemptions"] >= CLEAR["preemptions"]
                 or bad["queue_frac"] >= CLEAR["queue_frac"])
        quiet = (spec["preemptions"] <= QUIET["preemptions"]
                 and spec["queue_frac"] <= QUIET["queue_frac"])
        table.append({"config": cfg, "key": key(cfg), "clearly": clear, "barely": quiet,
                      "bad_slowdown": sb, "spec_slowdown": ss,
                      **{f"bad_{k}": bad[k] for k in ("preemptions", "queue_frac",
                                                      "max_waiting", "max_kv_blocks")},
                      **{f"spec_{k}": spec[k] for k in ("preemptions", "queue_frac",
                                                        "max_waiting", "max_kv_blocks")}})
    ok = [x for x in table if x["clearly"] and x["barely"]]
    if not ok:
        raise SystemExit("no config passes the selection rule: " + json.dumps(
            [{k: v for k, v in x.items() if k != "config"} for x in table], default=str))
    best = min(ok, key=lambda x: (round(x["bad_slowdown"], 3), -x["config"]["kv_blocks"],
                                  -x["config"]["max_num_seqs"]))
    return best["config"], table


# ----------------------------------------------------------------------------- answer
def d1(points: dict, cfg: dict) -> dict:
    """The decision rule on one config's simulated points: the plugin wins if its
    session p50 is at least RULE_MARGIN below the cap's, in either workload."""
    out = {}
    for wl, (pl, cp, pr) in D1_ARMS.items():
        p = points[(key(cfg), pl)]["session_p50"]
        out[wl] = {"plugin_vs_cap": p / points[(key(cfg), cp)]["session_p50"],
                   "plugin_vs_prio": p / points[(key(cfg), pr)]["session_p50"]}
    won = [wl for wl, v in out.items() if v["plugin_vs_cap"] <= 1 - RULE_MARGIN]
    return {"by_workload": out, "plugin_wins": bool(won), "won_in": won}


CHECK_V3 = {  # pressure arm on the default server -> prereg_v3's row of the same setting
    "fcfs-p/nospec": "fcfs/nospec", "fcfs-p/spec": "fcfs/spec",
    "fcfs-p/spec+bad": "fcfs/spec+bad", "prio-p/spec+bad": "prio-bets/spec+bad",
    "cap-p/spec+bad": "proxy/spec+bad"}


def checks(m: dict, points: dict) -> list[dict]:
    """With v3's decoy timing (decoy_at_call False) the arms on the default server are
    prereg_v3's (the plugin with its early tags put back); fcfs both equals fcfs decoys.
    Every check must hold."""
    v3 = {(r["arm"], r["agents"]): r for r in
          json.loads((V3 / "predictions.json").read_text())["sets"]["P1"]["summary"]["rows"]}
    d = key(DEFAULT)
    pairs = [(points[(d, a)] if not ARMS[a][1] else simulate(m, a, DEFAULT, decoy_at_call=False),
              v3[(b, AGENTS)], f"{a} with v3's decoy timing = prereg_v3 {b}")
             for a, b in CHECK_V3.items()]
    pairs.append((simulate(m, "plugin-p/spec+bad", DEFAULT, tag_early=True, decoy_at_call=False),
                  v3[("plugin/spec+bad", AGENTS)], "plugin-p/spec+bad with early tags and v3's "
                  "decoy timing = prereg_v3 plugin/spec+bad"))
    fb = setting("fcfs-p/spec+bad", DEFAULT) | {"mark_spec": "all"}  # every spec call a bet
    rec = w2.sim_run(m["cost"], m["tables"], ARMS[REF][2], AGENTS, m["traces"],
                     vb.WORKLOADS["mix4"]["turns"], lambda a: fb)
    pairs.append((point(rec), points[(d, REF)], "fcfs both = fcfs-p/spec+bad"))
    out = []
    for a, b, what in pairs:
        same = all(a[k] == b[k] for k in ("session_p50", "root_tpot_p50", "root_tpot_p99"))
        out.append({"check": what, "ok": same, "session_p50": [a["session_p50"],
                                                               b["session_p50"]]})
    if not all(x["ok"] for x in out):
        raise SystemExit(f"consistency checks failed: {out}")
    return out


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--fcfs-only", action="store_true",
                    help="stop after the stock FCFS grid and the choice (choice.json)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    git = P2.git_state()
    git["dirty_files"] = [x for x in git["dirty_files"] if "results/pressure" not in x]
    m = model()
    # 1. the KV peak of stock FCFS with bad guesses on the default server
    base = simulate(m, REF, DEFAULT)
    peak = base["max_kv_blocks"]
    configs = grid_configs(peak)
    # 2. the FCFS arms over the grid, then the T4 config from them alone
    points: dict = {}
    for cfg in configs:
        for name in FCFS_ARMS:
            points[(key(cfg), name)] = simulate(m, name, cfg)
            print(f"{key(cfg):18s} {name:18s} {points[(key(cfg), name)]['session_p50']:6.2f} s",
                  flush=True)
    chosen, table = choose_config(points, configs)
    max_len = 128 * math.ceil(2 * max(longest_request(m).values()) / 128)
    half = math.ceil(chosen["kv_blocks"] / 2)
    fallback = {**chosen, "kv_frac": round(half / peak, 4), "kv_blocks": half}
    choice = {"stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "chosen": t4_config(chosen, max_len), "fallback": t4_config(fallback, max_len),
              "longest_request": longest_request(m), "rule": {"clearly": CLEAR, "barely": QUIET},
              "table": table, "fcfs_only": True}
    (out / "choice.json").write_text(json.dumps(choice, indent=1, default=str))
    print(f"T4 config: {label(chosen)}; fallback {label(fallback)}", flush=True)
    if a.fcfs_only:
        return
    # 3. every other arm, over the grid and on the fallback config
    for cfg in configs + [fallback]:
        for name in ARMS:
            if (key(cfg), name) not in points:
                points[(key(cfg), name)] = simulate(m, name, cfg)
        print(f"{key(cfg):18s} D1 {json.dumps(d1(points, cfg)['by_workload'])}", flush=True)
    res = {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": "SIMULATED, not measured: before any GPU run of the pressure preset",
        "code": {**git, "script": "experiments/pressure.py"},
        "calibration": {**m["calibration"], "seq_cap": m["seq_cap"],
                        "from": "results/prereg_v3 set P1, not refit"},
        "agents": AGENTS, "cap": CAP, "kv_peak_blocks": peak, "configs": configs,
        "choice": choice, "rule_margin": RULE_MARGIN,
        "d1": {key(c): {"config": c, **d1(points, c)} for c in configs + [fallback]},
        "checks": checks(m, points),
        "sensitivity": sensitivity(m, chosen),
        "points": {f"{k[0]}|{k[1]}": {x: y for x, y in v.items() if x != "_rec"}
                   for k, v in points.items()},
    }
    res["wall_s"] = time.time() - t0
    (out / "grid.json").write_text(json.dumps(res, indent=1, default=str))
    write_csv(out / "grid.csv", points, configs + [fallback])
    (out / "README.md").write_text(readme(res, points, configs, chosen, fallback))
    print(f"wrote {out} in {res['wall_s']:.0f} s")


def sensitivity(m: dict, cfg: dict) -> dict:
    """The decision ratios on the chosen config under P0 and P1-alt (prereg_v3's other
    sets), and with a forced rejected bet re-issued at once instead of stopping the shadow
    (rejected_force reissue)."""
    out = {}
    runs = {"P0": (model(math.inf), {}), "P1-alt": (model(m["seq_caps_v3"]["P1-alt"]), {}),
            "P1, reissue": (m, {"rejected_force": "reissue"})}
    for name, (mm, over) in runs.items():
        pts = {(key(cfg), a): simulate(mm, a, cfg, **over)
               for a in [REF] + [a for wl in D1_ARMS.values() for a in wl]}
        ref = pts[(key(cfg), REF)]["session_p50"]
        out[name] = {**d1(pts, cfg), "both_vs_ref": {
            a: pts[(key(cfg), a)]["session_p50"] / ref for a in D1_ARMS["both"]}}
    return out


def write_csv(path: Path, points: dict, configs: list[dict]) -> None:
    cols = ["session_p50", "session_p99", "root_tpot_p50", "root_tpot_p99", "decoys_refused",
            "decoys_dropped", "real_bets_refused", "real_bets_dropped", "reissued",
            "shadow_stops", "preemptions", "bets_dropped", "max_waiting", "max_running",
            "max_kv_blocks", "max_kv", "queue_frac", "queue_mean", "makespan_s"]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kv_frac", "kv_blocks", "max_num_seqs", "arm", "workload",
                    "session_p50_vs_ref"] + cols)
        for cfg in configs:
            ref = points[(key(cfg), REF)]["session_p50"]
            for name in ARMS:
                p = points[(key(cfg), name)]
                w.writerow([cfg["kv_frac"], cfg["kv_blocks"], cfg["max_num_seqs"], name,
                            ARMS[name][1] or "-", round(p["session_p50"] / ref, 4)]
                           + [round(p[c], 4) if isinstance(p[c], float) else p[c] for c in cols])


# ----------------------------------------------------------------------------- README
def _f(x, nd=3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _pct(x) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def arm_table(points: dict, cfg: dict) -> list[str]:
    k = key(cfg)
    ref = points[(k, REF)]
    L = ["| arm | session p50 s | vs fcfs-p/spec+bad: session p50 | p99 | root TPOT p50 | "
         "p99 | decoys refused | real bets refused / dropped | preemptions | bets dropped | "
         "max waiting | KV peak blocks | queue (time) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ARMS:
        p = points[(k, name)]
        rb = "-" if not p["real_bets"] else \
            f"{_pct(p['real_bets_refused'])} / {_pct(p['real_bets_dropped'])}"
        L.append(f"| {name} | {p['session_p50']:.2f} | "
                 + " | ".join(_f(p[m] / ref[m]) for m in ("session_p50", "session_p99",
                                                         "root_tpot_p50", "root_tpot_p99"))
                 + f" | {_pct(p['decoys_refused'])} | {rb} | {p['preemptions']:.0f} | "
                 f"{p['bets_dropped']} | {p['max_waiting']:.0f} | {p['max_kv_blocks']} | "
                 f"{_pct(p['queue_frac'])} |")
    return L


def readme(res: dict, points: dict, configs: list[dict], chosen: dict, fallback: dict) -> str:
    ch, d = res["choice"], res["d1"][key(chosen)]
    verdict = ("**the plugin wins** (by the rule: in " + " and ".join(d["won_in"]) + ")"
               if d["plugin_wins"] else "**the plugin does not win**")
    c = res["calibration"]
    L = ["# KV pressure and a real queue (simulated)", "",
         f"**SIMULATED, not measured.** Written {res['stamp_utc']} by "
         "`experiments/pressure.py`, before any GPU run of the pressure preset. One "
         "deterministic simulator run per point (no repeats, no CIs). Code: commit "
         f"`{res['code']['commit'][:10]}`"
         + (" (clean tree)." if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}."), "",
         f"Calibration: prereg_v3's P1, not refit (client {1000 * c['client_s']:.0f} ms each "
         f"way, seq_cap {c['seq_cap']}). {AGENTS} agents, mix4, 4 turns each. Cap: run 2's "
         f"client-side window cap ({res['cap']}).", "",
         "## The question and the rule", "",
         "Does the plugin beat the client-side cap and vLLM priority under KV pressure and a "
         "real queue, with bets that are sometimes needed? The plugin wins if its session "
         f"p50 is at least {100 * RULE_MARGIN:.0f}% below the cap's at 4 agents, in either "
         "workload, with the pressure check passed.", "",
         "## Answer (simulated)", "",
         f"On the chosen T4 config ({label(chosen)}), {verdict}.", "",
         "| workload | plugin vs cap (session p50) | plugin vs priority |", "|---|---|---|"]
    for wl, v in d["by_workload"].items():
        L.append(f"| {wl} | {v['plugin_vs_cap']:.3f} | {v['plugin_vs_prio']:.3f} |")
    p = {a: points[(key(chosen), a)] for a in ARMS}
    r = {a: p[a]["session_p50"] / p[REF]["session_p50"] for a in ARMS}
    L += ["", f"What happens there. In `decoys` the cap and the plugin refuse "
          f"{_pct(p['cap-p/spec+bad']['decoys_refused'])} and "
          f"{_pct(p['plugin-p/spec+bad']['decoys_refused'])} of the decoys, so the decoys never "
          f"build the KV pressure that preempts fcfs-p/spec+bad {p[REF]['preemptions']:.0f} "
          f"times (KV peaks {p['cap-p/spec+bad']['max_kv_blocks']} and "
          f"{p['plugin-p/spec+bad']['max_kv_blocks']} of {chosen['kv_blocks']} blocks). Both "
          f"run close to fcfs-p/spec ({r['cap-p/spec+bad']:.3f}, "
          f"{r['plugin-p/spec+bad']:.3f}, {r['fcfs-p/spec']:.3f} of fcfs-p/spec+bad), and "
          f"priority, which only reorders, is at {r['prio-p/spec+bad']:.3f}. In `both` they "
          f"refuse {_pct(p['cap-p/both']['real_bets_refused'])} and "
          f"{_pct(p['plugin-p/both']['real_bets_refused'])} of the real bets too. The shadow "
          f"forces nearly every speculation, so it stops in {p['cap-p/both']['shadow_stops']} "
          f"and {p['plugin-p/both']['shadow_stops']} of 16 sessions, and both run close to no "
          f"speculation: {r['cap-p/both']:.3f} and {r['plugin-p/both']:.3f} of "
          f"fcfs-p/spec+bad, with fcfs-p/nospec at {r['fcfs-p/nospec']:.3f}. Priority admits "
          f"every bet and is at {r['prio-p/both']:.3f}."]
    L += ["", "Across the grid (below 1: the plugin is faster; the rule needs <= "
          f"{1 - RULE_MARGIN:.2f} against the cap):", "",
          "| config | pressure check | decoys: plugin vs cap | vs prio | both: plugin vs cap "
          "| vs prio |", "|---|---|---|---|---|---|"]
    tab = {x["key"]: x for x in ch["table"]}
    for cfg in configs:
        x, v = tab[key(cfg)], res["d1"][key(cfg)]["by_workload"]
        pc = "passed" if x["clearly"] and x["barely"] else (
            "no clear pressure" if not x["clearly"] else "fcfs-p/spec under pressure too")
        L.append(f"| {label(cfg)} | {pc} | {v['decoys']['plugin_vs_cap']:.3f} | "
                 f"{v['decoys']['plugin_vs_prio']:.3f} | {v['both']['plugin_vs_cap']:.3f} | "
                 f"{v['both']['plugin_vs_prio']:.3f} |")
    s = res["sensitivity"]
    rs = s["P1, reissue"]["both_vs_ref"]
    L += ["", "Sensitivity on the chosen config (plugin vs cap; decoys / both): "
          + "; ".join(f"{k} {v['by_workload']['decoys']['plugin_vs_cap']:.3f} / "
                      f"{v['by_workload']['both']['plugin_vs_cap']:.3f}"
                      for k, v in s.items()) + ". P0 and P1-alt are prereg_v3's other "
          "calibration sets. 'reissue' re-runs a forced refused bet at once and keeps the "
          "shadow going, where spec-ptc stops it. Most of the gates' loss in `both` is that "
          f"stop: with 'reissue', cap-p/both and plugin-p/both run at "
          f"{rs['cap-p/both']:.3f} and {rs['plugin-p/both']:.3f} of fcfs-p/spec+bad, not "
          f"{r['cap-p/both']:.3f} and {r['plugin-p/both']:.3f}.", "",
          "## The T4 config", "",
          f"- **Chosen: {label(chosen)}.** vLLM flags: `{ch['chosen']['flags']}`.",
          f"- **Fallback (half the blocks), if the probe shows neither preemption nor a "
          f"queue in fcfs-p/spec+bad:** `{ch['fallback']['flags']}`.",
          f"- `--max-model-len {ch['chosen']['max_model_len']}`: twice the bench's longest "
          f"request, rounded up to 128 (roots {ch['longest_request']['root']} tokens, "
          f"sub-calls {ch['longest_request']['sub_call']}, decoys "
          f"{ch['longest_request']['decoy']}; prompt + max_tokens).",
          f"- KV peak of fcfs-p/spec+bad on the default server: {res['kv_peak_blocks']} "
          "blocks (16 tokens each), the grid's 1x. vLLM keeps one block as its null block, "
          "so the override is the simulated blocks + 1.", "",
          "Chosen by `choose_config` from the stock FCFS arms only; the script writes "
          "`choice.json` before it simulates any other arm under pressure. Rule: the mildest "
          "config where fcfs-p/spec+bad preempts or queues clearly and fcfs-p/spec barely "
          f"does. 'clearly': >= {CLEAR['preemptions']} preemptions per run (16 sessions) or "
          f"a queue >= {_pct(CLEAR['queue_frac'])} of the run's time. 'barely': <= "
          f"{QUIET['preemptions']} preemptions and a queue <= {_pct(QUIET['queue_frac'])} of "
          "the time. Mildest: the smallest fcfs-p/spec+bad slowdown against the default "
          "server (equal to 0.1%: the most blocks, then the most seqs).", "",
          "How the rule was set: the thresholds were written before any run. Two changes "
          "followed, both before this run. (1) A scratch run of every arm showed the cap and "
          "the plugin refusing real bets far more often than decoys in `both`: a burst's "
          "decoys all reached the gate before its real calls. The bench starts each decoy "
          "inside its real call, so the arms now use `decoy_at_call`, a fidelity fix to the "
          "simulator, not a choice of config. (2) Under that timing, 256 blocks / 256 seqs "
          "slowed fcfs-p/spec+bad 3.9% instead of 5.1%, across a 5% cost floor that had been "
          "added to 'clearly' beyond the rule's wording. The floor was dropped, back to the "
          "rule's 'preempts or queues clearly', looking at stock FCFS arms only; with the "
          "floor the rule would have picked default KV with 32 seqs (no KV pressure, and "
          "'half the blocks' would not be a fallback). In that scratch run, under the old "
          "timing, plugin vs cap was 0.983-0.984 (decoys) and 1.008 (both) on every config, "
          "so it favoured no config.", "",
          "| config | spec+bad: slowdown | preemptions | queue | max waiting | KV peak | spec: "
          "slowdown | preemptions | queue | clearly | barely |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in ch["table"]:
        L.append(f"| {label(x['config'])} | {x['bad_slowdown']:.3f} | "
                 f"{x['bad_preemptions']:.0f} | {_pct(x['bad_queue_frac'])} | "
                 f"{x['bad_max_waiting']:.0f} | {x['bad_max_kv_blocks']} | "
                 f"{x['spec_slowdown']:.3f} | {x['spec_preemptions']:.0f} | "
                 f"{_pct(x['spec_queue_frac'])} | {'yes' if x['clearly'] else 'no'} | "
                 f"{'yes' if x['barely'] else 'no'} |")
    L += ["", f"## Every arm on the chosen config ({label(chosen)})", "",
          "Ratios to fcfs-p/spec+bad, as the bench's Pressure table. 'refused' counts a bet "
          "dropped before its first token too (the client cannot tell them apart); "
          "'bets dropped' are running bets the plugin dropped (not preemptions: vLLM's "
          "counter does not see them). Queue: share of the run with a request waiting.", ""]
    L += arm_table(points, chosen)
    L += ["", f"## Every arm on the fallback config ({label(fallback)})", ""]
    L += arm_table(points, fallback)
    fs = points[(key(fallback), "fcfs-p/spec")]
    if fs["preemptions"] or fs["max_kv_blocks"] >= fallback["kv_blocks"]:
        L += ["", f"Here fcfs-p/spec fills the KV too ({fs['max_kv_blocks']} of "
              f"{fallback['kv_blocks']} blocks, {fs['preemptions']:.0f} preemptions): the "
              "fallback is meant for a T4 that needs less KV than the simulator predicts."]
    dflt = res["d1"][key(DEFAULT)]["by_workload"]
    k = key(DEFAULT)
    both = {a: points[(k, a)]["session_p50"] / points[(k, REF)]["session_p50"]
            for a in ("prio-p/both", "cap-p/both", "plugin-p/both")}
    effect = max(abs(v - 1) for v in both.values())
    L += ["", "## `both` without pressure (default server)", "",
          "Step 5 of the GPU run uses `both` on the default servers only if this predicts an "
          "effect over 5%. Session p50 against fcfs-p/spec+bad (which is fcfs both): "
          + ", ".join(f"{a} {v:.3f}" for a, v in both.items())
          + f"; plugin vs cap {dflt['both']['plugin_vs_cap']:.3f}. Largest effect "
          f"{100 * effect:.1f}%: " + ("**over 5%, run step 5**." if effect > 0.05 else
                                      "**not over 5%, skip step 5**."), "",
          "## Every arm on every config", "", "`grid.csv` (one row per config and arm) and "
          "`grid.json` (the same, plus each run's session times and the choice).", "",
          "## Consistency checks (all hold)", ""]
    L += [f"- {x['check']}: session p50 {x['session_p50'][0]:.4f} s." for x in res["checks"]]
    L += ["", "## Limits", "",
          "- The simulator's KV model follows vLLM 0.32's code (full-sequence admission, "
          "resume from the prefix cache, one LRU free queue) but has never been checked "
          "under heavy preemption. The T4 run is that check.",
          "- A forced rejected bet stops spec-ptc's shadow for the rest of the turn; the sim "
          "models that (rejected_force abort). In this workload the shadow forces nearly "
          "every speculation, so in `both` almost any refused real bet stops it.",
          "- One deterministic run per point; the client's CPU and network are not modelled; "
          "the 1-second metrics poller sees less than the peaks here.",
          "- vLLM's preemption counter misses the plugin's dropped bets; the sim counts "
          "them apart ('bets dropped').", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
