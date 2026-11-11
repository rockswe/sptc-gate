# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| stream-open | 1 (1) | 1836.8 | 1277.1 | 552.2 | 0.301 | - | - | - | - |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | stream-open |
|---|---|
| pairs32k-1.fix1 | 75.2 (1.3) |
| pairs32k-1.fix2 | 81.7 (10.9) |
| pairs32k-15.fix1 | 237.8 (0.0) |
| pairs32k-16.fix1 | 155.9 (7.0) |
| pairs32k-16.fix2 | 106.6 (14.4) |
| trec132k-17000222.fix2 | 285.5 (178.5) |
| trec132k-17000232.fix1 | 101.5 (0.0) |
| trec132k-17000237.fix1 | 337.4 (256.5) |
| trec132k-17000237.fix2 | 238.8 (83.6) |
| trec132k-17000241.fix1 | 108.1 (0.0) |
| trec132k-17000241.fix2 | 108.1 (0.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream-open_c8_r1 | 394 | 11 / 11 | yes | 1836.8 | 1277.1 | 552.2 | 43.5 / 62.3 / 444 | 30.3 | 0.13 / 0.24 / 0.24 | 12775 (2) | 258 / 1071 / 183414 | 16.4 / 46 | 17 | 0.88 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream-open_c8_r1 | 10852 (0 / 10852) | 0 | 0 | 10852 | 1925 | 0 | 3x IndexError: list index out of range; 1x ShadowAborted: ; 1x NameError: name 're' is not defined | - |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| stream-open_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
