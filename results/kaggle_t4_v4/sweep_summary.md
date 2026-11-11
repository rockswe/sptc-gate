# Sweep summary

SLO per session: wall <= 2.0x and root TPOT <= 2.0x the `fcfs/nospec` arm at 1 agent, same pattern. Goodput = fraction of sessions meeting it; wall / TPOT = each half alone. Root TPOT is each session's mean; p50 and p99 are across sessions. Brackets: 95% bootstrap CI (repeats, then sessions); none for p99s. 'max': under 100 sessions, so the p99 is the slowest session. host CPU: whole host, mean over the run (max over repeats); cpu ok: every run below 0.85 with under 10% of seconds saturated.

| arm | agents | reps | session p50 s | session p99 s | root TPOT p50 ms | root TPOT p99 ms | sessions/min | goodput | wall / TPOT | decoys | preempt | max wait | client CPU | host CPU | cpu ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | 3 | 8.97 [7.88, 12.39] | 18.92 (max) | 20.1 [20.0, 20.3] | 20.7 (max) | 21.2 | - | - / - | completed:100,rejected:600 | 0 | 0 | 0.04 | 0.15 | yes |
| cap-p/both | 4 | 3 | 9.02 [7.93, 12.44] | 18.80 (max) | 20.3 [20.1, 20.4] | 20.8 (max) | 21.0 | - | - / - | completed:104,rejected:597 | 0 | 0 | 0.04 | 0.15 | yes |
| cap-p/spec+bad | 4 | 3 | 4.13 [3.57, 4.27] | 10.23 (max) | 23.6 [23.0, 23.9] | 25.3 (max) | 45.3 | - | - / - | cancelled:1,completed:27,rejected:512 | 0 | 0 | 0.09 | 0.20 | yes |
| fcfs-d/nospec | 4 | 3 | 9.81 [7.45, 12.54] | 17.78 (max) | 18.7 [18.7, 18.8] | 19.2 (max) | 23.2 | - | - / - | - | 0 | 0 | 0.05 | 0.15 | yes |
| fcfs-d/spec | 4 | 3 | 3.94 [3.40, 4.07] | 9.85 (max) | 22.6 [22.1, 23.0] | 24.6 (max) | 47.3 | - | - / - | - | 0 | 0 | 0.09 | 0.20 | yes |
| fcfs-d/spec+bad | 4 | 3 | 5.04 [4.71, 5.59] | 13.21 (max) | 29.8 [28.9, 30.6] | 33.6 (max) | 36.6 | - | - / - | cancelled:264,completed:276 | 0 | 0 | 0.09 | 0.21 | yes |
| fcfs-p/nospec | 4 | 3 | 9.83 [7.51, 12.60] | 17.97 (max) | 18.8 [18.7, 18.9] | 19.3 (max) | 23.0 | - | - / - | - | 0 | 0 | 0.04 | 0.14 | yes |
| fcfs-p/spec | 4 | 3 | 4.00 [3.50, 4.13] | 9.99 (max) | 23.0 [22.5, 23.3] | 25.2 (max) | 46.5 | - | - / - | - | 0 | 0 | 0.09 | 0.20 | yes |
| fcfs-p/spec+bad | 4 | 3 | 5.99 [5.28, 6.99] | 17.03 (max) | 29.8 [28.7, 29.9] | 57.9 (max) | 29.3 | - | - / - | cancelled:249,completed:291 | 576 | 49 | 0.08 | 0.19 | yes |
| plugin-d/both | 4 | 3 | 8.90 [8.13, 12.31] | 18.78 (max) | 20.2 [20.0, 20.4] | 20.8 (max) | 20.7 | - | - / - | completed:114,rejected:569 | 0 | 0 | 0.05 | 0.15 | yes |
| plugin-p/both | 4 | 3 | 9.02 [8.08, 12.47] | 19.20 (max) | 20.3 [20.0, 20.5] | 21.4 (max) | 20.8 | - | - / - | completed:112,rejected:563 | 0 | 0 | 0.05 | 0.16 | yes |
| plugin-p/spec+bad | 4 | 3 | 4.05 [3.51, 4.26] | 10.03 (max) | 23.3 [22.8, 23.8] | 25.2 (max) | 45.9 | - | - / - | cancelled:2,completed:16,rejected:522 | 0 | 0 | 0.10 | 0.21 | yes |
| prio-d/both | 4 | 3 | 5.06 [4.72, 5.71] | 13.43 (max) | 29.8 [29.1, 30.9] | 33.4 (max) | 36.4 | - | - / - | cancelled:262,completed:278 | 0 | 0 | 0.09 | 0.21 | yes |
| prio-p/both | 4 | 3 | 5.48 [5.22, 6.99] | 16.99 (max) | 29.9 [28.8, 30.5] | 33.0 (max) | 28.9 | - | - / - | cancelled:254,completed:286 | 720 | 40 | 0.08 | 0.20 | yes |
| prio-p/spec+bad | 4 | 3 | 5.21 [4.75, 5.56] | 13.75 (max) | 30.4 [29.9, 31.0] | 34.5 (max) | 34.9 | - | - / - | cancelled:351,completed:189 | 443 | 31 | 0.09 | 0.21 | yes |

