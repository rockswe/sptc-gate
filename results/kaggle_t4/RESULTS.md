# Real-GPU check: vLLM 0.32 on a Kaggle T4 (October 19–20, 2026)

This is the first measurement of the serving claims on real vLLM.

- Setup: one Tesla T4 (16 GB, Turing, no bf16, no FlashAttention 2), vLLM 0.32.0 with
  CUDA graphs on, Qwen/Qwen3-1.7B in fp16, vLLM's defaults for small GPUs (2,048-token
  batch budget).
- Files: raw results in `sptc_out/` (from `kaggle/sptc_kaggle.ipynb` and
  `kaggle/vllm_bench.py`). The simulator comparison is in `sim_vs_t4.md`.

## 1. Pre-registered predictions vs measured

`sptc_out/predict.json` was stamped 19:27:57 UTC, from the solo calibration alone,
before any concurrency run.

| measurement | predicted | measured | verdict |
|---|---|---|---|
| decode step with 1 / 3 / 7 / 15 other decoders (vs alone) | 1.00 / 1.01 / 1.03 / 1.06× | **1.08 / 1.14 / 1.26 / 1.50×** | miss: about 0.44 ms per extra sequence was not in the model |
| root's worst stall while a 468 / 1,405 / 2,809-token prompt prefills | 272 / 843 / 1,174 ms | 118 / 475 / 881 ms | miss: too pessimistic by 1.3–2.3× |
| that sub-call's time to first token | 0.27 / 0.84 / 1.78 s | 0.15 / 0.53 / 1.58 s | same miss |
| fan-out makespan, 1 / 2 / 4 / 8 / 16 calls | 1.17 / 1.34 / 1.68 / 2.36 / 3.73 s | 1.15 / 1.33 / 1.57 / 2.05 / 3.01 s | close at small k; 24% high at 16 |

**Why the two misses happened:**
- Decode. Extra concurrent sequences cost about 0.4–0.5 ms per step
  each. That is cheap (16 sequences run at 1.5× the batch-1 step for 16× the work), but
  it is not free, and the central roofline estimate assumed it was.
- Prefill. The model fit its compute rate to the longest prompt. On a T4 without
  FlashAttention, prefill throughput drops with prompt length (4,200 tokens/s at 464
  tokens; 1,900 tokens/s at 2,800), so a single linear rate over-predicts short prompts.
  Section 4 fixes this with a separate attention-efficiency term.

## 2. spec-ptc's own suite, real sub-calls, natural output lengths

These are spec-ptc's benchmark patterns, with the root stream scripted at 60 tok/s as in
its `runs.csv`. Medians of 3 runs:

| pattern | no speculation | spec-ptc | speedup | output tokens per call (median, max, coefficient of variation) |
|---|---|---|---|---|
| map16 | 4.37 s | 1.02 s | 4.31× | 9, 11, 0.11 |
| map8_slow | 25.36 s | 4.01 s | 6.32× | 152, 165, 0.05 |
| two_stage | 12.35 s | 2.82 s | 4.38× | 40, 85, 0.72 |
| multiblock | 13.55 s | 2.80 s | 4.83× | **96, 96 (every call hits the cap)**, 0.01 |
| mutating_loop | 7.12 s | 2.06 s | 3.46× | 49, 63, 0.12 |
| map_reduce | 7.40 s | 3.11 s | 2.38× | 13, 96, **1.15** |
| syntax_gauntlet | 5.81 s | 2.69 s | 2.16× | 54, 96, **0.86** |
| side_branch_chain | 4.24 s | 2.81 s | 1.51× | 8, 20, 0.80 |

The per-call token counts confirm the explanation for the simulator's four largest
calibration misses in report §2.2:
- `multiblock`'s calls run to the token cap;
- `syntax_gauntlet`, `map_reduce` and `side_branch_chain` mix very short and long calls.

That was the hypothesis then; it is measured now.

## 3. Load test: does speculation clog a shared vLLM server?

Each of 1, 4 or 8 agents runs 4 turns of spec-ptc programs (`map16`, `map_reduce`,
`two_stage`, `side_branch_chain`). The **root model's stream is served by the same vLLM**:
each root token releases 4 characters of the program. Sub-calls have natural lengths.

