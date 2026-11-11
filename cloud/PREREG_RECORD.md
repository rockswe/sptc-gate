# What the recording should show (fixed before the run)

Written 2026-11-10, before the recording. `rlm_record.py` records this file's sha256 in
`campaign.jsonl` (`begin`, under `files`) before the first unit. Never edit it after the
run. What the replay of the recording should show, in numbers, is fixed in an addendum
after the recording and before the replay.

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)).*

## The question

The replay took session time to 0.72 of the shipped client's with the scout
(`../results/modal_h100_replay/RESULTS.md`). One session carries most of that, and its
loop of 319 single calls is the model's reaction to a bug: rlms 0.1.3 loses prompts of
every batch after a session's first, the root saw the error strings and gave up on
batches.

**How often does the model write serial loops when rlms is not failing under it, and what
does the scout recover on those sessions?**

This takes the place of a live run with the fork as a fourth arm. A
live run of 8 tasks cannot show a ratio of 0.72 under a noise of 1.9 per task. A recording
that is then replayed can.

## What is run

1. A recording. The campaign's `nospec` arm with rlms' batch path fixed: 8 tasks, 8 at
   a time, twice. 16 sessions.
2. A census of what the 16 sessions wrote, from their trajectories.
3. A replay of the sessions that can be replayed, on another launch: the shipped
   client against the fork.

## The recording: what is fixed

- Engine: one H100 launch on Modal, vLLM 0.32.0, `Qwen/Qwen3-30B-A3B-Instruct-2507`,
  the campaign's server flags with `--max-model-len 65536` (as the rerun of November 9).
- Tasks, client, runner: the campaign's (`load_tasks(4, 4, seed=7)`, spec-ptc at
  `9b78b7d`, rlms 0.1.3, its 900 s task timeout). Roots stream, REPLs are thread-safe, a
  root reply is cut after 3,000 deltas, two warm-up passes: all as in the rerun.
- Arm: `nospec` only. The speculative arms leave no record of a claimed call's answer,
  so their sessions cannot be replayed.
- Three things are new (`rlm_record.py`, `batch_fix.py`):
  1. rlms' batch path is fixed. A client's async requests run on one event loop of
     its own, so a kept connection never meets a closed loop. The request, and rlms' width
     of 16 prompts in flight, are unchanged.
  2. A probe before the first unit: four batches of 20 through rlms' own path against
     the engine, the last one after 6 s without a request, with stock rlms and then with
     the fix. If a prompt is lost with the fix on, the run stops there.
  3. A deadline for a task's sub-calls: 1,200 s after the task starts they are
     refused, and the task counts as failed. rlms checks its 900 s timeout between turns
     only, and one block held a unit for 1,828 s on November 9. A session that long could
     not be replayed within what is left of the budget in any case.
- Budget: `--max-minutes 50`, hard timeout 58 minutes. A unit lasts about 22 minutes
  at most.

## What I have seen when writing this

- The 24 task runs of November 9 with the 65,536-token window (`../results/modal_h100_rlm`):
  8 in `nospec`, 16 in `stream`. In the `stream` arm a speculated batch goes out as single
  calls, which the bug does not touch: 13 of its 16 task runs never saw an error string.
  They are the nearest thing so far to unprovoked code.
  - Loops of single calls: 2 of those 16 task runs (160 calls, twice in one; 40, then
    787 in the other). Both ran into the 900 s timeout.
  - One of the two loops tests each result (`if 'human being' in classification:`).
    The other only splits and stores it.
  - Loops of batches (39 to 159 batches of 20) and single large batches are the common
    shapes. Half the sessions make few sub-calls or none.
- The probe against a fake server (`tests/test_batch_fix.py`): stock rlms loses 36 of 80
  prompts, the fixed path none.
- The probe on a real vLLM, in a smoke run on a T4 with a 1.7B model
  (`20261110-172345-smoke`): stock rlms lost 21 of 80 (16 of the second batch, 4 of the
  third, 1 of the fourth, which came after 6 s without a request), the fixed path none. Its
  one unit made no batched call: a model that small writes none.
- Nothing from a recording with the fix on the 30B model.

## Definitions

- A single call: a sub-call the trajectory records alone. **A batch:** consecutive
  recorded calls with one identical time (one `llm_query_batched`).
- A loop of single calls: a turn that makes at least 20 single calls. **A loop of
  batches:** a turn that makes at least 5 batches.
- A session is replayable if it finished with an answer, or the 900 s timeout stopped
  it at a turn boundary (it is then replayed up to that boundary), and it reproduces
  offline: every block prints what it printed, every turn's message history has the
  recorded sha256. A session the deadline stopped, one with a cut root reply, and one that
  failed for another reason are not replayable. They still count in the census.
- Session time in a replay: the time an arm takes for the session's recorded turns.

## Predictions for the recording

| | prediction | what it rests on | counts against it |
|---|---|---|---|
| R1 | **The fix holds.** No batched prompt comes back as `Event loop is closed` in 16 sessions | the two probes | any (before: 2,356 of 7,938 in one unit) |
| R2 | **The probe:** stock rlms loses at least 16 of its 80 prompts on this engine; with the fix, none | the two probes | fewer than 16 without the fix: the bug needs something this engine does not do |
| R3 | **Loops of single calls are still written, and not often:** 1 to 5 of the 16 sessions have one | 2 of 16 in `stream` | none: the 319-call loop was the bug's doing and the scout's main case does not occur unprovoked here. 6 or more: it is commoner than the `stream` arm showed |
| R4 | **Loops of batches are common:** at least 5 of the 16 sessions have one | 4 of 8 in `nospec` | fewer than 3 |
| R5 | **At most 4 of the 16 sessions fail** (timeout, deadline, error) | 2 of 16 in `stream`, 1 of 8 in `nospec` | 5 or more |
| R6 | **Of the sessions the timeout or the deadline stops, at least half have a loop of single calls** | both timeouts of the `stream` arm | fewer than half. Not testable if none is stopped |

