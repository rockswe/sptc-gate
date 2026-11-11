# Replay campaign summary (measured)

Every arm replays the same recorded sessions: same code, same sub-calls, same answers. Times are seconds on this run's engine. An arm's numbers are the mean of its units.

## Arms

Session time: the sum of the sessions' wall times. After-stream: from the end of each root stream until that turn's code has run. Ratios below 1 are faster. The per-session ratio is a geometric mean over sessions with a bootstrap 95% CI.

| arm | units (exact) | session time s | root streams s | after-stream s | after-stream share | session time vs nospec | vs stream | per session vs nospec [CI] | per session vs stream [CI] |
|---|---|---|---|---|---|---|---|---|---|
| stream | 1 (1) | 2185.5 | 1272.0 | 906.5 | 0.415 | - | - | - | - |
| wide | 1 (1) | 1967.7 | 1290.7 | 669.1 | 0.340 | - | 0.900 | - | 0.914 [0.788, 1.004] |
| auto | 1 (1) | 1775.2 | 1294.6 | 472.9 | 0.266 | - | 0.812 | - | 0.879 [0.727, 1.000] |
| auto-past | 1 (1) | 1727.9 | 1290.9 | 428.5 | 0.248 | - | 0.791 | - | 0.859 [0.710, 0.985] |
| wide-open | 1 (1) | 1643.2 | 1309.2 | 326.7 | 0.199 | - | 0.752 | - | 0.861 [0.705, 1.005] |

## The predictions (cloud/PREREG_GOVERN.md, fixed before the run)

| | prediction | measured | |
|---|---|---|---|
| H1 | every unit is exact (units that are not: 0) | 0 | held |
| H2 | no call is sent that the recorded run did not send, and none twice | 0 | held |
| H3 | no speculative call is evicted: past a test too, the scout places no bet | 0 | held |
| F1 | **the finish rule, 1:** over the 10, `auto`'s session time is at most 1.02 of `wide`'s | 0.985 | held |
| F2 | **the finish rule, 2:** over the 10, `auto`'s root stream seconds are at most 1.05 of `stream`'s | 1.014 | held |
| H4 | over the 10, `wide` is at 0.84 to 0.93 of `stream` in session time (measured on November 10: 0.874) | 0.862 | held |
| H5 | over the 10, `auto` is at 0.78 to 0.93 of `stream` in session time | 0.849 | held |
| H6 | the largest loop (`trec132k-17000237.fix1` turn 4, 3,181 calls): `auto` spends at most 1.10 of `wide`'s seconds after the stream | 0.600 | held |
| H7 | a window of `auto` gets wider than 128 | 256 | held |
| H8 | at least half of `auto`'s sub-calls are sent at a window above 16 | 0.99 | held |
| H9 | the long turn (`trec132k-17000222.fix2` turn 7) as shipped: `stream` spends at least 450 s after its stream (November: about 530 s, worked out from recorded call times) | 536.7 | held |
| H10 | the long turn: a wider window does nothing for it, `wide` at 0.90 to 1.10 of `stream` | 0.983 | held |
| H11 | the long turn: `auto` spends at most 0.80 of `stream`'s seconds | 0.659 | held |
| H12 | in `auto` the engine's KV cache stays at or under 97% | 0.74 | held |
| H13 | in `auto` the engine preempts nothing | 0 | held |
| H14 | control: with the character budget lifted and nothing following the load, the four long calls take the KV cache to at least 95% (`wide-open`) | 0.96 | held |
| H15 | control: and the 10 pay for it, their session time in `wide-open` at least 1.01 of `wide`'s | 1.013 | held |
| H16 | the loop that tests each result (`trec132k-17000237.fix2` turn 9): `auto-past` spends at most 0.60 of `auto`'s seconds after the stream | 0.237 | held |
| H17 | over the 10, `auto-past` is at most 1.00 of `auto` in session time | 0.966 | held |
| H18 | all 11 sessions: `auto` at most 0.90 of `stream` in session time | 0.812 | held |
| H19 | all 11 sessions: `auto-past` at most 0.88 of `stream` in session time | 0.791 | held |

## Limits that followed the load

A governed session's window starts at spec-ptc's 16 and moves with what the engine and the client report. Window at a call: the window of its session when the sub-call was sent. Cuts: moves down because the engine queued, preempted or was short of KV cache. KV pool: the tokens of KV cache the engine had free for speculative calls, as the client worked it out.

