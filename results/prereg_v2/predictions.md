# Pre-registered predictions for the second T4 run (v2)

**PREDICTED by the simulator, not measured.** Written 2026-10-20T02:11:35Z by `experiments/prereg_v2.py`, before any GPU run of `kaggle/sptc_kaggle_v2.ipynb`. The predictions were not changed after the run (wording about the working process and list formatting were edited for publication); the comparison is `experiments/prereg_compare.py`.

- Code: commit `3f835a4c246f9653a29abec231e3a41a73a69914` (clean tree).
- Calibration inputs (sha256 prefix): `calib.json` 39f63c8f847bfe13, `concur.json` 8b60689c1e32fa68, `suite.json` fd901aeba5f8002f, `load.json` 9da1efb1a4a1b992, `load_tagged.json` dea38b28c8413118, `vllm.log` 35f2870d53266671.
- Cost model from calib.json (solo decode, solo prefill at 3 lengths) and concur.json M3 (decode step vs concurrent decoders): experiments/t4_validate.fit_cost: t_fixed 1.90 ms, per sequence 0.436 ms, GEMM efficiency 0.32, attention efficiency 0.013. Server: KV 85,904 tokens (vllm.log), max_num_batched_tokens 2048, max_num_seqs 256.
- Tokens: suite.json no-speculation runs, per call by identity (sweep_predict.TableBackend); decoys forced to max_tokens.
- Fit on outcomes (all from the October 19 T4 run, none from the second run):
  - client overhead 30 ms each way: no-speculation suite medians of the October 19 run (suite.json).
  - P1 seq_cap 24: root TPOT p50 of the October 19 run's 18 load rows (load.json, load_tagged.json; 1/4/8 agents, stock and plugin fixed). P1's 1/4/8-agent points of those arms are in-sample.
