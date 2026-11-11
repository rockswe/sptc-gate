| concurrency | NIM ITL (ms) | model (ms) | error |
|---|---|---|---|
| 1 | 6.52 | 6.49 | -0.4% |
| 25 | 9.34 | 8.74 | -6.5% |
| 50 | 11.46 | 11.07 | -3.4% |
| 100 | 15.99 | 15.74 | -1.6% |
| 200 | 25.68 | 25.08 | -2.3% |

MoE anchor (arXiv 2609.12923, vLLM 0.16, H100 NVL, Qwen3-30B-A3B; t_fixed fit on the first row only; the paper's batch-32 figure is 'per-token time', read here as step/B):

| point | measured (ms) | model (ms) | error |
|---|---|---|---|
| batch 1, 16k ctx (fit) | 5.32 | 5.27 | -0.9% |
| batch 32, 8k ctx (check) | 30.72 | 28.72 | -6.5% |
