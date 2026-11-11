# Measured vs pre-registered (prereg_v4_fallback)

Predictions: commit `9b0e51d65b`, written 2026-10-29T15:14:59Z. Measured runs found: 45. Verdicts follow the rules in `results/prereg_v4_fallback/predictions.md`; 'not run' means the cell was not measured.

Prediction files vs the prereg commit (sha256): predictions.json match, predictions.md match.

- Simulator claims (P1): refuted 8, supported 14, unresolved 4
- Ratio claims, strict (launch-level CI, added before the run): refuted 6, supported 5, unresolved 11
- Scheduler overhead bounds: none
- General workload claims (not run; one run per cell, indicative): none

## Claims

'verdict' is the pre-registered rule: a ratio is supported when its point estimate is within the tolerance, however wide its CI. That alone does not show equivalence (for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, resampling server launches, then runs, then sessions, inside predicted +- tol (supported) or outside it (refuted), with >= 2 launches per side (launches: numerator/denominator). Read a ratio as shown only where both agree. 'work': sub-call tokens per session, numerator over denominator (not a verdict); away from 1 by more than the tolerance, the two sides did not run the same workload.

| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches | work | validity |
|---|---|---|---|---|---|---|---|
| PR-1 | fcfs-p/nospec / fcfs-p/spec+bad at 4: session_p50 | 1.023 (1.013, 1.013) | 1.641 | refuted | refuted [1.085, 2.082] 2/2 | 0.919 | ok, ok |
| PR-2 | fcfs-p/nospec / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.668 (0.661, 0.661) | 0.633 | supported | supported [0.628, 0.649] 2/2 | 0.919 | ok, ok |
| PR-3 | fcfs-p/spec / fcfs-p/spec+bad at 4: session_p50 | 0.499 (0.494, 0.494) | 0.667 | refuted | unresolved [0.528, 0.764] 2/2 | 1.009 | ok, ok |
| PR-4 | fcfs-p/spec / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.835 (0.829, 0.829) | 0.773 | refuted | unresolved [0.753, 0.793] 2/2 | 1.009 | ok, ok |
| PR-5 | prio-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.690 (0.692, 0.692) | 0.870 | unresolved | unresolved [0.713, 1.021] 2/2 | 1.002 | ok, ok |
| PR-6 | prio-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 1.072 (1.066, 1.066) | 1.022 | unresolved | unresolved [0.991, 1.054] 2/2 | 1.002 | ok, ok |
| PR-7 | cap-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.521 (0.516, 0.516) | 0.689 | unresolved | unresolved [0.541, 0.786] 2/2 | 1.008 | ok, ok |
| PR-8 | cap-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.868 (0.859, 0.859) | 0.794 | refuted | refuted [0.774, 0.816] 2/2 | 1.008 | ok, ok |
| PR-9 | plugin-p/spec+bad / fcfs-p/spec+bad at 4: session_p50 | 0.515 (0.511, 0.511) | 0.676 | unresolved | unresolved [0.525, 0.774] 2/2 | 1.000 | ok, ok |
| PR-10 | plugin-p/spec+bad / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.858 (0.849, 0.849) | 0.782 | refuted | refuted [0.763, 0.807] 2/2 | 1.000 | ok, ok |
| PR-11 | prio-p/both / fcfs-p/spec+bad at 4: session_p50 | 0.907 (0.911, 0.911) | 0.915 | supported | unresolved [0.775, 1.236] 2/2 | 1.000 | ok, ok |
| PR-12 | prio-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 1.017 (1.019, 1.019) | 1.005 | supported | unresolved [0.965, 1.040] 2/2 | 1.000 | ok, ok |
| PR-13 | cap-p/both / fcfs-p/spec+bad at 4: session_p50 | 0.988 (0.978, 0.978) | 1.505 | refuted | refuted [1.182, 2.262] 2/2 | 1.000 | ok, ok |
| PR-14 | cap-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.710 (0.702, 0.702) | 0.680 | supported | supported [0.673, 0.699] 2/2 | 1.000 | ok, ok |
| PR-15 | plugin-p/both / fcfs-p/spec+bad at 4: session_p50 | 0.988 (0.978, 0.978) | 1.506 | refuted | refuted [1.202, 2.272] 2/2 | 1.000 | ok, ok |
| PR-16 | plugin-p/both / fcfs-p/spec+bad at 4: root_tpot_p50 | 0.714 (0.706, 0.706) | 0.682 | supported | supported [0.671, 0.701] 2/2 | 1.000 | ok, ok |
| PC-1 | plugin-p/spec+bad / cap-p/spec+bad at 4: session_p50 | 0.989 (0.990, 0.990) | 0.982 | supported | unresolved [0.835, 1.157] 2/2 | 0.992 | ok, ok |
| PC-2 | plugin-p/spec+bad / cap-p/spec+bad at 4: root_tpot_p50 | 0.988 (0.988, 0.988) | 0.985 | supported | supported [0.960, 1.017] 2/2 | 0.992 | ok, ok |
| PC-3 | plugin-p/both / cap-p/both at 4: session_p50 | 1.000 (1.000, 1.000) | 1.000 | supported | unresolved [0.662, 1.512] 2/2 | 1.000 | ok, ok |
| PC-4 | plugin-p/both / cap-p/both at 4: root_tpot_p50 | 1.006 (1.006, 1.006) | 1.002 | supported | supported [0.987, 1.012] 2/2 | 1.000 | ok, ok |
| PP-1 | plugin-p/spec+bad / prio-p/spec+bad at 4: session_p50 | 0.747 (0.737, 0.738) | 0.778 | supported | unresolved [0.646, 0.863] 2/2 | 0.998 | ok, ok |
| PP-2 | plugin-p/both / prio-p/both at 4: session_p50 | 1.089 (1.073, 1.074) | 1.646 | refuted | refuted [1.188, 2.334] 2/2 | 1.000 | ok, ok |
| PF-1 | cap-p/spec+bad at 4: decoys rejected | 0.94 (0.94, 0.94) | 0.95 | supported | - | - | ok |
| PF-2 | plugin-p/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.97 | supported | - | - | ok |
| PF-3 | cap-p/both at 4: decoys rejected | 0.79 (0.79, 0.79) | 0.85 | supported | - | - | ok |
| PF-4 | plugin-p/both at 4: decoys rejected | 0.77 (0.77, 0.77) | 0.83 | supported | - | - | ok |

## Per-pattern ratios (secondary; session_p50 claims)

Median session wall per pattern, numerator over denominator: the same deterministic workload on both sides. The pooled p50 above can jump between pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.

| id | predicted | pooled | map16 | map_reduce | side_branch_chain | two_stage | geo mean |
|---|---|---|---|---|---|---|---|
| PR-1 | 1.023 | 1.641 | 1.141 | 1.260 | 1.236 | 1.807 | 1.339 |
| PR-3 | 0.499 | 0.667 | 0.365 | 0.684 | 0.700 | 0.616 | 0.573 |
| PR-5 | 0.690 | 0.870 | 0.512 | 0.924 | 0.946 | 0.844 | 0.784 |
| PR-7 | 0.521 | 0.689 | 0.376 | 0.709 | 0.718 | 0.629 | 0.589 |
| PR-9 | 0.515 | 0.676 | 0.374 | 0.704 | 0.712 | 0.622 | 0.584 |
| PR-11 | 0.907 | 0.915 | 0.981 | 1.018 | 1.049 | 0.924 | 0.992 |
| PR-13 | 0.988 | 1.505 | 1.442 | 1.333 | 1.030 | 2.186 | 1.442 |
| PR-15 | 0.988 | 1.506 | 1.479 | 1.355 | 1.089 | 2.195 | 1.479 |
| PC-1 | 0.989 | 0.982 | 0.994 | 0.992 | 0.991 | 0.988 | 0.991 |
| PC-3 | 1.000 | 1.000 | 1.026 | 1.016 | 1.058 | 1.004 | 1.026 |
| PP-1 | 0.747 | 0.778 | 0.730 | 0.762 | 0.752 | 0.737 | 0.745 |
| PP-2 | 1.089 | 1.646 | 1.507 | 1.330 | 1.039 | 2.375 | 1.491 |

## Point accuracy (|log(pred / meas)|; not pass/fail)

| set | part | metric | points | median | max |
|---|---|---|---|---|---|
| P1 | out_of_sample | session_p50 | 9 | 0.144 | 0.320 |
| P1 | out_of_sample | root_tpot_p50 | 9 | 0.101 | 0.150 |
| P0 | out_of_sample | session_p50 | 9 | 0.159 | 0.320 |
| P0 | out_of_sample | root_tpot_p50 | 9 | 0.096 | 0.138 |
| P1-alt | out_of_sample | session_p50 | 9 | 0.159 | 0.320 |
| P1-alt | out_of_sample | root_tpot_p50 | 9 | 0.096 | 0.138 |

## Launch-to-launch spread (same arm and load, different server launches)

| arm | agents | launches | session p50 per launch | spread |
|---|---|---|---|---|
| cap-d/both | 4 | fcfs#2, fcfs#3 | 12.24, 8.97 | 36.5% |
| cap-p/both | 4 | fcfs_p#2, fcfs_p#3 | 12.01, 9.02 | 33.2% |
| cap-p/spec+bad | 4 | fcfs_p#2, fcfs_p#3 | 4.15, 4.13 | 0.6% |
| fcfs-d/nospec | 4 | fcfs#2, fcfs#3 | 10.05, 9.81 | 2.4% |
| fcfs-d/spec | 4 | fcfs#2, fcfs#3 | 3.95, 3.94 | 0.4% |
| fcfs-d/spec+bad | 4 | fcfs#2, fcfs#3 | 5.04, 5.06 | 0.5% |
| fcfs-p/nospec | 4 | fcfs_p#2, fcfs_p#3 | 10.16, 9.83 | 3.3% |
| fcfs-p/spec | 4 | fcfs_p#2, fcfs_p#3 | 4.00, 4.04 | 1.0% |
| fcfs-p/spec+bad | 4 | fcfs_p#2, fcfs_p#3 | 6.08, 5.99 | 1.5% |
| plugin-d/both | 4 | plugin#1, plugin#2 | 12.08, 8.90 | 35.8% |
| plugin-p/both | 4 | plugin_p#1, plugin_p#2 | 12.05, 9.02 | 33.6% |
| plugin-p/spec+bad | 4 | plugin_p#1, plugin_p#2 | 4.05, 4.05 | 0.0% |
| prio-d/both | 4 | priority#1, priority#2 | 5.07, 5.06 | 0.2% |
| prio-p/both | 4 | priority_p#1, priority_p#2 | 5.48, 5.62 | 2.5% |
| prio-p/spec+bad | 4 | priority_p#1, priority_p#2 | 5.28, 5.15 | 2.4% |

## Server launches (compile state)

A fresh compile saves an artifact (AOT saved); a cached launch loads one (AOT loaded). Launches that ran the same code show the same artifact path in one of the two columns. Role cache_fill: compiled fresh, stopped unmeasured.

| launch | status | role | startup s | eager | fresh | AOT saved | AOT loaded | GPU C / SM MHz | plugin line |
|---|---|---|---|---|---|---|---|---|---|
| fcfs_p#1 | up | cache_fill | 184.1 | False | True | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | - | 68 / 585 | - |
| fcfs_p#2 | up | measure | 94.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 72 / 585 | - |
| priority_p#1 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 74 / 585 | - |
| plugin_p#1 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| plugin_p#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| priority_p#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 75 / 585 | - |
| fcfs_p#3 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/68b9d1291464f3341e4177d3dbebdc1305c64f4951b28ec43b916b6e4a1bd5ce/rank_0_0/model | 75 / 585 | - |
| fcfs#1 | up | cache_fill | 128.0 | False | True | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | - | 65 / 585 | - |
| fcfs#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 68 / 585 | - |
| priority#1 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 74 / 585 | - |
| plugin#1 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| plugin#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| priority#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 74 / 585 | - |
| fcfs#3 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | - |

## Scheduler overhead (added time per step vs stock)

| N | variant | scheduling | added us | bound us | verdict |
|---|---|---|---|---|---|

## General workload claims

One run per cell and one server launch per arm (fcfs, priority, plugin in that order): no CI, no launch-to-launch noise floor. Single-run, indicative verdicts.

| claim | predicted | bound | measured | verdict |
|---|---|---|---|---|


# Measured vs pre-registered (prereg_v4b) (also reported)

Predictions: commit `696c206252`, written 2026-10-29T16:08:47Z. Measured runs found: 45. Verdicts follow the rules in `results/prereg_v4b/predictions.md`; 'not run' means the cell was not measured.

Prediction files vs the prereg commit (sha256): predictions.json match, predictions.md match.

- Simulator claims (P1): supported 11, unresolved 4
- Ratio claims, strict (launch-level CI, added before the run): refuted 1, supported 3, unresolved 9
- Scheduler overhead bounds: none
- General workload claims (not run; one run per cell, indicative): none

## Claims

'verdict' is the pre-registered rule: a ratio is supported when its point estimate is within the tolerance, however wide its CI. That alone does not show equivalence (for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, resampling server launches, then runs, then sessions, inside predicted +- tol (supported) or outside it (refuted), with >= 2 launches per side (launches: numerator/denominator). Read a ratio as shown only where both agree. 'work': sub-call tokens per session, numerator over denominator (not a verdict); away from 1 by more than the tolerance, the two sides did not run the same workload.

| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches | work | validity |
|---|---|---|---|---|---|---|---|
| DB-1 | fcfs-d/nospec / fcfs-d/spec+bad at 4: session_p50 | 1.521 (1.325, 1.429) | 1.947 | unresolved | unresolved [1.355, 2.478] 2/2 | 0.919 | ok, ok |
| DB-2 | fcfs-d/nospec / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.601 (0.529, 0.570) | 0.629 | supported | supported [0.610, 0.651] 2/2 | 0.919 | ok, ok |
| DB-3 | fcfs-d/spec / fcfs-d/spec+bad at 4: session_p50 | 0.743 (0.647, 0.698) | 0.782 | supported | unresolved [0.625, 0.854] 2/2 | 1.000 | ok, ok |
| DB-4 | fcfs-d/spec / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.750 (0.664, 0.714) | 0.759 | supported | supported [0.730, 0.786] 2/2 | 1.000 | ok, ok |
| DB-5 | prio-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.000 (1.000, 1.000) | 1.004 | supported | unresolved [0.870, 1.153] 2/2 | 1.002 | ok, ok |
| DB-6 | prio-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.000 | supported | unresolved [0.961, 1.051] 2/2 | 1.002 | ok, ok |
| DB-7 | cap-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.469 (1.279, 1.380) | 1.780 | unresolved | unresolved [1.455, 2.584] 2/2 | 1.000 | ok, ok |
| DB-8 | cap-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.639 (0.562, 0.605) | 0.675 | supported | unresolved [0.655, 0.699] 2/2 | 1.000 | ok, ok |
| DB-9 | plugin-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.469 (1.279, 1.380) | 1.766 | unresolved | refuted [1.532, 2.548] 2/2 | 1.000 | ok, ok |
| DB-10 | plugin-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.642 (0.565, 0.609) | 0.677 | supported | unresolved [0.656, 0.702] 2/2 | 1.000 | ok, ok |
| DC-1 | plugin-d/both / cap-d/both at 4: session_p50 | 1.000 (1.000, 1.000) | 0.992 | supported | unresolved [0.682, 1.509] 2/2 | 1.000 | ok, ok |
| DC-2 | plugin-d/both / cap-d/both at 4: root_tpot_p50 | 1.006 (1.006, 1.006) | 1.003 | supported | supported [0.987, 1.018] 2/2 | 1.000 | ok, ok |
| DP-1 | plugin-d/both / prio-d/both at 4: session_p50 | 1.469 (1.279, 1.380) | 1.758 | unresolved | unresolved [1.496, 2.561] 2/2 | 0.998 | ok, ok |
| DF-1 | cap-d/both at 4: decoys rejected | 0.79 (0.79, 0.79) | 0.86 | supported | - | - | ok |
| DF-2 | plugin-d/both at 4: decoys rejected | 0.77 (0.77, 0.77) | 0.83 | supported | - | - | ok |

## Per-pattern ratios (secondary; session_p50 claims)

Median session wall per pattern, numerator over denominator: the same deterministic workload on both sides. The pooled p50 above can jump between pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.

| id | predicted | pooled | map16 | map_reduce | side_branch_chain | two_stage | geo mean |
|---|---|---|---|---|---|---|---|
| DB-1 | 1.521 | 1.947 | 2.452 | 1.356 | 1.377 | 2.156 | 1.773 |
| DB-3 | 0.743 | 0.782 | 0.785 | 0.738 | 0.774 | 0.721 | 0.754 |
| DB-5 | 1.000 | 1.004 | 1.012 | 0.993 | 1.001 | 1.002 | 1.002 |
| DB-7 | 1.469 | 1.780 | 3.149 | 1.437 | 1.137 | 2.623 | 1.917 |
| DB-9 | 1.469 | 1.766 | 3.188 | 1.514 | 1.057 | 2.606 | 1.909 |
| DC-1 | 1.000 | 0.992 | 1.012 | 1.053 | 0.929 | 0.993 | 0.996 |
| DP-1 | 1.469 | 1.758 | 3.150 | 1.524 | 1.055 | 2.600 | 1.905 |
