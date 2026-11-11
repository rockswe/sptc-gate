# Prefill allowance modes, simulated: fixed vs adaptive vs off

Everything here is **simulated**: `experiments/allowance_ab.py`. Full tables are in
`allowance_ab_tables.md` and the raw rows in `allowance_ab.json`.

## Setup

- Workload: `clog.py`'s RLM-style sessions (rlm_map, rlm_two_stage, rlm_branch,
  research; 3 turns each). Their sub-calls carry long document chunks, the case where a
  prefill allowance can matter. On the T4 spec-ptc workload it almost never binds
  (`predictions.md`).
- Arrivals: open-loop Poisson. Every arm sees the same arrivals, programs and output
  lengths (paired).
- Servers and loads: four simulated servers at a light, medium and heavy load each.
  - H100 + Qwen3-4B, calibrated eager: 0.05, 0.2, 0.6 sessions/s
  - H100 + Qwen3-4B, CUDA graphs: 0.05, 0.2, 0.6
  - RTX 4090 + Qwen3-4B: 0.02, 0.05, 0.1
  - H100 + Qwen3-30B-A3B MoE: 0.05, 0.1, 0.3

  The loads are picked from clog's busy fraction per server.
- Arms:
  - `stock`: vLLM FCFS.
  - `fixed`, `adaptive`, `off`: the plugin as it actually behaves
    (`ServerConfig.plugin_semantics`), differing only in `prefill_allowance`.
  - `adaptive_u`: an exploratory variant where all tagged prefill yields only to untagged
    decoders.
  - Plugin settings: free window 8 (4 for the MoE, the README knee), KV reserve 0.10,
    allowance 512 tokens per step.
- Speculation: spec-ptc's shadow policy (`shadow`), and the same with one bad guess per
  call (`shadow+waste1`, a decoy tagged `bet`).
- Allowance accounting as in the plugin: a tagged prefill is charged to the allowance
  only in a step where the allowance applies to it. The `adaptive` and `adaptive_u` rows
  were re-run after this fix (before it, an uncapped early prefill in an adaptive step also
  used up the allowance of a later bet). `fixed` and `off` rows are unaffected (checked:
  identical on the H100 graphs server). The fix moved the adaptive rows by at most 0.8% on
  any latency metric and 2.8% on the count of cut steps.
- Reduced size: 100 sessions per run, 2 seeds per cell, 240 runs,
  roughly half an hour on 2 workers. The `clog.py` sweeps use 240 sessions and
  3 seeds.

## Session p50 vs plugin `fixed` (shadow workload; the adaptive and off columns are within 1.1 points of the bad-guess workload)

| server | load | adaptive | off | stock (no bad guess / with) |
|---|---|---|---|---|
| H100 eager | light | +0.2% | −0.5% | −0.5% / +12.8% |
| | medium | +0.1% | +1.7% | +1.7% / +22.4% |
| | heavy | 0.0% | +13.7% | +13.7% / +81.5% |
| H100 graphs | light | +1.1% | +2.2% | +2.2% / +19.6% |
| | medium | +1.2% | +3.9% | +3.9% / +32.0% |
| | heavy | 0.0% | +14.8% | +14.8% / +99.5% |
| RTX 4090 | light | +0.8% | +1.7% | +1.7% / +25.7% |
| | medium | +0.5% | +1.8% | +1.8% / +31.0% |
| | heavy | +1.3% | +5.8% | +5.8% / +62.7% |
| H100 MoE | light | −0.6% | **−5.9%** | −5.9% / +26.7% |
| | medium | −0.6% | **−8.8%** | −8.8% / +34.9% |
| | heavy | 0.0% | **−6.2%** | −6.2% / +43.5% |

- Without bad guesses, `off` equals `stock`. The plugin with no bets and no allowance
  schedules like vLLM FCFS, a sanity check of the model.
