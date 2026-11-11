# Sweep summary

SLO per session: wall <= 2.0x and root TPOT <= 2.0x the `fcfs/nospec` arm at 1 agent, same pattern. Goodput = fraction of sessions meeting it; wall / TPOT = each half alone. Root TPOT is each session's mean; p50 and p99 are across sessions. Brackets: 95% bootstrap CI (repeats, then sessions); none for p99s. 'max': under 100 sessions, so the p99 is the slowest session. host CPU: whole host, mean over the run (max over repeats); cpu ok: every run below 0.85 with under 10% of seconds saturated.

| arm | agents | reps | session p50 s | session p99 s | root TPOT p50 ms | root TPOT p99 ms | sessions/min | goodput | wall / TPOT | decoys | preempt | max wait | client CPU | host CPU | cpu ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-adj/spec | 8 | 3 | 5.00 [4.05, 5.30] | 12.86 (max) | 28.6 [27.6, 29.4] | 32.9 (max) | 71.4 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.15 | 0.28 | yes |
| fcfs-adj/spec+bad | 8 | 3 | 7.46 [7.18, 7.70] | 18.45 (max) | 39.7 [38.1, 40.4] | 46.3 (max) | 50.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:390,completed:690 | 0 | 0 | 0.13 | 0.26 | yes |
| fcfs-b4/spec | 4 | 3 | 4.01 [3.49, 4.15] | 10.13 (max) | 23.0 [22.5, 23.6] | 25.1 (max) | 46.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.21 | yes |
| fcfs-b4/spec | 8 | 3 | 4.98 [4.47, 5.10] | 12.40 (max) | 28.0 [27.8, 28.4] | 32.1 (max) | 70.8 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.15 | 0.27 | yes |
| fcfs-b4/spec+bad | 4 | 3 | 5.14 [4.78, 5.69] | 13.44 (max) | 30.4 [29.4, 31.2] | 34.2 (max) | 35.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:264,completed:276 | 0 | 0 | 0.09 | 0.20 | yes |
| fcfs-b4/spec+bad | 8 | 3 | 6.99 [6.68, 7.29] | 17.84 (max) | 39.4 [38.5, 40.3] | 45.7 (max) | 52.5 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:474,completed:606 | 0 | 0 | 0.14 | 0.27 | yes |
| fcfs-eager/spec | 1 | 5 | 6.20 [5.16, 6.44] | 15.08 (max) | 35.0 [34.3, 35.3] | 36.0 (max) | 8.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.01 | 0.28 | yes |
| fcfs/nospec | 1 | 5 | 16.83 [10.03, 19.74] | 23.42 (max) | 25.5 [25.2, 25.9] | 33.7 (max) | 4.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.01 | 0.07 | yes |
| fcfs/nospec | 4 | 3 | 11.57 [7.60, 13.35] | 16.70 (max) | 19.2 [19.0, 19.3] | 19.7 (max) | 22.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.04 | 0.14 | yes |
| fcfs/nospec | 8 | 3 | 11.59 [8.48, 14.34] | 17.55 (max) | 21.1 [21.0, 21.2] | 21.6 (max) | 41.2 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.08 | 0.21 | yes |
| fcfs/nospec | 16 | 3 | 14.13 [9.85, 15.11] | 19.92 | 24.5 [24.4, 24.6] | 25.7 | 68.5 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.14 | 0.27 | yes |
| fcfs/nospec | 24 | 3 | 19.86 [12.20, 20.52] | 25.71 | 30.3 [29.9, 30.5] | 32.0 | 77.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.16 | 0.29 | NO |
| fcfs/spec | 1 | 5 | 3.71 [3.34, 3.92] | 8.10 (max) | 23.3 [20.5, 24.8] | 27.7 (max) | 13.3 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| fcfs/spec | 4 | 3 | 4.05 [3.65, 4.17] | 10.07 (max) | 23.1 [22.3, 23.3] | 25.4 (max) | 46.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.21 | yes |
| fcfs/spec | 8 | 3 | 5.05 [4.14, 5.19] | 12.56 (max) | 28.4 [28.1, 28.7] | 33.3 (max) | 71.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.15 | 0.27 | yes |
| fcfs/spec | 16 | 3 | 6.55 [6.41, 6.66] | 15.94 | 36.6 [35.9, 36.9] | 42.1 | 101.7 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.22 | 0.36 | NO |
| fcfs/spec | 24 | 3 | 8.01 [7.70, 8.24] | 19.99 | 45.1 [43.7, 45.9] | 56.3 | 120.0 | 0.94 [0.91, 0.96] | 1.00 / 0.94 | - | 0 | 0 | 0.28 | 0.43 | NO |
| fcfs/spec+bad | 1 | 5 | 4.30 [4.23, 4.36] | 8.85 (max) | 24.0 [23.5, 25.0] | 30.1 (max) | 11.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:80,completed:145 | 0 | 0 | 0.02 | 0.11 | yes |
| fcfs/spec+bad | 4 | 3 | 5.51 [5.01, 5.75] | 13.54 (max) | 30.4 [29.4, 31.4] | 34.4 (max) | 35.3 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:216,completed:324 | 0 | 0 | 0.09 | 0.21 | yes |
| fcfs/spec+bad | 8 | 3 | 7.49 [7.22, 7.66] | 17.91 (max) | 39.4 [38.9, 40.3] | 46.6 (max) | 51.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:384,completed:696 | 0 | 0 | 0.13 | 0.27 | yes |
| fcfs/spec+bad | 16 | 3 | 11.27 [11.00, 11.65] | 27.83 | 58.0 [55.9, 59.1] | 71.7 | 66.1 | 0.14 [0.08, 0.21] | 1.00 / 0.14 | cancelled:775,completed:1385 | 0 | 0 | 0.18 | 0.33 | yes |
| fcfs/spec+bad | 24 | 3 | 15.16 [13.48, 15.57] | 37.39 | 75.9 [73.9, 79.8] | 99.1 | 73.0 | 0.00 [0.00, 0.00] | 1.00 / 0.00 | cancelled:1285,completed:1955 | 0 | 139 | 0.21 | 0.39 | NO |
| plugin-adaptive-eager/spec | 1 | 5 | 6.26 [5.11, 6.36] | 14.88 (max) | 34.6 [34.3, 34.9] | 35.8 (max) | 8.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.01 | 0.28 | yes |
| plugin-adaptive/spec | 1 | 5 | 3.78 [3.19, 4.02] | 8.11 (max) | 23.1 [20.8, 26.0] | 29.2 (max) | 13.2 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| plugin-adaptive/spec | 4 | 3 | 4.04 [3.68, 4.14] | 9.99 (max) | 22.9 [22.4, 23.4] | 25.3 (max) | 45.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.20 | yes |
| plugin-adaptive/spec | 8 | 3 | 5.04 [4.13, 5.23] | 12.62 (max) | 28.7 [28.0, 29.0] | 32.9 (max) | 71.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 16 | 0.15 | 0.28 | NO |
| plugin-adaptive/spec+bad | 1 | 5 | 3.80 [3.57, 4.30] | 8.79 (max) | 22.6 [21.2, 26.3] | 35.5 (max) | 12.5 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:16,completed:61,rejected:148 | 0 | 0 | 0.02 | 0.11 | yes |
| plugin-adaptive/spec+bad | 4 | 3 | 4.11 [3.73, 4.28] | 10.25 (max) | 23.4 [22.8, 23.9] | 25.9 (max) | 45.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:3,completed:18,rejected:519 | 0 | 0 | 0.10 | 0.21 | yes |
| plugin-adaptive/spec+bad | 8 | 3 | 5.18 [5.10, 5.22] | 12.62 (max) | 28.5 [28.2, 28.9] | 33.0 (max) | 68.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:1080 | 0 | 0 | 0.15 | 0.29 | yes |
| plugin-b4/spec+bad | 4 | 3 | 4.01 [3.53, 4.23] | 10.33 (max) | 23.2 [22.8, 23.9] | 25.3 (max) | 45.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:1,completed:20,rejected:519 | 0 | 0 | 0.10 | 0.22 | yes |
| plugin-b4/spec+bad | 8 | 3 | 5.02 [4.60, 5.22] | 12.64 (max) | 28.5 [27.8, 28.8] | 32.2 (max) | 70.3 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:1080 | 0 | 0 | 0.15 | 0.30 | NO |
| plugin-eager/spec | 1 | 5 | 6.23 [5.14, 6.53] | 14.84 (max) | 35.0 [34.7, 35.5] | 35.9 (max) | 8.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.01 | 0.28 | yes |
| plugin-off-eager/spec | 1 | 5 | 6.24 [5.13, 6.30] | 14.69 (max) | 34.4 [34.2, 34.6] | 35.1 (max) | 8.2 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.01 | 0.28 | yes |
| plugin-off/spec | 1 | 5 | 3.77 [3.21, 4.16] | 8.30 (max) | 23.5 [20.6, 25.6] | 31.8 (max) | 13.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| plugin-off/spec | 4 | 3 | 4.05 [3.65, 4.15] | 10.02 (max) | 22.9 [22.4, 23.3] | 25.2 (max) | 46.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.21 | yes |
| plugin-off/spec | 8 | 3 | 5.06 [4.15, 5.20] | 12.57 (max) | 28.6 [28.1, 28.7] | 33.0 (max) | 71.2 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.15 | 0.28 | yes |
| plugin-off/spec+bad | 1 | 5 | 3.79 [3.71, 4.61] | 8.87 (max) | 23.0 [21.3, 26.1] | 31.3 (max) | 12.4 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:13,completed:62,rejected:150 | 0 | 0 | 0.02 | 0.11 | yes |
| plugin-off/spec+bad | 4 | 3 | 4.10 [3.73, 4.26] | 10.21 (max) | 23.4 [22.7, 23.8] | 25.7 (max) | 45.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:3,completed:18,rejected:519 | 0 | 0 | 0.10 | 0.21 | yes |
| plugin-off/spec+bad | 8 | 3 | 5.15 [5.07, 5.23] | 12.63 (max) | 28.4 [28.0, 28.6] | 33.7 (max) | 69.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:1080 | 0 | 0 | 0.15 | 0.29 | yes |
| plugin-untagged/spec | 1 | 5 | 3.70 [3.48, 3.83] | 9.09 (max) | 23.3 [20.4, 24.5] | 26.9 (max) | 12.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| plugin/spec | 1 | 5 | 3.75 [3.32, 4.24] | 8.48 (max) | 23.4 [20.7, 25.6] | 32.2 (max) | 13.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| plugin/spec | 4 | 3 | 4.05 [3.62, 4.17] | 10.06 (max) | 23.0 [22.4, 23.3] | 25.2 (max) | 46.0 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.20 | yes |
| plugin/spec | 8 | 3 | 5.06 [4.09, 5.16] | 12.54 (max) | 28.5 [28.0, 28.7] | 33.1 (max) | 71.4 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.16 | 0.28 | yes |
| plugin/spec | 16 | 3 | 6.56 [6.40, 6.68] | 16.10 | 36.6 [36.2, 37.0] | 42.4 | 101.7 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.22 | 0.37 | NO |
| plugin/spec | 24 | 3 | 7.99 [7.49, 8.22] | 20.05 | 45.0 [44.1, 45.5] | 53.4 | 120.5 | 0.94 [0.91, 0.97] | 1.00 / 0.94 | - | 0 | 1 | 0.27 | 0.41 | NO |
| plugin/spec+bad | 1 | 5 | 3.89 [3.82, 4.40] | 8.86 (max) | 23.5 [21.6, 27.2] | 34.7 (max) | 12.3 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:21,completed:67,rejected:137 | 0 | 0 | 0.02 | 0.11 | yes |
| plugin/spec+bad | 4 | 3 | 4.13 [3.73, 4.27] | 10.24 (max) | 23.4 [22.8, 24.1] | 25.7 (max) | 45.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:2,completed:20,rejected:518 | 0 | 0 | 0.10 | 0.21 | yes |
| plugin/spec+bad | 8 | 3 | 5.20 [5.01, 5.25] | 12.71 (max) | 28.6 [28.2, 28.9] | 33.3 (max) | 68.7 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:1080 | 0 | 0 | 0.15 | 0.29 | yes |
| plugin/spec+bad | 16 | 3 | 6.60 [6.46, 6.70] | 16.50 | 36.6 [36.2, 36.9] | 42.2 | 100.8 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:2160 | 0 | 0 | 0.23 | 0.39 | NO |
| plugin/spec+bad | 24 | 3 | 8.06 [7.82, 8.21] | 19.96 | 44.0 [43.3, 44.6] | 52.4 | 119.4 | 0.98 [0.93, 1.00] | 1.00 / 0.98 | rejected:3240 | 0 | 0 | 0.28 | 0.47 | NO |
| prio-bets/spec+bad | 4 | 3 | 5.12 [4.75, 5.68] | 13.31 (max) | 30.3 [29.4, 31.0] | 34.2 (max) | 35.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:263,completed:277 | 0 | 0 | 0.09 | 0.21 | yes |
| prio-bets/spec+bad | 8 | 3 | 7.03 [6.65, 7.35] | 17.70 (max) | 39.2 [37.0, 40.3] | 45.9 (max) | 52.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:480,completed:600 | 0 | 0 | 0.13 | 0.27 | yes |
| prio/spec | 1 | 3 | 3.69 [3.22, 7.94] | 8.18 (max) | 22.8 [20.2, 24.1] | 25.5 (max) | 13.4 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.02 | 0.10 | yes |
| prio/spec | 4 | 3 | 4.07 [3.67, 4.16] | 10.08 (max) | 22.9 [22.4, 23.3] | 25.5 (max) | 45.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.09 | 0.20 | yes |
| prio/spec | 8 | 3 | 5.03 [4.06, 5.30] | 12.82 (max) | 28.3 [27.7, 29.2] | 32.8 (max) | 71.3 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.15 | 0.28 | NO |
| prio/spec | 16 | 3 | 6.53 [6.38, 6.68] | 16.04 | 36.7 [35.9, 37.1] | 41.5 | 101.9 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | - | 0 | 0 | 0.22 | 0.36 | NO |
| prio/spec | 24 | 3 | 7.98 [7.65, 8.21] | 20.04 | 44.9 [44.0, 45.3] | 55.4 | 120.4 | 0.96 [0.92, 1.00] | 1.00 / 0.96 | - | 0 | 0 | 0.27 | 0.42 | NO |
| prio/spec+bad | 1 | 3 | 4.35 [4.29, 8.48] | 9.39 (max) | 24.8 [23.7, 31.5] | 33.5 (max) | 11.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:48,completed:87 | 0 | 0 | 0.02 | 0.11 | yes |
| prio/spec+bad | 4 | 3 | 5.51 [4.98, 5.69] | 13.44 (max) | 30.6 [29.3, 30.9] | 34.1 (max) | 35.4 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:216,completed:324 | 0 | 0 | 0.09 | 0.21 | yes |
| prio/spec+bad | 8 | 3 | 7.41 [7.17, 7.68] | 18.36 (max) | 39.5 [38.3, 40.4] | 46.4 (max) | 50.8 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:384,completed:696 | 0 | 0 | 0.13 | 0.27 | yes |
| prio/spec+bad | 16 | 3 | 11.32 [11.02, 11.60] | 27.60 | 57.2 [55.2, 58.5] | 72.0 | 66.4 | 0.11 [0.07, 0.16] | 1.00 / 0.11 | cancelled:780,completed:1380 | 0 | 8 | 0.18 | 0.33 | yes |
| prio/spec+bad | 24 | 3 | 14.94 [13.22, 15.70] | 37.55 | 75.9 [74.7, 80.4] | 99.7 | 73.2 | 0.00 [0.00, 0.00] | 1.00 / 0.00 | cancelled:1299,completed:1941 | 0 | 141 | 0.21 | 0.38 | NO |
| proxy-sem/spec+bad | 4 | 3 | 4.53 [4.03, 4.75] | 11.64 (max) | 25.9 [25.7, 26.2] | 28.7 (max) | 41.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:36,completed:137,rejected:367 | 0 | 0 | 0.09 | 0.20 | yes |
| proxy-sem/spec+bad | 8 | 3 | 5.66 [4.85, 5.73] | 13.75 (max) | 31.4 [31.1, 31.7] | 34.3 (max) | 64.6 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:32,completed:160,rejected:888 | 0 | 0 | 0.14 | 0.27 | yes |
| proxy/spec+bad | 4 | 3 | 4.15 [3.57, 4.29] | 10.36 (max) | 23.7 [23.1, 24.2] | 25.1 (max) | 45.1 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | cancelled:1,completed:27,rejected:512 | 0 | 0 | 0.09 | 0.20 | yes |
| proxy/spec+bad | 8 | 3 | 4.99 [4.58, 5.16] | 12.45 (max) | 28.3 [27.8, 28.6] | 32.3 (max) | 70.7 | 1.00 [1.00, 1.00] | 1.00 / 1.00 | rejected:1080 | 0 | 0 | 0.15 | 0.27 | yes |

