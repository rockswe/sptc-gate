# The sptc plugin's own per-step policy work (measured locally)

Low-power CPU cores, so slower than a server CPU. The plugin's hooks' code paths on plain objects, in a decode-saturated steady state; excludes vLLM's own scheduling. See README.md section 4.

Measured 2026-10-20T00:44:15Z, Python 3.13.0, `overhead_bench.py pure --out results/sweep_prep --steps 300`. Microseconds per step.

| running | waiting | tagged | policy work p50 us | p90 us |
|---|---|---|---|---|
| 8 | 4 | False | 3.3 | 3.5 |
| 8 | 4 | True | 7.5 | 7.8 |
| 32 | 16 | False | 13.1 | 13.8 |
| 32 | 16 | True | 25.2 | 26.5 |
| 64 | 32 | False | 26.0 | 27.0 |
| 64 | 32 | True | 48.8 | 51.4 |
| 128 | 64 | False | 51.3 | 53.2 |
| 128 | 64 | True | 97.2 | 103.4 |
| 256 | 128 | False | 104.7 | 108.8 |
| 256 | 128 | True | 200.8 | 1151.8 |
| 512 | 256 | False | 206.5 | 213.3 |
| 512 | 256 | True | 376.4 | 402.9 |
