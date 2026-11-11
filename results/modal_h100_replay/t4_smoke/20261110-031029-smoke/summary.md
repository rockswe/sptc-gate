# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| nospec | 1 (1) | 482.3 | 390.6 | 89.3 | 0.185 | - | 1.126 | - | 1.127 [1.116, 1.136] |
| stream | 1 (1) | 428.4 | 352.3 | 74.2 | 0.173 | 0.888 | - | 0.888 [0.881, 0.896] | - |
| scout | 1 (1) | 436.6 | 370.1 | 64.5 | 0.148 | 0.905 | 1.019 | 0.906 [0.872, 0.935] | 1.021 [0.990, 1.055] |
| wide | 1 (1) | 438.7 | 376.5 | 60.2 | 0.137 | 0.910 | 1.024 | 0.911 [0.853, 0.960] | 1.026 [0.969, 1.083] |
| wide-threads | 1 (1) | 378.4 | 375.2 | 0.9 | 0.002 | 0.785 | 0.883 | 0.792 [0.703, 0.900] | 0.892 [0.785, 1.015] |
| nospec-wide | 1 (1) | 423.1 | 335.3 | 85.4 | 0.202 | 0.877 | 0.988 | 0.872 [0.846, 0.921] | 0.983 [0.954, 1.028] |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | nospec s | stream s | scout s | wide s | wide-threads s | nospec-wide s | nospec recovers | scout recovers | wide recovers | wide-threads recovers | nospec-wide recovers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| not speculated | 1 | 20.5 | 16.6 | 7.1 | 3.7 | 0.1 | 15.0 | -23% | 57% | 78% | 99% | 10% |
| burst over the cap | 3 | 66.8 | 57.0 | 57.2 | 56.4 | 0.5 | 68.2 | -17% | -0% | 1% | 99% | -20% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | nospec s | stream s | scout s | wide s | wide-threads s | nospec-wide s |
|---|---|---|---|---|---|---|---|---|---|
| trec132k-17000222.w8k-c8 | 6 | 1007 (1) | burst over the cap | 28.4 | 25.6 | 25.6 | 20.0 | 0.2 | 23.4 |
| trec132k-17000222.w8k-c8 | 4 | 1002 (0) | burst over the cap | 29.6 | 23.7 | 23.9 | 19.4 | 0.1 | 26.1 |
| pairs32k-15 | 4 | 400 (387) | not speculated | 20.5 | 16.6 | 7.1 | 3.7 | 0.1 | 15.0 |
| trec132k-17000222.w8k-c8 | 8 | 1008 (1) | burst over the cap | 8.8 | 7.7 | 7.6 | 17.0 | 0.1 | 18.7 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | nospec | stream | scout | wide | wide-threads | nospec-wide |
|---|---|---|---|---|---|---|
| pairs32k-15 | 159.4 (20.5) | 140.3 (16.6) | 138.9 (7.1) | 136.0 (3.7) | 125.1 (0.1) | 135.7 (15.0) |
| trec132k-17000222.w8k-c8 | 189.5 (68.4) | 169.8 (57.2) | 173.0 (57.3) | 174.6 (56.4) | 133.3 (0.5) | 174.6 (70.0) |
| trec132k-17000232.w8k-c1 | 133.4 (0.5) | 118.2 (0.4) | 124.7 (0.0) | 128.1 (0.0) | 120.0 (0.2) | 112.8 (0.4) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec_c3_r1 | 190 | 3 / 3 | yes | 482.3 | 390.6 | 89.3 | 38.8 / 112.7 / 2055 | 28.9 | 0.60 / 13.71 / 13.71 | 3592 (390) | 340 / 559 / 4433 | 5.8 / 27 | 0 | 0.13 | 0 |
| stream_c3_r1 | 170 | 3 / 3 | yes | 428.4 | 352.3 | 74.2 | 39.7 / 120.0 / 1092 | 16.9 | 0.59 / 1.22 / 1.23 | 3592 (390) | 354 / 559 / 1694 | 6.8 / 27 | 0 | 0.13 | 0 |
| scout_c3_r1 | 173 | 3 / 3 | yes | 436.6 | 370.1 | 64.5 | 40.0 / 118.6 / 1133 | 18.6 | 0.60 / 1.24 / 1.26 | 3592 (390) | 369 / 578 / 1755 | 7.0 / 19 | 0 | 0.14 | 0 |
| wide_c3_r1 | 175 | 3 / 3 | yes | 438.7 | 376.5 | 60.2 | 39.8 / 180.5 / 4392 | 36.7 | 0.60 / 1.99 / 2.24 | 3591 (390) | 1841 / 5624 / 7186 | 9.7 / 126 | 35 | 0.16 | 0 |
| wide-threads_c3_r1 | 133 | 3 / 3 | yes | 378.4 | 375.2 | 0.9 | 41.0 / 239.5 / 1156 | 35.5 | 0.60 / 1.48 / 1.58 | 3592 (390) | 839 / 1226 / 2316 | 18.0 / 111 | 0 | 0.17 | 0 |
| nospec-wide_c3_r1 | 175 | 3 / 3 | yes | 423.1 | 335.3 | 85.4 | 38.9 / 142.5 / 1081 | 22.0 | 0.59 / 1.23 / 1.25 | 3591 (390) | 1690 / 5530 / 7303 | 9.2 / 125 | 43 | 0.14 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c3_r1 | 3182 (0 / 3182) | 0 | 0 | 3182 | 787 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | - |
| scout_c3_r1 | 3982 (3982 / 0) | 0 | 3982 | 3982 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 4x needs a value; 3x RuntimeError; 3x TypeError |
| wide_c3_r1 | 3982 (3982 / 0) | 3982 | 3982 | 3982 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 4x needs a value; 3x RuntimeError; 3x TypeError |
| wide-threads_c3_r1 | 3982 (3982 / 0) | 0 | 3982 | 3982 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 4x needs a value; 3x RuntimeError; 3x TypeError |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| nospec_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| stream_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| scout_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| wide_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| wide-threads_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| nospec-wide_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
