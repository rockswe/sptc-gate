# Why was the plugin slower with 1 agent on the T4?

The gap (Kaggle T4, vLLM 0.32, Qwen3-1.7B, `results/kaggle_t4/RESULTS.md` section 4): with 1
agent, spec-ptc sessions took **3.10 s with the plugin vs 2.73 s on stock vLLM**, and the
root stream's TPOT was **19.5 vs 16.8 ms**. The write-up guessed that the early-prefill
allowance (`spec_prefill_budget=512` tokens per step) stretches sub-call prefill when there is
nothing to protect.

## Bottom line

- The allowance did not cause it (high confidence). On this workload the allowance
  almost never binds: sub-call prompts are 15–47 tokens, and in a replay with the measured
  token counts it cuts or defers a request in **1 of 563 steps** at 1 agent.
- No other plugin mechanism found by reading the code explains it. The bet machinery
  does not run in that row (it has no bets). Per-step hook overhead is unlikely: the same
  hooks run at 4 and 8 agents, on more requests, with no gap. It is not measured with vLLM
  yet.
- The gap follows the tags, not the time since server start. The simulator fits all
  three stock 1-agent rows within about 1% on root TPOT p50. Against it, the plugin's 1-agent
  rows measured:
  - untagged (no speculation): root TPOT +2.5%, session −3%;
  - spec-ptc: root TPOT +16%, session +12%;
  - spec-ptc + 1 bad guess: root TPOT +19%, session +17%.

  The untagged row was the first load-test row after the plugin server started, and is the least affected.
  A slow first minute would hit it hardest, so it does not fit.
- Two explanations remain, and the data cannot tell them apart (both medium):
  - a plugin cost tied to tagged traffic that code reading did not find (candidate 9);
  - the plugin server's separately compiled kernels, if they are slower only at the batch
    shapes of the tagged rows (candidate 8). In the untagged row the root mostly decodes
    alone; in the spec rows it decodes next to the sub-calls. The two engines did not run
    the same compiled code: stock loaded a cached torch.compile artifact (0.26 s), while
    the plugin server compiled from scratch (32 s), because its `additional_config`
    changes vLLM's compile-cache hash.

  Both have to explain why the 4- and 8-agent rows agree within about 2%. Plain
  run-to-run noise is not excluded (one run per row, 4 turns each), but it would have to
  hit both tagged rows and spare the untagged one (candidate 7, low).
- Only the GPU can settle it. The protocol is at the end. The simulator cannot: it has
  no source of run-to-run variation and no model of compiled kernels.

## Data used

- `results/kaggle_t4/sptc_out/load.json` (stock) and `load_tagged.json` (plugin): one run
  per row.
- `vllm.log` and `vllm_plugin.log`: the two servers' logs for those runs, including their
  startup (compile) lines.
- `suite.json`: per-call token counts.
- The vLLM 0.32 scheduler source (`vllm_src_v0.32.0`), plus `sptc_vllm/scheduler.py` and
  `policy.py` at the commit that ran on Kaggle (`cc110c6` plus the bookkeeping patch
  described in RESULTS.md).

## How the row is computed (it matters)

In `kaggle/vllm_bench.py`'s `load()`, an agent runs 4 turns, each a different pattern:
map16, map_reduce, two_stage, side_branch_chain.
- Session p50 is `walls[len // 2]`: the 3rd of 4 sorted values, a single turn.
- p99 is the maximum.

So the 1-agent "p50" is one turn of whichever pattern ranks third. The suite medians of
those patterns are 1.02, 3.11, 2.82 and 2.81 s, so small perturbations reorder them.

Turn time is dominated by the root stream: the root is served by the same vLLM, at 4
characters per token. A 16% slower root TPOT therefore explains a 13% longer turn. The
question becomes **why the root decoded 2.7 ms per token slower**.

## Stock vs plugin, every row (measured)

