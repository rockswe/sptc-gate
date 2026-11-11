## H100, Qwen3-4B, eager (calibrated) (`results/clog_eager.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 51.1 | 19.3 | 19.3 | 20.6 | 22.0 |
| 0.1 | 53.1 | 52.6 | 20.0 | 19.9 | 21.6 | 23.2 |
| 0.2 | 56.5 | 55.3 | 21.3 | 21.2 | 23.6 | 26.3 |
| 0.4 | 62.8 | 62.8 | 24.6 | 24.5 | 28.7 | 33.7 |
| 0.6 | 68.9 | 68.9 | 28.5 | 28.5 | 36.5 | 48.5 |
| 0.8 | 75.9 | 75.9 | 34.2 | 34.1 | 49.8 | 73.7 |

### p50 session latency (s), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 51.1 | 19.4 | 19.3 | 20.6 | 22.0 |
| 0.1 | 53.1 | 52.6 | 19.9 | 19.8 | 21.4 | 22.9 |
| 0.2 | 56.5 | 55.3 | 20.9 | 20.7 | 22.7 | 24.7 |
| 0.4 | 62.8 | 62.8 | 23.0 | 22.7 | 25.6 | 28.8 |
| 0.6 | 68.9 | 68.9 | 24.9 | 24.8 | 29.3 | 55.1 |
| 0.8 | 75.9 | 75.9 | 27.8 | 27.6 | 50.6 | 94.7 |

### p50 session latency (s), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 51.1 | 19.4 | 19.3 | 20.6 | 22.0 |
| 0.1 | 53.1 | 52.6 | 19.9 | 19.8 | 21.4 | 22.9 |
| 0.2 | 56.5 | 55.3 | 20.9 | 20.7 | 22.7 | 24.7 |
| 0.4 | 62.8 | 62.8 | 23.0 | 22.7 | 25.6 | 28.8 |
| 0.6 | 68.9 | 68.9 | 24.9 | 24.8 | 29.3 | 55.0 |
| 0.8 | 75.9 | 75.9 | 27.8 | 27.6 | 50.2 | 94.3 |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 51.1 | 19.4 | 19.3 | 19.4 | 19.4 |
| 0.1 | 53.1 | 52.6 | 19.9 | 19.8 | 19.9 | 19.9 |
| 0.2 | 56.5 | 55.3 | 20.9 | 20.7 | 20.9 | 20.9 |
| 0.4 | 62.8 | 62.8 | 22.9 | 22.7 | 22.9 | 22.9 |
| 0.6 | 68.9 | 68.9 | 25.0 | 24.8 | 25.0 | 25.0 |
| 0.8 | 75.9 | 75.9 | 27.5 | 27.4 | 27.5 | 27.5 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 68.3 | 35.8 | 35.8 | 36.1 | 36.9 |
| 0.1 | 70.9 | 70.9 | 36.3 | 36.2 | 36.6 | 37.2 |
| 0.2 | 76.3 | 76.2 | 37.0 | 37.3 | 38.7 | 40.8 |
| 0.4 | 88.6 | 88.6 | 41.7 | 41.7 | 43.9 | 49.8 |
| 0.6 | 103.5 | 103.5 | 44.8 | 44.8 | 51.6 | 68.7 |
| 0.8 | 120.2 | 120.3 | 51.9 | 52.3 | 70.5 | 99.7 |

### p99 session latency (s), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 68.3 | 35.6 | 35.6 | 35.8 | 36.3 |
| 0.1 | 70.9 | 70.9 | 35.8 | 35.8 | 36.0 | 36.0 |
| 0.2 | 76.3 | 76.2 | 36.5 | 36.5 | 37.1 | 38.5 |
| 0.4 | 88.6 | 88.6 | 39.1 | 39.1 | 40.5 | 44.4 |
| 0.6 | 103.5 | 103.5 | 40.5 | 40.3 | 45.6 | 75.9 |
| 0.8 | 120.2 | 120.3 | 42.5 | 42.0 | 67.6 | 135.3 |

### p99 session latency (s), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 68.3 | 35.6 | 35.6 | 35.8 | 36.3 |
| 0.1 | 70.9 | 70.9 | 35.8 | 35.8 | 36.0 | 36.0 |
| 0.2 | 76.3 | 76.2 | 36.5 | 36.5 | 37.1 | 38.5 |
| 0.4 | 88.6 | 88.6 | 39.1 | 39.1 | 40.5 | 44.4 |
| 0.6 | 103.5 | 103.5 | 40.5 | 40.4 | 45.5 | 75.9 |
| 0.8 | 120.2 | 120.3 | 42.4 | 42.0 | 67.2 | 135.2 |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 68.3 | 35.6 | 35.6 | 35.6 | 35.6 |
| 0.1 | 70.9 | 70.9 | 35.8 | 35.8 | 35.8 | 35.8 |
| 0.2 | 76.3 | 76.2 | 36.5 | 36.5 | 36.5 | 36.5 |
| 0.4 | 88.6 | 88.6 | 39.1 | 39.1 | 39.1 | 39.1 |
| 0.6 | 103.5 | 103.5 | 40.6 | 40.4 | 40.6 | 40.6 |
| 0.8 | 120.2 | 120.3 | 42.1 | 42.0 | 42.1 | 42.1 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 16.5 | 20.0 | 20.0 | 21.3 | 22.7 |
| 0.1 | 17.5 | 17.5 | 21.7 | 21.7 | 23.3 | 24.4 |
| 0.2 | 19.1 | 19.1 | 23.8 | 24.3 | 27.8 | 30.8 |
| 0.4 | 22.6 | 22.5 | 29.9 | 29.1 | 35.8 | 41.8 |
| 0.6 | 26.3 | 26.3 | 35.4 | 35.3 | 45.9 | 59.6 |
| 0.8 | 30.6 | 30.7 | 44.1 | 44.0 | 62.8 | 74.6 |

### root TPOT p99 (ms), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 16.5 | 18.2 | 18.2 | 18.8 | 19.6 |
| 0.1 | 17.5 | 17.5 | 18.8 | 19.0 | 19.8 | 20.2 |
| 0.2 | 19.1 | 19.1 | 20.3 | 20.1 | 21.1 | 21.8 |
| 0.4 | 22.6 | 22.5 | 21.9 | 22.0 | 23.2 | 24.3 |
| 0.6 | 26.3 | 26.3 | 23.8 | 23.8 | 24.9 | 25.4 |
| 0.8 | 30.6 | 30.7 | 25.0 | 25.2 | 26.4 | 26.0 |

### root TPOT p99 (ms), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 16.5 | 18.2 | 18.2 | 18.8 | 19.6 |
| 0.1 | 17.5 | 17.5 | 18.8 | 19.0 | 19.8 | 20.2 |
| 0.2 | 19.1 | 19.1 | 20.3 | 20.1 | 21.1 | 21.8 |
| 0.4 | 22.6 | 22.5 | 21.9 | 22.0 | 23.2 | 24.3 |
| 0.6 | 26.3 | 26.3 | 23.9 | 23.8 | 24.9 | 25.4 |
| 0.8 | 30.6 | 30.7 | 25.3 | 25.3 | 26.4 | 26.1 |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 16.5 | 18.2 | 18.2 | 18.2 | 18.2 |
| 0.1 | 17.5 | 17.5 | 18.8 | 19.0 | 18.8 | 18.8 |
| 0.2 | 19.1 | 19.1 | 20.3 | 20.1 | 20.3 | 20.3 |
| 0.4 | 22.6 | 22.5 | 22.0 | 22.0 | 22.0 | 22.1 |
| 0.6 | 26.3 | 26.3 | 24.1 | 23.9 | 24.1 | 24.1 |
| 0.8 | 30.6 | 30.7 | 25.6 | 25.5 | 25.6 | 25.6 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 | 0.06 | 0.07 | 0.10 |
| 0.1 | 0.08 | 0.08 | 0.16 | 0.10 | 0.21 | 0.32 |
| 0.2 | 0.09 | 0.08 | 0.32 | 0.28 | 0.39 | 0.40 |
| 0.4 | 0.10 | 0.10 | 0.44 | 0.43 | 0.55 | 0.57 |
| 0.6 | 0.12 | 0.10 | 0.47 | 0.45 | 0.56 | 0.60 |
| 0.8 | 0.13 | 0.14 | 0.57 | 0.53 | 0.77 | 3.63 |

### root TTFT p99 (s), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 | 0.07 |
| 0.1 | 0.08 | 0.08 | 0.07 | 0.06 | 0.07 | 0.07 |
| 0.2 | 0.09 | 0.08 | 0.07 | 0.07 | 0.07 | 0.07 |
| 0.4 | 0.10 | 0.10 | 0.08 | 0.08 | 0.08 | 0.08 |
| 0.6 | 0.12 | 0.10 | 0.08 | 0.08 | 0.09 | 0.09 |
| 0.8 | 0.13 | 0.14 | 0.09 | 0.09 | 0.10 | 0.10 |

### root TTFT p99 (s), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 | 0.07 |
| 0.1 | 0.08 | 0.08 | 0.07 | 0.06 | 0.07 | 0.07 |
| 0.2 | 0.09 | 0.08 | 0.07 | 0.07 | 0.07 | 0.07 |
| 0.4 | 0.10 | 0.10 | 0.08 | 0.08 | 0.08 | 0.08 |
| 0.6 | 0.12 | 0.10 | 0.08 | 0.08 | 0.09 | 0.09 |
| 0.8 | 0.13 | 0.14 | 0.09 | 0.09 | 0.10 | 0.10 |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 |
| 0.1 | 0.08 | 0.08 | 0.07 | 0.06 | 0.07 | 0.07 |
| 0.2 | 0.09 | 0.08 | 0.07 | 0.07 | 0.07 | 0.07 |
| 0.4 | 0.10 | 0.10 | 0.08 | 0.08 | 0.08 | 0.08 |
| 0.6 | 0.12 | 0.10 | 0.08 | 0.08 | 0.08 | 0.08 |
| 0.8 | 0.13 | 0.14 | 0.09 | 0.09 | 0.09 | 0.09 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 0.08 | 0.44 | 0.44 | 0.55 | 0.53 |
| 0.1 | 0.09 | 0.09 | 0.46 | 0.46 | 0.56 | 0.55 |
| 0.2 | 0.09 | 0.09 | 0.46 | 0.46 | 0.60 | 0.59 |
| 0.4 | 0.10 | 0.10 | 0.73 | 0.60 | 0.76 | 0.73 |
| 0.6 | 0.12 | 0.12 | 0.75 | 0.73 | 0.90 | 0.90 |
| 0.8 | 0.13 | 0.13 | 0.87 | 0.76 | 1.05 | 3.32 |

### sub-call TTFT p99, claimed calls (s), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 0.08 | 1.34 | 1.25 | 1.68 | 1.58 |
| 0.1 | 0.09 | 0.09 | 1.49 | 1.61 | 1.93 | 1.88 |
| 0.2 | 0.09 | 0.09 | 1.83 | 1.88 | 2.40 | 2.53 |
| 0.4 | 0.10 | 0.10 | 2.53 | 2.60 | 3.48 | 7.20 |
| 0.6 | 0.12 | 0.12 | 3.31 | 3.37 | 9.16 | 38.32 |
| 0.8 | 0.13 | 0.13 | 6.32 | 6.01 | 30.94 | 100.88 |

### sub-call TTFT p99, claimed calls (s), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 0.08 | 1.34 | 1.25 | 1.68 | 1.58 |
| 0.1 | 0.09 | 0.09 | 1.49 | 1.61 | 1.93 | 1.88 |
| 0.2 | 0.09 | 0.09 | 1.83 | 1.88 | 2.40 | 2.53 |
| 0.4 | 0.10 | 0.10 | 2.54 | 2.60 | 3.48 | 7.20 |
| 0.6 | 0.12 | 0.12 | 3.23 | 3.37 | 9.16 | 38.29 |
| 0.8 | 0.13 | 0.13 | 5.80 | 6.02 | 30.57 | 100.46 |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 0.08 | 1.33 | 1.25 | 1.33 | 1.33 |
| 0.1 | 0.09 | 0.09 | 1.47 | 1.58 | 1.47 | 1.47 |
| 0.2 | 0.09 | 0.09 | 1.80 | 1.88 | 1.80 | 1.80 |
| 0.4 | 0.10 | 0.10 | 2.61 | 2.60 | 2.61 | 2.61 |
| 0.6 | 0.12 | 0.12 | 3.52 | 3.57 | 3.52 | 3.52 |
| 0.8 | 0.13 | 0.13 | 5.47 | 6.15 | 5.49 | 5.49 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.461 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.294 | 0.439 |

### wasted share of model tokens, agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.458 |