## Derived

- knee (session p50 >= 2x own 1-agent): {'fcfs-adj/spec': None, 'fcfs-adj/spec+bad': None, 'fcfs-b4/spec': None, 'fcfs-b4/spec+bad': None, 'fcfs-eager/spec': None, 'fcfs/nospec': None, 'fcfs/spec': 24, 'fcfs/spec+bad': 16, 'plugin-adaptive-eager/spec': None, 'plugin-adaptive/spec': None, 'plugin-adaptive/spec+bad': None, 'plugin-b4/spec+bad': None, 'plugin-eager/spec': None, 'plugin-off-eager/spec': None, 'plugin-off/spec': None, 'plugin-off/spec+bad': None, 'plugin-untagged/spec': None, 'plugin/spec': 24, 'plugin/spec+bad': 24, 'prio-bets/spec+bad': None, 'prio/spec': 24, 'prio/spec+bad': 16, 'proxy-sem/spec+bad': None, 'proxy/spec+bad': None}
- knee against stock FCFS's 1-agent p50, same mode: {'fcfs-adj/spec': None, 'fcfs-adj/spec+bad': None, 'fcfs-b4/spec': None, 'fcfs-b4/spec+bad': None, 'fcfs-eager/spec': None, 'fcfs/nospec': None, 'fcfs/spec': 24, 'fcfs/spec+bad': 16, 'plugin-adaptive-eager/spec': None, 'plugin-adaptive/spec': None, 'plugin-adaptive/spec+bad': None, 'plugin-b4/spec+bad': None, 'plugin-eager/spec': None, 'plugin-off-eager/spec': None, 'plugin-off/spec': None, 'plugin-off/spec+bad': None, 'plugin-untagged/spec': None, 'plugin/spec': 24, 'plugin/spec+bad': None, 'prio-bets/spec+bad': None, 'prio/spec': 24, 'prio/spec+bad': 16, 'proxy-sem/spec+bad': None, 'proxy/spec+bad': None}
- goodput < 0.5 first at: {'fcfs-adj/spec': None, 'fcfs-adj/spec+bad': None, 'fcfs-b4/spec': None, 'fcfs-b4/spec+bad': None, 'fcfs-eager/spec': None, 'fcfs/nospec': None, 'fcfs/spec': None, 'fcfs/spec+bad': 16, 'plugin-adaptive-eager/spec': None, 'plugin-adaptive/spec': None, 'plugin-adaptive/spec+bad': None, 'plugin-b4/spec+bad': None, 'plugin-eager/spec': None, 'plugin-off-eager/spec': None, 'plugin-off/spec': None, 'plugin-off/spec+bad': None, 'plugin-untagged/spec': None, 'plugin/spec': None, 'plugin/spec+bad': None, 'prio-bets/spec+bad': None, 'prio/spec': None, 'prio/spec+bad': 16, 'proxy-sem/spec+bad': None, 'proxy/spec+bad': None}
- wall half alone < 0.5 first at: {'fcfs-adj/spec': None, 'fcfs-adj/spec+bad': None, 'fcfs-b4/spec': None, 'fcfs-b4/spec+bad': None, 'fcfs-eager/spec': None, 'fcfs/nospec': None, 'fcfs/spec': None, 'fcfs/spec+bad': None, 'plugin-adaptive-eager/spec': None, 'plugin-adaptive/spec': None, 'plugin-adaptive/spec+bad': None, 'plugin-b4/spec+bad': None, 'plugin-eager/spec': None, 'plugin-off-eager/spec': None, 'plugin-off/spec': None, 'plugin-off/spec+bad': None, 'plugin-untagged/spec': None, 'plugin/spec': None, 'plugin/spec+bad': None, 'prio-bets/spec+bad': None, 'prio/spec': None, 'prio/spec+bad': None, 'proxy-sem/spec+bad': None, 'proxy/spec+bad': None}
- root TPOT half alone < 0.5 first at: {'fcfs-adj/spec': None, 'fcfs-adj/spec+bad': None, 'fcfs-b4/spec': None, 'fcfs-b4/spec+bad': None, 'fcfs-eager/spec': None, 'fcfs/nospec': None, 'fcfs/spec': None, 'fcfs/spec+bad': 16, 'plugin-adaptive-eager/spec': None, 'plugin-adaptive/spec': None, 'plugin-adaptive/spec+bad': None, 'plugin-b4/spec+bad': None, 'plugin-eager/spec': None, 'plugin-off-eager/spec': None, 'plugin-off/spec': None, 'plugin-off/spec+bad': None, 'plugin-untagged/spec': None, 'plugin/spec': None, 'plugin/spec+bad': None, 'prio-bets/spec+bad': None, 'prio/spec': None, 'prio/spec+bad': 16, 'proxy-sem/spec+bad': None, 'proxy/spec+bad': None}
- most sessions per minute at: {'fcfs-adj/spec': 8, 'fcfs-adj/spec+bad': 8, 'fcfs-b4/spec': 8, 'fcfs-b4/spec+bad': 8, 'fcfs-eager/spec': 1, 'fcfs/nospec': 24, 'fcfs/spec': 24, 'fcfs/spec+bad': 24, 'plugin-adaptive-eager/spec': 1, 'plugin-adaptive/spec': 8, 'plugin-adaptive/spec+bad': 8, 'plugin-b4/spec+bad': 8, 'plugin-eager/spec': 1, 'plugin-off-eager/spec': 1, 'plugin-off/spec': 8, 'plugin-off/spec+bad': 8, 'plugin-untagged/spec': 1, 'plugin/spec': 24, 'plugin/spec+bad': 24, 'prio-bets/spec+bad': 8, 'prio/spec': 24, 'prio/spec+bad': 24, 'proxy-sem/spec+bad': 8, 'proxy/spec+bad': 8}
- spec+bad no faster than nospec first at: {'fcfs': None, 'prio': None, 'plugin': None}
- prio/spec+bad vs fcfs/spec+bad (ratio, < 1 better): {1: {'session_p50': 1.0113928615507535, 'root_tpot_p99': 1.1133767683987745}, 4: {'session_p50': 1.0000612534186852, 'root_tpot_p99': 0.9923983091781555}, 8: {'session_p50': 0.988968885535444, 'root_tpot_p99': 0.9962376815000821}, 16: {'session_p50': 1.004555942741581, 'root_tpot_p99': 1.0034512519268528}, 24: {'session_p50': 0.9858361530460656, 'root_tpot_p99': 1.006832798860763}}
- plugin/spec+bad vs fcfs/spec+bad: {1: {'session_p50': 0.903617526092391, 'root_tpot_p99': 1.1514150482620105}, 4: {'session_p50': 0.7494814011128689, 'root_tpot_p99': 0.7456800280396032}, 8: {'session_p50': 0.694748673247517, 'root_tpot_p99': 0.7153904132495954}, 16: {'session_p50': 0.5852262568640554, 'root_tpot_p99': 0.5886999564160358}, 24: {'session_p50': 0.5317282165096963, 'root_tpot_p99': 0.5290044215964693}}