| agents | workload | scheduling identical to stock? | session p50 | root TPOT p50 | root TPOT p99 |
|---|---|---|---|---|---|
| 1 | no speculation (untagged) | **yes** (pass-through) | +4.0% | +3.6% | **+13.3%** |
| 1 | spec-ptc (early tags, no bets) | allowance only | **+13.5%** | **+16.2%** | +16.3% |
| 1 | spec-ptc + 1 bad guess | no (bets gated) | −0.1% | +8.8% | +18.5% |
| 4 | no speculation | **yes** | +2.3% | +1.8% | +2.3% |
| 4 | spec-ptc | allowance only | −0.4% | −0.4% | −0.6% |
| 8 | no speculation | **yes** | +0.5% | +0.2% | +0.9% |
| 8 | spec-ptc | allowance only | +1.0% | +1.0% | −1.0% |

(The 4- and 8-agent bad-guess rows are where the plugin acts: −27% and −34% session p50.)

- The untagged 1-agent row is barely slower: +4% session p50 and +3.6% root TPOT p50.
  Its +13% root TPOT p99 is the slowest of 4 turns. The two tagged rows are slower by
  +16% and +9% root TPOT p50.
- The differential test (`tests_vllm/test_sptc_differential.py`, passed on Kaggle) shows the
  plugin schedules untagged traffic exactly like stock vLLM, step by step. The only plugin
  code still running in that row is per-step bookkeeping.
- The **same bookkeeping** also runs at 4 and 8 agents, where those rows agree within 2%.

The bad-guess row needs the simulator to read. Its session time is the same on both
servers (3.38 vs 3.38 s), but the plugin should have been faster there: the replay has it
refuse 35 of the 45 decoys (simulated 2.90 s vs 3.33 s stock). So that row hides a gap of
about the same size as the spec row's. One caveat: the client does not log the decoys, so
it cannot be checked that the real plugin refused them. If it admitted them, the row would
run like stock, as measured, and the gap would be in root TPOT only (+9%).

Measured against the simulator (`sim_vs_t4_after.json`), which has no plugin cost at 1
agent:

| server | 1-agent row | session p50 measured / sim | root TPOT p50 measured / sim (ms) |
|---|---|---|---|
| stock | no speculation | 6.16 / 6.62 s (−7%) | 15.65 / 15.83 (−1.1%) |
| stock | spec-ptc | 2.73 / 2.76 s (−1%) | 16.78 / 16.81 (−0.2%) |
| stock | spec-ptc + 1 bad guess | 3.38 / 3.33 s (+2%) | 19.20 / 19.19 (+0.1%) |
| plugin | no speculation | 6.41 / 6.62 s (−3%) | 16.22 / 15.83 (+2.5%) |
| plugin | spec-ptc | 3.10 / 2.76 s (+12%) | 19.49 / 16.81 (+16%) |
| plugin | spec-ptc + 1 bad guess | 3.38 / 2.90 s (+17%) | 20.90 / 17.50 (+19%) |

`load()` runs, per agent count, the untagged row, then spec-ptc, then spec-ptc with bad
guesses (`kaggle/vllm_bench.py`, loops agents → decoys → mode). The rows above are in
that order. Something made the plugin server slower in its tagged 1-agent rows, and not
because of what the scheduler decided as far as the code shows. It is either a plugin
cost tied to tags, or specific to that server instance and visible only at small batches
of the tagged rows' shape, as a different compiled artifact could be (candidate 8).

## Candidate causes

