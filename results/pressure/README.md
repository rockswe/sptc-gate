# KV pressure and a real queue (simulated)

**SIMULATED, not measured.** Written 2026-10-29T15:14:25Z by `experiments/pressure.py`, before any GPU run of the pressure preset. One deterministic simulator run per point (no repeats, no CIs). Code: commit `33ecbf27db` (clean tree).

Calibration: prereg_v3's P1, not refit (client 30 ms each way, seq_cap 24). 4 agents, mix4, 4 turns each. Cap: run 2's client-side window cap (window:8).

## The question and the rule

Does the plugin beat the client-side cap and vLLM priority under KV pressure and a real queue, with bets that are sometimes needed? The plugin wins if its session p50 is at least 5% below the cap's at 4 agents, in either workload, with the pressure check passed.

## Answer (simulated)

On the chosen T4 config (0.75x peak (256 blocks), 256 seqs), **the plugin does not win**.

| workload | plugin vs cap (session p50) | plugin vs priority |
|---|---|---|
| decoys | 0.988 | 0.750 |
| both | 1.000 | 1.444 |

What happens there. In `decoys` the cap and the plugin refuse 94% and 96% of the decoys, so the decoys never build the KV pressure that preempts fcfs-p/spec+bad 57 times (KV peaks 148 and 140 of 256 blocks). Both run close to fcfs-p/spec (0.745, 0.737, 0.715 of fcfs-p/spec+bad), and priority, which only reorders, is at 0.982. In `both` they refuse 85% and 81% of the real bets too. The shadow forces nearly every speculation, so it stops in 16 and 16 of 16 sessions, and both run close to no speculation: 1.413 and 1.413 of fcfs-p/spec+bad, with fcfs-p/nospec at 1.464. Priority admits every bet and is at 0.979.

Across the grid (below 1: the plugin is faster; the rule needs <= 0.95 against the cap):

| config | pressure check | decoys: plugin vs cap | vs prio | both: plugin vs cap | vs prio |
|---|---|---|---|---|---|
| default KV (5369 blocks), 256 seqs | no clear pressure | 0.988 | 0.765 | 1.000 | 1.469 |
| default KV (5369 blocks), 32 seqs | passed | 0.991 | 0.774 | 1.000 | 1.359 |
| default KV (5369 blocks), 16 seqs | fcfs-p/spec under pressure too | 0.987 | 0.817 | 1.000 | 0.932 |
| 1x peak (341 blocks), 256 seqs | no clear pressure | 0.988 | 0.765 | 1.000 | 1.469 |
| 1x peak (341 blocks), 32 seqs | passed | 0.991 | 0.774 | 1.000 | 1.359 |
| 1x peak (341 blocks), 16 seqs | fcfs-p/spec under pressure too | 0.987 | 0.817 | 1.000 | 0.932 |
| 0.75x peak (256 blocks), 256 seqs | passed | 0.988 | 0.750 | 1.000 | 1.444 |
| 0.75x peak (256 blocks), 32 seqs | passed | 0.991 | 0.774 | 1.000 | 1.359 |
| 0.75x peak (256 blocks), 16 seqs | fcfs-p/spec under pressure too | 0.987 | 0.817 | 1.000 | 0.932 |
| 0.5x peak (170 blocks), 256 seqs | passed | 0.988 | 0.744 | 1.000 | 1.282 |
| 0.5x peak (170 blocks), 32 seqs | passed | 0.991 | 0.759 | 1.000 | 1.311 |
| 0.5x peak (170 blocks), 16 seqs | fcfs-p/spec under pressure too | 0.987 | 0.817 | 1.000 | 0.932 |

Sensitivity on the chosen config (plugin vs cap; decoys / both): P0 0.990 / 1.000; P1-alt 0.990 / 1.000; P1, reissue 0.988 / 1.010. P0 and P1-alt are prereg_v3's other calibration sets. 'reissue' re-runs a forced refused bet at once and keeps the shadow going, where spec-ptc stops it. Most of the gates' loss in `both` is that stop: with 'reissue', cap-p/both and plugin-p/both run at 1.026 and 1.036 of fcfs-p/spec+bad, not 1.413 and 1.413.

## The T4 config

- Chosen: 0.75x peak (256 blocks), 256 seqs. vLLM flags: `--num-gpu-blocks-override 257 --max-num-seqs 256 --max-model-len 512`.
- Fallback (half the blocks), if the probe shows neither preemption nor a queue in fcfs-p/spec+bad: `--num-gpu-blocks-override 129 --max-num-seqs 256 --max-model-len 512`.
- `--max-model-len 512`: twice the bench's longest request, rounded up to 128 (roots 209 tokens, sub-calls 151, decoys 154; prompt + max_tokens).
- KV peak of fcfs-p/spec+bad on the default server: 341 blocks (16 tokens each), the grid's 1x. vLLM keeps one block as its null block, so the override is the simulated blocks + 1.