## Derived

- knee (session p50 >= 2x own 1-agent): {'cap-d/both': None, 'cap-p/both': None, 'cap-p/spec+bad': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'fcfs-p/nospec': None, 'fcfs-p/spec': None, 'fcfs-p/spec+bad': None, 'plugin-d/both': None, 'plugin-p/both': None, 'plugin-p/spec+bad': None, 'prio-d/both': None, 'prio-p/both': None, 'prio-p/spec+bad': None}
- knee against stock FCFS's 1-agent p50, same mode: {'cap-d/both': None, 'cap-p/both': None, 'cap-p/spec+bad': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'fcfs-p/nospec': None, 'fcfs-p/spec': None, 'fcfs-p/spec+bad': None, 'plugin-d/both': None, 'plugin-p/both': None, 'plugin-p/spec+bad': None, 'prio-d/both': None, 'prio-p/both': None, 'prio-p/spec+bad': None}
- goodput < 0.5 first at: {'cap-d/both': None, 'cap-p/both': None, 'cap-p/spec+bad': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'fcfs-p/nospec': None, 'fcfs-p/spec': None, 'fcfs-p/spec+bad': None, 'plugin-d/both': None, 'plugin-p/both': None, 'plugin-p/spec+bad': None, 'prio-d/both': None, 'prio-p/both': None, 'prio-p/spec+bad': None}
- wall half alone < 0.5 first at: {'cap-d/both': None, 'cap-p/both': None, 'cap-p/spec+bad': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'fcfs-p/nospec': None, 'fcfs-p/spec': None, 'fcfs-p/spec+bad': None, 'plugin-d/both': None, 'plugin-p/both': None, 'plugin-p/spec+bad': None, 'prio-d/both': None, 'prio-p/both': None, 'prio-p/spec+bad': None}
- root TPOT half alone < 0.5 first at: {'cap-d/both': None, 'cap-p/both': None, 'cap-p/spec+bad': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'fcfs-p/nospec': None, 'fcfs-p/spec': None, 'fcfs-p/spec+bad': None, 'plugin-d/both': None, 'plugin-p/both': None, 'plugin-p/spec+bad': None, 'prio-d/both': None, 'prio-p/both': None, 'prio-p/spec+bad': None}
- most sessions per minute at: {'cap-d/both': 4, 'cap-p/both': 4, 'cap-p/spec+bad': 4, 'fcfs-d/nospec': 4, 'fcfs-d/spec': 4, 'fcfs-d/spec+bad': 4, 'fcfs-p/nospec': 4, 'fcfs-p/spec': 4, 'fcfs-p/spec+bad': 4, 'plugin-d/both': 4, 'plugin-p/both': 4, 'plugin-p/spec+bad': 4, 'prio-d/both': 4, 'prio-p/both': 4, 'prio-p/spec+bad': 4}
- spec+bad no faster than nospec first at: {'fcfs': None, 'prio': None, 'plugin': None}
- prio/spec+bad vs fcfs/spec+bad (ratio, < 1 better): {}
- plugin/spec+bad vs fcfs/spec+bad: {}

