Measured 2026-10-20T15:40:32Z, Python 3.13.15, `overhead_bench.py pure --out /kaggle/working/sptc_out_v3/overhead`. Microseconds per step.

| running | waiting | tagged | policy work p50 us | p90 us |
|---|---|---|---|---|
| 8 | 4 | False | 2.9 | 3.0 |
| 8 | 4 | True | 6.4 | 7.3 |
| 32 | 16 | False | 10.9 | 11.6 |
| 32 | 16 | True | 20.5 | 22.3 |
| 64 | 32 | False | 21.3 | 22.8 |
| 64 | 32 | True | 39.4 | 46.5 |
| 128 | 64 | False | 42.5 | 47.9 |
| 128 | 64 | True | 80.8 | 95.7 |
| 256 | 128 | False | 84.7 | 98.2 |
| 256 | 128 | True | 156.6 | 180.9 |
| 512 | 256 | False | 172.4 | 204.8 |
| 512 | 256 | True | 311.1 | 358.5 |