### wasted share of model tokens, agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.464 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.299 | 0.459 |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 | 0 | 0 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.89 | 0.60 | 0.59 | 0.61 | 0.64 |
| 0.1 | 0.99 | 0.99 | 0.85 | 0.85 | 0.87 | 0.88 |
| 0.2 | 1.00 | 1.00 | 0.98 | 0.98 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.89 | 0.60 | 0.60 | 0.62 | 0.64 |
| 0.1 | 0.99 | 0.99 | 0.85 | 0.85 | 0.87 | 0.88 |
| 0.2 | 1.00 | 1.00 | 0.98 | 0.98 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.89 | 0.60 | 0.60 | 0.62 | 0.64 |
| 0.1 | 0.99 | 0.99 | 0.85 | 0.85 | 0.87 | 0.88 |
| 0.2 | 1.00 | 1.00 | 0.98 | 0.98 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.89 | 0.60 | 0.60 | 0.60 | 0.60 |
| 0.1 | 0.99 | 0.99 | 0.85 | 0.85 | 0.85 | 0.85 |
| 0.2 | 1.00 | 1.00 | 0.98 | 0.98 | 0.98 | 0.98 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 0.97 | 1.00 | 1.00 | 0.99 | 0.99 |
| 0.2 | 0.97 | 0.96 | 0.99 | 0.99 | 0.98 | 0.97 |
| 0.4 | 0.96 | 0.95 | 0.98 | 0.98 | 0.96 | 0.96 |
| 0.6 | 0.97 | 0.97 | 0.98 | 0.98 | 0.98 | 1.05 |
| 0.8 | 1.01 | 1.01 | 1.00 | 0.99 | 1.13 | 1.42 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 0.97 | 1.00 | 0.99 | 0.99 | 0.99 |
| 0.2 | 0.97 | 0.96 | 0.99 | 0.99 | 0.99 | 0.98 |
| 0.4 | 0.96 | 0.95 | 0.99 | 0.98 | 0.98 | 0.97 |
| 0.6 | 0.97 | 0.97 | 0.97 | 0.98 | 0.96 | 1.64 |
| 0.8 | 1.01 | 1.01 | 0.98 | 0.97 | 1.59 | 2.97 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive-open

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 0.97 | 1.00 | 0.99 | 0.99 | 0.99 |
| 0.2 | 0.97 | 0.96 | 0.99 | 0.99 | 0.99 | 0.98 |
| 0.4 | 0.96 | 0.95 | 0.99 | 0.98 | 0.98 | 0.97 |
| 0.6 | 0.97 | 0.97 | 0.97 | 0.98 | 0.96 | 1.64 |
| 0.8 | 1.01 | 1.01 | 0.97 | 0.97 | 1.59 | 2.97 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | literal | shadow | dataflow | shadow+waste0.5 | shadow+waste1 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 0.97 | 1.00 | 0.99 | 1.00 | 1.00 |
| 0.2 | 0.97 | 0.96 | 0.99 | 0.99 | 0.99 | 0.99 |
| 0.4 | 0.96 | 0.95 | 0.98 | 0.99 | 0.98 | 0.98 |
| 0.6 | 0.97 | 0.97 | 0.97 | 0.98 | 0.97 | 0.97 |
| 0.8 | 1.01 | 1.01 | 0.97 | 0.97 | 0.97 | 0.97 |

### paired lat_p50: literal, fcfs

