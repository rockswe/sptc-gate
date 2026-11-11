# A recording with rlms fixed, and its replay, on a Modal H100, November 10, 2026 (measured)

The replay of the first recordings took session time to 0.72 of the shipped client's with
the scout (`../modal_h100_replay/RESULTS.md`). One session carried most of that, and its
loop of 319 single calls was the model's way around a bug: rlms 0.1.3 loses prompts of
every batch after a session's first. This run fixes rlms in the harness, records 16 new
sessions without speculation, and replays those that can be replayed.

**The question** (`cloud/PREREG_RECORD.md`, fixed before the recording): how often does
the model write serial loops when rlms is not failing under it, and what does the scout
recover on those sessions?

## In short

- The fix held. 14,361 batched prompts went through it and none was lost. On the same
  engine stock rlms lost 21 of 80 probe prompts.
- With its batches answered, the model batched. 13 single calls and 644 batches in 16
  sessions. No session wrote a loop of 20 single calls. I had predicted 1 to 5.
- On these sessions the scout adds nothing: 1.003 of the shipped client's session
  time (10 sessions, every unit exact). By the rule fixed beforehand: on unprovoked
  OOLONG code the scout as built gains little at the shipped window. The registered 0.72
  was the bug's.
- The reason is in the shipped client. The model's loops of batches only store their
  results, and spec-ptc launches such a loop whole: a result's placeholder does not make
  its shadow wait until the result is used. The scout launches the same calls.
- The shipped client is at 0.890 of no speculation here. On the first corpus it was at
  0.954.
- What is left is the window. 128 calls in flight took session time to 0.874 of the
  shipped client's. Width alone, rlms' own batches at 128 with no speculation, gave 0.922
  of no speculation: a batch of 20 cannot use it.
- One loop tests each result, and no arm launches it ahead. 80 s as shipped, 78 s with
  the scout, 63 s at 128 in flight, 57 s with rlms' batches at 128 and no speculation.
- spec-ptc holds long prompts back itself. It keeps at most 120,000 characters of
  speculative prompts in flight per session. With that budget lifted, four long calls of
  one session ran together: 178 s, where the recording took 700 s without speculation.
  The KV cache reached 88%, nothing was preempted, and the other ten sessions ran within
  1% of their time without it.
- Predictions: 4 of 6 held for the recording, 14 of the 15 that could be tested for
  the replay, 3 of 3 for the extra unit. The one that failed in the replay is my own
  reasoning about the scout on loops of batches (M6); the addendum said it would.
- 10 of the 16 sessions could be replayed. One loop of the scout's shape (30 s) is in
  a session that could not, through a mistake in my recording harness.

## Setup

- Engine: one H100 80 GB on Modal per launch, vLLM 0.32.0,
  `Qwen/Qwen3-30B-A3B-Instruct-2507`, the campaign's server flags with
  `--max-model-len 65536`.
- The recording (`cloud/rlm_record.py`): the campaign's `nospec` arm, its 8 tasks, 8 at
  a time, twice. spec-ptc at `9b78b7d`, rlms 0.1.3, the 900 s task timeout, roots streamed
  and cut after 3,000 deltas, two warm-up passes, as in the rerun of November 9. Three
  things are new:
  1. rlms' batch path is fixed (`cloud/batch_fix.py`): a client's async requests run on
     one event loop of its own. The request and rlms' width of 16 are unchanged.
  2. A probe before the first unit: four batches of 20 through rlms' own path, with
     stock rlms and with the fix.
  3. A deadline for a task's sub-calls: 1,200 s after a task starts they are refused
     and the task counts as failed.
- The replay (`cloud/replay_campaign.py`): another launch. Units, one each: a `scout`
  unit that is thrown away, then `stream`, `scout`, `wide`, `nospec`, as registered. After
  them a control (`nospec-wide`) and one extra unit (`stream-open`), both declared in the
  addendum before the run.

| run | what | GPU time |
|---|---|---|
| `t4_smoke/20261110-172345-smoke` | the recording's plumbing on a T4 with a 1.7B model | 5 min of T4 |
| `20261110-173155-record` | the recording: 2 `nospec` units, 16 sessions | 41 min |
| `20261110-191427-replay` | the replay: 7 units | 46 min |