| # | candidate | evidence | verdict |
|---|---|---|---|
| 1 | **The early-prefill allowance chunks sub-call prefill over more steps** | Sub-call prompts are 15–47 tokens (`suite.json`, chat template included). A step can only exceed 512 tagged tokens if more than 10 calls arrive in the same step, which only map16 does (16 × 39 = 624 tokens): one extra step for 1–3 calls. The server logs show 30–300 prompt tokens/s during the whole load test, with a 50–80% prefix-cache hit rate. In the simulator replay with the measured token counts, the allowance cuts or defers a request in **1 of 563 steps** at 1 agent (4 of 567 at 4 agents, 12 of 567 at 8). | **Ruled out for this run (high).** It is still a real cost elsewhere: on long-prompt workloads the simulator shows it (`allowance_ab.md`). |
| 2 | **Per-step hook overhead** (Python in `schedule()`, `_reserve_prefill_lookahead`, `update_from_output`) | Per step: a few dict and attribute operations, plus one `classify` per scheduled request, against a 2,700 µs gap. The same hooks run at 4 and 8 agents, on more requests, where there is no gap. One caveat: under async scheduling the scheduler's CPU work overlaps the GPU step, and a longer GPU step at 4 and 8 agents could hide a cost that shows at 1 agent. No number exists yet: `tests_vllm/test_sptc_overhead.py` measures it with vLLM on Kaggle. | **Unlikely (medium).** |
| 3 | **Wrong scheduler variant (sync instead of async)** | `SptcScheduler.__new__` picks the async variant from `scheduler_config.async_scheduling`, which `VllmConfig` resolves to `True` before the engine core builds the scheduler (`config/vllm.py` ~1585). `__init__` raises on a mismatch, so a wrong variant would have crashed. Sync scheduling would also slow the 4- and 8-agent rows, which match stock. A gap: the plugin's own startup line never reached the logs (its logger was outside vLLM's `vllm` namespace; fixed in this branch). | **Ruled out (high, by code reading).** It is not visible in the logs; with the fix, the next run will log the variant. |
| 4 | **Interaction with async scheduling** (placeholders, in-flight tokens) | The allowance only touches requests whose `num_tokens - num_computed_tokens > 1`. Async decodes have ≤ 0, so they are never charged or capped. The in-flight logic (`finishes_in_flight`, requeue instead of drop) only runs for bets, and this row has none. | **Ruled out (high).** |
| 5 | **`bets_last` reordering and end-of-step re-gating** | Both run only while bets exist. The 3.10 s row has no bets (no decoys). | **Ruled out for the 3.10 s row (high).** In the bad-guess row the plugin does change scheduling, and the simulator predicts it faster than stock there (2.90 vs 3.33 s). |
| 6 | **The tag itself** (`vllm_xargs`) | `extra_args` is read for KV/EC transfer parameters only (`v1/request.py`, `output_processor.py`). It is not part of the prefix-cache hash. | **Ruled out (high).** |
| 7 | **Run-to-run variation, e.g. a slower first minute on the plugin server** | Each row is one run of 4 turns, and the p50 is a single turn. The two servers ran 75 minutes apart (21:10 and 22:25 UTC), on a shared Kaggle VM (4 vCPUs shared by the engine core, the API server and the client processes). But the row order argues against a warm-up effect: the untagged row ran first after start and is the least affected (+2.5% root TPOT vs the simulator), while the two tagged rows that followed are +16% and +19%. The only first-request JIT compiles (2 Triton kernels) happened in the untagged row on both servers. | **Unlikely (low).** It cannot be excluded with one run per row; the protocol below measures the spread. |
| 8 | **The two servers ran different compiled code** | Stock (`vllm.log` lines 206-224): `Directly load AOT compilation from path ...`, `torch.compile took 0.26 s`, engine init 19 s. Plugin (`vllm_plugin.log` lines 206-229): `Starting torch.compile`, `Compiling a graph for compile range (1, 2048) takes 19.42 s`, `torch.compile took 32.04 s`, an inductor warning `Not enough SMs to use max_autotune_gemm mode`, engine init 77 s. `additional_config` is part of vLLM's compile hash (`config/vllm.py` ~549), so every plugin config compiles fresh on first launch. The stock artifact was compiled before this log starts, so its compile settings cannot be compared. Inductor makes benchmark-based choices (`benchmark_combo_kernel: True` in both configs), so two compiles need not give the same kernels. A difference that matters only at the small mixed batches of the tagged 1-agent rows (root plus a few sub-calls) would fit a gap that is large there and small in the untagged row, where the root mostly decodes alone. Why it would not show at 4 and 8 agents is not explained. | **One of the two likely explanations (medium), with 9.** Not tested. The protocol below holds the compiled code equal: a stock launch that shares the plugin's artifact, and every arm again with `--enforce-eager`. |
| 9 | Something in the plugin not found by reading the code | No mechanism was found that only acts at 1 agent with tags. But the gap follows the tags: +16% and +19% root TPOT over the simulator in the two tagged rows, +2.5% in the untagged row on the same server. The simulator, now matched to the plugin's semantics (below), reproduces the plugin spec rows at 4 and 8 agents within 4% (session p50) and 5% (root TPOT), and the plugin no-speculation rows within 3% and 7% (the 4-agent row: 17.1 vs 18.3 ms root TPOT). It shows no 1-agent cost. A cost that arises only with tagged requests, and that the longer GPU steps at 4 and 8 agents hide under async scheduling (candidate 2's caveat), would fit. | **One of the two likely explanations (medium), with 8.** |