| rate | literal (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.99 [0.99-0.99] | 0.98 |
| 0.1 | 0.99 [0.99-1.00] | 0.97 |
| 0.2 | 1.00 [0.98-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p99: literal, fcfs

| rate | literal (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 1.00 [1.00-1.00] | 0.98 |
| 0.1 | 1.00 [1.00-1.00] | 0.97 |
| 0.2 | 1.00 [1.00-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p50: literal, agent-naive

| rate | literal (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.99 [0.99-0.99] | 0.98 |
| 0.1 | 0.99 [0.99-1.00] | 0.97 |
| 0.2 | 1.00 [0.98-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p99: literal, agent-naive

| rate | literal (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 1.00 [1.00-1.00] | 0.98 |
| 0.1 | 1.00 [1.00-1.00] | 0.97 |
| 0.2 | 1.00 [1.00-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p50: literal, agent-naive-open

| rate | literal (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.99 [0.99-0.99] | 0.98 |
| 0.1 | 0.99 [0.99-1.00] | 0.97 |
| 0.2 | 1.00 [0.98-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p99: literal, agent-naive-open

| rate | literal (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 1.00 [1.00-1.00] | 0.98 |
| 0.1 | 1.00 [1.00-1.00] | 0.97 |
| 0.2 | 1.00 [1.00-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p50: literal, agent

| rate | literal (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.99 [0.99-0.99] | 0.98 |
| 0.1 | 0.99 [0.99-1.00] | 0.97 |
| 0.2 | 1.00 [0.98-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p99: literal, agent

| rate | literal (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 1.00 [1.00-1.00] | 0.98 |
| 0.1 | 1.00 [1.00-1.00] | 0.97 |
| 0.2 | 1.00 [1.00-1.00] | 0.96 |
| 0.4 | 1.00 [1.00-1.00] | 0.95 |
| 0.6 | 1.00 [1.00-1.00] | 0.97 |
| 0.8 | 1.00 [1.00-1.00] | 1.01 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.38 [0.37-0.46] | 0.99 |
| 0.4 | 0.39 [0.39-0.47] | 0.98 |
| 0.6 | 0.41 [0.41-0.49] | 0.98 |
| 0.8 | 0.45 [0.44-0.53] | 1.00 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.49 [0.41-0.52] | 0.99 |
| 0.4 | 0.47 [0.38-0.48] | 0.98 |
| 0.6 | 0.45 [0.39-0.45] | 0.98 |
| 0.8 | 0.43 [0.38-0.45] | 1.00 |

### paired lat_p50: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.99 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.98 |

### paired lat_p99: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.99 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.30-0.37] | 0.98 |

### paired lat_p50: shadow, agent-naive-open

| rate | shadow (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.99 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow, agent-naive-open

| rate | shadow (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.99 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.30-0.37] | 0.97 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.98 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.29-0.38] | 0.97 |

### paired lat_p50: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.38 [0.37-0.46] | 0.99 |
| 0.4 | 0.39 [0.38-0.47] | 0.98 |
| 0.6 | 0.41 [0.41-0.49] | 0.98 |
| 0.8 | 0.45 [0.44-0.53] | 0.99 |

### paired lat_p99: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.49 [0.41-0.52] | 0.99 |
| 0.4 | 0.47 [0.38-0.48] | 0.98 |
| 0.6 | 0.45 [0.39-0.45] | 0.98 |
| 0.8 | 0.44 [0.38-0.45] | 0.99 |

### paired lat_p50: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.37 [0.37-0.46] | 0.99 |
| 0.2 | 0.37 [0.36-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.43] | 0.98 |
| 0.6 | 0.35 [0.35-0.41] | 0.98 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 0.99 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.98 |
| 0.8 | 0.35 [0.31-0.37] | 0.97 |

### paired lat_p50: dataflow, agent-naive-open

| rate | dataflow (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.37 [0.37-0.46] | 0.99 |
| 0.2 | 0.37 [0.36-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.43] | 0.98 |
| 0.6 | 0.35 [0.35-0.41] | 0.98 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: dataflow, agent-naive-open

| rate | dataflow (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 0.99 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.98 |
| 0.8 | 0.35 [0.31-0.37] | 0.97 |

### paired lat_p50: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.37 [0.37-0.46] | 0.99 |
| 0.2 | 0.37 [0.36-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.43] | 0.99 |
| 0.6 | 0.36 [0.35-0.41] | 0.98 |
| 0.8 | 0.36 [0.35-0.40] | 0.97 |

### paired lat_p99: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 0.99 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.99 |
| 0.6 | 0.39 [0.33-0.42] | 0.98 |
| 0.8 | 0.35 [0.30-0.37] | 0.97 |

### paired lat_p50: shadow+waste0.5, fcfs

| rate | shadow+waste0.5 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.40 [0.39-0.50] | 1.00 |
| 0.1 | 0.41 [0.40-0.51] | 0.99 |
| 0.2 | 0.42 [0.41-0.51] | 0.98 |
| 0.4 | 0.45 [0.45-0.56] | 0.96 |
| 0.6 | 0.53 [0.52-0.65] | 0.98 |
| 0.8 | 0.66 [0.63-0.79] | 1.13 |

### paired lat_p99: shadow+waste0.5, fcfs

| rate | shadow+waste0.5 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.43-0.55] | 1.00 |
| 0.1 | 0.52 [0.44-0.53] | 0.99 |
| 0.2 | 0.51 [0.42-0.52] | 0.98 |
| 0.4 | 0.50 [0.44-0.53] | 0.96 |
| 0.6 | 0.51 [0.48-0.51] | 0.98 |
| 0.8 | 0.59 [0.57-0.59] | 1.13 |

### paired lat_p50: shadow+waste0.5, agent-naive

| rate | shadow+waste0.5 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.40 [0.39-0.50] | 1.00 |
| 0.1 | 0.40 [0.40-0.50] | 0.99 |
| 0.2 | 0.40 [0.40-0.50] | 0.99 |
| 0.4 | 0.40 [0.40-0.49] | 0.98 |
| 0.6 | 0.42 [0.42-0.50] | 0.96 |
| 0.8 | 0.67 [0.54-0.77] | 1.59 |

### paired lat_p99: shadow+waste0.5, agent-naive

| rate | shadow+waste0.5 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.49 [0.41-0.52] | 0.99 |
| 0.4 | 0.46 [0.38-0.47] | 0.98 |
| 0.6 | 0.44 [0.41-0.46] | 0.96 |
| 0.8 | 0.56 [0.49-0.65] | 1.59 |

### paired lat_p50: shadow+waste0.5, agent-naive-open

| rate | shadow+waste0.5 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.40 [0.39-0.50] | 1.00 |
| 0.1 | 0.40 [0.40-0.50] | 0.99 |
| 0.2 | 0.40 [0.40-0.50] | 0.99 |
| 0.4 | 0.40 [0.40-0.49] | 0.98 |
| 0.6 | 0.42 [0.42-0.50] | 0.96 |
| 0.8 | 0.66 [0.53-0.77] | 1.59 |

### paired lat_p99: shadow+waste0.5, agent-naive-open

| rate | shadow+waste0.5 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.49 [0.41-0.52] | 0.99 |
| 0.4 | 0.46 [0.38-0.47] | 0.98 |
| 0.6 | 0.44 [0.41-0.46] | 0.96 |
| 0.8 | 0.56 [0.48-0.65] | 1.59 |

### paired lat_p50: shadow+waste0.5, agent

| rate | shadow+waste0.5 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.98 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow+waste0.5, agent

| rate | shadow+waste0.5 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.29-0.38] | 0.97 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.43 [0.41-0.54] | 1.00 |
| 0.1 | 0.44 [0.43-0.54] | 0.99 |
| 0.2 | 0.46 [0.45-0.58] | 0.97 |
| 0.4 | 0.54 [0.53-0.67] | 0.96 |
| 0.6 | 0.70 [0.68-0.90] | 1.05 |
| 0.8 | 0.97 [0.91-1.14] | 1.42 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.43-0.55] | 1.00 |
| 0.1 | 0.52 [0.45-0.53] | 0.99 |
| 0.2 | 0.54 [0.46-0.54] | 0.97 |
| 0.4 | 0.57 [0.54-0.58] | 0.96 |
| 0.6 | 0.66 [0.65-0.69] | 1.05 |
| 0.8 | 0.83 [0.79-0.92] | 1.42 |

### paired lat_p50: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.42 [0.42-0.54] | 1.00 |
| 0.1 | 0.43 [0.42-0.54] | 0.99 |
| 0.2 | 0.44 [0.43-0.54] | 0.98 |
| 0.4 | 0.46 [0.45-0.55] | 0.97 |
| 0.6 | 0.80 [0.60-0.99] | 1.64 |
| 0.8 | 1.25 [1.13-1.43] | 2.97 |

### paired lat_p99: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.51 [0.42-0.52] | 0.98 |
| 0.4 | 0.50 [0.46-0.51] | 0.97 |
| 0.6 | 0.73 [0.62-0.89] | 1.64 |
| 0.8 | 1.15 [1.12-1.30] | 2.97 |

### paired lat_p50: shadow+waste1, agent-naive-open

| rate | shadow+waste1 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.42 [0.42-0.54] | 1.00 |
| 0.1 | 0.43 [0.42-0.54] | 0.99 |
| 0.2 | 0.44 [0.43-0.54] | 0.98 |
| 0.4 | 0.46 [0.45-0.55] | 0.97 |
| 0.6 | 0.80 [0.60-0.99] | 1.64 |
| 0.8 | 1.24 [1.13-1.43] | 2.97 |

### paired lat_p99: shadow+waste1, agent-naive-open

| rate | shadow+waste1 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.51 [0.42-0.52] | 0.98 |
| 0.4 | 0.50 [0.46-0.51] | 0.97 |
| 0.6 | 0.73 [0.62-0.89] | 1.64 |
| 0.8 | 1.15 [1.12-1.30] | 2.97 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.98 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.29-0.38] | 0.97 |

## Confidence-aware scheduler with mislabeled bets (`results/clog_eager_noise.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 19.3 | 22.0 | 22.0 | 22.0 | 22.0 |
| 0.1 | 53.1 | 20.0 | 23.2 | - | - | - |
| 0.2 | 56.5 | 21.3 | 26.3 | 26.3 | 26.3 | 26.3 |
| 0.4 | 62.8 | 24.6 | 33.7 | 33.7 | 33.7 | 33.7 |
| 0.6 | 68.9 | 28.5 | 48.5 | 48.5 | 48.5 | 48.5 |
| 0.8 | 75.9 | 34.2 | 73.7 | 73.7 | 73.7 | 73.7 |

### p50 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 19.4 | 22.0 | - | - | - |
| 0.1 | 53.1 | 19.9 | 22.9 | - | - | - |
| 0.2 | 56.5 | 20.9 | 24.7 | - | - | - |
| 0.4 | 62.8 | 23.0 | 28.8 | - | - | - |
| 0.6 | 68.9 | 24.9 | 55.1 | - | - | - |
| 0.8 | 75.9 | 27.8 | 94.7 | - | - | - |

### p50 session latency (s), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 19.4 | 22.0 | - | - | - |
| 0.1 | 53.1 | 19.9 | 22.9 | - | - | - |
| 0.2 | 56.5 | 20.9 | 24.7 | - | - | - |
| 0.4 | 62.8 | 23.0 | 28.8 | - | - | - |
| 0.6 | 68.9 | 24.9 | 55.0 | - | - | - |
| 0.8 | 75.9 | 27.8 | 94.3 | - | - | - |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 51.7 | 19.4 | 19.4 | 21.5 | 23.3 | 27.4 |
| 0.1 | 53.1 | 19.9 | 19.9 | - | - | - |
| 0.2 | 56.5 | 20.9 | 20.9 | 23.2 | 25.7 | 31.0 |
| 0.4 | 62.8 | 22.9 | 22.9 | 25.7 | 28.7 | 35.3 |
| 0.6 | 68.9 | 25.0 | 25.0 | 28.5 | 32.1 | 41.6 |
| 0.8 | 75.9 | 27.5 | 27.5 | 31.9 | 35.9 | 47.7 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 35.8 | 36.9 | 36.9 | 36.9 | 36.9 |
| 0.1 | 70.9 | 36.3 | 37.2 | - | - | - |
| 0.2 | 76.3 | 37.0 | 40.8 | 40.8 | 40.8 | 40.8 |
| 0.4 | 88.6 | 41.7 | 49.8 | 49.8 | 49.8 | 49.8 |
| 0.6 | 103.5 | 44.8 | 68.7 | 68.7 | 68.7 | 68.7 |
| 0.8 | 120.2 | 51.9 | 99.7 | 99.7 | 99.7 | 99.7 |

### p99 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 35.6 | 36.3 | - | - | - |
| 0.1 | 70.9 | 35.8 | 36.0 | - | - | - |
| 0.2 | 76.3 | 36.5 | 38.5 | - | - | - |
| 0.4 | 88.6 | 39.1 | 44.4 | - | - | - |
| 0.6 | 103.5 | 40.5 | 75.9 | - | - | - |
| 0.8 | 120.2 | 42.5 | 135.3 | - | - | - |

### p99 session latency (s), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 35.6 | 36.3 | - | - | - |
| 0.1 | 70.9 | 35.8 | 36.0 | - | - | - |
| 0.2 | 76.3 | 36.5 | 38.5 | - | - | - |
| 0.4 | 88.6 | 39.1 | 44.4 | - | - | - |
| 0.6 | 103.5 | 40.5 | 75.9 | - | - | - |
| 0.8 | 120.2 | 42.4 | 135.2 | - | - | - |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 68.3 | 35.6 | 35.6 | 37.8 | 38.5 | 49.3 |
| 0.1 | 70.9 | 35.8 | 35.8 | - | - | - |
| 0.2 | 76.3 | 36.5 | 36.5 | 39.7 | 40.3 | 52.4 |
| 0.4 | 88.6 | 39.1 | 39.1 | 43.0 | 47.4 | 60.9 |
| 0.6 | 103.5 | 40.6 | 40.6 | 46.9 | 51.8 | 71.1 |
| 0.8 | 120.2 | 42.1 | 42.1 | 51.9 | 59.9 | 85.0 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 20.0 | 22.7 | 22.7 | 22.7 | 22.7 |
| 0.1 | 17.5 | 21.7 | 24.4 | - | - | - |
| 0.2 | 19.1 | 23.8 | 30.8 | 30.8 | 30.8 | 30.8 |
| 0.4 | 22.6 | 29.9 | 41.8 | 41.8 | 41.8 | 41.8 |
| 0.6 | 26.3 | 35.4 | 59.6 | 59.6 | 59.6 | 59.6 |
| 0.8 | 30.6 | 44.1 | 74.6 | 74.6 | 74.6 | 74.6 |

### root TPOT p99 (ms), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 18.2 | 19.6 | - | - | - |
| 0.1 | 17.5 | 18.8 | 20.2 | - | - | - |
| 0.2 | 19.1 | 20.3 | 21.8 | - | - | - |
| 0.4 | 22.6 | 21.9 | 24.3 | - | - | - |
| 0.6 | 26.3 | 23.8 | 25.4 | - | - | - |
| 0.8 | 30.6 | 25.0 | 26.0 | - | - | - |

### root TPOT p99 (ms), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 18.2 | 19.6 | - | - | - |
| 0.1 | 17.5 | 18.8 | 20.2 | - | - | - |
| 0.2 | 19.1 | 20.3 | 21.8 | - | - | - |
| 0.4 | 22.6 | 21.9 | 24.3 | - | - | - |
| 0.6 | 26.3 | 23.9 | 25.4 | - | - | - |
| 0.8 | 30.6 | 25.3 | 26.1 | - | - | - |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 16.5 | 18.2 | 18.2 | 18.3 | 18.5 | 18.6 |
| 0.1 | 17.5 | 18.8 | 18.8 | - | - | - |
| 0.2 | 19.1 | 20.3 | 20.3 | 20.6 | 20.8 | 21.7 |
| 0.4 | 22.6 | 22.0 | 22.1 | 22.8 | 23.3 | 24.7 |
| 0.6 | 26.3 | 24.1 | 24.1 | 25.1 | 26.1 | 29.1 |
| 0.8 | 30.6 | 25.6 | 25.6 | 27.3 | 29.0 | 32.8 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.10 | 0.10 | 0.10 | 0.10 |
| 0.1 | 0.08 | 0.16 | 0.32 | - | - | - |
| 0.2 | 0.09 | 0.32 | 0.40 | 0.40 | 0.40 | 0.40 |
| 0.4 | 0.10 | 0.44 | 0.57 | 0.57 | 0.57 | 0.57 |
| 0.6 | 0.12 | 0.47 | 0.60 | 0.60 | 0.60 | 0.60 |
| 0.8 | 0.13 | 0.57 | 3.63 | 3.63 | 3.63 | 3.63 |

### root TTFT p99 (s), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.07 | - | - | - |
| 0.1 | 0.08 | 0.07 | 0.07 | - | - | - |
| 0.2 | 0.09 | 0.07 | 0.07 | - | - | - |
| 0.4 | 0.10 | 0.08 | 0.08 | - | - | - |
| 0.6 | 0.12 | 0.08 | 0.09 | - | - | - |
| 0.8 | 0.13 | 0.09 | 0.10 | - | - | - |

### root TTFT p99 (s), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.07 | - | - | - |
| 0.1 | 0.08 | 0.07 | 0.07 | - | - | - |
| 0.2 | 0.09 | 0.07 | 0.07 | - | - | - |
| 0.4 | 0.10 | 0.08 | 0.08 | - | - | - |
| 0.6 | 0.12 | 0.08 | 0.09 | - | - | - |
| 0.8 | 0.13 | 0.09 | 0.10 | - | - | - |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 | 0.06 | 0.06 | 0.07 |
| 0.1 | 0.08 | 0.07 | 0.07 | - | - | - |
| 0.2 | 0.09 | 0.07 | 0.07 | 0.08 | 0.08 | 0.08 |
| 0.4 | 0.10 | 0.08 | 0.08 | 0.08 | 0.09 | 0.10 |
| 0.6 | 0.12 | 0.08 | 0.08 | 0.09 | 0.10 | 0.11 |
| 0.8 | 0.13 | 0.09 | 0.09 | 0.10 | 0.11 | 0.12 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 0.44 | 0.53 | 0.53 | 0.53 | 0.53 |
| 0.1 | 0.09 | 0.46 | 0.55 | - | - | - |
| 0.2 | 0.09 | 0.46 | 0.59 | 0.59 | 0.59 | 0.59 |
| 0.4 | 0.10 | 0.73 | 0.73 | 0.73 | 0.73 | 0.73 |
| 0.6 | 0.12 | 0.75 | 0.90 | 0.90 | 0.90 | 0.90 |
| 0.8 | 0.13 | 0.87 | 3.32 | 3.32 | 3.32 | 3.32 |

### sub-call TTFT p99, claimed calls (s), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 1.34 | 1.58 | - | - | - |
| 0.1 | 0.09 | 1.49 | 1.88 | - | - | - |
| 0.2 | 0.09 | 1.83 | 2.53 | - | - | - |
| 0.4 | 0.10 | 2.53 | 7.20 | - | - | - |
| 0.6 | 0.12 | 3.31 | 38.32 | - | - | - |
| 0.8 | 0.13 | 6.32 | 100.88 | - | - | - |

### sub-call TTFT p99, claimed calls (s), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 1.34 | 1.58 | - | - | - |
| 0.1 | 0.09 | 1.49 | 1.88 | - | - | - |
| 0.2 | 0.09 | 1.83 | 2.53 | - | - | - |
| 0.4 | 0.10 | 2.54 | 7.20 | - | - | - |
| 0.6 | 0.12 | 3.23 | 38.29 | - | - | - |
| 0.8 | 0.13 | 5.80 | 100.46 | - | - | - |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.08 | 1.33 | 1.33 | 1.21 | 1.25 | 1.20 |
| 0.1 | 0.09 | 1.47 | 1.47 | - | - | - |
| 0.2 | 0.09 | 1.80 | 1.80 | 1.81 | 1.79 | 1.79 |
| 0.4 | 0.10 | 2.61 | 2.61 | 2.64 | 2.71 | 2.90 |
| 0.6 | 0.12 | 3.52 | 3.52 | 3.93 | 4.05 | 4.82 |
| 0.8 | 0.13 | 5.47 | 5.49 | 7.27 | 7.28 | 9.57 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.464 | 0.464 | 0.464 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.2 | 0.000 | 0.000 | 0.464 | 0.464 | 0.464 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.464 | 0.464 | 0.464 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.461 | 0.461 | 0.461 | 0.461 |
| 0.8 | 0.000 | 0.000 | 0.439 | 0.439 | 0.439 | 0.439 |

### wasted share of model tokens, agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.1 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.2 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.4 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.6 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.8 | 0.000 | 0.000 | 0.458 | - | - | - |

### wasted share of model tokens, agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.1 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.2 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.4 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.6 | 0.000 | 0.000 | 0.464 | - | - | - |
| 0.8 | 0.000 | 0.000 | 0.459 | - | - | - |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.089 | 0.160 | 0.274 |
| 0.1 | 0.000 | 0.000 | 0.000 | - | - | - |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.086 | 0.156 | 0.271 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.087 | 0.155 | 0.267 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.084 | 0.152 | 0.263 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.082 | 0.144 | 0.256 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | - | - | - |
| 0.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | - | - | - |
| 0.1 | 0 | 0 | 0 | - | - | - |
| 0.2 | 0 | 0 | 0 | - | - | - |
| 0.4 | 0 | 0 | 0 | - | - | - |
| 0.6 | 0 | 0 | 0 | - | - | - |
| 0.8 | 0 | 0 | 0 | - | - | - |

### suppressed bets re-issued because they were needed, agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | - | - | - |
| 0.1 | 0 | 0 | 0 | - | - | - |
| 0.2 | 0 | 0 | 0 | - | - | - |
| 0.4 | 0 | 0 | 0 | - | - | - |
| 0.6 | 0 | 0 | 0 | - | - | - |
| 0.8 | 0 | 0 | 0 | - | - | - |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 239 | 504 | 981 |
| 0.1 | 0 | 0 | 0 | - | - | - |
| 0.2 | 0 | 0 | 0 | 240 | 517 | 1008 |
| 0.4 | 0 | 0 | 0 | 251 | 534 | 1026 |
| 0.6 | 0 | 0 | 0 | 256 | 556 | 1091 |
| 0.8 | 0 | 0 | 0 | 276 | 582 | 1154 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.60 | 0.64 | 0.64 | 0.64 | 0.64 |
| 0.1 | 0.99 | 0.85 | 0.88 | - | - | - |
| 0.2 | 1.00 | 0.98 | 0.99 | 0.99 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.60 | 0.64 | - | - | - |
| 0.1 | 0.99 | 0.85 | 0.88 | - | - | - |
| 0.2 | 1.00 | 0.98 | 0.99 | - | - | - |
| 0.4 | 1.00 | 1.00 | 1.00 | - | - | - |
| 0.6 | 1.00 | 1.00 | 1.00 | - | - | - |
| 0.8 | 1.00 | 1.00 | 1.00 | - | - | - |

### GPU busy fraction (not spare capacity), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.60 | 0.64 | - | - | - |
| 0.1 | 0.99 | 0.85 | 0.88 | - | - | - |
| 0.2 | 1.00 | 0.98 | 0.99 | - | - | - |
| 0.4 | 1.00 | 1.00 | 1.00 | - | - | - |
| 0.6 | 1.00 | 1.00 | 1.00 | - | - | - |
| 0.8 | 1.00 | 1.00 | 1.00 | - | - | - |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.89 | 0.60 | 0.60 | 0.64 | 0.67 | 0.74 |
| 0.1 | 0.99 | 0.85 | 0.85 | - | - | - |
| 0.2 | 1.00 | 0.98 | 0.98 | 0.99 | 1.00 | 1.00 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 1.00 | 0.99 | - | - | - |
| 0.2 | 0.97 | 0.99 | 0.97 | 0.97 | 0.97 | 0.97 |
| 0.4 | 0.96 | 0.98 | 0.96 | 0.96 | 0.96 | 0.96 |
| 0.6 | 0.97 | 0.98 | 1.05 | 1.05 | 1.05 | 1.05 |
| 0.8 | 1.01 | 1.00 | 1.42 | 1.42 | 1.42 | 1.42 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 1.00 | 1.00 | - | - | - |
| 0.1 | 0.98 | 1.00 | 0.99 | - | - | - |
| 0.2 | 0.97 | 0.99 | 0.98 | - | - | - |
| 0.4 | 0.96 | 0.99 | 0.97 | - | - | - |
| 0.6 | 0.97 | 0.97 | 1.64 | - | - | - |
| 0.8 | 1.01 | 0.98 | 2.97 | - | - | - |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive-open

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 1.00 | 1.00 | - | - | - |
| 0.1 | 0.98 | 1.00 | 0.99 | - | - | - |
| 0.2 | 0.97 | 0.99 | 0.98 | - | - | - |
| 0.4 | 0.96 | 0.99 | 0.97 | - | - | - |
| 0.6 | 0.97 | 0.97 | 1.64 | - | - | - |
| 0.8 | 1.01 | 0.97 | 2.97 | - | - | - |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 | shadow+waste1+noise0.1 | shadow+waste1+noise0.2 | shadow+waste1+noise0.4 |
|---|---|---|---|---|---|---|
| 0.05 | 0.98 | 1.00 | 1.00 | 0.99 | 0.97 | 0.96 |
| 0.1 | 0.98 | 1.00 | 1.00 | - | - | - |
| 0.2 | 0.97 | 0.99 | 0.99 | 0.98 | 0.97 | 0.95 |
| 0.4 | 0.96 | 0.98 | 0.98 | 0.97 | 0.95 | 0.94 |
| 0.6 | 0.97 | 0.97 | 0.97 | 0.96 | 0.95 | 0.93 |
| 0.8 | 1.01 | 0.97 | 0.97 | 0.98 | 0.96 | 0.97 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.38 [0.37-0.46] | 0.99 |
| 0.4 | 0.39 [0.39-0.47] | 0.98 |
| 0.6 | 0.41 [0.41-0.49] | 0.98 |
| 0.8 | 0.45 [0.44-0.53] | 1.00 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.49 [0.41-0.52] | 0.99 |
| 0.4 | 0.47 [0.38-0.48] | 0.98 |
| 0.6 | 0.45 [0.39-0.45] | 0.98 |
| 0.8 | 0.43 [0.38-0.45] | 1.00 |

### paired lat_p50: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.99 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.98 |

### paired lat_p99: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.99 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.30-0.37] | 0.98 |

### paired lat_p50: shadow, agent-naive-open

| rate | shadow (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.99 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow, agent-naive-open

| rate | shadow (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.99 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.30-0.37] | 0.97 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.98 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.29-0.38] | 0.97 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.43 [0.41-0.54] | 1.00 |
| 0.1 | 0.44 [0.43-0.54] | 0.99 |
| 0.2 | 0.46 [0.45-0.58] | 0.97 |
| 0.4 | 0.54 [0.53-0.67] | 0.96 |
| 0.6 | 0.70 [0.68-0.90] | 1.05 |
| 0.8 | 0.97 [0.91-1.14] | 1.42 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.43-0.55] | 1.00 |
| 0.1 | 0.52 [0.45-0.53] | 0.99 |
| 0.2 | 0.54 [0.46-0.54] | 0.97 |
| 0.4 | 0.57 [0.54-0.58] | 0.96 |
| 0.6 | 0.66 [0.65-0.69] | 1.05 |
| 0.8 | 0.83 [0.79-0.92] | 1.42 |

### paired lat_p50: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.42 [0.42-0.54] | 1.00 |
| 0.1 | 0.43 [0.42-0.54] | 0.99 |
| 0.2 | 0.44 [0.43-0.54] | 0.98 |
| 0.4 | 0.46 [0.45-0.55] | 0.97 |
| 0.6 | 0.80 [0.60-0.99] | 1.64 |
| 0.8 | 1.25 [1.13-1.43] | 2.97 |

### paired lat_p99: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.51 [0.42-0.52] | 0.98 |
| 0.4 | 0.50 [0.46-0.51] | 0.97 |
| 0.6 | 0.73 [0.62-0.89] | 1.64 |
| 0.8 | 1.15 [1.12-1.30] | 2.97 |

### paired lat_p50: shadow+waste1, agent-naive-open

| rate | shadow+waste1 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.42 [0.42-0.54] | 1.00 |
| 0.1 | 0.43 [0.42-0.54] | 0.99 |
| 0.2 | 0.44 [0.43-0.54] | 0.98 |
| 0.4 | 0.46 [0.45-0.55] | 0.97 |
| 0.6 | 0.80 [0.60-0.99] | 1.64 |
| 0.8 | 1.24 [1.13-1.43] | 2.97 |

### paired lat_p99: shadow+waste1, agent-naive-open

| rate | shadow+waste1 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.44-0.53] | 0.99 |
| 0.2 | 0.51 [0.42-0.52] | 0.98 |
| 0.4 | 0.50 [0.46-0.51] | 0.97 |
| 0.6 | 0.73 [0.62-0.89] | 1.64 |
| 0.8 | 1.15 [1.12-1.30] | 2.97 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.37 [0.37-0.47] | 1.00 |
| 0.1 | 0.38 [0.37-0.47] | 1.00 |
| 0.2 | 0.37 [0.37-0.45] | 0.99 |
| 0.4 | 0.36 [0.36-0.44] | 0.98 |
| 0.6 | 0.36 [0.36-0.42] | 0.97 |
| 0.8 | 0.36 [0.36-0.40] | 0.97 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.43-0.55] | 1.00 |
| 0.1 | 0.51 [0.43-0.53] | 1.00 |
| 0.2 | 0.48 [0.40-0.51] | 0.99 |
| 0.4 | 0.44 [0.36-0.46] | 0.98 |
| 0.6 | 0.39 [0.33-0.42] | 0.97 |
| 0.8 | 0.35 [0.29-0.38] | 0.97 |

### paired lat_p50: shadow+waste1+noise0.1, fcfs

| rate | shadow+waste1+noise0.1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.43 [0.41-0.54] | 1.00 |
| 0.2 | 0.46 [0.45-0.58] | 0.97 |
| 0.4 | 0.54 [0.53-0.67] | 0.96 |
| 0.6 | 0.70 [0.68-0.90] | 1.05 |
| 0.8 | 0.97 [0.91-1.14] | 1.42 |

### paired lat_p99: shadow+waste1+noise0.1, fcfs

| rate | shadow+waste1+noise0.1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.43-0.55] | 1.00 |
| 0.2 | 0.54 [0.46-0.54] | 0.97 |
| 0.4 | 0.57 [0.54-0.58] | 0.96 |
| 0.6 | 0.66 [0.65-0.69] | 1.05 |
| 0.8 | 0.83 [0.79-0.92] | 1.42 |

### paired lat_p50: shadow+waste1+noise0.1, agent-naive

| rate | shadow+waste1+noise0.1 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.1, agent-naive

| rate | shadow+waste1+noise0.1 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.1, agent-naive-open

| rate | shadow+waste1+noise0.1 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.1, agent-naive-open

| rate | shadow+waste1+noise0.1 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.1, agent

| rate | shadow+waste1+noise0.1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.41 [0.41-0.52] | 0.99 |
| 0.2 | 0.41 [0.41-0.50] | 0.98 |
| 0.4 | 0.40 [0.40-0.49] | 0.97 |
| 0.6 | 0.41 [0.40-0.47] | 0.96 |
| 0.8 | 0.41 [0.41-0.46] | 0.98 |

### paired lat_p99: shadow+waste1+noise0.1, agent

| rate | shadow+waste1+noise0.1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.45-0.56] | 0.99 |
| 0.2 | 0.52 [0.43-0.53] | 0.98 |
| 0.4 | 0.48 [0.41-0.50] | 0.97 |
| 0.6 | 0.45 [0.38-0.47] | 0.96 |
| 0.8 | 0.43 [0.37-0.46] | 0.98 |

### paired lat_p50: shadow+waste1+noise0.2, fcfs

| rate | shadow+waste1+noise0.2 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.43 [0.41-0.54] | 1.00 |
| 0.2 | 0.46 [0.45-0.58] | 0.97 |
| 0.4 | 0.54 [0.53-0.67] | 0.96 |
| 0.6 | 0.70 [0.68-0.90] | 1.05 |
| 0.8 | 0.97 [0.91-1.14] | 1.42 |

### paired lat_p99: shadow+waste1+noise0.2, fcfs

| rate | shadow+waste1+noise0.2 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.43-0.55] | 1.00 |
| 0.2 | 0.54 [0.46-0.54] | 0.97 |
| 0.4 | 0.57 [0.54-0.58] | 0.96 |
| 0.6 | 0.66 [0.65-0.69] | 1.05 |
| 0.8 | 0.83 [0.79-0.92] | 1.42 |

### paired lat_p50: shadow+waste1+noise0.2, agent-naive

| rate | shadow+waste1+noise0.2 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.2, agent-naive

| rate | shadow+waste1+noise0.2 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.2, agent-naive-open

| rate | shadow+waste1+noise0.2 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.2, agent-naive-open

| rate | shadow+waste1+noise0.2 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.2, agent

| rate | shadow+waste1+noise0.2 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.45 [0.45-0.57] | 0.97 |
| 0.2 | 0.46 [0.45-0.56] | 0.97 |
| 0.4 | 0.45 [0.45-0.54] | 0.95 |
| 0.6 | 0.46 [0.46-0.53] | 0.95 |
| 0.8 | 0.47 [0.46-0.54] | 0.96 |

### paired lat_p99: shadow+waste1+noise0.2, agent

| rate | shadow+waste1+noise0.2 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.56 [0.53-0.57] | 0.97 |
| 0.2 | 0.53 [0.50-0.56] | 0.97 |
| 0.4 | 0.54 [0.48-0.54] | 0.95 |
| 0.6 | 0.50 [0.48-0.53] | 0.95 |
| 0.8 | 0.49 [0.47-0.51] | 0.96 |

### paired lat_p50: shadow+waste1+noise0.4, fcfs

| rate | shadow+waste1+noise0.4 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.43 [0.41-0.54] | 1.00 |
| 0.2 | 0.46 [0.45-0.58] | 0.97 |
| 0.4 | 0.54 [0.53-0.67] | 0.96 |
| 0.6 | 0.70 [0.68-0.90] | 1.05 |
| 0.8 | 0.97 [0.91-1.14] | 1.42 |

### paired lat_p99: shadow+waste1+noise0.4, fcfs

| rate | shadow+waste1+noise0.4 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.55 [0.43-0.55] | 1.00 |
| 0.2 | 0.54 [0.46-0.54] | 0.97 |
| 0.4 | 0.57 [0.54-0.58] | 0.96 |
| 0.6 | 0.66 [0.65-0.69] | 1.05 |
| 0.8 | 0.83 [0.79-0.92] | 1.42 |

### paired lat_p50: shadow+waste1+noise0.4, agent-naive

| rate | shadow+waste1+noise0.4 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.4, agent-naive

| rate | shadow+waste1+noise0.4 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.4, agent-naive-open

| rate | shadow+waste1+noise0.4 (agent-naive-open) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p99: shadow+waste1+noise0.4, agent-naive-open

| rate | shadow+waste1+noise0.4 (agent-naive-open) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|

### paired lat_p50: shadow+waste1+noise0.4, agent

| rate | shadow+waste1+noise0.4 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.54 [0.53-0.67] | 0.96 |
| 0.2 | 0.54 [0.54-0.68] | 0.95 |
| 0.4 | 0.57 [0.55-0.66] | 0.94 |
| 0.6 | 0.60 [0.57-0.68] | 0.93 |
| 0.8 | 0.63 [0.62-0.74] | 0.97 |

### paired lat_p99: shadow+waste1+noise0.4, agent

| rate | shadow+waste1+noise0.4 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.72 [0.67-0.73] | 0.96 |
| 0.2 | 0.69 [0.66-0.71] | 0.95 |
| 0.4 | 0.68 [0.66-0.70] | 0.94 |
| 0.6 | 0.67 [0.66-0.73] | 0.93 |
| 0.8 | 0.71 [0.71-0.73] | 0.97 |

## Sensitivity: per-sequence overhead 0.25 ms (`results/clog_eager_hiseq.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 54.8 | 20.7 | 24.6 |
| 0.1 | 57.8 | 22.4 | 27.8 |
| 0.2 | 65.6 | 26.2 | 38.2 |
| 0.4 | 84.9 | 39.1 | 120.1 |
| 0.6 | 125.6 | 76.7 | 236.7 |
| 0.8 | 164.3 | 117.5 | 328.7 |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 54.8 | 20.9 | 20.9 |
| 0.1 | 57.8 | 22.3 | 22.3 |
| 0.2 | 65.6 | 25.5 | 25.5 |
| 0.4 | 84.9 | 34.5 | 34.5 |
| 0.6 | 125.6 | 60.6 | 60.6 |
| 0.8 | 164.3 | 109.8 | 109.8 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 73.6 | 37.5 | 39.2 |
| 0.1 | 79.8 | 38.8 | 43.1 |
| 0.2 | 94.9 | 42.7 | 61.7 |
| 0.4 | 145.8 | 60.3 | 167.0 |
| 0.6 | 219.6 | 103.9 | 342.4 |
| 0.8 | 266.3 | 163.4 | 442.9 |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 73.6 | 37.3 | 37.3 |
| 0.1 | 79.8 | 37.5 | 37.5 |
| 0.2 | 94.9 | 41.6 | 41.6 |
| 0.4 | 145.8 | 52.1 | 52.1 |
| 0.6 | 219.6 | 83.6 | 83.7 |
| 0.8 | 266.3 | 138.1 | 138.1 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 18.2 | 24.3 | 29.9 |
| 0.1 | 20.6 | 26.9 | 36.9 |
| 0.2 | 25.0 | 33.5 | 54.5 |
| 0.4 | 38.3 | 55.7 | 131.6 |
| 0.6 | 56.4 | 96.8 | 161.7 |
| 0.8 | 77.0 | 135.9 | 171.2 |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 18.2 | 22.8 | 22.8 |
| 0.1 | 20.6 | 24.9 | 24.9 |
| 0.2 | 25.0 | 29.9 | 29.9 |
| 0.4 | 38.3 | 41.1 | 41.0 |
| 0.6 | 56.4 | 50.9 | 50.9 |
| 0.8 | 77.0 | 56.3 | 56.3 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.07 | 0.07 | 0.11 |
| 0.1 | 0.08 | 0.15 | 0.29 |
| 0.2 | 0.09 | 0.41 | 0.50 |
| 0.4 | 0.12 | 0.51 | 2.88 |
| 0.6 | 0.18 | 0.66 | 30.22 |
| 0.8 | 0.24 | 6.59 | 57.61 |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.07 | 0.07 | 0.07 |
| 0.1 | 0.08 | 0.07 | 0.07 |
| 0.2 | 0.09 | 0.09 | 0.09 |
| 0.4 | 0.12 | 0.11 | 0.11 |
| 0.6 | 0.18 | 0.13 | 0.13 |
| 0.8 | 0.24 | 0.16 | 0.17 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.08 | 0.46 | 0.56 |
| 0.1 | 0.09 | 0.48 | 0.58 |
| 0.2 | 0.10 | 0.61 | 0.66 |
| 0.4 | 0.14 | 0.81 | 3.27 |
| 0.6 | 0.19 | 1.08 | 31.19 |
| 0.8 | 0.25 | 6.01 | 63.50 |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.08 | 1.61 | 1.61 |
| 0.1 | 0.09 | 1.89 | 1.89 |
| 0.2 | 0.10 | 2.40 | 2.40 |
| 0.4 | 0.14 | 5.71 | 5.71 |
| 0.6 | 0.19 | 24.09 | 24.09 |
| 0.8 | 0.25 | 83.80 | 83.81 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.447 |
| 0.6 | 0.000 | 0.000 | 0.427 |
| 0.8 | 0.000 | 0.000 | 0.426 |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 |
| 0.1 | 0.000 | 0.000 | 0.000 |
| 0.2 | 0.000 | 0.000 | 0.000 |
| 0.4 | 0.000 | 0.000 | 0.000 |
| 0.6 | 0.000 | 0.000 | 0.000 |
| 0.8 | 0.000 | 0.000 | 0.000 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.90 | 0.62 | 0.67 |
| 0.1 | 1.00 | 0.87 | 0.91 |
| 0.2 | 1.00 | 0.99 | 1.00 |
| 0.4 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.90 | 0.62 | 0.62 |
| 0.1 | 1.00 | 0.87 | 0.87 |
| 0.2 | 1.00 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.98 | 1.01 | 1.00 |
| 0.1 | 0.97 | 0.99 | 0.99 |
| 0.2 | 0.96 | 0.97 | 0.95 |
| 0.4 | 1.01 | 0.99 | 1.82 |
| 0.6 | 1.19 | 1.43 | 2.19 |
| 0.8 | 1.17 | 1.79 | 1.91 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.98 | 1.01 | 1.01 |
| 0.1 | 0.97 | 0.99 | 0.99 |
| 0.2 | 0.96 | 0.97 | 0.97 |
| 0.4 | 1.01 | 0.99 | 0.98 |
| 0.6 | 1.19 | 1.37 | 1.37 |
| 0.8 | 1.17 | 2.40 | 2.40 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.38 [0.37-0.47] | 1.01 |
| 0.1 | 0.39 [0.39-0.46] | 0.99 |
| 0.2 | 0.40 [0.40-0.46] | 0.97 |
| 0.4 | 0.46 [0.43-0.50] | 0.99 |
| 0.6 | 0.61 [0.55-0.63] | 1.43 |
| 0.8 | 0.72 [0.69-0.79] | 1.79 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.52 [0.41-0.52] | 1.01 |
| 0.1 | 0.49 [0.40-0.49] | 0.99 |
| 0.2 | 0.46 [0.37-0.46] | 0.97 |
| 0.4 | 0.42 [0.38-0.44] | 0.99 |
| 0.6 | 0.47 [0.46-0.51] | 1.43 |
| 0.8 | 0.62 [0.60-0.67] | 1.79 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.38 [0.38-0.47] | 1.01 |
| 0.1 | 0.39 [0.38-0.46] | 0.99 |
| 0.2 | 0.39 [0.39-0.44] | 0.97 |
| 0.4 | 0.41 [0.38-0.43] | 0.99 |
| 0.6 | 0.48 [0.44-0.51] | 1.37 |
| 0.8 | 0.67 [0.60-0.72] | 2.40 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.52 [0.41-0.52] | 1.01 |
| 0.1 | 0.48 [0.40-0.48] | 0.99 |
| 0.2 | 0.44 [0.36-0.45] | 0.97 |
| 0.4 | 0.36 [0.32-0.38] | 0.99 |
| 0.6 | 0.38 [0.37-0.40] | 1.37 |
| 0.8 | 0.52 [0.50-0.58] | 2.40 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.45 [0.44-0.56] | 1.00 |
| 0.1 | 0.49 [0.48-0.58] | 0.99 |
| 0.2 | 0.58 [0.57-0.67] | 0.95 |
| 0.4 | 1.41 [1.24-1.56] | 1.82 |
| 0.6 | 1.90 [1.87-1.96] | 2.19 |
| 0.8 | 2.00 [1.91-2.08] | 1.91 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.53 [0.47-0.60] | 1.00 |
| 0.1 | 0.55 [0.49-0.55] | 0.99 |
| 0.2 | 0.63 [0.63-0.68] | 0.95 |
| 0.4 | 1.15 [1.11-1.28] | 1.82 |
| 0.6 | 1.60 [1.56-1.64] | 2.19 |
| 0.8 | 1.64 [1.62-1.66] | 1.91 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.38 [0.38-0.47] | 1.01 |
| 0.1 | 0.39 [0.38-0.46] | 0.99 |
| 0.2 | 0.39 [0.39-0.44] | 0.97 |
| 0.4 | 0.41 [0.38-0.43] | 0.98 |
| 0.6 | 0.48 [0.44-0.51] | 1.37 |
| 0.8 | 0.67 [0.60-0.72] | 2.40 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.52 [0.41-0.52] | 1.01 |
| 0.1 | 0.48 [0.40-0.48] | 0.99 |
| 0.2 | 0.44 [0.36-0.45] | 0.97 |
| 0.4 | 0.36 [0.32-0.38] | 0.98 |
| 0.6 | 0.38 [0.37-0.40] | 1.37 |
| 0.8 | 0.52 [0.50-0.58] | 2.40 |

## Programs that already batch their fan-out (`results/clog_eager_batched.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 24.1 | 19.0 | 21.4 |
| 0.1 | 24.7 | 19.5 | 22.4 |
| 0.2 | 26.2 | 20.6 | 24.6 |
| 0.4 | 29.6 | 23.2 | 31.0 |
| 0.6 | 32.7 | 26.5 | 40.0 |
| 0.8 | 37.2 | 30.9 | 55.1 |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 24.1 | 19.1 | 19.1 |
| 0.1 | 24.7 | 19.6 | 19.6 |
| 0.2 | 26.2 | 20.4 | 20.4 |
| 0.4 | 29.6 | 22.1 | 22.1 |
| 0.6 | 32.7 | 23.8 | 23.8 |
| 0.8 | 37.2 | 25.8 | 25.8 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 47.1 | 36.5 | 36.8 |
| 0.1 | 47.7 | 36.9 | 37.9 |
| 0.2 | 48.6 | 37.8 | 40.0 |
| 0.4 | 53.1 | 40.2 | 47.9 |
| 0.6 | 60.8 | 44.6 | 59.8 |
| 0.8 | 70.1 | 48.5 | 81.7 |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 47.1 | 36.3 | 36.3 |
| 0.1 | 47.7 | 36.7 | 36.7 |
| 0.2 | 48.6 | 37.3 | 37.3 |
| 0.4 | 53.1 | 38.6 | 38.7 |
| 0.6 | 60.8 | 40.7 | 40.7 |
| 0.8 | 70.1 | 42.1 | 42.1 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 17.8 | 19.1 | 21.6 |
| 0.1 | 19.0 | 20.5 | 24.0 |
| 0.2 | 20.5 | 23.1 | 27.8 |
| 0.4 | 24.9 | 28.0 | 38.2 |
| 0.6 | 28.7 | 32.6 | 49.2 |
| 0.8 | 32.7 | 39.3 | 65.3 |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 17.8 | 17.6 | 17.6 |
| 0.1 | 19.0 | 18.5 | 18.5 |
| 0.2 | 20.5 | 19.7 | 19.7 |
| 0.4 | 24.9 | 21.4 | 21.4 |
| 0.6 | 28.7 | 22.7 | 22.7 |
| 0.8 | 32.7 | 24.7 | 24.7 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.07 |
| 0.1 | 0.08 | 0.17 | 0.14 |
| 0.2 | 0.08 | 0.28 | 0.33 |
| 0.4 | 0.21 | 0.40 | 0.51 |
| 0.6 | 0.24 | 0.44 | 0.57 |
| 0.8 | 0.33 | 0.48 | 0.63 |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.06 | 0.06 | 0.06 |
| 0.1 | 0.08 | 0.07 | 0.07 |
| 0.2 | 0.08 | 0.07 | 0.07 |
| 0.4 | 0.21 | 0.08 | 0.08 |
| 0.6 | 0.24 | 0.08 | 0.08 |
| 0.8 | 0.33 | 0.09 | 0.09 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.31 | 0.44 | 0.53 |
| 0.1 | 0.31 | 0.45 | 0.54 |
| 0.2 | 0.31 | 0.58 | 0.58 |
| 0.4 | 0.34 | 0.59 | 0.72 |
| 0.6 | 0.34 | 0.70 | 0.88 |
| 0.8 | 0.44 | 0.86 | 1.03 |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.31 | 0.99 | 0.98 |
| 0.1 | 0.31 | 1.21 | 1.21 |
| 0.2 | 0.31 | 1.65 | 1.65 |
| 0.4 | 0.34 | 2.44 | 2.44 |
| 0.6 | 0.34 | 2.92 | 2.92 |
| 0.8 | 0.44 | 4.13 | 4.13 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.460 |
| 0.1 | 0.000 | 0.000 | 0.460 |
| 0.2 | 0.000 | 0.000 | 0.460 |
| 0.4 | 0.000 | 0.000 | 0.460 |
| 0.6 | 0.000 | 0.000 | 0.460 |
| 0.8 | 0.000 | 0.000 | 0.452 |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 |
| 0.1 | 0.000 | 0.000 | 0.000 |
| 0.2 | 0.000 | 0.000 | 0.000 |
| 0.4 | 0.000 | 0.000 | 0.000 |
| 0.6 | 0.000 | 0.000 | 0.000 |
| 0.8 | 0.000 | 0.000 | 0.000 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.72 | 0.59 | 0.62 |
| 0.1 | 0.93 | 0.85 | 0.88 |
| 0.2 | 1.00 | 0.98 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.72 | 0.59 | 0.59 |
| 0.1 | 0.93 | 0.85 | 0.85 |
| 0.2 | 1.00 | 0.98 | 0.98 |
| 0.4 | 1.00 | 1.00 | 1.00 |
| 0.6 | 1.00 | 1.00 | 1.00 |
| 0.8 | 1.00 | 1.00 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.99 | 0.98 | 0.99 |
| 0.1 | 1.00 | 0.99 | 1.00 |
| 0.2 | 1.01 | 1.00 | 1.01 |
| 0.4 | 1.03 | 1.02 | 1.06 |
| 0.6 | 1.05 | 1.04 | 1.15 |
| 0.8 | 1.09 | 1.08 | 1.37 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | shadow | shadow+waste1 |
|---|---|---|---|
| 0.05 | 0.99 | 0.98 | 0.98 |
| 0.1 | 1.00 | 0.99 | 0.99 |
| 0.2 | 1.01 | 1.00 | 1.00 |
| 0.4 | 1.03 | 1.00 | 1.00 |
| 0.6 | 1.05 | 1.02 | 1.02 |
| 0.8 | 1.09 | 1.03 | 1.03 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.77-0.80] | 0.98 |
| 0.1 | 0.78 [0.78-0.79] | 0.99 |
| 0.2 | 0.78 [0.78-0.81] | 1.00 |
| 0.4 | 0.78 [0.78-0.78] | 1.02 |
| 0.6 | 0.80 [0.79-0.81] | 1.04 |
| 0.8 | 0.81 [0.80-0.83] | 1.08 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.70-0.84] | 0.98 |
| 0.1 | 0.80 [0.71-0.83] | 0.99 |
| 0.2 | 0.79 [0.71-0.82] | 1.00 |
| 0.4 | 0.76 [0.71-0.81] | 1.02 |
| 0.6 | 0.73 [0.69-0.80] | 1.04 |
| 0.8 | 0.73 [0.69-0.76] | 1.08 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.78-0.80] | 0.98 |
| 0.1 | 0.78 [0.78-0.79] | 0.99 |
| 0.2 | 0.77 [0.77-0.79] | 1.00 |
| 0.4 | 0.75 [0.75-0.75] | 1.00 |
| 0.6 | 0.73 [0.71-0.73] | 1.02 |
| 0.8 | 0.69 [0.68-0.69] | 1.03 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.70-0.84] | 0.98 |
| 0.1 | 0.79 [0.70-0.83] | 0.99 |
| 0.2 | 0.78 [0.70-0.81] | 1.00 |
| 0.4 | 0.74 [0.68-0.79] | 1.00 |
| 0.6 | 0.67 [0.64-0.76] | 1.02 |
| 0.8 | 0.62 [0.60-0.71] | 1.03 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.89 [0.87-0.89] | 0.99 |
| 0.1 | 0.89 [0.89-0.91] | 1.00 |
| 0.2 | 0.93 [0.91-0.95] | 1.01 |
| 0.4 | 1.03 [1.02-1.05] | 1.06 |
| 0.6 | 1.18 [1.17-1.25] | 1.15 |
| 0.8 | 1.43 [1.41-1.50] | 1.37 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.80 [0.72-0.85] | 0.99 |
| 0.1 | 0.80 [0.73-0.85] | 1.00 |
| 0.2 | 0.82 [0.76-0.86] | 1.01 |
| 0.4 | 0.87 [0.81-0.91] | 1.06 |
| 0.6 | 0.94 [0.91-0.98] | 1.15 |
| 0.8 | 1.17 [1.15-1.18] | 1.37 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.78-0.80] | 0.98 |
| 0.1 | 0.78 [0.78-0.79] | 0.99 |
| 0.2 | 0.77 [0.77-0.79] | 1.00 |
| 0.4 | 0.75 [0.75-0.75] | 1.00 |
| 0.6 | 0.73 [0.71-0.73] | 1.02 |
| 0.8 | 0.69 [0.68-0.69] | 1.03 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.70-0.84] | 0.98 |
| 0.1 | 0.79 [0.70-0.83] | 0.99 |
| 0.2 | 0.78 [0.70-0.81] | 1.00 |
| 0.4 | 0.74 [0.68-0.79] | 1.00 |
| 0.6 | 0.67 [0.64-0.76] | 1.02 |
| 0.8 | 0.62 [0.60-0.71] | 1.03 |

## H100, Qwen3-4B, CUDA graphs (`results/clog_graphs.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 14.3 | 5.6 | 5.6 | 6.7 |
| 0.1 | 14.8 | 5.8 | 5.8 | 7.0 |
| 0.2 | 15.7 | 6.2 | 6.2 | 7.9 |
| 0.4 | 17.4 | 7.4 | 7.3 | 10.7 |
| 0.6 | 19.4 | 8.6 | 8.6 | 15.2 |
| 0.8 | 22.6 | 10.3 | 10.2 | 27.5 |

### p50 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 14.3 | 5.5 | 5.5 | 6.5 |
| 0.1 | 14.8 | 5.7 | 5.6 | 6.7 |
| 0.2 | 15.7 | 6.0 | 6.0 | 7.5 |
| 0.4 | 17.4 | 6.8 | 6.7 | 9.7 |
| 0.6 | 19.4 | 7.9 | 7.8 | 13.4 |
| 0.8 | 22.6 | 9.5 | 9.3 | 17.1 |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 14.3 | 5.5 | 5.5 | 5.5 |
| 0.1 | 14.8 | 5.7 | 5.6 | 5.7 |
| 0.2 | 15.7 | 6.0 | 5.9 | 6.0 |
| 0.4 | 17.4 | 6.7 | 6.6 | 6.7 |
| 0.6 | 19.4 | 7.4 | 7.4 | 7.4 |
| 0.8 | 22.6 | 8.3 | 8.2 | 8.3 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 30.2 | 25.0 | 25.0 | 25.1 |
| 0.1 | 30.4 | 25.6 | 25.6 | 26.7 |
| 0.2 | 30.6 | 26.2 | 26.2 | 27.6 |
| 0.4 | 32.2 | 26.9 | 26.8 | 29.3 |
| 0.6 | 34.0 | 27.4 | 27.3 | 32.2 |
| 0.8 | 38.5 | 31.1 | 30.6 | 48.9 |

### p99 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 30.2 | 25.0 | 25.0 | 25.2 |
| 0.1 | 30.4 | 25.5 | 25.5 | 26.0 |
| 0.2 | 30.6 | 26.0 | 26.0 | 26.3 |
| 0.4 | 32.2 | 26.3 | 26.2 | 27.9 |
| 0.6 | 34.0 | 26.5 | 26.4 | 30.0 |
| 0.8 | 38.5 | 28.1 | 28.0 | 32.3 |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 30.2 | 25.0 | 25.0 | 25.0 |
| 0.1 | 30.4 | 25.4 | 25.4 | 25.4 |
| 0.2 | 30.6 | 26.0 | 26.0 | 26.0 |
| 0.4 | 32.2 | 26.4 | 26.3 | 26.4 |
| 0.6 | 34.0 | 26.2 | 26.2 | 26.2 |
| 0.8 | 38.5 | 28.2 | 28.1 | 28.2 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 4.8 | 7.3 | 7.1 | 8.4 |
| 0.1 | 5.0 | 7.9 | 7.9 | 10.4 |
| 0.2 | 5.5 | 8.9 | 9.1 | 12.2 |
| 0.4 | 6.8 | 11.2 | 11.1 | 18.4 |
| 0.6 | 8.3 | 13.6 | 13.4 | 26.6 |
| 0.8 | 10.3 | 18.1 | 17.9 | 42.5 |

### root TPOT p99 (ms), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 4.8 | 6.1 | 5.9 | 6.6 |
| 0.1 | 5.0 | 6.3 | 6.3 | 6.8 |
| 0.2 | 5.5 | 6.7 | 6.7 | 7.4 |
| 0.4 | 6.8 | 6.9 | 7.1 | 9.1 |
| 0.6 | 8.3 | 8.1 | 8.4 | 10.8 |
| 0.8 | 10.3 | 9.5 | 9.4 | 12.4 |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 4.8 | 6.1 | 5.9 | 6.1 |
| 0.1 | 5.0 | 6.4 | 6.4 | 6.4 |
| 0.2 | 5.5 | 7.0 | 7.3 | 7.0 |
| 0.4 | 6.8 | 8.0 | 8.1 | 8.0 |
| 0.6 | 8.3 | 9.0 | 9.1 | 9.0 |
| 0.8 | 10.3 | 10.0 | 9.9 | 10.0 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.03 | 0.03 | 0.05 |
| 0.1 | 0.04 | 0.04 | 0.04 | 0.09 |
| 0.2 | 0.04 | 0.16 | 0.21 | 0.23 |
| 0.4 | 0.06 | 0.31 | 0.29 | 0.37 |
| 0.6 | 0.06 | 0.35 | 0.35 | 0.38 |
| 0.8 | 0.07 | 0.35 | 0.35 | 0.50 |

### root TTFT p99 (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.03 | 0.03 | 0.04 |
| 0.1 | 0.04 | 0.04 | 0.04 | 0.04 |
| 0.2 | 0.04 | 0.04 | 0.04 | 0.04 |
| 0.4 | 0.06 | 0.04 | 0.04 | 0.05 |
| 0.6 | 0.06 | 0.05 | 0.05 | 0.05 |
| 0.8 | 0.07 | 0.05 | 0.05 | 0.05 |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.03 | 0.03 | 0.03 |
| 0.1 | 0.04 | 0.04 | 0.04 | 0.04 |
| 0.2 | 0.04 | 0.04 | 0.04 | 0.04 |
| 0.4 | 0.06 | 0.04 | 0.04 | 0.04 |
| 0.6 | 0.06 | 0.05 | 0.05 | 0.05 |
| 0.8 | 0.07 | 0.05 | 0.05 | 0.05 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.35 | 0.35 | 0.42 |
| 0.1 | 0.03 | 0.35 | 0.35 | 0.42 |
| 0.2 | 0.06 | 0.36 | 0.36 | 0.42 |
| 0.4 | 0.06 | 0.36 | 0.47 | 0.45 |
| 0.6 | 0.06 | 0.47 | 0.47 | 0.53 |
| 0.8 | 0.07 | 0.59 | 0.48 | 0.72 |

### sub-call TTFT p99, claimed calls (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.58 | 0.68 | 1.40 |
| 0.1 | 0.03 | 0.98 | 0.98 | 2.11 |
| 0.2 | 0.06 | 1.57 | 1.64 | 2.32 |
| 0.4 | 0.06 | 2.14 | 2.18 | 2.66 |
| 0.6 | 0.06 | 2.45 | 2.48 | 3.60 |
| 0.8 | 0.07 | 2.89 | 2.88 | 5.06 |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.03 | 0.40 | 0.40 | 0.39 |
| 0.1 | 0.03 | 0.42 | 0.42 | 0.41 |
| 0.2 | 0.06 | 0.60 | 0.56 | 0.60 |
| 0.4 | 0.06 | 0.72 | 0.71 | 0.71 |
| 0.6 | 0.06 | 0.80 | 0.83 | 0.80 |
| 0.8 | 0.07 | 0.95 | 1.10 | 0.95 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.464 |

### wasted share of model tokens, agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.463 |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.001 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.001 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.001 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.6 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.8 | 0.000 | 0.000 | 0.000 | 0.000 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |
| 0.6 | 0 | 0 | 0 | 0 |
| 0.8 | 0 | 0 | 0 | 0 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.42 | 0.22 | 0.22 | 0.25 |
| 0.1 | 0.68 | 0.39 | 0.39 | 0.45 |
| 0.2 | 0.91 | 0.65 | 0.65 | 0.72 |
| 0.4 | 1.00 | 0.90 | 0.90 | 0.94 |
| 0.6 | 1.00 | 0.97 | 0.97 | 0.99 |
| 0.8 | 1.00 | 0.98 | 0.98 | 0.99 |

### GPU busy fraction (not spare capacity), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.42 | 0.22 | 0.22 | 0.24 |
| 0.1 | 0.68 | 0.39 | 0.39 | 0.44 |
| 0.2 | 0.91 | 0.64 | 0.64 | 0.70 |
| 0.4 | 1.00 | 0.89 | 0.89 | 0.94 |
| 0.6 | 1.00 | 0.96 | 0.96 | 0.99 |
| 0.8 | 1.00 | 0.98 | 0.98 | 1.00 |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.42 | 0.22 | 0.22 | 0.22 |
| 0.1 | 0.68 | 0.39 | 0.38 | 0.39 |
| 0.2 | 0.91 | 0.64 | 0.64 | 0.64 |
| 0.4 | 1.00 | 0.89 | 0.89 | 0.89 |
| 0.6 | 1.00 | 0.96 | 0.96 | 0.96 |
| 0.8 | 1.00 | 0.98 | 0.98 | 0.98 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 1.01 | 1.01 | 1.02 |
| 0.2 | 0.98 | 1.00 | 1.00 | 0.99 |
| 0.4 | 0.96 | 0.98 | 0.98 | 0.94 |
| 0.6 | 0.95 | 0.96 | 0.96 | 0.98 |
| 0.8 | 0.97 | 0.97 | 0.97 | 1.10 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.00 | 1.00 | 0.99 |
| 0.1 | 0.98 | 1.00 | 1.00 | 1.01 |
| 0.2 | 0.98 | 1.00 | 1.00 | 0.99 |
| 0.4 | 0.96 | 0.98 | 0.98 | 0.96 |
| 0.6 | 0.95 | 0.95 | 0.95 | 1.00 |
| 0.8 | 0.97 | 0.98 | 0.97 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.00 | 1.00 | 1.00 |
| 0.1 | 0.98 | 1.01 | 1.01 | 1.01 |
| 0.2 | 0.98 | 1.00 | 1.00 | 1.00 |
| 0.4 | 0.96 | 0.99 | 0.98 | 0.99 |
| 0.6 | 0.95 | 0.97 | 0.97 | 0.97 |
| 0.8 | 0.97 | 0.97 | 0.96 | 0.97 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.39 [0.38-0.39] | 1.00 |
| 0.1 | 0.39 [0.39-0.41] | 1.01 |
| 0.2 | 0.39 [0.39-0.41] | 1.00 |
| 0.4 | 0.43 [0.43-0.43] | 0.98 |
| 0.6 | 0.44 [0.43-0.45] | 0.96 |
| 0.8 | 0.45 [0.45-0.48] | 0.97 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.01 |
| 0.2 | 0.86 [0.81-0.87] | 1.00 |
| 0.4 | 0.84 [0.77-0.85] | 0.98 |
| 0.6 | 0.79 [0.67-0.87] | 0.96 |
| 0.8 | 0.79 [0.63-0.87] | 0.97 |

### paired lat_p50: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.39 [0.38-0.39] | 1.00 |
| 0.1 | 0.38 [0.38-0.39] | 1.00 |
| 0.2 | 0.38 [0.38-0.40] | 1.00 |
| 0.4 | 0.40 [0.39-0.40] | 0.98 |
| 0.6 | 0.40 [0.39-0.41] | 0.95 |
| 0.8 | 0.41 [0.41-0.44] | 0.98 |

### paired lat_p99: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.00 |
| 0.2 | 0.85 [0.80-0.86] | 1.00 |
| 0.4 | 0.82 [0.75-0.84] | 0.98 |
| 0.6 | 0.76 [0.64-0.85] | 0.95 |
| 0.8 | 0.71 [0.56-0.82] | 0.98 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.39 [0.38-0.39] | 1.00 |
| 0.1 | 0.38 [0.38-0.39] | 1.01 |
| 0.2 | 0.38 [0.38-0.40] | 1.00 |
| 0.4 | 0.39 [0.38-0.40] | 0.99 |
| 0.6 | 0.38 [0.37-0.39] | 0.97 |
| 0.8 | 0.36 [0.36-0.39] | 0.97 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.01 |
| 0.2 | 0.85 [0.80-0.86] | 1.00 |
| 0.4 | 0.82 [0.75-0.84] | 0.99 |
| 0.6 | 0.76 [0.63-0.85] | 0.97 |
| 0.8 | 0.72 [0.56-0.82] | 0.97 |

### paired lat_p50: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.39 [0.38-0.39] | 1.00 |
| 0.1 | 0.39 [0.39-0.40] | 1.01 |
| 0.2 | 0.39 [0.39-0.41] | 1.00 |
| 0.4 | 0.42 [0.42-0.43] | 0.98 |
| 0.6 | 0.44 [0.43-0.45] | 0.96 |
| 0.8 | 0.45 [0.45-0.48] | 0.97 |

### paired lat_p99: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.80-0.87] | 1.01 |
| 0.2 | 0.86 [0.81-0.87] | 1.00 |
| 0.4 | 0.83 [0.77-0.85] | 0.98 |
| 0.6 | 0.79 [0.67-0.87] | 0.96 |
| 0.8 | 0.78 [0.62-0.85] | 0.97 |

### paired lat_p50: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.38 [0.38-0.38] | 1.00 |
| 0.1 | 0.38 [0.38-0.39] | 1.00 |
| 0.2 | 0.38 [0.38-0.39] | 1.00 |
| 0.4 | 0.39 [0.39-0.40] | 0.98 |
| 0.6 | 0.40 [0.39-0.41] | 0.95 |
| 0.8 | 0.41 [0.41-0.43] | 0.97 |

### paired lat_p99: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.00 |
| 0.2 | 0.85 [0.80-0.86] | 1.00 |
| 0.4 | 0.81 [0.75-0.84] | 0.98 |
| 0.6 | 0.76 [0.64-0.85] | 0.95 |
| 0.8 | 0.71 [0.56-0.83] | 0.97 |

### paired lat_p50: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.38 [0.38-0.38] | 1.00 |
| 0.1 | 0.38 [0.38-0.39] | 1.01 |
| 0.2 | 0.38 [0.37-0.39] | 1.00 |
| 0.4 | 0.38 [0.38-0.39] | 0.98 |
| 0.6 | 0.38 [0.37-0.39] | 0.97 |
| 0.8 | 0.36 [0.36-0.39] | 0.96 |

### paired lat_p99: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.01 |
| 0.2 | 0.85 [0.80-0.86] | 1.00 |
| 0.4 | 0.82 [0.75-0.84] | 0.98 |
| 0.6 | 0.76 [0.63-0.85] | 0.97 |
| 0.8 | 0.72 [0.56-0.82] | 0.96 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.46 [0.46-0.47] | 1.00 |
| 0.1 | 0.48 [0.46-0.48] | 1.02 |
| 0.2 | 0.50 [0.50-0.53] | 0.99 |
| 0.4 | 0.62 [0.62-0.64] | 0.94 |
| 0.6 | 0.78 [0.75-0.86] | 0.98 |
| 0.8 | 1.22 [1.11-1.57] | 1.10 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.88] | 1.00 |
| 0.1 | 0.88 [0.80-0.88] | 1.02 |
| 0.2 | 0.88 [0.85-0.90] | 0.99 |
| 0.4 | 0.89 [0.89-0.97] | 0.94 |
| 0.6 | 0.96 [0.95-0.99] | 0.98 |
| 0.8 | 1.24 [1.19-1.33] | 1.10 |

