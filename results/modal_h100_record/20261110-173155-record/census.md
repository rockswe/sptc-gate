# What the recording's sessions wrote: 20261110-173155-record (measured)

`nospec`, rlms' batch path fixed (cloud/PREREG_RECORD.md). A single call is a sub-call recorded alone; a batch is one `llm_query_batched`. A loop of single calls is a turn with at least 20 of them, a loop of batches a turn with at least 5 batches. After-stream seconds: from the end of each root stream until that turn's code has run.

- 16 sessions: 1 deadline, 14 finished, 1 timeout.
- 0 with a loop of single calls (0 s after the streams in those turns), **6 with a loop of batches** (633 s), 5 with no sub-call.
- 14372 sub-calls recorded: 13 single calls and 644 batches.
- Time: 6027 s of sessions, 3790 s of root streams, 1895 s after them.
- Replayed: 10 sessions.

## The predictions (cloud/PREREG_RECORD.md, fixed before the recording)

| | prediction | measured | |
|---|---|---|---|
| R1 | the fix holds: no batched prompt comes back as `Event loop is closed` | 0 of 14361 batched prompts; the string is in the REPL output 0 times | held |
| R2 | the probe: stock rlms loses at least 16 of 80 prompts on this engine; with the fix, none | 21 of 80 (0, 16, 4, 1 by batch); 0 of 80 | held |
| R3 | loops of single calls: 1 to 5 of the 16 sessions have one | 0 of 16 | **did not hold** |
| R4 | loops of batches: at least 5 of the 16 sessions have one | 6 of 16 | held |
| R5 | at most 4 of the 16 sessions fail | 2 of 16 ({'timeout': 1, 'deadline': 1}) | held |
| R6 | of the sessions the timeout or the deadline stops, at least half have a loop of single calls | 0 of 2 | **did not hold** |

## Sessions

| session | status | wall s | turns | root streams s | after-stream s | sub-calls | single calls | batches (median size) | loops of single calls: turn (calls, s) | loops of batches: turn (batches, prompts, s) | most calls in a turn | replayed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trec132k-17000232.fix1 | finished | 124.3 | 9 | 123.0 | 0.5 | 13 | 0 | 1 (13) | - | - | 13 | yes |
| trec132k-17000241.fix1 | finished | 130.2 | 12 | 129.5 | 0.0 | 0 | 0 | 0 (-) | - | - | 0 | yes |
| trec132k-17000222.fix1 | finished | 899.1 | 12 | 888.5 | 0.0 | 0 | 0 | 0 (-) | - | - | 0 | no: a root reply was cut |
| trec132k-17000237.fix1 | finished | 536.1 | 8 | 94.6 | 440.6 | 6362 | 2 | 318 (20) | - | 4 (159, 3180, 363); 6 (159, 3180, 78) | 3181 | yes |
| pairs32k-16.fix1 | finished | 177.9 | 12 | 168.8 | 8.4 | 40 | 0 | 1 (40) | - | - | 40 | yes |
| pairs32k-20.fix1 | finished | 688.9 | 12 | 367.6 | 0.0 | 0 | 0 | 0 (-) | - | - | 0 | no: a root reply was cut |
| pairs32k-1.fix1 | finished | 122.0 | 7 | 82.5 | 38.7 | 787 | 0 | 40 (20) | - | 4 (40, 787, 39) | 787 | yes |
| pairs32k-15.fix1 | finished | 263.4 | 12 | 262.9 | 0.0 | 0 | 0 | 0 (-) | - | - | 0 | yes |
| trec132k-17000232.fix2 | timeout | 920.1 | 10 | 919.7 | 0.0 | 0 | 0 | 0 (-) | - | - | 0 | no: a root reply was cut |
| trec132k-17000241.fix2 | finished | 110.7 | 12 | 104.6 | 5.0 | 4 | 4 | 0 (-) | - | - | 1 | yes |
| trec132k-17000222.fix2 | deadline | 1339.7 | 11 | 118.4 | 1220.6 | 7 | 7 | 0 (-) | - | - | 4 | no: the deadline stopped it |
| trec132k-17000237.fix2 | finished | 229.3 | 12 | 151.6 | 76.6 | 3205 | 0 | 161 (20) | - | 9 (160, 3185, 76) | 3185 | yes |
| pairs32k-16.fix2 | finished | 114.8 | 10 | 88.9 | 25.6 | 1574 | 0 | 2 (787) | - | - | 787 | yes |
| pairs32k-20.fix2 | finished | 159.2 | 11 | 127.4 | 31.2 | 807 | 0 | 41 (20) | - | 6 (39, 767, 30) | 767 | no: does not reproduce (turn 8 block 1: output differs from the recorded one; turn 9: message history di) |
| pairs32k-1.fix2 | finished | 90.8 | 7 | 72.6 | 17.8 | 786 | 0 | 40 (20) | - | 4 (40, 786, 18) | 786 | yes |
| pairs32k-15.fix2 | finished | 120.4 | 10 | 89.9 | 30.2 | 787 | 0 | 40 (20) | - | 5 (39, 767, 30) | 767 | no: does not reproduce (turn 6 block 1: output differs from the recorded one; turn 7: message history di) |

## The probe before the first unit

Batches of 20 prompts through rlms' own path; the last one after 6 s without a request.

| rlms | prompts lost, by batch | of |
|---|---|---|
| stock 0.1.3 | 0, 16, 4, 1 | 21 of 80 |
| with the fix | 0, 0, 0, 0 | 0 of 80 |

## Batched prompts, by unit

| unit | sent through the fix | failed, by cause | tasks the deadline stopped |
|---|---|---|---|
| nospec_c8_r1 | 7202 | none | none |
| nospec_c8_r2 | 7159 | none | trec132k-17000222 |