| unit | moves (by reason) | window at a call, median / 90th / mean | calls sent above 16 / above 128 / below 16 | widest / narrowest window | cuts | KV pool, smallest / largest (tokens) |
|---|---|---|---|---|---|---|
| auto_c8_r1 | 134 (80 idle, 50 grow, 4 queue) | 256 / 256 / 177 | 12610 / 8357 / 4 of 12775 | 256 / 11 | 4 | 99802 / 136238 |
| auto-past_c8_r1 | 149 (91 idle, 56 grow, 2 queue) | 256 / 256 / 231 | 12610 / 11330 / 3 of 12775 | 256 / 11 | 2 | 111089 / 135059 |

## What each arm leaves of the time spec-ptc as shipped still waited

Turns in which the `stream` arm spent at least 1 s after the stream, grouped by why (its own events). Seconds after the stream in the same turns, per arm, and the share of the `stream` arm's seconds that is gone.

| cause in `stream` | turns | stream s | wide s | auto s | auto-past s | wide-open s | wide recovers | auto recovers | auto-past recovers | wide-open recovers |
|---|---|---|---|---|---|---|---|---|---|---|
| partly speculated | 1 | 78.6 | 57.9 | 58.2 | 13.8 | 56.5 | 26% | 26% | 82% | 28% |
| burst over the cap | 7 | 290.8 | 83.0 | 60.5 | 61.6 | 85.5 | 71% | 79% | 79% | 71% |
| still running at stream end | 1 | 536.7 | 527.8 | 353.9 | 352.7 | 184.1 | 2% | 34% | 34% | 66% |

The turns:

| session | turn | sub-calls sent (errors returned) | cause in `stream` | stream s | wide s | auto s | auto-past s | wide-open s |
|---|---|---|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 7 | 4 (0) | still running at stream end | 536.7 | 527.8 | 353.9 | 352.7 | 184.1 |
| trec132k-17000237.fix1 | 4 | 3181 (0) | burst over the cap | 211.1 | 54.4 | 32.7 | 33.8 | 56.9 |
| trec132k-17000237.fix2 | 9 | 3185 (0) | partly speculated | 78.6 | 57.9 | 58.2 | 13.8 | 56.5 |
| trec132k-17000237.fix1 | 6 | 3181 (0) | burst over the cap | 46.3 | 18.3 | 13.7 | 14.1 | 20.1 |
| pairs32k-1.fix2 | 4 | 786 (0) | burst over the cap | 10.5 | 5.1 | 7.3 | 7.1 | 2.5 |
| pairs32k-16.fix1 | 8 | 40 (0) | burst over the cap | 7.3 | 2.1 | 2.7 | 2.5 | 2.1 |
| pairs32k-16.fix2 | 6 | 787 (0) | burst over the cap | 7.1 | 0.7 | 4.0 | 3.9 | 0.1 |
| pairs32k-16.fix2 | 5 | 787 (0) | burst over the cap | 7.1 | 2.4 | 0.1 | 0.1 | 3.7 |
| pairs32k-1.fix1 | 4 | 787 (0) | burst over the cap | 1.3 | 0.1 | 0.1 | 0.1 | 0.1 |

## Sessions

Wall time of each session, seconds (after-stream seconds).

| session | stream | wide | auto | auto-past | wide-open |
|---|---|---|---|---|---|
| pairs32k-1.fix1 | 75.2 (1.4) | 76.4 (0.1) | 76.2 (0.1) | 75.9 (0.1) | 76.0 (0.1) |
| pairs32k-1.fix2 | 80.7 (10.6) | 74.7 (5.1) | 76.3 (7.4) | 75.8 (7.2) | 72.5 (2.5) |
| pairs32k-15.fix1 | 236.3 (0.0) | 237.0 (0.1) | 237.7 (0.1) | 236.9 (0.0) | 239.0 (0.1) |
| pairs32k-16.fix1 | 154.5 (7.4) | 153.3 (2.1) | 154.4 (2.7) | 153.7 (2.5) | 156.4 (2.2) |
| pairs32k-16.fix2 | 107.6 (14.2) | 93.8 (3.1) | 96.1 (4.1) | 95.5 (4.0) | 94.4 (3.8) |
| trec132k-17000222.fix2 | 638.5 (536.7) | 634.2 (527.8) | 461.5 (353.9) | 459.3 (352.7) | 292.8 (184.1) |
| trec132k-17000232.fix1 | 101.2 (0.0) | 105.4 (0.0) | 105.2 (0.0) | 105.6 (0.0) | 108.0 (0.2) |
| trec132k-17000237.fix1 | 338.7 (257.4) | 155.8 (72.7) | 128.8 (46.3) | 130.5 (47.9) | 160.9 (77.1) |
| trec132k-17000237.fix2 | 236.2 (78.7) | 213.4 (58.0) | 213.4 (58.3) | 168.5 (13.9) | 214.0 (56.6) |
| trec132k-17000241.fix1 | 108.6 (0.0) | 111.9 (0.0) | 112.8 (0.0) | 113.5 (0.0) | 114.8 (0.0) |
| trec132k-17000241.fix2 | 108.1 (0.0) | 111.7 (0.0) | 112.8 (0.0) | 112.9 (0.0) | 114.3 (0.0) |

