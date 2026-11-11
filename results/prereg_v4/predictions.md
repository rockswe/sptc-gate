# Pre-registered predictions for the pressure run (v4)

**PREDICTED by the simulator, not measured.** Written 2026-10-29T15:14:56Z by `experiments/prereg_v4.py`, before any GPU run of the pressure preset. The predictions were not changed after the run (wording about the working process and list formatting were edited for publication); `experiments/prereg_compare.py --prereg results/prereg_v4 --also ''` scores it.

- Code: commit `9b0e51d65b6c5d4168669777ea6199a2773b74d9` (clean tree).
- T4 config (chosen): `--num-gpu-blocks-override 257 --max-num-seqs 256 --max-model-len 512` (0.75x peak (256 blocks), 256 seqs). The fallback, used only if the probe shows no pressure: `--num-gpu-blocks-override 129 --max-num-seqs 256 --max-model-len 512`.
- Chosen by experiments/pressure.choose_config, stock FCFS arms only (fcfs-p/spec+bad's simulated KV peak on the default server: 341 blocks); same as `results/pressure/choice.json`.
- Calibration: prereg_v3's, not refit (its files match their prereg commit 2e39a4d: {'predictions.json': 'match', 'predictions.md': 'match', 'general_predictions.json': 'match'}). Sets: **P1 (primary)**, seq_cap P1 24, P0 inf, P1-alt 32.
- One deterministic simulator run per point: no repeats, no CIs. The client's CPU is not modelled.

## Arms

| arm | server | tags | client cap | workload | simulator |
|---|---|---|---|---|---|
| fcfs-p/nospec | fcfs_p | none | - | - | fcfs |
| fcfs-p/spec | fcfs_p | none | - | - | fcfs |
| fcfs-p/spec+bad | fcfs_p | none | - | decoys | fcfs, bets: decoys |
| prio-p/spec+bad | priority_p | priority_bets | - | decoys | vllm-priority, bets: decoys |
| cap-p/spec+bad | fcfs_p | none | window:8 | decoys | fcfs, bets: decoys, proxy bets decoys |
| plugin-p/spec+bad | plugin_p | sptc_bets | - | decoys | agent + plugin_semantics, bets: decoys |
| prio-p/both | priority_p | priority_bets | - | both | vllm-priority, bets: every speculative call |
| cap-p/both | fcfs_p | none | window:8 | both | fcfs, bets: every speculative call, proxy bets spec |
| plugin-p/both | plugin_p | sptc_bets | - | both | agent + plugin_semantics, bets: every speculative call |

Every arm: only bets tagged (tag_early False), a decoy started by its real call (decoy_at_call), and a forced refused bet stops the shadow (rejected_force abort).

## Probe

Before the main sweep: one launch of the fcfs_p server on the chosen config, then fcfs-p/spec and fcfs-p/spec+bad at 4 agents, once each. If fcfs-p/spec+bad shows neither a preemption (vllm:num_preemptions) nor a queue (vllm:num_requests_waiting > 0 in any 1-second sample), the sweep runs on the fallback config and is scored against results/prereg_v4_fallback; otherwise on the chosen config, scored against results/prereg_v4. The predicted probe values are each set's `pressure` rows.

| arm | preemptions | max waiting | KV peak (share) | queue (time) |
|---|---|---|---|---|
| fcfs-p/spec | 0 | 0 | 0.55 | 0% |
| fcfs-p/spec+bad | 57 | 20 | 1.00 | 20% |

## The decision (simulated)

The rule: the plugin wins if its session p50 is at least 5% below the cap's at 4 agents, in either workload (plugin-p/spec+bad vs cap-p/spec+bad, or plugin-p/both vs cap-p/both), with the pressure check passed. Decided on the measured values, not on these claims' verdicts. Each set's `d1` is the simulated answer.

| workload | plugin vs cap | plugin vs priority |
|---|---|---|
| decoys | 0.988 | 0.750 |
| both | 1.000 | 1.444 |

Simulated: **the plugin does not win**. P0 / P1-alt: P0 0.990 / 1.000; P1-alt 0.990 / 1.000 (plugin vs cap, decoys / both).

## Rows (P1; P0 in brackets)

| arm | session p50 s | vs fcfs-p/spec+bad | root TPOT p50 ms | decoys rejected | real bets refused | preemptions | bets dropped | max waiting | KV peak blocks |
|---|---|---|---|---|---|---|---|---|---|
| fcfs-p/nospec | 7.14 [7.14] | 1.464 | 17.1 [17.1] | - | - | 0 | 0 | 0 | 35 |
| fcfs-p/spec | 3.49 [3.49] | 0.715 | 21.4 [21.5] | - | - | 0 | 0 | 0 | 140 |
| fcfs-p/spec+bad | 4.88 [5.56] | 1.000 | 29.2 [32.3] | 0.00 | - | 57 | 0 | 20 | 256 |
| prio-p/spec+bad | 4.79 [5.52] | 0.982 | 29.1 [32.5] | 0.00 | - | 53 | 0 | 21 | 256 |
| cap-p/spec+bad | 3.64 [3.64] | 0.745 | 22.2 [22.3] | 0.94 | - | 0 | 0 | 0 | 148 |
| plugin-p/spec+bad | 3.59 [3.60] | 0.737 | 21.9 [22.0] | 0.96 | - | 0 | 0 | 0 | 140 |
| prio-p/both | 4.78 [5.53] | 0.979 | 29.0 [32.5] | 0.00 | 0.00 | 44 | 0 | 23 | 256 |
| cap-p/both | 6.90 [6.90] | 1.413 | 18.2 [18.2] | 0.79 | 0.85 | 0 | 0 | 0 | 57 |
| plugin-p/both | 6.90 [6.90] | 1.413 | 18.3 [18.3] | 0.77 | 0.81 | 0 | 0 | 0 | 60 |

## Claims (P1 predicted; P0, P1-alt in brackets)

| id | section | claim | predicted | tol |
|---|---|---|---|---|
| PR-1 | each arm vs fcfs-p/spec+bad | fcfs-p/nospec / fcfs-p/spec+bad at 4: session_p50 | 1.464 [1.284, 1.364] | 0.05 |
| PR-2 | each arm vs fcfs-p/spec+bad | fcfs-p/nospec / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.586 [0.530, 0.553] | 0.05 |
| PR-3 | each arm vs fcfs-p/spec+bad | fcfs-p/spec / fcfs-p/spec+bad at 4: session_p50 | 0.715 [0.627, 0.666] | 0.05 |
| PR-4 | each arm vs fcfs-p/spec+bad | fcfs-p/spec / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.731 [0.665, 0.693] | 0.05 |
| PR-5 | each arm vs fcfs-p/spec+bad | prio-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.982 [0.993, 0.981] | 0.05 |
| PR-6 | each arm vs fcfs-p/spec+bad | prio-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.994 [1.003, 0.999] | 0.05 |
| PR-7 | each arm vs fcfs-p/spec+bad | cap-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.745 [0.654, 0.695] | 0.05 |
| PR-8 | each arm vs fcfs-p/spec+bad | cap-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.761 [0.689, 0.719] | 0.05 |
| PR-9 | each arm vs fcfs-p/spec+bad | plugin-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.737 [0.647, 0.688] | 0.05 |
| PR-10 | each arm vs fcfs-p/spec+bad | plugin-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.749 [0.681, 0.711] | 0.05 |
| PR-11 | each arm vs fcfs-p/spec+bad | prio-p/both / fcfs-p/spec+bad at 4: session_p50 | 0.979 [0.993, 0.980] | 0.05 |
| PR-12 | each arm vs fcfs-p/spec+bad | prio-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.991 [1.005, 1.000] | 0.05 |
| PR-13 | each arm vs fcfs-p/spec+bad | cap-p/both / fcfs-p/spec+bad at 4: session_p50 | 1.413 [1.240, 1.317] | 0.05 |
| PR-14 | each arm vs fcfs-p/spec+bad | cap-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.622 [0.563, 0.587] | 0.05 |
| PR-15 | each arm vs fcfs-p/spec+bad | plugin-p/both / fcfs-p/spec+bad at 4: session_p50 | 1.413 [1.240, 1.317] | 0.05 |
| PR-16 | each arm vs fcfs-p/spec+bad | plugin-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.626 [0.566, 0.591] | 0.05 |
| PC-1 | plugin vs the client-side cap (the decision rule's ratio) | plugin-p/spec+bad / cap-p/spec+bad at 4: session_p50 | 0.988 [0.990, 0.990] | 0.05 |
| PC-2 | plugin vs the client-side cap (the decision rule's ratio) | plugin-p/spec+bad / cap-p/spec+bad at 4: root_tpot_p50 | 0.985 [0.988, 0.988] | 0.05 |
| PC-3 | plugin vs the client-side cap (the decision rule's ratio) | plugin-p/both / cap-p/both at 4: session_p50 | 1.000 [1.000, 1.000] | 0.05 |
| PC-4 | plugin vs the client-side cap (the decision rule's ratio) | plugin-p/both / cap-p/both at 4: root_tpot_p50 | 1.006 [1.006, 1.006] | 0.05 |
| PP-1 | plugin vs vLLM priority | plugin-p/spec+bad / prio-p/spec+bad at 4: session_p50 | 0.750 [0.652, 0.701] | 0.05 |
| PP-2 | plugin vs vLLM priority | plugin-p/both / prio-p/both at 4: session_p50 | 1.444 [1.248, 1.344] | 0.05 |
| PF-1 | decoys rejected | cap-p/spec+bad at 4: share of decoys rejected | 0.944 [0.944, 0.944] | 0.1 |
| PF-2 | decoys rejected | plugin-p/spec+bad at 4: share of decoys rejected | 0.961 [0.961, 0.961] | 0.1 |
| PF-3 | decoys rejected | cap-p/both at 4: share of decoys rejected | 0.794 [0.794, 0.794] | 0.1 |
| PF-4 | decoys rejected | plugin-p/both at 4: share of decoys rejected | 0.768 [0.768, 0.768] | 0.1 |

## Rules (v3's, unchanged)

- validity. A measured point counts only if every run has status ok and its row's cpu_ok is true (whole-host CPU < 0.85 mean, < 10% of seconds >= 95% busy). Otherwise every claim using it is 'invalid'.
- ratio. measured ratio m of two measured points vs predicted p: supported if |m - p| <= tol; refuted if |m - p| > tol and the numerator's 95% CI does not overlap p x the denominator's 95% CI (both from vllm_bench.summarize's bootstrap); otherwise unresolved. Eager ratios use eager points only.
- fraction. measured share of decoys logged 'rejected' vs predicted: supported if within tol (absolute), otherwise refuted.
- points. for every measured (arm, load), |log(predicted / measured)| of session p50 and root TPOT p50 for P1, P0 and P1-alt: median and max, P1's in-sample points (1/4/8 agents of fcfs/* and plugin/*) apart from the rest. Not pass/fail.
- pressure. Claims PR, PC, PP use v3's ratio rule and PF v3's fraction rule (decoys logged rejected, which includes a bet dropped before its first token). The denominators are fcfs-p/spec+bad (PR), cap (PC) and priority (PP), all at 4 agents on the same config. No point here is in-sample for P1: its seq_cap was fit on the October 19 rows, none of them a pressure arm.

## How to read these (fixed before the run)

- Pooled p50s sit on pattern clusters. The 16 sessions of a run are 4 of each mix4 pattern, and patterns differ by up to 3x in session time. The pooled p50 is the lowest session of the third-fastest pattern, so a small change in one pattern can move it a lot. Read every session_p50 claim with `prereg_compare.py`'s per-pattern ratios (geometric mean over patterns).
- Why cap and plugin lose in `both`. In mix4 the shadow forces nearly every speculation, and spec-ptc's shadow stops for the rest of the turn when it forces a refused bet (shadow.py _abort('force-failed')). The window of 8 refuses most real bets at 4 agents, so these arms run close to no speculation: the claims predict cap-p/both and plugin-p/both well above fcfs-p/spec+bad (PR) and the plugin well above priority (PP-2). Simulated with the shadow re-running a refused call instead, the loss would be far smaller (results/pressure README, sensitivity 'reissue').
- What the claims cannot show. PC-1..4 test the decision rule's ratios, but the rule is applied to the measured values. A claim refuted in the plugin's favour can still leave the rule unmet, and the reverse.
- The sim's KV model under heavy preemption is unchecked (a known risk): the probe values (preemptions, queue, KV peak) are predictions too, not inputs.

## GPU time (estimate)

27 runs on 6 launches, about 54 min with `vllm_bench.plan`'s constants (warm passes and one cache-filling launch included; the probe not).
