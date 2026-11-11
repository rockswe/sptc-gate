Simulated. 100 sessions per run, 2 seeds per cell (paired: every arm sees the same arrivals, programs and output lengths), values averaged over seeds.

### eager

| workload | rate | metric | stock | fixed | adaptive | adaptive_u | off | adaptive vs fixed | off vs fixed |
|---|---|---|---|---|---|---|---|---|---|
| shadow | 0.05 | session p50 (s) | 19.31 | 19.41 | 19.44 | 19.44 | 19.31 | +0.2% | -0.5% |
| shadow | 0.05 | session p99 (s) | 30.32 | 30.34 | 30.33 | 30.33 | 30.32 | -0.0% | -0.0% |
| shadow | 0.05 | root TPOT p99 (ms) | 19.25 | 17.72 | 17.72 | 17.72 | 19.25 | +0.0% | +8.6% |
| shadow | 0.05 | root ITL p99 (ms) | 17.91 | 23.66 | 23.66 | 23.66 | 17.91 | -0.0% | -24.3% |
| shadow | 0.05 | sub-call TTFT p50 (ms) | 163.26 | 335.88 | 262.36 | 262.36 | 163.26 | -21.9% | -51.4% |
| shadow | 0.05 | steps the allowance cut | 0.0% | 4.6% | 3.3% | 3.3% | 0.0% | | |
| shadow | 0.2 | session p50 (s) | 21.05 | 20.70 | 20.73 | 20.73 | 21.05 | +0.1% | +1.7% |
| shadow | 0.2 | session p99 (s) | 31.31 | 31.05 | 31.05 | 31.05 | 31.31 | -0.0% | +0.8% |
| shadow | 0.2 | root TPOT p99 (ms) | 23.47 | 19.60 | 19.60 | 19.60 | 23.47 | +0.0% | +19.7% |
| shadow | 0.2 | root ITL p99 (ms) | 87.00 | 24.04 | 24.04 | 24.04 | 87.00 | +0.0% | +261.9% |
| shadow | 0.2 | sub-call TTFT p50 (ms) | 163.96 | 353.41 | 349.85 | 349.85 | 163.96 | -1.0% | -53.6% |
| shadow | 0.2 | steps the allowance cut | 0.0% | 11.7% | 11.2% | 11.2% | 0.0% | | |
| shadow | 0.6 | session p50 (s) | 28.34 | 24.93 | 24.93 | 24.93 | 28.34 | +0.0% | +13.7% |
| shadow | 0.6 | session p99 (s) | 39.19 | 34.03 | 34.03 | 34.03 | 39.19 | +0.0% | +15.2% |
| shadow | 0.6 | root TPOT p99 (ms) | 32.96 | 23.24 | 23.24 | 23.24 | 32.96 | +0.0% | +41.8% |
| shadow | 0.6 | root ITL p99 (ms) | 150.38 | 45.42 | 45.42 | 45.42 | 150.38 | +0.0% | +231.1% |
| shadow | 0.6 | sub-call TTFT p50 (ms) | 168.88 | 604.05 | 604.05 | 604.05 | 168.88 | +0.0% | -72.0% |
| shadow | 0.6 | steps the allowance cut | 0.0% | 36.1% | 36.1% | 36.1% | 0.0% | | |
| shadow+waste1 | 0.05 | session p50 (s) | 21.90 | 19.42 | 19.48 | 19.48 | 19.37 | +0.3% | -0.3% |
| shadow+waste1 | 0.05 | session p99 (s) | 30.58 | 30.36 | 30.35 | 30.35 | 30.34 | -0.0% | -0.0% |
| shadow+waste1 | 0.05 | root TPOT p99 (ms) | 21.54 | 17.78 | 17.80 | 17.80 | 19.25 | +0.1% | +8.2% |
| shadow+waste1 | 0.05 | root ITL p99 (ms) | 43.31 | 23.69 | 23.69 | 23.69 | 17.95 | -0.0% | -24.2% |
| shadow+waste1 | 0.05 | sub-call TTFT p50 (ms) | 78.43 | 335.97 | 262.20 | 262.20 | 163.20 | -22.0% | -51.4% |
| shadow+waste1 | 0.05 | steps the allowance cut | 0.0% | 4.7% | 3.4% | 3.4% | 0.0% | | |
| shadow+waste1 | 0.2 | session p50 (s) | 25.39 | 20.73 | 20.76 | 20.76 | 21.07 | +0.1% | +1.6% |
| shadow+waste1 | 0.2 | session p99 (s) | 36.61 | 31.09 | 31.09 | 31.09 | 31.34 | -0.0% | +0.8% |
| shadow+waste1 | 0.2 | root TPOT p99 (ms) | 30.06 | 19.65 | 19.64 | 19.64 | 23.45 | -0.0% | +19.3% |
| shadow+waste1 | 0.2 | root ITL p99 (ms) | 146.38 | 24.05 | 24.05 | 24.05 | 87.05 | +0.0% | +262.0% |
| shadow+waste1 | 0.2 | sub-call TTFT p50 (ms) | 85.24 | 357.81 | 349.39 | 349.39 | 163.89 | -2.4% | -54.2% |
| shadow+waste1 | 0.2 | steps the allowance cut | 0.0% | 11.8% | 11.4% | 11.4% | 0.0% | | |
| shadow+waste1 | 0.6 | session p50 (s) | 45.25 | 24.93 | 24.93 | 24.93 | 28.35 | +0.0% | +13.7% |
| shadow+waste1 | 0.6 | session p99 (s) | 62.58 | 34.02 | 34.02 | 34.02 | 39.19 | +0.0% | +15.2% |
| shadow+waste1 | 0.6 | root TPOT p99 (ms) | 56.28 | 23.27 | 23.27 | 23.27 | 32.96 | +0.0% | +41.6% |
| shadow+waste1 | 0.6 | root ITL p99 (ms) | 146.76 | 45.33 | 45.33 | 45.33 | 150.39 | +0.0% | +231.8% |
| shadow+waste1 | 0.6 | sub-call TTFT p50 (ms) | 113.94 | 604.07 | 604.07 | 604.07 | 168.97 | +0.0% | -72.0% |
| shadow+waste1 | 0.6 | steps the allowance cut | 0.0% | 36.2% | 36.2% | 36.2% | 0.0% | | |