## Pressure: each arm against its reference, same load

References: `fcfs-p/spec+bad` on the pressure servers (one T4 KV config, sweep/pressure.json), `fcfs-d/spec+bad` on the default servers. Ratios < 1 are faster; under 100 sessions a p99 is the slowest session. Decoys and real bets (speculative calls sent as bets, workload `both`): share logged rejected (refused, or dropped before its first token: the client cannot tell them apart) / dropped (after one). Bets per call: real bets over the distinct calls they were for; spec-ptc bets again on a call whose bet failed (a re-peek, then its statement), the simulator does not (1.0). Re-runs: calls run for real at their claim after their bets were refused. Shadow stops: sessions whose spec-ptc shadow stopped at a refused bet it forced. Preempt: vLLM's counter, per run (a bet the plugin drops is not in it). Max wait: most requests waiting in a 1-s sample. Queue: share of 1-s samples with one waiting, mean over runs. KV peak: vLLM's KV usage, highest sample.

| arm | agents | session p50 | p99 | root TPOT p50 | p99 | decoys rejected / dropped | real bets rejected / dropped | bets per call | re-runs | shadow stops | preempt | max wait | queue | KV peak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-p/nospec | 4 | 1.641 | 1.055 | 0.633 | 0.333 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.27 |
| fcfs-p/spec | 4 | 0.667 | 0.587 | 0.773 | 0.435 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.70 |
| fcfs-p/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 | - | - | 0 | 0/48 | 192.0 | 49 | 42% | 1.00 |
| prio-p/spec+bad | 4 | 0.870 | 0.807 | 1.022 | 0.597 | 0.00 / 0.00 | - | - | 0 | 0/48 | 147.7 | 31 | 42% | 1.00 |
| cap-p/spec+bad | 4 | 0.689 | 0.601 | 0.794 | 0.436 | 0.95 / 0.00 | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.90 |
| plugin-p/spec+bad | 4 | 0.676 | 0.589 | 0.782 | 0.435 | 0.97 / 0.00 | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.83 |
| prio-p/both | 4 | 0.915 | 0.997 | 1.005 | 0.570 | 0.00 / 0.00 | 0.00 / 0.00 | 1.12 | 0 | 0/48 | 240.0 | 40 | 52% | 1.00 |
| cap-p/both | 4 | 1.505 | 1.104 | 0.680 | 0.360 | 0.85 / 0.00 | 0.91 / 0.00 | 1.73 | 345 | 34/48 | 0.0 | 0 | 0% | 0.48 |
| plugin-p/both | 4 | 1.506 | 1.127 | 0.682 | 0.369 | 0.83 / 0.00 | 0.94 / 0.00 | 1.67 | 363 | 35/48 | 0.0 | 0 | 0% | 0.49 |
| fcfs-d/nospec | 4 | 1.947 | 1.347 | 0.629 | 0.573 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.01 |
| fcfs-d/spec | 4 | 0.782 | 0.746 | 0.759 | 0.734 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.02 |
| fcfs-d/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| prio-d/both | 4 | 1.004 | 1.017 | 1.000 | 0.996 | 0.00 / 0.00 | 0.00 / 0.00 | 1.12 | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| cap-d/both | 4 | 1.780 | 1.433 | 0.675 | 0.616 | 0.86 / 0.00 | 0.92 / 0.00 | 1.72 | 355 | 35/48 | 0.0 | 0 | 0% | 0.01 |
| plugin-d/both | 4 | 1.766 | 1.422 | 0.677 | 0.621 | 0.83 / 0.00 | 0.92 / 0.00 | 1.66 | 362 | 34/48 | 0.0 | 0 | 0% | 0.01 |

Decision rule on these values: the plugin wins if its session p50 is at most 0.95x the cap's at 4 agents in `decoys` or `both` on the pressure servers, with the pressure check passed.