Chosen by `choose_config` from the stock FCFS arms only; the script writes `choice.json` before it simulates any other arm under pressure. Rule: the mildest config where fcfs-p/spec+bad preempts or queues clearly and fcfs-p/spec barely does. 'clearly': >= 16 preemptions per run (16 sessions) or a queue >= 25% of the run's time. 'barely': <= 2 preemptions and a queue <= 5% of the time. Mildest: the smallest fcfs-p/spec+bad slowdown against the default server (equal to 0.1%: the most blocks, then the most seqs).

How the rule was set: the thresholds were written before any run. Two changes followed, both before this run. (1) A scratch run of every arm showed the cap and the plugin refusing real bets far more often than decoys in `both`: a burst's decoys all reached the gate before its real calls. The bench starts each decoy inside its real call, so the arms now use `decoy_at_call`, a fidelity fix to the simulator, not a choice of config. (2) Under that timing, 256 blocks / 256 seqs slowed fcfs-p/spec+bad 3.9% instead of 5.1%, across a 5% cost floor that had been added to 'clearly' beyond the rule's wording. The floor was dropped, back to the rule's 'preempts or queues clearly', looking at stock FCFS arms only; with the floor the rule would have picked default KV with 32 seqs (no KV pressure, and 'half the blocks' would not be a fallback). In that scratch run, under the old timing, plugin vs cap was 0.983-0.984 (decoys) and 1.008 (both) on every config, so it favoured no config.

| config | spec+bad: slowdown | preemptions | queue | max waiting | KV peak | spec: slowdown | preemptions | queue | clearly | barely |
|---|---|---|---|---|---|---|---|---|---|---|
| default KV (5369 blocks), 256 seqs | 1.000 | 0 | 0% | 0 | 341 | 1.000 | 0 | 0% | no | yes |
| default KV (5369 blocks), 32 seqs | 1.077 | 0 | 57% | 37 | 272 | 1.000 | 0 | 2% | yes | yes |
| default KV (5369 blocks), 16 seqs | 1.643 | 0 | 91% | 50 | 136 | 0.985 | 0 | 20% | yes | no |
| 1x peak (341 blocks), 256 seqs | 1.000 | 0 | 0% | 0 | 341 | 1.000 | 0 | 0% | no | yes |
| 1x peak (341 blocks), 32 seqs | 1.077 | 0 | 57% | 37 | 272 | 1.000 | 0 | 2% | yes | yes |
| 1x peak (341 blocks), 16 seqs | 1.643 | 0 | 91% | 50 | 136 | 0.985 | 0 | 20% | yes | no |
| 0.75x peak (256 blocks), 256 seqs | 1.039 | 57 | 20% | 20 | 256 | 1.000 | 0 | 0% | yes | yes |
| 0.75x peak (256 blocks), 32 seqs | 1.077 | 3 | 57% | 37 | 256 | 1.000 | 0 | 2% | yes | yes |
| 0.75x peak (256 blocks), 16 seqs | 1.643 | 0 | 91% | 50 | 136 | 0.985 | 0 | 20% | yes | no |
| 0.5x peak (170 blocks), 256 seqs | 1.286 | 139 | 61% | 50 | 170 | 1.000 | 0 | 0% | yes | yes |
| 0.5x peak (170 blocks), 32 seqs | 1.251 | 110 | 64% | 42 | 170 | 1.000 | 0 | 2% | yes | yes |
| 0.5x peak (170 blocks), 16 seqs | 1.643 | 0 | 91% | 50 | 136 | 0.985 | 0 | 20% | yes | no |

## Every arm on the chosen config (0.75x peak (256 blocks), 256 seqs)

Ratios to fcfs-p/spec+bad, as the bench's Pressure table. 'refused' counts a bet dropped before its first token too (the client cannot tell them apart); 'bets dropped' are running bets the plugin dropped (not preemptions: vLLM's counter does not see them). Queue: share of the run with a request waiting.

| arm | session p50 s | vs fcfs-p/spec+bad: session p50 | p99 | root TPOT p50 | p99 | decoys refused | real bets refused / dropped | preemptions | bets dropped | max waiting | KV peak blocks | queue (time) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-p/nospec | 7.14 | 1.464 | 2.030 | 0.586 | 0.466 | - | - | 0 | 0 | 0 | 35 | 0% |
| fcfs-p/spec | 3.49 | 0.715 | 0.724 | 0.731 | 0.617 | - | - | 0 | 0 | 0 | 140 | 0% |
| fcfs-p/spec+bad | 4.88 | 1.000 | 1.000 | 1.000 | 1.000 | 0% | - | 57 | 0 | 20 | 256 | 20% |
| prio-p/spec+bad | 4.79 | 0.982 | 0.989 | 0.994 | 0.849 | 0% | - | 53 | 0 | 21 | 256 | 20% |
| cap-p/spec+bad | 3.64 | 0.745 | 0.747 | 0.761 | 0.639 | 94% | - | 0 | 0 | 0 | 148 | 0% |
| plugin-p/spec+bad | 3.59 | 0.737 | 0.739 | 0.749 | 0.626 | 96% | - | 0 | 0 | 0 | 140 | 0% |
| prio-p/both | 4.78 | 0.979 | 0.993 | 0.991 | 0.841 | 0% | 0% / 0% | 44 | 0 | 23 | 256 | 20% |
| cap-p/both | 6.90 | 1.413 | 2.152 | 0.622 | 0.501 | 79% | 85% / 0% | 0 | 0 | 0 | 57 | 0% |
| plugin-p/both | 6.90 | 1.413 | 2.158 | 0.626 | 0.508 | 77% | 81% / 0% | 0 | 0 | 0 | 60 | 0% |

