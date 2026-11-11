# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| nospec | 1 (1) | 1728.4 | 1149.7 | 572.3 | 0.331 | - | 1.124 | - | 1.085 [1.011, 1.184] |
| stream | 1 (1) | 1537.9 | 1164.4 | 366.8 | 0.239 | 0.890 | - | 0.922 [0.845, 0.989] | - |
| scout | 1 (1) | 1541.9 | 1171.4 | 363.1 | 0.236 | 0.892 | 1.003 | 0.925 [0.847, 0.996] | 1.004 [0.996, 1.011] |
| wide | 1 (1) | 1344.8 | 1195.7 | 142.9 | 0.106 | 0.778 | 0.874 | 0.845 [0.673, 0.989] | 0.917 [0.786, 1.016] |
| nospec-wide | 1 (1) | 1592.8 | 1159.7 | 426.1 | 0.267 | 0.922 | 1.036 | 0.945 [0.903, 0.986] | 1.026 [0.972, 1.091] |

## The number reported first (cloud/PREREG_RECORD.md)

- `scout` over `stream`, summed session time, every replayable session: 1.003. Over the 10 replayed sessions alone: 1.003.
- 0 session(s) left out or dropped count as not recovered: 0 s added to both sums.
- The scout saves -4 s over the replayed sessions. Sessions giving a tenth of that or more: none.
- `wide` over `stream`: 0.874 (0.874 over the replayed sessions alone).
- By the rule fixed beforehand: above 0.95 (1.003): on unprovoked code the scout as built gains little at the shipped window.

## The predictions (cloud/PREREG_RECORD.md and its addendum, fixed before the replay)