- Integrity. The hashes are of the files as they were at run time. The published
  pre-registration files and campaign scripts have since had planning notes, schedule
  notes and costs removed, so they hash differently.
  The recording wrote the sha256 of `PREREG_RECORD.md` (`77de9271…`) into
  its `campaign.jsonl` before its first unit, next to the hashes of the campaign code,
  `batch_fix.py` and `rlm_record.py`. The replay wrote those of `PREREG_RECORD.md`,
  `PREREG_RECORD_ADDENDUM.md` (`f6c81a46…`), `design_fixed.json` (`1a767d03…`), the replay
  code, both client trees (`f46414b0…`, `7aa23f07…`: the trees the follow-up replay ran)
  and the corpus (manifest `07fecba5…`).
- Files here: per run `campaign.jsonl`, `server.json`, `launch.json` and its
  summaries; the recording's `census.md` (`cloud/record_report.py`); the corpus's
  `manifest.json`; the replay's `design.json`, each unit's `replay.json`, and
  `long_calls.md` (`cloud/long_calls.py`). Events and trajectories hold OOLONG text and
  stay out of the repository.

## 1. The recording's predictions

| | prediction | measured | |
|---|---|---|---|
| R1 | the fix holds: no batched prompt comes back as `Event loop is closed` | 0 of 14,361 batched prompts | held |
| R2 | the probe: stock rlms loses at least 16 of 80 prompts on this engine; with the fix, none | 21 of 80 (0, 16, 4 and 1 by batch); 0 of 80 | held |
| R3 | loops of single calls: 1 to 5 of the 16 sessions have one | 0 of 16 | **did not hold** |
| R4 | loops of batches: at least 5 of the 16 sessions have one | 6 of 16 | held |
| R5 | at most 4 of the 16 sessions fail | 2 of 16: one timeout, one deadline | held |
| R6 | of the sessions the timeout or the deadline stops, at least half have a loop of single calls | 0 of 2 | **did not hold** |

- R3 failed downwards. I had given it 7 chances in 8, from 2 such loops in the 16
  sessions of November's `stream` arm. With every batch answered, no session wrote a loop
  of 20 single calls.
- R3 and R6 fail by the definition, and the definition misses something. A loop of
  single calls was "a turn with at least 20 single calls recorded". One session wrote two
  loops of single calls that are not that (section 2).

## 2. What the 16 sessions wrote

`cloud/record_report.py`, from the trajectories. A single call is a sub-call recorded
alone; a batch is one `llm_query_batched`. After-stream seconds: from the end of each
root stream until that turn's code has run.

| session | status | wall s | turns | root streams s | after-stream s | sub-calls | single calls | batches (median size) | loops of batches | replayed |
|---|---|---|---|---|---|---|---|---|---|---|
| `trec132k-17000232.fix1` | finished | 124 | 9 | 123 | 0 | 13 | 0 | 1 (13) | - | yes |
| `trec132k-17000241.fix1` | finished | 130 | 12 | 130 | 0 | 0 | 0 | 0 | - | yes |
| `trec132k-17000222.fix1` | finished | 899 | 12 | 889 | 0 | 0 | 0 | 0 | - | no: a root reply was cut |
| `trec132k-17000237.fix1` | finished | 536 | 8 | 95 | 441 | 6,362 | 2 | 318 (20) | turn 4: 159 batches, 3,180 prompts, 363 s; turn 6: 159 batches, 3,180 prompts, 78 s | yes |
| `pairs32k-16.fix1` | finished | 178 | 12 | 169 | 8 | 40 | 0 | 1 (40) | - | yes |
| `pairs32k-20.fix1` | finished | 689 | 12 | 368 | 0 | 0 | 0 | 0 | - | no: a root reply was cut |
| `pairs32k-1.fix1` | finished | 122 | 7 | 82 | 39 | 787 | 0 | 40 (20) | turn 4: 40 batches, 787 prompts, 39 s | yes |
| `pairs32k-15.fix1` | finished | 263 | 12 | 263 | 0 | 0 | 0 | 0 | - | yes |
| `trec132k-17000232.fix2` | timeout | 920 | 10 | 920 | 0 | 0 | 0 | 0 | - | no: a root reply was cut |
| `trec132k-17000241.fix2` | finished | 111 | 12 | 105 | 5 | 4 | 4 | 0 | - | yes |
| `trec132k-17000222.fix2` | deadline | 1,340 | 11 | 118 | 1,221 | 7 | 7 | 0 | - | no: the deadline (as an extra, up to turn 10) |
| `trec132k-17000237.fix2` | finished | 229 | 12 | 152 | 77 | 3,205 | 0 | 161 (20) | turn 9: 160 batches, 3,185 prompts, 76 s | yes |
| `pairs32k-16.fix2` | finished | 115 | 10 | 89 | 26 | 1,574 | 0 | 2 (787) | - | yes |
| `pairs32k-20.fix2` | finished | 159 | 11 | 127 | 31 | 807 | 0 | 41 (20) | turn 6: 39 batches, 767 prompts, 30 s | no: does not reproduce |
| `pairs32k-1.fix2` | finished | 91 | 7 | 73 | 18 | 786 | 0 | 40 (20) | turn 4: 40 batches, 786 prompts, 18 s | yes |
| `pairs32k-15.fix2` | finished | 120 | 10 | 90 | 30 | 787 | 0 | 40 (20) | turn 5: 39 batches, 767 prompts, 30 s | no: does not reproduce |