## Baselines (B4) against `fcfs-b4/spec+bad` (session p50 / root TPOT p50 / p99; < 1 better)

Sub-call tokens: sub-call completion tokens per session, same ratio; away from 1, the arms did not run the same amount of work (sub-calls stop at EOS). vs no bets: session p50 against `fcfs-b4/spec`, stock FCFS without bad guesses. Every B4 bet is a worthless decoy, so refusing every bet is the best a gate can do here: an arm near 1.0 in that column has refused (nearly) all bets, and B4 cannot show a cost of refusing too many. Decoys refused: share of decoys logged rejected. Prefix hits: the server's prefix-cache hit share over the arm's runs ('-': no counter).

| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens | vs no bets | decoys refused | prefix hits |
|---|---|---|---|---|---|---|---|---|
| fcfs-b4/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.281 | 0.00 | 0.66 |
| fcfs-b4/spec+bad | 8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.403 | 0.00 | 0.71 |
| proxy/spec+bad | 4 | 0.807 | 0.779 | 0.734 | 1.000 | 1.034 | 0.95 | 0.63 |
| proxy/spec+bad | 8 | 0.714 | 0.717 | 0.707 | 1.013 | 1.002 | 1.00 | 0.69 |
| proxy-sem/spec+bad | 4 | 0.883 | 0.853 | 0.839 | 0.999 | 1.131 | 0.68 | 0.62 |
| proxy-sem/spec+bad | 8 | 0.810 | 0.796 | 0.751 | 1.005 | 1.136 | 0.82 | 0.68 |
| prio-bets/spec+bad | 4 | 0.996 | 0.999 | 1.000 | 1.001 | 1.275 | 0.00 | 0.66 |
| prio-bets/spec+bad | 8 | 1.006 | 0.994 | 1.004 | 1.005 | 1.411 | 0.00 | 0.71 |
| plugin-b4/spec+bad | 4 | 0.780 | 0.763 | 0.740 | 1.000 | 0.999 | 0.96 | 0.63 |
| plugin-b4/spec+bad | 8 | 0.718 | 0.723 | 0.706 | 0.993 | 1.008 | 1.00 | 0.69 |
| fcfs-b4/spec | 4 | 0.781 | 0.757 | 0.734 | 1.001 | 1.000 | - | 0.64 |
| fcfs-b4/spec | 8 | 0.713 | 0.711 | 0.702 | 1.014 | 1.000 | - | 0.69 |

