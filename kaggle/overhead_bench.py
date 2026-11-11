"""Scheduler overhead: wall time of one scheduling step, stock vLLM vs the sptc plugin.

  python kaggle/overhead_bench.py vllm --out DIR [--n 8,32,64,128,256,512] [--steps 300]
  python kaggle/overhead_bench.py pure --out DIR [--n ...]                # no vLLM needed

vllm  needs vllm==0.32.0 (CPU is enough: no model runs; the scheduler is driven directly
      with the factory of integrations/tests_vllm/_helpers.py, which fetches only the
      facebook/opt-125m config from the HF hub). For each N it builds a scheduler with N
      running decodes and N/2 requests waiting behind max_num_seqs, and times
      schedule() and update_from_output() separately, step by step:
        stock          vLLM's Scheduler / AsyncScheduler
        sptc-untagged  SptcScheduler, no tagged traffic (the pass-through cost)
        sptc-tagged    SptcScheduler; running: 1/4 bets, 1/4 early; waiting: 1/2 early.
                       free_window, kv_reserve and bet_hold_steps are set so that no bet
                       is ever rejected, which keeps the bet bookkeeping busy every step
      for sync and async scheduling. Reports microseconds per step (median, p90).
pure  the plugin's own per-step work on plain objects (sptc_vllm.policy only), in a
      decode-saturated steady state, following the hooks' code paths: begin-step bet
      sweep and running reorder, the allowance hook per running request, the
      update_from_output sweep. It excludes vLLM's own loop and the cost of calling the
      hooks, so it is an estimate of the added work, not of schedule().

Context for the numbers: a Qwen3-1.7B decode step on the T4 takes about 16 ms
(results/kaggle_t4/sptc_out/calib.json), so 16 us of scheduler time is 0.1% of a step.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def _stats(ns: list[int]) -> dict:
    us = [x / 1000 for x in ns]
    return {"p50_us": statistics.median(us), "p90_us": _q(us, 0.9), "mean_us": statistics.mean(us)}


# ----------------------------------------------------------------------------- vllm
VARIANTS = ("stock", "sptc-untagged", "sptc-tagged")


def _cls(i: int, tagged: bool) -> str | None:
    if not tagged:
        return None
    return {0: "bet", 1: "early"}.get(i % 4)


def _waiting_cls(i: int, tagged: bool) -> str | None:
    """Waiting requests: early or normal, never bets. A bet waiting behind normal work is
    rejected by the gate at once (non-bet work waiting), so it would not stay to be timed."""
    return "early" if tagged and i % 2 else None


def vllm_case(n: int, variant: str, async_scheduling: bool, steps: int, prompt: int = 64) -> dict:
    sys.path.insert(0, str(ROOT / "integrations" / "tests_vllm"))
    from _helpers import build, make_sched, req, runner_output

    budget = max(8192, 4 * n)
    kw = dict(async_scheduling=async_scheduling, max_num_seqs=n, num_blocks=200_000,
              max_num_batched_tokens=budget)
    if variant == "stock":
        s = build(**kw)
    else:
        # never reject a bet (window, KV reserve, hold limit out of reach) and no prefill
        # allowance during loading, so every bet stays running and its bookkeeping runs
        # every step
        s = make_sched({"free_window": 10**6, "kv_reserve": 0.0, "bet_hold_steps": 10**9,
                        "spec_prefill_budget": 0}, **kw)
    tagged = variant == "sptc-tagged"

    def step():
        out = s.schedule()
        s.update_from_output(out, runner_output(s, out))

    # load n running requests in batches that fit one step's token budget (with the
    # decodes of those already running), so nothing is left waiting behind a bet
    batch = max(1, (budget - n) // prompt - 1)
    for start in range(0, n, batch):
        for i in range(start, min(n, start + batch)):
            s.add_request(req(f"r{i}", prompt, _cls(i, tagged), max_tokens=10**6))
        step()
    for i in range(n // 2):  # these wait behind max_num_seqs for the whole measurement
        s.add_request(req(f"w{i}", prompt, _waiting_cls(i, tagged), max_tokens=10**6))
    for _ in range(3):
        step()
    assert len(s.running) == n and len(s.waiting) == n // 2, (variant, len(s.running), n)
    sched, upd = [], []
    gc.collect()
    for _ in range(steps):
        t0 = time.perf_counter_ns()
        out = s.schedule()
        t1 = time.perf_counter_ns()
        ro = runner_output(s, out)
        t2 = time.perf_counter_ns()
        s.update_from_output(out, ro)
        t3 = time.perf_counter_ns()
        sched.append(t1 - t0)
        upd.append(t3 - t2)
    assert len(s.running) == n and len(s.waiting) == n // 2, (variant, len(s.running), n)
    bets = sum(_cls(i, tagged) == "bet" for i in range(n))
    return {"n_running": n, "n_waiting": n // 2, "running_bets": bets, "variant": variant,
            "scheduling": "async" if async_scheduling else "sync", "steps": steps,
            "schedule": _stats(sched), "update_from_output": _stats(upd),
            "total_p50_us": statistics.median((a + b) / 1000 for a, b in zip(sched, upd))}


def run_vllm(a) -> dict:
    import vllm

    rows = []
    for async_scheduling in (False, True):
        for n in a.n:
            for variant in VARIANTS:
                r = vllm_case(n, variant, async_scheduling, a.steps)
                rows.append(r)
                print(json.dumps(r), flush=True)
    return {"vllm": vllm.__version__, "python": sys.version.split()[0], "rows": rows}


# ----------------------------------------------------------------------------- pure
class _R:
    """The request attributes the plugin's hooks read."""

    __slots__ = ("request_id", "extra_args", "num_tokens", "num_computed_tokens", "running",
                 "num_output_placeholders", "num_prompt_tokens", "max_tokens")

    def __init__(self, i: int, cls: str | None) -> None:
        self.request_id = f"r{i}"
        self.extra_args = {"sptc_class": cls} if cls else None
        self.num_tokens, self.num_computed_tokens = 100, 99  # decoding
        self.running, self.num_output_placeholders = True, 0
        self.num_prompt_tokens, self.max_tokens = 64, 10**6