Together: 6,027 s of sessions, 3,790 s of root streams, 1,895 s after them. 14,372
sub-calls: 13 single calls and 644 batches.

- With its batches answered, the model batched. Its serial shape is a loop of batches
  of 20: seven such loops in six sessions, 633 s of the waiting.
- Five of the seven loops only store their results. The shipped client launches such a
  loop whole: its placeholder for a result does not make the shadow wait until the result
  is used. That was the "burst over the cap" of the first campaign.
- One loop tests each result (`trec132k-17000237.fix2` turn 9:
  `if label == 'location':` inside the loop, 76 s). The scout places no bet, so it stops
  at the first test, and the shadow waits at every batch.
- One loop splits each result and tests none (`pairs32k-20.fix2` turn 6, 30 s). That
  is the scout's case: the shadow waits where a result is used, the scout does not. It is
  the only one in 16 sessions, and its session cannot be replayed.
- One session wrote two loops of single calls that the definition does not count.
  `trec132k-17000222.fix2` cut its context into four chunks of 100,000 characters and
  called `llm_query` on each in a loop: 4 calls, 700 s, each of three prompts 36,000
  tokens long, every answer cut at 4,096 tokens. Then it looped over 32 chunks of 100
  lines: three calls ran before the deadline refused the other 29. Both loops only store
  their results. In seconds they are most of the recording's waiting: 1,221 of 1,895 s.
- Three roots wrote until they were cut, in turn after turn (6, 2 and 7 replies cut at
  3,000 deltas). None made a sub-call. One of them then spent 321 s in rlms' last,
  unstreamed answer call, which the cap does not reach.
- Five sessions made no sub-call at all.

## 3. The fix and the probe

| rlms | where | prompts lost, by batch | of |
|---|---|---|---|
| stock 0.1.3 | a fake server (`cloud/tests/test_batch_fix.py`) | 0, 16, 4, 16 | 36 of 80 |
| stock 0.1.3 | vLLM on a T4, Qwen3-1.7B | 0, 16, 4, 1 | 21 of 80 |
| stock 0.1.3 | vLLM on the H100, Qwen3-30B-A3B | 0, 16, 4, 1 | 21 of 80 |
| with the fix | all three | 0, 0, 0, 0 | 0 of 80 |

- The fourth batch comes 6 s after the third. uvicorn closes a kept connection after
  5 s without a request, so by then the server has dropped all but one of the connections
  the dead loop left behind: 1 prompt lost in place of 16. Batches that follow each other
  closely are the ones that lose most.
- In the recording: 14,361 batched prompts through the fix, none failed for any
  reason (`batch_fix.json` per unit). The string `Event loop is closed` is in no REPL
  output.
