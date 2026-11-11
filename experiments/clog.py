"""Q1: does speculation clog a shared server?

Open-loop Poisson arrivals of RLM-style sessions (rlm_map, rlm_two_stage,
rlm_branch, research; 3 turns each; root model and sub-calls on ONE server).
Sweep the arrival rate up to and past saturation. For each rate, every policy
sees the same arrivals, programs and output lengths (paired), under two
server schedulers: vLLM-default FCFS and the PASTE-style agent policy.

Waste knob: shadow+wasteX launches X decoy speculations per real one
(mispredicted arms / unroll overshoot), evicted at turn end.

  .venv/bin/python experiments/clog.py [--quick] [--config eager|graphs|moe]

KV model: vLLM 0.32 semantics by default (ServerConfig.full_isl, resume_from_cache,
cache_freed_blocks). Workload: a private system prompt per session, as in the report and
kaggle/bench_general.py (run_session sys_share="session"); --sys-share program|all lets
sessions share it (a workload assumption, not a vLLM one). --legacy-sim runs the KV model
every result before the KV fixes used (LEGACY_KV); results/corrections/corrections.md compares.
"""

from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import random
from dataclasses import replace
from pathlib import Path

import pandas as pd

from sptc_sim.agent import OutputModel, PolicyCfg, ServerBackend, ToolLatency
from sptc_sim.des import Sim
from sptc_sim.hardware import GPUS, GRAPHS, GRAPHS_MOE, MODELS, Overheads, StepCost
from sptc_sim.server import LEGACY_KV, Server, ServerConfig
from sptc_sim.session import run_session, summarize
from sptc_sim.workloads import output_weight, session_turns

RES = Path(__file__).resolve().parents[1] / "results"
MIXES = {
    "serial": ["rlm_map", "rlm_two_stage", "rlm_branch", "research"],
    # programs where the model already batched its fan-out (llm_query_batched)
    "batched": ["rlm_map_batched", "rlm_branch", "research"],
}
PROGRAMS = MIXES["serial"]
POLICIES = {
    "baseline": PolicyCfg("baseline"),
    "literal": PolicyCfg("literal"),
    "shadow": PolicyCfg("shadow"),
    "dataflow": PolicyCfg("dataflow"),
    "shadow+waste0.5": PolicyCfg("shadow", waste_frac=0.5),
    "shadow+waste1": PolicyCfg("shadow", waste_frac=1.0),
    # the confidence-aware scheduler without a perfect oracle: 20% of labels flipped
    "shadow+waste1+noise0.1": PolicyCfg("shadow", waste_frac=1.0, label_noise=0.1),
    "shadow+waste1+noise0.2": PolicyCfg("shadow", waste_frac=1.0, label_noise=0.2),
    "shadow+waste1+noise0.4": PolicyCfg("shadow", waste_frac=1.0, label_noise=0.4),
}


# fcfs: vLLM default. agent-naive: PASTE-style, every early dispatch is low
# priority until the real run claims it. agent: confidence-aware, only bets
# are low priority, promoted as soon as the shadow adopts or forces them.
SCHED_HINTS = {
    "fcfs": {},
    "agent-naive": {"mark_spec": "all", "promote_early": False},
    "agent-naive-open": {"mark_spec": "all", "promote_early": False},
    "agent": {"mark_spec": "guesses", "promote_early": True},
}
# server-side knobs per scheduler. Bets are droppable (nothing waits on them; a
# mislabeled real call is promoted the moment it is claimed or forced), so the
# confidence-aware scheduler never ages them. The naive one labels certain work as
# speculative too, so it needs aging against starvation. agent-naive-open drops the
# free-window gate (priority + prefill allowance only) to show what the gate does.
SCHED_SERVER = {
    "agent": {"spec_max_wait": float("inf"), "reject_bets": True},
    "agent-naive": {"spec_max_wait": 2.0},
    "agent-naive-open": {"spec_max_wait": 2.0, "spec_knee": float("inf")},
}


def cost_for(name: str) -> StepCost:
    if name == "eager":
        tf, ts, ta, cl = json.loads((RES / "calibration.json").read_text())["best_params"]
        return StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"],
                        ov=Overheads(t_fixed=tf, t_per_seq=ts, t_admit=ta, client_s=cl))
    if name == "eager_hiseq":  # sensitivity: largest per-sequence cost the fit tolerates
        tf, ts, ta, cl = json.loads((RES / "calibration.json").read_text())["best_params"]
        return StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"],
                        ov=Overheads(t_fixed=tf, t_per_seq=0.00025, t_admit=ta, client_s=cl))
    if name == "graphs":
        return StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS)
    if name == "moe":
        return StepCost(GPUS["H100-SXM"], MODELS["Qwen3-30B-A3B"], ov=GRAPHS_MOE)
    if name == "rtx4090":
        return StepCost(GPUS["RTX4090"], MODELS["Qwen3-4B"], ov=GRAPHS)
    raise ValueError(name)


LEGACY = {"kv": LEGACY_KV, "sys_share": "session"}  # the simulator before the KV fixes


