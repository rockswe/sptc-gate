# results/general, re-run on the corrected simulator (simulated)

**Simulated, not measured.** `results/general` was computed before the October 20 KV
fixes (`results/corrections/corrections.md`: resume from the prefix cache, one LRU free
queue; `GeneralServer` already had full-sequence admission) and was not re-run then. This
directory is that re-run. `results/general` itself is left as it was, so its
`general.md` text still matches its own tables.

- Code: the corrected simulator, run from a clean copy of the tree.
- Command, per workload (react, branch, batchlong, batch) and config (t4, h100, moe):
  `experiments/general.py --workload W --config C --procs 2`, then `--report`.
- Sizes as before: default rates, `max(60, 40 x rate)` sessions, seeds 0-2. Cells are
  means over seeds, as in `results/general`.
- Files: the per-run CSVs, `summary.csv`, `verdict.csv` and the generated `tables.md`.
  `general.md`, `predictions.json` and the figures were not regenerated.

## What moved (session p50, mean over seeds; old → corrected)

| cell | old | corrected |
|---|---|---|
| ReAct H100 4B, 3 guesses, stock FCFS vs no speculation, 4 / 6 / 8 per s | +46% / +84% / +109% | +46% / +91% / +119% |
| same, 1 guess | +3% / +18% / +32% | +3% / +18% / +37% |
| same, plugin vs no speculation (1 or 3 guesses, 4-8/s) | within 0.4% | within 0.4% |
| same, wasted share of tokens, FCFS → plugin | 20-58% → 0.3-5% | 19-58% → 0.3-5% |
| ReAct T4, 3 guesses, plugin vs no speculation, 0.05-0.3/s | +3% to +28% | +3% to +28% |
| same, plugin vs FCFS from 0.1/s | 7-80% faster | 8-81% faster |
| ReAct T4, 1 guess, plugin vs no speculation from 0.15/s | +5% to +12% | +5% to +12% |
| ReAct T4, 3 guesses, priority vs FCFS, 0.1 / 0.15 / 0.2 per s | 0.0% / +0.3% / +1.5% | +0.9% / +5.8% / -3.2% |
| ReAct MoE, action candidates, stock FCFS vs no speculation, 0.5-3.5/s | 4-10% faster | 4-10% faster |
| same, plugin vs FCFS | 4-9% slower | 4-9% slower |
| branch, plugin vs FCFS (H100 0.5-4/s, MoE all rates, T4 0.1-0.15/s) | 6-31% slower | 6-31% slower |
| long background jobs, T4 0.05/s, interactive p50: FCFS / priority 1 / bet, window 8 | 1,173 / 126 / 40.9 s | 1,087 / 126 / 41.3 s |
| same, bets refused per run | 50,444 | 50,300 |

- The FCFS cells under load get worse (more speculation cost on stock); the plugin cells
  barely move. Conclusions in the README hold; the quoted ranges change at
  their upper ends.
- The T4 priority cells with 3 guesses now differ from FCFS by up to 5.8% at 0.1-0.2/s,
  where stock FCFS is already 32-266% slower than no speculation. Elsewhere (H100, MoE,
  branch, other T4 cells) priority stays within ±0.3% of FCFS except at the top rate of
  each ladder.
- Old and corrected values per cell: compare `verdict.csv` here with
  `results/general/verdict.csv`.