- rlm's main branch had the same two files on November 10 (`rlm/clients/openai.py`,
  `rlm/core/lm_handler.py`), and 0.1.3 was the latest release.

## 4. The corpus

`cloud/replay_corpus.py build --tag fix`: 10 sessions for the registered replay, and the
session the deadline stopped, up to its turn 10, for the extra unit. Each was run again
offline and kept only if every block prints what it printed and every turn's message
history has the recorded sha256.

- Registered: 101 turns, 12,771 sub-calls, one prompt that returns a recorded error
  (a context overflow), 1,279 s of root streams and 613 s after them when recorded.
- Left out by the rule fixed beforehand (one sub-call per turn, 120 s after the
  streams): none. **Dropped for the budget:** none.
- Not replayable, 6 of 16:
  - the three roots that wrote until cut (2,508 s of sessions, none of it waiting for a
    sub-call);
  - the session the deadline stopped;
  - two that do not reproduce offline. Their code prints Python sets, whose order follows
    the process's hash seed. The replay fixes it (`PYTHONHASHSEED=0`); the recording did
    not. That is a mistake in my harness, and it cost the one loop of the scout's shape.

## 5. The replay's predictions

`20261110-191427-replay`, scored by `cloud/replay_report.py` from `design.json` as hashed
before the first unit. M1 to M7 are `PREREG_RECORD.md`'s, D1 to D11 the addendum's.

| | prediction | dry run | measured | |
|---|---|---|---|---|
| M1 | every unit exact | all exact | 5 of 5 (7 of 7 with the thrown-away and the extra unit) | held |
| M2 | in the fork's arms no call is sent twice and none is evicted | 0, 0 | 0, 0 | held |
| M3 | a loop of single calls stays serial as shipped | - | - | not testable: the corpus has none |
| M4 | the scout removes one that only stores or prints each result | - | - | not testable |
| M5 | the scout does not remove one that tests each result | - | - | not testable |
| M6 | loops of batches: `scout` at 0.55 to 0.95 of `stream` over those turns, `wide` at most 0.45 | 1.000, 0.396 | 0.990, 0.406 | **did not hold** |
| M7 | the number reported first, `scout` over `stream` in session time, is at least 0.78 | 1.000 | 1.003 | held |
| D1 | session time: `stream` at 0.83 to 0.95 of `nospec` | 0.888 | 0.890 | held |
| D2 | the number reported first is 0.97 to 1.03 | 1.000 | 1.003 | held |
| D3 | session time: `wide` at 0.84 to 0.96 of `stream` | 0.892 | 0.874 | held |
| D4 | root stream seconds: `scout` within 5% of `stream` | 1.000 | 1.006 | held |
| D5 | root stream seconds: `wide` within 10% of `stream` | 1.033 | 1.027 | held |
| D6 | the largest loop of batches (`trec132k-17000237.fix1` turn 4): `stream` at most 0.80 of `nospec` | 0.605 | 0.622 | held |
| D7 | the same turn: `wide` at most 0.50 of `stream` | 0.260 | 0.253 | held |
| D8 | the loop that tests each result (`trec132k-17000237.fix2` turn 9): `stream` at least 0.85 of `nospec` | 0.999 | 1.003 | held |
| D9 | the same turn: `scout` at least 0.85 of `stream` | 1.000 | 0.977 | held |
| D10 | control: `nospec-wide` at 0.86 to 0.98 of `nospec` in session time | 0.929 | 0.922 | held |
| D11 | control: `wide` at most 0.93 of `nospec-wide` in session time | 0.853 | 0.844 | held |
| X1 | the extra unit is exact | exact | exact | held |
| X2 | with the character budget lifted the four chunk calls leave within 2 s of each other | 0.0 s | 0.0 s | held |
| X3 | that turn takes at most 420 s after its stream | 195 s | 178 s | held |

- M6 failed on its scout half, as the addendum said it would. `PREREG_RECORD.md`
  reasoned that "a batch of 20 fills 16 slots, then 4: the scout fills all 16". The
  shipped client fills them already. The first campaign's "burst over the cap" turns
  were this, and I had not read my own record that way.