- Root-stream protection depends on the metric and the load (shadow workload, `off`
  vs `fixed`; the bad-guess workload has the same signs everywhere, within 2 points at
  light load):

  | server | load | root TPOT p99 (ms), fixed / off | root ITL p99 (ms), fixed / off |
  |---|---|---|---|
  | H100 eager | light | 17.7 / 19.3 (off +9%) | **23.7 / 17.9 (off −24%)** |
  | | medium | 19.6 / 23.5 (+20%) | 24.0 / 87.0 (+262%) |
  | | heavy | 23.2 / 33.0 (+42%) | 45.4 / 150.4 (+231%) |
  | H100 graphs | light | 6.0 / 7.1 (+18%) | **8.7 / 5.7 (−34%)** |
  | | medium | 6.5 / 8.4 (+30%) | **8.8 / 7.2 (−18%)** |
  | | heavy | 8.7 / 13.6 (+56%) | 9.6 / 69.9 (+631%) |
  | RTX 4090 | light | 22.7 / 25.9 (+14%) | 47.2 / 177.6 (+276%) |
  | | medium | 25.3 / 29.4 (+16%) | 47.6 / 178.4 (+275%) |
  | | heavy | 30.4 / 39.8 (+31%) | 48.3 / 178.7 (+270%) |
  | H100 MoE | light | 17.3 / 15.9 (−9%) | **26.4 / 20.3 (−23%)** |
  | | medium | 20.4 / 19.4 (−5%) | **26.6 / 24.7 (−7%)** |
  | | heavy | 28.8 / 30.2 (+5%) | 29.5 / 88.8 (+201%) |

  - At heavy load, `fixed` protects the root on both metrics, by 3–7× on ITL p99: `off` lets a long prefill run in one step and stall every decoder.
  - At light load, `fixed` makes the root's ITL p99 worse on the two H100 dense servers
    and on the MoE, by 18–34% (bold). The likely mechanism: a long sub-call prefill is cut
    into 512-token chunks, so many more of the root's steps carry a chunk, while with few
    concurrent prefills the rarer big stalls of `off` fall above the 99th percentile. On
    these servers this is a few milliseconds per token (H100 graphs: 5.7 → 8.7 ms).
  - On most servers `fixed` also delays sub-calls at light load: sub-call TTFT p50 is 2.1×
    `off` on H100 eager (163 → 336 ms) and 3.2× on the MoE (100 → 323 ms). On H100 graphs
    it is lower (123 → 103 ms).
  - The RTX 4090 is the exception: `fixed` wins on both metrics at every load. Its token
    budget is 2048, so `off` already runs long prefills in 2048-token chunks, which are slow
    steps on that GPU.
- `adaptive` vs `fixed`, root TPOT p99: within ±0.6%, except two cells (MoE medium
  +2.6%; RTX 4090 heavy with bad guesses +7.6%). Root ITL p99 is within 0.1% everywhere,
  so `adaptive` does not remove the light-load ITL cost either.

## What it shows

1. `adaptive` changes almost nothing (−0.6% to +1.3% session p50). In these agent
   workloads a root stream is nearly always decoding while sub-calls prefill, so there is
   almost always something to protect. Even at light load, the share of steps where the
   allowance cuts a request only drops from about 4.6% to 3.3%.
   - The class-aware rule (a bet yields to any non-bet decoder) and the untagged-only
     variant (`adaptive_u`) differ by at most 0.1%.
   - The rule is principled: it never limits work when nothing more certain is decoding.
     But in simulation it does not fix any cost, measured or simulated.
2. `fixed` has a light-load cost in simulation, on the stream it protects.
   - Root ITL p99 is 18–34% worse than `off` at light load on both H100 dense servers and
     the MoE (table above), and sub-call TTFT is higher.
   - Session p50: `off` beats `fixed` by 0.5% on the H100 eager server at light load, and
     by 6–9% on the MoE at every load. There each 512-token chunk step re-reads most of the
     experts' weights, so splitting a long prefill into chunks multiplies that cost.
   - On session p50 and root TPOT p99, the dense CUDA-graph servers favour `fixed` even
     at light load. On root ITL p99 they do not.
3. Where `fixed` pays off: at medium and heavy load on dense models it is clearly better
   than `off`, up to 15% on session p50 and 16–56% on root TPOT p99. With bad guesses it
   is far better than stock, which is the plugin's main point and holds in every arm.

## Decision

- Default stays `fixed`. No mode wins everywhere. `fixed` bounds the root's worst
  token gaps at heavy load, where `off` lets them grow 3–7×; the price is a few milliseconds
  of root ITL p99 and slower sub-call starts at light load. `adaptive` is a no-cost safety
  refinement in simulation, not a fix (it keeps the light-load ITL cost), and the T4 has
  not yet measured any of them.
- `adaptive` and `off` ship behind the knob for the second T4 run's A/B.
- For MoE deployments, `off` (or a larger `spec_prefill_budget`, not simulated here)
  looks better on session latency, at the price of the root's worst-case token gaps under
  load. The simulator suggests that, but nothing measures it yet.
- Not done: no new free parameter was introduced or tuned. A stall-bounded allowance,
  sized from measured step times, is a possible next design. It would need online step
  timing in the plugin and was not attempted.