I give R3 about 7 chances in 8: with 2 of 16 as the rate, no loop in 16 sessions has a
chance of about 1 in 8.

## The replay: what is fixed now

- Engine and settings: as the registered replay (`PREREG_REPLAY.md`): another H100
  launch with the same flags, sessions 8 at a time, rlms' handler with a backlog of 1,024,
  a salt per unit, no task timeout, `PYTHONHASHSEED=0`. Clients: spec-ptc at `9b78b7d`,
  and the fork as the follow-up ran it (`ac5d733`, tree `7aa23f07…`).
- Units, in this order, one each: a `scout` unit that is thrown away (the first unit
  of a launch pays for a cold engine), then `stream`, `scout`, `wide`, `nospec`.
- Sessions: every replayable session, with one exception fixed here. A session in
  which no turn makes more than one sub-call, and which spent at least 120 s after its
  streams when recorded, is left out: nothing within a turn can overlap its calls, and
  every unit would last as long as it does.
- If it does not fit. The dry run (below) gives each unit's length. If the five units
  sum to more than 55 minutes, units are dropped from the end of the order (`nospec`, then
  `wide`). If three units still do not fit, sessions are dropped, the one with the longest
  `stream` time in the dry run first.
- A session left out or dropped counts as not recovered: its recorded wall time is
  added to every arm's sum.
- The number that is reported first: the sum of session times of `scout` over that of
  `stream`, over all replayable sessions, with those left out or dropped added to both.
  The same ratio over the replayed sessions alone is reported next to it.

## Predictions for the replay, fixed now

The addendum will add numbers from a local dry run (the corpus against
`tests/fake_engine.py`, as for the registered replay). These do not wait for it.

| | prediction | what it rests on | counts against it |
|---|---|---|---|
| M1 | Every unit is exact | 15 of 15 units so far | any unit not exact: it does not count |
| M2 | In the fork's arms no call is sent twice and none is evicted: the scout places no bet | the follow-up run | either |
| M3 | **The shipped client leaves a loop of single calls serial:** on each such turn `stream` spends at least 0.90 of `nospec`'s seconds after the stream | P3 of the registered run (1.02) | below 0.90 |
| M4 | **The scout removes it where the loop only stores or prints each result:** on such a turn `scout` spends at most 0.25 of `stream`'s seconds | P4 (0.07) | above 0.25 |
| M5 | **The scout does not remove it where the loop tests each result** (`in`, a comparison, a truth test): it launches no call behind a test on a value it does not have. On such a turn `scout` spends at least 0.85 of `stream`'s seconds | the fork's code (`Unknown`: a test raises `ScoutStop`) | below 0.85: the scout launched calls behind a test |
| M6 | **Loops of batches:** at the shipped window the scout gains little, `scout` at 0.55 to 0.95 of `stream` over those turns. At 128 in flight, `wide` at most 0.45 | a batch of 20 fills 16 slots, then 4: the scout fills all 16 | `scout` below 0.55, or `wide` above 0.45 |
| M7 | **The number reported first is at least 0.78:** less of a gain than the registered 0.72 | below | below 0.78: unprovoked code gives the scout as much as the provoked loop did |

Which kind a loop of single calls is (M4 or M5) is read from its code before the replay
and listed in the addendum.

**Where M7 comes from.** The 0.72 was one loop: 313 of the 329 s the scout saved. From the
`stream` arm I expect a loop of single calls in about one session in eight, and about
half of them to be loops the scout passes. The other shapes give the scout little at 16
in flight. So:

- no session with a loop the scout passes (about 1 chance in 3): about 0.95;
- one such session (about 2 in 5): 0.80 to 0.90, depending on how long its loop is;
- two or more (about 1 in 4): 0.70 to 0.80.

I give M7 about 2 chances in 3.

## What the result changes in the README

The 0.72 stays as the registered run's number. Next to it goes the number reported first
here, with the count of sessions behind it.

- At most 0.80, with at least two sessions each giving a tenth of the saving or more:
  the gain holds on unprovoked code. The limit "that session's loop answers a bug" is
  replaced by this result.
- At most 0.80, with one such session: the README gives the number and says that one
  session carries it, as it says of the registered run.
- Between 0.80 and 0.95: the README says what the scout gives on unprovoked code, and
  that the registered 0.72 was mostly the bug's.
- Above 0.95: on unprovoked OOLONG code the scout as built gains little at the shipped
  window. The README leads the H100 section with that.

If the recording shows loops the scout stops at (M5), I may build a scout that goes past a
test whose arms cannot leave the loop, and replay it as an extra arm. It would be built
after seeing the recording and reported as such. The registered comparison stays `scout`
against `stream`.

## What this cannot say

- 16 sessions. A rate of 2 in 16 has a 95% interval of about 2% to 38%.
- One model, one workload, one sampling temperature (the model's default).
- The timeout shapes the corpus. A session with a long serial loop is the likeliest to
  run into the 900 s timeout or the 1,200 s deadline. One the timeout stops is replayed up
  to that turn. One the deadline stops is only counted.
- Quality. Answers are replayed.
- A live session's later turns. A session the timeout stopped would have gone on under
  a faster client. The replay ends where the recording does.