### paired lat_p50: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.44 [0.44-0.45] | 0.99 |
| 0.1 | 0.45 [0.44-0.46] | 1.01 |
| 0.2 | 0.47 [0.46-0.49] | 0.99 |
| 0.4 | 0.57 [0.56-0.58] | 0.96 |
| 0.6 | 0.69 [0.66-0.74] | 1.00 |
| 0.8 | 0.76 [0.74-0.85] | 1.00 |

### paired lat_p99: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.88] | 0.99 |
| 0.1 | 0.86 [0.79-0.87] | 1.01 |
| 0.2 | 0.86 [0.82-0.87] | 0.99 |
| 0.4 | 0.87 [0.82-0.88] | 0.96 |
| 0.6 | 0.86 [0.75-0.90] | 1.00 |
| 0.8 | 0.82 [0.67-0.90] | 1.00 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.39 [0.38-0.39] | 1.00 |
| 0.1 | 0.38 [0.38-0.39] | 1.01 |
| 0.2 | 0.38 [0.38-0.40] | 1.00 |
| 0.4 | 0.39 [0.38-0.40] | 0.99 |
| 0.6 | 0.38 [0.37-0.39] | 0.97 |
| 0.8 | 0.36 [0.36-0.39] | 0.97 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.83 [0.78-0.87] | 1.00 |
| 0.1 | 0.84 [0.79-0.87] | 1.01 |
| 0.2 | 0.85 [0.80-0.86] | 1.00 |
| 0.4 | 0.82 [0.75-0.84] | 0.99 |
| 0.6 | 0.76 [0.63-0.85] | 0.97 |
| 0.8 | 0.72 [0.55-0.82] | 0.97 |

