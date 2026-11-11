# Addendum: what the replay of the recording should show (fixed before the replay)

Written 2026-11-10, after the recording (`20261110-173155-record`) and before its replay.
`replay_campaign.py` records this file's sha256 and `design_fixed.json`'s in
`campaign.jsonl` before the first unit. Never edit either after the run.
`PREREG_RECORD.md` is unchanged since the recording hashed it (sha256 `77de9271…`).

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)).*

## What the recording showed

16 sessions, 41 H100-minutes. The census is `record_report.py`'s
(`../results/modal_h100_record/20261110-173155-record/census.md`).

| | prediction | measured | |
|---|---|---|---|
| R1 | the fix holds: no batched prompt comes back as `Event loop is closed` | 0 of 14,361 batched prompts | held |
| R2 | the probe: stock rlms loses at least 16 of 80 prompts on this engine; with the fix, none | 21 of 80 (0, 16, 4 and 1 by batch); 0 of 80 | held |
| R3 | loops of single calls: 1 to 5 of the 16 sessions have one | 0 of 16 | **did not hold** |
| R4 | loops of batches: at least 5 of the 16 sessions have one | 6 of 16 | held |
| R5 | at most 4 of the 16 sessions fail | 2 of 16: one timeout, one deadline | held |
| R6 | of the sessions the timeout or the deadline stops, at least half have a loop of single calls | 0 of 2 | **did not hold** |

- With its batches answered, the model batched. 14,372 sub-calls were recorded: 13
  single calls and 644 batches. No session wrote a loop of 20 single calls. The scout's
  main case, as `PREREG_RECORD.md` defined it, does not occur in this recording.
- One session wrote two loops of single calls that the definition does not count.
  `trec132k-17000222.fix2` split its context into four chunks of 100,000 characters and
  called `llm_query` on each in a loop: 4 calls, 700 s, every answer cut at 4,096 tokens.
  Then it looped over 32 chunks of 100 lines. Three of those calls ran before the 1,200 s
  deadline refused the other 29. By the definition (20 recorded single calls in a turn)
  neither is a loop of single calls. In seconds they are most of the recording's waiting:
  1,221 of the 1,895 s after the streams.
- Both loops only store their results. Of the seven loops of batches, in six
  sessions, five do the same. One tests each result (`trec132k-17000237.fix2` turn 9).
  One splits each result and tests none (`pairs32k-20.fix2` turn 6: 39 batches, 30 s).
  That last shape is the scout's: the shipped shadow waits where a result is used, the
  scout does not.
- 10 of the 16 sessions are replayable. The six that are not:
  - 3 roots that wrote until their replies were cut at 3,000 deltas (one of them is the
    session the timeout stopped). None made a sub-call: 2,508 s of sessions between them.
  - 1 session the deadline stopped (above).
  - 2 that do not reproduce offline (`pairs32k-20.fix2`, `pairs32k-15.fix2`). Their code
    prints Python sets, whose order follows the process's hash seed. The replay fixes
    that seed (`PYTHONHASHSEED=0`); the recording did not, and a recording should. The
    one loop of the scout's shape is in one of these two: it is counted, not replayed.

## The corpus

Built by `replay_corpus.py build --tag fix`. Manifest sha256 `07fecba5…`
(`../results/modal_h100_record/corpus/manifest.json`).

| session | turns | recorded stream s | recorded after-stream s | sub-calls answered | returned an error | batches / single calls | ends with | sha256 |
|---|---|---|---|---|---|---|---|---|
| `trec132k-17000232.fix1` | 9 | 123.0 | 0.5 | 13 | 0 | 1 / 0 | answer | `c1bd733ff7c0` |
| `trec132k-17000241.fix1` | 12 | 129.5 | 0.0 | 0 | 0 | 0 / 0 | default_answer | `d595e9e95cb4` |
| `trec132k-17000237.fix1` | 8 | 94.6 | 440.6 | 6,362 | 0 | 320 / 0 | answer | `d0b24825a2bd` |
| `pairs32k-16.fix1` | 12 | 168.8 | 8.4 | 40 | 0 | 1 / 0 | answer | `790d4a54bff6` |
| `pairs32k-1.fix1` | 7 | 82.5 | 38.7 | 787 | 0 | 40 / 0 | answer | `9b52a3ee057e` |
| `pairs32k-15.fix1` | 12 | 262.9 | 0.0 | 0 | 0 | 0 / 0 | answer | `4bf28a829b3f` |
| `trec132k-17000241.fix2` | 12 | 104.6 | 5.0 | 4 | 0 | 0 / 4 | default_answer | `c5f4d37a62b3` |
| `trec132k-17000237.fix2` | 12 | 151.6 | 76.6 | 3,205 | 1 | 161 / 1 | answer | `d53ee22d2951` |
| `pairs32k-16.fix2` | 10 | 88.9 | 25.6 | 1,574 | 0 | 2 / 0 | answer | `882862ccae58` |
| `pairs32k-1.fix2` | 7 | 72.6 | 17.8 | 786 | 0 | 40 / 0 | answer | `924f3e68f741` |

