"""When does speculation pay? AOSpec-style replay sweep (no server contention).

The 22 suite programs streamed at TPOT 20 -> 1 ms; every tool call's latency
drawn from a lognormal fit (p50, p99) to one GitHub Copilot tool class
(results/copilot_tool_latency.csv, one day of the 2026 dataset). Paired runs:
baseline and spec-ptc see the same latencies. Reports the distribution of the
per-run speedup (p50/p90/p99 across programs x draws).

  .venv/bin/python experiments/sweep.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from sptc_sim import suite
from sptc_sim.agent import FixedBackend, PolicyCfg, ScriptedStream, ToolLatency, run_turn
from sptc_sim.calib import trace_of
from sptc_sim.des import Sim

RES = Path(__file__).resolve().parents[1] / "results"
TPOT_MS = [20, 10, 5, 2, 1]
DRAWS = 40


def dists() -> dict[str, ToolLatency]:
    df = pd.read_csv(RES / "copilot_tool_latency.csv").set_index("tool")
    pick = {"all Copilot tools": "ALL", "get_file": "get_file", "code_search": "code_search",
            "run_command_in_terminal": "run_command_in_terminal"}
    return {k: ToolLatency(p50=df.loc[v, "p50_s"], p99=df.loc[v, "p99_s"]) for k, v in pick.items()}


def run(name, policy, tl: ToolLatency, tps: float, seed: int) -> float:
    t = trace_of(name)
    sim = Sim()
    be = FixedBackend(sim, lambda info: tl.seconds(info, salt=str(seed)))
    p = sim.process(run_turn(sim, t, PolicyCfg(policy), be, ScriptedStream(sim, t, tps)))
    sim.run()
    return p.value.wall


def main() -> None:
    names = sorted(suite.measured_medians().pattern.unique())
    rows = []
    for dname, tl in dists().items():
        for tpot in TPOT_MS:
            tps = 1000 / tpot
            for n in names:
                for s in range(DRAWS):
                    b = run(n, "baseline", tl, tps, s)
                    sp = run(n, "shadow", tl, tps, s)
                    df_ = run(n, "dataflow", tl, tps, s)
                    rows.append({"dist": dname, "tpot_ms": tpot, "pattern": n, "draw": s,
                                 "base": b, "shadow": sp, "dataflow": df_})
        print("done", dname, flush=True)
    df = pd.DataFrame(rows)
    df["speedup"] = df.base / df.shadow
    df["speedup_df"] = df.base / df.dataflow
    df.to_csv(RES / "sweep_runs.csv", index=False)
    summ = df.groupby(["dist", "tpot_ms"]).agg(
        p50=("speedup", lambda x: np.percentile(x, 50)),
        p90=("speedup", lambda x: np.percentile(x, 90)),
        p99=("speedup", lambda x: np.percentile(x, 99)),
        geo_mean=("speedup", lambda x: math.exp(np.log(x).mean())),
        dataflow_geo=("speedup_df", lambda x: math.exp(np.log(x).mean())),
        share_below_1_05=("speedup", lambda x: (x < 1.05).mean()),
    ).reset_index()
    summ.to_csv(RES / "sweep_summary.csv", index=False)
    print(summ.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