## H100, Qwen3-30B-A3B, CUDA graphs (`results/clog_moe.csv`)

### p50 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 20.3 | 10.1 | 10.0 | 13.9 |
| 0.1 | 25.0 | 11.9 | 11.8 | 18.6 |
| 0.2 | 39.8 | 17.9 | 17.6 | 28.9 |
| 0.3 | 54.6 | 24.7 | 24.7 | 36.2 |
| 0.4 | 63.1 | 29.9 | 29.8 | 42.9 |

### p50 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 20.3 | 12.7 | 12.6 | 18.9 |
| 0.1 | 25.0 | 15.4 | 15.3 | 24.7 |
| 0.2 | 39.8 | 22.5 | 21.7 | 36.1 |
| 0.3 | 54.6 | 29.1 | 28.9 | 43.4 |
| 0.4 | 63.1 | 33.8 | 33.6 | 52.2 |

### p50 session latency (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 20.3 | 10.6 | 10.6 | 10.6 |
| 0.1 | 25.0 | 13.1 | 13.0 | 13.1 |
| 0.2 | 39.8 | 19.5 | 19.3 | 19.5 |
| 0.3 | 54.6 | 26.1 | 25.5 | 26.1 |
| 0.4 | 63.1 | 29.9 | 29.8 | 29.9 |