### graphs

| workload | rate | metric | stock | fixed | adaptive | adaptive_u | off | adaptive vs fixed | off vs fixed |
|---|---|---|---|---|---|---|---|---|---|
| shadow | 0.05 | session p50 (s) | 5.63 | 5.51 | 5.57 | 5.57 | 5.63 | +1.1% | +2.2% |
| shadow | 0.05 | session p99 (s) | 20.01 | 20.01 | 20.01 | 20.01 | 20.01 | +0.0% | +0.0% |
| shadow | 0.05 | root TPOT p99 (ms) | 7.08 | 5.99 | 5.99 | 5.99 | 7.08 | +0.0% | +18.1% |
| shadow | 0.05 | root ITL p99 (ms) | 5.74 | 8.68 | 8.68 | 8.68 | 5.74 | -0.0% | -33.8% |
| shadow | 0.05 | sub-call TTFT p50 (ms) | 123.00 | 103.46 | 136.51 | 136.51 | 123.00 | +31.9% | +18.9% |
| shadow | 0.05 | steps the allowance cut | 0.0% | 3.4% | 2.2% | 2.2% | 0.0% | | |
| shadow | 0.2 | session p50 (s) | 6.10 | 5.88 | 5.94 | 5.94 | 6.10 | +1.2% | +3.9% |
| shadow | 0.2 | session p99 (s) | 20.02 | 20.02 | 20.02 | 20.02 | 20.02 | +0.0% | +0.0% |
| shadow | 0.2 | root TPOT p99 (ms) | 8.35 | 6.45 | 6.44 | 6.44 | 8.35 | -0.1% | +29.5% |
| shadow | 0.2 | root ITL p99 (ms) | 7.20 | 8.79 | 8.78 | 8.78 | 7.20 | -0.0% | -18.1% |
| shadow | 0.2 | sub-call TTFT p50 (ms) | 123.13 | 134.20 | 138.95 | 138.95 | 123.13 | +3.5% | -8.3% |
| shadow | 0.2 | steps the allowance cut | 0.0% | 4.8% | 3.5% | 3.5% | 0.0% | | |
| shadow | 0.6 | session p50 (s) | 8.19 | 7.14 | 7.14 | 7.14 | 8.19 | +0.0% | +14.8% |
| shadow | 0.6 | session p99 (s) | 21.29 | 20.90 | 20.90 | 20.90 | 21.29 | +0.0% | +1.9% |
| shadow | 0.6 | root TPOT p99 (ms) | 13.57 | 8.73 | 8.73 | 8.73 | 13.57 | +0.0% | +55.5% |
| shadow | 0.6 | root ITL p99 (ms) | 69.91 | 9.56 | 9.57 | 9.57 | 69.91 | +0.0% | +631.1% |
| shadow | 0.6 | sub-call TTFT p50 (ms) | 123.62 | 154.32 | 154.15 | 154.15 | 123.62 | -0.1% | -19.9% |
| shadow | 0.6 | steps the allowance cut | 0.0% | 10.9% | 10.5% | 10.5% | 0.0% | | |
| shadow+waste1 | 0.05 | session p50 (s) | 6.62 | 5.54 | 5.59 | 5.59 | 5.68 | +1.0% | +2.5% |
| shadow+waste1 | 0.05 | session p99 (s) | 20.03 | 20.03 | 20.03 | 20.03 | 20.03 | +0.0% | +0.0% |
| shadow+waste1 | 0.05 | root TPOT p99 (ms) | 8.36 | 5.99 | 5.99 | 5.99 | 7.19 | +0.0% | +20.0% |
| shadow+waste1 | 0.05 | root ITL p99 (ms) | 6.60 | 8.69 | 8.69 | 8.69 | 5.76 | -0.0% | -33.7% |
| shadow+waste1 | 0.05 | sub-call TTFT p50 (ms) | 52.83 | 103.53 | 123.07 | 123.07 | 122.92 | +18.9% | +18.7% |
| shadow+waste1 | 0.05 | steps the allowance cut | 0.0% | 3.5% | 2.3% | 2.3% | 0.0% | | |
| shadow+waste1 | 0.2 | session p50 (s) | 7.84 | 5.94 | 5.99 | 5.99 | 6.19 | +0.9% | +4.3% |
| shadow+waste1 | 0.2 | session p99 (s) | 20.19 | 20.04 | 20.04 | 20.04 | 20.04 | +0.0% | +0.0% |
| shadow+waste1 | 0.2 | root TPOT p99 (ms) | 10.95 | 6.47 | 6.47 | 6.47 | 8.37 | -0.0% | +29.4% |
| shadow+waste1 | 0.2 | root ITL p99 (ms) | 30.76 | 8.80 | 8.79 | 8.79 | 7.26 | -0.1% | -17.5% |
| shadow+waste1 | 0.2 | sub-call TTFT p50 (ms) | 53.17 | 134.77 | 136.50 | 136.50 | 123.08 | +1.3% | -8.7% |
| shadow+waste1 | 0.2 | steps the allowance cut | 0.0% | 4.9% | 3.7% | 3.7% | 0.0% | | |
| shadow+waste1 | 0.6 | session p50 (s) | 14.34 | 7.19 | 7.19 | 7.19 | 8.27 | +0.0% | +15.1% |
| shadow+waste1 | 0.6 | session p99 (s) | 27.43 | 20.91 | 20.92 | 20.92 | 21.32 | +0.0% | +2.0% |
| shadow+waste1 | 0.6 | root TPOT p99 (ms) | 25.02 | 8.73 | 8.73 | 8.73 | 13.62 | +0.0% | +56.0% |
| shadow+waste1 | 0.6 | root ITL p99 (ms) | 120.04 | 9.57 | 9.57 | 9.57 | 93.05 | +0.0% | +872.6% |
| shadow+waste1 | 0.6 | sub-call TTFT p50 (ms) | 59.81 | 156.34 | 156.78 | 156.78 | 123.49 | +0.3% | -21.0% |
| shadow+waste1 | 0.6 | steps the allowance cut | 0.0% | 11.1% | 10.7% | 10.7% | 0.0% | | |