- decoys: plugin-p/spec+bad / cap-p/spec+bad 0.982, / prio-p/spec+bad 0.778
- both: plugin-p/both / cap-p/both 1.000, / prio-p/both 1.646
- both, default servers: plugin-d/both / cap-d/both 0.992, / prio-d/both 1.758 (no pressure: reported, not part of the rule)
- pressure check (per run; queue: share of 1-s samples, the simulator's is a share of time): fcfs-p/spec+bad 192.0 preemptions, queue 42% (clearly: >= 16 preemptions or a queue >= 25%); fcfs-p/spec 0.0 preemptions, queue 0% (barely: <= 2 and <= 5%). Passed: yes
- plugin wins: no

## Baselines (B4) against `fcfs-b4/spec+bad` (session p50 / root TPOT p50 / p99; < 1 better)

Sub-call tokens: sub-call completion tokens per session, same ratio; away from 1, the arms did not run the same amount of work (sub-calls stop at EOS). vs no bets: session p50 against `fcfs-b4/spec`, stock FCFS without bad guesses. Every B4 bet is a worthless decoy, so refusing every bet is the best a gate can do here: an arm near 1.0 in that column has refused (nearly) all bets, and B4 cannot show a cost of refusing too many. Decoys refused: share of decoys logged rejected. Prefix hits: the server's prefix-cache hit share over the arm's runs ('-': no counter).

| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens | vs no bets | decoys refused | prefix hits |
|---|---|---|---|---|---|---|---|---|

## Against stock FCFS, same mode (session p50 / root TPOT p50 / p99; > 1 slower)

Last column: sub-call completion tokens per session, same ratio. Both arms send the same prompts, but sub-calls stop at EOS: a ratio away from 1 means the arms did not run the same amount of work.

| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens |
|---|---|---|---|---|---|

## Goodput curve (both thresholds = multiplier)

| arm | agents | 1.0x | 1.25x | 1.5x | 1.75x | 2.0x | 2.5x | 3.0x | 4.0x | 5.0x |
|---|---|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | - | - | - | - | - | - | - | - | - |
| cap-p/both | 4 | - | - | - | - | - | - | - | - | - |
| cap-p/spec+bad | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-d/nospec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-d/spec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-d/spec+bad | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-p/nospec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-p/spec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-p/spec+bad | 4 | - | - | - | - | - | - | - | - | - |
| plugin-d/both | 4 | - | - | - | - | - | - | - | - | - |
| plugin-p/both | 4 | - | - | - | - | - | - | - | - | - |
| plugin-p/spec+bad | 4 | - | - | - | - | - | - | - | - | - |
| prio-d/both | 4 | - | - | - | - | - | - | - | - | - |
| prio-p/both | 4 | - | - | - | - | - | - | - | - | - |
| prio-p/spec+bad | 4 | - | - | - | - | - | - | - | - | - |

## Per server launch (GPU: lowest SM clock MHz and peak temperature C over the launch's runs; '-' without nvidia-smi)

| arm | agents | launch | first run (UTC) | sessions | session p50 s | root TPOT p50 ms | GPU SM min | GPU temp max |
|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | fcfs#2 | 2026-10-29T19:09:47Z | 32 | 12.24 | 20.1 | 525 | 78 |
| cap-d/both | 4 | fcfs#3 | 2026-10-29T19:27:19Z | 16 | 8.97 | 20.0 | 960 | 78 |
| cap-p/both | 4 | fcfs_p#2 | 2026-10-29T18:36:21Z | 32 | 12.01 | 20.3 | 480 | 78 |
| cap-p/both | 4 | fcfs_p#3 | 2026-10-29T18:56:54Z | 16 | 9.02 | 20.2 | 450 | 78 |
| cap-p/spec+bad | 4 | fcfs_p#2 | 2026-10-29T18:36:00Z | 32 | 4.15 | 23.6 | 1005 | 78 |
| cap-p/spec+bad | 4 | fcfs_p#3 | 2026-10-29T18:56:33Z | 16 | 4.13 | 23.7 | 960 | 77 |
| fcfs-d/nospec | 4 | fcfs#2 | 2026-10-29T19:08:15Z | 32 | 10.05 | 18.7 | 990 | 78 |
| fcfs-d/nospec | 4 | fcfs#3 | 2026-10-29T19:28:05Z | 16 | 9.81 | 18.8 | 975 | 77 |
| fcfs-d/spec | 4 | fcfs#2 | 2026-10-29T19:09:00Z | 32 | 3.95 | 22.6 | 1020 | 78 |
| fcfs-d/spec | 4 | fcfs#3 | 2026-10-29T19:26:32Z | 16 | 3.94 | 22.6 | 1065 | 77 |
| fcfs-d/spec+bad | 4 | fcfs#2 | 2026-10-29T19:09:21Z | 32 | 5.04 | 29.8 | 945 | 78 |
| fcfs-d/spec+bad | 4 | fcfs#3 | 2026-10-29T19:26:52Z | 16 | 5.06 | 30.0 | 1020 | 78 |
| fcfs-p/nospec | 4 | fcfs_p#2 | 2026-10-29T18:34:21Z | 32 | 10.16 | 18.8 | 975 | 78 |
| fcfs-p/nospec | 4 | fcfs_p#3 | 2026-10-29T18:57:40Z | 16 | 9.83 | 18.9 | 990 | 77 |
| fcfs-p/spec | 4 | fcfs_p#2 | 2026-10-29T18:35:06Z | 32 | 4.00 | 23.0 | 735 | 78 |
| fcfs-p/spec | 4 | fcfs_p#3 | 2026-10-29T18:55:40Z | 16 | 4.04 | 23.0 | 1065 | 78 |
| fcfs-p/spec+bad | 4 | fcfs_p#2 | 2026-10-29T18:35:27Z | 32 | 6.08 | 29.8 | 930 | 78 |
| fcfs-p/spec+bad | 4 | fcfs_p#3 | 2026-10-29T18:56:01Z | 16 | 5.99 | 29.8 | 990 | 78 |
| plugin-d/both | 4 | plugin#1 | 2026-10-29T19:17:26Z | 32 | 12.08 | 20.3 | 465 | 78 |
| plugin-d/both | 4 | plugin#2 | 2026-10-29T19:21:07Z | 16 | 8.90 | 20.0 | 900 | 77 |
| plugin-p/both | 4 | plugin_p#1 | 2026-10-29T18:45:40Z | 32 | 12.05 | 20.2 | 525 | 78 |
| plugin-p/both | 4 | plugin_p#2 | 2026-10-29T18:49:16Z | 16 | 9.02 | 20.4 | 540 | 82 |
| plugin-p/spec+bad | 4 | plugin_p#1 | 2026-10-29T18:45:19Z | 32 | 4.05 | 23.4 | 960 | 82 |
| plugin-p/spec+bad | 4 | plugin_p#2 | 2026-10-29T18:50:03Z | 16 | 4.05 | 23.1 | 990 | 77 |
| prio-d/both | 4 | priority#1 | 2026-10-29T19:14:28Z | 32 | 5.07 | 29.8 | 1005 | 82 |
| prio-d/both | 4 | priority#2 | 2026-10-29T19:23:37Z | 16 | 5.06 | 30.6 | 1020 | 81 |
| prio-p/both | 4 | priority_p#1 | 2026-10-29T18:42:02Z | 32 | 5.48 | 29.9 | 810 | 78 |
| prio-p/both | 4 | priority_p#2 | 2026-10-29T18:52:08Z | 16 | 5.62 | 30.0 | 1020 | 82 |
| prio-p/spec+bad | 4 | priority_p#1 | 2026-10-29T18:41:34Z | 32 | 5.28 | 30.7 | 705 | 81 |
| prio-p/spec+bad | 4 | priority_p#2 | 2026-10-29T18:52:43Z | 16 | 5.15 | 30.1 | 825 | 77 |
