# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| stream | 1 (1) | 2590.1 | 2119.8 | 464.4 | 0.179 | - | - | - | - |
| wide | 1 (1) | 2540.5 | 2156.9 | 375.6 | 0.148 | - | 0.981 | - | 0.977 [0.942, 1.010] |
| auto | 1 (1) | 2580.1 | 2066.7 | 506.6 | 0.196 | - | 0.996 | - | 0.995 [0.969, 1.029] |

## The predictions (cloud/PREREG_GOVERN.md, fixed before the run)

| | prediction | measured | |
|---|---|---|---|
| S1 | every unit is exact (units that are not: 0) | 0 | held |
| S2 | no call is sent that the recorded run did not send, and none twice (dry run: 0) | 0 | held |
| S3 | no speculative call is evicted (dry run: 0) | 0 | held |
| S4 | a fixed 128 makes the root's turn wait: `wide`'s root TTFT, 90th percentile, is at least 2.5 times `stream`'s (dry run: 7.4) | 3.73 | held |
| S5 | the governed window does not: `auto`'s root TTFT, 90th percentile, is at most 1.25 times `stream`'s (dry run: 0.66) | 0.69 | held |
| S6 | the engine's largest queue: `wide`'s is at least 3 times `stream`'s (dry run: 9.2) | 9.39 | held |
| S7 | the engine's largest queue: `auto`'s is at most 1.5 times `stream`'s (dry run: 0.74) | 0.89 | held |
| S8 | width buys nothing on an engine with 16 places: `wide` at least 0.98 of `stream` in session time (dry run: 1.031) | 0.981 | held |
| S9 | session time: `auto` at most 1.04 of `stream` (dry run: 1.018) | 0.996 | held |
| S10 | session time: `auto` at most 1.01 of `wide` (dry run: 0.987) | 1.016 | **did not hold** |
| S11 | the governed windows close: at least 10 cuts in `auto` (dry run: 63) | 189 | held |
| S12 | and no window of `auto` gets to 128 (dry run: the widest is 42) | 38 | held |
| S13 | root stream seconds: `auto` at most 1.03 of `stream` (dry run: 0.992) | 0.975 | held |

## Limits that followed the load

A governed session's window starts at spec-ptc's 16 and moves with what the engine and the client report. Window at a call: the window of its session when the sub-call was sent. Cuts: moves down because the engine queued, preempted or was short of KV cache. KV pool: the tokens of KV cache the engine had free for speculative calls, as the client worked it out.

| unit | moves (by reason) | window at a call, median / 90th / mean | calls sent above 16 / above 128 / below 16 | widest / narrowest window | cuts | KV pool, smallest / largest (tokens) |
|---|---|---|---|---|---|---|
| auto_c8_r1 | 631 (433 grow, 189 queue, 9 idle) | 28 / 28 / 21 | 4055 / 0 / 2038 of 6405 | 38 / 1 | 189 | 53836 / 79664 |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | stream s | wide s | auto s | wide recovers | auto recovers |
|---|---|---|---|---|---|---|
| partly speculated | 1 | 143.0 | 131.6 | 137.7 | 8% | 4% |
| burst over the cap | 6 | 321.2 | 243.7 | 368.7 | 24% | -15% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | stream s | wide s | auto s |
|---|---|---|---|---|---|---|
| trec132k-17000237.fix2 | 9 | 3185 (0) | partly speculated | 143.0 | 131.6 | 137.7 |
| pairs32k-1.fix2 | 4 | 786 (0) | burst over the cap | 95.0 | 75.2 | 87.4 |
| pairs32k-16.fix2 | 5 | 787 (0) | burst over the cap | 80.9 | 59.4 | 95.6 |
| pairs32k-1.fix1 | 4 | 787 (0) | burst over the cap | 74.5 | 52.3 | 85.5 |
| pairs32k-16.fix2 | 6 | 787 (0) | burst over the cap | 41.1 | 32.7 | 59.0 |
| pairs32k-16.fix1 | 8 | 40 (0) | burst over the cap | 25.1 | 18.4 | 36.0 |
| trec132k-17000237.fix2 | 8 | 20 (0) | burst over the cap | 4.6 | 5.6 | 5.1 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | stream | wide | auto |
|---|---|---|---|
| pairs32k-1.fix1 | 237.0 (74.5) | 217.2 (52.3) | 244.6 (85.5) |
| pairs32k-1.fix2 | 251.0 (95.1) | 227.9 (75.2) | 240.9 (87.4) |
| pairs32k-15.fix1 | 475.6 (0.1) | 468.8 (0.1) | 467.1 (0.1) |
| pairs32k-16.fix1 | 346.9 (25.1) | 356.9 (18.4) | 349.5 (36.1) |
| pairs32k-16.fix2 | 310.3 (122.0) | 289.1 (92.2) | 340.0 (154.7) |
| trec132k-17000232.fix1 | 235.9 (0.0) | 242.2 (0.0) | 224.1 (0.0) |
| trec132k-17000237.fix2 | 480.0 (147.6) | 476.5 (137.3) | 468.6 (142.9) |
| trec132k-17000241.fix1 | 253.3 (0.0) | 261.9 (0.0) | 245.3 (0.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max (share of samples with a request waiting) | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 480 | 8 / 8 | yes | 2590.1 | 2119.8 | 464.4 | 83.6 / 429.3 / 6077 | 177.9 | 1.23 / 5.32 / 6.17 | 6405 (1) | 742 / 2263 / 15986 | 9.6 / 16 | 38 (0.48) | 0.35 | 0 |
| wide_c8_r1 | 476 | 8 / 8 | yes | 2540.5 | 2156.9 | 375.6 | 79.6 / 417.9 / 6069 | 172.7 | 1.25 / 12.95 / 13.06 | 6405 (1) | 1939 / 12047 / 21524 | 9.0 / 16 | 357 (0.41) | 0.32 | 0 |
| auto_c8_r1 | 469 | 8 / 8 | yes | 2580.1 | 2066.7 | 506.6 | 70.8 / 431.6 / 6063 | 175.5 | 1.04 / 5.32 / 6.17 | 6405 (1) | 630 / 1328 / 16795 | 9.6 / 16 | 34 (0.41) | 0.32 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 5041 (0 / 5041) | 0 | 0 | 5041 | 1365 | 0 | 2x IndexError: list index out of range; 1x ShadowAborted:  | - |
| wide_c8_r1 | 6406 (3241 / 3165) | 6405 | 3241 | 6406 | 0 | 0 | 2x IndexError: list index out of range | 4x after an error; 2x IndexError; 2x needs a value |
| auto_c8_r1 | 6406 (3241 / 3165) | 6405 | 3241 | 6406 | 0 | 0 | 2x IndexError: list index out of range | 4x after an error; 2x IndexError; 2x needs a value |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| stream_c8_r1 | yes | 82 / 82 | 8 / 8 | 0 | 0 | 0 |
| wide_c8_r1 | yes | 82 / 82 | 8 / 8 | 0 | 0 | 0 |
| auto_c8_r1 | yes | 82 / 82 | 8 / 8 | 0 | 0 | 0 |
