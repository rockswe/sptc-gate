# Pre-registered predictions, addendum v3b: section B4

**PREDICTED by the simulator, not measured.** Written 2026-10-20T06:22:09Z by `experiments/prereg_v3b.py`, before any GPU run of `kaggle/sptc_kaggle_v3.ipynb`. The predictions were not changed after the run (list formatting was edited for publication). `experiments/prereg_compare.py` scores it next to `results/prereg_v3` (primary) and `results/prereg_v2`.

- Code: commit `da1ae49bd15e17f5a811338d3aa47e58816784c0` (clean tree).
- Based on `results/prereg_v3` (prereg commit 2e39a4d, written 2026-10-20T05:40:28Z; its files checked against that commit's sha256: {'predictions.json': 'match', 'predictions.md': 'match', 'general_predictions.json': 'match'}). Nothing in prereg_v3 or prereg_v2 changes.
- No new simulation. The no-bets reference `fcfs-b4/spec` is simulated as stock FCFS with speculation and no bad guesses, which is v3's `fcfs/spec` row per set. The script checks the identity it rests on: in every set, v3's fcfs-b4/spec+bad and plugin-b4/spec+bad rows equal fcfs/spec+bad and plugin/spec+bad at 4 and 8 agents.
- Nothing fit: the claims are ratios of v3's predicted rows.

## Protocol change after v3, before any run

- Same prompts on every B4 arm. In v3's protocol the three arms on each stock FCFS launch (fcfs-b4, proxy, proxy-sem) had numbered prompt prefixes (`[spec d1 n8 r0]`, `[spec d1 v1 n8 r0]`, `[spec d1 v2 n8 r0]`), to keep their runs out of each other's prefix cache. Sub-calls stop at EOS, so a different prefix can change their length: B4-1..8 and B4P-1..8 compared unlike prompts. Now every B4 arm sends the same text (`[spec n8 r0]`, the number of bad guesses left out), and the arms that share a launch are kept apart by vLLM's per-request `cache_salt` (`sptc-v1`, `sptc-v2`, `sptc-v3`; it enters the first KV block's hash). If a server refuses `cache_salt` the bench falls back to numbered prefixes and says so; every run records `salt` and `cache_salt`. The predicted values of v3's B4 claims do not change: the simulator has no prompt text.
- No-bets reference `fcfs-b4/spec` on the same stock FCFS launches: speculation without bad guesses, 3 repeats at 8 and 4 agents (6 more runs). Claims B4C-* and B4N-* below.
- Work and prefix-cache columns. The B4 table of `sweep/summary.md` now gives, per arm, sub-call completion tokens per session against fcfs-b4, session p50 against the no-bets reference, the share of decoys refused, and the server's prefix-cache hit share (`vllm:prefix_cache_hits` over `vllm:prefix_cache_queries`, per run).

## Corrections to v3's B4 text

- v3's rule 'baselines' (predictions.json `rules.baselines` and predictions.md) says the B4 denominators are fcfs-b4/spec+bad. That holds for B4-1..16 only. B4P-1..8 divide plugin-b4/spec+bad (plugin launches) by proxy/spec+bad or proxy-sem/spec+bad (stock FCFS launches). prereg_compare scores every claim with its own numerator and denominator, so no verdict changes; only the rule text was wrong.
- The same rule's '(same server, other prompt prefix)' no longer holds: see the protocol change above.

## How to read B4 (fixed before the run)

