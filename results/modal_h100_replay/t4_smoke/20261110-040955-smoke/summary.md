# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| nospec | 1 (1) | 477.9 | 387.2 | 89.2 | 0.187 | - | - | - | - |
| wide | 1 (1) | 378.4 | 372.3 | 4.4 | 0.012 | 0.792 | - | 0.799 [0.714, 0.907] | - |
| wide-threads | 1 (1) | 368.0 | 365.1 | 0.8 | 0.002 | 0.770 | - | 0.777 [0.690, 0.884] | - |
| nospec-wide | 1 (1) | 373.2 | 330.3 | 40.8 | 0.109 | 0.781 | - | 0.786 [0.713, 0.832] | - |

## The predictions (cloud/PREREG_REPLAY.md, fixed before the run)

| | prediction | measured | |
|---|---|---|---|
| P1 | every unit exact; no unrecorded call, no repeat | 4 of 4 exact; 0 stray calls | held |
| P2 | nothing evicted | 0 evicted | held |
| P3 | the loop of 319 single calls: `stream` at least 0.90 of `nospec` | - | not testable |
| P4 | the same turn: `scout` at most 0.15 of `stream` | - | not testable |
| P5 | serial launches: `scout` recovers at least 75%, `wide` at least 85% | -, - | not testable |
| P6 | the cap: `scout` recovers between -15% and +15%, `wide` at least 50% | -, - | not testable |
| P7 | session time: `stream` 0.93–1.02 of `nospec`; `scout` at most 0.80 of `stream`; `wide` at most 0.75 | -, -, - | not testable |
| P8 | root stream seconds: `scout` within 5% of `stream`, `wide` within 10% | -, - | not testable |
| P9 | an arm's two units differ by less than 5% in session time | - | not testable |
| P10 | controls: `wide-threads` within 25% of `wide`; `nospec-wide` recovers at most 10% of the serial-launch seconds and is at least 0.90 of `nospec` | 0.972, -, 0.781 | not testable |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | nospec | wide | wide-threads | nospec-wide |
|---|---|---|---|---|
| pairs32k-15 | 158.0 (20.2) | 124.7 (1.2) | 121.7 (0.1) | 129.3 (17.7) |
| trec132k-17000222.w8k-c8 | 187.8 (68.6) | 134.0 (3.1) | 129.6 (0.5) | 134.0 (22.7) |
| trec132k-17000232.w8k-c1 | 132.1 (0.4) | 119.8 (0.0) | 116.7 (0.1) | 109.9 (0.4) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec_c3_r1 | 188 | 3 / 3 | yes | 477.9 | 387.2 | 89.2 | 37.9 / 112.8 / 2104 | 29.8 | 0.59 / 14.11 / 14.11 | 3592 (390) | 334 / 557 / 4511 | 6.0 / 32 | 0 | 0.13 | 0 |
| wide_c3_r1 | 134 | 3 / 3 | yes | 378.4 | 372.3 | 4.4 | 39.7 / 218.7 / 4391 | 42.4 | 0.59 / 1.16 / 1.17 | 3592 (390) | 814 / 1208 / 5664 | 16.9 / 131 | 0 | 0.18 | 0 |
| wide-threads_c3_r1 | 130 | 3 / 3 | yes | 368.0 | 365.1 | 0.8 | 40.0 / 215.6 / 1151 | 29.1 | 0.59 / 1.49 / 1.52 | 3592 (390) | 799 / 1161 / 2282 | 17.5 / 105 | 0 | 0.18 | 0 |
| nospec-wide_c3_r1 | 134 | 3 / 3 | yes | 373.2 | 330.3 | 40.8 | 39.2 / 192.8 / 1104 | 23.4 | 0.60 / 1.40 / 1.48 | 3592 (390) | 776 / 1151 / 1767 | 14.9 / 126 | 41 | 0.15 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| wide_c3_r1 | 3982 (3982 / 0) | 3982 | 3982 | 3982 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 4x needs a value; 3x RuntimeError; 3x TypeError |
| wide-threads_c3_r1 | 3982 (3982 / 0) | 0 | 3982 | 3982 | 0 | 0 | 3x RuntimeError: opaque value 're' touched in shadow | 4x needs a value; 3x RuntimeError; 3x TypeError |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| nospec_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| wide_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| wide-threads_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
| nospec-wide_c3_r1 | yes | 26 / 26 | 3 / 3 | 0 | 0 | 0 |