## What the simulator says

All files are in `results/t4_run1_analysis/` and written by `experiments/t4_validate.py`. Two changes
were made, in this order:

1. A replay bug, fixed. The old `t4_validate.py` kept each call's measured prompt and
   output length in backend state, set when the call started. It also swapped
   `sptc_sim.agent.Request` per turn. The request is only built one client delay (30 ms)
   later, so a call could get the tokens of a call started after it. Example: a real call
   inherited its decoy's forced maximum length, or another agent's call. Now both are looked
   up by the call's rid. Fixing it:
   - improves the spec-ptc suite: max error 12.2% → 5.7%, mean 4.3% → 2.8%;
   - makes the stock bad-guess rows heavier: 1 agent 3.11 → 3.33 s (measured 3.38); 4 agents
     4.29 → 5.22 s (measured 5.04); 8 agents 6.31 → 8.21 s (measured 6.62).

   Part of the old fit on those rows came from the bug.
2. The plugin modeled as it actually behaves (`ServerConfig.plugin_semantics`):
   - tags fixed at dispatch (no promotion);
   - vLLM FCFS with bets moved last (not program-level FCFS);
   - no eviction of running bets for waiting work;
   - no gate at submit: bets are gated when the waiting loop reaches them, rejected in the
     step the gate fails, and held for at most `bet_hold_steps`.

All 18 load rows (`sim_vs_t4_compare.md`):

| model | session p50 median / max abs error | root TPOT p50 median / max |
|---|---|---|
| before (`sim_vs_t4_before.md`: written at commit 938cad8, identical to `results/kaggle_t4/sim_vs_t4.md` on main; that file is now regenerated with the fix) | 3% / 16% | 5% / 17% |
| replay fix only (`sim_vs_t4_tokenfix.md`) | 3% / 21% | 5% / 22% |
| replay fix + plugin semantics (`sim_vs_t4_after.md`) | 3% / 21% | 5% / 22% |

- The worst row after the fix is stock with 8 agents and bad guesses: 8.21 s predicted
  vs 6.62 s measured. The simulator probably makes the forced-length decoys too costly at
  high load. That is a separate issue, not looked into here.
- The 1-agent plugin rows stay off:
  - spec-ptc: 2.76 s and 16.8 ms simulated, vs 3.10 s and 19.5 ms measured;
  - with a bad guess: 2.90 s and 17.5 ms, vs 3.38 s and 20.9 ms.
- The simulated plugin equals simulated stock at 1 agent without bad guesses (2.76 s
  both).

The faithful model does not reproduce the 1-agent cost. That is consistent with candidates 1–6
being ruled out. No new parameter was fitted to any load row. The calibration is the same as
before: the T4's solo measurements, plus one client overhead (30 ms each way, refitted with
the same result) fitted on the no-speculation suite medians.

## What only the GPU can settle, and how

*Written before the second T4 run, which followed this protocol. Its result is in
`../kaggle_t4_v3/RESULTS.md`, section 4.*

