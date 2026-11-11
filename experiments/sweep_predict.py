"""Pre-registered simulator predictions for the Kaggle T4 saturation sweep
(kaggle/vllm_bench.py sweep), written before any GPU run of the sweep.

Calibration: exactly that of experiments/t4_validate.py, nothing refit:
  - cost model from calib.json (solo decode, solo prefill) and concur.json M3;
  - per-call prompt/output tokens from suite.json's no-speculation runs;
  - one client overhead, fit on the no-speculation SUITE medians only (same grid).
Two prediction sets, both written before any GPU run of the sweep:
  P0  that calibration alone. The 18 load rows of the first T4 run (1/4/8 agents) are not
      used; they are replayed as a check.
  P1  (primary) P0 plus ONE parameter fit on those 18 rows' root TPOT p50: a cap on the
      per-sequence step cost (t_per_seq x min(seqs, seq_cap)). t_per_seq was measured
      with at most 16 sequences (concur.json M3); P0 extrapolates it linearly, and over-
      predicts the 8-agent bad-guess row's root TPOT by 31%. The sweep's points at 1, 4
      and 8 agents are in-sample for P1; its other loads and the priority arms are not.
Server inputs read from the T4 server log, not outcomes: KV capacity 85,904 tokens,
max_num_batched_tokens 2048, max_num_seqs 256.

Each arm of the sweep maps to one simulator setting:
  fcfs/*    policy fcfs
  prio/*    policy vllm-priority, every speculative call (early and decoy) at priority 1
  plugin/*  policy agent with reject_bets, free_window 8, kv_reserve 0.10, prefill
            allowance 512 (as t4_validate's plugin rows), decoys tagged bet, the rest early
The simulator is deterministic, so each point is one run (no repeats, no CIs).

Differences from t4_validate's load replay, decided before looking at any sweep data:
  - each call's prompt and output tokens are looked up by the call's own identity when its
    request is built. t4_validate's MeasuredBackend stores them on the backend and reads
    them back after the client delay, so concurrent calls of one turn (and a real call
    and its decoy) can take each other's values;
  - prompts carry the sweep's per-run prefix (about 8 tokens);
  - agents start together (the sweep releases them behind a barrier).

  PYTHONPATH=. .venv/bin/python experiments/sweep_predict.py [--agents 1,2,4,...]
writes results/sweep_prep/predictions.json and predictions_table.md.
  ... sweep_predict.py --seq-cap 32 --sets P1 --name predictions_seqcap32
skips the fit and uses the given seq_cap (the sensitivity set: 24 and 32 tie in the fit).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kaggle"))

import t4_validate as t4  # noqa: E402
import vllm_bench as vb  # noqa: E402

from sptc_sim import suite  # noqa: E402
from sptc_sim.agent import (CHARS_PER_TOKEN, TEMPLATE_TOKENS, OutputModel,  # noqa: E402
                            CallHandle, PolicyCfg, ServedStream, ServerBackend, run_turn)
from sptc_sim.des import Sim  # noqa: E402
from sptc_sim.hardware import StepCost  # noqa: E402
from sptc_sim.server import BLOCK, PRIO_SPEC, ServerConfig  # noqa: E402
from sptc_sim.server import Server as SimServer  # noqa: E402
from sptc_sim.trace import compile_turn  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "sweep_prep"
KV_TOKENS = 85_904  # results/kaggle_t4/sptc_out/vllm.log: "GPU KV cache size: 85,904 tokens"
SALT_TOKENS = 8  # "[prio/spec+bad n16 r0] " prefixed to every prompt by the sweep
ROOT_PROMPT = 20 + SALT_TOKENS  # t4_validate's root prompt, plus the prefix


@dataclasses.dataclass
class CappedStepCost(StepCost):
    """StepCost whose per-sequence overhead stops growing past seq_cap sequences."""

    seq_cap: float = math.inf

    def step_time(self, items, n_new=0):
        t = super().step_time(items, n_new)
        extra = len(items) - self.seq_cap
        return t - self.ov.t_per_seq * extra if extra > 0 else t


SEQ_CAPS = [8, 12, 16, 24, 32, 48, 64, 96, math.inf]


def known_rows() -> list[tuple[str, int, dict]]:
    """(arm, agents, measured row) for the first T4 load test's 18 rows."""
    out = []
    for tagged, fname in ((False, "load.json"), (True, "load_tagged.json")):
        for r in json.loads((t4.D / fname).read_text())["load"]:
            arm = ("plugin/" if tagged else "fcfs/") + ("nospec" if r["mode"] == "baseline"
                                                        else "spec+bad" if r["decoys"] else "spec")
            out.append((arm, r["agents"], r))
    return out


