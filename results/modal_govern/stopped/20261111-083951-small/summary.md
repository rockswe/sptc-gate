# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| stream | 1 (1) | 2625.1 | 2148.6 | 471.1 | 0.179 | - | - | - | - |

## The predictions (cloud/PREREG_GOVERN.md, fixed before the run)

| | prediction | measured | |
|---|---|---|---|
| S1 | every unit is exact (units that are not: 0) | 0 | held |
| S2 | no call is sent that the recorded run did not send, and none twice (dry run: 0) | 0 | held |
| S3 | no speculative call is evicted (dry run: 0) | 0 | held |
| S4 | a fixed 128 makes the root's turn wait: `wide`'s root TTFT, 90th percentile, is at least 2.5 times `stream`'s (dry run: 7.4) | - | not testable |
| S5 | the governed window does not: `auto`'s root TTFT, 90th percentile, is at most 1.25 times `stream`'s (dry run: 0.66) | - | not testable |
| S6 | the engine's largest queue: `wide`'s is at least 3 times `stream`'s (dry run: 9.2) | - | not testable |
| S7 | the engine's largest queue: `auto`'s is at most 1.5 times `stream`'s (dry run: 0.74) | - | not testable |
| S8 | width buys nothing on an engine with 16 places: `wide` at least 0.98 of `stream` in session time (dry run: 1.031) | - | not testable |
| S9 | session time: `auto` at most 1.04 of `stream` (dry run: 1.018) | - | not testable |
| S10 | session time: `auto` at most 1.01 of `wide` (dry run: 0.987) | - | not testable |
| S11 | the governed windows close: at least 10 cuts in `auto` (dry run: 63) | - | not testable |
| S12 | and no window of `auto` gets to 128 (dry run: the widest is 42) | - | not testable |
| S13 | root stream seconds: `auto` at most 1.03 of `stream` (dry run: 0.992) | - | not testable |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | stream s |  |
|---|---|---|
| partly speculated | 1 | 145.8 |  |
| burst over the cap | 6 | 325.1 |  |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | stream s |
|---|---|---|---|---|
| trec132k-17000237.fix2 | 9 | 3185 (0) | partly speculated | 145.8 |
| pairs32k-1.fix2 | 4 | 786 (0) | burst over the cap | 96.2 |
| pairs32k-16.fix2 | 5 | 787 (0) | burst over the cap | 82.0 |
| pairs32k-1.fix1 | 4 | 787 (0) | burst over the cap | 75.3 |
| pairs32k-16.fix2 | 6 | 787 (0) | burst over the cap | 41.3 |
| pairs32k-16.fix1 | 8 | 40 (0) | burst over the cap | 25.5 |
| trec132k-17000237.fix2 | 8 | 20 (0) | burst over the cap | 4.7 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | stream |
|---|---|
| pairs32k-1.fix1 | 239.4 (75.3) |
| pairs32k-1.fix2 | 254.3 (96.3) |
| pairs32k-15.fix1 | 482.6 (0.0) |
| pairs32k-16.fix1 | 351.7 (25.5) |
| pairs32k-16.fix2 | 314.6 (123.3) |
| trec132k-17000232.fix1 | 238.4 (0.0) |
| trec132k-17000237.fix2 | 487.2 (150.6) |
| trec132k-17000241.fix1 | 256.8 (0.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max (share of samples with a request waiting) | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 487 | 8 / 8 | yes | 2625.1 | 2148.6 | 471.1 | 86.0 / 452.3 / 6103 | 182.5 | 1.27 / 5.36 / 6.20 | 6405 (1) | 758 / 2290 / 16178 | 9.7 / 16 | 38 (0.48) | 0.35 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 4981 (0 / 4981) | 0 | 0 | 4981 | 1425 | 0 | 2x IndexError: list index out of range; 1x ShadowAborted:  | - |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| stream_c8_r1 | yes | 82 / 82 | 8 / 8 | 0 | 0 | 0 |