- B4 cannot show a cost of refusing too many bets. Every bet in this bench is a decoy: a bad guess of the same size, never claimed. Real speculative calls are kind `early`, which no gate and no bets-only priority touches. So refusing every bet is the best possible gate here, and the B4 arms rank by how many bets they refuse. The no-bets reference measures that best case directly. An arm within tolerance of it (B4N-*) has refused nearly every bet. Where two arms both refuse (nearly) all bets (in P1 at 8 agents, the window cap and the plugin both refuse 100%: B4P-3/4 predict 0.994), their ratio compares two arms that send almost no bets, and says nothing about which gate is smarter. 'If the GPU agrees, the T4 win needs no scheduler change at this load' holds only for a workload whose bets are all worthless.
- Work check (secondary, not a verdict). Next to each B4 ratio, read the ratio of sub-call tokens per session (numerator over denominator; `experiments/prereg_compare.py` prints it as 'work'). Away from 1 by more than the claim's tolerance, the two arms did not run the same workload and the claim is read as confounded, whatever its verdict.
- Prefix-cache check (secondary). The proxy and no-bets arms' prefix-cache hit share should be close to fcfs-b4's on the same launches. A clearly higher share means `cache_salt` did not keep the runs apart.
- Launch depth (known limit, not corrected). Four B4 arms share each stock FCFS launch (fcfs-b4, proxy, proxy-sem, no-bets: 16 measured runs in round 0, 8 in round 1), while prio-bets and plugin-b4 have a launch each (4 and 2). Arm order rotates within a launch and the rounds are ABBA, but claims across launches (B4P-*, B4-9..16, B4N for prio-bets and plugin-b4) compare runs made at different depths into a launch. Read them with the per-launch GPU clocks in `sweep/summary.md` ('Per server launch').

## B4 rows and ratios (P1; P0 in brackets)

| arm | agents | session p50 s | root TPOT p50 ms | vs fcfs-b4: session p50 | vs no bets: session p50 | vs no bets: root TPOT p50 | decoys rejected |
|---|---|---|---|---|---|---|---|
| fcfs-b4/spec+bad | 4 | 4.70 [5.39] | 28.5 [32.4] | 1.000 | 1.347 | 1.333 | 0.00 |
| fcfs-b4/spec+bad | 8 | 5.81 [8.56] | 35.9 [51.0] | 1.000 | 1.322 | 1.342 | 0.00 |
| proxy/spec+bad | 4 | 3.65 [3.67] | 22.4 [22.4] | 0.778 | 1.048 | 1.046 | 0.92 |
| proxy/spec+bad | 8 | 4.40 [4.61] | 26.8 [28.2] | 0.757 | 1.000 | 1.000 | 1.00 |
| proxy-sem/spec+bad | 4 | 3.94 [3.99] | 24.1 [24.3] | 0.840 | 1.131 | 1.126 | 0.72 |
| proxy-sem/spec+bad | 8 | 4.69 [5.13] | 28.7 [31.2] | 0.806 | 1.065 | 1.071 | 0.86 |
| prio-bets/spec+bad | 4 | 4.70 [5.39] | 28.5 [32.4] | 1.000 | 1.347 | 1.333 | 0.00 |
| prio-bets/spec+bad | 8 | 5.81 [8.55] | 35.9 [50.9] | 1.000 | 1.321 | 1.342 | 0.00 |
| plugin-b4/spec+bad | 4 | 3.58 [3.59] | 21.8 [21.9] | 0.763 | 1.028 | 1.022 | 0.96 |
| plugin-b4/spec+bad | 8 | 4.37 [4.58] | 26.6 [27.9] | 0.752 | 0.994 | 0.994 | 1.00 |
| fcfs-b4/spec | 4 | 3.49 [3.49] | 21.4 [21.5] | 0.743 | 1.000 | 1.000 | - |
| fcfs-b4/spec | 8 | 4.40 [4.61] | 26.8 [28.2] | 0.757 | 1.000 | 1.000 | - |

## Claims (P1 predicted; P0, P1-alt in brackets)