Together: 101 turns, 12,771 sub-calls, 1 prompt that returns a recorded error (a context
overflow), 1,279 s of root streams and 613 s after them when recorded.

- Left out by `PREREG_RECORD.md`'s rule (one sub-call per turn, 120 s after the
  streams): none.
- Dropped for the budget: none. The dry run's five units sum to 30 minutes; the limit
  was 55.
- The loops of these 10 sessions (`design_fixed.json`): no loop of single calls, so
  M3, M4 and M5 have nothing to test. Five loops of batches. One of them tests each result
  (`trec132k-17000237.fix2` turn 9: `if label == 'location':` inside the loop), the other
  four only store them.

## What I have seen when writing this

- The recording: its census, and the code of every turn named here.
- A local dry run of the design: the same code, corpus and arms against
  `tests/fake_engine.py` at 45 ms a step, each speculative launch slowed to 2 ms as in a
  busy process on Modal (`/tmp`, not kept). All units exact. Numbers below.
- Something in spec-ptc I had not seen before. Its launcher keeps at most 120,000
  characters of speculative prompts in flight per session (`Budget.max_inflight_chars`,
  "the prefill-pressure control"; `speculation.py:353` at `9b78b7d`). A call that does not
  fit waits in its worker thread. That is about 43,000 tokens of OOLONG text, so it only
  matters for long prompts. The four chunk calls of `trec132k-17000222.fix2` are far over
  it: launched together, they run one long one at a time.

## What I now expect, and why it differs from `PREREG_RECORD.md`

`PREREG_RECORD.md` expected the scout to gain a little on loops of batches (M6: 0.55 to
0.95 of `stream`), because "a batch of 20 fills 16 slots, then 4: the scout fills all 16".
That reasoning was wrong, and the records of November 9 already said so: a loop of
batches that only stores its results is launched whole by the shipped client, whose
placeholder for a result does not make the shadow wait until the result is used. That is
the "burst over the cap" of the first campaign. So on these 10 sessions the scout has
nothing to add at the same window. **M6 will fail on its scout half, and the number
reported first will be about 1.00.** The one recorded loop where the scout would add
something is 30 s long and cannot be replayed.

## The dry run

Summed over the 10 sessions, one unit per arm:

| arm | session time s | of `nospec` | of `stream` | after-stream s | unit s |
|---|---|---|---|---|---|
| `nospec` | 1,837.5 | - | 1.126 | 579.2 | 516 |
| `stream` | 1,632.0 | 0.888 | - | 353.5 | 345 |
| `scout` | 1,632.1 | 0.888 | 1.000 | 353.6 | 345 |
| `wide` | 1,455.4 | 0.792 | 0.892 | 135.3 | 261 |
| `nospec-wide` | 1,706.5 | 0.929 | 1.046 | 441.7 | 431 |

The turns that waited, seconds after the stream:

| session | turn | sub-calls | `nospec` | `stream` | `scout` | `wide` | `nospec-wide` |
|---|---|---|---|---|---|---|---|
| `trec132k-17000237.fix1` | 4 | 3,181 | 356.0 | 215.4 | 215.4 | 56.1 | 288.6 |
| `trec132k-17000237.fix2` | 9 | 3,185 | 70.5 | 70.4 | 70.4 | 62.6 | 51.9 |
| `trec132k-17000237.fix1` | 6 | 3,181 | 71.7 | 41.1 | 41.1 | 13.2 | 54.4 |
| `pairs32k-1.fix2` | 4 | 786 | 16.4 | 8.5 | 8.5 | 0.9 | 12.9 |
| `pairs32k-16.fix1` | 8 | 40 | 9.4 | 7.8 | 7.8 | 2.1 | 4.2 |
| `pairs32k-16.fix2` | 6 | 787 | 10.8 | 5.1 | 5.1 | 0.0 | 2.3 |
| `pairs32k-16.fix2` | 5 | 787 | 10.7 | 4.9 | 4.9 | 0.0 | 2.2 |

- The shipped client is ahead of no speculation here by more than in the registered
  replay (0.89 against 0.95): there half the batched prompts returned an error at once,
  in every arm.
- In turn 9 of `trec132k-17000237.fix2` no speculative arm helps. The loop tests each
  result, so the scout stops at the first test and the shadow waits at every batch. rlms'
  own batches at 128 are the fastest there.

## Two things added to the design