### p99 session latency (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 39.2 | 29.9 | 29.9 | 33.2 |
| 0.1 | 50.2 | 31.7 | 31.7 | 37.2 |
| 0.2 | 75.2 | 36.4 | 36.4 | 44.1 |
| 0.3 | 97.8 | 41.4 | 41.4 | 50.0 |
| 0.4 | 112.3 | 44.9 | 44.8 | 62.7 |

### p99 session latency (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 39.2 | 31.1 | 31.1 | 35.7 |
| 0.1 | 50.2 | 32.4 | 32.4 | 40.2 |
| 0.2 | 75.2 | 39.4 | 37.9 | 51.1 |
| 0.3 | 97.8 | 44.0 | 44.0 | 61.3 |
| 0.4 | 112.3 | 46.5 | 45.8 | 79.2 |

### p99 session latency (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 39.2 | 31.0 | 30.9 | 31.0 |
| 0.1 | 50.2 | 32.6 | 32.6 | 32.6 |
| 0.2 | 75.2 | 37.5 | 37.4 | 37.5 |
| 0.3 | 97.8 | 41.2 | 42.1 | 41.2 |
| 0.4 | 112.3 | 44.1 | 44.2 | 44.1 |

### root TPOT p99 (ms), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 10.5 | 18.8 | 18.6 | 24.2 |
| 0.1 | 13.9 | 21.8 | 22.6 | 27.7 |
| 0.2 | 20.4 | 27.5 | 27.4 | 33.9 |
| 0.3 | 25.3 | 31.7 | 31.8 | 36.0 |
| 0.4 | 28.4 | 35.0 | 34.9 | 36.5 |