def pure_case(n: int, tagged: bool, steps: int) -> dict:
    """One decode-saturated step of the plugin's own work, in the order its hooks run
    (integrations/sptc_vllm/scheduler.py): begin-step sweep and reorder, the prefill-
    allowance hook once per running request, the update_from_output sweep. The waiting
    loop is not entered (max_num_seqs is full), and no bet waits: behind normal work a
    waiting bet is rejected at once."""
    from sptc_vllm import policy

    bet, normal = policy.SptcClass.BET, policy.SptcClass.NORMAL
    cfg = policy.SptcConfig()
    running = [_R(i, _cls(i, tagged)) for i in range(n)]
    running_bets = {r.request_id: r for r in running if policy.classify(r.extra_args) is bet}
    waiting_bets: dict = {}
    allow = policy.PrefillAllowance(cfg.spec_prefill_budget)

    def rank(r: _R) -> int:
        if r.request_id not in running_bets:
            return 0
        return 1 if policy.finishes_in_flight(
            num_output_placeholders=r.num_output_placeholders,
            num_computed_tokens=r.num_computed_tokens, num_prompt_tokens=r.num_prompt_tokens,
            max_tokens=r.max_tokens) else 2

    times = []
    gc.collect()
    for _ in range(steps):
        t0 = time.perf_counter_ns()
        # _sptc_begin_step
        allow.reset()
        if running_bets:
            for rid in [rid for rid, r in running_bets.items() if not r.running]:
                del running_bets[rid]
        if running_bets:
            running = policy.order_by_rank(running, rank)
        if waiting_bets:
            pass  # none in this steady state
        # _reserve_prefill_lookahead, once per scheduled running request
        for r in running:
            if not (allow.unlimited or policy.classify(r.extra_args) is normal
                    or not policy.is_prefill(r.num_tokens, r.num_computed_tokens)):
                allow.charge(allow.cap(1))
        # update_from_output sweep; _sptc_end_step finds no waiting bet
        if running_bets:
            [rid for rid, r in running_bets.items() if not r.running]
        times.append(time.perf_counter_ns() - t0)
    return {"n_running": n, "n_waiting": n // 2, "running_bets": len(running_bets),
            "tagged": tagged, "steps": steps, "policy": _stats(times)}


def run_pure(a) -> dict:
    rows = []
    for n in a.n:
        for tagged in (False, True):
            r = pure_case(n, tagged, a.steps)
            rows.append(r)
            print(json.dumps(r), flush=True)
    return {"python": sys.version.split()[0], "rows": rows}


# ----------------------------------------------------------------------------- report
def table(res: dict, kind: str) -> str:
    head = (f"Measured {res.get('stamp_utc', '?')}, Python {res.get('python', '?')}"
            + (f", vLLM {res['vllm']}" if "vllm" in res else "")
            + f", `overhead_bench.py {' '.join(res.get('argv', []))}`. Microseconds per step.\n\n")
    if kind == "pure":
        lines = ["| running | waiting | tagged | policy work p50 us | p90 us |", "|---|---|---|---|---|"]
        for r in res["rows"]:
            lines.append(f"| {r['n_running']} | {r['n_waiting']} | {r['tagged']} | "
                         f"{r['policy']['p50_us']:.1f} | {r['policy']['p90_us']:.1f} |")
        return head + "\n".join(lines) + "\n"
    lines = ["| scheduling | running | waiting | variant | schedule() p50 us | p90 us | "
             "update_from_output() p50 us | total p50 us | vs stock |",
             "|---|---|---|---|---|---|---|---|---|"]
    stock = {(r["scheduling"], r["n_running"]): r["total_p50_us"] for r in res["rows"]
             if r["variant"] == "stock"}
    for r in res["rows"]:
        base = stock.get((r["scheduling"], r["n_running"]))
        rel = f"{r['total_p50_us'] - base:+.1f} us" if base is not None else "-"
        lines.append(f"| {r['scheduling']} | {r['n_running']} | {r['n_waiting']} | {r['variant']} "
                     f"| {r['schedule']['p50_us']:.1f} | {r['schedule']['p90_us']:.1f} | "
                     f"{r['update_from_output']['p50_us']:.1f} | {r['total_p50_us']:.1f} | {rel} |")
    return head + "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["vllm", "pure"])
    ap.add_argument("--n", default="8,32,64,128,256,512")
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--out", default="kaggle_out")
    a = ap.parse_args()
    a.n = [int(x) for x in a.n.split(",")]
    res = run_vllm(a) if a.cmd == "vllm" else run_pure(a)
    res.update(stamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), argv=sys.argv[1:])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"overhead_{a.cmd}.json").write_text(json.dumps(res, indent=1))
    (out / f"overhead_{a.cmd}.md").write_text(table(res, a.cmd))
    print(table(res, a.cmd))


if __name__ == "__main__":
    main()
