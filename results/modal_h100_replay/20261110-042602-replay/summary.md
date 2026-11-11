# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| nospec | 2 (2) | 1236.9 | 735.2 | 496.0 | 0.401 | - | 1.049 | - | 1.059 [1.040, 1.084] |
| stream | 2 (2) | 1179.5 | 708.6 | 465.8 | 0.395 | 0.954 | - | 0.944 [0.923, 0.962] | - |
| scout | 2 (2) | 850.9 | 699.0 | 147.0 | 0.173 | 0.688 | 0.721 | 0.819 [0.649, 0.933] | 0.867 [0.683, 0.987] |
| wide | 2 (2) | 760.8 | 698.5 | 56.9 | 0.075 | 0.615 | 0.645 | 0.742 [0.563, 0.899] | 0.786 [0.595, 0.953] |
| wide-threads | 1 (1) | 750.8 | 677.1 | 68.3 | 0.091 | 0.607 | 0.636 | 0.726 [0.557, 0.887] | 0.768 [0.588, 0.935] |
| nospec-wide | 1 (1) | 1137.9 | 690.7 | 441.0 | 0.388 | 0.920 | 0.965 | 0.866 [0.754, 0.957] | 0.917 [0.797, 1.009] |

## The predictions (cloud/PREREG_REPLAY.md, fixed before the run)