- Sets: **P1 (primary)**, seq_cap 24; P0, no seq_cap; P1-alt, seq_cap 32 (the fit's runner-up, a sensitivity set).
- Plugin arms: `ServerConfig.plugin_semantics` with the arm's `prefill_allowance`; decoys tagged bet, spec-ptc dispatches early. `plugin-untagged/spec` is simulated as stock FCFS (the plugin schedules untagged traffic exactly as stock). Priority arms: `vllm-priority`, every speculative call at priority 1.
- Eager arms (`--enforce-eager`) have no calibration: only their ratios are predicted, equal to the compiled twins' ratios.
- One deterministic simulator run per point: no repeats, no CIs. vLLM's full-sequence admission check and CUDA-graph padding are not modeled in these (code-mode) predictions; the client's CPU is not modeled.
- For scoring this run these files replace `results/t4_run1_analysis/predictions.*` and `results/sweep_prep/predictions*` (kept as written). The model differs from the sweep predictions' in one way: plugin arms use `plugin_semantics` instead of the idealized agent policy (program-level order, promotion of claimed calls). Bets are then gated after the root is admitted, so more decoys are rejected at light load than those predicted. The C2 claims are unchanged.
- Known misses carried over: the simulator does not reproduce the October 19 1-agent plugin gap (3.10 vs 2.73 s, `results/t4_run1_analysis/root_cause.md`); before the seq_cap fit it over-predicted stock 8 agents with bad guesses (8.21 vs 6.62 s).

## seq_cap fit (root TPOT p50, 18 October 19 rows)

| seq_cap | mean abs log error |
|---|---|
| 8 | 0.0919 |
| 12 | 0.0690 |
| 16 | 0.0544 |
| 24 | 0.0465 |
| 32 | 0.0466 |
| 48 | 0.0582 |
| 64 | 0.0629 |
| 96 | 0.0679 |
| inf | 0.0684 |

## GPU minutes per preset (`vllm_bench.py plan`, P1 session times)

| preset | runs | launches | estimated minutes |
|---|---|---|---|
| ab | 98 | 8 | 101 |
| ab_eager | 20 | 4 | 33 |
| prio8 | 6 | 1 | 9 |
| core | 105 | 3 | 100 |
| full | 216 | 3 | 211 |

## What the simulator predicts, in short (P1)

- Without bad guesses, every plugin arm (fixed, adaptive, off, untagged) is within 0.6% of stock FCFS in session p50 at 1/4/8 agents, root TPOT within 0.6%. So the October 19 1-agent gap (+13.5% session p50) is not predicted: if it repeats, claims AB-1/AB-2 are refuted.
- The three allowance modes are within 0.6% of each other everywhere in the A/B (compiled and, as ratios, eager).
- With one bad guess per call the plugin's session p50 relative to stock FCFS is 0.86 at 1, 0.76 at 4, 0.75 at 8, 0.63 at 16, 0.55 at 24, 0.52 at 32; it rejects 78% of decoys at 1, 96% of decoys at 4, 100% of decoys at 8.
- vLLM priority scheduling is within 0.0% of FCFS with bad guesses at 8, 16 and 24 agents: it reorders only the waiting queue, and running bad guesses keep decoding next to the root streams.
- Stock speculation with bad guesses becomes a net loss at 24 agents; the plugin's never does in the ladder.

## B. Regression A/B (P1; P0 in brackets)

| arm | agents | session p50 s | root TPOT p50 ms | vs stock: session p50 | root TPOT p50 | decoys rejected | steps the allowance cut |
|---|---|---|---|---|---|---|---|
| fcfs/nospec | 1 | 6.62 [6.62] | 15.8 [15.8] | - | - | - | 0 of 1428 |
| fcfs/spec | 1 | 2.78 [2.78] | 17.0 [17.0] | - | - | - | 0 of 563 |
| fcfs/spec | 4 | 3.49 [3.49] | 21.4 [21.5] | - | - | - | 0 of 567 |
| fcfs/spec | 8 | 4.40 [4.61] | 26.8 [28.2] | - | - | - | 0 of 567 |
| fcfs/spec+bad | 1 | 3.37 [3.37] | 19.6 [19.6] | - | - | 0.00 | 0 of 566 |
| fcfs/spec+bad | 4 | 4.70 [5.39] | 28.5 [32.4] | - | - | 0.00 | 0 of 567 |
| fcfs/spec+bad | 8 | 5.81 [8.56] | 35.9 [51.0] | - | - | 0.00 | 0 of 567 |
| plugin/spec | 1 | 2.78 [2.78] | 17.0 [17.0] | 1.000 | 1.000 | - | 1 of 563 |
| plugin/spec | 4 | 3.48 [3.48] | 21.3 [21.4] | 0.997 | 0.997 | - | 4 of 567 |
| plugin/spec | 8 | 4.37 [4.58] | 26.6 [27.9] | 0.994 | 0.994 | - | 17 of 567 |
| plugin/spec+bad | 1 | 2.91 [2.91] | 17.6 [17.6] | 0.864 | 0.895 | 0.78 | 1 of 563 |
| plugin/spec+bad | 4 | 3.58 [3.59] | 21.8 [21.9] | 0.763 | 0.767 | 0.96 | 4 of 567 |
| plugin/spec+bad | 8 | 4.37 [4.58] | 26.6 [27.9] | 0.752 | 0.741 | 1.00 | 17 of 567 |
| plugin-untagged/spec | 1 | 2.78 [2.78] | 17.0 [17.0] | 1.000 | 1.000 | - | 0 of 563 |
| plugin-adaptive/spec | 1 | 2.78 [2.78] | 17.0 [17.0] | 1.000 | 1.000 | - | 1 of 563 |
| plugin-adaptive/spec | 4 | 3.48 [3.48] | 21.3 [21.4] | 0.997 | 0.997 | - | 4 of 567 |
| plugin-adaptive/spec | 8 | 4.37 [4.58] | 26.6 [27.9] | 0.994 | 0.994 | - | 17 of 567 |
| plugin-adaptive/spec+bad | 1 | 2.91 [2.91] | 17.6 [17.6] | 0.864 | 0.895 | 0.78 | 1 of 563 |
| plugin-adaptive/spec+bad | 4 | 3.58 [3.59] | 21.8 [21.9] | 0.763 | 0.767 | 0.96 | 4 of 567 |
| plugin-adaptive/spec+bad | 8 | 4.37 [4.58] | 26.6 [27.9] | 0.752 | 0.741 | 1.00 | 17 of 567 |
| plugin-off/spec | 1 | 2.78 [2.78] | 17.0 [17.0] | 1.000 | 1.000 | - | 0 of 563 |
| plugin-off/spec | 4 | 3.49 [3.49] | 21.4 [21.5] | 1.000 | 1.000 | - | 0 of 567 |
| plugin-off/spec | 8 | 4.40 [4.61] | 26.8 [28.2] | 1.000 | 1.000 | - | 0 of 567 |
| plugin-off/spec+bad | 1 | 2.91 [2.91] | 17.6 [17.6] | 0.864 | 0.895 | 0.78 | 0 of 563 |
| plugin-off/spec+bad | 4 | 3.59 [3.60] | 21.9 [22.0] | 0.765 | 0.769 | 0.96 | 0 of 567 |
| plugin-off/spec+bad | 8 | 4.40 [4.61] | 26.8 [28.2] | 0.757 | 0.745 | 1.00 | 0 of 567 |
| prio/spec | 8 | 4.40 [4.61] | 26.8 [28.2] | 1.000 | 1.000 | - | 0 of 567 |
| prio/spec+bad | 8 | 5.81 [8.56] | 35.9 [51.0] | 1.000 | 1.000 | 0.00 | 0 of 567 |

## C1. Saturation sweep (P1)

### Session p50 (s)

| agents | fcfs/nospec | fcfs/spec | fcfs/spec+bad | plugin/nospec | plugin/spec | plugin/spec+bad | prio/nospec | prio/spec | prio/spec+bad |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 6.62 | 2.78 | 3.37 | 6.62 | 2.78 | 2.91 | 6.62 | 2.78 | 3.37 |
| 2 | 6.81 | 3.02 | 3.89 | 6.81 | 3.02 | 3.06 | 6.81 | 3.02 | 3.89 |
| 4 | 7.14 | 3.49 | 4.70 | 7.14 | 3.48 | 3.58 | 7.14 | 3.49 | 4.70 |
| 8 | 7.89 | 4.40 | 5.81 | 7.89 | 4.37 | 4.37 | 7.89 | 4.40 | 5.81 |
| 12 | 8.83 | 5.00 | 7.19 | 8.83 | 4.98 | 4.98 | 8.83 | 5.00 | 7.19 |
| 16 | 9.74 | 5.55 | 8.76 | 9.74 | 5.52 | 5.52 | 9.74 | 5.55 | 8.76 |
| 24 | 11.70 | 6.64 | 11.93 | 11.70 | 6.60 | 6.60 | 11.70 | 6.64 | 11.93 |
| 32 | 12.53 | 7.70 | 14.57 | 12.53 | 7.65 | 7.65 | 12.53 | 7.70 | 14.55 |

### Root TPOT p50 (ms)

| agents | fcfs/nospec | fcfs/spec | fcfs/spec+bad | plugin/nospec | plugin/spec | plugin/spec+bad | prio/nospec | prio/spec | prio/spec+bad |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 15.8 | 17.0 | 19.6 | 15.8 | 17.0 | 17.6 | 15.8 | 17.0 | 19.6 |
| 2 | 16.3 | 18.6 | 24.3 | 16.3 | 18.5 | 19.3 | 16.3 | 18.6 | 24.3 |
| 4 | 17.1 | 21.4 | 28.5 | 17.1 | 21.3 | 21.8 | 17.1 | 21.4 | 28.5 |
| 8 | 19.0 | 26.8 | 35.9 | 19.0 | 26.6 | 26.6 | 19.0 | 26.8 | 35.9 |
| 12 | 21.1 | 30.7 | 44.5 | 21.1 | 30.4 | 30.4 | 21.1 | 30.7 | 44.5 |
| 16 | 23.6 | 34.4 | 53.6 | 23.6 | 34.1 | 34.1 | 23.6 | 34.4 | 53.6 |
| 24 | 28.1 | 41.1 | 71.1 | 28.1 | 40.5 | 40.5 | 28.1 | 41.1 | 71.1 |
| 32 | 30.1 | 47.6 | 77.9 | 30.1 | 46.6 | 46.6 | 30.1 | 47.6 | 78.7 |

### Sessions per minute

| agents | fcfs/nospec | fcfs/spec | fcfs/spec+bad | plugin/nospec | plugin/spec | plugin/spec+bad | prio/nospec | prio/spec | prio/spec+bad |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 9.5 | 25.2 | 21.6 | 9.5 | 25.2 | 24.3 | 9.5 | 25.2 | 21.6 |
| 2 | 18.4 | 46.1 | 36.1 | 18.4 | 46.2 | 44.6 | 18.4 | 46.1 | 36.1 |
| 4 | 35.1 | 79.5 | 59.2 | 35.1 | 79.7 | 77.6 | 35.1 | 79.5 | 59.2 |
| 8 | 63.4 | 126.5 | 95.6 | 63.4 | 127.3 | 127.3 | 63.4 | 126.5 | 95.6 |
| 12 | 84.9 | 166.0 | 116.7 | 84.9 | 167.1 | 167.1 | 84.9 | 166.0 | 116.7 |
| 16 | 102.4 | 198.8 | 128.5 | 102.4 | 199.9 | 199.9 | 102.4 | 198.8 | 128.5 |
| 24 | 127.1 | 251.3 | 140.7 | 127.1 | 253.3 | 253.3 | 127.1 | 251.3 | 140.7 |
| 32 | 155.8 | 291.5 | 136.3 | 155.8 | 293.9 | 293.9 | 155.8 | 291.5 | 138.8 |

### Goodput (SLO 2x / 2x)

| agents | fcfs/nospec | fcfs/spec | fcfs/spec+bad | plugin/nospec | plugin/spec | plugin/spec+bad | prio/nospec | prio/spec | prio/spec+bad |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 8 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| 12 | 1.00 | 0.62 | 0.00 | 1.00 | 0.69 | 0.69 | 1.00 | 0.62 | 0.00 |
| 16 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 |
| 24 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 |
| 32 | 0.88 | 0.00 | 0.00 | 0.88 | 0.00 | 0.00 | 0.88 | 0.00 | 0.00 |

### Derived answers (P1)

- knee_ref: {'fcfs/nospec': None, 'fcfs/spec': 16, 'fcfs/spec+bad': 12, 'plugin/nospec': None, 'plugin/spec': 24, 'plugin/spec+bad': 32, 'prio/nospec': None, 'prio/spec': 16, 'prio/spec+bad': 12}
- goodput < 0.5 first at: {'fcfs/nospec': None, 'fcfs/spec': 16, 'fcfs/spec+bad': 8, 'plugin/nospec': None, 'plugin/spec': 16, 'plugin/spec+bad': 16, 'prio/nospec': None, 'prio/spec': 16, 'prio/spec+bad': 8}
- spec+bad no faster than nospec first at: {'fcfs': 24, 'prio': 24, 'plugin': None}
- throughput peak in the ladder: {'fcfs/nospec': 32, 'fcfs/spec': 32, 'fcfs/spec+bad': 24, 'plugin/nospec': 32, 'plugin/spec': 32, 'plugin/spec+bad': 32, 'prio/nospec': 32, 'prio/spec': 32, 'prio/spec+bad': 24}

## C2. ReAct / background workload

`general_predictions.json`, regenerated by `experiments/general.py --kaggle-predict` on this code: identical cells to `results/general/predictions.json` (checked). 12 claims; the quick matrix carries claims [1, 3, 5].

| claim | predicted ratio | bound |
|---|---|---|
| 1. on stock vLLM, 3 next-call guesses slow 8 agents down | 1.627 | [1.3, None] |
| 2. on stock vLLM, 3 action candidates slow 8 agents down, less than next-call guesses | 1.134 | [1.05, None] |
| 3. vLLM priority (bets at 1) does not protect the agents: same as FCFS | 1.000 | [0.9, 1.1] |
| 4. vLLM priority, action candidates: same as FCFS | 1.000 | [0.9, 1.1] |
| 5. the plugin removes most of the slowdown at 8 agents (next3) | 0.714 | [None, 0.8] |
| 6. the plugin removes part of the smaller action-candidate slowdown at 8 agents | 0.919 | [None, 0.97] |
| 7. at 16 agents the plugin refuses almost every bet: same as no speculation | 1.000 | [0.9, 1.1] |
| 8. at 1 agent next-call guessing is a net win on these 3 sessions (plugin shown; 6 of 15 steps guessed right, more than the 27.8% average, so not a general light-load gain) | 0.806 | [None, 0.9] |
| 9. background jobs as bets protect the agents better than untagged jobs | 0.593 | [None, 0.75] |
| 10. background jobs at priority 1 are no better than untagged jobs | 0.981 | [0.9, 1.1] |
| 11. at 1 agent, action candidates under the plugin do not raise root TPOT (each candidate prefills only ~60-75 tokens, under the 512-token bet allowance) | 1.000 | [0.95, 1.05] |
| 12. at 1 agent with no bets the plugin does not raise root TPOT (a repeat of the earlier T4 run's untagged 1-agent row, measured 16.2 vs 15.7 ms; not a test of gap (1), which involved `early` tags) | 1.000 | [0.95, 1.05] |

## A. Scheduler overhead (a declared bound, not a simulator prediction)

| N running | variant | plugin policy work measured locally, p50 us | bound on added time per step, us |
|---|---|---|---|
| 8 | sptc-untagged | 3.3 | 30 |
| 8 | sptc-tagged | 7.5 | 43 |
| 32 | sptc-untagged | 13.1 | 59 |
| 32 | sptc-tagged | 25.2 | 96 |
| 64 | sptc-untagged | 26.0 | 98 |
| 64 | sptc-tagged | 48.8 | 166 |
| 128 | sptc-untagged | 51.3 | 174 |
| 128 | sptc-tagged | 97.2 | 312 |
| 256 | sptc-untagged | 104.7 | 334 |
| 256 | sptc-tagged | 200.8 | 623 |
| 512 | sptc-untagged | 206.5 | 639 |
| 512 | sptc-tagged | 376.4 | 1149 |

## Claims (P1 values; checked by `experiments/prereg_compare.py`)

| id | section | claim | predicted | tolerance |
|---|---|---|---|---|
| AB-1 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 1: session_p50 | 1.000 | 0.05 |
| AB-2 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| AB-3 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 4: session_p50 | 0.997 | 0.05 |
| AB-4 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 | 0.05 |
| AB-5 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 8: session_p50 | 0.994 | 0.05 |
| AB-6 | B: plugin vs stock, compiled | plugin/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 | 0.05 |
| AB-7 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 | 0.05 |
| AB-8 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 | 0.05 |
| AB-9 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 | 0.05 |
| AB-10 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 | 0.05 |
| AB-11 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 | 0.05 |
| AB-12 | B: plugin vs stock, compiled | plugin/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 | 0.05 |
| AB-13 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 1: session_p50 | 1.000 | 0.05 |
| AB-14 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| AB-15 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 4: session_p50 | 0.997 | 0.05 |
| AB-16 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 | 0.05 |
| AB-17 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 8: session_p50 | 0.994 | 0.05 |
| AB-18 | B: plugin vs stock, compiled | plugin-adaptive/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 | 0.05 |
| AB-19 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 | 0.05 |
| AB-20 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 | 0.05 |
| AB-21 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 | 0.05 |
| AB-22 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 | 0.05 |
| AB-23 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 | 0.05 |
| AB-24 | B: plugin vs stock, compiled | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 | 0.05 |
| AB-25 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 1: session_p50 | 1.000 | 0.05 |
| AB-26 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| AB-27 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 4: session_p50 | 1.000 | 0.05 |
| AB-28 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 4: root_tpot_p50 | 1.000 | 0.05 |
| AB-29 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 8: session_p50 | 1.000 | 0.05 |
| AB-30 | B: plugin vs stock, compiled | plugin-off/spec / fcfs/spec at 8: root_tpot_p50 | 1.000 | 0.05 |
| AB-31 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 | 0.05 |
| AB-32 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 | 0.05 |
| AB-33 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.765 | 0.05 |
| AB-34 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.769 | 0.05 |
| AB-35 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.757 | 0.05 |
| AB-36 | B: plugin vs stock, compiled | plugin-off/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.745 | 0.05 |
| UNT-1 | B: plugin server, untagged traffic | plugin-untagged/spec / fcfs/spec at 1: session_p50 | 1.000 | 0.05 |
| UNT-2 | B: plugin server, untagged traffic | plugin-untagged/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| EAG-1 | B: eager launches (relative only) | plugin-eager/spec / fcfs-eager/spec at 1: session_p50 | 1.000 | 0.05 |
| EAG-2 | B: eager launches (relative only) | plugin-eager/spec / fcfs-eager/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| EAG-3 | B: eager launches (relative only) | plugin-adaptive-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 | 0.05 |
| EAG-4 | B: eager launches (relative only) | plugin-adaptive-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| EAG-5 | B: eager launches (relative only) | plugin-off-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 | 0.05 |
| EAG-6 | B: eager launches (relative only) | plugin-off-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 | 0.05 |
| PRIO-1 | B/C1: vLLM priority vs FCFS | prio/spec / fcfs/spec at 8: session_p50 | 1.000 | 0.05 |
| PRIO-2 | B/C1: vLLM priority vs FCFS | prio/spec / fcfs/spec at 16: session_p50 | 1.000 | 0.05 |
| PRIO-3 | B/C1: vLLM priority vs FCFS | prio/spec / fcfs/spec at 24: session_p50 | 1.000 | 0.05 |
| PRIO-4 | B/C1: vLLM priority vs FCFS | prio/spec / fcfs/spec at 32: session_p50 | 1.000 | 0.05 |
| PRIO-5 | B/C1: vLLM priority vs FCFS | prio/spec+bad / fcfs/spec+bad at 8: session_p50 | 1.000 | 0.05 |
| PRIO-6 | B/C1: vLLM priority vs FCFS | prio/spec+bad / fcfs/spec+bad at 16: session_p50 | 1.000 | 0.05 |
| PRIO-7 | B/C1: vLLM priority vs FCFS | prio/spec+bad / fcfs/spec+bad at 24: session_p50 | 1.000 | 0.05 |
| PRIO-8 | B/C1: vLLM priority vs FCFS | prio/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.999 | 0.05 |
| PLG-1 | C1: plugin vs FCFS with bad guesses | plugin/spec+bad / fcfs/spec+bad at 16: session_p50 | 0.630 | 0.05 |
| PLG-2 | C1: plugin vs FCFS with bad guesses | plugin/spec+bad / fcfs/spec+bad at 24: session_p50 | 0.554 | 0.05 |
| PLG-3 | C1: plugin vs FCFS with bad guesses | plugin/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.525 | 0.05 |
| BAD-1 | C1: bad guesses under the plugin | plugin/spec+bad / plugin/spec at 8: session_p50 | 1.000 | 0.05 |
| BAD-2 | C1: bad guesses under the plugin | plugin/spec+bad / plugin/spec at 16: session_p50 | 1.000 | 0.05 |
| BAD-3 | C1: bad guesses under the plugin | plugin/spec+bad / plugin/spec at 24: session_p50 | 1.000 | 0.05 |
| BAD-4 | C1: bad guesses under the plugin | plugin/spec+bad / plugin/spec at 32: session_p50 | 1.000 | 0.05 |
| REJ-1 | B/C1: decoys rejected | plugin/spec+bad at 1: share of decoys rejected | 0.78 | 0.1 |
| REJ-2 | B/C1: decoys rejected | plugin/spec+bad at 4: share of decoys rejected | 0.96 | 0.1 |
| REJ-3 | B/C1: decoys rejected | plugin/spec+bad at 8: share of decoys rejected | 1.00 | 0.1 |
| REJ-4 | B/C1: decoys rejected | plugin/spec+bad at 16: share of decoys rejected | 1.00 | 0.1 |
| REJ-5 | B/C1: decoys rejected | plugin/spec+bad at 24: share of decoys rejected | 1.00 | 0.1 |
| REJ-6 | B/C1: decoys rejected | plugin/spec+bad at 32: share of decoys rejected | 1.00 | 0.1 |
| REJ-7 | B/C1: decoys rejected | plugin-adaptive/spec+bad at 1: share of decoys rejected | 0.78 | 0.1 |
| REJ-8 | B/C1: decoys rejected | plugin-adaptive/spec+bad at 4: share of decoys rejected | 0.96 | 0.1 |
| REJ-9 | B/C1: decoys rejected | plugin-adaptive/spec+bad at 8: share of decoys rejected | 1.00 | 0.1 |
| REJ-10 | B/C1: decoys rejected | plugin-off/spec+bad at 1: share of decoys rejected | 0.78 | 0.1 |
| REJ-11 | B/C1: decoys rejected | plugin-off/spec+bad at 4: share of decoys rejected | 0.96 | 0.1 |
| REJ-12 | B/C1: decoys rejected | plugin-off/spec+bad at 8: share of decoys rejected | 1.00 | 0.1 |
| THR-1 | C1: thresholds | knee_ref of fcfs/nospec | None | adjacent step |
| THR-2 | C1: thresholds | knee_ref of fcfs/spec | 16 | adjacent step |
| THR-3 | C1: thresholds | knee_ref of fcfs/spec+bad | 12 | adjacent step |
| THR-4 | C1: thresholds | knee_ref of plugin/nospec | None | adjacent step |
| THR-5 | C1: thresholds | knee_ref of plugin/spec | 24 | adjacent step |
| THR-6 | C1: thresholds | knee_ref of plugin/spec+bad | 32 | adjacent step |
| THR-7 | C1: thresholds | knee_ref of prio/nospec | None | adjacent step |
| THR-8 | C1: thresholds | knee_ref of prio/spec | 16 | adjacent step |
| THR-9 | C1: thresholds | knee_ref of prio/spec+bad | 12 | adjacent step |
| THR-10 | C1: thresholds | good50 of fcfs/nospec | None | adjacent step |
| THR-11 | C1: thresholds | good50 of fcfs/spec | 16 | adjacent step |
| THR-12 | C1: thresholds | good50 of fcfs/spec+bad | 8 | adjacent step |
| THR-13 | C1: thresholds | good50 of plugin/nospec | None | adjacent step |
| THR-14 | C1: thresholds | good50 of plugin/spec | 16 | adjacent step |
| THR-15 | C1: thresholds | good50 of plugin/spec+bad | 16 | adjacent step |
| THR-16 | C1: thresholds | good50 of prio/nospec | None | adjacent step |
| THR-17 | C1: thresholds | good50 of prio/spec | 16 | adjacent step |
| THR-18 | C1: thresholds | good50 of prio/spec+bad | 8 | adjacent step |
| THR-19 | C1: thresholds | net_loss of fcfs | 24 | adjacent step |
| THR-20 | C1: thresholds | net_loss of prio | 24 | adjacent step |
| THR-21 | C1: thresholds | net_loss of plugin | None | adjacent step |

## Scoring rules (fixed now)

- validity. A measured point counts only if every run has status ok and its row's cpu_ok is true (whole-host CPU < 0.85 mean, < 10% of seconds >= 95% busy). Otherwise every claim using it is 'invalid'.
- ratio. measured ratio m of two measured points vs predicted p: supported if |m - p| <= tol; refuted if |m - p| > tol and the numerator's 95% CI does not overlap p x the denominator's 95% CI (both from vllm_bench.summarize's bootstrap); otherwise unresolved. Eager ratios use eager points only.
- fraction. measured share of decoys logged 'rejected' vs predicted: supported if within tol (absolute), otherwise refuted.
- threshold. a predicted knee_ref / good50 / net_loss load is right if the measured one is the same ladder step or the adjacent one; a prediction above the ladder (None) is right if no measured load reaches it. Scored on the presets that ran; a threshold beyond the loads measured is 'unchecked'.
- overhead. plugin total p50 minus stock total p50 (same N, same scheduling, sync and async), from overhead_bench.py vllm: supported if <= bound_added_us.
- general. experiments/general.py's claims (results/general/predictions.json, regenerated identically): supported if the measured ratio is inside the bound.
- points. for every measured (arm, load), |log(predicted / measured)| of session p50 and root TPOT p50 for P1, P0 and P1-alt: median and max, P1's in-sample points (1/4/8 agents of fcfs/* and plugin/*) apart from the rest. Not pass/fail.