## Against stock FCFS, same mode (session p50 / root TPOT p50 / p99; > 1 slower)

Last column: sub-call completion tokens per session, same ratio. Both arms send the same prompts, but sub-calls stop at EOS: a ratio away from 1 means the arms did not run the same amount of work.

| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens |
|---|---|---|---|---|---|
| fcfs-adj/spec | 8 | 0.990 | 1.005 | 0.987 | 1.001 |
| fcfs-adj/spec+bad | 8 | 0.995 | 1.009 | 0.992 | 1.000 |
| fcfs-b4/spec | 4 | 0.991 | 0.997 | 0.987 | 1.018 |
| fcfs-b4/spec | 8 | 0.986 | 0.985 | 0.963 | 1.018 |
| fcfs-b4/spec+bad | 4 | 0.933 | 0.998 | 0.993 | 1.002 |
| fcfs-b4/spec+bad | 8 | 0.933 | 1.001 | 0.980 | 0.934 |
| plugin-adaptive-eager/spec | 1 | 1.010 | 0.990 | 0.994 | 1.000 |
| plugin-adaptive/spec | 1 | 1.019 | 0.992 | 1.053 | 0.989 |
| plugin-adaptive/spec | 4 | 0.999 | 0.994 | 0.997 | 0.997 |
| plugin-adaptive/spec | 8 | 0.998 | 1.008 | 0.987 | 1.000 |
| plugin-adaptive/spec+bad | 1 | 0.884 | 0.942 | 1.178 | 0.999 |
| plugin-adaptive/spec+bad | 4 | 0.746 | 0.769 | 0.752 | 0.999 |
| plugin-adaptive/spec+bad | 8 | 0.691 | 0.725 | 0.708 | 0.993 |
| plugin-b4/spec+bad | 4 | 0.728 | 0.762 | 0.735 | 1.002 |
| plugin-b4/spec+bad | 8 | 0.670 | 0.724 | 0.692 | 0.928 |
| plugin-eager/spec | 1 | 1.004 | 0.999 | 0.996 | 1.000 |
| plugin-off-eager/spec | 1 | 1.006 | 0.983 | 0.975 | 1.000 |
| plugin-off/spec | 1 | 1.017 | 1.006 | 1.149 | 0.989 |
| plugin-off/spec | 4 | 1.000 | 0.992 | 0.991 | 0.999 |
| plugin-off/spec | 8 | 1.002 | 1.007 | 0.993 | 1.001 |
| plugin-off/spec+bad | 1 | 0.882 | 0.960 | 1.039 | 0.999 |
| plugin-off/spec+bad | 4 | 0.745 | 0.769 | 0.747 | 0.999 |
| plugin-off/spec+bad | 8 | 0.688 | 0.720 | 0.723 | 0.990 |
| plugin-untagged/spec | 1 | 0.997 | 0.998 | 0.969 | 0.977 |
| plugin/spec | 1 | 1.012 | 1.002 | 1.163 | 0.989 |
| plugin/spec | 4 | 1.000 | 0.997 | 0.991 | 0.998 |
| plugin/spec | 8 | 1.001 | 1.002 | 0.996 | 0.999 |
| plugin/spec | 16 | 1.002 | 1.001 | 1.007 | 0.997 |
| plugin/spec | 24 | 0.998 | 0.997 | 0.949 | 1.000 |
| plugin/spec+bad | 1 | 0.904 | 0.978 | 1.151 | 0.999 |
| plugin/spec+bad | 4 | 0.749 | 0.770 | 0.746 | 0.998 |
| plugin/spec+bad | 8 | 0.695 | 0.728 | 0.715 | 0.993 |
| plugin/spec+bad | 16 | 0.585 | 0.631 | 0.589 | 1.000 |
| plugin/spec+bad | 24 | 0.532 | 0.580 | 0.529 | 1.000 |
| prio-bets/spec+bad | 4 | 0.929 | 0.997 | 0.993 | 1.003 |
| prio-bets/spec+bad | 8 | 0.938 | 0.995 | 0.984 | 0.939 |
| prio/spec | 1 | 0.996 | 0.978 | 0.919 | 1.005 |
| prio/spec | 4 | 1.005 | 0.993 | 1.004 | 1.004 |
| prio/spec | 8 | 0.995 | 0.994 | 0.986 | 1.003 |
| prio/spec | 16 | 0.997 | 1.003 | 0.985 | 0.997 |
| prio/spec | 24 | 0.996 | 0.996 | 0.985 | 0.999 |
| prio/spec+bad | 1 | 1.011 | 1.033 | 1.113 | 0.998 |
| prio/spec+bad | 4 | 1.000 | 1.007 | 0.992 | 0.998 |
| prio/spec+bad | 8 | 0.989 | 1.003 | 0.996 | 0.998 |
| prio/spec+bad | 16 | 1.005 | 0.986 | 1.003 | 1.000 |
| prio/spec+bad | 24 | 0.986 | 1.001 | 1.007 | 0.997 |
| proxy-sem/spec+bad | 4 | 0.823 | 0.851 | 0.834 | 1.001 |
| proxy-sem/spec+bad | 8 | 0.755 | 0.797 | 0.737 | 0.939 |
| proxy/spec+bad | 4 | 0.753 | 0.777 | 0.729 | 1.002 |
| proxy/spec+bad | 8 | 0.666 | 0.718 | 0.693 | 0.947 |