## Every arm on the fallback config (0.3754x peak (128 blocks), 256 seqs)

| arm | session p50 s | vs fcfs-p/spec+bad: session p50 | p99 | root TPOT p50 | p99 | decoys refused | real bets refused / dropped | preemptions | bets dropped | max waiting | KV peak blocks | queue (time) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-p/nospec | 7.14 | 1.023 | 1.014 | 0.668 | 0.624 | - | - | 0 | 0 | 0 | 35 | 0% |
| fcfs-p/spec | 3.49 | 0.499 | 0.362 | 0.835 | 0.828 | - | - | 4 | 0 | 3 | 128 | 2% |
| fcfs-p/spec+bad | 6.98 | 1.000 | 1.000 | 1.000 | 1.000 | 0% | - | 183 | 0 | 48 | 128 | 78% |
| prio-p/spec+bad | 4.82 | 0.690 | 0.485 | 1.072 | 1.073 | 0% | - | 127 | 0 | 49 | 128 | 82% |
| cap-p/spec+bad | 3.64 | 0.521 | 0.374 | 0.868 | 0.856 | 94% | - | 5 | 0 | 5 | 128 | 4% |
| plugin-p/spec+bad | 3.60 | 0.515 | 0.369 | 0.858 | 0.839 | 96% | - | 4 | 0 | 3 | 128 | 2% |
| prio-p/both | 6.33 | 0.907 | 0.820 | 1.017 | 0.992 | 0% | 0% / 0% | 169 | 0 | 54 | 128 | 78% |
| cap-p/both | 6.90 | 0.988 | 1.075 | 0.710 | 0.671 | 79% | 85% / 0% | 0 | 0 | 0 | 57 | 0% |
| plugin-p/both | 6.90 | 0.988 | 1.078 | 0.714 | 0.680 | 77% | 81% / 0% | 0 | 0 | 0 | 60 | 0% |

Here fcfs-p/spec fills the KV too (128 of 128 blocks, 4 preemptions): the fallback is meant for a T4 that needs less KV than the simulator predicts.

## `both` without pressure (default server)

Step 5 of the GPU run uses `both` on the default servers only if this predicts an effect over 5%. Session p50 against fcfs-p/spec+bad (which is fcfs both): prio-p/both 1.000, cap-p/both 1.469, plugin-p/both 1.469; plugin vs cap 1.000. Largest effect 46.9%: **over 5%, run step 5**.

## Every arm on every config

`grid.csv` (one row per config and arm) and `grid.json` (the same, plus each run's session times and the choice).

## Consistency checks (all hold)

- fcfs-p/nospec with v3's decoy timing = prereg_v3 fcfs/nospec: session p50 7.1431 s.
- fcfs-p/spec with v3's decoy timing = prereg_v3 fcfs/spec: session p50 3.4872 s.
- fcfs-p/spec+bad with v3's decoy timing = prereg_v3 fcfs/spec+bad: session p50 4.6955 s.
- prio-p/spec+bad with v3's decoy timing = prereg_v3 prio-bets/spec+bad: session p50 4.6955 s.
- cap-p/spec+bad with v3's decoy timing = prereg_v3 proxy/spec+bad: session p50 3.6538 s.
- plugin-p/spec+bad with early tags and v3's decoy timing = prereg_v3 plugin/spec+bad: session p50 3.5847 s.
- fcfs both = fcfs-p/spec+bad: session p50 4.6955 s.

## Limits

- The simulator's KV model follows vLLM 0.32's code (full-sequence admission, resume from the prefix cache, one LRU free queue) but has never been checked under heavy preemption. The T4 run is that check.
- A forced rejected bet stops spec-ptc's shadow for the rest of the turn; the sim models that (rejected_force abort). In this workload the shadow forces nearly every speculation, so in `both` almost any refused real bet stops it.
- One deterministic run per point; the client's CPU and network are not modelled; the 1-second metrics poller sees less than the peaks here.
- vLLM's preemption counter misses the plugin's dropped bets; the sim counts them apart ('bets dropped').
