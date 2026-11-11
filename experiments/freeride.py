"""Q2: do extra sub-calls ride along almost free, and where does that stop?

Part A, cost model only: how a decode step's time grows with batch size,
context length, model (dense vs MoE) and GPU; and how much one sub-call's
prefill chunk inflates the root model's next token.

Part B, simulated: one agent on a local server (root model + its sub-calls on
the same GPU). A fan-out of k sub-calls over chunks of S chars, baseline vs
spec-ptc's shadow. Marginal cost of the k-th parallel sub-call, the root's
TPOT inflation, and end-to-end speedup.

  .venv/bin/python experiments/freeride.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from sptc_sim.agent import OutputModel, PolicyCfg, ServerBackend
from sptc_sim.des import Sim
from sptc_sim.hardware import GPUS, GRAPHS, GRAPHS_MOE, MODELS, Overheads, StepCost
from sptc_sim.server import Request, Server, ServerConfig
from sptc_sim.session import run_session
from sptc_sim.workloads import output_weight, session_turns

RES = Path(__file__).resolve().parents[1] / "results"


def eager() -> Overheads:
    cal = json.loads((RES / "calibration.json").read_text())
    tf, ts, ta, cl = cal["best_params"]
    return Overheads(t_fixed=tf, t_per_seq=ts, t_admit=ta, client_s=cl)


def configs() -> dict[str, StepCost]:
    return {
        "H100 Qwen3-4B eager (calibrated)": StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=eager()),
        "H100 Qwen3-4B graphs": StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=GRAPHS),
        "H100 Qwen3-30B-A3B graphs": StepCost(GPUS["H100-SXM"], MODELS["Qwen3-30B-A3B"], ov=GRAPHS_MOE),
        "RTX4090 Qwen3-4B graphs": StepCost(GPUS["RTX4090"], MODELS["Qwen3-4B"], ov=GRAPHS),
        "M4-Max Qwen3-4B": StepCost(GPUS["M4-Max"], MODELS["Qwen3-4B"], ov=GRAPHS),
    }


# ---------------------------------------------------------------- part A
def part_a() -> pd.DataFrame:
    rows = []
    for name, c in configs().items():
        for ctx in (1000, 8000, 32000):
            base = c.decode_step(1, ctx)
            for b in (1, 2, 4, 8, 16, 32, 64, 128, 256):
                rows.append({"config": name, "ctx": ctx, "batch": b,
                             "step_ms": 1000 * c.decode_step(b, ctx),
                             "ratio": c.decode_step(b, ctx) / base,
                             "kv_capacity": c.kv_capacity_tokens()})
            # root decode sharing a step with one sub-call's prefill chunk, up to
            # this GPU class's default token budget
            for p in (256, 1024, 2048, 8192):
                if p > server_cfg(c).max_batched_tokens:
                    continue
                rows.append({"config": name, "ctx": ctx, "batch": -p,
                             "step_ms": 1000 * c.step_time([(1, ctx), (p, 0)]),
                             "ratio": c.step_time([(1, ctx), (p, 0)]) / base})
    return pd.DataFrame(rows)


def knees(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (cfg, ctx), g in df[df.batch > 0].groupby(["config", "ctx"]):
        g = g.sort_values("batch")
        row = {"config": cfg, "ctx": ctx, "step1_ms": g.step_ms.iloc[0]}
        for thr in (1.1, 1.5, 2.0):
            hit = g[g.ratio >= thr]
            row[f"b_at_{thr}x"] = int(hit.batch.iloc[0]) if len(hit) else ">256"
        out.append(row)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- part B
def server_cfg(cost: StepCost) -> ServerConfig:
    """vLLM V1 defaults by GPU class (8192/1024 on >=70 GiB GPUs, else 2048/256)."""
    if cost.gpu.mem_gb >= 70 and not cost.gpu.name.startswith("M4"):
        return ServerConfig()
    return ServerConfig(max_batched_tokens=2048, max_num_seqs=256)


def makespan(cost: StepCost, k: int, prompt: int, out: int) -> float:
    """k identical sub-calls launched together on an idle server."""
    sim = Sim()
    srv = Server(sim, cost, server_cfg(cost))
    evs = [srv.submit(Request(prompt=prompt, out=out)) for _ in range(k)]
    done = sim.all_of(evs)
    sim.run(until=done)
    return sim.now


def part_b() -> pd.DataFrame:
    rows = []
    for name, cost in configs().items():
        for chunk in (400, 8000, 32000):
            prompt = chunk // 4 + 30
            t1 = makespan(cost, 1, prompt, 200)
            for k in (1, 2, 4, 8, 16, 32, 64):
                if prompt * (k + 1) > cost.kv_capacity_tokens():
                    continue
                tk = makespan(cost, k, prompt, 200)
                tk1 = makespan(cost, k + 1, prompt, 200) if k < 64 else float("nan")
                turns = session_turns("fanout", chunk_chars=chunk, k=k)
                res = {}
                for pol in ("baseline", "shadow"):
                    sim = Sim()
                    srv = Server(sim, cost, server_cfg(cost))
                    be = ServerBackend(sim, srv, OutputModel(mean=1.0, sigma=0.0, cap=4096,
                                                             weight=output_weight))
                    # spec-ptc's own caps (16 in flight, 120k chars) lifted: Q2 asks about
                    # the hardware, not the client's throttles
                    pcfg = PolicyCfg(pol, max_inflight=10**6, char_budget=10**12)
                    p = sim.process(run_session(sim, srv, be, turns[1:2], pcfg, 0))
                    sim.run(until=p)
                    s = p.value
                    root = s.roots[0]
                    itl = sorted(root.itl)
                    res[pol] = (s.latency, root.tpot,
                                itl[int(0.99 * (len(itl) - 1))] if itl else float("nan"))
                rows.append({
                    "config": name, "chunk_chars": chunk, "prompt_tok": prompt, "k": k,
                    "solo_call_s": t1, "batch_k_s": tk,
                    "efficiency": k * t1 / tk,  # k serial calls / k parallel calls
                    "marginal_vs_solo": (tk1 - tk) / t1,  # cost of the (k+1)-th call
                    "turn_base_s": res["baseline"][0], "turn_spec_s": res["shadow"][0],
                    "speedup": res["baseline"][0] / res["shadow"][0],
                    "root_tpot_base_ms": 1000 * res["baseline"][1],
                    "root_tpot_spec_ms": 1000 * res["shadow"][1],
                    "root_itl_p99_base_ms": 1000 * res["baseline"][2],
                    "root_itl_p99_spec_ms": 1000 * res["shadow"][2],
                })
                print({k_: (round(v, 3) if isinstance(v, float) else v) for k_, v in rows[-1].items()},
                      flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    RES.mkdir(exist_ok=True)
    a = part_a()
    a.to_csv(RES / "freeride_stepcost.csv", index=False)
    kn = knees(a)
    kn.to_csv(RES / "freeride_knees.csv", index=False)
    print(kn.to_string(index=False))
    pre = a[a.batch < 0].assign(prefill_chunk=lambda d: -d.batch)
    print(pre.pivot_table(index=["config", "ctx"], columns="prefill_chunk", values="ratio")
          .round(2).to_string())
    if "--a-only" not in sys.argv:
        b = part_b()
        b.to_csv(RES / "freeride_sim.csv", index=False)


if __name__ == "__main__":
    main()