def fit_seq_cap(cost0, tables, traces, setting=None) -> tuple[float, list]:
    """P1's one parameter: seq_cap minimising mean |log error| of root TPOT p50 over the
    18 known rows (session times are not used in the fit). setting: as in sim_run."""
    rows = known_rows()
    scores = []
    for cap in SEQ_CAPS:
        cost = CappedStepCost(cost0.gpu, cost0.model, cost0.tp, cost0.ov, cost0.decode_table,
                              seq_cap=cap)
        errs = []
        for arm, n, r in rows:
            rec = sim_run(cost, tables, vb.ARM[arm], n, traces, 4, setting)
            tp = vb.pctl([x["root_tpot_ms"] for x in rec["sessions"]], 0.5)
            errs.append(abs(math.log(tp / r["root_tpot_p50_ms"])))
        scores.append({"seq_cap": cap, "tpot_mean_abs_log_err": statistics.mean(errs)})
        print(f"seq_cap {cap}: root TPOT mean |log err| {statistics.mean(errs):.3f}", flush=True)
    best = min(scores, key=lambda x: x["tpot_mean_abs_log_err"])
    return best["seq_cap"], scores


class TableOutputs(OutputModel):
    """Output tokens by call identity: measured table, decoys forced to max length."""

    def __init__(self, table: dict, decoy_out: int) -> None:
        super().__init__()
        self.table, self.decoy_out = table, decoy_out

    def tokens(self, info, salt=""):
        if info.rid.endswith("~decoy"):
            return self.decoy_out  # vllm_bench decoys: raw completions, ignore_eos, max_tokens
        return self.table.get(info.rid, (0, 20))[1]


class TableBackend(ServerBackend):
    """Prompt tokens by call identity, through the call's own CallInfo (no shared state)."""

    def __init__(self, sim, server, table: dict, decoy_out: int, client_s: float, log: list):
        super().__init__(sim, server, TableOutputs(table, decoy_out), client_s=client_s)
        self.table, self.log = table, log

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        rid = info.rid.removesuffix("~decoy")
        prompt = self.table.get(rid, (int(info.prompt_chars / CHARS_PER_TOKEN)
                                      + TEMPLATE_TOKENS, 0))[0] + SALT_TOKENS
        if info.rid.endswith("~decoy"):
            prompt += 3  # " [alt 0]"
        chars = int(max(0, prompt - TEMPLATE_TOKENS) * CHARS_PER_TOKEN)
        assert int(chars / CHARS_PER_TOKEN) + TEMPLATE_TOKENS == prompt or prompt < TEMPLATE_TOKENS
        h = super().start(dataclasses.replace(info, prompt_chars=chars), spec, salt, prog_t,
                          early, tag_early)
        self.log.append(h)
        return h


class ProxySim:
    """vllm_bench.ProxyGate in the simulator: a client-side cap on bets, shared by every
    agent of a run. window: refuse a bet unless the requests in flight (calls the clients
    have started and not seen end, plus root streams at the server) + 1 <= cap; bets:
    unless the bets in flight + 1 <= cap. A refused bet is never sent. The time a root
    spends on the wire before it reaches the server is not counted.

    Which calls are bets: "decoys" (run 2's bench, where spec-ptc's own speculative calls
    go as kind early and pass the gate) or "spec" (every call sent with the bet label,
    spec=True: with mark_spec "all", every speculative dispatch, decoys included)."""

    def __init__(self, srv, gate: str, bets: str = "decoys") -> None:
        mode, cap = gate.split(":")
        assert mode in ("window", "bets"), gate
        assert bets in ("decoys", "spec"), bets
        self.srv, self.mode, self.cap, self.bets = srv, mode, int(cap), bets
        self.live: list = []  # handles of LLM calls started through the gate
        self.sent = self.refused = 0

    def is_bet(self, info, spec: bool) -> bool:
        return spec if self.bets == "spec" else info.rid.endswith("~decoy")

    def admit_bet(self) -> bool:
        self.live = [h for h in self.live if not h.done.triggered]
        if self.mode == "window":
            n = len(self.live) + sum(r.kind == "root" for r in self.srv.running + self.srv.waiting)
        elif self.bets == "spec":
            n = sum(h.spec for h in self.live)
        else:
            n = sum(h.info.rid.endswith("~decoy") for h in self.live)
        ok = n + 1 <= self.cap
        self.sent += ok
        self.refused += not ok
        return ok


