# What the replay should show (fixed before the run)

Written 2026-11-10, before the H100 replay. `replay_campaign.py` records this file's
sha256 in `campaign.jsonl` before the first unit. Never edit it after a run.

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)).*

## The question

With the same code, the same sub-calls and the same answers in every arm,
how much of the time spec-ptc as shipped still spends after the root's stream does the
fork remove? RESULTS.md section 3 named two parts of that time: calls launched one after
another (serial launches), and bursts wider than the window (the cap). Those two are what
the fork is built for.

## What is fixed

- Engine: one H100 launch on Modal, vLLM 0.32.0, `Qwen/Qwen3-30B-A3B-Instruct-2507`,
  the campaign's server flags with `--max-model-len 65536` (as the rerun of November 9).
- Corpus: 8 recorded sessions, replayed 8 at a time. Manifest sha256 `4873c26c…`.

  | session | recorded in | turns | recorded stream s | recorded after-stream s | sub-calls answered | returned an error | batches / single calls | sha256 |
  |---|---|---|---|---|---|---|---|---|
  | `pairs32k-15` | 230918-main | 8 | 97.8 | 14.4 | 400 | 387 | 40 / 0 | `a079b6b4675d` |
  | `pairs32k-1` | 230918-main | 7 | 72.8 | 20.0 | 400 | 387 | 40 / 0 | `8defd8fef881` |
  | `pairs32k-20` | 230918-main | 9 | 92.7 | 0.0 | 0 | 0 | 0 / 0 | `23f0bc4b52cd` |
  | `trec132k-17000222` | 230918-main | 11 | 150.5 | 396.8 | 1,922 | 1,582 | 160 / 322 | `5eb309061a44` |
  | `trec132k-17000232` | 230918-main | 12 | 127.3 | 0.0 | 0 | 0 | 0 / 0 | `1690e701d8d1` |
  | `trec132k-17000241` | 230918-main | 12 | 62.1 | 57.5 | 3,182 | 0 | 1 / 0 | `74d7a3fbda22` |
  | `trec132k-17000222.w8k-c8` | 222742-main | 11 | 139.8 | 62.7 | 3,179 | 3 | 4 / 0 | `cbb487aba65b` |
  | `trec132k-17000232.w8k-c1` | 221230-smoke | 7 | 116.5 | 1.1 | 13 | 0 | 1 / 0 | `4c7d228f3ded` |

  Together: 77 turns, 9,096 sub-calls sent, 2,359 prompts that return a recorded error,
  859.5 s of root streams and 552.5 s after them when recorded.
- Arms: `nospec`, `stream`, `scout`, `wide`, two units each in ABBA order. Then one
  unit each of two controls: `wide-threads`, `nospec-wide`. Definitions: `replay.ARMS`.
- In every arm: rlms' LM handler listens with a backlog of 1,024; every unit salts its
  prompts; no task timeout; `PYTHONHASHSEED=0`. (`cloud/README.md`.)
- Budget: `--max-minutes 95`. A budget stop drops the controls first, then units of
  repeat 2. What ran is analysed; what did not is reported as not run.
- Analysis: `replay_report.py` as hashed in `campaign.jsonl`. A unit counts only if it
  is exact (`replay.json`).

### What is left out, and why

- `trec132k-17000237`. Its four sub-calls are one per turn (36,000-token prompts,
  4,096-token answers, 566 s after its streams when recorded). No arm can overlap calls of
  different turns, and every unit, the fork's included, would last 10 to 15 minutes
  because of it. Its seconds are counted as not recovered.
- `trec132k-17000241.w8k-c8`. No sub-calls; left out to keep 8 sessions at
  concurrency 8.
- Every session recorded in the `stream` arm. A claimed call left no record of its
  answer, so those sessions cannot be replayed. Section 3's own turns are among them. The
  corpus holds the same two shapes, in sessions recorded without speculation.

### What the corpus is, said plainly

- Recorded with stock rlms, whose batches lose prompts (RESULTS.md, Corrections 3). The
  2,359 error strings are replayed as recorded, at once, in every arm.
- Its largest item, a loop of 319 single calls in `trec132k-17000222` turn 7, is the
  model's reaction to those errors. The `stream` arm's recordings have loops of the same
  shape that are not (160 calls, twice), but this one is.

## Where the predictions come from

1. The recorded runs.
2. A local dry run of the whole design: the same code, corpus and arms against
   `tests/fake_engine.py` at 45 ms a step (`/tmp/sptc-sim-pred`, not kept). All six units
   were exact. The fake engine batches for free and has no capacity limit.
3. Its calibration: the recorded `nospec` unit's seven sessions on the fake engine at
   33 ms a step, against the recording.
   - Seconds after the streams: 1,043 simulated, 1,055 recorded (0.99).
   - Turns of single calls: 0.97 to 1.06 of the recorded time.
   - Turns of batches: 0.43 to 0.84. The real path is slower there than the model.
   - Root streams: 0.87. Real streams have stalls and a longer first token.
4. Two T4 smoke runs on Modal (1.7B model, 3 sessions: `20261110-031029-smoke`,
   `20261110-040955-smoke`): all ten units exact on a real vLLM. The client drove 130
   calls a second through 128 threads.
   - In the first run `wide` and `nospec-wide` used a wrong setting of the replay client:
     256 pooled keep-alive connections, where rlms' own client pools 100. httpx's async
     pool then fell to a third of its rate at 128 in flight. Fixed: the replay client is
     now built as rlms builds its own.
   - The second run has the fix. Seconds after the streams: 89 (`nospec`), 41
     (`nospec-wide`), 4 (`wide`), 1 (`wide-threads`).
   - A T4's times say nothing about the H100's.