## Goodput curve (both thresholds = multiplier)

| arm | agents | 1.0x | 1.25x | 1.5x | 1.75x | 2.0x | 2.5x | 3.0x | 4.0x | 5.0x |
|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-adj/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-adj/spec+bad | 8 | 0.00 | 0.00 | 0.42 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-b4/spec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-b4/spec | 8 | 0.00 | 0.97 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-b4/spec+bad | 4 | 0.00 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-b4/spec+bad | 8 | 0.00 | 0.00 | 0.36 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs-eager/spec | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/nospec | 1 | 0.45 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/nospec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/nospec | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/nospec | 16 | 0.79 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/nospec | 24 | 0.00 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec | 1 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec | 16 | 0.00 | 0.00 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec | 24 | 0.00 | 0.00 | 0.00 | 0.48 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec+bad | 1 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec+bad | 4 | 0.00 | 0.73 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec+bad | 8 | 0.00 | 0.00 | 0.35 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| fcfs/spec+bad | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.14 | 0.69 | 1.00 | 1.00 | 1.00 |
| fcfs/spec+bad | 24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.05 | 0.51 | 1.00 | 1.00 |
| plugin-adaptive-eager/spec | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec | 1 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec+bad | 1 | 0.70 | 0.95 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec+bad | 4 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-adaptive/spec+bad | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-b4/spec+bad | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-b4/spec+bad | 8 | 0.00 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-eager/spec | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off-eager/spec | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec | 1 | 0.75 | 0.95 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec+bad | 1 | 0.70 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec+bad | 4 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-off/spec+bad | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin-untagged/spec | 1 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec | 1 | 0.75 | 0.95 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec | 16 | 0.00 | 0.00 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec | 24 | 0.00 | 0.00 | 0.00 | 0.43 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec+bad | 1 | 0.70 | 0.95 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec+bad | 4 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec+bad | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec+bad | 16 | 0.00 | 0.00 | 0.84 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| plugin/spec+bad | 24 | 0.00 | 0.00 | 0.00 | 0.66 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio-bets/spec+bad | 4 | 0.00 | 0.77 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio-bets/spec+bad | 8 | 0.00 | 0.00 | 0.44 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec | 1 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec | 4 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec | 8 | 0.00 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec | 16 | 0.00 | 0.01 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec | 24 | 0.00 | 0.00 | 0.00 | 0.50 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec+bad | 1 | 0.58 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec+bad | 4 | 0.00 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec+bad | 8 | 0.00 | 0.00 | 0.38 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| prio/spec+bad | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.11 | 0.71 | 1.00 | 1.00 | 1.00 |
| prio/spec+bad | 24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.06 | 0.52 | 1.00 | 1.00 |
| proxy-sem/spec+bad | 4 | 0.29 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| proxy-sem/spec+bad | 8 | 0.00 | 0.73 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| proxy/spec+bad | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| proxy/spec+bad | 8 | 0.00 | 0.97 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

