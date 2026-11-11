# Sweep summary

SLO per session: wall <= 2.0x and root TPOT <= 2.0x the `fcfs/nospec` arm at 1 agent, same pattern. Goodput = fraction of sessions meeting it; wall / TPOT = each half alone. Root TPOT is each session's mean; p50 and p99 are across sessions. Brackets: 95% bootstrap CI (repeats, then sessions); none for p99s. 'max': under 100 sessions, so the p99 is the slowest session. host CPU: whole host, mean over the run (max over repeats); cpu ok: every run below 0.85 with under 10% of seconds saturated.

| arm | agents | reps | session p50 s | session p99 s | root TPOT p50 ms | root TPOT p99 ms | sessions/min | goodput | wall / TPOT | decoys | preempt | max wait | client CPU | host CPU | cpu ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | 3 | 8.27 [7.08, 11.36] | 17.26 (max) | 18.5 [18.4, 18.6] | 19.0 (max) | 23.5 | - | - / - | completed:102,rejected:594 | 0 | 0 | 0.01 | 0.04 | yes |
| fcfs-d/nospec | 4 | 3 | 9.15 [6.94, 11.73] | 16.56 (max) | 17.4 [17.4, 17.5] | 17.7 (max) | 25.2 | - | - / - | - | 0 | 0 | 0.01 | 0.03 | yes |
| fcfs-d/spec | 4 | 3 | 3.59 [3.08, 3.69] | 8.96 (max) | 20.5 [20.1, 20.6] | 22.1 (max) | 53.2 | - | - / - | - | 0 | 0 | 0.02 | 0.05 | yes |
| fcfs-d/spec+bad | 4 | 3 | 4.52 [4.18, 4.97] | 11.68 (max) | 26.4 [25.5, 27.2] | 29.8 (max) | 41.8 | - | - / - | cancelled:264,completed:276 | 0 | 0 | 0.01 | 0.05 | yes |
| plugin-d/both | 4 | 3 | 9.87 [7.34, 11.41] | 17.27 (max) | 18.5 [18.3, 18.7] | 19.0 (max) | 23.4 | - | - / - | completed:106,rejected:560 | 0 | 0 | 0.01 | 0.05 | yes |
| prio-d/both | 4 | 3 | 4.52 [4.17, 4.97] | 11.64 (max) | 26.5 [25.3, 27.2] | 29.6 (max) | 42.0 | - | - / - | cancelled:264,completed:276 | 0 | 0 | 0.01 | 0.05 | yes |

## Derived

- knee (session p50 >= 2x own 1-agent): {'cap-d/both': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'plugin-d/both': None, 'prio-d/both': None}
- knee against stock FCFS's 1-agent p50, same mode: {'cap-d/both': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'plugin-d/both': None, 'prio-d/both': None}
- goodput < 0.5 first at: {'cap-d/both': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'plugin-d/both': None, 'prio-d/both': None}
- wall half alone < 0.5 first at: {'cap-d/both': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'plugin-d/both': None, 'prio-d/both': None}
- root TPOT half alone < 0.5 first at: {'cap-d/both': None, 'fcfs-d/nospec': None, 'fcfs-d/spec': None, 'fcfs-d/spec+bad': None, 'plugin-d/both': None, 'prio-d/both': None}
- most sessions per minute at: {'cap-d/both': 4, 'fcfs-d/nospec': 4, 'fcfs-d/spec': 4, 'fcfs-d/spec+bad': 4, 'plugin-d/both': 4, 'prio-d/both': 4}
- spec+bad no faster than nospec first at: {'fcfs': None, 'prio': None, 'plugin': None}
- prio/spec+bad vs fcfs/spec+bad (ratio, < 1 better): {}
- plugin/spec+bad vs fcfs/spec+bad: {}

## Pressure: each arm against its reference, same load

References: `fcfs-p/spec+bad` on the pressure servers (one T4 KV config, sweep/pressure.json), `fcfs-d/spec+bad` on the default servers. Ratios < 1 are faster; under 100 sessions a p99 is the slowest session. Decoys and real bets (speculative calls sent as bets, workload `both`): share logged rejected (refused, or dropped before its first token: the client cannot tell them apart) / dropped (after one). Bets per call: real bets over the distinct calls they were for; spec-ptc bets again on a call whose bet failed (a re-peek, then its statement), the simulator does not (1.0). Re-runs: calls run for real at their claim after their bets were refused. Shadow stops: sessions whose spec-ptc shadow stopped at a refused bet it forced. Preempt: vLLM's counter, per run (a bet the plugin drops is not in it). Max wait: most requests waiting in a 1-s sample. Queue: share of 1-s samples with one waiting, mean over runs. KV peak: vLLM's KV usage, highest sample.

