# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| stream | 1 (1) | 1476.1 | 873.2 | 596.7 | 0.404 | - | - | - | - |
| scout | 1 (1) | 1042.7 | 857.0 | 179.1 | 0.172 | - | 0.706 | - | 0.858 [0.670, 0.981] |
| wide | 2 (2) | 1047.0 | 969.3 | 70.7 | 0.068 | - | 0.709 | - | 0.874 [0.651, 1.075] |
| wide-threads | 1 (1) | 961.0 | 863.4 | 90.8 | 0.095 | - | 0.651 | - | 0.793 [0.604, 0.966] |

## The predictions (cloud/PREREG_REPLAY_ADDENDUM.md, fixed before the follow-up run)

| | prediction | measured | |
|---|---|---|---|
| A1 | every unit exact; no call launched twice, none evicted, none left to the real run in the fork's arms | 5 of 5 exact; 0 stray, 0 evicted, 0 not speculated | held |
| A2 | the batch of 3,182: `wide` at most 0.45 of `stream` | 0.318 | held |
| A3 | the cap: `wide` recovers at least 50% | 64% | held |
| A4 | serial launches: `wide` recovers at least 85% | 95% | held |
| A5 | session time: `wide` at most 0.75 of `stream`; root stream seconds within 10% | 0.709, 1.110 | **did not hold** |
| A6 | `wide-threads` within 25% of `wide` in session time | 0.918 | held |
| A7 | `wide`'s two units differ by less than 5% in session time | 15.5% | **did not hold** |
| A8 | the runaway guard cuts no shadow statement in the fork's arms | 0 cut | held |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | stream s | scout s | wide s | wide-threads s | scout recovers | wide recovers | wide-threads recovers |
|---|---|---|---|---|---|---|---|---|
| not speculated | 1 | 15.1 | 5.4 | 4.5 | 14.4 | 64% | 70% | 5% |
| serial launches | 2 | 460.5 | 57.4 | 20.9 | 35.5 | 88% | 95% | 92% |
| burst over the cap | 5 | 117.6 | 113.6 | 42.8 | 38.2 | 3% | 64% | 67% |
| still running at stream end | 2 | 2.5 | 2.3 | 2.4 | 2.4 | 7% | 3% | 2% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | stream s | scout s | wide s | wide-threads s |
|---|---|---|---|---|---|---|---|
| trec132k-17000222 | 7 | 319 (0) | serial launches | 431.7 | 29.2 | 5.7 | 4.9 |
| trec132k-17000241 | 12 | 3182 (0) | burst over the cap | 69.3 | 66.8 | 22.0 | 21.0 |
| trec132k-17000222 | 4 | 1600 (1582) | serial launches | 28.8 | 28.2 | 15.2 | 30.6 |
| pairs32k-15 | 4 | 400 (387) | not speculated | 15.1 | 5.4 | 4.5 | 14.4 |
| trec132k-17000222.w8k-c8 | 4 | 1002 (0) | burst over the cap | 15.0 | 13.9 | 9.1 | 9.8 |
| trec132k-17000222.w8k-c8 | 6 | 1007 (1) | burst over the cap | 13.6 | 13.2 | 1.5 | 1.9 |
| trec132k-17000222.w8k-c8 | 8 | 1008 (1) | burst over the cap | 13.1 | 12.9 | 1.6 | 1.4 |
| pairs32k-1 | 4 | 400 (387) | burst over the cap | 6.5 | 6.6 | 8.5 | 4.2 |
| trec132k-17000222 | 9 | 2 (0) | still running at stream end | 1.4 | 1.2 | 1.2 | 1.3 |
| trec132k-17000222 | 6 | 1 (0) | still running at stream end | 1.1 | 1.1 | 1.2 | 1.2 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | stream | scout | wide | wide-threads |
|---|---|---|---|---|
| pairs32k-1 | 87.5 (6.5) | 86.2 (6.7) | 97.1 (8.5) | 85.3 (4.2) |
| pairs32k-15 | 120.8 (15.1) | 109.5 (5.4) | 123.1 (4.5) | 117.6 (14.4) |
| pairs32k-20 | 95.2 (0.0) | 93.6 (0.0) | 107.5 (0.0) | 95.6 (0.0) |
| trec132k-17000222 | 643.0 (463.0) | 235.6 (59.7) | 217.1 (23.3) | 213.3 (37.9) |
| trec132k-17000222.w8k-c8 | 155.5 (42.1) | 152.2 (40.3) | 139.9 (12.3) | 127.0 (13.1) |
| trec132k-17000232 | 142.2 (0.1) | 139.2 (0.1) | 153.3 (0.1) | 139.2 (0.1) |
| trec132k-17000232.w8k-c1 | 103.3 (0.5) | 100.6 (0.0) | 114.6 (0.1) | 102.2 (0.1) |
| trec132k-17000241 | 128.7 (69.4) | 125.7 (66.9) | 94.3 (22.0) | 80.6 (21.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wide_c8_r1 | 231 | 8 / 8 | yes | 1122.4 | 1038.3 | 77.1 | 45.8 / 73.0 / 3400 | 71.5 | 0.14 / 10.21 / 10.25 | 9096 (2359) | 460 / 1178 / 7469 | 15.1 / 134 | 0 | 0.05 | 0 |
| wide_c8_r2 | 204 | 8 / 8 | yes | 971.6 | 900.4 | 64.4 | 48.2 / 66.2 / 173 | 0.0 | 0.15 / 0.28 / 0.33 | 9096 (2359) | 444 / 1106 / 3475 | 15.1 / 134 | 0 | 0.05 | 0 |
| stream_c8_r1 | 643 | 8 / 8 | yes | 1476.1 | 873.2 | 596.7 | 45.6 / 60.2 / 170 | 0.0 | 0.14 / 0.25 / 0.33 | 9096 (2359) | 281 / 430 / 2885 | 4.6 / 51 | 0 | 0.05 | 0 |
| scout_c8_r1 | 236 | 8 / 8 | yes | 1042.7 | 857.0 | 179.1 | 44.8 / 58.1 / 163 | 0.0 | 0.13 / 0.25 / 0.34 | 9096 (2359) | 269 / 417 / 2764 | 12.5 / 43 | 0 | 0.05 | 0 |
| wide-threads_c8_r1 | 213 | 8 / 8 | yes | 961.0 | 863.4 | 90.8 | 43.9 / 64.3 / 176 | 0.0 | 0.14 / 0.25 / 0.33 | 9096 (2359) | 371 / 561 / 3243 | 15.2 / 128 | 0 | 0.05 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| wide_c8_r1 | 11455 (11455 / 0) | 11133 | 11455 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |
| wide_c8_r2 | 11455 (11455 / 0) | 11133 | 11455 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |
| stream_c8_r1 | 10654 (0 / 10654) | 0 | 0 | 10655 | 787 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | - |
| scout_c8_r1 | 11455 (11455 / 0) | 0 | 11455 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |
| wide-threads_c8_r1 | 11455 (11455 / 0) | 0 | 11455 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| wide_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| wide_c8_r2 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| stream_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| scout_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| wide-threads_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |

## Noise: one arm's two units

| arm | session time, unit 1 / unit 2 | per-session spread (factor) | after-stream s, unit 1 / unit 2 | root streams s, unit 1 / unit 2 |
|---|---|---|---|---|
| wide | 1.155 | x1.163 | 77.1 / 64.4 | 1038.3 / 900.4 |