A "bad guess" is a decoy speculation the same prompt size as each real one, forced to
the maximum output length and cancelled at turn end. One run per row.

| agents | session p50, no speculation | spec-ptc | spec-ptc + 1 bad guess per call | root TPOT p50 (p99): no spec | spec-ptc | + bad guess |
|---|---|---|---|---|---|---|
| 1 | 6.16 s | 2.73 s (2.26×) | 3.38 s (1.82×) | 15.7 (15.7) ms | 16.8 (17.1) | 19.2 (19.6) |
| 4 | 7.20 s | 3.55 s (2.03×) | 5.04 s (1.43×) | 18.0 (18.2) | 21.1 (22.6) | 29.6 (33.0) |
| 8 | 8.01 s | 4.36 s (1.84×) | 6.62 s (1.21×) | 19.9 (20.2) | 25.6 (29.3) | **39.0 (45.3)** |

**What the table shows:**
1. Correct speculation didn't clog the server, it helped. It cut session time 1.8–2.3×.
   The gain shrinks with load. Its cost is other agents' root streams: +7% → +29% at p50
   and +45% at p99 with 8 agents.
2. Bad guesses eat the gain, and the damage grows with load. At 8 agents the speedup
   falls from 1.84× to 1.21×, and root TPOT doubles (p50 39 ms vs 20 ms; p99 45 vs 20).
   At this load it was still a net gain. 16 agents were not run, so whether it inverts on
   this GPU is untested.

## 4. The scheduler plugin on real vLLM

**Unit tests.** `pytest tests tests_vllm`: **151 passed, 9 skipped.** The skips are static
checks that read a vLLM source tree that was not on the Kaggle machine.
- The first run had 2 failures. The plugin cleared finished bets from its bookkeeping one
  step late; it now clears them as soon as vLLM reports them finished. The change was
  patched in, and all tests passed on the rerun.