| | prediction | measured | |
|---|---|---|---|
| P1 | every unit exact; no unrecorded call, no repeat | 10 of 10 exact; 1042 stray calls | **did not hold** |
| P2 | nothing evicted | 1042 evicted | **did not hold** |
| P3 | the loop of 319 single calls: `stream` at least 0.90 of `nospec` | 1.019 | held |
| P4 | the same turn: `scout` at most 0.15 of `stream` | 0.070 | held |
| P5 | serial launches: `scout` recovers at least 75%, `wide` at least 85% | 87%, 96% | held |
| P6 | the cap: `scout` recovers between -15% and +15%, `wide` at least 50% | -1%, 63% | held |
| P7 | session time: `stream` 0.93–1.02 of `nospec`; `scout` at most 0.80 of `stream`; `wide` at most 0.75 | 0.954, 0.721, 0.645 | held |
| P8 | root stream seconds: `scout` within 5% of `stream`, `wide` within 10% | 0.987, 0.986 | held |
| P9 | an arm's two units differ by less than 5% in session time | largest difference 5.2% (4 arms with two units) | **did not hold** |
| P10 | controls: `wide-threads` within 25% of `wide`; `nospec-wide` recovers at most 10% of the serial-launch seconds and is at least 0.90 of `nospec` | 0.987, -8%, 0.920 | held |
| live run | worth it if the better fork arm is at most 0.85 of `stream` in session time and its root streams at most 10% longer | `wide`: 0.645, root streams 0.986 | held |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | nospec s | stream s | scout s | wide s | wide-threads s | nospec-wide s | nospec recovers | scout recovers | wide recovers | wide-threads recovers | nospec-wide recovers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| not speculated | 1 | 10.4 | 11.8 | 4.3 | 4.3 | 9.4 | 12.4 | 12% | 64% | 63% | 20% | -5% |
| serial launches | 2 | 372.2 | 357.1 | 45.4 | 15.9 | 26.4 | 387.4 | -4% | 87% | 96% | 93% | -8% |
| burst over the cap | 5 | 108.9 | 94.2 | 95.1 | 34.6 | 30.5 | 37.8 | -16% | -1% | 63% | 68% | 60% |
| still running at stream end | 1 | 1.1 | 1.1 | 1.0 | 1.0 | 0.9 | 1.1 | -5% | 11% | 9% | 14% | -5% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | nospec s | stream s | scout s | wide s | wide-threads s | nospec-wide s |
|---|---|---|---|---|---|---|---|---|---|
| trec132k-17000222 | 7 | 319 (0) | serial launches | 327.1 | 333.3 | 23.3 | 4.0 | 3.9 | 343.2 |
| trec132k-17000241 | 12 | 4224 (0) | burst over the cap | 58.0 | 55.8 | 55.9 | 21.0 | 15.6 | 14.6 |
| trec132k-17000222 | 4 | 1600 (1582) | serial launches | 45.2 | 23.8 | 22.1 | 11.9 | 22.5 | 44.2 |
| pairs32k-15 | 4 | 400 (387) | not speculated | 10.4 | 11.8 | 4.3 | 4.3 | 9.4 | 12.4 |
| trec132k-17000222.w8k-c8 | 4 | 1002 (0) | burst over the cap | 13.7 | 11.4 | 11.5 | 7.0 | 8.1 | 7.4 |
| trec132k-17000222.w8k-c8 | 6 | 1007 (1) | burst over the cap | 13.1 | 11.2 | 11.4 | 1.3 | 1.7 | 3.3 |
| trec132k-17000222.w8k-c8 | 8 | 1008 (1) | burst over the cap | 12.6 | 10.7 | 11.2 | 1.1 | 1.5 | 2.6 |
| pairs32k-1 | 4 | 400 (387) | burst over the cap | 11.5 | 5.1 | 5.2 | 4.1 | 3.5 | 9.8 |
| trec132k-17000222 | 9 | 2 (0) | still running at stream end | 1.1 | 1.1 | 1.0 | 1.0 | 0.9 | 1.1 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | nospec | stream | scout | wide | wide-threads | nospec-wide |
|---|---|---|---|---|---|---|
| pairs32k-1 | 79.8 (11.5) | 70.6 (5.1) | 69.3 (5.2) | 68.5 (4.1) | 67.0 (3.5) | 74.3 (9.8) |
| pairs32k-15 | 100.9 (10.4) | 97.8 (11.8) | 89.7 (4.3) | 89.3 (4.4) | 91.5 (9.4) | 95.6 (12.4) |
| pairs32k-20 | 80.7 (0.0) | 76.9 (0.0) | 75.4 (0.0) | 77.0 (0.0) | 74.7 (0.0) | 75.3 (0.0) |
| trec132k-17000222 | 520.3 (374.3) | 504.9 (359.1) | 192.0 (47.2) | 160.8 (17.8) | 165.8 (28.1) | 532.1 (389.8) |
| trec132k-17000222.w8k-c8 | 138.0 (41.4) | 126.3 (33.5) | 125.1 (34.3) | 101.6 (9.5) | 100.8 (11.4) | 105.3 (14.0) |
| trec132k-17000232 | 120.2 (0.0) | 115.5 (0.1) | 114.7 (0.1) | 111.0 (0.1) | 109.2 (0.1) | 111.4 (0.0) |
| trec132k-17000232.w8k-c1 | 87.1 (0.3) | 83.5 (0.4) | 81.8 (0.0) | 82.4 (0.0) | 79.9 (0.1) | 81.7 (0.3) |
| trec132k-17000241 | 110.0 (58.0) | 104.0 (55.8) | 103.0 (55.9) | 70.1 (21.0) | 61.9 (15.6) | 62.2 (14.6) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec_c8_r1 | 521 | 8 / 8 | yes | 1268.0 | 771.2 | 491.2 | 35.6 / 44.7 / 1321 | 25.5 | 0.11 / 8.40 / 8.44 | 9096 (2359) | 231 / 346 / 2855 | 4.5 / 48 | 0 | 0.19 | 0 |
| stream_c8_r1 | 502 | 8 / 8 | yes | 1173.8 | 704.3 | 464.6 | 36.7 / 47.2 / 207 | 0.8 | 0.11 / 0.25 / 0.33 | 9096 (2359) | 230 / 355 / 2381 | 4.7 / 49 | 0 | 0.23 | 0 |
| scout_c8_r1 | 192 | 8 / 8 | yes | 855.8 | 703.3 | 147.6 | 36.5 / 48.7 / 228 | 1.2 | 0.11 / 0.32 / 0.33 | 9096 (2359) | 222 / 347 / 2408 | 12.6 / 50 | 0 | 0.23 | 0 |
| wide_c8_r1 | 162 | 8 / 8 | yes | 767.9 | 702.9 | 59.6 | 35.0 / 54.8 / 2861 | 19.8 | 0.11 / 0.25 / 0.32 | 10138 (2359) | 359 / 1004 / 3193 | 16.7 / 131 | 0 | 0.24 | 0 |
| wide_c8_r2 | 160 | 8 / 8 | yes | 753.6 | 694.2 | 54.2 | 35.6 / 54.5 / 182 | 0.0 | 0.11 / 0.25 / 0.31 | 9096 (2359) | 344 / 1031 / 2645 | 15.2 / 130 | 0 | 0.24 | 0 |
| scout_c8_r2 | 192 | 8 / 8 | yes | 846.1 | 694.8 | 146.5 | 36.0 / 48.2 / 180 | 0.0 | 0.11 / 0.25 / 0.32 | 9096 (2359) | 222 / 346 / 2105 | 12.3 / 50 | 3 | 0.23 | 0 |
| stream_c8_r2 | 507 | 8 / 8 | yes | 1185.3 | 712.9 | 467.0 | 37.8 / 45.8 / 183 | 0.0 | 0.11 / 0.26 / 0.33 | 9096 (2359) | 224 / 345 / 2220 | 4.6 / 50 | 0 | 0.23 | 0 |
| nospec_c8_r2 | 519 | 8 / 8 | yes | 1205.7 | 699.2 | 500.8 | 35.4 / 57.5 / 177 | 0.0 | 0.11 / 0.26 / 0.35 | 9096 (2359) | 238 / 361 / 2831 | 4.4 / 48 | 1 | 0.19 | 0 |
| wide-threads_c8_r1 | 166 | 8 / 8 | yes | 750.8 | 677.1 | 68.3 | 34.6 / 49.3 / 186 | 0.0 | 0.11 / 0.25 / 0.32 | 9096 (2359) | 282 / 454 / 2380 | 14.6 / 128 | 0 | 0.23 | 0 |
| nospec-wide_c8_r1 | 532 | 8 / 8 | yes | 1137.9 | 690.7 | 441.0 | 35.9 / 50.8 / 182 | 0.0 | 0.11 / 0.24 / 0.29 | 9096 (2359) | 351 / 994 / 2601 | 4.5 / 131 | 0 | 0.19 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 10655 (0 / 10655) | 0 | 0 | 10655 | 787 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | - |
| scout_c8_r1 | 11454 (11454 / 0) | 0 | 10713 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow; 1x ShadowAborted:  | 5x needs a value; 3x RuntimeError; 3x TypeError |
| wide_c8_r1 | 12367 (11291 / 1076) | 12045 | 10249 | 11327 | 128 | 1042 | 3x RuntimeError: opaque value 're' touched in shadow; 1x AttributeError: 'NoneType' object has no attribute 'lower' | 5x needs a value; 3x RuntimeError; 3x TypeError |
| wide_c8_r2 | 11452 (11452 / 0) | 11130 | 11452 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |
| scout_c8_r2 | 11454 (11454 / 0) | 0 | 11153 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow; 1x ShadowAborted:  | 5x needs a value; 3x RuntimeError; 3x TypeError |
| stream_c8_r2 | 10233 (0 / 10233) | 0 | 0 | 10233 | 1209 | 0 | 3x RuntimeError: opaque value 're' touched in shadow; 1x ShadowAborted:  | - |
| wide-threads_c8_r1 | 11452 (11452 / 0) | 0 | 11451 | 11455 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 5x needs a value; 3x RuntimeError; 3x TypeError |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| nospec_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| stream_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| scout_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| wide_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 1042 | 24 |
| wide_c8_r2 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| scout_c8_r2 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| stream_c8_r2 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| nospec_c8_r2 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| wide-threads_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |
| nospec-wide_c8_r1 | yes | 78 / 78 | 8 / 8 | 0 | 0 | 0 |

## Noise: one arm's two units

| arm | session time, unit 1 / unit 2 | per-session spread (factor) | after-stream s, unit 1 / unit 2 | root streams s, unit 1 / unit 2 |
|---|---|---|---|---|
| nospec | 1.052 | x1.088 | 491.2 / 500.8 | 771.2 / 699.2 |
| stream | 0.990 | x1.012 | 464.6 / 467.0 | 704.3 / 712.9 |
| scout | 1.011 | x1.022 | 147.6 / 146.5 | 703.3 / 694.8 |
| wide | 1.019 | x1.029 | 59.6 / 54.2 | 702.9 / 694.2 |
