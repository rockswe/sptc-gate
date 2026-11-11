"""Predict the Kaggle T4 vLLM runs with the simulator, then compare.

Inputs taken from the T4 run, none of them the predicted outcomes:
  - calib.json : batch-1 decode time, solo prefill at 3 prompt lengths
                 -> t_fixed, GEMM and attention efficiency (least squares)
  - concur.json M3 : decode step vs number of concurrent decoders -> t_per_seq
  - suite.json : per-call prompt/output tokens from the NO-speculation runs, matched
                 to the simulator's calls by execution order (same deterministic order)
Fitted on outcomes: one client overhead, on the no-speculation suite medians only.
Predicted: spec-ptc suite medians (8 patterns) and the 18 load-test rows (1/4/8 agents x
no-spec / spec / spec+1 decoy, stock vLLM and the sptc_vllm plugin).

Plugin rows: --semantics plugin (default) models what sptc_vllm does: tags fixed when the
call is dispatched (no promotion), vLLM FCFS with bets last, bets rejected in the step
the gate fails or after bet_hold_steps. --semantics sim is the idealized agent policy the
first comparison used (program-level FCFS, early calls promoted when adopted or forced).

  .venv/bin/python experiments/t4_validate.py [--semantics plugin|sim] [--out DIR]
  .venv/bin/python experiments/t4_validate.py --predict   # results/t4_run1_analysis/predictions.*
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import replace
from pathlib import Path

import numpy as np

from sptc_sim import suite
from sptc_sim.agent import (CHARS_PER_TOKEN, TEMPLATE_TOKENS, OutputModel, PolicyCfg,
                            ScriptedStream, ServedStream, ServerBackend, run_turn)
from sptc_sim.des import Sim
from sptc_sim.hardware import GPU, MODELS, Overheads, StepCost
from sptc_sim.server import Server, ServerConfig
from sptc_sim.trace import compile_turn

RES = Path(__file__).resolve().parents[1] / "results"
D = RES / "kaggle_t4" / "sptc_out"
MODEL = MODELS["Qwen3-1.7B"]
T4 = GPU("T4", 16, 0.320, 65.0)
BUDGET, SEQS = 2048, 256  # vLLM V1 defaults on GPUs under 70 GiB


# ----------------------------------------------------------------------------- cost
def fit_cost(client_s: float) -> StepCost:
    cal = json.loads((D / "calib.json").read_text())
    con = json.loads((D / "concur.json").read_text())
    d1 = statistics.mean(x["itl_median_ms"] for x in cal["M1_solo_decode"]) / 1000
    # prefill time = GEMM work / (peak * mfu) + attention work / (peak * attn_mfu) + d1
    pts = [(x["prompt_tokens"], x["ttft_s"] - d1) for x in cal["M2_solo_prefill"]]
    body = MODEL.active_params - MODEL.lm_head_params
    gem = [2.0 * (body * n + MODEL.lm_head_params) for n, _ in pts]
    att = [4.0 * MODEL.layers * MODEL.heads * MODEL.head_dim * n * (n / 2) for n, _ in pts]
    A = np.array([gem, att]).T
    x, *_ = np.linalg.lstsq(A, np.array([t for _, t in pts]), rcond=None)
    peak = T4.bf16_tflops * 1e12
    mfu, attn_mfu = 1.0 / (x[0] * peak), 1.0 / (x[1] * peak)
    base = StepCost(T4, MODEL, ov=Overheads(t_fixed=0.0, t_per_seq=0.0, bw_eff=0.8, mfu=mfu,
                                            attn_mfu=attn_mfu, client_s=client_s))
    # per-sequence decode cost: slope of measured step time vs concurrent decoders
    ks = [r["k_other"] + 1 for r in con["M3"]]
    ms = [r["itl_median_ms"] / 1000 for r in con["M3"]]
    roof = [base.decode_step(k, 150) - base.decode_step(1, 150) for k in ks]
    t_seq = float(np.polyfit(ks, np.array(ms) - np.array(roof), 1)[0])
    t_fixed = d1 - base.decode_step(1, 150) - t_seq
    return base.with_overheads(t_fixed=t_fixed, t_per_seq=max(0.0, t_seq))


# ----------------------------------------------------------------------------- tokens
class MeasuredBackend(ServerBackend):
    """Prompt/output tokens per call from the measured no-speculation suite runs.

    Both are looked up by the call's rid when its request is built (one client delay after
    start()). An earlier version kept them in backend state set at start() and swapped
    sptc_sim.agent.Request per turn, so a call could get the tokens of a call started after
    it (e.g. its decoy's forced max length) or of another agent's call."""

    def __init__(self, sim, server, table: dict, decoy_out: int, client_s: float):
        super().__init__(sim, server, _Measured(table, decoy_out), client_s=client_s)
        self.table = table

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        prompt = self.table.get(info.rid.removesuffix("~decoy"), (None, None))[0]
        if prompt is not None:  # ServerBackend sizes the prompt as chars / 4 + template
            info = replace(info, prompt_chars=max(0, prompt - TEMPLATE_TOKENS) * CHARS_PER_TOKEN)
        return super().start(info, spec, salt, prog_t, early, tag_early)


class _Measured(OutputModel):
    def __init__(self, table: dict, decoy_out: int):
        super().__init__()
        self.table, self.decoy_out = table, decoy_out

    def tokens(self, info, salt=""):
        if info.rid.endswith("~decoy"):
            return self.decoy_out  # vllm_bench decoys are raw completions forced to max length
        return self.table.get(info.rid, (None, 20))[1]


def token_tables(trace_of) -> dict:
    """pattern -> {rid: (prompt, output)} by baseline execution order."""
    suite_runs = json.loads((D / "suite.json").read_text())["suite"]
    out = {}
    for name in {r["pattern"] for r in suite_runs}:
        runs = [r for r in suite_runs if r["pattern"] == name and r["mode"] == "baseline"]
        n = min(len(r["calls"]) for r in runs)
        per = [(statistics.median(r["calls"][i]["usage"]["prompt"] for r in runs),
                statistics.median(r["calls"][i]["usage"]["completion"] for r in runs))
               for i in range(n)]
        rids = []
        for op in trace_of(name).base_exec:
            rids += [op[1].rid] if op[0] == "run" else [i.rid for i in op[1]]
        out[name] = {rid: (int(p), int(c)) for rid, (p, c) in zip(rids, per, strict=False)}
    return out


# ----------------------------------------------------------------------------- suite
def suite_sim(cost, tables, name, policy) -> float:
    t = compile_turn(suite.response_text(name), suite.context())
    sim = Sim()
    srv = Server(sim, cost, ServerConfig(max_batched_tokens=BUDGET, max_num_seqs=SEQS))
    be = MeasuredBackend(sim, srv, tables[name], suite.patterns()[name].sub_max_tokens,
                         cost.ov.client_s)
    p = sim.process(run_turn(sim, t, PolicyCfg(policy), be, ScriptedStream(sim, t, 60.0)))
    sim.run(until=p)
    return p.value.wall


def measured_suite() -> dict:
    out = {}
    for r in json.loads((D / "suite.json").read_text())["suite"]:
        out.setdefault((r["pattern"], r["mode"]), []).append(r["wall_s"])
    return {k: statistics.median(v) for k, v in out.items()}


# ----------------------------------------------------------------------------- load
MIX = ["map16", "map_reduce", "two_stage", "side_branch_chain"]


def load_sim(cost, tables, agents, mode, decoys, tagged, semantics="plugin",
             allowance="fixed") -> dict:
    sim = Sim()
    cfg = ServerConfig(max_batched_tokens=BUDGET, max_num_seqs=SEQS)
    if tagged:
        plugin = semantics == "plugin"
        cfg = ServerConfig(max_batched_tokens=BUDGET, max_num_seqs=SEQS, policy="agent",
                           reject_bets=True, spec_max_wait=math.inf, free_window=8,
                           spec_kv_reserve=0.10, spec_prefill_budget=512,
                           spec_prefill_mode=allowance, plugin_semantics=plugin)
    srv = Server(sim, cost, cfg)
    # the plugin has no promotion: a call keeps the tag it was dispatched with
    pol = PolicyCfg("baseline" if mode == "baseline" else "shadow", waste_frac=float(decoys),
                    decoys_bypass_pool=True, mark_spec="guesses" if tagged else "all",
                    promote_early=tagged and semantics == "sim")
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4) for n in MIX}
    turns = []

    def agent(i):
        for j in range(4):
            name = MIX[(i + j) % len(MIX)]
            be = MeasuredBackend(sim, srv, tables[name], suite.patterns()[name].sub_max_tokens,
                                 cost.ov.client_s)
            stream = ServedStream(sim, traces[name], srv, prompt_tokens=20)
            r = yield sim.process(run_turn(sim, traces[name], pol, be, stream, salt=f"{i}/{j}"))
            yield stream.done
            turns.append((r.wall, stream.req.tpot))

    done = sim.all_of([sim.process(agent(i)) for i in range(agents)])
    sim.run(until=done)
    # same order statistics as kaggle/vllm_bench.py's load()
    walls = sorted(w for w, _ in turns)
    tp = sorted(t for _, t in turns if t == t)
    return {"wall_p50": walls[len(walls) // 2],
            "wall_p99": walls[min(len(walls) - 1, int(0.99 * len(walls)))],
            "root_tpot_p50_ms": 1000 * tp[len(tp) // 2],
            "root_tpot_p99_ms": 1000 * tp[min(len(tp) - 1, int(0.99 * len(tp)))],
            "steps": srv.steps, "allowance_steps": srv.allowance_steps,
            "bets_rejected": srv.bets_rejected}


def calibrated():
    """(cost, tables, client overhead, measured suite medians): the T4 calibration."""
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def tr(n):
        return compile_turn(suite.response_text(n), suite.context())

    tables = token_tables(tr)
    meas = measured_suite()
    names = sorted({k[0] for k in meas})
    # one global client overhead, fit on the NO-speculation suite medians only
    best = None
    for c in [0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]:
        cost = fit_cost(c)
        err = statistics.mean(abs(math.log(suite_sim(cost, tables, n, "baseline")
                                           / meas[(n, "baseline")])) for n in names)
        if best is None or err < best[0]:
            best = (err, c)
    return fit_cost(best[1]), tables, best[1], meas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semantics", choices=["plugin", "sim"], default="plugin")
    ap.add_argument("--out", default=str(RES / "kaggle_t4"))
    ap.add_argument("--tag", default="sim_vs_t4")
    ap.add_argument("--predict", action="store_true")
    ap.add_argument("--compare", default="", help="comma list of --tag outputs in --out")
    a = ap.parse_args()
    if a.predict:
        return predict()
    if a.compare:
        return compare(Path(a.out), a.compare.split(","))
    cost, tables, client, meas = calibrated()
    names = sorted({k[0] for k in meas})
    best = (None, client)
    lines = ["# Simulator vs the Kaggle T4 run (vLLM 0.32, Qwen3-1.7B fp16)", "",
             f"Plugin rows modeled with `--semantics {a.semantics}`.", "",
             f"Cost from the T4's solo calibration: t_fixed {1000 * cost.ov.t_fixed:.2f} ms, "
             f"per-sequence {1000 * cost.ov.t_per_seq:.3f} ms, GEMM efficiency "
             f"{cost.ov.mfu:.2f}, attention efficiency {cost.ov.attn_mfu:.3f}. Client "
             f"overhead {1000 * best[1]:.0f} ms each way, fit on the no-speculation suite "
             "medians only. Output tokens per call: measured in the no-speculation runs.", "",
             "## spec-ptc suite (scripted root stream, real sub-calls)", "",
             "| pattern | no-spec measured | no-spec sim | spec measured | spec sim (predicted) | "
             "error | speedup measured | speedup sim |", "|---|---|---|---|---|---|---|---|"]
    errs = []
    for n in names:
        b, s = suite_sim(cost, tables, n, "baseline"), suite_sim(cost, tables, n, "shadow")
        mb, ms = meas[(n, "baseline")], meas[(n, "spec")]
        e = (s - ms) / ms
        errs.append(abs(e))
        lines.append(f"| {n} | {mb:.2f} | {b:.2f} | {ms:.2f} | {s:.2f} | {100 * e:+.1f}% | "
                     f"{mb / ms:.2f}x | {b / s:.2f}x |")
    lines += ["", f"Speculative wall time, predicted: median |error| "
              f"{100 * statistics.median(errs):.1f}%, mean {100 * statistics.mean(errs):.1f}%, "
              f"max {100 * max(errs):.1f}%.", "",
              "## Load test (root served by vLLM, 4 turns per agent)", "",
              "| server | agents | mode | session p50 measured | sim | root TPOT p50 measured "
              "| sim |", "|---|---|---|---|---|---|---|"]
    rows = []
    for tagged, fname in ((False, "load.json"), (True, "load_tagged.json")):
        for r in json.loads((D / fname).read_text())["load"]:
            mode = r["mode"] + (" +1 bad guess" if r["decoys"] else "")
            s = load_sim(cost, tables, r["agents"], r["mode"], r["decoys"], tagged,
                         a.semantics)
            rows.append({"tagged": tagged, **r, "sim": s})
            lines.append(f"| {'plugin' if tagged else 'stock vLLM'} | {r['agents']} | {mode} | "
                         f"{r['wall_p50']:.2f} | {s['wall_p50']:.2f} | "
                         f"{r['root_tpot_p50_ms']:.1f} | {s['root_tpot_p50_ms']:.1f} |")
    we = [abs(math.log(x["sim"]["wall_p50"] / x["wall_p50"])) for x in rows]
    te = [abs(math.log(x["sim"]["root_tpot_p50_ms"] / x["root_tpot_p50_ms"])) for x in rows]
    lines += ["", f"Load rows: session p50 median |error| {100 * statistics.median(we):.0f}% "
              f"(max {100 * max(we):.0f}%); root TPOT p50 median |error| "
              f"{100 * statistics.median(te):.0f}% (max {100 * max(te):.0f}%)."]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.tag}.md").write_text("\n".join(lines) + "\n")
    json.dump(rows, open(out / f"{a.tag}.json", "w"), indent=1, default=str)
    print("\n".join(lines))


def compare(out: Path, tags: list[str]) -> None:
    """All 18 load rows side by side for several runs of main() (log errors, as main())."""
    runs = {t: json.loads((out / f"{t}.json").read_text()) for t in tags}
    head = " | ".join(f"{t}: p50 / TPOT (err)" for t in tags)
    lines = [f"| server | agents | mode | measured p50 / TPOT | {head} |",
             "|---|---|---|---|" + "---|" * len(tags)]
    errs = {t: ([], []) for t in tags}
    for i, r in enumerate(runs[tags[0]]):
        mode = r["mode"] + (" +1 bad guess" if r["decoys"] else "")
        cells = []
        for t in tags:
            x = runs[t][i]
            assert (x["tagged"], x["agents"], x["mode"], x["decoys"]) == \
                (r["tagged"], r["agents"], r["mode"], r["decoys"])
            ew = math.log(x["sim"]["wall_p50"] / r["wall_p50"])
            et = math.log(x["sim"]["root_tpot_p50_ms"] / r["root_tpot_p50_ms"])
            errs[t][0].append(abs(ew))
            errs[t][1].append(abs(et))
            cells.append(f"{x['sim']['wall_p50']:.2f} / {x['sim']['root_tpot_p50_ms']:.1f} "
                         f"({100 * ew:+.0f}% / {100 * et:+.0f}%)")
        lines.append(f"| {'plugin' if r['tagged'] else 'stock'} | {r['agents']} | {mode} | "
                     f"{r['wall_p50']:.2f} / {r['root_tpot_p50_ms']:.1f} | " + " | ".join(cells)
                     + " |")
    lines.append("| | | median / max abs error | | " + " | ".join(
        f"{100 * statistics.median(w):.0f}% / {100 * max(w):.0f}% (p50), "
        f"{100 * statistics.median(tp):.0f}% / {100 * max(tp):.0f}% (TPOT)"
        for w, tp in errs.values()) + " |")
    text = "\n".join(lines)
    (out / "sim_vs_t4_compare.md").write_text(text + "\n")
    print(text)


def predict() -> None:
    """Simulator predictions for the second T4 run's A/B (results/t4_run1_analysis/predictions.*):
    {stock, plugin fixed, plugin adaptive, plugin off} x {spec-ptc, +1 bad guess} x
    {1, 4, 8 agents}, with the same calibration as main() and no input from the load test."""
    cost, tables, client, _ = calibrated()
    measured = {}
    for tagged, fname in ((False, "load.json"), (True, "load_tagged.json")):
        for r in json.loads((D / fname).read_text())["load"]:
            measured[(tagged, r["agents"], r["mode"], r["decoys"])] = r
    arms = [("stock", False, "fixed"), ("plugin fixed", True, "fixed"),
            ("plugin adaptive", True, "adaptive"), ("plugin off", True, "off")]
    rows = []
    for agents in (1, 4, 8):
        for decoys in (0, 1):
            for arm, tagged, allowance in arms:
                s = load_sim(cost, tables, agents, "spec", decoys, tagged, "plugin", allowance)
                m = measured.get((tagged, agents, "spec", decoys)) if allowance == "fixed" \
                    else None
                rows.append({"arm": arm, "agents": agents, "bad_guesses": decoys,
                             "predicted": s,
                             "measured_t4_2026_10_19": None if m is None else {
                                 k: m[k] for k in ("wall_p50", "wall_p99", "root_tpot_p50_ms",
                                                   "root_tpot_p99_ms")}})
    calib = {
        "inputs": ["sptc_out/calib.json (batch-1 decode, solo prefill at 3 lengths)",
                   "sptc_out/concur.json M3 (decode step vs concurrent decoders)",
                   "sptc_out/suite.json (per-call prompt/output tokens, no-spec runs)"],
        "fitted_on_outcomes": f"client overhead {1000 * client:.0f} ms each way, on the "
                              "no-speculation suite medians only",
        "cost": {"t_fixed_ms": 1000 * cost.ov.t_fixed, "t_per_seq_ms": 1000 * cost.ov.t_per_seq,
                 "gemm_eff": cost.ov.mfu, "attn_eff": cost.ov.attn_mfu},
        "server": {"max_batched_tokens": BUDGET, "max_num_seqs": SEQS, "free_window": 8,
                   "kv_reserve": 0.10, "spec_prefill_budget": 512},
        "plugin_model": "ServerConfig.plugin_semantics (FCFS with bets last, no promotion, "
                        "bets gated in the waiting loop, rejected or held <= 16 steps)",
    }
    out = RES / "t4_run1_analysis"
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"calibration": calib, "rows": rows}, open(out / "predictions.json", "w"),
              indent=1)
    lines = [
        "# Predictions for the second T4 run's A/B (simulated, not measured)", "",
        "Written by `experiments/t4_validate.py --predict`; numbers in `predictions.json`.", "",
        "## Calibration (the same as `sim_vs_t4_after.md`; no load-test row is an input)", "",
        f"- Step cost from the T4's solo runs: `calib.json` (batch-1 decode, solo prefill at "
        f"3 lengths) and `concur.json` M3 (step time vs concurrent decoders): t_fixed "
        f"{1000 * cost.ov.t_fixed:.2f} ms, per sequence {1000 * cost.ov.t_per_seq:.3f} ms, "
        f"GEMM efficiency {cost.ov.mfu:.2f}, attention efficiency {cost.ov.attn_mfu:.3f}.",
        "- Per-call prompt and output tokens: `suite.json` (no-speculation runs). Bad guesses "
        "are forced to the call's max_tokens, as in `kaggle/vllm_bench.py`.",
        f"- Fitted on outcomes: one client overhead ({1000 * client:.0f} ms each way), on the "
        "no-speculation suite medians only.",
        "- Server: vLLM defaults for small GPUs (2,048-token step budget, 256 sequences). "
        "Plugin: free_window 8, kv_reserve 0.10, spec_prefill_budget 512, modeled with "
        "`plugin_semantics`.",
        "- Workload: `vllm_bench.py load`, 4 turns per agent (map16, map_reduce, two_stage, "
        "side_branch_chain), root served at 4 characters per token; p50 and p99 are the "
        "same order statistics as `load()` (at 1 agent: the 3rd of 4 turns and the max).", "",
        "## Table", "",
        "| agents | workload | arm | session p50 (s) | session p99 (s) | root TPOT p50 (ms) "
        "| root TPOT p99 (ms) | steps the allowance cut | bets rejected | measured 2026-10-19:"
        " session p50, TPOT p50 / p99 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s, m = r["predicted"], r["measured_t4_2026_10_19"]
        meas = "" if m is None else (f"{m['wall_p50']:.2f} s, {m['root_tpot_p50_ms']:.1f} / "
                                     f"{m['root_tpot_p99_ms']:.1f} ms")
        lines.append(f"| {r['agents']} | spec-ptc{' +1 bad guess' if r['bad_guesses'] else ''} "
                     f"| {r['arm']} | {s['wall_p50']:.2f} | {s['wall_p99']:.2f} | "
                     f"{s['root_tpot_p50_ms']:.1f} | {s['root_tpot_p99_ms']:.1f} | "
                     f"{s['allowance_steps']} of {s['steps']} | {s['bets_rejected']} | {meas} |")
    lines += ["", PREDICT_NOTES]
    (out / "predictions.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


PREDICT_NOTES = """## How to read it

- **Simulated.** One deterministic simulator run per cell, no noise model. The measured
  column is the single October 19 run (`sptc_out/load.json`, `load_tagged.json`); it is only
  shown for the stock and plugin-fixed arms, the arms that ran.
- **Expected error.** On the 18 measured load rows this simulator is off by a median of 3%
  (session p50) and 5% (root TPOT p50), at worst 21% and 22% (`sim_vs_t4_compare.md`).
  - The worst row is stock vLLM with 8 agents and bad guesses: predicted 8.21 s vs 6.62 s
    measured. The simulator likely makes decoys too costly at high load.
  - Next are the 1-agent plugin rows, which it does not reproduce: −12% to −18%
    (`root_cause.md`).
- **The four plugin-side arms schedule differently only in the prefill allowance.** On this
  workload the allowance cuts a request in at most a few percent of steps (column "steps
  the allowance cut"), because sub-call prompts are 15-47 tokens. So the simulator predicts
  **fixed, adaptive and off within about 1% of each other**.
  - On the GPU the arms also differ in compiled code: the mode is part of
    `additional_config`, which is part of vLLM's compile hash, so each arm compiles its own
    torch.compile artifact (`root_cause.md`, candidate 8). Compare the modes on
    `--enforce-eager` launches, where no arm runs compiled code.
  - There, a gap between them larger than the stock-vs-stock spread would contradict the
    simulator, and would point at the allowance after all.
  - If plugin `off` is as slow as plugin `fixed` at 1 agent, the allowance is cleared as
    the cause of the October 19 gap.
- **Plugin vs stock.**
  - Without bad guesses: the same within about 1%.
  - With one bad guess per call: the plugin is faster at every load, because it refuses
    most decoys (column "bets rejected"; 45, 180 and 360 decoys are launched at 1, 4 and 8
    agents).
- **Run-to-run variation is unknown** (one run per row so far). In the 1-agent row where
  the plugin provably schedules like stock vLLM (no speculation), the October 19 run
  differed by +4% (session p50) and +3.6% (root TPOT p50); the tagged 1-agent rows differed
  by +13.5% and +16%. Repeat each 1-agent arm at least 5 times before comparing arms.

## Running the A/B (same settings as October 19)

```bash
# stock
vllm serve Qwen/Qwen3-1.7B --dtype half --max-model-len 8192 --gpu-memory-utilization 0.9
# plugin: one server per mode, MODE in fixed | adaptive | off
vllm serve Qwen/Qwen3-1.7B --dtype half --max-model-len 8192 --gpu-memory-utilization 0.9 \\
  --scheduler-cls sptc_vllm.scheduler.SptcScheduler \\
  --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1,
                                 "spec_prefill_budget": 512, "prefill_allowance": "MODE"}}'
# stock sharing the plugin-fixed artifact: stock flags plus the plugin-fixed arm's exact
# --additional-config (stock does not use the "sptc" key, it only hashes it; --scheduler-cls is not hashed)
# eager runs: every arm again with --enforce-eager (no torch.compile, no CUDA graphs)
# client, once per server (tagged on the plugin servers), a separate --out per arm/repeat.
# --turns and --patterns as on October 19 and in the simulator (the default --patterns is
# the 8-pattern suite list, a different workload)
python kaggle/vllm_bench.py load --model Qwen/Qwen3-1.7B --spec-ptc SPEC_PTC_DIR \\
  --agents 1,4,8 --decoys 0,1 --turns 4 \\
  --patterns map16,map_reduce,two_stage,side_branch_chain [--tag-bets] --out OUT_DIR
```

- Check that the plugin server's log shows `sptc scheduler (SptcAsyncScheduler): ...
  prefill allowance 512 (MODE)` (`off` prints `unlimited`).
- Record each launch's compile state from its log: the cache directory
  (`Using cache directory: .../torch_compile_cache/<hash>/...`), `Directly load AOT
  compilation` (cached) or `Compiling a graph ... takes` (fresh), and the `torch.compile
  took` line. Each `additional_config` has its own compile-cache entry, so every plugin
  arm runs its own artifact; relaunching an arm reloads that same artifact, it does not
  make the arms' code equal. On October 19 stock loaded a cached artifact and the plugin
  compiled fresh (`root_cause.md`). Compare modes on the eager launches, and stock vs
  plugin `fixed` also on the shared-artifact pair (same cache directory in both logs).
- Throw away one 1-agent pass after each server start.
- Repeat the 1-agent rows, which is cheap: about 1 minute per pass and arm.
- Also run `pytest integrations/tests_vllm -q -s` (this includes the per-step overhead
  benchmark `test_sptc_overhead.py`).
"""


if __name__ == "__main__":
    main()