So single-call turns are predicted from the dry run. For bursts the dry run is too fast:
its local client outruns Modal's, and its engine has no limit. Burst predictions are
therefore bounds, not points.

## Predictions

Seconds are after-stream seconds, an arm's mean over its units. "Waited turns" are the
turns in which `stream` spent at least 1 s after the stream. A turn's cause is read from
the `stream` arm's events (`analyze.turn_cause`, with its window of 16).

| | prediction | dry run | counts against it |
|---|---|---|---|
| P1 | Every unit is exact. No unrecorded call, no repeat | all exact | any unit not exact |
| P2 | No arm wastes a call: nothing evicted | 0 evicted | any eviction |
| P3 | **The shipped client leaves the serial loop serial.** `trec132k-17000222` turn 7: `stream` at least 0.90 of `nospec` | 1.00 | below 0.90 |
| P4 | **The scout removes it at the shipped window.** Same turn: `scout` at most 0.15 of `stream` | 0.07 | above 0.15 |
| P5 | **Serial launches.** Over the waited turns of that cause, `scout` recovers at least 75% of `stream`'s seconds, `wide` at least 85% | 88%, 96% | `scout` below 50%: the scout does not do on an engine what it does on paper |
| P6 | **The cap.** Over the waited turns of that cause, `scout` recovers between -15% and +15% (same window, nothing to recover), `wide` at least 50% | 0%, 91% | `wide` below 25%: a wider window buys nothing on this stack |
| P7 | **Sessions.** Sum of session times: `stream` 0.93 to 1.02 of `nospec`; `scout` at most 0.80 of `stream`; `wide` at most 0.75 of `stream` | 0.98, 0.72, 0.64 | `scout` above 0.90 |
| P8 | **The root pays little.** Sum of root stream seconds: `scout` within 5% of `stream`, `wide` within 10% | 1.00, 1.02 | `wide` more than 15% above |
| P9 | **A replay is repeatable.** An arm's two units differ by less than 5% in summed session time (live: a factor of 1.9 per task) | one unit each | 10% or more |
| P10 | **Controls.** `wide-threads` is within 25% of `wide` in summed session time. `nospec-wide` recovers at most 10% of `stream`'s serial-launch seconds, and its summed session time is at least 0.90 of `nospec`'s | 0.99; -6%; 0.95 | - |

The headline number: of the seconds `stream` spends after its streams in these 8
sessions (596 in the dry run), `scout` should leave about a quarter (163) and `wide` less
(30 in the dry run, with a client faster than Modal's and an engine without a limit).

The dry run, turn by turn (seconds after the stream, 45 ms a step):

| session | turn | sub-calls sent (errors returned) | cause in `stream` | `nospec` | `stream` | `scout` | `wide` | `wide-threads` | `nospec-wide` |
|---|---|---|---|---|---|---|---|---|---|
| `trec132k-17000222` | 7 | 319 (0) | serial launches | 456.0 | 456.2 | 32.1 | 7.1 | 6.9 | 456.3 |
| `trec132k-17000241` | 12 | 3,182 (0) | burst over the cap | 65.7 | 62.4 | 62.3 | 7.1 | 6.8 | 11.9 |
| `trec132k-17000222` | 4 | 1,600 (1,582) | serial launches | 48.1 | 23.1 | 23.1 | 10.9 | 3.8 | 50.5 |
| `pairs32k-15` | 4 | 400 (387) | not speculated | 11.1 | 11.8 | 3.8 | 0.2 | 0.0 | 14.9 |
| `trec132k-17000222.w8k-c8` | 4 | 1,002 (0) | burst over the cap | 14.5 | 11.7 | 11.7 | 0.0 | 0.0 | 3.1 |
| `trec132k-17000222.w8k-c8` | 6 | 1,007 (1) | burst over the cap | 14.3 | 11.4 | 11.4 | 0.0 | 0.0 | 2.8 |
| `trec132k-17000222.w8k-c8` | 8 | 1,008 (1) | burst over the cap | 12.9 | 10.7 | 10.6 | 0.0 | 0.0 | 2.6 |
| `pairs32k-1` | 4 | 400 (387) | burst over the cap | 10.6 | 5.4 | 5.4 | 2.2 | 1.1 | 10.8 |

- `pairs32k-15` turn 4 is "not speculated" because the shipped shadow thread dies there
  (`shadow.py:314`, the list-argument peek). The fork has the fix.
- Which turns the real run classes as which cause can differ from this table: the cause
  is read from event timing.

### Not predicted

- What 256, 512 and 1,024 concurrent short calls do to a root stream. The warm-up
  measures it (`warmup_wave`). The campaign measured up to 128.
- How the engine's step grows above 128 sequences. The dry run assumes it does not.
- `wide` on bursts, as a number. The T4's client reached 130 calls a second. At that
  rate 3,182 calls take 24 s, against about 58 s at 16 in flight. Bursts of several
  sessions overlap in turn 4 and share one Python process.

## What would change the plan

- The live run is worth running if the better of `scout` and `wide`
  has a summed session time at most 0.85 of `stream`'s in exact units, and its root
  streams are at most 10% longer than `stream`'s. That arm is then the fourth arm.
- If `scout` fails P5, the scout is wrong somewhere the unit tests do not reach: stop
  and find out before any live run.
- If `wide` fails P6 or P8, the window of 128 is too wide for this client or engine:
  the live run uses `scout`, and the window becomes the next stage's question, with data.

## What the replay cannot say

- Quality. Answers are replayed, so scores are the recorded ones by construction.
- A live run's trajectory. A faster turn changes nothing here. Live, the root writes
  different code after different timings only if something times out.
- Other models and workloads. 8 sessions of one model on OOLONG.