Neither is in `PREREG_RECORD.md`. Both run after its five units, so a budget stop costs
them first, and neither enters the number reported first.

1. A control, `nospec-wide` (no speculation, rlms' batches 128 wide), one unit. The
   corpus turned out to be loops of batches of 20. On one huge batch, width needed no
   speculation (the registered replay). A loop of small batches is the other case: a wider
   handler gives each batch at most 20 in flight.
2. One extra unit on 11 sessions: the 10, and `trec132k-17000222.fix2` replayed up to
   its turn 10, the last turn that ended before the deadline (`replay_corpus.py`, a
   session the deadline stopped). Arm `stream-open`: spec-ptc at `9b78b7d` with its
   character budget lifted. It is the only place in these recordings where real code asks
   the engine for several long prompts at once: three of 36,000 tokens and one of 6,000,
   each answered with 4,096 tokens, next to the other sessions. The engine's KV cache
   holds 154,816 tokens.

## Predictions, in numbers

Scored by `replay_report.py` from `design_fixed.json` (`checks`). Definitions as in
`PREREG_RECORD.md`. M1 to M7 stand as registered.

| | prediction | dry run | counts against it |
|---|---|---|---|
| D1 | Session time: `stream` at 0.83 to 0.95 of `nospec` | 0.888 | outside |
| D2 | **The number reported first, `scout` over `stream`: 0.97 to 1.03** | 1.000 | below 0.97: the scout finds something the shipped client does not |
| D3 | Session time: `wide` at 0.84 to 0.96 of `stream` | 0.892 | above 0.96: a window of 128 buys nothing on loops of small batches |
| D4 | Root stream seconds: `scout` within 5% of `stream` | 1.000 | outside |
| D5 | Root stream seconds: `wide` within 10% of `stream` | 1.033 | more than 10% above |
| D6 | The largest loop of batches (`trec132k-17000237.fix1` turn 4): `stream` at most 0.80 of `nospec` | 0.605 | above 0.80: the shipped client does not launch it ahead |
| D7 | The same turn: `wide` at most 0.50 of `stream` | 0.260 | above 0.50 |
| D8 | The loop that tests each result (`trec132k-17000237.fix2` turn 9): `stream` at least 0.85 of `nospec` | 0.999 | below 0.85 |
| D9 | The same turn: `scout` at least 0.85 of `stream` | 1.000 | below 0.85: the scout launched calls behind a test |
| D10 | Control: `nospec-wide` at 0.86 to 0.98 of `nospec` in session time | 0.929 | outside |
| D11 | Control: `wide` at most 0.93 of `nospec-wide` in session time | 0.853 | above 0.93: on loops of small batches too, width needs no speculation |

The dry run's engine batches for free and has no limit. It predicted the registered
replay's session ratios within 0.03 and its bursts badly, which is why D3 and D7 are wide.

**The extra unit** is scored by hand from `extra/summary.md`:

| | prediction | what it rests on | counts against it |
|---|---|---|---|
| X1 | The unit is exact | every unit so far | not exact |
| X2 | With the budget lifted the four chunk calls leave together: all four requests are sent within 2 s | the dry run, `tests/test_replay_chars.py` | later |
| X3 | The turn takes at most 420 s after its stream | 195 s in the dry run, where the same turn takes 575 s as shipped and 770 s without speculation. Recorded without speculation: 700 s | more than 420 s: the engine cannot run them together |

Not predicted, and the reason for the unit: what the engine does with them. Their prompts
and answers come to about 131,000 tokens, 85% of the KV cache, before the other sessions'
requests. Watched: the KV cache's peak, preemptions, requests waiting, and the other ten
sessions' root streams and stalls next to the registered `stream` unit.

## Budget

| unit | sessions | dry run s |
|---|---|---|
| `scout`, thrown away | 10 | 345 |
| `stream` | 10 | 345 |
| `scout` | 10 | 345 |
| `wide` | 10 | 261 |
| `nospec` | 10 | 516 |
| `nospec-wide` (control) | 10 | 431 |
| `stream-open` (extra) | 11 | 432 |

About 45 minutes of units, and 5 to start the engine and warm it. `--max-minutes 66`,
hard timeout 75 minutes.

## What the result changes

`PREREG_RECORD.md`'s rule stands. If D2 holds, its third case applies: on unprovoked
OOLONG code the scout as built gains little at the shipped window, and the README leads
the H100 section with that. The registered 0.72 stays as the registered run's number, with
what this run says of it: the loop it removed was written because rlms was failing.

What the README would then say is left to win on this workload:

- the window, if D3 holds, and that on loops of small batches it needs speculation to
  use it (D11);
- loops that test each result, where neither client launches ahead (D8, D9);
- long prompts, where the shipped client holds itself back (the extra unit).