## Units, in the order they ran

| unit | wall s | sessions ok | exact | session time s | root streams s | after-stream s | root gap p50 / p99 / max ms | stall s | TTFT p50 / p99 / max s | sub-calls sent (errors returned) | call p50 / p90 / max ms | running mean / max | waiting max (share of samples with a request waiting) | KV peak | preempt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 638 | 11 / 11 | yes | 2185.5 | 1272.0 | 906.5 | 44.0 / 55.8 / 445 | 33.2 | 0.14 / 0.21 / 0.23 | 12775 (2) | 248 / 1082 / 190302 | 10.4 / 43 | 16 (0.01) | 0.45 | 0 |
| wide_c8_r1 | 634 | 11 / 11 | yes | 1967.7 | 1290.7 | 669.1 | 44.3 / 79.8 / 489 | 32.2 | 0.14 / 0.24 / 1.28 | 12775 (2) | 488 / 1305 / 186707 | 10.8 / 141 | 40 (0.01) | 0.48 | 0 |
| auto_c8_r1 | 461 | 11 / 11 | yes | 1775.2 | 1294.6 | 472.9 | 44.2 / 116.0 / 445 | 46.2 | 0.14 / 0.31 / 2.73 | 12775 (2) | 805 / 1716 / 187425 | 15.5 / 236 | 40 (0.01) | 0.74 | 0 |
| auto-past_c8_r1 | 459 | 11 / 11 | yes | 1727.9 | 1290.9 | 428.5 | 44.0 / 109.3 / 447 | 44.9 | 0.14 / 0.23 / 2.80 | 12775 (2) | 874 / 1947 / 184495 | 15.6 / 220 | 40 (0.01) | 0.73 | 0 |
| wide-open_c8_r1 | 293 | 11 / 11 | yes | 1643.2 | 1309.2 | 326.7 | 44.3 / 120.8 / 456 | 47.3 | 0.14 / 0.28 / 4.39 | 12775 (2) | 511 / 1346 / 189058 | 23.7 / 128 | 83 (0.02) | 0.96 | 0 |

## What speculation did

| unit | launched (by the scout or a peek / by the shadow) | of them in a batch launch | adopted | claimed | not speculated | evicted | shadow stops | scout statements cut short |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 11752 (0 / 11752) | 0 | 0 | 11752 | 1025 | 0 | 3x IndexError: list index out of range; 1x NameError: name 're' is not defined; 1x ShadowAborted:  | - |
| wide_c8_r1 | 12777 (9612 / 3165) | 12767 | 9612 | 12777 | 0 | 0 | 3x IndexError: list index out of range; 1x NameError: name 're' is not defined | 7x after an error; 4x TypeError; 3x IndexError; 2x needs a value; 1x NameError |
| auto_c8_r1 | 12777 (9612 / 3165) | 12767 | 9612 | 12777 | 0 | 0 | 3x IndexError: list index out of range; 1x NameError: name 're' is not defined | 7x after an error; 4x TypeError; 3x IndexError; 2x needs a value; 1x NameError |
| auto-past_c8_r1 | 12777 (12777 / 0) | 12767 | 12777 | 12777 | 0 | 0 | 3x IndexError: list index out of range; 1x NameError: name 're' is not defined | 7x after an error; 4x TypeError; 3x IndexError; 1x NameError |
| wide-open_c8_r1 | 12777 (9612 / 3165) | 12767 | 9612 | 12777 | 0 | 0 | 3x IndexError: list index out of range; 1x NameError: name 're' is not defined | 7x after an error; 4x TypeError; 3x IndexError; 2x needs a value; 1x NameError |

## Fidelity

A unit is exact if every session finished, ran the recorded number of turns, sent the root the recorded message history in every turn (sha256), and ended with the recorded answer. Unrecorded: sub-calls for a prompt the recorded run never sent. Repeats: sub-calls beyond the number recorded for their prompt.

| unit | exact | turns with the recorded history | sessions with the recorded answer | unrecorded calls | repeats | answers given back by evictions |
|---|---|---|---|---|---|---|
| stream_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
| wide_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
| auto_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
| auto-past_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
| wide-open_c8_r1 | yes | 114 / 114 | 11 / 11 | 0 | 0 | 0 |
