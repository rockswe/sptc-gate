# Simulator vs the Kaggle T4 run (vLLM 0.32, Qwen3-1.7B fp16)

Plugin rows modeled with `--semantics plugin`.

Cost from the T4's solo calibration: t_fixed 1.90 ms, per-sequence 0.436 ms, GEMM efficiency 0.32, attention efficiency 0.013. Client overhead 30 ms each way, fit on the no-speculation suite medians only. Output tokens per call: measured in the no-speculation runs.

## spec-ptc suite (scripted root stream, real sub-calls)

| pattern | no-spec measured | no-spec sim | spec measured | spec sim (predicted) | error | speedup measured | speedup sim |
|---|---|---|---|---|---|---|---|
| map16 | 4.37 | 4.38 | 1.02 | 1.07 | +5.7% | 4.31x | 4.08x |
| map8_slow | 25.36 | 20.41 | 4.01 | 3.81 | -4.9% | 6.32x | 5.35x |
| map_reduce | 7.40 | 6.85 | 3.11 | 3.10 | -0.2% | 2.38x | 2.21x |
| multiblock | 13.55 | 10.71 | 2.80 | 2.72 | -2.9% | 4.83x | 3.93x |
| mutating_loop | 7.12 | 5.81 | 2.06 | 1.95 | -5.0% | 3.46x | 2.97x |
| side_branch_chain | 4.24 | 4.39 | 2.81 | 2.80 | -0.2% | 1.51x | 1.57x |
| syntax_gauntlet | 5.81 | 5.21 | 2.69 | 2.63 | -2.2% | 2.16x | 1.98x |
| two_stage | 12.35 | 10.31 | 2.82 | 2.78 | -1.4% | 4.38x | 3.71x |

Speculative wall time, predicted: median |error| 2.5%, mean 2.8%, max 5.7%.

## Load test (root served by vLLM, 4 turns per agent)

| server | agents | mode | session p50 measured | sim | root TPOT p50 measured | sim |
|---|---|---|---|---|---|---|
| stock vLLM | 1 | baseline | 6.16 | 6.62 | 15.7 | 15.8 |
| stock vLLM | 1 | spec | 2.73 | 2.76 | 16.8 | 16.8 |
| stock vLLM | 1 | spec +1 bad guess | 3.38 | 3.33 | 19.2 | 19.2 |
| stock vLLM | 4 | baseline | 7.20 | 7.14 | 18.0 | 17.1 |
| stock vLLM | 4 | spec | 3.55 | 3.43 | 21.1 | 21.0 |
| stock vLLM | 4 | spec +1 bad guess | 5.04 | 5.22 | 29.6 | 31.4 |
| stock vLLM | 8 | baseline | 8.01 | 7.84 | 19.9 | 18.9 |
| stock vLLM | 8 | spec | 4.36 | 4.48 | 25.6 | 27.3 |
| stock vLLM | 8 | spec +1 bad guess | 6.62 | 8.21 | 39.0 | 48.6 |
| plugin | 1 | baseline | 6.41 | 6.62 | 16.2 | 15.8 |
| plugin | 1 | spec | 3.10 | 2.76 | 19.5 | 16.8 |
| plugin | 1 | spec +1 bad guess | 3.38 | 2.90 | 20.9 | 17.5 |
| plugin | 4 | baseline | 7.37 | 7.14 | 18.3 | 17.1 |
| plugin | 4 | spec | 3.53 | 3.42 | 21.0 | 20.9 |
| plugin | 4 | spec +1 bad guess | 3.68 | 3.54 | 21.8 | 21.5 |
| plugin | 8 | baseline | 8.05 | 7.84 | 19.9 | 18.9 |
| plugin | 8 | spec | 4.41 | 4.45 | 25.8 | 27.1 |
| plugin | 8 | spec +1 bad guess | 4.41 | 4.45 | 25.9 | 27.1 |

Load rows: session p50 median |error| 3% (max 21%); root TPOT p50 median |error| 5% (max 22%).