### moe

| workload | rate | metric | stock | fixed | adaptive | adaptive_u | off | adaptive vs fixed | off vs fixed |
|---|---|---|---|---|---|---|---|---|---|
| shadow | 0.05 | session p50 (s) | 9.80 | 10.41 | 10.35 | 10.35 | 9.80 | -0.6% | -5.9% |
| shadow | 0.05 | session p99 (s) | 21.78 | 21.90 | 21.79 | 21.79 | 21.78 | -0.5% | -0.5% |
| shadow | 0.05 | root TPOT p99 (ms) | 15.86 | 17.34 | 17.24 | 17.24 | 15.86 | -0.6% | -8.5% |
| shadow | 0.05 | root ITL p99 (ms) | 20.25 | 26.36 | 26.36 | 26.36 | 20.25 | -0.0% | -23.2% |
| shadow | 0.05 | sub-call TTFT p50 (ms) | 99.87 | 322.74 | 219.70 | 219.70 | 99.87 | -31.9% | -69.1% |
| shadow | 0.05 | steps the allowance cut | 0.0% | 3.8% | 2.6% | 2.6% | 0.0% | | |
| shadow | 0.1 | session p50 (s) | 11.47 | 12.58 | 12.50 | 12.50 | 11.47 | -0.6% | -8.8% |
| shadow | 0.1 | session p99 (s) | 22.58 | 23.78 | 23.62 | 23.62 | 22.58 | -0.7% | -5.0% |
| shadow | 0.1 | root TPOT p99 (ms) | 19.38 | 20.42 | 20.96 | 20.96 | 19.38 | +2.6% | -5.1% |
| shadow | 0.1 | root ITL p99 (ms) | 24.71 | 26.64 | 26.63 | 26.63 | 24.71 | -0.0% | -7.3% |
| shadow | 0.1 | sub-call TTFT p50 (ms) | 102.66 | 410.13 | 258.42 | 258.42 | 102.66 | -37.0% | -75.0% |
| shadow | 0.1 | steps the allowance cut | 0.0% | 4.9% | 3.6% | 3.6% | 0.0% | | |
| shadow | 0.3 | session p50 (s) | 23.31 | 24.85 | 24.84 | 24.84 | 23.31 | -0.0% | -6.2% |
| shadow | 0.3 | session p99 (s) | 35.87 | 36.57 | 36.57 | 36.57 | 35.87 | +0.0% | -1.9% |
| shadow | 0.3 | root TPOT p99 (ms) | 30.19 | 28.77 | 28.77 | 28.77 | 30.19 | +0.0% | +4.9% |
| shadow | 0.3 | root ITL p99 (ms) | 88.80 | 29.52 | 29.52 | 29.52 | 88.80 | +0.0% | +200.9% |
| shadow | 0.3 | sub-call TTFT p50 (ms) | 113.68 | 491.15 | 489.45 | 489.45 | 113.68 | -0.3% | -76.9% |
| shadow | 0.3 | steps the allowance cut | 0.0% | 18.1% | 17.9% | 17.9% | 0.0% | | |
| shadow+waste1 | 0.05 | session p50 (s) | 13.49 | 10.65 | 10.62 | 10.62 | 10.09 | -0.3% | -5.3% |
| shadow+waste1 | 0.05 | session p99 (s) | 26.77 | 22.28 | 22.18 | 22.18 | 22.14 | -0.5% | -0.6% |
| shadow+waste1 | 0.05 | root TPOT p99 (ms) | 21.69 | 17.36 | 17.39 | 17.39 | 16.05 | +0.2% | -7.6% |
| shadow+waste1 | 0.05 | root ITL p99 (ms) | 25.60 | 26.37 | 26.36 | 26.36 | 20.50 | -0.0% | -22.3% |
| shadow+waste1 | 0.05 | sub-call TTFT p50 (ms) | 46.17 | 360.87 | 196.32 | 196.32 | 99.87 | -45.6% | -72.3% |
| shadow+waste1 | 0.05 | steps the allowance cut | 0.0% | 3.9% | 2.7% | 2.7% | 0.0% | | |
| shadow+waste1 | 0.1 | session p50 (s) | 17.57 | 13.03 | 13.00 | 13.00 | 11.88 | -0.2% | -8.8% |
| shadow+waste1 | 0.1 | session p99 (s) | 30.79 | 23.96 | 23.82 | 23.82 | 22.78 | -0.6% | -4.9% |
| shadow+waste1 | 0.1 | root TPOT p99 (ms) | 26.15 | 20.14 | 20.14 | 20.14 | 19.89 | +0.0% | -1.3% |
| shadow+waste1 | 0.1 | root ITL p99 (ms) | 28.42 | 26.65 | 26.65 | 26.65 | 24.75 | +0.0% | -7.1% |
| shadow+waste1 | 0.1 | sub-call TTFT p50 (ms) | 47.56 | 411.98 | 259.56 | 259.56 | 101.66 | -37.0% | -75.3% |
| shadow+waste1 | 0.1 | steps the allowance cut | 0.0% | 5.0% | 3.9% | 3.9% | 0.0% | | |
| shadow+waste1 | 0.3 | session p50 (s) | 35.77 | 24.92 | 24.90 | 24.90 | 23.36 | -0.1% | -6.2% |
| shadow+waste1 | 0.3 | session p99 (s) | 48.77 | 36.59 | 36.58 | 36.58 | 35.91 | -0.0% | -1.9% |
| shadow+waste1 | 0.3 | root TPOT p99 (ms) | 35.88 | 28.76 | 28.76 | 28.76 | 30.21 | +0.0% | +5.1% |
| shadow+waste1 | 0.3 | root ITL p99 (ms) | 97.95 | 29.53 | 29.52 | 29.52 | 89.08 | -0.0% | +201.7% |
| shadow+waste1 | 0.3 | sub-call TTFT p50 (ms) | 66.12 | 491.57 | 488.81 | 488.81 | 113.98 | -0.6% | -76.8% |
| shadow+waste1 | 0.3 | steps the allowance cut | 0.0% | 18.2% | 18.0% | 18.0% | 0.0% | | |

