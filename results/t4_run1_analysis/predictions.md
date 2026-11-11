# Predictions for the second T4 run's A/B (simulated, not measured)

Written by `experiments/t4_validate.py --predict`; numbers in `predictions.json`.

## Calibration (the same as `sim_vs_t4_after.md`; no load-test row is an input)

- Step cost from the T4's solo runs: `calib.json` (batch-1 decode, solo prefill at 3 lengths) and `concur.json` M3 (step time vs concurrent decoders): t_fixed 1.90 ms, per sequence 0.436 ms, GEMM efficiency 0.32, attention efficiency 0.013.
- Per-call prompt and output tokens: `suite.json` (no-speculation runs). Bad guesses are forced to the call's max_tokens, as in `kaggle/vllm_bench.py`.
- Fitted on outcomes: one client overhead (30 ms each way), on the no-speculation suite medians only.
- Server: vLLM defaults for small GPUs (2,048-token step budget, 256 sequences). Plugin: free_window 8, kv_reserve 0.10, spec_prefill_budget 512, modeled with `plugin_semantics`.
- Workload: `vllm_bench.py load`, 4 turns per agent (map16, map_reduce, two_stage, side_branch_chain), root served at 4 characters per token; p50 and p99 are the same order statistics as `load()` (at 1 agent: the 3rd of 4 turns and the max).

## Table

| agents | workload | arm | session p50 (s) | session p99 (s) | root TPOT p50 (ms) | root TPOT p99 (ms) | steps the allowance cut | bets rejected | measured 2026-10-19: session p50, TPOT p50 / p99 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | spec-ptc | stock | 2.76 | 2.99 | 16.8 | 18.3 | 0 of 563 | 0 | 2.73 s, 16.8 / 17.1 ms |
| 1 | spec-ptc | plugin fixed | 2.76 | 2.99 | 16.8 | 18.1 | 1 of 563 | 0 | 3.10 s, 19.5 / 19.9 ms |
| 1 | spec-ptc | plugin adaptive | 2.76 | 2.99 | 16.8 | 18.1 | 1 of 563 | 0 |  |
| 1 | spec-ptc | plugin off | 2.76 | 2.99 | 16.8 | 18.3 | 0 of 563 | 0 |  |
| 1 | spec-ptc +1 bad guess | stock | 3.33 | 3.47 | 19.2 | 22.2 | 0 of 566 | 0 | 3.38 s, 19.2 / 19.6 ms |
| 1 | spec-ptc +1 bad guess | plugin fixed | 2.90 | 3.04 | 17.5 | 18.1 | 1 of 563 | 35 | 3.38 s, 20.9 / 23.2 ms |
| 1 | spec-ptc +1 bad guess | plugin adaptive | 2.90 | 3.04 | 17.5 | 18.1 | 1 of 563 | 35 |  |
| 1 | spec-ptc +1 bad guess | plugin off | 2.90 | 3.04 | 17.5 | 18.3 | 0 of 563 | 35 |  |
| 4 | spec-ptc | stock | 3.43 | 3.87 | 21.0 | 22.5 | 0 of 567 | 0 | 3.55 s, 21.1 / 22.6 ms |
| 4 | spec-ptc | plugin fixed | 3.42 | 3.86 | 20.9 | 22.4 | 4 of 567 | 0 | 3.53 s, 21.0 / 22.5 ms |
| 4 | spec-ptc | plugin adaptive | 3.42 | 3.86 | 20.9 | 22.4 | 4 of 567 | 0 |  |
| 4 | spec-ptc | plugin off | 3.43 | 3.87 | 21.0 | 22.5 | 0 of 567 | 0 |  |
| 4 | spec-ptc +1 bad guess | stock | 5.22 | 5.94 | 31.4 | 36.2 | 0 of 567 | 0 | 5.04 s, 29.6 / 33.0 ms |
| 4 | spec-ptc +1 bad guess | plugin fixed | 3.54 | 3.94 | 21.5 | 22.7 | 4 of 567 | 173 | 3.68 s, 21.8 / 23.6 ms |
| 4 | spec-ptc +1 bad guess | plugin adaptive | 3.54 | 3.94 | 21.5 | 22.7 | 4 of 567 | 173 |  |
| 4 | spec-ptc +1 bad guess | plugin off | 3.54 | 3.95 | 21.5 | 22.7 | 0 of 567 | 173 |  |
| 8 | spec-ptc | stock | 4.48 | 5.02 | 27.3 | 30.0 | 0 of 567 | 0 | 4.36 s, 25.6 / 29.3 ms |
| 8 | spec-ptc | plugin fixed | 4.45 | 5.00 | 27.1 | 29.7 | 12 of 567 | 0 | 4.41 s, 25.8 / 29.0 ms |
| 8 | spec-ptc | plugin adaptive | 4.45 | 5.00 | 27.1 | 29.7 | 12 of 567 | 0 |  |
| 8 | spec-ptc | plugin off | 4.48 | 5.02 | 27.3 | 30.0 | 0 of 567 | 0 |  |
| 8 | spec-ptc +1 bad guess | stock | 8.21 | 9.32 | 48.6 | 59.0 | 0 of 566 | 0 | 6.62 s, 39.0 / 45.3 ms |
| 8 | spec-ptc +1 bad guess | plugin fixed | 4.45 | 5.00 | 27.1 | 29.7 | 12 of 567 | 360 | 4.41 s, 25.9 / 29.5 ms |
| 8 | spec-ptc +1 bad guess | plugin adaptive | 4.45 | 5.00 | 27.1 | 29.7 | 12 of 567 | 360 |  |
| 8 | spec-ptc +1 bad guess | plugin off | 4.48 | 5.02 | 27.3 | 30.0 | 0 of 567 | 360 |  |