class ProxyTableBackend(TableBackend):
    """TableBackend behind a ProxySim: bets may be refused before they are sent."""

    def __init__(self, *args, proxy: ProxySim, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxy = proxy

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        if info.tool in self.llm_tools and self.proxy.is_bet(info, spec) \
                and not self.proxy.admit_bet():
            h = CallHandle(self.sim.event(), info, spec, self.sim.now, backend=self)
            h.rejected = True
            h.done.succeed(h)
            self.log.append(h)
            return h
        h = super().start(info, spec, salt, prog_t, early, tag_early)
        if info.tool in self.llm_tools:
            self.proxy.live.append(h)
        return h


def decoy_outcome(h) -> str:
    """vllm_bench.outcome's labels: a bet dropped before its first token reads as rejected
    on the client (vLLM never streams its finish), so it is counted as one here too."""
    if h.rejected or (h.dropped and h.req is not None and h.req.generated == 0):
        return "rejected"
    if h.req is not None and h.req.state == "done":
        return "completed"
    if h.cancelled:
        return "cancelled"
    if h.dropped:
        return "dropped"
    return "unknown"


class MeteredServer(SimServer):
    """The simulator's server with what vllm_bench.MetricsPoller reads from vLLM's /metrics,
    taken after every schedule() (the poller samples once a second, so it can only see
    less): running and waiting requests; KV blocks held by requests (vLLM's
    kv_cache_usage_perc counts blocks with a reference, not cached free ones: here total
    minus headroom); and preemptions as vLLM counts them, requeues only. A running bet the
    plugin drops is counted apart: sptc_vllm finishes it without vLLM's _preempt_request.
    Also the waiting queue over time (time-weighted, from one schedule() to the next)."""

    def __init__(self, sim, cost, cfg=None) -> None:
        self.peak = {"running": 0, "waiting": 0, "kv_blocks": 0}
        self.preempted = self.dropped = 0
        self.queue_s = 0.0  # integral of waiting requests over time
        self.queue_any_s = 0.0  # time with at least one request waiting
        self._last: tuple[float, int] | None = None
        super().__init__(sim, cost, cfg)

    def _schedule(self):
        batch = super()._schedule()
        now, n = self.sim.now, len(self.waiting)
        if self._last is not None:
            dt = now - self._last[0]
            self.queue_s += self._last[1] * dt
            self.queue_any_s += dt if self._last[1] else 0.0
        self._last = (now, n)
        p = self.peak
        p["running"] = max(p["running"], len(self.running))
        p["waiting"] = max(p["waiting"], n)
        p["kv_blocks"] = max(p["kv_blocks"], self.kv.total - self.kv.headroom(now))
        return batch

    def _preempt(self, victim) -> None:
        drop = self.cfg.reject_bets and victim.priority == PRIO_SPEC
        super()._preempt(victim)
        if drop:
            self.dropped += 1
        else:
            self.preempted += 1


SIM_ARMS = {
    "fcfs": dict(cfg={}, mark_spec="all", promote_early=False),
    "priority": dict(cfg={"policy": "vllm-priority"}, mark_spec="all", promote_early=False),
    "plugin": dict(cfg={"policy": "agent", "reject_bets": True, "spec_max_wait": math.inf,
                        "free_window": vb.PLUGIN_CFG["sptc"]["free_window"],
                        "spec_kv_reserve": vb.PLUGIN_CFG["sptc"]["kv_reserve"],
                        "spec_prefill_budget": vb.PLUGIN_CFG["sptc"]["spec_prefill_budget"]},
                   mark_spec="guesses", promote_early=True),
}


def sim_run(cost, tables, arm: vb.Arm, agents: int, traces: dict, turns: int,
            setting=None) -> dict:
    """One simulated sweep run, in the bench's run-record format. setting(arm) -> a
    SIM_ARMS-style entry (default: SIM_ARMS[arm.server]). Its "cfg" overrides any
    ServerConfig field, the T4 server's (budget, max_num_seqs, KV blocks) included.
    Optional keys: "proxy", a vllm_bench.ProxyGate spec (MODE:CAP) for a client-side cap
    on bets, with "proxy_bets" (ProxySim's bets, default decoys); "tag_early",
    "rejected_force" and "decoy_at_call" (PolicyCfg's, default True, reissue, False)."""
    sa = setting(arm) if setting is not None else SIM_ARMS[arm.server]
    sim = Sim()
    cfg = {"max_batched_tokens": t4.BUDGET, "max_num_seqs": t4.SEQS,
           "kv_blocks": KV_TOKENS // BLOCK} | sa["cfg"]
    srv = MeteredServer(sim, cost, ServerConfig(**cfg))
    proxy = ProxySim(srv, sa["proxy"], sa.get("proxy_bets", "decoys")) \
        if sa.get("proxy") else None
    pol = PolicyCfg("baseline" if arm.mode == "baseline" else "shadow",
                    waste_frac=float(arm.decoys), decoys_bypass_pool=True,
                    mark_spec=sa["mark_spec"], promote_early=sa["promote_early"],
                    tag_early=sa.get("tag_early", True),
                    rejected_force=sa.get("rejected_force", "reissue"),
                    decoy_at_call=sa.get("decoy_at_call", False))
    mix = vb.WORKLOADS[arm.workload]["patterns"].split(",")
    sessions = []

    def agent(i):
        for j in range(turns):
            name = mix[(i + j) % len(mix)]
            log: list = []
            if proxy is None:
                be = TableBackend(sim, srv, tables[name], suite.patterns()[name].sub_max_tokens,
                                  cost.ov.client_s, log)
            else:
                be = ProxyTableBackend(sim, srv, tables[name],
                                       suite.patterns()[name].sub_max_tokens, cost.ov.client_s,
                                       log, proxy=proxy)
            stream = ServedStream(sim, traces[name], srv, prompt_tokens=ROOT_PROMPT)
            r = yield sim.process(run_turn(sim, traces[name], pol, be, stream, salt=f"{i}/{j}"))
            yield stream.done
            itl = sorted(stream.req.itl)
            sessions.append({
                "agent": i, "turn": j, "pattern": name, "wall_s": r.wall,
                "root_tpot_ms": 1000 * stream.req.tpot,
                "root_itl_p99_ms": 1000 * vb.pctl(itl, 0.99) if itl else None,
                "root_tokens": stream.req.generated, "sub_refused": 0, "calls": [],
                "decoys": [{"outcome": decoy_outcome(h)} for h in log
                           if h.info.rid.endswith("~decoy")],
                # the real speculative calls sent as bets (mark_spec "all"), and the calls
                # re-run after a needed bet was refused or dropped
                "real_bets": [{"outcome": decoy_outcome(h)} for h in log
                              if h.spec and not h.info.rid.endswith("~decoy")],
                "reissued": r.reissued, "shadow_stopped": r.shadow_stop is not None})

    done = sim.all_of([sim.process(agent(i)) for i in range(agents)])
    sim.run(until=done)
    return {"arm": arm.name, "server": arm.server, "mode": arm.mode, "decoys": arm.decoys,
            "tags": arm.tags, "agents": agents, "rep": 0, "status": "ok", "source": "simulated",
            "makespan_s": sim.now, "sessions": sessions,
            "server_metrics": {"preemptions": float(srv.preempted),
                               "max_waiting": float(srv.peak["waiting"]),
                               "max_running": float(srv.peak["running"]),
                               "max_kv": srv.peak["kv_blocks"] / srv.kv.total},
            "sim_steps": srv.steps, "sim_allowance_steps": srv.allowance_steps,
            "sim_kv_blocks": srv.kv.total, "sim_max_kv_blocks": srv.peak["kv_blocks"],
            "sim_max_num_seqs": srv.cfg.max_num_seqs, "sim_bets_dropped": srv.dropped,
            "sim_bets_rejected": srv.bets_rejected,
            "sim_queue_mean": srv.queue_s / sim.now if sim.now else 0.0,
            "sim_queue_frac": srv.queue_any_s / sim.now if sim.now else 0.0,
            "client_cpu_util": None,
            **({"proxy": {"gate": sa["proxy"], "bets_sent": proxy.sent,
                          "bets_refused": proxy.refused}} if proxy is not None else {})}


def calibrate():
    """t4_validate's calibration, unchanged: cost from calib/concur, client overhead from
    the no-speculation suite medians (same grid, same error)."""
    tr = {}

    def trace_of(n):
        if n not in tr:
            tr[n] = compile_turn(suite.response_text(n), suite.context())
        return tr[n]

    tables = t4.token_tables(trace_of)
    meas = t4.measured_suite()
    names = sorted({k[0] for k in meas})
    best = None
    for c in [0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]:
        cost = t4.fit_cost(c)
        err = statistics.mean(abs(math.log(t4.suite_sim(cost, tables, n, "baseline")
                                           / meas[(n, "baseline")])) for n in names)
        if best is None or err < best[0]:
            best = (err, c)
    return t4.fit_cost(best[1]), tables, best[1]


def known_rows_check(s: dict) -> list[dict]:
    """The first T4 load test's 18 rows next to a prediction set's points for the same arms
    and loads. The conditions differ slightly: that run had no per-run prompt prefix,
    staggered agent starts and prefix-cache reuse across arms."""
    pred = {(r["arm"], r["agents"]): r for r in s["rows"]}
    rows = []
    for arm, n, r in known_rows():
        p = pred.get((arm, n))
        if p is not None:
            rows.append({"arm": arm, "agents": n, "measured_session_p50": r["wall_p50"],
                         "sim_session_p50": p["session_p50"],
                         "measured_tpot_p50": r["root_tpot_p50_ms"],
                         "sim_tpot_p50": p["root_tpot_p50"]})
    return rows


def predict_set(cost, tables, traces, arms: list[str], loads: list[int]) -> tuple[list, dict]:
    runs = []
    for name in arms:
        arm = vb.ARM[name]
        for n in loads:
            rec = sim_run(cost, tables, arm, n, traces, vb.WORKLOADS[arm.workload]["turns"])
            runs.append(rec)
            w = [x["wall_s"] for x in rec["sessions"]]
            print(f"{name:16s} n={n:3d} session p50 {vb.pctl(w, 0.5):6.2f} s  "
                  f"makespan {rec['makespan_s']:6.1f} s", flush=True)
    return runs, vb.summarize(runs, boot=0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=vb.PRESETS["full"]["agents"] + ",48,64")
    ap.add_argument("--arms", default=",".join(vb.PRESETS["full"]["arms"]))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--seq-cap", type=float, default=None, help="skip the fit, use this cap")
    ap.add_argument("--sets", default="P1,P0")
    ap.add_argument("--name", default="predictions", help="output files NAME.json, NAME_table.md")
    a = ap.parse_args()
    t_start = time.time()
    cost0, tables, client_s = calibrate()
    mix = sorted({p for x in vb.ARMS for p in vb.WORKLOADS[x.workload]["patterns"].split(",")})
    traces = {n: compile_turn(suite.response_text(n), suite.context(), chunk=4) for n in mix}
    if a.seq_cap is None:
        cap, cap_scores = fit_seq_cap(cost0, tables, traces)
    else:
        cap, cap_scores = a.seq_cap, None
    cost1 = CappedStepCost(cost0.gpu, cost0.model, cost0.tp, cost0.ov, cost0.decode_table,
                           seq_cap=cap)
    arms, loads = a.arms.split(","), [int(x) for x in a.agents.split(",")]
    sets = {}
    for key, cost in (("P1", cost1), ("P0", cost0)):
        if key not in a.sets.split(","):
            continue
        print(f"--- {key}", flush=True)
        runs, summ = predict_set(cost, tables, traces, arms, loads)
        sets[key] = {"summary": summ, "known_rows_check": known_rows_check(summ),
                     "runs": [{k: v for k, v in r.items() if k != "sessions"}
                              | {"session_walls": [x["wall_s"] for x in r["sessions"]]}
                              for r in runs]}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = {"stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "label": "PREDICTED by the simulator, before any GPU run of the sweep",
           "primary": "P1",
           "calibration": {"t_fixed_ms": 1000 * cost0.ov.t_fixed,
                           "t_per_seq_ms": 1000 * cost0.ov.t_per_seq, "mfu": cost0.ov.mfu,
                           "attn_mfu": cost0.ov.attn_mfu, "client_s": client_s,
                           "kv_tokens": KV_TOKENS, "budget": t4.BUDGET, "max_num_seqs": t4.SEQS,
                           "P1_seq_cap": cap, "P1_fit": cap_scores},
           "summary": sets[a.sets.split(",")[0]]["summary"],  # what `vllm_bench.py plan` reads
           "sets": sets, "wall_s": None}
    path = out / f"{a.name}.json"
    path.write_text(json.dumps(res, indent=1, default=str))
    # GPU minutes per preset, from the primary set's session times (vllm_bench.py plan)
    res["gpu_minutes"] = {}
    for preset in ("quick", "core", "full"):
        ns = argparse.Namespace(preset=preset, arms=None, agents=None, reps=None, turns=None,
                                predictions=str(path))
        res["gpu_minutes"][preset] = {k: v for k, v in vb.plan(ns).items() if k != "rows"}
    res["wall_s"] = time.time() - t_start
    path.write_text(json.dumps(res, indent=1, default=str))
    md = tables_md(res)
    (out / f"{a.name}_table.md").write_text(md)
    print(md[:5000])


def pivot(rows: list[dict], key: str, nd: int) -> list[str]:
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    loads = sorted({r["agents"] for r in rows})
    by = {(r["arm"], r["agents"]): r for r in rows}
    lines = ["| agents | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for n in loads:
        cells = []
        for a in arms:
            v = by.get((a, n), {}).get(key)
            cells.append("-" if v is None else f"{v:.{nd}f}")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return lines


def tables_md(res: dict) -> str:
    c = res["calibration"]
    lines = ["# Simulator predictions for the T4 sweep: generated tables", "",
             f"**PREDICTED, not measured.** Written {res['stamp_utc']} by "
             "`experiments/sweep_predict.py`, before any GPU run of the sweep. One deterministic "
             "simulator run per point (no repeats, no CIs). Loads 48 and 64 are beyond the "
             "sweep's ladder.", "",
             f"Calibration (t4_validate, unchanged): t_fixed {c['t_fixed_ms']:.2f} ms, "
             f"per-sequence {c['t_per_seq_ms']:.3f} ms, GEMM efficiency {c['mfu']:.2f}, "
             f"attention efficiency {c['attn_mfu']:.3f}, client {1000 * c['client_s']:.0f} ms "
             f"each way; KV {c['kv_tokens']} tokens, budget {c['budget']}, max_num_seqs "
             f"{c['max_num_seqs']}. P1 adds seq_cap = {c['P1_seq_cap']}"]
    if c["P1_fit"]:
        lines[-1] += " (fit on the first run's 18 root TPOT p50s):"
        lines += ["", "| seq_cap | root TPOT mean abs log error |", "|---|---|"]
        lines += [f"| {x['seq_cap']} | {x['tpot_mean_abs_log_err']:.4f} |" for x in c["P1_fit"]]
    else:
        lines[-1] += " (given, not fit: the sensitivity set)."
    lines += ["", "## GPU minutes per preset (vllm_bench.py plan, from P1 session times)", "",
              "| preset | runs | estimated minutes |", "|---|---|---|"]
    for k, v in res["gpu_minutes"].items():
        lines.append(f"| {k} | {v['runs']} | {v['est_minutes']} |")
    for key in res["sets"]:
        st = res["sets"][key]
        lines += ["", f"# Set {key}" + (" (primary)" if key == res["primary"] else ""), ""]
        for title, k, nd in (("Session p50 (s)", "session_p50", 2),
                             ("Session p99 (s)", "session_p99", 2),
                             ("Root TPOT p50 (ms)", "root_tpot_p50", 1),
                             ("Root TPOT p99 (ms)", "root_tpot_p99", 1),
                             ("Sessions per minute", "sessions_per_min", 1),
                             ("Goodput (SLO 2x / 2x)", "goodput", 2)):
            lines += [f"## {key}: {title}", ""] + pivot(st["summary"]["rows"], k, nd) + [""]
        lines += [f"## {key}: check against the first T4 load test (known rows)", "",
                  "| arm | agents | session p50 measured | predicted | root TPOT p50 measured "
                  "| predicted |", "|---|---|---|---|---|---|"]
        for r in st["known_rows_check"]:
            lines.append(f"| {r['arm']} | {r['agents']} | {r['measured_session_p50']:.2f} | "
                         f"{r['sim_session_p50']:.2f} | {r['measured_tpot_p50']:.1f} | "
                         f"{r['sim_tpot_p50']:.1f} |")
        lines += ["", vb.summary_md(st["summary"], f"{key}: full summary (same code as the "
                                    "measured report)").replace("\n# ", "\n## ")]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
