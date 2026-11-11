Measured 2026-10-20T15:40:30Z, Python 3.13.15, vLLM 0.32.0, `overhead_bench.py vllm --out /kaggle/working/sptc_out_v3/overhead`. Microseconds per step.

| scheduling | running | waiting | variant | schedule() p50 us | p90 us | update_from_output() p50 us | total p50 us | vs stock |
|---|---|---|---|---|---|---|---|---|
| sync | 8 | 4 | stock | 109.1 | 132.6 | 49.7 | 162.0 | +0.0 us |
| sync | 8 | 4 | sptc-untagged | 116.5 | 138.7 | 51.9 | 171.0 | +9.0 us |
| sync | 8 | 4 | sptc-tagged | 123.7 | 147.2 | 52.9 | 179.2 | +17.2 us |
| sync | 32 | 16 | stock | 326.5 | 388.0 | 148.9 | 479.4 | +0.0 us |
| sync | 32 | 16 | sptc-untagged | 334.1 | 400.7 | 146.3 | 482.3 | +2.9 us |
| sync | 32 | 16 | sptc-tagged | 348.4 | 402.8 | 149.3 | 499.3 | +20.0 us |
| sync | 64 | 32 | stock | 599.8 | 713.1 | 271.7 | 876.7 | +0.0 us |
| sync | 64 | 32 | sptc-untagged | 647.5 | 1111.0 | 283.7 | 949.4 | +72.7 us |
| sync | 64 | 32 | sptc-tagged | 657.9 | 773.7 | 289.1 | 959.6 | +82.9 us |
| sync | 128 | 64 | stock | 1176.7 | 1387.3 | 545.8 | 1732.5 | +0.0 us |
| sync | 128 | 64 | sptc-untagged | 1225.8 | 1423.8 | 554.1 | 1796.2 | +63.7 us |
| sync | 128 | 64 | sptc-tagged | 1261.4 | 1473.8 | 555.0 | 1828.0 | +95.6 us |
| sync | 256 | 128 | stock | 2320.4 | 2612.7 | 1101.4 | 3478.8 | +0.0 us |
| sync | 256 | 128 | sptc-untagged | 2383.5 | 2675.4 | 1089.7 | 3512.0 | +33.2 us |
| sync | 256 | 128 | sptc-tagged | 2465.0 | 2865.7 | 1139.1 | 3645.6 | +166.7 us |
| sync | 512 | 256 | stock | 4755.4 | 5164.7 | 2270.5 | 7126.7 | +0.0 us |
| sync | 512 | 256 | sptc-untagged | 4827.5 | 5280.8 | 2252.1 | 7171.9 | +45.1 us |
| sync | 512 | 256 | sptc-tagged | 5067.6 | 5450.2 | 2318.1 | 7476.5 | +349.8 us |
| async | 8 | 4 | stock | 115.3 | 134.5 | 56.6 | 174.6 | +0.0 us |
| async | 8 | 4 | sptc-untagged | 118.0 | 137.2 | 55.3 | 175.3 | +0.7 us |
| async | 8 | 4 | sptc-tagged | 128.8 | 153.2 | 59.3 | 190.4 | +15.8 us |
| async | 32 | 16 | stock | 345.5 | 406.6 | 166.8 | 518.4 | +0.0 us |
| async | 32 | 16 | sptc-untagged | 347.8 | 405.3 | 161.7 | 512.7 | -5.7 us |
| async | 32 | 16 | sptc-tagged | 365.4 | 425.9 | 166.2 | 534.9 | +16.5 us |
| async | 64 | 32 | stock | 624.7 | 728.5 | 303.9 | 932.1 | +0.0 us |
| async | 64 | 32 | sptc-untagged | 651.9 | 765.8 | 309.2 | 972.8 | +40.6 us |
| async | 64 | 32 | sptc-tagged | 668.1 | 785.0 | 311.1 | 987.2 | +55.1 us |
| async | 128 | 64 | stock | 1216.4 | 1410.8 | 610.6 | 1845.6 | +0.0 us |
| async | 128 | 64 | sptc-untagged | 1257.5 | 1473.7 | 605.4 | 1873.3 | +27.6 us |
| async | 128 | 64 | sptc-tagged | 1320.5 | 1691.0 | 626.5 | 1979.3 | +133.7 us |
| async | 256 | 128 | stock | 2434.6 | 2732.4 | 1237.1 | 3745.3 | +0.0 us |
| async | 256 | 128 | sptc-untagged | 2522.8 | 2847.0 | 1248.2 | 3860.3 | +115.0 us |
| async | 256 | 128 | sptc-tagged | 2583.7 | 2880.3 | 1269.8 | 3895.7 | +150.4 us |
| async | 512 | 256 | stock | 4934.9 | 5395.5 | 2554.6 | 7605.0 | +0.0 us |
| async | 512 | 256 | sptc-untagged | 5131.3 | 5629.0 | 2564.2 | 7777.8 | +172.8 us |
| async | 512 | 256 | sptc-tagged | 5299.0 | 5821.2 | 2626.4 | 8008.7 | +403.7 us |