### rtx4090

| workload | rate | metric | stock | fixed | adaptive | adaptive_u | off | adaptive vs fixed | off vs fixed |
|---|---|---|---|---|---|---|---|---|---|
| shadow | 0.02 | session p50 (s) | 16.69 | 16.42 | 16.55 | 16.55 | 16.69 | +0.8% | +1.7% |
| shadow | 0.02 | session p99 (s) | 26.87 | 26.87 | 26.87 | 26.87 | 26.87 | +0.0% | +0.0% |
| shadow | 0.02 | root TPOT p99 (ms) | 25.87 | 22.74 | 22.74 | 22.74 | 25.87 | +0.0% | +13.8% |
| shadow | 0.02 | root ITL p99 (ms) | 177.64 | 47.24 | 47.23 | 47.23 | 177.64 | -0.0% | +276.1% |
| shadow | 0.02 | sub-call TTFT p50 (ms) | 542.12 | 561.89 | 563.01 | 563.01 | 542.12 | +0.2% | -3.5% |
| shadow | 0.02 | steps the allowance cut | 0.0% | 3.5% | 2.4% | 2.4% | 0.0% | | |
| shadow | 0.05 | session p50 (s) | 17.79 | 17.48 | 17.57 | 17.57 | 17.79 | +0.5% | +1.8% |
| shadow | 0.05 | session p99 (s) | 27.86 | 27.42 | 27.43 | 27.43 | 27.86 | +0.0% | +1.6% |
| shadow | 0.05 | root TPOT p99 (ms) | 29.43 | 25.29 | 25.24 | 25.24 | 29.43 | -0.2% | +16.3% |
| shadow | 0.05 | root ITL p99 (ms) | 178.39 | 47.57 | 47.57 | 47.57 | 178.39 | -0.0% | +275.0% |
| shadow | 0.05 | sub-call TTFT p50 (ms) | 545.57 | 695.38 | 711.41 | 711.41 | 545.57 | +2.3% | -21.5% |
| shadow | 0.05 | steps the allowance cut | 0.0% | 4.3% | 3.1% | 3.1% | 0.0% | | |
| shadow | 0.1 | session p50 (s) | 20.86 | 19.72 | 19.98 | 19.98 | 20.86 | +1.3% | +5.8% |
| shadow | 0.1 | session p99 (s) | 34.91 | 30.08 | 30.09 | 30.09 | 34.91 | +0.0% | +16.1% |
| shadow | 0.1 | root TPOT p99 (ms) | 39.82 | 30.37 | 30.37 | 30.37 | 39.82 | -0.0% | +31.1% |
| shadow | 0.1 | root ITL p99 (ms) | 178.66 | 48.26 | 48.25 | 48.25 | 178.66 | -0.0% | +270.2% |
| shadow | 0.1 | sub-call TTFT p50 (ms) | 655.44 | 816.48 | 810.78 | 810.78 | 655.44 | -0.7% | -19.7% |
| shadow | 0.1 | steps the allowance cut | 0.0% | 6.3% | 5.5% | 5.5% | 0.0% | | |
| shadow+waste1 | 0.02 | session p50 (s) | 20.73 | 16.49 | 16.70 | 16.70 | 16.83 | +1.3% | +2.1% |
| shadow+waste1 | 0.02 | session p99 (s) | 33.25 | 26.89 | 26.89 | 26.89 | 26.89 | +0.0% | +0.0% |
| shadow+waste1 | 0.02 | root TPOT p99 (ms) | 33.80 | 22.59 | 22.59 | 22.59 | 26.33 | +0.0% | +16.6% |
| shadow+waste1 | 0.02 | root ITL p99 (ms) | 178.43 | 47.30 | 47.27 | 47.27 | 178.25 | -0.1% | +276.8% |
| shadow+waste1 | 0.02 | sub-call TTFT p50 (ms) | 186.47 | 563.45 | 660.91 | 663.10 | 545.31 | +17.3% | -3.2% |
| shadow+waste1 | 0.02 | steps the allowance cut | 0.0% | 3.6% | 2.5% | 2.5% | 0.0% | | |
| shadow+waste1 | 0.05 | session p50 (s) | 23.06 | 17.60 | 17.71 | 17.71 | 17.93 | +0.6% | +1.9% |
| shadow+waste1 | 0.05 | session p99 (s) | 44.03 | 27.55 | 27.58 | 27.58 | 27.97 | +0.1% | +1.5% |
| shadow+waste1 | 0.05 | root TPOT p99 (ms) | 43.01 | 25.51 | 25.48 | 25.48 | 29.80 | -0.1% | +16.8% |
| shadow+waste1 | 0.05 | root ITL p99 (ms) | 178.70 | 47.63 | 47.63 | 47.63 | 178.42 | +0.0% | +274.6% |
| shadow+waste1 | 0.05 | sub-call TTFT p50 (ms) | 187.32 | 695.50 | 723.03 | 724.12 | 630.90 | +4.0% | -9.3% |
| shadow+waste1 | 0.05 | steps the allowance cut | 0.0% | 4.5% | 3.3% | 3.3% | 0.0% | | |
| shadow+waste1 | 0.1 | session p50 (s) | 32.55 | 20.01 | 20.20 | 20.20 | 20.94 | +1.0% | +4.7% |
| shadow+waste1 | 0.1 | session p99 (s) | 80.39 | 30.31 | 30.31 | 30.31 | 35.86 | -0.0% | +18.3% |
| shadow+waste1 | 0.1 | root TPOT p99 (ms) | 63.09 | 29.65 | 31.92 | 31.92 | 41.11 | +7.6% | +38.6% |
| shadow+waste1 | 0.1 | root ITL p99 (ms) | 179.54 | 48.34 | 48.34 | 48.34 | 178.68 | +0.0% | +269.7% |
| shadow+waste1 | 0.1 | sub-call TTFT p50 (ms) | 292.59 | 798.85 | 814.18 | 814.18 | 716.84 | +1.9% | -10.3% |
| shadow+waste1 | 0.1 | steps the allowance cut | 0.0% | 6.5% | 5.7% | 5.7% | 0.0% | | |