- The local dry run was within 0.03 on every ratio of this table. For the
  registered replay it had been far off on bursts. The difference is one setting: each
  speculative launch was slowed to 2 ms, the rate measured in a busy process on Modal.
- By `PREREG_RECORD.md`'s rule, a first number above 0.95 means: on unprovoked OOLONG
  code the scout as built gains little at the shipped window.

## 6. Arms and sessions

One launch, one unit per arm, the 10 sessions 8 at a time. Session time: the sum of the
sessions' wall times. After-stream: from the end of each root stream until that turn's
code has run.

| arm | session time s | root streams s | after-stream s | of `nospec` | of `stream` | per session, of `stream` [95% CI] |
|---|---|---|---|---|---|---|
| `nospec` | 1,728.4 | 1,149.7 | 572.3 | - | 1.124 | 1.085 [1.011, 1.184] |
| `stream` | 1,537.9 | 1,164.4 | 366.8 | 0.890 | - | - |
| `scout` | 1,541.9 | 1,171.4 | 363.1 | 0.892 | **1.003** | 1.004 [0.996, 1.011] |
| `wide` | 1,344.8 | 1,195.7 | 142.9 | 0.778 | **0.874** | 0.917 [0.786, 1.016] |
| `nospec-wide` (control) | 1,592.8 | 1,159.7 | 426.1 | 0.922 | 1.036 | 1.026 [0.972, 1.091] |

By session, wall seconds (after-stream seconds):

| session | `nospec` | `stream` | `scout` | `wide` | `nospec-wide` |
|---|---|---|---|---|---|
| `trec132k-17000237.fix1` | 486.4 (405.7) | 332.7 (253.4) | 332.3 (251.5) | 158.7 (72.8) | 398.3 (317.8) |
| `trec132k-17000237.fix2` | 232.9 (80.5) | 235.0 (80.3) | 235.2 (78.4) | 219.8 (63.0) | 212.8 (57.5) |
| `pairs32k-15.fix1` | 232.3 (0.0) | 234.8 (0.0) | 234.9 (0.0) | 234.0 (0.1) | 233.4 (0.0) |
| `pairs32k-16.fix1` | 155.1 (8.3) | 155.0 (7.0) | 155.9 (7.1) | 155.2 (2.0) | 151.8 (3.3) |
| `pairs32k-16.fix2` | 115.5 (24.4) | 107.2 (14.2) | 105.4 (13.9) | 93.6 (0.3) | 98.0 (7.1) |
| `trec132k-17000241.fix2` | 108.8 (5.0) | 107.6 (0.0) | 109.1 (0.0) | 112.7 (0.0) | 110.4 (5.0) |
| `trec132k-17000241.fix1` | 107.6 (0.0) | 107.6 (0.0) | 109.6 (0.0) | 112.7 (0.0) | 108.7 (0.0) |
| `trec132k-17000232.fix1` | 101.0 (0.4) | 101.2 (0.0) | 102.3 (0.0) | 105.5 (0.0) | 102.5 (0.4) |
| `pairs32k-1.fix1` | 98.7 (28.7) | 74.9 (1.3) | 76.4 (1.6) | 77.6 (0.1) | 92.1 (19.1) |
| `pairs32k-1.fix2` | 90.2 (19.4) | 81.9 (10.6) | 80.6 (10.4) | 75.0 (4.6) | 84.8 (15.8) |

- No session moves between `stream` and `scout`. The largest difference is 2 s.
- One session carries the window's gain: `trec132k-17000237.fix1`, 333 s to 159 s. It
  is 174 of the 193 s `wide` saves.
- The shipped client hides a whole loop of batches behind the root's stream where
  the root goes on writing after the loop (`pairs32k-1.fix1`: 28.7 s to 1.3 s).
- The root is now 76% of session time as shipped, and 89% at 128 in flight.

## 7. The turns

Turns in which `stream` spent at least 1 s after its stream, with the cause its own
events give (`analyze.turn_cause`). Seconds after the stream.