## How to read it

- Simulated. One deterministic simulator run per cell, no noise model. The measured
  column is the single October 19 run (`sptc_out/load.json`, `load_tagged.json`); it is only
  shown for the stock and plugin-fixed arms, the arms that ran.
- Expected error. On the 18 measured load rows this simulator is off by a median of 3%
  (session p50) and 5% (root TPOT p50), at worst 21% and 22% (`sim_vs_t4_compare.md`).
  - The worst row is stock vLLM with 8 agents and bad guesses: predicted 8.21 s vs 6.62 s
    measured. The simulator likely makes decoys too costly at high load.
  - Next are the 1-agent plugin rows, which it does not reproduce: −12% to −18%
    (`root_cause.md`).
- The four plugin-side arms schedule differently only in the prefill allowance. On this
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
- Plugin vs stock.
  - Without bad guesses: the same within about 1%.
  - With one bad guess per call: the plugin is faster at every load, because it refuses
    most decoys (column "bets rejected"; 45, 180 and 360 decoys are launched at 1, 4 and 8
    agents).
- Run-to-run variation is unknown (one run per row so far). In the 1-agent row where
  the plugin provably schedules like stock vLLM (no speculation), the October 19 run
  differed by +4% (session p50) and +3.6% (root TPOT p50); the tagged 1-agent rows differed
  by +13.5% and +16%. Repeat each 1-agent arm at least 5 times before comparing arms.

## Running the A/B (same settings as October 19)

*Written before the second T4 run, which ran this A/B: `../kaggle_t4_v3/RESULTS.md`,
section 4.*

```bash
# stock
vllm serve Qwen/Qwen3-1.7B --dtype half --max-model-len 8192 --gpu-memory-utilization 0.9
# plugin: one server per mode, MODE in fixed | adaptive | off
vllm serve Qwen/Qwen3-1.7B --dtype half --max-model-len 8192 --gpu-memory-utilization 0.9 \
  --scheduler-cls sptc_vllm.scheduler.SptcScheduler \
  --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1,
                                 "spec_prefill_budget": 512, "prefill_allowance": "MODE"}}'
# stock sharing the plugin-fixed artifact: stock flags plus the plugin-fixed arm's exact
# --additional-config (stock does not use the "sptc" key, it only hashes it; --scheduler-cls is not hashed)
# eager runs: every arm again with --enforce-eager (no torch.compile, no CUDA graphs)
# client, once per server (tagged on the plugin servers), a separate --out per arm/repeat.
# --turns and --patterns as on October 19 and in the simulator (the default --patterns is
# the 8-pattern suite list, a different workload)
python kaggle/vllm_bench.py load --model Qwen/Qwen3-1.7B --spec-ptc SPEC_PTC_DIR \
  --agents 1,4,8 --decoys 0,1 --turns 4 \
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