## Per server launch (GPU: lowest SM clock MHz and peak temperature C over the launch's runs; '-' without nvidia-smi)

| arm | agents | launch | first run (UTC) | sessions | session p50 s | root TPOT p50 ms | GPU SM min | GPU temp max |
|---|---|---|---|---|---|---|---|---|
| fcfs-adj/spec | 8 | fcfs#4 | 2026-10-20T17:13:38Z | 64 | 5.12 | 28.8 | 945 | 81 |
| fcfs-adj/spec | 8 | fcfs#5 | 2026-10-20T17:18:13Z | 32 | 4.84 | 27.8 | 1080 | 76 |
| fcfs-adj/spec+bad | 8 | fcfs#4 | 2026-10-20T17:14:07Z | 64 | 7.44 | 39.3 | 855 | 78 |
| fcfs-adj/spec+bad | 8 | fcfs#5 | 2026-10-20T17:17:34Z | 32 | 7.47 | 40.0 | 765 | 81 |
| fcfs-b4/spec | 4 | fcfs#6 | 2026-10-20T17:31:54Z | 32 | 4.01 | 23.0 | 420 | 77 |
| fcfs-b4/spec | 4 | fcfs#7 | 2026-10-20T17:50:56Z | 16 | 4.03 | 23.2 | 1005 | 78 |
| fcfs-b4/spec | 8 | fcfs#6 | 2026-10-20T17:28:09Z | 64 | 5.02 | 28.0 | 795 | 78 |
| fcfs-b4/spec | 8 | fcfs#7 | 2026-10-20T17:49:06Z | 32 | 4.84 | 28.0 | 945 | 78 |
| fcfs-b4/spec+bad | 4 | fcfs#6 | 2026-10-20T17:30:42Z | 32 | 5.14 | 30.4 | 930 | 78 |
| fcfs-b4/spec+bad | 4 | fcfs#7 | 2026-10-20T17:51:18Z | 16 | 5.14 | 30.4 | 915 | 78 |
| fcfs-b4/spec+bad | 8 | fcfs#6 | 2026-10-20T17:26:33Z | 64 | 7.05 | 39.4 | 930 | 81 |
| fcfs-b4/spec+bad | 8 | fcfs#7 | 2026-10-20T17:49:33Z | 32 | 6.74 | 39.4 | 1005 | 78 |
| fcfs-eager/spec | 1 | fcfs_eager#1 | 2026-10-20T16:46:17Z | 12 | 6.37 | 35.3 | 1335 | 81 |
| fcfs-eager/spec | 1 | fcfs_eager#2 | 2026-10-20T17:06:58Z | 8 | 6.20 | 34.3 | 1380 | 81 |
| fcfs/nospec | 1 | fcfs#2 | 2026-10-20T15:46:18Z | 12 | 16.83 | 25.5 | 330 | 81 |
| fcfs/nospec | 1 | fcfs#3 | 2026-10-20T16:40:04Z | 8 | 17.89 | 25.8 | 345 | 78 |
| fcfs/nospec | 4 | fcfs#8 | 2026-10-20T17:53:21Z | 48 | 11.57 | 19.2 | 345 | 81 |
| fcfs/nospec | 8 | fcfs#8 | 2026-10-20T17:55:30Z | 96 | 11.59 | 21.1 | 495 | 78 |
| fcfs/nospec | 16 | fcfs#8 | 2026-10-20T17:57:52Z | 192 | 14.13 | 24.5 | 585 | 80 |
| fcfs/nospec | 24 | fcfs#8 | 2026-10-20T18:05:44Z | 288 | 19.86 | 30.3 | 585 | 81 |
| fcfs/spec | 1 | fcfs#2 | 2026-10-20T15:47:20Z | 12 | 3.71 | 23.3 | 390 | 78 |
| fcfs/spec | 1 | fcfs#3 | 2026-10-20T16:39:25Z | 8 | 3.71 | 23.8 | 360 | 78 |
| fcfs/spec | 4 | fcfs#2 | 2026-10-20T15:51:11Z | 32 | 4.07 | 23.1 | 735 | 78 |
| fcfs/spec | 4 | fcfs#3 | 2026-10-20T16:42:39Z | 16 | 3.99 | 23.2 | 990 | 77 |
| fcfs/spec | 8 | fcfs#2 | 2026-10-20T15:52:50Z | 64 | 5.12 | 28.5 | 975 | 78 |
| fcfs/spec | 8 | fcfs#3 | 2026-10-20T16:43:27Z | 32 | 4.88 | 28.2 | 1050 | 78 |
| fcfs/spec | 16 | fcfs#8 | 2026-10-20T17:58:48Z | 192 | 6.55 | 36.6 | 585 | 80 |
| fcfs/spec | 24 | fcfs#8 | 2026-10-20T18:07:00Z | 288 | 8.01 | 45.1 | 585 | 82 |
| fcfs/spec+bad | 1 | fcfs#2 | 2026-10-20T15:47:38Z | 12 | 4.26 | 24.0 | 960 | 78 |
| fcfs/spec+bad | 1 | fcfs#3 | 2026-10-20T16:39:43Z | 8 | 4.34 | 24.7 | 960 | 78 |
| fcfs/spec+bad | 4 | fcfs#2 | 2026-10-20T15:51:33Z | 32 | 5.60 | 30.3 | 990 | 77 |
| fcfs/spec+bad | 4 | fcfs#3 | 2026-10-20T16:43:00Z | 16 | 5.11 | 30.7 | 810 | 77 |
| fcfs/spec+bad | 8 | fcfs#2 | 2026-10-20T15:53:18Z | 64 | 7.49 | 39.4 | 960 | 78 |
| fcfs/spec+bad | 8 | fcfs#3 | 2026-10-20T16:43:54Z | 32 | 7.51 | 39.3 | 1050 | 78 |
| fcfs/spec+bad | 16 | fcfs#8 | 2026-10-20T17:59:28Z | 192 | 11.27 | 58.0 | 585 | 79 |
| fcfs/spec+bad | 24 | fcfs#8 | 2026-10-20T18:07:52Z | 288 | 15.16 | 75.9 | 585 | 82 |
| plugin-adaptive-eager/spec | 1 | plugin_adaptive_eager#1 | 2026-10-20T16:52:38Z | 12 | 6.27 | 34.6 | 1440 | 81 |
| plugin-adaptive-eager/spec | 1 | plugin_adaptive_eager#2 | 2026-10-20T17:01:38Z | 8 | 6.26 | 34.8 | 1425 | 81 |
| plugin-adaptive/spec | 1 | plugin_adaptive#2 | 2026-10-20T16:07:16Z | 12 | 3.86 | 23.1 | 450 | 79 |
| plugin-adaptive/spec | 1 | plugin_adaptive#3 | 2026-10-20T16:28:47Z | 8 | 3.78 | 24.0 | 420 | 78 |
| plugin-adaptive/spec | 4 | plugin_adaptive#2 | 2026-10-20T16:09:09Z | 32 | 4.05 | 22.9 | 975 | 77 |
| plugin-adaptive/spec | 4 | plugin_adaptive#3 | 2026-10-20T16:30:04Z | 16 | 3.99 | 23.1 | 1005 | 77 |
| plugin-adaptive/spec | 8 | plugin_adaptive#2 | 2026-10-20T16:10:36Z | 64 | 5.14 | 28.8 | 960 | 78 |
| plugin-adaptive/spec | 8 | plugin_adaptive#3 | 2026-10-20T16:30:53Z | 32 | 4.88 | 28.2 | 945 | 78 |
| plugin-adaptive/spec+bad | 1 | plugin_adaptive#2 | 2026-10-20T16:07:35Z | 12 | 3.80 | 22.3 | 405 | 77 |
| plugin-adaptive/spec+bad | 1 | plugin_adaptive#3 | 2026-10-20T16:28:27Z | 8 | 4.07 | 23.8 | 435 | 80 |
| plugin-adaptive/spec+bad | 4 | plugin_adaptive#2 | 2026-10-20T16:09:30Z | 32 | 4.18 | 23.5 | 990 | 77 |
| plugin-adaptive/spec+bad | 4 | plugin_adaptive#3 | 2026-10-20T16:29:43Z | 16 | 4.04 | 23.4 | 990 | 78 |
| plugin-adaptive/spec+bad | 8 | plugin_adaptive#2 | 2026-10-20T16:11:05Z | 64 | 5.18 | 28.5 | 975 | 78 |
| plugin-adaptive/spec+bad | 8 | plugin_adaptive#3 | 2026-10-20T16:30:25Z | 32 | 5.18 | 28.6 | 945 | 77 |
| plugin-b4/spec+bad | 4 | plugin#3 | 2026-10-20T17:40:19Z | 32 | 4.01 | 23.2 | 975 | 78 |
| plugin-b4/spec+bad | 4 | plugin#4 | 2026-10-20T17:43:13Z | 16 | 4.01 | 23.2 | 1005 | 76 |
| plugin-b4/spec+bad | 8 | plugin#3 | 2026-10-20T17:39:23Z | 64 | 5.05 | 28.5 | 975 | 81 |
| plugin-b4/spec+bad | 8 | plugin#4 | 2026-10-20T17:42:45Z | 32 | 4.92 | 28.7 | 945 | 81 |
| plugin-eager/spec | 1 | plugin_eager#1 | 2026-10-20T16:49:28Z | 12 | 6.33 | 35.1 | 1395 | 81 |
| plugin-eager/spec | 1 | plugin_eager#2 | 2026-10-20T17:04:18Z | 8 | 6.23 | 34.7 | 1395 | 81 |
| plugin-off-eager/spec | 1 | plugin_off_eager#1 | 2026-10-20T16:55:48Z | 12 | 6.24 | 34.5 | 1335 | 81 |
| plugin-off-eager/spec | 1 | plugin_off_eager#2 | 2026-10-20T16:58:58Z | 8 | 6.27 | 34.2 | 1410 | 81 |
| plugin-off/spec | 1 | plugin_off#2 | 2026-10-20T16:16:43Z | 12 | 3.86 | 23.5 | 420 | 79 |
| plugin-off/spec | 1 | plugin_off#3 | 2026-10-20T16:24:06Z | 8 | 3.73 | 23.8 | 420 | 77 |
| plugin-off/spec | 4 | plugin_off#2 | 2026-10-20T16:18:38Z | 32 | 4.05 | 22.9 | 990 | 77 |
| plugin-off/spec | 4 | plugin_off#3 | 2026-10-20T16:25:23Z | 16 | 3.99 | 23.2 | 990 | 78 |
| plugin-off/spec | 8 | plugin_off#2 | 2026-10-20T16:20:04Z | 64 | 5.12 | 28.7 | 1005 | 78 |
| plugin-off/spec | 8 | plugin_off#3 | 2026-10-20T16:26:13Z | 32 | 4.92 | 28.3 | 1020 | 78 |
| plugin-off/spec+bad | 1 | plugin_off#2 | 2026-10-20T16:17:03Z | 12 | 3.79 | 22.4 | 960 | 77 |
| plugin-off/spec+bad | 1 | plugin_off#3 | 2026-10-20T16:23:46Z | 8 | 4.18 | 25.5 | 435 | 81 |
| plugin-off/spec+bad | 4 | plugin_off#2 | 2026-10-20T16:18:59Z | 32 | 4.20 | 23.4 | 975 | 77 |
| plugin-off/spec+bad | 4 | plugin_off#3 | 2026-10-20T16:25:02Z | 16 | 4.05 | 23.3 | 960 | 78 |
| plugin-off/spec+bad | 8 | plugin_off#2 | 2026-10-20T16:20:33Z | 64 | 5.17 | 28.5 | 960 | 78 |
| plugin-off/spec+bad | 8 | plugin_off#3 | 2026-10-20T16:25:44Z | 32 | 5.12 | 28.3 | 1020 | 77 |
| plugin-untagged/spec | 1 | plugin#1 | 2026-10-20T15:57:31Z | 12 | 3.67 | 23.3 | 405 | 77 |
| plugin-untagged/spec | 1 | plugin#2 | 2026-10-20T16:33:28Z | 8 | 3.80 | 24.2 | 405 | 78 |
| plugin/spec | 1 | plugin#1 | 2026-10-20T15:56:51Z | 12 | 3.82 | 24.0 | 375 | 80 |
| plugin/spec | 1 | plugin#2 | 2026-10-20T16:33:47Z | 8 | 3.66 | 23.0 | 420 | 78 |
| plugin/spec | 4 | plugin#1 | 2026-10-20T15:59:43Z | 32 | 4.08 | 23.0 | 810 | 78 |
| plugin/spec | 4 | plugin#2 | 2026-10-20T16:35:23Z | 16 | 4.01 | 23.1 | 975 | 77 |
| plugin/spec | 8 | plugin#1 | 2026-10-20T16:01:09Z | 64 | 5.11 | 28.6 | 1050 | 78 |
| plugin/spec | 8 | plugin#2 | 2026-10-20T16:36:12Z | 32 | 4.94 | 28.2 | 870 | 77 |
| plugin/spec | 16 | plugin#5 | 2026-10-20T18:34:55Z | 192 | 6.56 | 36.6 | 585 | 81 |
| plugin/spec | 24 | plugin#5 | 2026-10-20T18:38:53Z | 288 | 7.99 | 45.0 | 585 | 81 |
| plugin/spec+bad | 1 | plugin#1 | 2026-10-20T15:57:12Z | 12 | 3.87 | 23.4 | 375 | 78 |
| plugin/spec+bad | 1 | plugin#2 | 2026-10-20T16:33:07Z | 8 | 4.10 | 24.5 | 840 | 80 |
| plugin/spec+bad | 4 | plugin#1 | 2026-10-20T16:00:04Z | 32 | 4.15 | 23.4 | 975 | 77 |
| plugin/spec+bad | 4 | plugin#2 | 2026-10-20T16:35:01Z | 16 | 4.06 | 23.5 | 720 | 77 |
| plugin/spec+bad | 8 | plugin#1 | 2026-10-20T16:01:38Z | 64 | 5.19 | 28.6 | 975 | 78 |
| plugin/spec+bad | 8 | plugin#2 | 2026-10-20T16:35:44Z | 32 | 5.21 | 28.7 | 990 | 78 |
| plugin/spec+bad | 16 | plugin#5 | 2026-10-20T18:35:35Z | 192 | 6.60 | 36.6 | 585 | 79 |
| plugin/spec+bad | 24 | plugin#5 | 2026-10-20T18:39:44Z | 288 | 8.06 | 44.0 | 585 | 80 |
| prio-bets/spec+bad | 4 | priority#3 | 2026-10-20T17:36:46Z | 32 | 5.17 | 30.5 | 930 | 78 |
| prio-bets/spec+bad | 4 | priority#4 | 2026-10-20T17:45:56Z | 16 | 5.07 | 30.0 | 1020 | 76 |
| prio-bets/spec+bad | 8 | priority#3 | 2026-10-20T17:35:32Z | 64 | 7.06 | 38.7 | 945 | 81 |
| prio-bets/spec+bad | 8 | priority#4 | 2026-10-20T17:45:18Z | 32 | 6.85 | 39.8 | 975 | 81 |
| prio/spec | 1 | priority#5 | 2026-10-20T18:17:35Z | 12 | 3.69 | 22.8 | 360 | 80 |
| prio/spec | 4 | priority#5 | 2026-10-20T18:19:32Z | 48 | 4.07 | 22.9 | 750 | 78 |
| prio/spec | 8 | priority#1 | 2026-10-20T17:09:42Z | 64 | 5.15 | 29.0 | 675 | 81 |
| prio/spec | 8 | priority#2 | 2026-10-20T17:21:02Z | 32 | 4.84 | 27.9 | 990 | 76 |
| prio/spec | 16 | priority#5 | 2026-10-20T18:21:59Z | 192 | 6.53 | 36.7 | 585 | 80 |
| prio/spec | 24 | priority#5 | 2026-10-20T18:26:56Z | 288 | 7.98 | 44.9 | 585 | 81 |
| prio/spec+bad | 1 | priority#5 | 2026-10-20T18:17:53Z | 12 | 4.35 | 24.8 | 720 | 81 |
| prio/spec+bad | 4 | priority#5 | 2026-10-20T18:19:54Z | 48 | 5.51 | 30.6 | 750 | 77 |
| prio/spec+bad | 8 | priority#1 | 2026-10-20T17:10:11Z | 64 | 7.35 | 39.3 | 975 | 79 |
| prio/spec+bad | 8 | priority#2 | 2026-10-20T17:20:23Z | 32 | 7.46 | 39.7 | 750 | 81 |
| prio/spec+bad | 16 | priority#5 | 2026-10-20T18:22:39Z | 192 | 11.32 | 57.2 | 585 | 80 |
| prio/spec+bad | 24 | priority#5 | 2026-10-20T18:27:48Z | 288 | 14.94 | 75.9 | 585 | 82 |
| proxy-sem/spec+bad | 4 | fcfs#6 | 2026-10-20T17:31:30Z | 32 | 4.53 | 25.9 | 810 | 77 |
| proxy-sem/spec+bad | 4 | fcfs#7 | 2026-10-20T17:50:32Z | 16 | 4.57 | 26.1 | 1035 | 77 |
| proxy-sem/spec+bad | 8 | fcfs#6 | 2026-10-20T17:27:39Z | 64 | 5.66 | 31.4 | 990 | 79 |
| proxy-sem/spec+bad | 8 | fcfs#7 | 2026-10-20T17:48:36Z | 32 | 5.66 | 31.6 | 1065 | 77 |
| proxy/spec+bad | 4 | fcfs#6 | 2026-10-20T17:31:09Z | 32 | 4.15 | 23.7 | 885 | 78 |
| proxy/spec+bad | 4 | fcfs#7 | 2026-10-20T17:50:10Z | 16 | 4.18 | 24.2 | 1005 | 77 |
| proxy/spec+bad | 8 | fcfs#6 | 2026-10-20T17:27:11Z | 64 | 5.09 | 28.2 | 960 | 77 |
| proxy/spec+bad | 8 | fcfs#7 | 2026-10-20T17:48:08Z | 32 | 4.86 | 28.4 | 960 | 80 |