| session | turn | sub-calls | what the loop does | cause in `stream` | `nospec` | `stream` | `scout` | `wide` | `nospec-wide` |
|---|---|---|---|---|---|---|---|---|---|
| `trec132k-17000237.fix1` | 4 | 3,181 | 159 batches of 20, stored | burst over the cap | 334.4 | 208.0 | 206.4 | 52.7 | 269.7 |
| `trec132k-17000237.fix2` | 9 | 3,185 | 160 batches of 20, each result tested | serial launches | 79.9 | 80.2 | 78.3 | 62.9 | 57.0 |
| `trec132k-17000237.fix1` | 6 | 3,181 | 159 batches of 20, stored | burst over the cap | 71.3 | 45.4 | 45.1 | 20.1 | 48.1 |
| `pairs32k-1.fix2` | 4 | 786 | 40 batches of 20, stored | burst over the cap | 19.3 | 10.5 | 10.4 | 4.5 | 15.8 |
| `pairs32k-16.fix2` | 6 | 787 | one batch | burst over the cap | 12.1 | 7.3 | 6.9 | 0.1 | 3.9 |
| `pairs32k-16.fix1` | 8 | 40 | one batch | burst over the cap | 8.3 | 6.9 | 7.1 | 2.0 | 3.3 |
| `pairs32k-16.fix2` | 5 | 787 | one batch | burst over the cap | 12.2 | 6.9 | 7.0 | 0.1 | 3.1 |
| `pairs32k-1.fix1` | 4 | 787 | 40 batches of 20, stored | burst over the cap | 28.6 | 1.2 | 1.5 | 0.1 | 19.1 |

| cause in `stream` | turns | `nospec` | `stream` | `scout` | `wide` | `nospec-wide` | `scout` recovers | `wide` recovers |
|---|---|---|---|---|---|---|---|---|
| burst over the cap | 7 | 486.4 | 286.3 | 284.4 | 79.6 | 363.1 | 1% | 72% |
| serial launches | 1 | 79.9 | 80.2 | 78.3 | 62.9 | 57.0 | 2% | 22% |

- Seven of the eight turns are bursts over the cap. Everything is launched; 16 in
  flight is what holds it. That is the window's case, and the scout's 1%.
- The one serial turn is a loop that tests each result:

  ```python
  for batch in batches:
      prompts = [...]                      # one prompt per line of the batch
      responses = llm_query_batched(prompts)
      for resp in responses:
          label = resp.strip()
          if label == 'location':          # the test: neither client launches past it
              count_location += 1
          elif label == 'abbreviation':
              count_abbreviation += 1
  ```

  The shadow waits at every batch for the labels. The scout stops at the first test: it
  places no bet. But the test cannot leave the loop, so every one of the 160 batches is
  certain. A scout that goes on past a test whose arms only assign would launch them
  all. It is not built. Here it is worth at most the 80 s of this turn.
- Three long prompts with answers of two or three tokens do not show
  (`trec132k-17000241.fix2`, one call a turn, prompts of 36,000 tokens): 1.6 s each
  without speculation, hidden by both clients.

## 8. Width, with and without speculation

`nospec-wide` is stock rlms with its batch width at 128 in place of 16.

| | `nospec` | `nospec-wide` | `stream` | `wide` |
|---|---|---|---|---|
| in flight at most | 16 within a batch | 128 within a batch | 16 | 128 |
| session time, of `nospec` | - | 0.922 | 0.890 | 0.778 |
| 159 batches of 20, stored (turn 4 above) | 334.4 | 269.7 | 208.0 | 52.7 |
| 160 batches of 20, each result tested | 79.9 | 57.0 | 80.2 | 62.9 |
| one batch of 787 | 12.2 | 3.1 | 6.9 | 0.1 |

- On one large batch width needs no speculation, as in the registered replay: rlms at
  128 runs a batch of 787 in 3 s.
- On a loop of batches of 20 it needs speculation to be used. A batch of 20 can fill
  20 of 128 slots, so rlms at 128 takes 270 s where the scout at 128 takes 53 s. The
  model chose 20 in every loop of batches it wrote.
- Where each result is tested, rlms at 128 is the fastest arm (57 s): the speculative
  arms send those batches one after another like rlms does, and pay for their threads.
- The root pays a little at 128: its streams are 2.7% longer than as shipped, with 52
  s of stalls against 23 s and one token gap of 3.5 s. Its median token gap does not move
  (43.0 ms against 43.6 ms).