def one_run(args) -> dict:
    """args: (config, policy, sched, rate, n_sessions, seed, kv, mix[, sim]); sim is a dict
    {"kv": ServerConfig overrides, "sys_share": run_session's} (default: vLLM 0.32 KV
    semantics, a private system prompt per session)."""
    config, policy, sched, rate, n_sessions, seed, kv, mix = args[:8]
    simopt = args[8] if len(args) > 8 else {}
    sys_share = simopt.get("sys_share", "session")
    programs = MIXES[mix]
    cost = cost_for(config)
    sim = Sim()
    small = cost.gpu.mem_gb < 70  # vLLM's smaller-GPU defaults
    pcfg = replace(POLICIES[policy], **SCHED_HINTS[sched])
    server = Server(sim, cost, ServerConfig(
        policy="fcfs" if sched == "fcfs" else "agent", kv_policy=kv, pin_ttl=5.0,
        **SCHED_SERVER.get(sched, {}),
        max_batched_tokens=2048 if small else 8192, max_num_seqs=256 if small else 1024,
        **simopt.get("kv", {})))
    outputs = OutputModel(mean=1.0, sigma=0.25, cap=1024, seed=seed, weight=output_weight)
    be = ServerBackend(sim, server, outputs, ToolLatency(p50=1.6, p99=29.6, seed=seed))
    rng = random.Random(seed)
    plan = [(rng.expovariate(rate), rng.choice(programs)) for _ in range(n_sessions)]
    sessions = []

    def start(i, prog):
        p = sim.process(run_session(sim, server, be, session_turns(prog), pcfg,
                                    sid=i, program=prog, sys_share=sys_share))
        sessions.append(p)
        return p

    def arrivals():
        for i, (gap, prog) in enumerate(plan):
            yield sim.timeout(gap)
            start(i, prog)

    sim.process(arrivals())
    sim.run()
    results = [p.value for p in sessions]
    horizon = max(r.t_end for r in results) - min(r.t_arrive for r in results)
    out = summarize(results, server, be, horizon)
    out.update(config=config, policy=policy, sched=sched, rate=rate, seed=seed, kv=kv, mix=mix)
    out["by_program"] = {
        prog: sorted(r.latency for r in results if r.program == prog) for prog in programs
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="eager")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--rates", default="")
    ap.add_argument("--sessions", type=int, default=240)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--procs", type=int, default=max(1, mp.cpu_count() - 2))
    ap.add_argument("--kv", default="lru", help="comma list: lru,pin,none")
    ap.add_argument("--policies", default="")
    ap.add_argument("--scheds", default="fcfs,agent-naive,agent-naive-open,agent")
    ap.add_argument("--tag", default="")
    ap.add_argument("--mix", default="serial", choices=list(MIXES))
    ap.add_argument("--legacy-sim", action="store_true",
                    help="the KV model before the KV fixes (reproduces the report's original numbers)")
    ap.add_argument("--sys-share", default=None, choices=["session", "program", "all"])
    ap.add_argument("--outdir", default=str(RES))
    args = ap.parse_args()
    simopt = dict(LEGACY) if args.legacy_sim else {}
    if args.sys_share:
        simopt["sys_share"] = args.sys_share
    rates = [float(x) for x in args.rates.split(",")] if args.rates else (
        [0.05, 0.2, 0.4] if args.quick else [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    pols = (args.policies.split(",") if args.policies else
            (["baseline", "shadow"] if args.quick else
             [p for p in POLICIES if "noise" not in p]))
    scheds = args.scheds.split(",")
    n = 60 if args.quick else args.sessions
    jobs = [(args.config, p, s, r, n, seed, kv, args.mix, simopt) for r, p, s, seed, kv in
            itertools.product(rates, pols, scheds, range(args.seeds), args.kv.split(","))
            if not (p == "baseline" and s.startswith("agent-naive"))]  # == agent w/o specs
    with mp.Pool(args.procs) as pool:
        rows = []
        for i, row in enumerate(pool.imap_unordered(one_run, jobs)):
            rows.append(row)
            print(f"[{i + 1}/{len(jobs)}] {row['policy']:16s} {row['sched']:5s} "
                  f"rate={row['rate']:.2f} seed={row['seed']} p50={row['lat_p50']:7.1f} "
                  f"p99={row['lat_p99']:7.1f} rootTPOTp99={1000 * row['root_tpot_p99']:6.1f}ms "
                  f"busy={row['busy']:.2f} drift={row['drift']:.2f} "
                  f"waste={row['wasted_frac']:.3f} kv={row['kv']} "
                  f"hit={row['root_cache_hit']:.2f}", flush=True)
    tag = args.tag or f"clog_{args.config}{'_quick' if args.quick else ''}"
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{k: v for k, v in r.items() if k != "by_program"} for r in rows]).to_csv(
        out / f"{tag}.csv", index=False)
    json.dump(rows, open(out / f"{tag}.json", "w"))


if __name__ == "__main__":
    main()