### root TPOT p99 (ms), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 10.5 | 17.9 | 18.6 | 24.2 |
| 0.1 | 13.9 | 22.5 | 22.7 | 27.4 |
| 0.2 | 20.4 | 27.5 | 27.5 | 30.2 |
| 0.3 | 25.3 | 29.0 | 29.0 | 31.9 |
| 0.4 | 28.4 | 31.0 | 30.7 | 32.7 |

### root TPOT p99 (ms), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 10.5 | 20.0 | 20.1 | 20.0 |
| 0.1 | 13.9 | 22.4 | 22.9 | 22.4 |
| 0.2 | 20.4 | 26.8 | 27.1 | 26.8 |
| 0.3 | 25.3 | 29.2 | 29.3 | 29.2 |
| 0.4 | 28.4 | 30.7 | 30.5 | 30.7 |

### root TTFT p99 (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 0.05 | 0.05 | 0.05 |
| 0.1 | 0.05 | 0.05 | 0.05 | 0.07 |
| 0.2 | 0.05 | 0.19 | 0.12 | 0.34 |
| 0.3 | 0.06 | 0.28 | 0.23 | 1.18 |
| 0.4 | 0.08 | 0.29 | 0.29 | 4.51 |

### root TTFT p99 (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 0.05 | 0.05 | 0.05 |
| 0.1 | 0.05 | 0.05 | 0.05 | 0.06 |
| 0.2 | 0.05 | 0.06 | 0.06 | 0.06 |
| 0.3 | 0.06 | 0.06 | 0.06 | 0.07 |
| 0.4 | 0.08 | 0.07 | 0.07 | 0.10 |

### root TTFT p99 (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 0.05 | 0.05 | 0.05 |
| 0.1 | 0.05 | 0.05 | 0.05 | 0.05 |
| 0.2 | 0.05 | 0.06 | 0.06 | 0.06 |
| 0.3 | 0.06 | 0.06 | 0.06 | 0.06 |
| 0.4 | 0.08 | 0.07 | 0.07 | 0.07 |

### sub-call TTFT p99, claimed calls (s), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 0.29 | 0.29 | 0.34 |
| 0.1 | 0.05 | 0.30 | 0.30 | 0.36 |
| 0.2 | 0.06 | 0.30 | 0.31 | 0.48 |
| 0.3 | 0.06 | 0.31 | 0.37 | 1.20 |
| 0.4 | 0.07 | 0.40 | 0.39 | 4.72 |

### sub-call TTFT p99, claimed calls (s), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 3.47 | 3.46 | 3.75 |
| 0.1 | 0.05 | 4.05 | 4.07 | 4.44 |
| 0.2 | 0.06 | 4.82 | 4.57 | 7.14 |
| 0.3 | 0.06 | 5.12 | 5.69 | 13.50 |
| 0.4 | 0.07 | 6.70 | 6.31 | 29.25 |

### sub-call TTFT p99, claimed calls (s), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.04 | 1.24 | 1.24 | 1.23 |
| 0.1 | 0.05 | 1.89 | 1.80 | 1.89 |
| 0.2 | 0.06 | 2.28 | 2.33 | 2.28 |
| 0.3 | 0.06 | 3.08 | 3.37 | 3.08 |
| 0.4 | 0.07 | 3.52 | 3.81 | 3.52 |

### wasted share of model tokens, fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.461 |
| 0.3 | 0.000 | 0.000 | 0.000 | 0.453 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.439 |

### wasted share of model tokens, agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.464 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.463 |
| 0.3 | 0.000 | 0.000 | 0.000 | 0.456 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.440 |

### wasted share of model tokens, agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.1 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.2 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.3 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.4 | 0.000 | 0.000 | 0.000 | 0.000 |

### suppressed bets re-issued because they were needed, fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.3 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.3 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |

### suppressed bets re-issued because they were needed, agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0 | 0 | 0 | 0 |
| 0.1 | 0 | 0 | 0 | 0 |
| 0.2 | 0 | 0 | 0 | 0 |
| 0.3 | 0 | 0 | 0 | 0 |
| 0.4 | 0 | 0 | 0 | 0 |

### GPU busy fraction (not spare capacity), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.55 | 0.34 | 0.34 | 0.44 |
| 0.1 | 0.84 | 0.61 | 0.61 | 0.73 |
| 0.2 | 1.00 | 0.90 | 0.90 | 0.98 |
| 0.3 | 1.00 | 0.99 | 0.99 | 1.00 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.55 | 0.40 | 0.40 | 0.53 |
| 0.1 | 0.84 | 0.69 | 0.68 | 0.83 |
| 0.2 | 1.00 | 0.95 | 0.95 | 0.99 |
| 0.3 | 1.00 | 1.00 | 1.00 | 1.00 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 |

### GPU busy fraction (not spare capacity), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.55 | 0.36 | 0.36 | 0.36 |
| 0.1 | 0.84 | 0.63 | 0.63 | 0.63 |
| 0.2 | 1.00 | 0.92 | 0.92 | 0.92 |
| 0.3 | 1.00 | 0.99 | 0.99 | 0.99 |
| 0.4 | 1.00 | 1.00 | 1.00 | 1.00 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), fcfs

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.04 | 1.04 | 1.03 |
| 0.1 | 0.96 | 1.02 | 1.02 | 1.03 |
| 0.2 | 0.96 | 1.02 | 1.02 | 1.01 |
| 0.3 | 1.00 | 1.02 | 1.02 | 0.98 |
| 0.4 | 1.02 | 1.01 | 1.01 | 0.99 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent-naive

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.04 | 1.03 | 1.01 |
| 0.1 | 0.96 | 1.01 | 1.01 | 1.03 |
| 0.2 | 0.96 | 1.03 | 1.02 | 0.98 |
| 0.3 | 1.00 | 0.98 | 0.99 | 0.98 |
| 0.4 | 1.02 | 1.00 | 1.01 | 1.05 |

### drift: mean latency of last third / first third of sessions (>1.2: not a steady state), agent

| rate (sessions/s) | baseline | shadow | dataflow | shadow+waste1 |
|---|---|---|---|---|
| 0.05 | 0.99 | 1.04 | 1.04 | 1.04 |
| 0.1 | 0.96 | 1.01 | 1.01 | 1.01 |
| 0.2 | 0.96 | 1.04 | 1.03 | 1.04 |
| 0.3 | 1.00 | 1.01 | 1.00 | 1.01 |
| 0.4 | 1.02 | 1.00 | 1.00 | 1.00 |

### paired lat_p50: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.48 [0.48-0.50] | 1.04 |
| 0.1 | 0.48 [0.47-0.49] | 1.02 |
| 0.2 | 0.46 [0.45-0.46] | 1.02 |
| 0.3 | 0.45 [0.40-0.47] | 1.02 |
| 0.4 | 0.47 [0.42-0.50] | 1.01 |

