# Sweep summary

SLO per session: wall <= 2.0x and root TPOT <= 2.0x the `fcfs/nospec` arm at 1 agent, same pattern. Goodput = fraction of sessions meeting it; wall / TPOT = each half alone. Root TPOT is each session's mean; p50 and p99 are across sessions. Brackets: 95% bootstrap CI (repeats, then sessions); none for p99s. 'max': under 100 sessions, so the p99 is the slowest session. host CPU: whole host, mean over the run (max over repeats); cpu ok: every run below 0.85 with under 10% of seconds saturated.

| arm | agents | reps | session p50 s | session p99 s | root TPOT p50 ms | root TPOT p99 ms | sessions/min | goodput | wall / TPOT | decoys | preempt | max wait | client CPU | host CPU | cpu ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cap-d/both | 4 | 3 | 10.09 [5.59, 11.48] | 15.75 (max) | 19.1 [18.9, 19.2] | 19.6 (max) | 26.2 | - | - / - | completed:135,rejected:405 | 0 | 0 | 0.01 | 0.04 | yes |
| fcfs-d/nospec | 4 | 3 | 9.25 [7.02, 11.85] | 16.73 (max) | 17.6 [17.6, 17.7] | 17.9 (max) | 25.0 | - | - / - | - | 0 | 0 | 0.01 | 0.03 | yes |
| fcfs-d/spec | 4 | 3 | 3.64 [3.12, 3.75] | 9.10 (max) | 20.8 [20.4, 21.1] | 22.5 (max) | 52.6 | - | - / - | - | 0 | 0 | 0.02 | 0.04 | yes |
| fcfs-d/spec+bad | 4 | 3 | 4.62 [4.28, 5.07] | 11.90 (max) | 26.6 [25.9, 27.8] | 30.1 (max) | 41.0 | - | - / - | cancelled:252,completed:288 | 0 | 0 | 0.01 | 0.04 | yes |
| plugin-d/both | 4 | 3 | 10.08 [5.49, 10.74] | 15.71 (max) | 19.1 [18.8, 19.2] | 19.6 (max) | 25.7 | - | - / - | completed:136,rejected:404 | 0 | 0 | 0.01 | 0.04 | yes |
| prio-d/both | 4 | 3 | 4.58 [4.25, 5.04] | 11.85 (max) | 26.9 [25.8, 27.6] | 30.2 (max) | 41.3 | - | - / - | cancelled:264,completed:276 | 0 | 0 | 0.01 | 0.05 | yes |

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
| fcfs-d/nospec | 4 | 2.002 | 1.406 | 0.662 | 0.595 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.01 |
| fcfs-d/spec | 4 | 0.789 | 0.765 | 0.782 | 0.746 | - | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.02 |
| fcfs-d/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 | - | - | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| prio-d/both | 4 | 0.991 | 0.996 | 1.011 | 1.001 | 0.00 / 0.00 | 0.00 / 0.00 | 1.12 | 0 | 0/48 | 0.0 | 0 | 0% | 0.04 |
| cap-d/both | 4 | 2.184 | 1.324 | 0.719 | 0.652 | 0.75 / 0.00 | 0.88 / 0.00 | 1.12 | 426 | 0/48 | 0.0 | 0 | 0% | 0.01 |
| plugin-d/both | 4 | 2.183 | 1.321 | 0.718 | 0.650 | 0.75 / 0.00 | 0.89 / 0.00 | 1.12 | 433 | 0/48 | 0.0 | 0 | 0% | 0.01 |

Decision rule on these values: the plugin wins if its session p50 is at most 0.95x the cap's at 4 agents in `decoys` or `both` on the pressure servers, with the pressure check passed.

- decoys: plugin-p/spec+bad / cap-p/spec+bad -, / prio-p/spec+bad -
- both: plugin-p/both / cap-p/both -, / prio-p/both -
- both, default servers: plugin-d/both / cap-d/both 1.000, / prio-d/both 2.202 (no pressure: reported, not part of the rule)
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
| cap-d/both | 4 | fcfs#2 | 2026-11-10T01:02:38Z | 32 | 10.53 | 19.2 | 1290 | 50 |
| cap-d/both | 4 | fcfs#3 | 2026-11-10T01:17:46Z | 16 | 10.09 | 19.1 | 1095 | 49 |
| fcfs-d/nospec | 4 | fcfs#2 | 2026-11-10T01:01:14Z | 32 | 9.54 | 17.6 | 1260 | 50 |
| fcfs-d/nospec | 4 | fcfs#3 | 2026-11-10T01:18:23Z | 16 | 9.25 | 17.6 | 1290 | 50 |
| fcfs-d/spec | 4 | fcfs#2 | 2026-11-10T01:01:56Z | 32 | 3.65 | 20.9 | 1305 | 50 |
| fcfs-d/spec | 4 | fcfs#3 | 2026-11-10T01:17:03Z | 16 | 3.64 | 20.8 | 1350 | 47 |
| fcfs-d/spec+bad | 4 | fcfs#2 | 2026-11-10T01:02:14Z | 32 | 4.66 | 26.6 | 1305 | 50 |
| fcfs-d/spec+bad | 4 | fcfs#3 | 2026-11-10T01:17:22Z | 16 | 4.60 | 27.0 | 1365 | 48 |
| plugin-d/both | 4 | plugin#1 | 2026-11-10T01:09:22Z | 32 | 10.08 | 19.1 | 1050 | 49 |
| plugin-d/both | 4 | plugin#2 | 2026-11-10T01:12:24Z | 16 | 10.33 | 19.2 | 1350 | 48 |
| prio-d/both | 4 | priority#1 | 2026-11-10T01:06:44Z | 32 | 4.59 | 27.0 | 1305 | 48 |
| prio-d/both | 4 | priority#2 | 2026-11-10T01:14:36Z | 16 | 4.58 | 26.9 | 1320 | 46 |