| arm | agents | session p50 | p99 | root TPOT p50 | p99 | decoys rejected / dropped | real bets rejected / dropped | bets per call | re-runs | shadow stops | preempt | max wait | queue | KV peak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-d/nospec | 4 | 2.024 | 1.417 | 0.660 | 0.595 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.01 |
| fcfs-d/spec | 4 | 0.795 | 0.767 | 0.778 | 0.742 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.02 |
| fcfs-d/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| prio-d/both | 4 | 1.000 | 0.997 | 1.002 | 0.995 | 0.00 / 0.00 | 0.00 / 0.00 | 1.12 | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| cap-d/both | 4 | 1.830 | 1.477 | 0.700 | 0.638 | 0.85 / 0.00 | 0.90 / 0.00 | 1.70 | 342 | 34/48 | 0.0 | 0 | 0% | 0.01 |
| plugin-d/both | 4 | 2.183 | 1.479 | 0.700 | 0.637 | 0.84 / 0.00 | 0.93 / 0.00 | 1.65 | 355 | 36/48 | 0.0 | 0 | 0% | 0.01 |

Decision rule on these values: the plugin wins if its session p50 is at most 0.95x the cap's at 4 agents in `decoys` or `both` on the pressure servers, with the pressure check passed.

- decoys: plugin-p/spec+bad / cap-p/spec+bad -, / prio-p/spec+bad -
- both: plugin-p/both / cap-p/both -, / prio-p/both -
- both, default servers: plugin-d/both / cap-d/both 1.193, / prio-d/both 2.184 (no pressure: reported, not part of the rule)
- pressure check (per run; queue: share of 1-s samples, the simulator's is a share of time): fcfs-p/spec+bad - (clearly: >= 16 preemptions or a queue >= 25%); fcfs-p/spec - (barely: <= 2 and <= 5%). Passed: unknown (rows missing)
- plugin wins: unknown (rows missing)

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
| fcfs-d/nospec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-d/spec | 4 | - | - | - | - | - | - | - | - | - |
| fcfs-d/spec+bad | 4 | - | - | - | - | - | - | - | - | - |
| plugin-d/both | 4 | - | - | - | - | - | - | - | - | - |
| prio-d/both | 4 | - | - | - | - | - | - | - | - | - |

## Per server launch (GPU: lowest SM clock MHz and peak temperature C over the launch's runs; '-' without nvidia-smi)

| arm | agents | launch | first run (UTC) | sessions | session p50 s | root TPOT p50 ms | GPU SM min | GPU temp max |
|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | fcfs#1 | 2026-11-10T01:25:18Z | 32 | 10.72 | 18.5 | 1200 | 42 |
| cap-d/both | 4 | fcfs#2 | 2026-11-10T01:40:57Z | 16 | 8.27 | 18.5 | 1170 | 43 |
| fcfs-d/nospec | 4 | fcfs#1 | 2026-11-10T01:23:55Z | 32 | 9.43 | 17.4 | 1410 | 43 |
| fcfs-d/nospec | 4 | fcfs#2 | 2026-11-10T01:41:38Z | 16 | 9.15 | 17.5 | 1410 | 43 |
| fcfs-d/spec | 4 | fcfs#1 | 2026-11-10T01:24:36Z | 32 | 3.59 | 20.5 | 1230 | 43 |
| fcfs-d/spec | 4 | fcfs#2 | 2026-11-10T01:40:15Z | 16 | 3.59 | 20.6 | 1425 | 41 |
| fcfs-d/spec+bad | 4 | fcfs#1 | 2026-11-10T01:24:54Z | 32 | 4.52 | 26.4 | 1335 | 42 |
| fcfs-d/spec+bad | 4 | fcfs#2 | 2026-11-10T01:40:34Z | 16 | 4.53 | 26.5 | 1380 | 42 |
| plugin-d/both | 4 | plugin#1 | 2026-11-10T01:32:18Z | 32 | 9.87 | 18.6 | 1290 | 41 |
| plugin-d/both | 4 | plugin#2 | 2026-11-10T01:35:28Z | 16 | 11.15 | 18.5 | 1380 | 41 |
| prio-d/both | 4 | priority#1 | 2026-11-10T01:29:42Z | 32 | 4.52 | 26.6 | 1365 | 42 |
| prio-d/both | 4 | priority#2 | 2026-11-10T01:37:48Z | 16 | 4.52 | 26.5 | 1320 | 40 |
