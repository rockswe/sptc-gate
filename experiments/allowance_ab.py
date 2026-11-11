"""Prefill-allowance modes of the sptc plugin (fixed | adaptive | off), simulated.

The plugin as it is (ServerConfig.plugin_semantics: FCFS with bets last, no promotion,
bets rejected or dropped), with its prefill allowance applied in every step (fixed), only
while an untagged request is decoding (adaptive), or never (off). Stock vLLM FCFS is the
reference. Workload: clog.py's RLM-style sessions (long sub-call prompts, where the
allowance can matter), open-loop Poisson arrivals, on several simulated servers.

Sizes are kept small (see results/t4_run1_analysis/allowance_ab.md):

  .venv/bin/python experiments/allowance_ab.py --procs 2 [--sessions 40] [--seeds 2]
  .venv/bin/python experiments/allowance_ab.py --report TAG   # tables from results/t4_run1_analysis/TAG.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import random
from dataclasses import replace
from pathlib import Path

from clog import MIXES, POLICIES, cost_for

from sptc_sim.agent import OutputModel, ServerBackend, ToolLatency
from sptc_sim.des import Sim
from sptc_sim.server import Server, ServerConfig
from sptc_sim.session import run_session, summarize
from sptc_sim.workloads import output_weight, session_turns

RES = Path(__file__).resolve().parents[1] / "results" / "t4_run1_analysis"
# light / medium / heavy arrival rates (sessions/s), from clog's busy fraction per server
RATES = {"eager": [0.05, 0.2, 0.6], "graphs": [0.05, 0.2, 0.6], "moe": [0.05, 0.1, 0.3],
         "rtx4090": [0.02, 0.05, 0.1]}
# free window per server: README knees (about 8 for 4B dense, about 4 for 30B-A3B)
WINDOW = {"eager": 8, "graphs": 8, "rtx4090": 8, "moe": 4}
ARMS = ["stock", "fixed", "adaptive", "off"]


def one_run(args) -> dict:
    config, policy, arm, rate, n_sessions, seed = args
    cost = cost_for(config)
    sim = Sim()
    small = cost.gpu.mem_gb < 70  # vLLM's smaller-GPU defaults
    base = dict(max_batched_tokens=2048 if small else 8192, max_num_seqs=256 if small else 1024)
    if arm == "stock":
        cfg = ServerConfig(**base)
        hints = {}
    else:
        cfg = ServerConfig(**base, policy="agent", plugin_semantics=True, reject_bets=True,
                           spec_max_wait=float("inf"), free_window=WINDOW[config],
                           spec_kv_reserve=0.10, spec_prefill_budget=512,
                           spec_prefill_mode=arm)
        hints = {"mark_spec": "guesses", "promote_early": False}  # tags as dispatched
    server = Server(sim, cost, cfg)
    pcfg = replace(POLICIES[policy], **hints)
    outputs = OutputModel(mean=1.0, sigma=0.25, cap=1024, seed=seed, weight=output_weight)
    be = ServerBackend(sim, server, outputs, ToolLatency(p50=1.6, p99=29.6, seed=seed))
    rng = random.Random(seed)
    plan = [(rng.expovariate(rate), rng.choice(MIXES["serial"])) for _ in range(n_sessions)]
    sessions = []

    def arrivals():
        for i, (gap, prog) in enumerate(plan):
            yield sim.timeout(gap)
            sessions.append(sim.process(run_session(sim, server, be, session_turns(prog), pcfg,
                                                    sid=i, program=prog)))

    sim.process(arrivals())
    sim.run()
    results = [p.value for p in sessions]
    horizon = max(r.t_end for r in results) - min(r.t_arrive for r in results)
    out = summarize(results, server, be, horizon)
    out.update(config=config, policy=policy, arm=arm, rate=rate, seed=seed,
               sessions=n_sessions, allowance_steps=server.allowance_steps,
               bets_rejected=server.bets_rejected)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="eager,graphs,rtx4090,moe")
    ap.add_argument("--policies", default="shadow,shadow+waste1")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--sessions", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--tag", default="allowance_ab")
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    if a.report:
        return report(a.report)
    jobs = [(c, p, arm, r, a.sessions, seed)
            for c in a.configs.split(",") for r in RATES[c]
            for p, arm, seed in itertools.product(a.policies.split(","), a.arms.split(","),
                                                  range(a.seeds))]
    RES.mkdir(parents=True, exist_ok=True)
    rows = []
    with mp.Pool(min(2, a.procs)) as pool:  # at most 2 workers
        for i, row in enumerate(pool.imap_unordered(one_run, jobs)):
            rows.append(row)
            print(f"[{i + 1}/{len(jobs)}] {row['config']:7s} {row['policy']:13s} "
                  f"{row['arm']:8s} rate={row['rate']:.2f} seed={row['seed']} "
                  f"p50={row['lat_p50']:6.2f} p99={row['lat_p99']:6.2f} "
                  f"rootTPOTp99={1000 * row['root_tpot_p99']:5.1f}ms "
                  f"rootITLp99={1000 * row['root_itl_p99']:6.1f}ms "
                  f"cut={row['allowance_steps']}/{row['steps']}", flush=True)
    json.dump(rows, open(RES / f"{a.tag}.json", "w"), indent=1, default=str)


METRICS = [("lat_p50", "session p50 (s)", 1), ("lat_p99", "session p99 (s)", 1),
           ("root_tpot_p99", "root TPOT p99 (ms)", 1000),
           ("root_itl_p99", "root ITL p99 (ms)", 1000),
           ("sub_ttft_p50", "sub-call TTFT p50 (ms)", 1000)]


def report(tag: str) -> str:
    """Seed-averaged tables per server: every arm, and each arm's change vs plugin fixed."""
    import pandas as pd

    d = pd.DataFrame(json.load(open(RES / f"{tag}.json")))
    d["cut"] = d.allowance_steps / d.steps
    keys = ["config", "policy", "rate", "arm"]
    g = d.groupby(keys)[[m for m, _, _ in METRICS] + ["cut", "sessions"]].mean()
    seeds = int(d.groupby(keys).size().max())
    arms = [a for a in ["stock", "fixed", "adaptive", "adaptive_u", "off"] if a in set(d.arm)]
    lines = [f"Simulated. {int(g.sessions.max())} sessions per run, {seeds} seeds per cell "
             "(paired: every arm sees the same arrivals, programs and output lengths), "
             "values averaged over seeds.", ""]
    for config in [c for c in RATES if c in set(d.config)]:
        lines += [f"### {config}", "",
                  "| workload | rate | metric | " + " | ".join(arms) + " | adaptive vs fixed "
                  "| off vs fixed |", "|---|---|---|" + "---|" * (len(arms) + 2)]
        for policy in sorted(set(d.policy)):
            for rate in RATES[config]:
                for m, label, k in METRICS:
                    v = {a: g.loc[(config, policy, rate, a), m] * k for a in arms}
                    rel = [f"{100 * (v[a] / v['fixed'] - 1):+.1f}%" for a in ("adaptive", "off")]
                    lines.append(f"| {policy} | {rate} | {label} | "
                                 + " | ".join(f"{v[a]:.2f}" for a in arms)
                                 + f" | {rel[0]} | {rel[1]} |")
                cut = {a: g.loc[(config, policy, rate, a), "cut"] for a in arms}
                lines.append(f"| {policy} | {rate} | steps the allowance cut | "
                             + " | ".join(f"{100 * cut[a]:.1f}%" for a in arms) + " | | |")
        lines.append("")
    text = "\n".join(lines)
    (RES / f"{tag}_tables.md").write_text(text + "\n")
    print(text)
    return text


if __name__ == "__main__":
    main()