## 9. Long prompts: spec-ptc's character budget

**What I had missed.** spec-ptc's launcher keeps at most 120,000 characters of speculative
prompts in flight per session (`Budget.max_inflight_chars`, "the prefill-pressure
control", `speculation.py:353` at `9b78b7d`). A call that does not fit waits in its
worker thread. That is about 43,000 tokens of OOLONG text: one call over a
100,000-character chunk at a time. The first write-ups name only the cap of 16 calls.

**Where it bites.** `trec132k-17000222.fix2`, turn 7: a loop over four chunks, three
prompts of 36,000 tokens and one of 6,000, every answer 4,096 tokens long.

```python
for i, chunk in enumerate(chunks):           # four chunks of 100,000 characters
    prompt = f"Classify each question in the following text ...\n\n{chunk}"
    result = llm_query(prompt)
    classification_results.append(result)    # stored, not used
```

The loop only stores its results, so the shipped client launches all four calls while the
root is still writing. Its character budget then runs the three long ones one after
another.

**The extra unit:** arm `stream-open`, the shipped client with that budget lifted, on 11
sessions: the 10, and this one up to its turn 10 (the recording's deadline struck in its
turn 11). Not part of the registered comparison.

| the turn's seconds after its stream | |
|---|---|
| recorded, no speculation (four calls one after another) | 700 |
| as shipped, from the recorded call times (three long calls one after another) | about 530 |
| budget lifted, measured (four calls together, 183 s each) | **178** |

What the engine did while the four calls ran (`long_calls.md`, a window of 183 s):

| | `stream-open`, in the window | `stream-open`, outside it | registered `stream` unit |
|---|---|---|---|
| KV cache, peak | 0.88 | - | 0.37 |
| preemptions | 0 | 0 | 0 |
| requests waiting, at most | 17 | - | 5 |
| other sessions' root token gap, median / 99th percentile ms | 42.7 / 61.4 | 43.7 / 61.2 | 43.6 / 57.8 |
| the ten sessions' time, summed | 1,551.3 s | | 1,537.9 s |
| the ten sessions' root streams, summed | 1,170.5 s | | 1,164.4 s |

- The engine took it. 114,000 tokens of prompts prefilled at once and four answers of
  4,096 tokens decoded next to ten other sessions. The KV cache went to 88%. Nothing was
  preempted.
- The other sessions did not pay. Their root token gap was the same inside the window
  as outside it, and their summed time was within 1% of the registered `stream` unit
  (1.009; root streams 1.005).
- One more such call would not have fitted. Four chunks of 100,000 characters with
  their answers are 160,000 tokens, more than this engine's 154,816. The budget is a
  sensible guard with a fixed number in it: 120,000 characters is a bit over a third of
  the 318,000 this engine held without trouble.
- So on this session spec-ptc as shipped leaves about 350 s on the table that the
  engine could have given at no cost to the others. This is one session, one launch.

## 10. The root and the engine

| unit | root gap median / 99th ms | stall s | sub-call median / 90th ms | running mean / max | waiting max | KV peak |
|---|---|---|---|---|---|---|
| `scout`, thrown away | 44.7 / - | 59.5 | - | - | - | - |
| `stream` | 43.6 / 57.8 | 23.4 | 246 / 1,069 | 16.9 / 44 | 5 | 0.37 |
| `scout` | 44.1 / 57.6 | 23.5 | 243 / 1,063 | 16.9 / 48 | 6 | 0.38 |
| `wide` | 43.0 / 68.8 | 52.0 | 488 / 1,244 | 26.6 / 128 | 40 | 0.40 |
| `nospec` | 43.2 / 56.6 | 16.7 | 262 / 1,046 | 11.2 / 45 | 4 | 0.34 |
| `nospec-wide` | 43.6 / 58.1 | 19.0 | 315 / 1,070 | 14.3 / 140 | 20 | 0.35 |
| `stream-open` (extra, 11 sessions) | 43.5 / 62.3 | 30.3 | 258 / 1,071 | 16.4 / 46 | 17 | 0.88 |

- No arm slows the root's tokens. The median gap is 43.0 to 44.1 ms in the units
  that count. This host was slower than the registered replay's (35 to 38 ms).
- Nothing was preempted in any unit.
- The first unit of the launch paid for a cold engine again, which is why it was
  thrown away: the same ten sessions took 1,679 s in it and 1,542 s in the `scout` unit
  that counts (1.09), with 60 s of root stalls against 23 s.
- One unit per arm, so this run has no repeat of its own. In the registered replay an
  arm's two units differed by 1 to 2% once the engine was warm.

## What it changes

- The registered 0.72 was the bug's. The loop the scout removed was written because
  rlms was losing the model's batch prompts. With rlms fixed the model wrote no such loop
  in 16 sessions, and on the 10 that could be replayed the scout ran at 1.003 of the
  shipped client.
- The scout's case is narrower than I had it: a loop that *uses* each result without
  *testing* it. A loop that only stores its results is already launched whole by the
  shipped client. A loop that tests each result is launched by neither. In 16 unprovoked
  sessions the scout's case came up once, for 30 s. In the 16 `stream` sessions of
  November 9 two sessions wrote loops of single calls, in five turns. By their code the
  scout would pass four of those turns (1,376 s) and stop in the fifth, whose loop tests
  each result (1,071 s). So the scout's case exists unprovoked, and so does the loop it
  stops at.
- The shipped client does more than its own benchmark can show. Here it is at 0.890
  of no speculation. spec-ptc's campaign pins rlms 0.1.3: its baseline arm sends batches
  through the path that loses prompts, and a lost prompt returns at once, so on loops of
  batches that baseline does as little as half the work.
- What is left on this workload, in order of size:
  1. the window (0.874 of the shipped client at 128 in flight, one session carrying it);
  2. long prompts held back by a fixed character budget (350 s in one session);
  3. loops that test each result (80 s in one session).
- The engine was never the limit. Not at 128 calls in flight per session, and not
  with 114,000 tokens of prompts prefilled at once.

## Bugs found

| in | what |
|---|---|
| spec-ptc `9b78b7d` | A character budget next to the cap of 16 calls: at most 120,000 characters of speculative prompts in flight per session (`speculation.py:353`). It is fixed, and a bit over a third of what this engine took at once |
| rlms 0.1.3 | The lost batch prompts depend on timing: uvicorn closes a kept connection after 5 s, so a batch that comes later than that loses 1 prompt where one that follows at once loses 16 |
| rlms 0.1.3 | Its last answer call, made when a session runs out of turns, is not streamed and has no length limit: one took 321 s |
| the model | 3 of 16 roots wrote until their replies were cut at 3,000 deltas, turn after turn, without making a sub-call |
| my recording harness | It ran without `PYTHONHASHSEED=0`. Two sessions print Python sets and could not be rebuilt offline; one of them holds the only loop of the scout's shape |
| my pre-registration | M6 expected the scout to gain on loops of batches. The shipped client launches those whole, as the first campaign's records already showed |
| my definition | "A loop of single calls: a turn with at least 20 recorded." A loop over four chunks, and one over 32 that its deadline stopped after three calls, are neither. They were 64% of the recording's waiting |

## Limits

- 16 sessions, one model, one workload. No loop of 20 single calls in 16 sessions does
  not put their rate at zero: with the 2 in 16 of November's `stream` arm it is 2 in 32,
  and a 95% interval of about 1% to 21%.
- 10 of 16 sessions were replayed. Three of the six others have nothing to speculate
  on (roots that wrote until cut). One is in the extra unit. Two could not be rebuilt,
  and one of those holds the one loop the scout would have helped: 30 s.
- One launch, one unit per arm. No repeat inside this run.
- `scout` against `stream` is a comparison of two clients on recorded code. It says
  the scout finds nothing more here. It does not say the scout is wrong: where a loop
  uses each result, it removed 87% of the waiting in the registered replay, and that
  shape does occur unprovoked.
- The extra unit is one session on one launch, outside the registered comparison. Its
  as-shipped time is computed from recorded call times, not measured.
- Quality is not measured: answers are replayed.
- An eager server, as in the campaign.