All of this is CPU-cheap on the Kaggle side.
1. Hold the compiled code equal, and record it. The prefill-allowance mode is part of
   `additional_config`, and `additional_config` is part of vLLM's compile hash
   (`config/vllm.py` ~549). So every plugin arm compiles its own torch.compile artifact,
   and relaunching an arm reloads that arm's own artifact. Relaunching makes the compile
   *state* equal (cached), not the *code*. Two ways to make the code equal:
   - Eager launches: run every arm a second time with `--enforce-eager`. It sets the
     compilation mode to none and turns CUDA graphs off (`config/vllm.py` ~1691), so all
     arms run the same uncompiled code. Absolute times are slower; compare arms within
     the eager launches only.
   - Shared-artifact pair: launch stock vLLM with the plugin-`fixed` arm's exact
     `--additional-config`. Stock does not use the `sptc` key, it only hashes it, and
     `--scheduler-cls` is not part of the hash (`SchedulerConfig.compute_hash` hashes
     only `max_num_batched_tokens` and `max_num_seqs`). Stock and plugin `fixed` then
     run one compiled artifact: the October 19 comparison with the code held equal.

   For every launch, keep the log lines `Using cache directory: .../torch_compile_cache/
   <hash>`, `Directly load AOT compilation` (cached) or `Compiling a graph ... takes`
   (fresh), and `torch.compile took`. Two launches with the same cache directory ran the
   same artifact. Launch each compiled arm once to fill its cache, and measure on later
   launches.

   Compile-to-compile variance needs separate compiles. Stock relaunched reuses one cached
   artifact, so stock vs stock measures launch noise only. A stock arm with an inert
   `--additional-config '{"sptc_noop": 1}'` compiles fresh; each new value (2, 3, ...) is
   one more sample.

   Then **warm each server up** with one throwaway 1-agent pass before measuring.
2. Repeat the 1-agent spec-ptc row at least 5 times per arm, on these four arms:
   - stock vLLM;
   - plugin `fixed`;
   - plugin `adaptive`;
   - plugin `off`;

   each compiled and with `--enforce-eager`, plus the shared-artifact stock arm (compiled).
   About 1 minute per pass and arm. Interleave server launches if time allows (stock,
   plugin, stock, plugin). Report the median and the spread per arm.
3. Run the plugin server with untagged traffic too (`load` without `--tag-bets`). This
   separates "plugin server instance" from "tags".
4. Read the evidence:
   - plugin `off` vs plugin `fixed`, **eager launches**: isolates the allowance
     (predicted: no difference, `predictions.md`). On compiled launches the two arms also
     run different artifacts, so a difference there does not isolate it;
   - stock vs plugin `fixed`, shared-artifact pair and eager launches: the plugin with the
     code held equal. A gap that survives there is the plugin's (candidate 9); a gap that
     only shows between separately compiled servers points at candidate 8;
   - plugin-untagged vs stock (shared artifact): hooks plus server instance (predicted: no
     difference);
   - stock vs stock across launches: the launch noise floor;
   - stock vs stock with inert configs: whether a separately compiled artifact alone
     moves the 1-agent rows (candidate 8).
5. Run `pytest tests_vllm/test_sptc_overhead.py -s`. It gives the plugin's per-step CPU
   cost against stock vLLM on the Kaggle CPU.
6. Check the server log for `sptc scheduler (SptcAsyncScheduler): ... prefill allowance
   512 (fixed)`. It now reaches vLLM's log, and confirms the variant and the mode.
7. Optionally, add `--enable-logging-iteration-details`. vLLM 0.32 then logs per
   iteration the prefill/decode request and token counts, and the time spent waiting for
   the step (`v1/engine/core.py` ~578). That would show directly whether tagged prefill was
   ever chunked, and whether decode-only steps were slower on one server. Under async
   scheduling its `elapsed_ms` is the wait for the step's result, not the GPU time.

**If plugin `off` is still slower than stock by a similar margin on eager launches**, the
allowance is exonerated on the GPU too. The remaining difference is then the plugin (if it
also survives the shared-artifact pair), the compiled artifact (if it only shows between
separately compiled servers, or the inert-config stock arms spread as much), or noise (if
stock vs stock spreads as much).