| id | section | claim | predicted | tol |
|---|---|---|---|---|
| B4C-1 | B4: cost of the bets (no-bets reference) | fcfs-b4/spec / fcfs-b4/spec+bad at 4: session_p50 | 0.743 [0.647, 0.698] | 0.05 |
| B4C-2 | B4: cost of the bets (no-bets reference) | fcfs-b4/spec / fcfs-b4/spec+bad at 4: root_tpot_p50 | 0.750 [0.664, 0.714] | 0.05 |
| B4C-3 | B4: cost of the bets (no-bets reference) | fcfs-b4/spec / fcfs-b4/spec+bad at 8: session_p50 | 0.757 [0.539, 0.717] | 0.05 |
| B4C-4 | B4: cost of the bets (no-bets reference) | fcfs-b4/spec / fcfs-b4/spec+bad at 8: root_tpot_p50 | 0.745 [0.554, 0.717] | 0.05 |
| B4N-1 | B4: each arm vs refusing every bet | proxy/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.048 [1.052, 1.048] | 0.05 |
| B4N-2 | B4: each arm vs refusing every bet | proxy/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.046 [1.042, 1.042] | 0.05 |
| B4N-3 | B4: each arm vs refusing every bet | proxy/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.000 [1.000, 1.000] | 0.05 |
| B4N-4 | B4: each arm vs refusing every bet | proxy/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.000 [1.000, 1.000] | 0.05 |
| B4N-5 | B4: each arm vs refusing every bet | proxy-sem/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.131 [1.145, 1.140] | 0.05 |
| B4N-6 | B4: each arm vs refusing every bet | proxy-sem/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.126 [1.128, 1.129] | 0.05 |
| B4N-7 | B4: each arm vs refusing every bet | proxy-sem/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.065 [1.112, 1.090] | 0.05 |
| B4N-8 | B4: each arm vs refusing every bet | proxy-sem/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.071 [1.107, 1.084] | 0.05 |
| B4N-9 | B4: each arm vs refusing every bet | prio-bets/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.347 [1.546, 1.433] | 0.05 |
| B4N-10 | B4: each arm vs refusing every bet | prio-bets/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.333 [1.506, 1.400] | 0.05 |
| B4N-11 | B4: each arm vs refusing every bet | prio-bets/spec+bad / fcfs-b4/spec at 8: session_p50 | 1.321 [1.854, 1.395] | 0.05 |
| B4N-12 | B4: each arm vs refusing every bet | prio-bets/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 1.342 [1.803, 1.395] | 0.05 |
| B4N-13 | B4: each arm vs refusing every bet | plugin-b4/spec+bad / fcfs-b4/spec at 4: session_p50 | 1.028 [1.030, 1.030] | 0.05 |
| B4N-14 | B4: each arm vs refusing every bet | plugin-b4/spec+bad / fcfs-b4/spec at 4: root_tpot_p50 | 1.022 [1.018, 1.020] | 0.05 |
| B4N-15 | B4: each arm vs refusing every bet | plugin-b4/spec+bad / fcfs-b4/spec at 8: session_p50 | 0.994 [0.993, 0.995] | 0.05 |
| B4N-16 | B4: each arm vs refusing every bet | plugin-b4/spec+bad / fcfs-b4/spec at 8: root_tpot_p50 | 0.994 [0.987, 0.989] | 0.05 |

## Rules

- ratio (v3's, unchanged): measured ratio m of two measured points vs predicted p: supported if |m - p| <= tol; refuted if |m - p| > tol and the numerator's 95% CI does not overlap p x the denominator's 95% CI (both from vllm_bench.summarize's bootstrap); otherwise unresolved. Eager ratios use eager points only.
- validity (v3's, unchanged): A measured point counts only if every run has status ok and its row's cpu_ok is true (whole-host CPU < 0.85 mean, < 10% of seconds >= 95% busy). Otherwise every claim using it is 'invalid'.
- baselines. B4C and B4N ratio claims use v3's ratio rule (tol 0.05); each claim's denominator is its own: fcfs-b4/spec+bad for B4C, the no-bets reference fcfs-b4/spec for B4N, both on the stock FCFS launches.

## GPU time of section B4 (estimate, `vllm_bench.py plan` on v3's predictions)

Preset `baselines`: 36 runs, 6 launches (plus up to 1 cache-filling), about 58 min (v3: 54 min).