### paired lat_p99: shadow, fcfs

| rate | shadow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.74 [0.55-0.83] | 1.04 |
| 0.1 | 0.61 [0.47-0.65] | 1.02 |
| 0.2 | 0.49 [0.38-0.51] | 1.02 |
| 0.3 | 0.43 [0.37-0.44] | 1.02 |
| 0.4 | 0.40 [0.37-0.42] | 1.01 |

### paired lat_p50: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.61 [0.60-0.63] | 1.04 |
| 0.1 | 0.63 [0.62-0.63] | 1.01 |
| 0.2 | 0.57 [0.57-0.58] | 1.03 |
| 0.3 | 0.53 [0.47-0.56] | 0.98 |
| 0.4 | 0.53 [0.48-0.56] | 1.00 |

### paired lat_p99: shadow, agent-naive

| rate | shadow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.77 [0.60-0.82] | 1.04 |
| 0.1 | 0.62 [0.52-0.68] | 1.01 |
| 0.2 | 0.52 [0.44-0.53] | 1.03 |
| 0.3 | 0.45 [0.39-0.46] | 0.98 |
| 0.4 | 0.43 [0.39-0.43] | 1.00 |

### paired lat_p50: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.51 [0.51-0.53] | 1.04 |
| 0.1 | 0.53 [0.51-0.54] | 1.01 |
| 0.2 | 0.50 [0.49-0.51] | 1.04 |
| 0.3 | 0.48 [0.42-0.50] | 1.01 |
| 0.4 | 0.47 [0.43-0.50] | 1.00 |

### paired lat_p99: shadow, agent

| rate | shadow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.76 [0.56-0.84] | 1.04 |
| 0.1 | 0.63 [0.49-0.67] | 1.01 |
| 0.2 | 0.50 [0.41-0.51] | 1.04 |
| 0.3 | 0.42 [0.36-0.45] | 1.01 |
| 0.4 | 0.40 [0.36-0.40] | 1.00 |

### paired lat_p50: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.48 [0.47-0.50] | 1.04 |
| 0.1 | 0.48 [0.47-0.49] | 1.02 |
| 0.2 | 0.46 [0.44-0.46] | 1.02 |
| 0.3 | 0.45 [0.40-0.47] | 1.02 |
| 0.4 | 0.47 [0.41-0.49] | 1.01 |

### paired lat_p99: dataflow, fcfs

| rate | dataflow (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.73 [0.55-0.83] | 1.04 |
| 0.1 | 0.61 [0.48-0.64] | 1.02 |
| 0.2 | 0.49 [0.38-0.51] | 1.02 |
| 0.3 | 0.44 [0.37-0.44] | 1.02 |
| 0.4 | 0.40 [0.36-0.42] | 1.01 |

### paired lat_p50: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.61 [0.60-0.63] | 1.03 |
| 0.1 | 0.62 [0.61-0.62] | 1.01 |
| 0.2 | 0.56 [0.55-0.57] | 1.02 |
| 0.3 | 0.53 [0.47-0.56] | 0.99 |
| 0.4 | 0.53 [0.47-0.55] | 1.01 |

### paired lat_p99: dataflow, agent-naive

| rate | dataflow (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.79 [0.61-0.82] | 1.03 |
| 0.1 | 0.62 [0.53-0.69] | 1.01 |
| 0.2 | 0.51 [0.44-0.52] | 1.02 |
| 0.3 | 0.45 [0.39-0.46] | 0.99 |
| 0.4 | 0.42 [0.39-0.43] | 1.01 |

### paired lat_p50: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.51 [0.51-0.53] | 1.04 |
| 0.1 | 0.53 [0.51-0.54] | 1.01 |
| 0.2 | 0.50 [0.49-0.51] | 1.03 |
| 0.3 | 0.47 [0.42-0.49] | 1.00 |
| 0.4 | 0.47 [0.42-0.49] | 1.00 |

### paired lat_p99: dataflow, agent

| rate | dataflow (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.76 [0.56-0.84] | 1.04 |
| 0.1 | 0.63 [0.49-0.66] | 1.01 |
| 0.2 | 0.50 [0.40-0.51] | 1.03 |
| 0.3 | 0.43 [0.36-0.44] | 1.00 |
| 0.4 | 0.40 [0.36-0.41] | 1.00 |

### paired lat_p50: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.68 [0.67-0.69] | 1.03 |
| 0.1 | 0.74 [0.74-0.76] | 1.03 |
| 0.2 | 0.73 [0.72-0.76] | 1.01 |
| 0.3 | 0.66 [0.60-0.70] | 0.98 |
| 0.4 | 0.67 [0.61-0.72] | 0.99 |

### paired lat_p99: shadow+waste1, fcfs

| rate | shadow+waste1 (fcfs) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.88 [0.68-0.88] | 1.03 |
| 0.1 | 0.71 [0.61-0.75] | 1.03 |
| 0.2 | 0.59 [0.56-0.61] | 1.01 |
| 0.3 | 0.53 [0.48-0.53] | 0.98 |
| 0.4 | 0.57 [0.54-0.59] | 0.99 |

### paired lat_p50: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.93 [0.89-0.93] | 1.01 |
| 0.1 | 1.02 [0.99-1.03] | 1.03 |
| 0.2 | 0.91 [0.88-0.99] | 0.98 |
| 0.3 | 0.79 [0.72-0.84] | 0.98 |
| 0.4 | 0.83 [0.73-0.98] | 1.05 |

### paired lat_p99: shadow+waste1, agent-naive

| rate | shadow+waste1 (agent-naive) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.94 [0.82-0.95] | 1.01 |
| 0.1 | 0.80 [0.78-0.81] | 1.03 |
| 0.2 | 0.68 [0.64-0.70] | 0.98 |
| 0.3 | 0.63 [0.59-0.65] | 0.98 |
| 0.4 | 0.71 [0.70-0.80] | 1.05 |

### paired lat_p50: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p50: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.51 [0.51-0.53] | 1.04 |
| 0.1 | 0.53 [0.51-0.54] | 1.01 |
| 0.2 | 0.50 [0.49-0.51] | 1.04 |
| 0.3 | 0.48 [0.42-0.50] | 1.01 |
| 0.4 | 0.47 [0.43-0.50] | 1.00 |

### paired lat_p99: shadow+waste1, agent

| rate | shadow+waste1 (agent) / no-speculation FCFS, lat_p99: median [min-max] over seeds | drift |
|---|---|---|
| 0.05 | 0.76 [0.56-0.84] | 1.04 |
| 0.1 | 0.63 [0.49-0.67] | 1.01 |
| 0.2 | 0.50 [0.41-0.51] | 1.04 |
| 0.3 | 0.42 [0.36-0.45] | 1.01 |
| 0.4 | 0.40 [0.36-0.40] | 1.00 |

## RTX 4090, Qwen3-4B: KV retention across tool gaps (`results/kv_rtx4090.csv`)

### p50 session latency (s)

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 40.8 | 40.8 | 41.4 |
| 0.02 | shadow | 16.6 | 16.6 | 17.2 |
| 0.02 | shadow+waste1 | 20.8 | 20.8 | 21.2 |
| 0.05 | baseline | 43.1 | 43.1 | 44.4 |
| 0.05 | shadow | 18.0 | 18.0 | 18.7 |
| 0.05 | shadow+waste1 | 23.8 | 23.8 | 25.1 |
| 0.08 | baseline | 45.6 | 45.6 | 48.2 |
| 0.08 | shadow | 20.0 | 20.0 | 21.3 |
| 0.08 | shadow+waste1 | 29.5 | 29.6 | 31.7 |
| 0.11 | baseline | 49.6 | 49.6 | 52.6 |
| 0.11 | shadow | 21.9 | 21.9 | 24.1 |
| 0.11 | shadow+waste1 | 38.0 | 38.1 | 41.0 |
| 0.14 | baseline | 54.4 | 54.4 | 59.3 |
| 0.14 | shadow | 24.8 | 24.8 | 27.2 |
| 0.14 | shadow+waste1 | 79.8 | 91.9 | 90.0 |

### p99 session latency (s)

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 56.8 | 56.8 | 58.0 |
| 0.02 | shadow | 32.1 | 32.1 | 34.0 |
| 0.02 | shadow+waste1 | 38.9 | 38.9 | 40.3 |
| 0.05 | baseline | 62.8 | 62.8 | 65.7 |
| 0.05 | shadow | 35.8 | 35.8 | 36.5 |
| 0.05 | shadow+waste1 | 48.0 | 48.1 | 49.5 |
| 0.08 | baseline | 73.1 | 73.1 | 78.0 |
| 0.08 | shadow | 36.8 | 36.8 | 39.1 |
| 0.08 | shadow+waste1 | 67.9 | 66.5 | 71.2 |
| 0.11 | baseline | 83.2 | 83.2 | 91.6 |
| 0.11 | shadow | 39.0 | 39.2 | 42.3 |
| 0.11 | shadow+waste1 | 89.3 | 89.9 | 96.0 |
| 0.14 | baseline | 96.7 | 96.7 | 107.1 |
| 0.14 | shadow | 49.3 | 49.1 | 53.3 |
| 0.14 | shadow+waste1 | 188.2 | 211.5 | 201.5 |

### root prefix-cache hit rate

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 0.68 | 0.68 | 0.00 |
| 0.02 | shadow | 0.68 | 0.68 | 0.00 |
| 0.02 | shadow+waste1 | 0.68 | 0.68 | 0.00 |
| 0.05 | baseline | 0.68 | 0.68 | 0.00 |
| 0.05 | shadow | 0.68 | 0.68 | 0.00 |
| 0.05 | shadow+waste1 | 0.66 | 0.66 | 0.00 |
| 0.08 | baseline | 0.68 | 0.68 | 0.00 |
| 0.08 | shadow | 0.67 | 0.68 | 0.00 |
| 0.08 | shadow+waste1 | 0.61 | 0.62 | 0.00 |
| 0.11 | baseline | 0.68 | 0.68 | 0.00 |
| 0.11 | shadow | 0.66 | 0.67 | 0.00 |
| 0.11 | shadow+waste1 | 0.51 | 0.53 | 0.00 |
| 0.14 | baseline | 0.65 | 0.65 | 0.00 |
| 0.14 | shadow | 0.63 | 0.64 | 0.00 |
| 0.14 | shadow+waste1 | 0.29 | 0.29 | 0.00 |

### root TTFT p99 (s)

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 0.22 | 0.22 | 0.28 |
| 0.02 | shadow | 0.47 | 0.47 | 0.80 |
| 0.02 | shadow+waste1 | 1.05 | 1.05 | 1.30 |
| 0.05 | baseline | 0.29 | 0.29 | 0.40 |
| 0.05 | shadow | 1.25 | 1.29 | 1.58 |
| 0.05 | shadow+waste1 | 2.06 | 2.06 | 1.92 |
| 0.08 | baseline | 0.31 | 0.31 | 0.43 |
| 0.08 | shadow | 1.85 | 1.85 | 1.99 |
| 0.08 | shadow+waste1 | 2.73 | 3.22 | 3.09 |
| 0.11 | baseline | 0.34 | 0.34 | 0.44 |
| 0.11 | shadow | 2.11 | 2.11 | 2.11 |
| 0.11 | shadow+waste1 | 8.36 | 8.45 | 9.22 |
| 0.14 | baseline | 0.36 | 0.36 | 0.48 |
| 0.14 | shadow | 2.13 | 2.30 | 2.32 |
| 0.14 | shadow+waste1 | 22.36 | 24.34 | 26.10 |

### preemptions

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 0 | 0 | 0 |
| 0.02 | shadow | 0 | 0 | 0 |
| 0.02 | shadow+waste1 | 0 | 0 | 0 |
| 0.05 | baseline | 0 | 0 | 0 |
| 0.05 | shadow | 0 | 0 | 0 |
| 0.05 | shadow+waste1 | 8 | 19 | 10 |
| 0.08 | baseline | 0 | 0 | 0 |
| 0.08 | shadow | 0 | 1 | 0 |
| 0.08 | shadow+waste1 | 62 | 66 | 76 |
| 0.11 | baseline | 0 | 0 | 0 |
| 0.11 | shadow | 2 | 9 | 5 |
| 0.11 | shadow+waste1 | 133 | 137 | 168 |
| 0.14 | baseline | 0 | 0 | 0 |
| 0.14 | shadow | 20 | 18 | 22 |
| 0.14 | shadow+waste1 | 524 | 658 | 606 |

### drift

| rate | policy | lru | pin (5 s TTL) | none |
|---|---|---|---|---|
| 0.02 | baseline | 0.98 | 0.98 | 0.98 |
| 0.02 | shadow | 1.00 | 1.00 | 1.01 |
| 0.02 | shadow+waste1 | 0.99 | 0.99 | 0.99 |
| 0.05 | baseline | 0.98 | 0.98 | 0.98 |
| 0.05 | shadow | 1.01 | 1.01 | 1.01 |
| 0.05 | shadow+waste1 | 0.98 | 0.98 | 0.98 |
| 0.08 | baseline | 0.96 | 0.96 | 0.96 |
| 0.08 | shadow | 0.99 | 0.99 | 1.00 |
| 0.08 | shadow+waste1 | 0.95 | 0.94 | 0.96 |
| 0.11 | baseline | 0.95 | 0.95 | 0.95 |
| 0.11 | shadow | 0.98 | 0.98 | 1.00 |
| 0.11 | shadow+waste1 | 0.90 | 0.89 | 0.89 |
| 0.14 | baseline | 0.94 | 0.94 | 0.94 |
| 0.14 | shadow | 0.95 | 0.96 | 0.96 |
| 0.14 | shadow+waste1 | 1.03 | 1.09 | 1.08 |
