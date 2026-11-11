"""Where does a best-effort request class matter beyond code-mode sPTC?

Three workloads where bets are common (sptc_sim/general.py):
  react   ReAct agents with prediction-based speculation (modes none/action/next/next3)
  branch  code-mode programs whose literal calls in both if-arms are launched (literal)
  batch   background jobs next to interactive ReAct agents, tagged per scheduler
Each runs under three schedulers on one shared server:
  fcfs      stock vLLM (tags ignored)
  priority  stock vLLM --scheduling-policy priority, bets at priority 1
  plugin    the sptc_vllm plugin's policy (bets on spare capacity, rejected or dropped)
over an open-loop Poisson load ladder, on three configs:
  t4    Qwen3-1.7B fp16 on a T4, cost fitted to the Kaggle T4 calibration
  h100  Qwen3-4B on H100 with CUDA graphs
  moe   Qwen3-30B-A3B on H100 with CUDA graphs

Every scheduler and variant at a given rate sees the same arrivals and sessions.

  python experiments/general.py --workload react --config t4 --procs 2
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sptc_sim.agent import OutputModel, PolicyCfg, ServerBackend, ToolLatency
from sptc_sim.des import Sim
from sptc_sim.general import (REACT_MODES, BatchCfg, BatchStats, GeneralServer, ReactCfg,
                              batch_worker, branch_turns, branch_weight, plugin_config,
                              react_session)
from sptc_sim.server import ServerConfig
from sptc_sim.session import pct, run_session

sys.path.insert(0, str(Path(__file__).resolve().parent))
RES = Path(__file__).resolve().parents[1] / "results" / "general"

SCHEDS = ["fcfs", "priority", "plugin"]
VARIANTS = {
    "react": list(REACT_MODES),
    "branch": ["baseline", "literal"],
    # (scheduler, batch tag): each tag only exists under one scheduler
    # bet32 / bg32: a 32-sequence window, wide enough for background work to hold KV
    "batch": ["none", "normal", "low", "bet", "reissue", "bg", "bet32", "bg32"],
    # 48 workers with long jobs (3000-token documents, 1000-token outputs): enough KV
    # demand for drops and preemptions to happen
    "batchlong": ["normal", "low", "bet", "bg", "bet32", "bg32"],
}
LONG_JOB = dict(prompt=3000, out=1000.0, workers=48)
BATCH_SCHED = {"none": "fcfs", "normal": "fcfs", "low": "priority", "bet": "plugin",
               "reissue": "plugin", "bg": "plugin", "bet32": "plugin", "bg32": "plugin"}
RATES = {  # sessions/s, chosen with short probes; the top rates sit past saturation
    "react": {"t4": [0.05, 0.1, 0.15, 0.2, 0.3], "h100": [1, 4, 6, 8, 12],
              "moe": [0.5, 1.5, 2.5, 3.5, 5]},
    "branch": {"t4": [0.02, 0.05, 0.1, 0.15, 0.2], "h100": [0.5, 1, 2, 4, 6],
               "moe": [0.1, 0.25, 0.5, 1, 2]},
    "batch": {"t4": [0.05, 0.1, 0.15], "h100": [1, 4, 8], "moe": [0.5, 1.5, 2.5]},
    "batchlong": {"t4": [0.05, 0.1], "h100": [4, 8], "moe": [1.5, 2.5]},
}
FREE_WINDOW = {"t4": 8, "h100": 8, "moe": 4}  # integrations/README.md knee guidance


def cost_for(config: str):
    if config == "t4":
        from t4_validate import fit_cost

        return fit_cost(0.03)  # client overhead fitted in results/kaggle_t4/sim_vs_t4.md
    from clog import cost_for as clog_cost

    return clog_cost({"h100": "graphs", "moe": "moe"}[config])


def server_for(sim: Sim, cost, config: str, sched: str, bg_window: int | None = None,
               free_window: int | None = None):
    small = cost.gpu.mem_gb < 70  # vLLM's smaller-GPU defaults
    base = dict(max_batched_tokens=2048 if small else 8192,
                max_num_seqs=256 if small else 1024)
    if sched == "plugin":
        cfg = ServerConfig(**base, **plugin_config(free_window or FREE_WINDOW[config]))
    else:
        cfg = ServerConfig(**base, policy=sched)
    return GeneralServer(sim, cost, cfg, bg_window=bg_window)


def redone(r) -> int:
    """Tokens a request ran more than once: recompute after preemption (without it, a
    request runs its uncached prompt once, then one token per further output token)."""
    return max(0, r.computed_tokens - (r.prompt - r.hit_tokens) - max(r.generated - 1, 0))


def waste(calls) -> dict:
    """Wasted GPU work, as a fraction of all tokens the server ran:
      unused   every token of a request whose result nobody used (a missed or refused
               guess, a dropped bet);
      redone   tokens a used request ran twice because it was preempted (recompute).
    Batch jobs cut off when the run ends are neither: their result is still needed."""
    reqs = [c.req for c in calls if c.submitted]
    total = sum(r.computed_tokens for r in reqs)
    unused = sum(r.computed_tokens for r in reqs if not r.claimed and not getattr(r, "cut", 0))
    redo = sum(redone(r) for r in reqs if r.claimed and not getattr(r, "cut", 0))
    cut = sum(r.computed_tokens for r in reqs if getattr(r, "cut", 0))
    gen = sum(r.generated for r in reqs)
    lost_gen = sum(r.generated for r in reqs if not r.claimed and not getattr(r, "cut", 0))
    f = (lambda x: x / total) if total else (lambda x: 0.0)
    return {"wasted_frac": f(unused + redo), "unused_frac": f(unused),
            "redone_frac": f(redo), "cut_frac": f(cut),
            "wasted_decode_frac": lost_gen / gen if gen else 0.0,
            "computed_tokens": total}


def _dropped(c) -> bool:
    """Aborted by the server (a bet dropped under KV pressure), not by the client."""
    if hasattr(c, "done"):
        return c.done.triggered and c.done.value == "dropped"
    # backend requests carry no outcome: with reject_bets a preempted bet is aborted
    # and never requeued, so aborted after a preemption means dropped
    return (c.req.state == "aborted" and c.req.spec and c.req.preemptions > 0
            and not getattr(c.req, "sptc_rejected", False))


def metrics(lat: list, roots: list, horizon: float, slo: float) -> dict:
    itl = [x for r in roots for x in r.itl]
    return {
        "sessions": len(lat),
        "lat_p50": pct(lat, 50), "lat_p99": pct(lat, 99),
        "lat_mean": float(np.mean(lat)) if lat else math.nan,
        "root_ttft_p99": pct([r.ttft for r in roots], 99),
        "root_tpot_p50": pct([r.tpot for r in roots], 50),
        "root_tpot_p99": pct([r.tpot for r in roots], 99),
        "root_itl_p99": pct(itl, 99),
        "slo_s": slo,
        "goodput": sum(x <= slo for x in lat) / horizon if horizon else math.nan,
        "slo_attain": sum(x <= slo for x in lat) / len(lat) if lat else math.nan,
    }


# ----------------------------------------------------------------------------- runs
def run_react(config, cost, sched, rate, n, seed, rcfg: ReactCfg, batch: BatchCfg | None,
              bg_window=None, free_window=None):
    sim = Sim()
    srv = server_for(sim, cost, config, sched, bg_window, free_window)
    client_s = cost.ov.client_s
    rng = random.Random(seed)
    gaps = [rng.expovariate(rate) for _ in range(n)]
    calls, procs = [], []
    stop = sim.event()
    stats = BatchStats()

    def arrivals():
        for i, gap in enumerate(gaps):
            yield sim.timeout(gap)
            procs.append(sim.process(react_session(sim, srv, rcfg, i, seed, client_s, calls)))
        yield sim.all_of(procs)
        stop.succeed()

    sim.process(arrivals())
    if batch is not None:
        for w in range(batch.workers):
            sim.process(batch_worker(sim, srv, batch, w, seed, client_s, stop, stats, calls))
    sim.run()
    sess = [p.value for p in procs]
    horizon = max(s.t_end for s in sess) - min(s.t_arrive for s in sess)
    out = {"lat": [s.latency for s in sess], "roots": [r for s in sess for r in s.roots],
           "horizon": horizon, "calls": calls, "server": srv,
           "hits": sum(s.hits for s in sess), "spec_used": sum(s.spec_used for s in sess),
           "bets": sum(s.bets for s in sess)}
    if batch is not None:
        out.update(batch_jobs_s=stats.jobs / horizon, batch_tok_s=stats.out_tokens / horizon,
                   batch_rejected=stats.rejected, batch_dropped=stats.dropped,
                   batch_lat_p50=pct(stats.lat, 50))
    return out


def run_branch(config, cost, sched, rate, n, seed, policy: str):
    sim = Sim()
    srv = server_for(sim, cost, config, sched)
    pcfg = {"baseline": PolicyCfg("baseline"),
            "literal": PolicyCfg("literal", mark_spec="guesses", promote_early=True)}[policy]
    outputs = OutputModel(mean=1.0, sigma=0.25, cap=1024, seed=seed, weight=branch_weight)
    be = ServerBackend(sim, srv, outputs, ToolLatency(p50=1.6, p99=29.6, seed=seed))
    rng = random.Random(seed)
    gaps = [rng.expovariate(rate) for _ in range(n)]
    procs = []

    def arrivals():
        for i, gap in enumerate(gaps):
            yield sim.timeout(gap)
            procs.append(sim.process(run_session(sim, srv, be, branch_turns(), pcfg, sid=i,
                                                 program="triage")))

    sim.process(arrivals())
    sim.run()
    sess = [p.value for p in procs]
    horizon = max(s.t_end for s in sess) - min(s.t_arrive for s in sess)

    class _C:  # adapt backend requests to waste()'s call interface
        def __init__(self, r):
            self.req, self.submitted = r, True

    roots = [r for s in sess for r in s.roots]
    turns = [t for s in sess for t in s.turns]
    return {"lat": [s.latency for s in sess], "roots": roots, "horizon": horizon,
            "calls": [_C(r) for r in be.requests + roots], "server": srv,
            "hits": sum(t.hits for t in turns), "spec_used": sum(t.hits for t in turns),
            "bets": sum(t.dispatched for t in turns),
            "reissued": sum(t.reissued for t in turns)}


def solo_slo(workload: str, config: str, seed: int) -> float:
    """SLO = 2x the median latency of the same sessions run one at a time, no
    speculation, stock FCFS (a very low arrival rate)."""
    cost = cost_for(config)
    if workload == "branch":
        r = run_branch(config, cost, "fcfs", 0.002, 10, seed, "baseline")
    else:
        r = run_react(config, cost, "fcfs", 0.01, 20, seed, ReactCfg(), None)
    return 2.0 * float(np.median(r["lat"]))


def one_run(args) -> dict:
    workload, config, variant, sched, rate, n, seed, slo = args
    t0 = time.time()
    cost = cost_for(config)
    if workload == "react":
        r = run_react(config, cost, sched, rate, n, seed, ReactCfg(**REACT_MODES[variant]),
                      None)
    elif workload == "branch":
        r = run_branch(config, cost, sched, rate, n, seed, variant)
    else:
        size = LONG_JOB if workload == "batchlong" else {}
        batch = None if variant == "none" else BatchCfg(tag=variant.removesuffix("32"), **size)
        r = run_react(config, cost, sched, rate, n, seed, ReactCfg(), batch,
                      bg_window=32 if variant == "bg32" else None,
                      free_window=32 if variant == "bet32" else None)
    srv = r["server"]
    row = {"workload": workload, "config": config, "variant": variant, "sched": sched,
           "rate": rate, "seed": seed}
    row.update(metrics(r["lat"], r["roots"], r["horizon"], slo))
    row.update(waste(r["calls"]))
    reqs = [c.req for c in r["calls"]]
    row.update(bets=r["bets"], hits=r["hits"], spec_used=r["spec_used"],
               rejected=sum(q.state == "rejected" or getattr(q, "sptc_rejected", False)
                            for q in reqs),
               dropped=sum(map(_dropped, r["calls"])),
               preemptions=sum(q.preemptions for q in reqs),
               busy=srv.busy_time / r["horizon"], reissued=r.get("reissued", 0),
               wall_s=time.time() - t0)
    for k in ("batch_jobs_s", "batch_tok_s", "batch_rejected", "batch_dropped",
              "batch_lat_p50"):
        if k in r:
            row[k] = r[k]
    return row


# ----------------------------------------------------------------------------- Kaggle
KAGGLE_BATCH_TAG = {"fcfs": "normal", "priority": "low", "plugin": "bet"}  # = bench_general
KAGGLE_SIZES = {  # = bench_general.QUICK / FULL
    "quick_cells": dict(modes=["none", "next3"], agents=[8], sessions=3, batch=False),
    "cells": dict(modes=["none", "action", "next", "next3"], agents=[1, 4, 8, 16], sessions=3,
                  batch=True),
}


def _nearest_rank(xs, q):  # = bench_general.pctl
    xs = sorted(x for x in xs if x == x)
    return xs[min(len(xs) - 1, max(0, math.ceil(q / 100 * len(xs)) - 1))] if xs else math.nan


def kaggle_cell(arm: str, mode: str, agents: int, sessions: int, batch_workers: int = 0) -> dict:
    """The simulator's prediction for one cell of kaggle/bench_general.py: `agents`
    closed-loop ReAct agents, session ids agent * 1000 + j, plan seed 0, on the T4 fit."""
    cost = cost_for("t4")
    sim = Sim()
    srv = server_for(sim, cost, "t4", arm)
    client_s = cost.ov.client_s
    rcfg = ReactCfg(**REACT_MODES[mode])
    calls, recs = [], []
    stop = sim.event()
    stats = BatchStats()

    def agent(i):
        for j in range(sessions):
            r = yield sim.process(react_session(sim, srv, rcfg, i * 1000 + j, 0, client_s, calls))
            recs.append(r)

    done = sim.all_of([sim.process(agent(i)) for i in range(agents)])
    wall = []

    def stopper():
        yield done
        wall.append(sim.now)
        stop.succeed()

    sim.process(stopper())
    for w in range(batch_workers):
        sim.process(batch_worker(sim, srv, BatchCfg(tag=KAGGLE_BATCH_TAG[arm]), w, 0, client_s,
                                 stop, stats, []))
    sim.run()
    lat = [r.latency for r in recs]
    tp = [r.tpot for s_ in recs for r in s_.roots if r.tpot == r.tpot]
    reqs = [c.req for c in calls if c.submitted]
    gen = sum(r.generated for r in reqs)
    row = {"arm": arm, "mode": mode, "agents": agents, "sessions": len(recs),
           "batch_workers": batch_workers, "wall_s": wall[0],
           "lat_p50": float(np.median(lat)), "lat_p99": _nearest_rank(lat, 99),
           "lat_mean": float(np.mean(lat)),
           "root_tpot_p50_ms": 1000 * float(np.median(tp)),
           "root_tpot_p99_ms": 1000 * _nearest_rank(tp, 99),
           "bets": sum(r.bets for r in recs), "hits": sum(r.hits for r in recs),
           "used": sum(r.spec_used for r in recs),
           "rejected": sum(c.done.triggered and c.done.value == "rejected" for c in calls),
           "dropped": sum(c.done.triggered and c.done.value == "dropped" for c in calls),
           "wasted_token_frac": sum(r.generated for r in reqs if not r.claimed) / gen if gen
           else 0.0}
    if batch_workers:
        row.update(batch_jobs_s=stats.jobs / wall[0], batch_tok_s=stats.out_tokens / wall[0])
    return row


# (claim, (arm, mode, agents, batch) numerator, denominator, metric, bound): the
# measured ratio numerator / denominator must fall inside `bound`. Bounds are set from
# the predicted ratio with room for the T4 fit's known error, before any measurement.
KAGGLE_CLAIMS = [
    ("on stock vLLM, 3 next-call guesses slow 8 agents down",
     ("fcfs", "next3", 8, 0), ("fcfs", "none", 8, 0), "lat_p50", (1.3, None)),
    ("on stock vLLM, 3 action candidates slow 8 agents down, less than next-call guesses",
     ("fcfs", "action", 8, 0), ("fcfs", "none", 8, 0), "lat_p50", (1.05, None)),
    ("vLLM priority (bets at 1) does not protect the agents: same as FCFS",
     ("priority", "next3", 8, 0), ("fcfs", "next3", 8, 0), "lat_p50", (0.9, 1.1)),
    ("vLLM priority, action candidates: same as FCFS",
     ("priority", "action", 8, 0), ("fcfs", "action", 8, 0), "lat_p50", (0.9, 1.1)),
    ("the plugin removes most of the slowdown at 8 agents (next3)",
     ("plugin", "next3", 8, 0), ("fcfs", "next3", 8, 0), "lat_p50", (None, 0.8)),
    ("the plugin removes part of the smaller action-candidate slowdown at 8 agents",
     ("plugin", "action", 8, 0), ("fcfs", "action", 8, 0), "lat_p50", (None, 0.97)),
    ("at 16 agents the plugin refuses almost every bet: same as no speculation",
     ("plugin", "next3", 16, 0), ("plugin", "none", 16, 0), "lat_p50", (0.9, 1.1)),
    ("at 1 agent next-call guessing is a net win on these 3 sessions (plugin shown; 6 of "
     "15 steps guessed right, more than the 27.8% average, so not a general light-load gain)",
     ("plugin", "next", 1, 0), ("plugin", "none", 1, 0), "lat_p50", (None, 0.9)),
    ("background jobs as bets protect the agents better than untagged jobs",
     ("plugin", "none", 4, 16), ("fcfs", "none", 4, 16), "lat_p50", (None, 0.75)),
    ("background jobs at priority 1 are no better than untagged jobs",
     ("priority", "none", 4, 16), ("fcfs", "none", 4, 16), "lat_p50", (0.9, 1.1)),
    # 11 and 12 were revised before any run. Neither tests light-load gap (1): that gap
    # (plugin root TPOT 19.5 vs 16.8 ms at 1 agent, kaggle_t4/RESULTS.md) was measured with
    # spec-ptc calls tagged `early`, and this bench sends no `early` tags. 12 repeats a
    # measured row (untagged, 1 agent: 16.2 vs 15.7 ms, ratio 1.03, kaggle_t4/sim_vs_t4.md).
    ("at 1 agent, action candidates under the plugin do not raise root TPOT (each "
     "candidate prefills only ~60-75 tokens, under the 512-token bet allowance)",
     ("plugin", "action", 1, 0), ("fcfs", "action", 1, 0), "root_tpot_p50_ms", (0.95, 1.05)),
    ("at 1 agent with no bets the plugin does not raise root TPOT (a repeat of the earlier "
     "T4 run's untagged 1-agent row, measured 16.2 vs 15.7 ms; not a test of gap (1), "
     "which involved `early` tags)",
     ("plugin", "none", 1, 0), ("fcfs", "none", 1, 0), "root_tpot_p50_ms", (0.95, 1.05)),
]


REVISION = (
    "Revised 2026-10-20, still before any run of the benchmark. The first version "
    "(2026-10-20T00:44Z, 65dac71) charged each action candidate a full uncached "
    "observation prefill; vLLM caches the root's blocks at schedule time, so candidates "
    "prefill only their suffix. That changed the action cells and claims 2, 6 and 11 "
    "(first-version ratios 1.74, 0.68, 1.16 would now be predicted 1.13, 0.92, 1.00). "
    "Bounds of 2 and 6 were reset from the new predictions by the same rule; 11 was "
    "restated and 12 added. The quick matrix became a subset of the full one (claims 1, "
    "3, 5). Other cells moved only through the running-order fix. Second revision "
    "(2026-10-20, still before any run): the model now admits a waiting request only if "
    "its whole sequence fits in KV (vLLM 0.32 scheduler_reserve_full_isl, default True). "
    "No cell changed. Claims 11 and 12 were reworded (bounds and ratios unchanged): "
    "neither tests light-load gap (1), which was measured with `early` tags this bench "
    "does not send, and 12 repeats an already measured untagged row (ratio 1.03).")


def kaggle_claims(cells: list) -> list:
    """The claims whose two cells are both in `cells`, numbered as in KAGGLE_CLAIMS."""
    by = {(c["arm"], c["mode"], c["agents"], c["batch_workers"]): c for c in cells}
    out = []
    for i, (text, num, den, metric, (lo, hi)) in enumerate(KAGGLE_CLAIMS, 1):
        if num not in by or den not in by:
            continue
        ratio = by[num][metric] / by[den][metric]
        out.append({"n": i, "claim": text, "numerator": list(num), "denominator": list(den),
                    "metric": metric, "bound": [lo, hi], "predicted_ratio": ratio,
                    "inside_bound_as_predicted": (lo is None or ratio >= lo)
                    and (hi is None or ratio <= hi)})
    return out


def kaggle_predict(path: Path | None = None) -> None:
    """Pre-registered predictions for kaggle/bench_general.py on the Kaggle T4, written to
    path (default results/general/predictions.json)."""
    import datetime
    import subprocess

    cost = cost_for("t4")
    out = {
        "stamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head_when_written": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1]).stdout.strip(),
        "what": "simulator predictions for kaggle/bench_general.py (vLLM 0.32, Qwen3-1.7B fp16, "
                "one T4), written before any run of that benchmark",
        "cost": {"t_fixed_ms": 1000 * cost.ov.t_fixed, "t_per_seq_ms": 1000 * cost.ov.t_per_seq,
                 "mfu": cost.ov.mfu, "attn_mfu": cost.ov.attn_mfu,
                 "client_s": cost.ov.client_s},
        "calibration": "experiments/t4_validate.fit_cost: solo decode/prefill (calib.json) and "
                       "the decode-vs-concurrency slope (concur.json) of the earlier T4 run, plus "
                       "one client overhead fitted on that run's no-speculation suite medians. "
                       "Nothing was fitted on this workload.",
        "expected_error": "on the earlier T4 load rows the same fit had median |error| 3% (max "
                          "16%) on session p50 and 5% (max 17%) on root TPOT p50 "
                          "(results/kaggle_t4/sim_vs_t4.md); p99 over 2-48 sessions is noisy",
        "plugin": {"free_window": 8, "kv_reserve": 0.10, "spec_prefill_budget": 512,
                   "bet_hold_steps": 16},
        "revision": REVISION,
    }
    size = KAGGLE_SIZES["cells"]
    cells = []
    for arm in SCHEDS:
        for agents in size["agents"]:
            for mode in size["modes"]:
                cells.append(kaggle_cell(arm, mode, agents, size["sessions"]))
                print(json.dumps(cells[-1]), flush=True)
        if size["batch"]:
            cells.append(kaggle_cell(arm, "none", 4, size["sessions"], 16))
            print(json.dumps(cells[-1]), flush=True)
    out["cells"] = cells
    quick = KAGGLE_SIZES["quick_cells"]  # a subset of the full cells, same sessions
    assert quick["sessions"] == size["sessions"]
    out["quick_cells"] = [c for c in cells if c["mode"] in quick["modes"]
                          and c["agents"] in quick["agents"] and not c["batch_workers"]]
    out["claims"] = kaggle_claims(out["cells"])
    out["quick_claims"] = [c["n"] for c in kaggle_claims(out["quick_cells"])]
    path = path or RES / "predictions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))


# ----------------------------------------------------------------------------- report
CONFIGS = ["t4", "h100", "moe"]
CONFIG_NAMES = {"t4": "T4, Qwen3-1.7B (T4 fit)", "h100": "H100, Qwen3-4B",
                "moe": "H100, Qwen3-30B-A3B"}
METRICS = ["lat_p50", "lat_p99", "root_tpot_p50", "root_tpot_p99", "goodput", "slo_attain",
           "wasted_frac", "unused_frac", "redone_frac", "cut_frac", "wasted_decode_frac",
           "bets", "spec_used", "rejected", "dropped", "preemptions", "batch_jobs_s", "batch_tok_s", "batch_rejected", "batch_dropped"]


def summary() -> pd.DataFrame:
    frames = [pd.read_csv(RES / f"{w}_{c}.csv") for w in VARIANTS for c in CONFIGS
              if (RES / f"{w}_{c}.csv").exists()]
    df = pd.concat(frames, ignore_index=True)
    keys = ["workload", "config", "variant", "sched", "rate"]
    g = df.groupby(keys, sort=False)
    s = g[[m for m in METRICS if m in df]].mean()
    s["lat_p50_min"], s["lat_p50_max"] = g.lat_p50.min(), g.lat_p50.max()
    s["seeds"] = g.seed.nunique()
    return s.reset_index()


def _cell(r) -> str:
    return f"{r.lat_p50:.1f} / {1000 * r.root_tpot_p99:.0f} / {r.goodput:.3g}"


def verdict(s: pd.DataFrame, tol: float = 0.05) -> pd.DataFrame:
    """Per speculative variant, config and rate: the plugin vs stock FCFS, and vs no
    speculation at all (session p50, mean over seeds)."""
    rows = []
    base_v = {"react": "none", "branch": "baseline"}
    for (w, c, v, rate), g in s.groupby(["workload", "config", "variant", "rate"]):
        if w not in base_v or v == base_v[w]:
            continue
        by = g.set_index("sched")
        none = s[(s.workload == w) & (s.config == c) & (s.variant == base_v[w])
                 & (s.rate == rate) & (s.sched == "fcfs")].iloc[0]
        d_f = by.lat_p50["plugin"] / by.lat_p50["fcfs"] - 1
        d_n = by.lat_p50["plugin"] / none.lat_p50 - 1
        d_fn = by.lat_p50["fcfs"] / none.lat_p50 - 1
        d_p = by.lat_p50["priority"] / by.lat_p50["fcfs"] - 1
        word = lambda d: "helps" if d < -tol else "hurts" if d > tol else "same"  # noqa: E731
        rows.append({"workload": w, "config": c, "variant": v, "rate": rate,
                     "spec_fcfs_vs_none": d_fn, "priority_vs_fcfs": d_p,
                     "plugin_vs_fcfs": d_f, "plugin_vs_none": d_n,
                     "plugin_tpot99_vs_fcfs": by.root_tpot_p99["plugin"]
                     / by.root_tpot_p99["fcfs"] - 1,
                     "plugin_waste": by.wasted_frac["plugin"],
                     "fcfs_waste": by.wasted_frac["fcfs"],
                     "plugin_vs_fcfs_word": word(d_f), "plugin_vs_none_word": word(d_n)})
    return pd.DataFrame(rows)


def report() -> None:
    s = summary()
    s.to_csv(RES / "summary.csv", index=False)
    v = verdict(s)
    v.to_csv(RES / "verdict.csv", index=False)
    lines = ["# Workloads with common bets: full tables (simulated)", "",
             "Generated by `experiments/general.py --report` from the per-run CSVs. Mean over "
             "seeds. Cell: session p50 (s) / root TPOT p99 (ms) / goodput (sessions/s within "
             "the SLO, 2x the solo no-speculation median).", ""]
    for w in VARIANTS:
        for c in CONFIGS:
            g = s[(s.workload == w) & (s.config == c)]
            if g.empty:
                continue
            rates = sorted(g.rate.unique())
            lines += [f"## {w}, {CONFIG_NAMES[c]}", "",
                      "| variant | scheduler | " + " | ".join(f"rate {r:g}/s" for r in rates)
                      + " |", "|---|---|" + "---|" * len(rates)]
            for (var, sch), h in g.groupby(["variant", "sched"], sort=False):
                h = h.set_index("rate")
                lines.append(f"| {var} | {sch} | " + " | ".join(
                    _cell(h.loc[r]) if r in h.index else "" for r in rates) + " |")
            if w.startswith("batch"):
                lines += ["", "Batch throughput (jobs/s) and refusals per run:", "",
                          "| variant | " + " | ".join(f"rate {r:g}/s" for r in rates) + " |",
                          "|---|" + "---|" * len(rates)]
                for var, h in g.groupby("variant", sort=False):
                    if var == "none":
                        continue
                    h = h.set_index("rate")
                    lines.append(f"| {var} | " + " | ".join(
                        f"{h.loc[r].batch_jobs_s:.2f} jobs/s, {h.loc[r].batch_rejected:.0f} rej, "
                        f"{h.loc[r].batch_dropped:.0f} drop" for r in rates) + " |")
            lines.append("")
    lines += ["## Verdict: the plugin against stock FCFS and against no speculation", "",
              "Change in session p50 (negative = faster). `spec fcfs vs none`: what the "
              "speculation costs or gains on stock vLLM.", "",
              "| workload | config | variant | rate | spec fcfs vs none | priority vs fcfs | "
              "plugin vs fcfs | plugin vs none | plugin TPOT p99 vs fcfs | waste fcfs -> plugin |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in v.itertuples():
        lines.append(f"| {r.workload} | {r.config} | {r.variant} | {r.rate:g} | "
                     f"{100 * r.spec_fcfs_vs_none:+.0f}% | {100 * r.priority_vs_fcfs:+.0f}% | "
                     f"{100 * r.plugin_vs_fcfs:+.0f}% | {100 * r.plugin_vs_none:+.0f}% | "
                     f"{100 * r.plugin_tpot99_vs_fcfs:+.0f}% | "
                     f"{100 * r.fcfs_waste:.0f}% -> {100 * r.plugin_waste:.0f}% |")
    (RES / "tables.md").write_text("\n".join(lines) + "\n")
    figures(s)


def figures(s: pd.DataFrame) -> None:
    from sptc_sim import plots as PL

    # 1: ReAct with three next-call guesses per tool wait, per config
    fig, axes = PL._fig(ncols=3, w=4.4, h=3.6)
    series = [("none", "fcfs", "no speculation"), ("next3", "fcfs", "3 guesses, vLLM FCFS"),
              ("next3", "priority", "3 guesses, vLLM priority"),
              ("next3", "plugin", "3 guesses, sptc plugin")]
    for i, (ax, c) in enumerate(zip(axes, CONFIGS, strict=True)):
        g = s[(s.workload == "react") & (s.config == c)]
        groups = {}
        for var, sch, name in series:
            h = g[(g.variant == var) & (g.sched == sch)].sort_values("rate")
            groups[name] = (h.rate.tolist(), h.lat_p50.tolist())
        PL._lines(ax, groups, label_last=False, legend=(i == 0))
        ax.set_yscale("log")
        ticks = [t for t in (10, 15, 20, 30, 50, 100, 200, 400)
                 if g.lat_p50.min() * 0.8 <= t <= g.lat_p50.max() * 1.25]
        ax.set_yticks(ticks, [f"{t:g}" for t in ticks])
        ax.yaxis.set_minor_formatter(PL.matplotlib.ticker.NullFormatter())
        PL._style(ax, CONFIG_NAMES[c], "session arrival rate (sessions/s)",
                  "session p50 (s, log)" if i == 0 else "")
    fig.suptitle("ReAct agents guessing the next call (3 guesses, 43.9% right): simulated. "
                 "FCFS and priority overlap",
                 x=0.01, ha="left", fontsize=11, color=PL.INK)
    fig.tight_layout()
    fig.savefig(RES / "fig_general_react.png", dpi=160)
    PL.plt.close(fig)

    # 2: interactive latency and batch throughput by job class, middle rate per config
    fig, axes = PL._fig(ncols=3, w=4.4, h=3.4)
    names = [("normal", "untagged (FCFS)"), ("low", "priority 1"), ("reissue", "bet, re-issued"),
             ("bet", "bet + retry"), ("bg", "background, window 8"),
             ("bet32", "bet, window 32"), ("bg32", "background, window 32")]
    for i, (ax, c) in enumerate(zip(axes, CONFIGS, strict=True)):
        g = s[(s.workload == "batch") & (s.config == c)]
        rate = sorted(g.rate.unique())[1]
        g = g[g.rate == rate].set_index("variant")
        base = g.loc["none"].lat_p50
        ys = list(range(len(names)))[::-1]
        vals = [g.loc[v].lat_p50 / base for v, _ in names]
        ax.barh(ys, vals, color=PL.SERIES[0], height=0.6)
        for y, (v, _), x in zip(ys, names, vals, strict=True):
            ax.text(x, y, f"  {g.loc[v].batch_jobs_s:.2f} jobs/s", va="center", fontsize=6.5,
                    color=PL.INK2)
        ax.axvline(1.0, color=PL.INK2, linewidth=0.8, linestyle=":")
        ax.set_yticks(ys, [n for _, n in names] if i == 0 else [""] * len(names), fontsize=7)
        ax.set_xlim(0, max(vals) * 1.45)
        PL._style(ax, f"{CONFIG_NAMES[c]}, {rate:g} sessions/s",
                  "interactive session p50 / no batch", "")
    fig.suptitle("16 background workers next to ReAct agents, by how the jobs are tagged "
                 "(simulated; text: batch jobs/s)", x=0.01, ha="left", fontsize=11,
                 color=PL.INK)
    fig.tight_layout()
    fig.savefig(RES / "fig_general_batch.png", dpi=160)
    PL.plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", choices=list(VARIANTS))
    ap.add_argument("--kaggle-predict", action="store_true")
    ap.add_argument("--predict-out", default="", help="--kaggle-predict: output file")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--config", default="t4", help="comma list: t4,h100,moe")
    ap.add_argument("--variants", default="")
    ap.add_argument("--scheds", default=",".join(SCHEDS))
    ap.add_argument("--rates", default="")
    ap.add_argument("--sessions", type=int, default=60)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    if args.kaggle_predict:
        kaggle_predict(Path(args.predict_out) if args.predict_out else None)
        return
    if args.report:
        report()
        return
    if args.procs > 2:
        raise SystemExit("--procs is capped at 2 on this machine")
    w = args.workload
    variants = args.variants.split(",") if args.variants else VARIANTS[w]
    jobs = []
    for config in args.config.split(","):
        rates = [float(x) for x in args.rates.split(",")] if args.rates else RATES[w][config]
        slo = {s: solo_slo(w, config, s) for s in range(args.seeds)}
        for v, s, rate, seed in itertools.product(variants, args.scheds.split(","), rates,
                                                  range(args.seeds)):
            if w.startswith("batch") and s != BATCH_SCHED[v]:
                continue
            # untagged traffic: every scheduler is FCFS (checked in tests), run it once
            if (w, v) in (("react", "none"), ("branch", "baseline")) and s != "fcfs":
                continue
            n = max(args.sessions, math.ceil(40 * rate))  # >= 40 s of arrivals
            jobs.append((w, config, v, s, rate, n, seed, slo[seed]))
    rows = []
    with mp.Pool(args.procs) as pool:
        for i, row in enumerate(pool.imap_unordered(one_run, jobs)):
            rows.append(row)
            print(f"[{i + 1}/{len(jobs)}] {row['config']:4s} {row['variant']:8s} "
                  f"{row['sched']:8s} rate={row['rate']:<5g} p50={row['lat_p50']:6.1f} "
                  f"p99={row['lat_p99']:6.1f} tpot99={1000 * row['root_tpot_p99']:6.1f}ms "
                  f"good={row['goodput']:.3f} waste={row['wasted_frac']:.2f} "
                  f"rej={row['rejected']} drop={row['dropped']} ({row['wall_s']:.0f}s)",
                  flush=True)
    RES.mkdir(parents=True, exist_ok=True)
    tag = args.tag or f"{w}_{args.config.replace(',', '_')}"
    pd.DataFrame(rows).sort_values(["config", "variant", "sched", "rate", "seed"]).to_csv(
        RES / f"{tag}.csv", index=False)


if __name__ == "__main__":
    main()
