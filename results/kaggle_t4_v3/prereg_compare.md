# Measured vs pre-registered (prereg_v3)

Predictions: commit `3ded06ba89`, written 2026-10-20T05:40:28Z. Measured runs found: 226. Verdicts follow the rules in `results/prereg_v3/predictions.md`; 'not run' means the cell was not measured.

Prediction files vs the prereg commit (sha256): predictions.json match, predictions.md match, general_predictions.json match.

- Simulator claims (P1): invalid 19, not run 11, refuted 8, supported 74, unchecked 8, unresolved 2
- Ratio claims, strict (launch-level CI, added before the run): supported 21, unresolved 42
- Scheduler overhead bounds: supported 24
- General workload claims (general_quick/general.json; one run per cell, indicative): not run 9, supported 3

## Claims

'verdict' is the pre-registered rule: a ratio is supported when its point estimate is within the tolerance, however wide its CI. That alone does not show equivalence (for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, resampling server launches, then runs, then sessions, inside predicted +- tol (supported) or outside it (refuted), with >= 2 launches per side (launches: numerator/denominator). Read a ratio as shown only where both agree. 'work': sub-call tokens per session, numerator over denominator (not a verdict); away from 1 by more than the tolerance, the two sides did not run the same workload.

| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches | work | validity |
|---|---|---|---|---|---|---|---|
| AB-1 | plugin/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.012 | supported | unresolved [0.857, 1.187] 2/2 | 0.989 | ok, ok |
| AB-2 | plugin/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.002 | supported | unresolved [0.846, 1.178] 2/2 | 0.989 | ok, ok |
| AB-3 | plugin/spec / fcfs/spec at 4: session_p50 | 0.997 (0.997, 0.997) | 1.000 | supported | unresolved [0.854, 1.170] 2/2 | 0.998 | ok, ok |
| AB-4 | plugin/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 (0.994, 0.995) | 0.997 | supported | supported [0.966, 1.035] 2/2 | 0.998 | ok, ok |
| AB-5 | plugin/spec / fcfs/spec at 8: session_p50 | 0.994 (0.993, 0.995) | 1.001 | supported | unresolved [0.805, 1.234] 2/2 | 0.999 | ok, ok |
| AB-6 | plugin/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | 1.002 | supported | supported [0.978, 1.017] 2/2 | 0.999 | ok, ok |
| AB-7 | plugin/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.904 | supported | unresolved [0.876, 1.037] 2/2 | 0.999 | ok, ok |
| AB-8 | plugin/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.978 | unresolved | unresolved [0.867, 1.140] 2/2 | 0.999 | ok, ok |
| AB-9 | plugin/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 (0.666, 0.719) | 0.749 | supported | unresolved [0.637, 0.859] 2/2 | 0.998 | ok, ok |
| AB-10 | plugin/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 (0.676, 0.728) | 0.770 | supported | supported [0.738, 0.810] 2/2 | 0.998 | ok, ok |
| AB-11 | plugin/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 (0.535, 0.713) | 0.695 | refuted | unresolved [0.667, 0.726] 2/2 | 0.993 | ok, ok |
| AB-12 | plugin/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 (0.547, 0.709) | 0.728 | supported | supported [0.707, 0.739] 2/2 | 0.993 | ok, ok |
| AB-13 | plugin-adaptive/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.019 | supported | unresolved [0.836, 1.186] 2/2 | 0.989 | ok, ok |
| AB-14 | plugin-adaptive/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.992 | supported | unresolved [0.852, 1.184] 2/2 | 0.989 | ok, ok |
| AB-15 | plugin-adaptive/spec / fcfs/spec at 4: session_p50 | 0.997 (0.997, 0.997) | 0.999 | supported | unresolved [0.852, 1.170] 2/2 | 0.997 | ok, ok |
| AB-16 | plugin-adaptive/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 (0.994, 0.995) | 0.994 | supported | supported [0.967, 1.036] 2/2 | 0.997 | ok, ok |
| AB-17 | plugin-adaptive/spec / fcfs/spec at 8: session_p50 | 0.994 (0.993, 0.995) | - | invalid | - | - | invalid: host CPU saturated, ok |
| AB-18 | plugin-adaptive/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | - | invalid | - | - | invalid: host CPU saturated, ok |
| AB-19 | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.884 | supported | unresolved [0.817, 1.014] 2/2 | 0.999 | ok, ok |
| AB-20 | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.942 | supported | unresolved [0.858, 1.119] 2/2 | 0.999 | ok, ok |
| AB-21 | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 (0.666, 0.719) | 0.746 | supported | unresolved [0.637, 0.856] 2/2 | 0.999 | ok, ok |
| AB-22 | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 (0.676, 0.728) | 0.769 | supported | supported [0.738, 0.809] 2/2 | 0.999 | ok, ok |
| AB-23 | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 (0.535, 0.713) | 0.691 | refuted | unresolved [0.673, 0.722] 2/2 | 0.993 | ok, ok |
| AB-24 | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 (0.547, 0.709) | 0.725 | supported | supported [0.705, 0.737] 2/2 | 0.993 | ok, ok |
| AB-25 | plugin-off/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.017 | supported | unresolved [0.839, 1.195] 2/2 | 0.989 | ok, ok |
| AB-26 | plugin-off/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.006 | supported | unresolved [0.862, 1.204] 2/2 | 0.989 | ok, ok |
| AB-27 | plugin-off/spec / fcfs/spec at 4: session_p50 | 1.000 (1.000, 1.000) | 1.000 | supported | unresolved [0.858, 1.170] 2/2 | 0.999 | ok, ok |
| AB-28 | plugin-off/spec / fcfs/spec at 4: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.992 | supported | supported [0.968, 1.036] 2/2 | 0.999 | ok, ok |
| AB-29 | plugin-off/spec / fcfs/spec at 8: session_p50 | 1.000 (1.000, 1.000) | 1.002 | supported | unresolved [0.810, 1.236] 2/2 | 1.001 | ok, ok |
| AB-30 | plugin-off/spec / fcfs/spec at 8: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.007 | supported | supported [0.986, 1.019] 2/2 | 1.001 | ok, ok |
| AB-31 | plugin-off/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.882 | supported | unresolved [0.819, 1.087] 2/2 | 0.999 | ok, ok |
| AB-32 | plugin-off/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.960 | unresolved | unresolved [0.858, 1.113] 2/2 | 0.999 | ok, ok |
| AB-33 | plugin-off/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.765 (0.668, 0.721) | 0.745 | supported | unresolved [0.636, 0.854] 2/2 | 0.999 | ok, ok |
| AB-34 | plugin-off/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.769 (0.680, 0.733) | 0.769 | supported | supported [0.733, 0.809] 2/2 | 0.999 | ok, ok |
| AB-35 | plugin-off/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.757 (0.539, 0.717) | 0.688 | refuted | unresolved [0.668, 0.719] 2/2 | 0.990 | ok, ok |
| AB-36 | plugin-off/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.745 (0.554, 0.717) | 0.720 | supported | supported [0.702, 0.733] 2/2 | 0.990 | ok, ok |
| UNT-1 | plugin-untagged/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 0.997 | supported | unresolved [0.931, 1.160] 2/2 | 0.977 | ok, ok |
| UNT-2 | plugin-untagged/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.998 | supported | unresolved [0.837, 1.164] 2/2 | 0.977 | ok, ok |
| EAG-1 | plugin-eager/spec / fcfs-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.004 | supported | unresolved [0.799, 1.267] 2/2 | 1.000 | ok, ok |
| EAG-2 | plugin-eager/spec / fcfs-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.999 | supported | supported [0.982, 1.024] 2/2 | 1.000 | ok, ok |
| EAG-3 | plugin-adaptive-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.006 | supported | unresolved [0.793, 1.236] 2/2 | 1.000 | ok, ok |
| EAG-4 | plugin-adaptive-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.991 | supported | supported [0.975, 1.005] 2/2 | 1.000 | ok, ok |
| EAG-5 | plugin-off-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.001 | supported | unresolved [0.789, 1.234] 2/2 | 1.000 | ok, ok |
| EAG-6 | plugin-off-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.984 | supported | supported [0.968, 0.997] 2/2 | 1.000 | ok, ok |
| PRIO-1 | prio/spec / fcfs/spec at 8: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, ok |
| PRIO-2 | prio/spec / fcfs/spec at 16: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-3 | prio/spec / fcfs/spec at 24: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-4 | prio/spec / fcfs/spec at 32: session_p50 | 1.000 (1.000, 1.000) | - | not run | - | - | missing, missing |
| PRIO-5 | prio/spec+bad / fcfs/spec+bad at 8: session_p50 | 1.000 (1.000, 1.000) | 0.989 | supported | unresolved [0.944, 1.058] 2/2 | 0.998 | ok, ok |
| PRIO-6 | prio/spec+bad / fcfs/spec+bad at 16: session_p50 | 1.000 (1.000, 1.000) | 1.005 | supported | unresolved [0.956, 1.040] 1/1 | 1.000 | ok, ok |
| PRIO-7 | prio/spec+bad / fcfs/spec+bad at 24: session_p50 | 1.000 (1.001, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-8 | prio/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.999 (1.014, 0.996) | - | not run | - | - | missing, missing |
| PLG-1 | plugin/spec+bad / fcfs/spec+bad at 16: session_p50 | 0.630 (0.437, 0.634) | - | invalid | - | - | invalid: host CPU saturated, ok |
| PLG-2 | plugin/spec+bad / fcfs/spec+bad at 24: session_p50 | 0.554 (0.401, 0.569) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PLG-3 | plugin/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.525 (0.407, 0.537) | - | not run | - | - | missing, missing |
| BAD-1 | plugin/spec+bad / plugin/spec at 8: session_p50 | 1.000 (1.000, 1.000) | 1.029 | supported | unresolved [0.981, 1.271] 2/2 | 1.069 | ok, ok |
| BAD-2 | plugin/spec+bad / plugin/spec at 16: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| BAD-3 | plugin/spec+bad / plugin/spec at 24: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| BAD-4 | plugin/spec+bad / plugin/spec at 32: session_p50 | 1.000 (1.000, 1.000) | - | not run | - | - | missing, missing |
| REJ-1 | plugin/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.61 | refuted | - | - | ok |
| REJ-2 | plugin/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-3 | plugin/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| REJ-4 | plugin/spec+bad at 16: decoys rejected | 1.00 (1.00, 1.00) | - | invalid | - | - | invalid: host CPU saturated |
| REJ-5 | plugin/spec+bad at 24: decoys rejected | 1.00 (1.00, 1.00) | - | invalid | - | - | invalid: host CPU saturated |
| REJ-6 | plugin/spec+bad at 32: decoys rejected | 1.00 (1.00, 1.00) | - | not run | - | - | missing |
| REJ-7 | plugin-adaptive/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.66 | refuted | - | - | ok |
| REJ-8 | plugin-adaptive/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-9 | plugin-adaptive/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| REJ-10 | plugin-off/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.67 | refuted | - | - | ok |
| REJ-11 | plugin-off/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-12 | plugin-off/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| THR-1 | knee_ref of fcfs/nospec | None (32, 32) | None | unchecked | - | - | - |
| THR-2 | knee_ref of fcfs/spec | 16 (12, 16) | 24 | supported | - | - | - |
| THR-3 | knee_ref of fcfs/spec+bad | 12 (8, 12) | 16 | supported | - | - | - |
| THR-4 | knee_ref of plugin/nospec | None (32, 32) | - | not run | - | - | - |
| THR-5 | knee_ref of plugin/spec | 24 (12, 16) | 24 | supported | - | - | - |
| THR-6 | knee_ref of plugin/spec+bad | 32 (16, 24) | None | unchecked | - | - | - |
| THR-7 | knee_ref of prio/nospec | None (32, 32) | - | not run | - | - | - |
| THR-8 | knee_ref of prio/spec | 16 (12, 16) | 24 | supported | - | - | - |
| THR-9 | knee_ref of prio/spec+bad | 12 (8, 12) | 16 | supported | - | - | - |
| THR-10 | good50 of fcfs/nospec | None (32, 32) | None | unchecked | - | - | - |
| THR-11 | good50 of fcfs/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-12 | good50 of fcfs/spec+bad | 8 (4, 8) | 16 | refuted | - | - | - |
| THR-13 | good50 of plugin/nospec | None (32, 32) | - | not run | - | - | - |
| THR-14 | good50 of plugin/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-15 | good50 of plugin/spec+bad | 16 (12, 12) | None | unchecked | - | - | - |
| THR-16 | good50 of prio/nospec | None (32, 32) | - | not run | - | - | - |
| THR-17 | good50 of prio/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-18 | good50 of prio/spec+bad | 8 (4, 8) | 16 | refuted | - | - | - |
| THR-19 | net_loss of fcfs | 24 (8, 24) | None | unchecked | - | - | - |
| THR-20 | net_loss of prio | 24 (8, 24) | - | not run | - | - | - |
| THR-21 | net_loss of plugin | None (None, None) | - | not run | - | - | - |
| B4-1 | proxy/spec+bad / fcfs-b4/spec+bad at 4: session_p50 | 0.778 (0.680, 0.731) | 0.807 | supported | unresolved [0.648, 0.876] 2/2 | 1.000 | ok, ok |
| B4-2 | proxy/spec+bad / fcfs-b4/spec+bad at 4: root_tpot_p50 | 0.785 (0.692, 0.744) | 0.779 | supported | supported [0.751, 0.806] 2/2 | 1.000 | ok, ok |
| B4-3 | proxy/spec+bad / fcfs-b4/spec+bad at 8: session_p50 | 0.757 (0.539, 0.717) | 0.714 | supported | unresolved [0.636, 0.787] 2/2 | 1.013 | ok, ok |
| B4-4 | proxy/spec+bad / fcfs-b4/spec+bad at 8: root_tpot_p50 | 0.745 (0.554, 0.717) | 0.717 | supported | supported [0.697, 0.740] 2/2 | 1.013 | ok, ok |
| B4-5 | proxy-sem/spec+bad / fcfs-b4/spec+bad at 4: session_p50 | 0.840 (0.740, 0.796) | 0.883 | supported | unresolved [0.731, 0.973] 2/2 | 0.999 | ok, ok |
| B4-6 | proxy-sem/spec+bad / fcfs-b4/spec+bad at 4: root_tpot_p50 | 0.845 (0.749, 0.806) | 0.853 | supported | supported [0.828, 0.880] 2/2 | 0.999 | ok, ok |
| B4-7 | proxy-sem/spec+bad / fcfs-b4/spec+bad at 8: session_p50 | 0.806 (0.599, 0.781) | 0.810 | supported | unresolved [0.674, 0.884] 2/2 | 1.005 | ok, ok |
| B4-8 | proxy-sem/spec+bad / fcfs-b4/spec+bad at 8: root_tpot_p50 | 0.798 (0.613, 0.777) | 0.796 | supported | supported [0.777, 0.824] 2/2 | 1.005 | ok, ok |
| B4-9 | prio-bets/spec+bad / fcfs-b4/spec+bad at 4: session_p50 | 1.000 (1.000, 1.000) | 0.996 | supported | unresolved [0.861, 1.150] 2/2 | 1.001 | ok, ok |
| B4-10 | prio-bets/spec+bad / fcfs-b4/spec+bad at 4: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.999 | supported | supported [0.956, 1.029] 2/2 | 1.001 | ok, ok |
| B4-11 | prio-bets/spec+bad / fcfs-b4/spec+bad at 8: session_p50 | 1.000 (0.999, 1.000) | 1.006 | supported | unresolved [0.909, 1.099] 2/2 | 1.005 | ok, ok |
| B4-12 | prio-bets/spec+bad / fcfs-b4/spec+bad at 8: root_tpot_p50 | 1.000 (0.999, 1.000) | 0.994 | supported | unresolved [0.947, 1.038] 2/2 | 1.005 | ok, ok |
| B4-13 | plugin-b4/spec+bad / fcfs-b4/spec+bad at 4: session_p50 | 0.763 (0.666, 0.719) | 0.780 | supported | unresolved [0.645, 0.871] 2/2 | 1.000 | ok, ok |
| B4-14 | plugin-b4/spec+bad / fcfs-b4/spec+bad at 4: root_tpot_p50 | 0.767 (0.676, 0.728) | 0.763 | supported | supported [0.738, 0.802] 2/2 | 1.000 | ok, ok |
| B4-15 | plugin-b4/spec+bad / fcfs-b4/spec+bad at 8: session_p50 | 0.752 (0.535, 0.713) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4-16 | plugin-b4/spec+bad / fcfs-b4/spec+bad at 8: root_tpot_p50 | 0.741 (0.547, 0.709) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4P-1 | plugin-b4/spec+bad / proxy/spec+bad at 4: session_p50 | 0.981 (0.979, 0.983) | 0.967 | supported | unresolved [0.847, 1.168] 2/2 | 1.000 | ok, ok |
| B4P-2 | plugin-b4/spec+bad / proxy/spec+bad at 4: root_tpot_p50 | 0.977 (0.977, 0.979) | 0.980 | supported | unresolved [0.947, 1.031] 2/2 | 1.000 | ok, ok |
| B4P-3 | plugin-b4/spec+bad / proxy/spec+bad at 8: session_p50 | 0.994 (0.993, 0.995) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4P-4 | plugin-b4/spec+bad / proxy/spec+bad at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4P-5 | plugin-b4/spec+bad / proxy-sem/spec+bad at 4: session_p50 | 0.909 (0.900, 0.903) | 0.884 | supported | unresolved [0.762, 1.037] 2/2 | 1.001 | ok, ok |
| B4P-6 | plugin-b4/spec+bad / proxy-sem/spec+bad at 4: root_tpot_p50 | 0.908 (0.902, 0.903) | 0.895 | supported | supported [0.875, 0.938] 2/2 | 1.001 | ok, ok |
| B4P-7 | plugin-b4/spec+bad / proxy-sem/spec+bad at 8: session_p50 | 0.933 (0.893, 0.913) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4P-8 | plugin-b4/spec+bad / proxy-sem/spec+bad at 8: root_tpot_p50 | 0.928 (0.892, 0.913) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4R-1 | proxy/spec+bad at 4: decoys rejected | 0.92 (0.92, 0.92) | 0.95 | supported | - | - | ok |
| B4R-2 | proxy/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| B4R-3 | proxy-sem/spec+bad at 4: decoys rejected | 0.72 (0.72, 0.72) | 0.68 | supported | - | - | ok |
| B4R-4 | proxy-sem/spec+bad at 8: decoys rejected | 0.86 (0.86, 0.86) | 0.82 | supported | - | - | ok |
| B4R-5 | plugin-b4/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| B4R-6 | plugin-b4/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | - | invalid | - | - | invalid: host CPU saturated |

## Per-pattern ratios (secondary; session_p50 claims)

Median session wall per pattern, numerator over denominator: the same deterministic workload on both sides. The pooled p50 above can jump between pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.

| id | predicted | pooled | map16 | map_reduce | side_branch_chain | two_stage | geo mean |
|---|---|---|---|---|---|---|---|
| AB-1 | 1.000 | 1.012 | 1.007 | 0.996 | 0.999 | 0.980 | 0.995 |
| AB-3 | 0.997 | 1.000 | 1.002 | 0.997 | 1.000 | 1.006 | 1.001 |
| AB-5 | 0.994 | 1.001 | 1.001 | 0.999 | 1.002 | 0.991 | 0.998 |
| AB-7 | 0.864 | 0.904 | 0.941 | 0.920 | 1.020 | 0.888 | 0.941 |
| AB-9 | 0.763 | 0.749 | 0.808 | 0.748 | 0.787 | 0.760 | 0.776 |
| AB-11 | 0.752 | 0.695 | 0.746 | 0.690 | 0.729 | 0.703 | 0.717 |
| AB-13 | 1.000 | 1.019 | 1.044 | 0.994 | 1.001 | 1.006 | 1.011 |
| AB-15 | 0.997 | 0.999 | 1.007 | 0.999 | 1.000 | 1.010 | 1.004 |
| AB-19 | 0.864 | 0.884 | 0.913 | 0.901 | 1.011 | 0.856 | 0.919 |
| AB-21 | 0.763 | 0.746 | 0.807 | 0.748 | 0.788 | 0.760 | 0.775 |
| AB-23 | 0.752 | 0.691 | 0.740 | 0.689 | 0.732 | 0.705 | 0.716 |
| AB-25 | 1.000 | 1.017 | 1.046 | 1.010 | 0.998 | 1.011 | 1.016 |
| AB-27 | 1.000 | 1.000 | 1.015 | 0.999 | 1.002 | 0.981 | 0.999 |
| AB-29 | 1.000 | 1.002 | 1.010 | 1.005 | 1.009 | 1.003 | 1.007 |
| AB-31 | 0.864 | 0.882 | 0.940 | 0.912 | 1.008 | 0.860 | 0.928 |
| AB-33 | 0.765 | 0.745 | 0.815 | 0.750 | 0.786 | 0.758 | 0.777 |
| AB-35 | 0.757 | 0.688 | 0.754 | 0.687 | 0.726 | 0.705 | 0.718 |
| UNT-1 | 1.000 | 0.997 | 0.984 | 0.980 | 1.034 | 1.015 | 1.003 |
| EAG-1 | 1.000 | 1.004 | 0.997 | 0.993 | 0.991 | 0.984 | 0.991 |
| EAG-3 | 1.000 | 1.006 | 0.990 | 0.993 | 0.994 | 0.984 | 0.990 |
| EAG-5 | 1.000 | 1.001 | 0.994 | 0.992 | 0.981 | 0.997 | 0.991 |
| PRIO-5 | 1.000 | 0.989 | 1.001 | 1.001 | 1.002 | 0.993 | 0.999 |
| PRIO-6 | 1.000 | 1.005 | 1.017 | 0.996 | 1.001 | 0.996 | 1.002 |
| BAD-1 | 1.000 | 1.029 | 1.004 | 1.018 | 1.012 | 1.241 | 1.064 |
| B4-1 | 0.778 | 0.807 | 0.802 | 0.759 | 0.796 | 0.744 | 0.775 |
| B4-3 | 0.757 | 0.714 | 0.729 | 0.698 | 0.732 | 0.721 | 0.720 |
| B4-5 | 0.840 | 0.883 | 0.852 | 0.840 | 0.882 | 0.841 | 0.854 |
| B4-7 | 0.806 | 0.810 | 0.809 | 0.774 | 0.829 | 0.725 | 0.783 |
| B4-9 | 1.000 | 0.996 | 0.998 | 0.996 | 0.993 | 0.998 | 0.996 |
| B4-11 | 1.000 | 1.006 | 0.991 | 1.000 | 1.001 | 0.980 | 0.993 |
| B4-13 | 0.763 | 0.780 | 0.795 | 0.750 | 0.783 | 0.737 | 0.766 |
| B4P-1 | 0.981 | 0.967 | 0.991 | 0.988 | 0.984 | 0.991 | 0.988 |
| B4P-5 | 0.909 | 0.884 | 0.933 | 0.892 | 0.888 | 0.877 | 0.897 |

## Priority against stock launched next to it (secondary)

The priority claims' denominators are B1's stock launches, hours earlier. Here the same ratios use stock FCFS from prio8 (fcfs-adj, launched in turn with priority: priority, stock, stock, priority).

| id | metric | predicted | vs B1 stock | vs adjacent stock | verdict | strict |
|---|---|---|---|---|---|---|
| PRIO-1 | session_p50 | 1.000 | - | - | invalid | unresolved |
| PRIO-2 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-3 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-4 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-5 | session_p50 | 1.000 | 0.989 | 0.994 | supported | unresolved |
| PRIO-6 | session_p50 | 1.000 | 1.005 | - | not run | not run |
| PRIO-7 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-8 | session_p50 | 0.999 | - | - | not run | not run |

## Point accuracy (|log(pred / meas)|; not pass/fail)

| set | part | metric | points | median | max |
|---|---|---|---|---|---|
| P1 | in_sample | session_p50 | 15 | 0.245 | 0.933 |
| P1 | in_sample | root_tpot_p50 | 15 | 0.091 | 0.478 |
| P1 | out_of_sample | session_p50 | 31 | 0.169 | 0.373 |
| P1 | out_of_sample | root_tpot_p50 | 31 | 0.073 | 0.322 |
| P0 | out_of_sample | session_p50 | 46 | 0.149 | 0.933 |
| P0 | out_of_sample | root_tpot_p50 | 46 | 0.070 | 0.480 |
| P1-alt | in_sample | session_p50 | 15 | 0.175 | 0.933 |
| P1-alt | in_sample | root_tpot_p50 | 15 | 0.073 | 0.478 |
| P1-alt | out_of_sample | session_p50 | 31 | 0.143 | 0.373 |
| P1-alt | out_of_sample | root_tpot_p50 | 31 | 0.046 | 0.322 |

## Launch-to-launch spread (same arm and load, different server launches)

| arm | agents | launches | session p50 per launch | spread |
|---|---|---|---|---|
| fcfs-adj/spec | 8 | fcfs#4, fcfs#5 | 5.12, 4.84 | 5.8% |
| fcfs-adj/spec+bad | 8 | fcfs#4, fcfs#5 | 7.44, 7.47 | 0.3% |
| fcfs-b4/spec | 4 | fcfs#6, fcfs#7 | 4.01, 4.03 | 0.5% |
| fcfs-b4/spec | 8 | fcfs#6, fcfs#7 | 5.02, 4.84 | 3.7% |
| fcfs-b4/spec+bad | 4 | fcfs#6, fcfs#7 | 5.14, 5.14 | 0.1% |
| fcfs-b4/spec+bad | 8 | fcfs#6, fcfs#7 | 7.05, 6.74 | 4.5% |
| fcfs-eager/spec | 1 | fcfs_eager#1, fcfs_eager#2 | 6.37, 6.20 | 2.7% |
| fcfs/nospec | 1 | fcfs#2, fcfs#3 | 16.83, 17.89 | 6.3% |
| fcfs/spec | 1 | fcfs#2, fcfs#3 | 3.71, 3.71 | 0.2% |
| fcfs/spec | 4 | fcfs#2, fcfs#3 | 4.07, 3.99 | 1.9% |
| fcfs/spec | 8 | fcfs#2, fcfs#3 | 5.12, 4.88 | 4.9% |
| fcfs/spec+bad | 1 | fcfs#2, fcfs#3 | 4.26, 4.34 | 1.9% |
| fcfs/spec+bad | 4 | fcfs#2, fcfs#3 | 5.60, 5.11 | 9.6% |
| fcfs/spec+bad | 8 | fcfs#2, fcfs#3 | 7.49, 7.51 | 0.2% |
| plugin-adaptive-eager/spec | 1 | plugin_adaptive_eager#1, plugin_adaptive_eager#2 | 6.27, 6.26 | 0.0% |
| plugin-adaptive/spec | 1 | plugin_adaptive#2, plugin_adaptive#3 | 3.86, 3.78 | 2.1% |
| plugin-adaptive/spec | 4 | plugin_adaptive#2, plugin_adaptive#3 | 4.05, 3.99 | 1.4% |
| plugin-adaptive/spec | 8 | plugin_adaptive#2, plugin_adaptive#3 | 5.14, 4.88 | 5.4% |
| plugin-adaptive/spec+bad | 1 | plugin_adaptive#2, plugin_adaptive#3 | 3.80, 4.07 | 6.9% |
| plugin-adaptive/spec+bad | 4 | plugin_adaptive#2, plugin_adaptive#3 | 4.18, 4.04 | 3.5% |
| plugin-adaptive/spec+bad | 8 | plugin_adaptive#2, plugin_adaptive#3 | 5.18, 5.18 | 0.1% |
| plugin-b4/spec+bad | 4 | plugin#3, plugin#4 | 4.01, 4.01 | 0.2% |
| plugin-b4/spec+bad | 8 | plugin#3, plugin#4 | 5.05, 4.92 | 2.6% |
| plugin-eager/spec | 1 | plugin_eager#1, plugin_eager#2 | 6.33, 6.23 | 1.5% |
| plugin-off-eager/spec | 1 | plugin_off_eager#1, plugin_off_eager#2 | 6.24, 6.27 | 0.6% |
| plugin-off/spec | 1 | plugin_off#2, plugin_off#3 | 3.86, 3.73 | 3.7% |
| plugin-off/spec | 4 | plugin_off#2, plugin_off#3 | 4.05, 3.99 | 1.4% |
| plugin-off/spec | 8 | plugin_off#2, plugin_off#3 | 5.12, 4.92 | 4.1% |
| plugin-off/spec+bad | 1 | plugin_off#2, plugin_off#3 | 3.79, 4.18 | 10.3% |
| plugin-off/spec+bad | 4 | plugin_off#2, plugin_off#3 | 4.20, 4.05 | 3.7% |
| plugin-off/spec+bad | 8 | plugin_off#2, plugin_off#3 | 5.17, 5.12 | 0.9% |
| plugin-untagged/spec | 1 | plugin#1, plugin#2 | 3.67, 3.80 | 3.5% |
| plugin/spec | 1 | plugin#1, plugin#2 | 3.82, 3.66 | 4.3% |
| plugin/spec | 4 | plugin#1, plugin#2 | 4.08, 4.01 | 1.8% |
| plugin/spec | 8 | plugin#1, plugin#2 | 5.11, 4.94 | 3.4% |
| plugin/spec+bad | 1 | plugin#1, plugin#2 | 3.87, 4.10 | 5.9% |
| plugin/spec+bad | 4 | plugin#1, plugin#2 | 4.15, 4.06 | 2.3% |
| plugin/spec+bad | 8 | plugin#1, plugin#2 | 5.19, 5.21 | 0.4% |
| prio-bets/spec+bad | 4 | priority#3, priority#4 | 5.17, 5.07 | 2.0% |
| prio-bets/spec+bad | 8 | priority#3, priority#4 | 7.06, 6.85 | 3.1% |
| prio/spec | 8 | priority#1, priority#2 | 5.15, 4.84 | 6.4% |
| prio/spec+bad | 8 | priority#1, priority#2 | 7.35, 7.46 | 1.6% |
| proxy-sem/spec+bad | 4 | fcfs#6, fcfs#7 | 4.53, 4.57 | 0.8% |
| proxy-sem/spec+bad | 8 | fcfs#6, fcfs#7 | 5.66, 5.66 | 0.1% |
| proxy/spec+bad | 4 | fcfs#6, fcfs#7 | 4.15, 4.18 | 0.9% |
| proxy/spec+bad | 8 | fcfs#6, fcfs#7 | 5.09, 4.86 | 4.8% |

## Server launches (compile state)

A fresh compile saves an artifact (AOT saved); a cached launch loads one (AOT loaded). Launches that ran the same code show the same artifact path in one of the two columns. Role cache_fill: compiled fresh, stopped unmeasured.

| launch | status | role | startup s | eager | fresh | AOT saved | AOT loaded | GPU C / SM MHz | plugin line |
|---|---|---|---|---|---|---|---|---|---|
| fcfs#1 | up | cache_fill | 176.1 | False | True | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | - | 56 / 585 | - |
| fcfs#2 | up | measure | 96.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 62 / 585 | - |
| plugin#1 | up | measure | 72.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| plugin_adaptive#1 | up | cache_fill | 130.0 | False | True | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/e07e99d58408bcfb0df334dea04720af43256c8877b34228a05d3d68ad86a728/rank_0_0/model | - | 75 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='adaptive', bet_hold_steps=16), prefill allowance 512 (adaptive) |
| plugin_adaptive#2 | up | measure | 72.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/e07e99d58408bcfb0df334dea04720af43256c8877b34228a05d3d68ad86a728/rank_0_0/model | 74 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='adaptive', bet_hold_steps=16), prefill allowance 512 (adaptive) |
| plugin_off#1 | up | cache_fill | 132.0 | False | True | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/29b5ab51c0bd1c701306a7b392fd53040f5e2a761e6ec4abecf271c02f2e4ac3/rank_0_0/model | - | 75 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='off', bet_hold_steps=16), prefill allowance unlimited |
| plugin_off#2 | up | measure | 72.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/29b5ab51c0bd1c701306a7b392fd53040f5e2a761e6ec4abecf271c02f2e4ac3/rank_0_0/model | 74 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='off', bet_hold_steps=16), prefill allowance unlimited |
| plugin_off#3 | up | measure | 72.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/29b5ab51c0bd1c701306a7b392fd53040f5e2a761e6ec4abecf271c02f2e4ac3/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='off', bet_hold_steps=16), prefill allowance unlimited |
| plugin_adaptive#3 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/e07e99d58408bcfb0df334dea04720af43256c8877b34228a05d3d68ad86a728/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='adaptive', bet_hold_steps=16), prefill allowance 512 (adaptive) |
| plugin#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| fcfs#3 | up | measure | 72.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| fcfs_eager#1 | up | measure | 54.0 | True | False | - | - | 68 / 585 | - |
| plugin_eager#1 | up | measure | 54.0 | True | False | - | - | 67 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| plugin_adaptive_eager#1 | up | measure | 54.0 | True | False | - | - | 67 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='adaptive', bet_hold_steps=16), prefill allowance 512 (adaptive) |
| plugin_off_eager#1 | up | measure | 54.0 | True | False | - | - | 68 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='off', bet_hold_steps=16), prefill allowance unlimited |
| plugin_off_eager#2 | up | measure | 54.0 | True | False | - | - | 67 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='off', bet_hold_steps=16), prefill allowance unlimited |
| plugin_adaptive_eager#2 | up | measure | 54.0 | True | False | - | - | 67 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='adaptive', bet_hold_steps=16), prefill allowance 512 (adaptive) |
| plugin_eager#2 | up | measure | 54.0 | True | False | - | - | 67 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| fcfs_eager#2 | up | measure | 54.0 | True | False | - | - | 67 / 585 | - |
| priority#1 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 71 / 585 | - |
| fcfs#4 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | - |
| fcfs#5 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| priority#2 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| fcfs#6 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | - |
| priority#3 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| plugin#3 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| plugin#4 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |
| priority#4 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | - |
| fcfs#7 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| fcfs#8 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 72 / 585 | - |
| priority#5 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 73 / 585 | - |
| plugin#5 | up | measure | 70.0 | False | False | - | /root/.cache/vllm/torch_compile_cache/torch_aot_compile/86fe43c9591c8313242f2a27606e02ef89af9c4c4cc24554a68cc1b273d11723/rank_0_0/model | 71 / 585 | sptc scheduler (SptcAsyncScheduler): SptcConfig(free_window=8, kv_reserve=0.1, spec_prefill_budget=512, prefill_allowance='fixed', bet_hold_steps=16), prefill allowance 512 (fixed) |

## Scheduler overhead (added time per step vs stock)

| N | variant | scheduling | added us | bound us | verdict |
|---|---|---|---|---|---|
| 8 | sptc-untagged | sync | 9.0 | 30 | supported |
| 8 | sptc-untagged | async | 0.7 | 30 | supported |
| 8 | sptc-tagged | sync | 17.2 | 43 | supported |
| 8 | sptc-tagged | async | 15.8 | 43 | supported |
| 32 | sptc-untagged | sync | 2.9 | 59 | supported |
| 32 | sptc-untagged | async | -5.7 | 59 | supported |
| 32 | sptc-tagged | sync | 20.0 | 96 | supported |
| 32 | sptc-tagged | async | 16.5 | 96 | supported |
| 64 | sptc-untagged | sync | 72.7 | 98 | supported |
| 64 | sptc-untagged | async | 40.6 | 98 | supported |
| 64 | sptc-tagged | sync | 82.9 | 166 | supported |
| 64 | sptc-tagged | async | 55.1 | 166 | supported |
| 128 | sptc-untagged | sync | 63.7 | 174 | supported |
| 128 | sptc-untagged | async | 27.6 | 174 | supported |
| 128 | sptc-tagged | sync | 95.6 | 312 | supported |
| 128 | sptc-tagged | async | 133.7 | 312 | supported |
| 256 | sptc-untagged | sync | 33.2 | 334 | supported |
| 256 | sptc-untagged | async | 115.0 | 334 | supported |
| 256 | sptc-tagged | sync | 166.7 | 623 | supported |
| 256 | sptc-tagged | async | 150.4 | 623 | supported |
| 512 | sptc-untagged | sync | 45.1 | 639 | supported |
| 512 | sptc-untagged | async | 172.8 | 639 | supported |
| 512 | sptc-tagged | sync | 349.8 | 1149 | supported |
| 512 | sptc-tagged | async | 403.7 | 1149 | supported |

## General workload claims

One run per cell and one server launch per arm (fcfs, priority, plugin in that order): no CI, no launch-to-launch noise floor. Single-run, indicative verdicts.

| claim | predicted | bound | measured | verdict |
|---|---|---|---|---|
| 1. on stock vLLM, 3 next-call guesses slow 8 agents down | 1.628 | [1.3, None] | 1.533 | supported |
| 2. on stock vLLM, 3 action candidates slow 8 agents down, less than next-call guesses | 1.134 | [1.05, None] | - | not run |
| 3. vLLM priority (bets at 1) does not protect the agents: same as FCFS | 1.000 | [0.9, 1.1] | 1.014 | supported |
| 4. vLLM priority, action candidates: same as FCFS | 1.000 | [0.9, 1.1] | - | not run |
| 5. the plugin removes most of the slowdown at 8 agents (next3) | 0.697 | [None, 0.8] | 0.767 | supported |
| 6. the plugin removes part of the smaller action-candidate slowdown at 8 agents | 0.919 | [None, 0.97] | - | not run |
| 7. at 16 agents the plugin refuses almost every bet: same as no speculation | 1.001 | [0.9, 1.1] | - | not run |
| 8. at 1 agent next-call guessing is a net win on these 3 sessions (plugin shown; 6 of 15 step | 0.806 | [None, 0.9] | - | not run |
| 9. background jobs as bets protect the agents better than untagged jobs | 0.593 | [None, 0.75] | - | not run |
| 10. background jobs at priority 1 are no better than untagged jobs | 0.981 | [0.9, 1.1] | - | not run |
| 11. at 1 agent, action candidates under the plugin do not raise root TPOT (each candidate pref | 1.000 | [0.95, 1.05] | - | not run |
| 12. at 1 agent with no bets the plugin does not raise root TPOT (a repeat of the earlier T4 ru | 1.000 | [0.95, 1.05] | - | not run |


# Measured vs pre-registered (prereg_v3b) (also reported)

Predictions: commit `da1ae49bd1`, written 2026-10-20T06:22:09Z. Measured runs found: 226. Verdicts follow the rules in `results/prereg_v3b/predictions.md`; 'not run' means the cell was not measured.

Prediction files vs the prereg commit (sha256): predictions.json match, predictions.md match.

- Simulator claims (P1): invalid 2, supported 14, unresolved 4
- Ratio claims, strict (launch-level CI, added before the run): supported 4, unresolved 14
- Scheduler overhead bounds: none
- General workload claims (general_quick/general.json; one run per cell, indicative): none

## Claims

'verdict' is the pre-registered rule: a ratio is supported when its point estimate is within the tolerance, however wide its CI. That alone does not show equivalence (for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, resampling server launches, then runs, then sessions, inside predicted +- tol (supported) or outside it (refuted), with >= 2 launches per side (launches: numerator/denominator). Read a ratio as shown only where both agree. 'work': sub-call tokens per session, numerator over denominator (not a verdict); away from 1 by more than the tolerance, the two sides did not run the same workload.

| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches | work | validity |
|---|---|---|---|---|---|---|---|
| B4C-1 | fcfs-b4/spec / fcfs-b4/spec+bad at 4: session_p50 | 0.743 (0.647, 0.698) | 0.781 | supported | unresolved [0.637, 0.851] 2/2 | 1.001 | ok, ok |
| B4C-2 | fcfs-b4/spec / fcfs-b4/spec+bad at 4: root_tpot_p50 | 0.750 (0.664, 0.714) | 0.757 | supported | supported [0.727, 0.787] 2/2 | 1.001 | ok, ok |
| B4C-3 | fcfs-b4/spec / fcfs-b4/spec+bad at 8: session_p50 | 0.757 (0.539, 0.717) | 0.713 | supported | unresolved [0.629, 0.785] 2/2 | 1.014 | ok, ok |
| B4C-4 | fcfs-b4/spec / fcfs-b4/spec+bad at 8: root_tpot_p50 | 0.745 (0.554, 0.717) | 0.711 | supported | unresolved [0.693, 0.734] 2/2 | 1.014 | ok, ok |
| B4N-1 | proxy/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.048 (1.052, 1.048) | 1.034 | supported | unresolved [0.881, 1.201] 2/2 | 0.999 | ok, ok |
| B4N-2 | proxy/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.046 (1.042, 1.042) | 1.028 | supported | unresolved [0.989, 1.071] 2/2 | 0.999 | ok, ok |
| B4N-3 | proxy/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.000 (1.000, 1.000) | 1.002 | supported | unresolved [0.898, 1.145] 2/2 | 1.000 | ok, ok |
| B4N-4 | proxy/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.009 | supported | supported [0.989, 1.022] 2/2 | 1.000 | ok, ok |
| B4N-5 | proxy-sem/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.131 (1.145, 1.140) | 1.131 | supported | unresolved [0.986, 1.334] 2/2 | 0.998 | ok, ok |
| B4N-6 | proxy-sem/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.126 (1.128, 1.129) | 1.127 | supported | supported [1.093, 1.158] 2/2 | 0.998 | ok, ok |
| B4N-7 | proxy-sem/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.065 (1.112, 1.090) | 1.136 | unresolved | unresolved [0.956, 1.275] 2/2 | 0.992 | ok, ok |
| B4N-8 | proxy-sem/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.071 (1.107, 1.084) | 1.120 | supported | unresolved [1.103, 1.137] 2/2 | 0.992 | ok, ok |
| B4N-9 | prio-bets/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.347 (1.546, 1.433) | 1.275 | unresolved | unresolved [1.177, 1.568] 2/2 | 1.000 | ok, ok |
| B4N-10 | prio-bets/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.333 (1.506, 1.400) | 1.319 | supported | unresolved [1.259, 1.361] 2/2 | 1.000 | ok, ok |
| B4N-11 | prio-bets/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.321 (1.854, 1.395) | 1.411 | unresolved | unresolved [1.298, 1.621] 2/2 | 0.992 | ok, ok |
| B4N-12 | prio-bets/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.342 (1.803, 1.395) | 1.398 | unresolved | unresolved [1.342, 1.442] 2/2 | 0.992 | ok, ok |
| B4N-13 | plugin-b4/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.028 (1.030, 1.030) | 0.999 | supported | unresolved [0.871, 1.187] 2/2 | 0.999 | ok, ok |
| B4N-14 | plugin-b4/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.022 (1.018, 1.020) | 1.008 | supported | supported [0.973, 1.070] 2/2 | 0.999 | ok, ok |
| B4N-15 | plugin-b4/spec+bad / fcfs-b4/spec at 8: session_p50 | 0.994 (0.993, 0.995) | - | invalid | - | - | invalid: host CPU saturated, ok |
| B4N-16 | plugin-b4/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | - | invalid | - | - | invalid: host CPU saturated, ok |

## Per-pattern ratios (secondary; session_p50 claims)

Median session wall per pattern, numerator over denominator: the same deterministic workload on both sides. The pooled p50 above can jump between pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.

| id | predicted | pooled | map16 | map_reduce | side_branch_chain | two_stage | geo mean |
|---|---|---|---|---|---|---|---|
| B4C-1 | 0.743 | 0.781 | 0.792 | 0.733 | 0.775 | 0.728 | 0.757 |
| B4C-3 | 0.757 | 0.713 | 0.731 | 0.694 | 0.733 | 0.697 | 0.713 |
| B4N-1 | 1.048 | 1.034 | 1.012 | 1.035 | 1.027 | 1.022 | 1.024 |
| B4N-3 | 1.000 | 1.002 | 0.997 | 1.006 | 0.999 | 1.034 | 1.009 |
| B4N-5 | 1.131 | 1.131 | 1.075 | 1.146 | 1.138 | 1.155 | 1.128 |
| B4N-7 | 1.065 | 1.136 | 1.107 | 1.115 | 1.131 | 1.041 | 1.098 |
| B4N-9 | 1.347 | 1.275 | 1.259 | 1.358 | 1.281 | 1.372 | 1.317 |
| B4N-11 | 1.321 | 1.411 | 1.357 | 1.441 | 1.366 | 1.407 | 1.393 |
| B4N-13 | 1.028 | 0.999 | 1.003 | 1.023 | 1.011 | 1.013 | 1.012 |


# Measured vs pre-registered (prereg_v2) (also reported)

Predictions: commit `3f835a4c24`, written 2026-10-20T02:11:35Z. Measured runs found: 226. Verdicts follow the rules in `results/prereg_v2/predictions.md`; 'not run' means the cell was not measured.

Prediction files vs the prereg commit (sha256): predictions.json match, predictions.md match, general_predictions.json match.

- Simulator claims (P1): invalid 12, not run 11, refuted 8, supported 51, unchecked 8, unresolved 2
- Ratio claims, strict (launch-level CI, added before the run): supported 14, unresolved 31
- Scheduler overhead bounds: supported 24
- General workload claims (general_quick/general.json; one run per cell, indicative): not run 9, supported 3

## Claims

'verdict' is the pre-registered rule: a ratio is supported when its point estimate is within the tolerance, however wide its CI. That alone does not show equivalence (for example 'no gap' in AB-1/AB-2). 'strict' also needs the ratio's 95% CI, resampling server launches, then runs, then sessions, inside predicted +- tol (supported) or outside it (refuted), with >= 2 launches per side (launches: numerator/denominator). Read a ratio as shown only where both agree. 'work': sub-call tokens per session, numerator over denominator (not a verdict); away from 1 by more than the tolerance, the two sides did not run the same workload.

| id | claim | predicted P1 (P0, P1-alt) | measured | verdict | strict [CI] launches | work | validity |
|---|---|---|---|---|---|---|---|
| AB-1 | plugin/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.012 | supported | unresolved [0.857, 1.187] 2/2 | 0.989 | ok, ok |
| AB-2 | plugin/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.002 | supported | unresolved [0.846, 1.178] 2/2 | 0.989 | ok, ok |
| AB-3 | plugin/spec / fcfs/spec at 4: session_p50 | 0.997 (0.997, 0.997) | 1.000 | supported | unresolved [0.854, 1.170] 2/2 | 0.998 | ok, ok |
| AB-4 | plugin/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 (0.994, 0.995) | 0.997 | supported | supported [0.966, 1.035] 2/2 | 0.998 | ok, ok |
| AB-5 | plugin/spec / fcfs/spec at 8: session_p50 | 0.994 (0.993, 0.995) | 1.001 | supported | unresolved [0.805, 1.234] 2/2 | 0.999 | ok, ok |
| AB-6 | plugin/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | 1.002 | supported | supported [0.978, 1.017] 2/2 | 0.999 | ok, ok |
| AB-7 | plugin/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.904 | supported | unresolved [0.876, 1.037] 2/2 | 0.999 | ok, ok |
| AB-8 | plugin/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.978 | unresolved | unresolved [0.867, 1.140] 2/2 | 0.999 | ok, ok |
| AB-9 | plugin/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 (0.666, 0.719) | 0.749 | supported | unresolved [0.637, 0.859] 2/2 | 0.998 | ok, ok |
| AB-10 | plugin/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 (0.676, 0.728) | 0.770 | supported | supported [0.738, 0.810] 2/2 | 0.998 | ok, ok |
| AB-11 | plugin/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 (0.535, 0.713) | 0.695 | refuted | unresolved [0.667, 0.726] 2/2 | 0.993 | ok, ok |
| AB-12 | plugin/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 (0.547, 0.709) | 0.728 | supported | supported [0.707, 0.739] 2/2 | 0.993 | ok, ok |
| AB-13 | plugin-adaptive/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.019 | supported | unresolved [0.836, 1.186] 2/2 | 0.989 | ok, ok |
| AB-14 | plugin-adaptive/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.992 | supported | unresolved [0.852, 1.184] 2/2 | 0.989 | ok, ok |
| AB-15 | plugin-adaptive/spec / fcfs/spec at 4: session_p50 | 0.997 (0.997, 0.997) | 0.999 | supported | unresolved [0.852, 1.170] 2/2 | 0.997 | ok, ok |
| AB-16 | plugin-adaptive/spec / fcfs/spec at 4: root_tpot_p50 | 0.997 (0.994, 0.995) | 0.994 | supported | supported [0.967, 1.036] 2/2 | 0.997 | ok, ok |
| AB-17 | plugin-adaptive/spec / fcfs/spec at 8: session_p50 | 0.994 (0.993, 0.995) | - | invalid | - | - | invalid: host CPU saturated, ok |
| AB-18 | plugin-adaptive/spec / fcfs/spec at 8: root_tpot_p50 | 0.994 (0.987, 0.989) | - | invalid | - | - | invalid: host CPU saturated, ok |
| AB-19 | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.884 | supported | unresolved [0.817, 1.014] 2/2 | 0.999 | ok, ok |
| AB-20 | plugin-adaptive/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.942 | supported | unresolved [0.858, 1.119] 2/2 | 0.999 | ok, ok |
| AB-21 | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.763 (0.666, 0.719) | 0.746 | supported | unresolved [0.637, 0.856] 2/2 | 0.999 | ok, ok |
| AB-22 | plugin-adaptive/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.767 (0.676, 0.728) | 0.769 | supported | supported [0.738, 0.809] 2/2 | 0.999 | ok, ok |
| AB-23 | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.752 (0.535, 0.713) | 0.691 | refuted | unresolved [0.673, 0.722] 2/2 | 0.993 | ok, ok |
| AB-24 | plugin-adaptive/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.741 (0.547, 0.709) | 0.725 | supported | supported [0.705, 0.737] 2/2 | 0.993 | ok, ok |
| AB-25 | plugin-off/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.017 | supported | unresolved [0.839, 1.195] 2/2 | 0.989 | ok, ok |
| AB-26 | plugin-off/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.006 | supported | unresolved [0.862, 1.204] 2/2 | 0.989 | ok, ok |
| AB-27 | plugin-off/spec / fcfs/spec at 4: session_p50 | 1.000 (1.000, 1.000) | 1.000 | supported | unresolved [0.858, 1.170] 2/2 | 0.999 | ok, ok |
| AB-28 | plugin-off/spec / fcfs/spec at 4: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.992 | supported | supported [0.968, 1.036] 2/2 | 0.999 | ok, ok |
| AB-29 | plugin-off/spec / fcfs/spec at 8: session_p50 | 1.000 (1.000, 1.000) | 1.002 | supported | unresolved [0.810, 1.236] 2/2 | 1.001 | ok, ok |
| AB-30 | plugin-off/spec / fcfs/spec at 8: root_tpot_p50 | 1.000 (1.000, 1.000) | 1.007 | supported | supported [0.986, 1.019] 2/2 | 1.001 | ok, ok |
| AB-31 | plugin-off/spec+bad / fcfs/spec+bad at 1: session_p50 | 0.864 (0.864, 0.864) | 0.882 | supported | unresolved [0.819, 1.087] 2/2 | 0.999 | ok, ok |
| AB-32 | plugin-off/spec+bad / fcfs/spec+bad at 1: root_tpot_p50 | 0.895 (0.895, 0.895) | 0.960 | unresolved | unresolved [0.858, 1.113] 2/2 | 0.999 | ok, ok |
| AB-33 | plugin-off/spec+bad / fcfs/spec+bad at 4: session_p50 | 0.765 (0.668, 0.721) | 0.745 | supported | unresolved [0.636, 0.854] 2/2 | 0.999 | ok, ok |
| AB-34 | plugin-off/spec+bad / fcfs/spec+bad at 4: root_tpot_p50 | 0.769 (0.680, 0.733) | 0.769 | supported | supported [0.733, 0.809] 2/2 | 0.999 | ok, ok |
| AB-35 | plugin-off/spec+bad / fcfs/spec+bad at 8: session_p50 | 0.757 (0.539, 0.717) | 0.688 | refuted | unresolved [0.668, 0.719] 2/2 | 0.990 | ok, ok |
| AB-36 | plugin-off/spec+bad / fcfs/spec+bad at 8: root_tpot_p50 | 0.745 (0.554, 0.717) | 0.720 | supported | supported [0.702, 0.733] 2/2 | 0.990 | ok, ok |
| UNT-1 | plugin-untagged/spec / fcfs/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 0.997 | supported | unresolved [0.931, 1.160] 2/2 | 0.977 | ok, ok |
| UNT-2 | plugin-untagged/spec / fcfs/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.998 | supported | unresolved [0.837, 1.164] 2/2 | 0.977 | ok, ok |
| EAG-1 | plugin-eager/spec / fcfs-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.004 | supported | unresolved [0.799, 1.267] 2/2 | 1.000 | ok, ok |
| EAG-2 | plugin-eager/spec / fcfs-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.999 | supported | supported [0.982, 1.024] 2/2 | 1.000 | ok, ok |
| EAG-3 | plugin-adaptive-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.006 | supported | unresolved [0.793, 1.236] 2/2 | 1.000 | ok, ok |
| EAG-4 | plugin-adaptive-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.991 | supported | supported [0.975, 1.005] 2/2 | 1.000 | ok, ok |
| EAG-5 | plugin-off-eager/spec / plugin-eager/spec at 1: session_p50 | 1.000 (1.000, 1.000) | 1.001 | supported | unresolved [0.789, 1.234] 2/2 | 1.000 | ok, ok |
| EAG-6 | plugin-off-eager/spec / plugin-eager/spec at 1: root_tpot_p50 | 1.000 (1.000, 1.000) | 0.984 | supported | supported [0.968, 0.997] 2/2 | 1.000 | ok, ok |
| PRIO-1 | prio/spec / fcfs/spec at 8: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, ok |
| PRIO-2 | prio/spec / fcfs/spec at 16: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-3 | prio/spec / fcfs/spec at 24: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-4 | prio/spec / fcfs/spec at 32: session_p50 | 1.000 (1.000, 1.000) | - | not run | - | - | missing, missing |
| PRIO-5 | prio/spec+bad / fcfs/spec+bad at 8: session_p50 | 1.000 (1.000, 1.000) | 0.989 | supported | unresolved [0.944, 1.058] 2/2 | 0.998 | ok, ok |
| PRIO-6 | prio/spec+bad / fcfs/spec+bad at 16: session_p50 | 1.000 (1.000, 1.000) | 1.005 | supported | unresolved [0.956, 1.040] 1/1 | 1.000 | ok, ok |
| PRIO-7 | prio/spec+bad / fcfs/spec+bad at 24: session_p50 | 1.000 (1.001, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PRIO-8 | prio/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.999 (1.014, 0.996) | - | not run | - | - | missing, missing |
| PLG-1 | plugin/spec+bad / fcfs/spec+bad at 16: session_p50 | 0.630 (0.437, 0.634) | - | invalid | - | - | invalid: host CPU saturated, ok |
| PLG-2 | plugin/spec+bad / fcfs/spec+bad at 24: session_p50 | 0.554 (0.401, 0.569) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| PLG-3 | plugin/spec+bad / fcfs/spec+bad at 32: session_p50 | 0.525 (0.407, 0.537) | - | not run | - | - | missing, missing |
| BAD-1 | plugin/spec+bad / plugin/spec at 8: session_p50 | 1.000 (1.000, 1.000) | 1.029 | supported | unresolved [0.981, 1.271] 2/2 | 1.069 | ok, ok |
| BAD-2 | plugin/spec+bad / plugin/spec at 16: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| BAD-3 | plugin/spec+bad / plugin/spec at 24: session_p50 | 1.000 (1.000, 1.000) | - | invalid | - | - | invalid: host CPU saturated, invalid: host CPU saturated |
| BAD-4 | plugin/spec+bad / plugin/spec at 32: session_p50 | 1.000 (1.000, 1.000) | - | not run | - | - | missing, missing |
| REJ-1 | plugin/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.61 | refuted | - | - | ok |
| REJ-2 | plugin/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-3 | plugin/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| REJ-4 | plugin/spec+bad at 16: decoys rejected | 1.00 (1.00, 1.00) | - | invalid | - | - | invalid: host CPU saturated |
| REJ-5 | plugin/spec+bad at 24: decoys rejected | 1.00 (1.00, 1.00) | - | invalid | - | - | invalid: host CPU saturated |
| REJ-6 | plugin/spec+bad at 32: decoys rejected | 1.00 (1.00, 1.00) | - | not run | - | - | missing |
| REJ-7 | plugin-adaptive/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.66 | refuted | - | - | ok |
| REJ-8 | plugin-adaptive/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-9 | plugin-adaptive/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| REJ-10 | plugin-off/spec+bad at 1: decoys rejected | 0.78 (0.78, 0.78) | 0.67 | refuted | - | - | ok |
| REJ-11 | plugin-off/spec+bad at 4: decoys rejected | 0.96 (0.96, 0.96) | 0.96 | supported | - | - | ok |
| REJ-12 | plugin-off/spec+bad at 8: decoys rejected | 1.00 (1.00, 1.00) | 1.00 | supported | - | - | ok |
| THR-1 | knee_ref of fcfs/nospec | None (32, 32) | None | unchecked | - | - | - |
| THR-2 | knee_ref of fcfs/spec | 16 (12, 16) | 24 | supported | - | - | - |
| THR-3 | knee_ref of fcfs/spec+bad | 12 (8, 12) | 16 | supported | - | - | - |
| THR-4 | knee_ref of plugin/nospec | None (32, 32) | - | not run | - | - | - |
| THR-5 | knee_ref of plugin/spec | 24 (12, 16) | 24 | supported | - | - | - |
| THR-6 | knee_ref of plugin/spec+bad | 32 (16, 24) | None | unchecked | - | - | - |
| THR-7 | knee_ref of prio/nospec | None (32, 32) | - | not run | - | - | - |
| THR-8 | knee_ref of prio/spec | 16 (12, 16) | 24 | supported | - | - | - |
| THR-9 | knee_ref of prio/spec+bad | 12 (8, 12) | 16 | supported | - | - | - |
| THR-10 | good50 of fcfs/nospec | None (32, 32) | None | unchecked | - | - | - |
| THR-11 | good50 of fcfs/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-12 | good50 of fcfs/spec+bad | 8 (4, 8) | 16 | refuted | - | - | - |
| THR-13 | good50 of plugin/nospec | None (32, 32) | - | not run | - | - | - |
| THR-14 | good50 of plugin/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-15 | good50 of plugin/spec+bad | 16 (12, 12) | None | unchecked | - | - | - |
| THR-16 | good50 of prio/nospec | None (32, 32) | - | not run | - | - | - |
| THR-17 | good50 of prio/spec | 16 (12, 12) | None | unchecked | - | - | - |
| THR-18 | good50 of prio/spec+bad | 8 (4, 8) | 16 | refuted | - | - | - |
| THR-19 | net_loss of fcfs | 24 (8, 24) | None | unchecked | - | - | - |
| THR-20 | net_loss of prio | 24 (8, 24) | - | not run | - | - | - |
| THR-21 | net_loss of plugin | None (None, None) | - | not run | - | - | - |

## Per-pattern ratios (secondary; session_p50 claims)

Median session wall per pattern, numerator over denominator: the same deterministic workload on both sides. The pooled p50 above can jump between pattern clusters (results/t4_run1_analysis/root_cause.md); the geometric mean cannot.

| id | predicted | pooled | map16 | map_reduce | side_branch_chain | two_stage | geo mean |
|---|---|---|---|---|---|---|---|
| AB-1 | 1.000 | 1.012 | 1.007 | 0.996 | 0.999 | 0.980 | 0.995 |
| AB-3 | 0.997 | 1.000 | 1.002 | 0.997 | 1.000 | 1.006 | 1.001 |
| AB-5 | 0.994 | 1.001 | 1.001 | 0.999 | 1.002 | 0.991 | 0.998 |
| AB-7 | 0.864 | 0.904 | 0.941 | 0.920 | 1.020 | 0.888 | 0.941 |
| AB-9 | 0.763 | 0.749 | 0.808 | 0.748 | 0.787 | 0.760 | 0.776 |
| AB-11 | 0.752 | 0.695 | 0.746 | 0.690 | 0.729 | 0.703 | 0.717 |
| AB-13 | 1.000 | 1.019 | 1.044 | 0.994 | 1.001 | 1.006 | 1.011 |
| AB-15 | 0.997 | 0.999 | 1.007 | 0.999 | 1.000 | 1.010 | 1.004 |
| AB-19 | 0.864 | 0.884 | 0.913 | 0.901 | 1.011 | 0.856 | 0.919 |
| AB-21 | 0.763 | 0.746 | 0.807 | 0.748 | 0.788 | 0.760 | 0.775 |
| AB-23 | 0.752 | 0.691 | 0.740 | 0.689 | 0.732 | 0.705 | 0.716 |
| AB-25 | 1.000 | 1.017 | 1.046 | 1.010 | 0.998 | 1.011 | 1.016 |
| AB-27 | 1.000 | 1.000 | 1.015 | 0.999 | 1.002 | 0.981 | 0.999 |
| AB-29 | 1.000 | 1.002 | 1.010 | 1.005 | 1.009 | 1.003 | 1.007 |
| AB-31 | 0.864 | 0.882 | 0.940 | 0.912 | 1.008 | 0.860 | 0.928 |
| AB-33 | 0.765 | 0.745 | 0.815 | 0.750 | 0.786 | 0.758 | 0.777 |
| AB-35 | 0.757 | 0.688 | 0.754 | 0.687 | 0.726 | 0.705 | 0.718 |
| UNT-1 | 1.000 | 0.997 | 0.984 | 0.980 | 1.034 | 1.015 | 1.003 |
| EAG-1 | 1.000 | 1.004 | 0.997 | 0.993 | 0.991 | 0.984 | 0.991 |
| EAG-3 | 1.000 | 1.006 | 0.990 | 0.993 | 0.994 | 0.984 | 0.990 |
| EAG-5 | 1.000 | 1.001 | 0.994 | 0.992 | 0.981 | 0.997 | 0.991 |
| PRIO-5 | 1.000 | 0.989 | 1.001 | 1.001 | 1.002 | 0.993 | 0.999 |
| PRIO-6 | 1.000 | 1.005 | 1.017 | 0.996 | 1.001 | 0.996 | 1.002 |
| BAD-1 | 1.000 | 1.029 | 1.004 | 1.018 | 1.012 | 1.241 | 1.064 |

## Priority against stock launched next to it (secondary)

The priority claims' denominators are B1's stock launches, hours earlier. Here the same ratios use stock FCFS from prio8 (fcfs-adj, launched in turn with priority: priority, stock, stock, priority).

| id | metric | predicted | vs B1 stock | vs adjacent stock | verdict | strict |
|---|---|---|---|---|---|---|
| PRIO-1 | session_p50 | 1.000 | - | - | invalid | unresolved |
| PRIO-2 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-3 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-4 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-5 | session_p50 | 1.000 | 0.989 | 0.994 | supported | unresolved |
| PRIO-6 | session_p50 | 1.000 | 1.005 | - | not run | not run |
| PRIO-7 | session_p50 | 1.000 | - | - | not run | not run |
| PRIO-8 | session_p50 | 0.999 | - | - | not run | not run |

## General workload claims

| claim | predicted | bound | measured | verdict |
|---|---|---|---|---|
| 1. on stock vLLM, 3 next-call guesses slow 8 agents down | 1.627 | [1.3, None] | 1.533 | supported |
| 2. on stock vLLM, 3 action candidates slow 8 agents down, less than next-call guesses | 1.134 | [1.05, None] | - | not run |
| 3. vLLM priority (bets at 1) does not protect the agents: same as FCFS | 1.000 | [0.9, 1.1] | 1.014 | supported |
| 4. vLLM priority, action candidates: same as FCFS | 1.000 | [0.9, 1.1] | - | not run |
| 5. the plugin removes most of the slowdown at 8 agents (next3) | 0.714 | [None, 0.8] | 0.767 | supported |
| 6. the plugin removes part of the smaller action-candidate slowdown at 8 agents | 0.919 | [None, 0.97] | - | not run |
| 7. at 16 agents the plugin refuses almost every bet: same as no speculation | 1.000 | [0.9, 1.1] | - | not run |
| 8. at 1 agent next-call guessing is a net win on these 3 sessions (plugin shown; 6 of 15 step | 0.806 | [None, 0.9] | - | not run |
| 9. background jobs as bets protect the agents better than untagged jobs | 0.593 | [None, 0.75] | - | not run |
| 10. background jobs at priority 1 are no better than untagged jobs | 0.981 | [0.9, 1.1] | - | not run |
| 11. at 1 agent, action candidates under the plugin do not raise root TPOT (each candidate pref | 1.000 | [0.95, 1.05] | - | not run |
| 12. at 1 agent with no bets the plugin does not raise root TPOT (a repeat of the earlier T4 ru | 1.000 | [0.95, 1.05] | - | not run |