| | prediction | measured | |
|---|---|---|---|
| M1 | every unit exact | 5 of 5 exact | held |
| M2 | in the fork's arms no call is sent twice and none is evicted | 0 sent twice or unrecorded, 0 evicted | held |
| M3 | a loop of single calls stays serial as shipped: `stream` at least 0.90 of `nospec` on each such turn | - | not testable |
| M4 | where the loop only stores or prints each result, `scout` at most 0.25 of `stream` on that turn | - | not testable |
| M5 | where the loop tests each result, `scout` at least 0.85 of `stream` on that turn | - | not testable |
| M6 | loops of batches: `scout` at 0.55 to 0.95 of `stream` over those turns, `wide` at most 0.45 | 0.990, 0.406 | **did not hold** |
| M7 | the number reported first (`scout` over `stream`, all replayable sessions) is at least 0.78 | 1.003 (1.003 over the 10 replayed sessions alone) | held |
| D1 | session time: `stream` at 0.83 to 0.95 of `nospec` (dry run: 0.888) | 0.890 | held |
| D2 | the number reported first, `scout` over `stream`, is 0.97 to 1.03 (dry run: 1.000) | 1.003 | held |
| D3 | session time: `wide` at 0.84 to 0.96 of `stream` (dry run: 0.892) | 0.874 | held |
| D4 | root stream seconds: `scout` within 5% of `stream` (dry run: 1.000) | 1.006 | held |
| D5 | root stream seconds: `wide` within 10% of `stream` (dry run: 1.033) | 1.027 | held |
| D6 | the largest loop of batches (`trec132k-17000237.fix1` turn 4, 159 batches of 20): `stream` at most 0.80 of `nospec` (dry run: 0.605) | 0.622 | held |
| D7 | the same turn: `wide` at most 0.50 of `stream` (dry run: 0.260) | 0.253 | held |
| D8 | the loop of batches that tests each result (`trec132k-17000237.fix2` turn 9): `stream` at least 0.85 of `nospec` (dry run: 0.999) | 1.003 | held |
| D9 | the same turn: `scout` at least 0.85 of `stream` (dry run: 1.000) | 0.977 | held |
| D10 | control, session time: `nospec-wide` at 0.86 to 0.98 of `nospec` (dry run: 0.929) | 0.922 | held |
| D11 | control: `wide` at most 0.93 of `nospec-wide` in session time (dry run: 0.853) | 0.844 | held |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | nospec s | stream s | scout s | wide s | nospec-wide s | nospec recovers | scout recovers | wide recovers | nospec-wide recovers |
|---|---|---|---|---|---|---|---|---|---|---|
| serial launches | 1 | 79.9 | 80.2 | 78.3 | 62.9 | 57.0 | 0% | 2% | 22% | 29% |
| burst over the cap | 7 | 486.4 | 286.3 | 284.4 | 79.6 | 363.1 | -70% | 1% | 72% | -27% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | nospec s | stream s | scout s | wide s | nospec-wide s |
|---|---|---|---|---|---|---|---|---|
| trec132k-17000237.fix1 | 4 | 3181 (0) | burst over the cap | 334.4 | 208.0 | 206.4 | 52.7 | 269.7 |
| trec132k-17000237.fix2 | 9 | 3185 (0) | serial launches | 79.9 | 80.2 | 78.3 | 62.9 | 57.0 |
| trec132k-17000237.fix1 | 6 | 3181 (0) | burst over the cap | 71.3 | 45.4 | 45.1 | 20.1 | 48.1 |
| pairs32k-1.fix2 | 4 | 786 (0) | burst over the cap | 19.3 | 10.5 | 10.4 | 4.5 | 15.8 |
| pairs32k-16.fix2 | 6 | 787 (0) | burst over the cap | 12.1 | 7.3 | 6.9 | 0.1 | 3.9 |
| pairs32k-16.fix1 | 8 | 40 (0) | burst over the cap | 8.3 | 6.9 | 7.1 | 2.0 | 3.3 |
| pairs32k-16.fix2 | 5 | 787 (0) | burst over the cap | 12.2 | 6.9 | 7.0 | 0.1 | 3.1 |
| pairs32k-1.fix1 | 4 | 787 (0) | burst over the cap | 28.6 | 1.2 | 1.5 | 0.1 | 19.1 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | nospec | stream | scout | wide | nospec-wide |
|---|---|---|---|---|---|
| pairs32k-1.fix1 | 98.7 (28.7) | 74.9 (1.3) | 76.4 (1.6) | 77.6 (0.1) | 92.1 (19.1) |
| pairs32k-1.fix2 | 90.2 (19.4) | 81.9 (10.6) | 80.6 (10.4) | 75.0 (4.6) | 84.8 (15.8) |
| pairs32k-15.fix1 | 232.3 (0.0) | 234.8 (0.0) | 234.9 (0.0) | 234.0 (0.1) | 233.4 (0.0) |
| pairs32k-16.fix1 | 155.1 (8.3) | 155.0 (7.0) | 155.9 (7.1) | 155.2 (2.0) | 151.8 (3.3) |
| pairs32k-16.fix2 | 115.5 (24.4) | 107.2 (14.2) | 105.4 (13.9) | 93.6 (0.3) | 98.0 (7.1) |
| trec132k-17000232.fix1 | 101.0 (0.4) | 101.2 (0.0) | 102.3 (0.0) | 105.5 (0.0) | 102.5 (0.4) |
| trec132k-17000237.fix1 | 486.4 (405.7) | 332.7 (253.4) | 332.3 (251.5) | 158.7 (72.8) | 398.3 (317.8) |
| trec132k-17000237.fix2 | 232.9 (80.5) | 235.0 (80.3) | 235.2 (78.4) | 219.8 (63.0) | 212.8 (57.5) |
| trec132k-17000241.fix1 | 107.6 (0.0) | 107.6 (0.0) | 109.6 (0.0) | 112.7 (0.0) | 108.7 (0.0) |
| trec132k-17000241.fix2 | 108.8 (5.0) | 107.6 (0.0) | 109.1 (0.0) | 112.7 (0.0) | 110.4 (5.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 333 | 10 / 10 | yes | 1537.9 | 1164.4 | 366.8 | 43.6 / 57.8 / 441 | 23.4 | 0.13 / 0.21 / 0.21 | 12771 (1) | 246 / 1069 / 8448 | 16.9 / 44 | 5 | 0.37 | 0 |
| scout_c8_r1 | 332 | 10 / 10 | yes | 1541.9 | 1171.4 | 363.1 | 44.1 / 57.6 / 443 | 23.5 | 0.14 / 0.22 / 0.23 | 12771 (1) | 243 / 1063 / 8689 | 16.9 / 48 | 6 | 0.38 | 0 |
| wide_c8_r1 | 234 | 10 / 10 | yes | 1344.8 | 1195.7 | 142.9 | 43.0 / 68.8 / 3462 | 52.0 | 0.14 / 0.22 / 0.22 | 12771 (1) | 488 / 1244 / 11037 | 26.6 / 128 | 40 | 0.40 | 0 |
| nospec_c8_r1 | 486 | 10 / 10 | yes | 1728.4 | 1149.7 | 572.3 | 43.2 / 56.6 / 443 | 16.7 | 0.13 / 0.22 / 0.23 | 12771 (1) | 262 / 1046 / 9240 | 11.2 / 45 | 4 | 0.34 | 0 |
| nospec-wide_c8_r1 | 398 | 10 / 10 | yes | 1592.8 | 1159.7 | 426.1 | 43.6 / 58.1 / 442 | 19.0 | 0.13 / 0.22 / 0.23 | 12771 (1) | 315 / 1070 / 8996 | 14.3 / 140 | 20 | 0.35 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 12772 (0 / 12772) | 0 | 0 | 12772 | 0 | 0 | 3x IndexError: list index out of range | - |
| scout_c8_r1 | 12772 (9607 / 3165) | 0 | 9607 | 12772 | 0 | 0 | 3x IndexError: list index out of range | 4x after an error; 3x IndexError; 2x needs a value |
| wide_c8_r1 | 12772 (9607 / 3165) | 12767 | 9607 | 12772 | 0 | 0 | 3x IndexError: list index out of range | 4x after an error; 3x IndexError; 2x needs a value |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| stream_c8_r1 | yes | 103 / 103 | 10 / 10 | 0 | 0 | 0 |
| scout_c8_r1 | yes | 103 / 103 | 10 / 10 | 0 | 0 | 0 |
| wide_c8_r1 | yes | 103 / 103 | 10 / 10 | 0 | 0 | 0 |
| nospec_c8_r1 | yes | 103 / 103 | 10 / 10 | 0 | 0 | 0 |
| nospec-wide_c8_r1 | yes | 103 / 103 | 10 / 10 | 0 | 0 | 0 |