- The suite includes a step-by-step differential test showing untagged traffic is
  scheduled exactly as by stock vLLM. *(Note, October 20: that version compared only part
  of each step's scheduler output, in one narrow config, and could not catch capped
  untagged prefill (audit #13); the broadened test has not run on vLLM. See README,
  "Differential test".)*

**End-to-end smoke tests** through the OpenAI API: all pass.
- S1: a bet admitted while the server is idle completes normally.
- S2: a bet arriving with no spare capacity is refused at once:
  `finish_reason=abort`, `stop_reason=sptc_bet_rejected`. Streamed, it ends with no finish
  reason, as documented.
- S3: an `early`-tagged call completes. The run also printed a concurrent normal
  stream's p99 inter-token gap of 45 ms (untagged pass) and 39 ms (tagged pass), but that
  difference does not show the allowance: both passes sent the same prompt with prefix
  caching on, so the tagged pass prefilled about 18 tokens (audit #41). The smoke test
  now uses a fresh prompt per pass and compares the stream's longest stall; it has not run again. Section S of
  `kaggle/sptc_kaggle_v3.ipynb` runs it on vLLM (corrected October 20; audit ledger
  `results/corrections/ledger.md`, #41).
- S4: under KV pressure, a *running* bet is dropped (`stop_reason=sptc_bet_dropped`,
  after 3,426 characters).
- No tracebacks in any server log.

**Tagged load test.** The same load test with the plugin, decoys tagged `bet` and
spec-ptc's calls tagged `early`:

| agents | spec-ptc + 1 bad guess, session p50: stock → plugin | root TPOT p50 (p99): stock → plugin | plugin, no bad guess (reference) |
|---|---|---|---|
| 1 | 3.38 → 3.38 s | 19.2 (19.6) → 20.9 (23.2) ms | 3.10 s, 19.5 ms |
| 4 | 5.04 → **3.68 s** | 29.6 (33.0) → **21.8 (23.6)** | 3.53 s, 21.0 ms |
| 8 | 6.62 → **4.41 s** | 39.0 (45.3) → **25.9 (29.5)** | 4.41 s, 25.8 ms |

**What the table shows:**
- Under load, the plugin removes the cost of bad guesses. At 8 agents, sessions with
  one bad guess per call are as fast as sessions with none (4.41 s vs 4.41 s), and other
  agents' root streams return to the correct-speculation level (p99 29.5 ms vs 45.3).
- Untagged traffic is unaffected. The no-speculation rows under the plugin match stock
  vLLM within 1–4% (e.g. 8.05 vs 8.01 s).
- The plugin costs something at light load. With 1 agent, spec-ptc sessions took
  3.10 s against 2.73 s on stock vLLM, and root TPOT was 19.5 ms against 16.8 ms. The
  first guess was the early-prefill allowance. A later simulated replay makes it unlikely
  (it cuts or defers a request in 1 of 563 steps on this workload,
  `../t4_run1_analysis/root_cause.md`), but that is not a GPU test; the second run's A/B with the
  allowance off is (corrected October 20: this read "rules it out"). The
  cause is open. The gap shows in the tagged rows, not in the untagged one; the candidates
  are a plugin cost not found in the code and the plugin server's separately compiled
  kernels. The simulator does not reproduce it (section 5).
- Caveat: the client does not log the decoys, so it can't confirm directly that each
  one was refused or dropped. That is inferred from the timings, plus S2 and S4 showing
  the mechanism works.

## 5. Does the simulator predict this run?

This comparison is not pre-registered. It is run afterwards, with the simulator
calibrated from the T4's own solo measurements and fed the measured per-call token
counts (`../../experiments/t4_validate.py`, `sim_vs_t4.md`).

**Inputs taken from the T4 run** (none is a predicted outcome):
- `calib.json`: batch-1 decode, and solo prefill at 3 lengths. These give the GEMM
  efficiency and a separate attention efficiency (1.3% of peak, a lumped stand-in for the
  T4's missing FlashAttention), fit by least squares.
- `concur.json` M3: 0.44 ms per extra decoding sequence.
- `suite.json`: per-call prompt and output tokens from the no-speculation runs.

**Fitted on outcomes:** one client overhead (30 ms each way), on the no-speculation suite
medians only.

**Results:**

| predicted quantity | median error | mean error | worst |
|---|---|---|---|
| spec-ptc suite wall time, 8 patterns | **2.5%** | 2.8% | 5.7% |
| load test session p50, 18 rows (stock and plugin) | **3%** | — | 21% |
| load test root TPOT p50, 18 rows | **5%** | — | 22% |

- The simulator predicted the plugin's main effect: the 8-agent bad-guess run identical
  to the no-bad-guess run (4.45 s vs 4.45 s; measured 4.41 vs 4.41).
- Its biggest misses:
  - the 8-agent bad-guess run on stock vLLM: 8.21 vs 6.62 s (+21%), root TPOT 48.6 vs
    39.0 ms. It probably makes the forced-length decoys too costly at high load.
  - the plugin at 1 agent, where it shows no light-load cost: 2.76 vs 3.10 s, and 2.90 vs
    3.38 s with a bad guess.
- Correction. A first version of this section reported the suite at mean 4.3% and
  worst 12%, and the load rows at worst 16% and 17%, with the 4-agent stock bad-guess run
  as the biggest miss (4.29 vs 5.04 s). That version had a replay bug: a call could take
  the token counts of a later call or of a decoy. Fixing it improved the suite and the
  4-agent row (now 5.22 s), and worsened the 8-agent stock bad-guess row (was 6.31 s).
  Part of the old load-row fit came from the bug. Old and new, row by row:
  `../t4_run1_analysis/sim_vs_t4_compare.md`. The fix and the plugin model it uses are described in
  `../t4_run1_analysis/root_cause.md`.

## Limits

- Small scale: one GPU type, one small model, one run per load row, 4 turns per agent,
  at most 8 agents.
- Bad guesses: decoys are forced to maximum length. That makes them heavier than the
  real calls, which mostly stop early.
- Discarded first attempt: the first load-test attempt failed inside its worker
  processes (cause unknown; the root stream received nothing). It was discarded and rerun
  after the runner was changed to natural lengths and to report failures. All numbers
  here are from the rerun.
- Patches made on Kaggle: they are mirrored in the repository's `kaggle/vllm_bench.py`,
  `integrations/sptc_vllm/scheduler.py` and `kaggle/sptc_kaggle.ipynb`:
  - the load runner's natural lengths and failure reporting;
  - the plugin's bookkeeping fix;
  - the S4 server size.
