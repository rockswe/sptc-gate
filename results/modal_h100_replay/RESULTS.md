# The replay on a Modal H100, November 10, 2026 (measured)

Eight sessions recorded in the RLM campaign were run again on one vLLM
engine in six arms: the same code, the same sub-calls and the same answers in every arm,
so that only the speculation policy differs. What the fork should recover was written
down before the run (`cloud/PREREG_REPLAY.md`, sha256 `a2c0f9db…` in `campaign.jsonl`). That hash
is of the file at run time; the published copy has since had planning notes and costs
removed, so it hashes differently.
Sections 1 to 8 are that run, `20261110-042602-replay`. Section 9 is its follow-up.

**The question:** how much of the time spec-ptc as shipped still spends after the root's
stream does the fork remove?

**Read with `../modal_h100_record/RESULTS.md`** (added later on November 10): the same
measurement on sessions recorded with rlms fixed. There the scout ran at 1.003 of the
shipped client. The gain below is real on these 8 sessions, and most of it answers the
bug named under "What it changes".

## In short

- The scout removes the serial launches. A loop of 319 single calls that uses each
  result took 327 s without speculation, 333 s with spec-ptc as shipped, and 23 s with the
  scout at the same window of 16. Over the turns the shipped client launched serially,
  the scout recovered 87% of its seconds after the stream (predicted: at least 75%).
- Session time: 0.72 of the shipped client's with the scout, 0.65 with a window of 128
  as well. Summed over the 8 sessions: 1,237 s without speculation, 1,180 s as shipped,
  851 s with the scout, 761 s wide. The shipped client is at 0.95 of no speculation.
- A wider window recovers the cap seconds (63%), and the scout alone none, both as
  predicted. Width does it without speculation too: rlms' own batches at 128 recover 60%.
- The root pays nothing. Its median token gap is 35 to 38 ms in every arm, and its
  streams are within 1.4% of the shipped client's. A wave of 1,024 concurrent short calls
  stretched one token gap of a stream to 99 ms.
- 8 of 11 predictions held. Three did not:
  - `wide` launched 1,042 calls twice in one of its two units and evicted them (P1, P2):
    a defect in the fork's handoff from scout to shadow that only shows in a busy
    process. It is fixed, with tests that fail on the code of this run (section 8).
  - `nospec`'s two units differ by 5.2%, not under 5% (P9): the first unit of the launch
    had 25 s of root stalls. The other arms repeat within 1.0 to 1.9%.
- A follow-up run checked the fixed fork on another launch (section 9): no call sent
  twice in 4 fork units, each of which met the condition that had caused it. 6 of its 8
  predictions held; the two that did not are the cold first unit again, which its design
  should have kept away from the arm under test.
- Launching a batch as a batch changes little in total, and the plan's reason for it
  was wrong: rlms runs a batch 16 wide too. On the engine `wide` and `wide-threads` ended
  within 1.3% of each other. Per turn they differ in both directions (section 4).
- At 128 the limit is the Python client, not the engine. Launching 3,182 speculative
  calls took the scout 6.6 s in a busy process, and on that turn speculation at 128 was
  slower than no speculation at 128 (16 to 23 s against 15 s).
- The replay itself holds: all 10 units exact, and the replayed `nospec` units
  reproduce the recorded turns (325 and 330 s for the loop recorded at 343 s).
- GPU time: 61 H100-minutes for the registered
  run, 29 for the follow-up, two T4 smoke runs and two CPU probes before them.

## Setup

- Engine: one H100 80 GB on Modal, vLLM 0.32.0, `Qwen/Qwen3-30B-A3B-Instruct-2507`,
  the campaign's server flags with `--max-model-len 65536`. One launch for all units; the
  root's median token gap was 35 to 38 ms throughout.
- Corpus: 8 sessions recorded in the campaign's `nospec` arm (77 turns, 9,096
  sub-calls, 2,359 prompts that return a recorded error string). Built and checked by
  `cloud/replay_corpus.py`: each session is run again offline and kept only if every block
  prints what it printed in the recorded run. `PREREG_REPLAY.md` lists the sessions and
  what was left out.
- How a unit replays (`cloud/replay.py`): the root is a real streamed request with the
  message history rlms builds, forced to the recorded number of tokens, and each engine
  token releases the next recorded delta. A sub-call is a real request with the recorded
  prompt and output length and returns the recorded answer. Between them runs the
  campaign's own stack.
- Arms:

  | arm | client | what it does |
  |---|---|---|
  | `nospec` | stock rlms | sub-calls run when the program reaches them |
  | `stream` | spec-ptc at `9b78b7d` | the shipped client, fed by the root's stream |
  | `scout` | the fork | scout pass on; window 16, one thread per prompt, as shipped |
  | `wide` | the fork | scout, window 128, a batch launched as a batch |
  | `wide-threads` | the fork | scout, window 128, one thread per prompt (control) |
  | `nospec-wide` | stock rlms | no speculation, rlms' batches 128 wide (control) |

- Units: the four main arms twice in ABBA order, then one unit of each control. A unit
  is the 8 sessions, 8 at a time, in its own process with its arm's spec-ptc tree.
- Exact: a unit is exact if every session ran the recorded number of turns, sent the
  root the recorded message history in every turn (sha256) and ended with the recorded
  answer. All 10 units were.
- In every arm: rlms' LM handler listens with a backlog of 1,024 (section 8), each
  unit salts its prompts so that no unit finds another's in the prefix cache, no task
  timeout, `PYTHONHASHSEED=0`.
- The fork is the tree committed since as `2555dd1` on `sptc-hints` (Python tree
  sha256 `33387f6a…`, as hashed in `campaign.jsonl`). At launch it was `dbee0c2` plus the
  uncommitted changes listed in `launch.json`. The follow-up ran `ac5d733`
  (`7aa23f07…`). The campaign code of each run is likewise a commit of this repository:
  the files each run hashed before its first unit are the files of that commit.
- Files here: per run `summary.md` and `summary.json` (written by the run, with the
  report code hashed in `campaign.jsonl`), `campaign.jsonl`, `server.json`, `launch.json`,
  and each unit's `replay.json`. Events and trajectories hold OOLONG text and stay out of
  the repository.

## 1. The predictions

| | prediction | dry run | measured | |
|---|---|---|---|---|
| P1 | every unit exact; no unrecorded call, no repeat | all exact | 10 of 10 exact; 1,042 calls sent twice | **did not hold** |
| P2 | nothing evicted | 0 | 1,042 evicted | **did not hold** |
| P3 | the loop of 319 single calls: `stream` at least 0.90 of `nospec` | 1.00 | 1.02 | held |
| P4 | the same turn: `scout` at most 0.15 of `stream` | 0.07 | 0.07 | held |
| P5 | serial launches: `scout` recovers at least 75%, `wide` at least 85% | 88%, 96% | 87%, 96% | held |
| P6 | the cap: `scout` recovers between -15% and +15%, `wide` at least 50% | 0%, 91% | -1%, 63% | held |
| P7 | session time: `stream` 0.93–1.02 of `nospec`; `scout` at most 0.80 of `stream`; `wide` at most 0.75 | 0.98, 0.72, 0.64 | 0.954, 0.721, 0.645 | held |
| P8 | root stream seconds: `scout` within 5% of `stream`, `wide` within 10% | 1.00, 1.02 | 0.987, 0.986 | held |
| P9 | an arm's two units differ by less than 5% in session time | - | 5.2% at most | **did not hold** |
| P10 | controls: `wide-threads` within 25% of `wide`; `nospec-wide` recovers at most 10% of the serial-launch seconds and is at least 0.90 of `nospec` | 0.99; -6%; 0.95 | 0.987; -8%; 0.920 | held |
| live run | worth it if the better fork arm is at most 0.85 of `stream` in session time and its root streams at most 10% longer | - | `wide`: 0.645, 0.986 | held |

- P1 and P2 are one event, in `wide_c8_r1` (section 8). The other nine units sent no
  call twice and evicted nothing.
- P6's dry run was far too optimistic (91% against 63%), as the pre-registration said
  it would be: the local client outruns Modal's, and the fake engine has no limit.
- P9: `nospec` 5.2%, `wide` 1.9%, `scout` 1.1%, `stream` 1.0% (section 6).

## 2. Sessions

Sum of the 8 sessions' wall times, mean of an arm's units. After-stream: from the end of
each root stream until that turn's code has run.

| arm | units | session time s | root streams s | after-stream s | of `nospec` | of `stream` |
|---|---|---|---|---|---|---|
| `nospec` | 2 | 1,236.9 | 735.2 | 496.0 | - | 1.049 |
| `stream` | 2 | 1,179.5 | 708.6 | 465.8 | 0.954 | - |
| `scout` | 2 | 850.9 | 699.0 | 147.0 | 0.688 | 0.721 |
| `wide` | 2 | 760.8 | 698.5 | 56.9 | 0.615 | 0.645 |
| `wide-threads` | 1 | 750.8 | 677.1 | 68.3 | 0.607 | 0.636 |
| `nospec-wide` | 1 | 1,137.9 | 690.7 | 441.0 | 0.920 | 0.965 |

- Of the 419 s `wide` saves against `stream`, the scout saves 329 at the shipped
  window. The window adds 90.
- What is left is the root. In `wide` the root's streams are 92% of session time.
  Within a turn there is nothing more to take on this corpus.
- `nospec`'s first unit was the launch's first and had 72 s more root stream than its
  second (section 6). Against the second unit alone the ratios are 0.978 (`stream`),
  0.706 (`scout`) and 0.631 (`wide`). Ratios against `stream` are not affected.

By session, wall seconds (after-stream seconds):

| session | `nospec` | `stream` | `scout` | `wide` | `wide-threads` | `nospec-wide` |
|---|---|---|---|---|---|---|
| `trec132k-17000222` | 520.3 (374.3) | 504.9 (359.1) | 192.0 (47.2) | 160.8 (17.8) | 165.8 (28.1) | 532.1 (389.8) |
| `trec132k-17000222.w8k-c8` | 138.0 (41.4) | 126.3 (33.5) | 125.1 (34.3) | 101.6 (9.5) | 100.8 (11.4) | 105.3 (14.0) |
| `trec132k-17000241` | 110.0 (58.0) | 104.0 (55.8) | 103.0 (55.9) | 70.1 (21.0) | 61.9 (15.6) | 62.2 (14.6) |
| `pairs32k-15` | 100.9 (10.4) | 97.8 (11.8) | 89.7 (4.3) | 89.3 (4.4) | 91.5 (9.4) | 95.6 (12.4) |
| `pairs32k-1` | 79.8 (11.5) | 70.6 (5.1) | 69.3 (5.2) | 68.5 (4.1) | 67.0 (3.5) | 74.3 (9.8) |
| `trec132k-17000232` | 120.2 (0.0) | 115.5 (0.1) | 114.7 (0.1) | 111.0 (0.1) | 109.2 (0.1) | 111.4 (0.0) |
| `trec132k-17000232.w8k-c1` | 87.1 (0.3) | 83.5 (0.4) | 81.8 (0.0) | 82.4 (0.0) | 79.9 (0.1) | 81.7 (0.3) |
| `pairs32k-20` | 80.7 (0.0) | 76.9 (0.0) | 75.4 (0.0) | 77.0 (0.0) | 74.7 (0.0) | 75.3 (0.0) |

- One session carries the scout's gain: 505 s to 192 s. Per session the geometric
  mean against `stream` is 0.87 for `scout` (bootstrap 95% CI 0.68–0.99) and 0.79 for
  `wide` (0.60–0.95).
- Three sessions make no sub-call worth the name and do not move.

## 3. The turns

Turns in which `stream` spent at least 1 s after its stream, by why (its own events:
`analyze.turn_cause`). Seconds after the stream in the same turns, and the share of
`stream`'s seconds that is gone.

| cause in `stream` | turns | `nospec` | `stream` | `scout` | `wide` | `wide-threads` | `nospec-wide` | `scout` recovers | `wide` recovers |
|---|---|---|---|---|---|---|---|---|---|
| serial launches | 2 | 372.2 | 357.1 | 45.4 | 15.9 | 26.4 | 387.4 | 87% | 96% |
| burst over the cap | 5 | 108.9 | 94.2 | 95.1 | 34.6 | 30.5 | 37.8 | -1% | 63% |
| not speculated | 1 | 10.4 | 11.8 | 4.3 | 4.3 | 9.4 | 12.4 | 64% | 63% |
| still running at stream end | 1 | 1.1 | 1.1 | 1.0 | 1.0 | 0.9 | 1.1 | 11% | 9% |

| session | turn | sub-calls sent (errors returned) | cause in `stream` | `nospec` | `stream` | `scout` | `wide` | `wide-threads` | `nospec-wide` |
|---|---|---|---|---|---|---|---|---|---|
| `trec132k-17000222` | 7 | 319 (0) | serial launches | 327.1 | 333.3 | 23.3 | 4.0 | 3.9 | 343.2 |
| `trec132k-17000241` | 12 | 3,182 (0) | burst over the cap | 58.0 | 55.8 | 55.9 | 21.0 | 15.6 | 14.6 |
| `trec132k-17000222` | 4 | 1,600 (1,582) | serial launches | 45.2 | 23.8 | 22.1 | 11.9 | 22.5 | 44.2 |
| `pairs32k-15` | 4 | 400 (387) | not speculated | 10.4 | 11.8 | 4.3 | 4.3 | 9.4 | 12.4 |
| `trec132k-17000222.w8k-c8` | 4 | 1,002 (0) | burst over the cap | 13.7 | 11.4 | 11.5 | 7.0 | 8.1 | 7.4 |
| `trec132k-17000222.w8k-c8` | 6 | 1,007 (1) | burst over the cap | 13.1 | 11.2 | 11.4 | 1.3 | 1.7 | 3.3 |
| `trec132k-17000222.w8k-c8` | 8 | 1,008 (1) | burst over the cap | 12.6 | 10.7 | 11.2 | 1.1 | 1.5 | 2.6 |
| `pairs32k-1` | 4 | 400 (387) | burst over the cap | 11.5 | 5.1 | 5.2 | 4.1 | 3.5 | 9.8 |

- The loop (turn 7). The shipped client claims every call and gains nothing: its
  shadow waits at each result, so the calls go out one after another. The scout launches
  all 319 before the first answers. At 16 in flight they take 23 s; at 128, 4 s.
- The loop of 160 batches of 20 (turn 4). The shipped client halves it (45 s to 24 s):
  a batch's 20 calls go out together and before the stream ends. Half of the prompts
  return a recorded error at once, so the scout at 16 finds little more.
- One batch of 3,182 (turn 12). At 16 in flight nothing helps: 56 to 58 s in `nospec`,
  `stream` and `scout`. A head start of 2.7 s is all speculation has there.
- `pairs32k-15` turn 4 is "not speculated" because the shipped shadow thread dies
  there (`shadow.py:314`, the list-argument peek), in both units. The fork has the fix.
- The dry run named the same turns with the same causes.

## 4. The window, and a batch as a batch

**The window.** `scout` and `wide-threads` differ only in the window:

| | 16 in flight | 128 in flight |
|---|---|---|
| 319 single calls of about 30 tokens | 23.3 s | 3.9 s |
| one batch of 3,182 calls of about 7 tokens | 55.9 s | 15.6 s |
| three batches of about 1,000 | 34.1 s | 11.3 s |
| sub-call latency, median / 90th percentile | 222 / 347 ms | 282 / 454 ms |

- Eight times the window gave 3 to 6 times the speed. A call takes a quarter longer at
  the median.
- Width needs no speculation to pay on a batch. `nospec-wide` ran the batch of 3,182
  in 14.6 s, faster than both speculative wide arms (15.6 s, and 18.9 and 23.1 s).
  rlms' 16 is a constant in `LMHandler`; `RLM()` cannot set it.
- It does nothing for a loop. `nospec-wide` left the 319-call loop at 343 s and the
  loop of batches at 44 s.

**A batch launched as a batch.** `wide` and `wide-threads` differ only in that:

| | `wide` (as a batch) | `wide-threads` (a thread per prompt) |
|---|---|---|
| summed session time | 760.8 s | 750.8 s |
| 160 batches of 20, half of them errors | 11.9 s | 22.5 s |
| one batch of 3,182 | 18.9 s, and 23.1 s in the unit with the defect | 15.6 s |
| sub-call latency, median / 90th percentile | 352 / 1,018 ms | 282 / 454 ms |

- Many small batches: better. One request to rlms' handler per batch, where a thread
  per prompt makes 3,182 round trips for 1,600 real calls.
- One huge batch: worse. The batch is sent once all its speculations exist, and
  creating 3,182 took the scout seconds (section 8). A thread per prompt sends each call
  as it is created.
- The reason for building it was wrong. The premise was that the model's own batch "sends its
  whole list at once" and spec-ptc throttles it to 16. rlms throttles it to 16 itself
  (`../modal_h100_rlm/RESULTS.md`, Corrections 1).

## 5. The root and the engine

| unit | root gap median / 99th ms | stall s | first token median / max s | sub-call median / 90th ms | running mean / max | KV peak |
|---|---|---|---|---|---|---|
| `nospec_c8_r1` | 35.6 / 44.7 | 25.5 | 0.11 / 8.44 | 231 / 346 | 4.5 / 48 | 0.19 |
| `stream_c8_r1` | 36.7 / 47.2 | 0.8 | 0.11 / 0.33 | 230 / 355 | 4.7 / 49 | 0.23 |
| `scout_c8_r1` | 36.5 / 48.7 | 1.2 | 0.11 / 0.33 | 222 / 347 | 12.6 / 50 | 0.23 |
| `wide_c8_r1` | 35.0 / 54.8 | 19.8 | 0.11 / 0.32 | 359 / 1,004 | 16.7 / 131 | 0.24 |
| `wide_c8_r2` | 35.6 / 54.5 | 0.0 | 0.11 / 0.31 | 344 / 1,031 | 15.2 / 130 | 0.24 |
| `scout_c8_r2` | 36.0 / 48.2 | 0.0 | 0.11 / 0.32 | 222 / 346 | 12.3 / 50 | 0.23 |
| `stream_c8_r2` | 37.8 / 45.8 | 0.0 | 0.11 / 0.33 | 224 / 345 | 4.6 / 50 | 0.23 |
| `nospec_c8_r2` | 35.4 / 57.5 | 0.0 | 0.11 / 0.35 | 238 / 361 | 4.4 / 48 | 0.19 |
| `wide-threads_c8_r1` | 34.6 / 49.3 | 0.0 | 0.11 / 0.32 | 282 / 454 | 14.6 / 128 | 0.23 |
| `nospec-wide_c8_r1` | 35.9 / 50.8 | 0.0 | 0.11 / 0.29 | 351 / 994 | 4.5 / 131 | 0.19 |

- No arm slows the root's tokens. The median gap is 34.6 to 37.8 ms, with no order
  between the arms. The 99th percentile rises from 45–49 ms to 55 ms at 128 in flight.
- Stalls are two events, not a pattern: the launch's first unit (section 6), and
  `wide_c8_r1` during the turn with the duplicated launches (one gap of 2.9 s).
- Nothing queued, nothing preempted. At most 3 requests were ever seen waiting in the
  engine, and the KV cache peaked at 24%.

The warm-up's second pass: one 48-token stream next to n concurrent short calls.

| n | 1–16 | 32–128 | 256 | 512 | 1,024 | 4 long | 16 long |
|---|---|---|---|---|---|---|---|
| longest token gap of the stream, ms | 36–40 | 50–54 | 58 | 59 | 99 | 106 | 144 |
| wall time of the wave, s | 1.6 | 1.6–1.7 | 1.8 | 2.0 | 3.2 | 1.7 | 2.2 |

The campaign had measured up to 128. This engine takes 1,024 short calls at once for one
token gap of 99 ms. (Long: prompts of about 3,400 tokens.)

## 6. How repeatable a replay is

An arm's unit 1 against its unit 2:

| arm | session time, ratio | per-session spread (factor) | after-stream s | root streams s |
|---|---|---|---|---|
| `nospec` | 1.052 | 1.088 | 491.2 / 500.8 | 771.2 / 699.2 |
| `stream` | 0.990 | 1.012 | 464.6 / 467.0 | 704.3 / 712.9 |
| `scout` | 1.012 | 1.022 | 147.6 / 146.5 | 703.3 / 694.8 |
| `wide` | 1.019 | 1.029 | 59.6 / 54.2 | 702.9 / 694.2 |

- Seconds after the streams repeat within 2% where nothing went wrong (`wide`'s unit 1
  has the duplicated launches).
- The first unit of the launch paid for a cold engine: 25 s of root stalls, one first
  token after 8.4 s, 72 s more root stream than the same arm's second unit. The warm-up
  sends short prompts and 3,400-token ones; the roots' histories reach 18,000 tokens.
  A warm-up should send one such prompt, or the first unit should be thrown away. The
  follow-up's first unit shows the same (section 9).
- Live, the same arm's two repeats of a task differed by a factor of 1.9. Here a
  session's two replays differ by 1 to 3% (9% in `nospec`, for the reason above).

## 7. The replay against the recording

The replayed `nospec` units against what was recorded (same server flags; recorded at 33
ms a token, replayed at 35.5 ms):

| session | turn | recorded | recorded s | replay, unit 1 | unit 2 |
|---|---|---|---|---|---|
| `trec132k-17000222` | 7 | 230918-main | 342.9 | 324.5 | 329.6 |
| `trec132k-17000241` | 12 | 230918-main | 57.5 | 56.1 | 59.9 |
| `trec132k-17000222` | 4 | 230918-main | 51.7 | 43.8 | 46.6 |
| `pairs32k-1` | 4 | 230918-main | 20.0 | 13.4 | 9.6 |
| `pairs32k-15` | 4 | 230918-main | 14.4 | 10.6 | 10.1 |
| `trec132k-17000222.w8k-c8` | 4 | 222742-main (53 ms a token) | 22.3 | 12.8 | 14.7 |
| `trec132k-17000222.w8k-c8` | 8 | 222742-main | 19.5 | 12.5 | 12.7 |
| `trec132k-17000222.w8k-c8` | 6 | 222742-main | 17.8 | 12.9 | 13.3 |

- The two largest turns come back within 5%. Over the six sessions of the rerun:
  489 s recorded after the streams, 451 and 458 s replayed.
- Small batches replay faster than recorded (0.5 to 0.9). The recorded unit had two
  more sessions on the engine, one of them with 36,000-token sub-calls.

## 8. What the bench found, before and during the run

**In the fork.**

| found | what | state |
|---|---|---|
| before the run, in a local dry run | After a statement that raised, the scout went on with the old value of the variable it could not set, and launched a call the program never makes: a 36,000-token prompt of the turn before | fixed before the run: names such a statement would have set are unknown to the scout, and a real error ends the scout for its block. 4 tests |
| in the run, `wide_c8_r1` | The shadow waited 3 s for the scout, then ran the statement itself. In a busy process the scout needed 6.6 s to launch a batch of 3,182 (456 launches a second). Both launched the rest: 1,042 calls sent twice, the turn's dispatch cap used up, 128 calls left to the real run | fixed after the run: the shadow lets the scout finish its launches, launching is not counted as a statement's computing, and an interrupted batch launch still runs what it announced. 4 tests; a dry run with launches slowed to 2 ms reproduces it (1,318 twice) and shows the fix (none) |

**In spec-ptc as shipped** (`9b78b7d`), seen again or new:

| where | what |
|---|---|
| `src/engine/shadow.py:314` | The shadow thread dies on a peek whose call takes a list: `pairs32k-15` turn 4, in every `stream` unit. 787 calls not speculated each time. Fixed in the fork |
| `src/engine/shadow.py:273`, the runaway guard | It budgets a statement's own computing (2 s) but counts launching. In `stream_c8_r2` it cut a statement that launches 3,182 calls after 2,760: 422 calls not speculated, in one unit of three. Fixed in the fork after the registered run |
| `src/engine/shadow.py:52` | A module imported in an earlier turn is opaque to the shadow: 3 shadow stops per unit at the first `re.`. Not fixed: in these sessions it cost no call |

**In rlms 0.1.3:** the batch that loses prompts, the width of 16 and the listen backlog
of 5 are in `../modal_h100_rlm/RESULTS.md` (Corrections, and section 10).

- The backlog was measured on Modal before the run (`replay_app.py::probe_handler`, 2,000
  single calls of 150 ms through the handler):

  | backlog | threads | calls a second or more late | wall s (ideal) |
  |---|---|---|---|
  | 5 (rlms) | 16 | 1 | 19.3 (18.8) |
  | 5 (rlms) | 128 | 76 | 4.5 (2.3) |
  | 1,024 | 16 | 0 | 19.2 (18.8) |
  | 1,024 | 128 | 0 | 3.3 (2.3) |

  On macOS the same overflow times out, and rlms returns `Error: Request failed: ...` as
  the call's answer: 14 answers in a dry run of `wide-threads`. The replay sets 1,024 in
  every arm.

**In the replay's own client.** The first T4 smoke run had `wide` and `nospec-wide` three
times slower than `wide-threads`. The replay client pooled 256 keep-alive connections,
where rlms' own pools 100, and httpx's async pool falls from 130 to 50 calls a second at
128 in flight with the larger pool. Fixed before the run: the client is built as rlms
builds its own. The second smoke run confirmed it.

## 9. The follow-up run

`20261110-053243-replay`: the fork after the second fix, on another H100 launch. What it
should show was fixed before it ran (`cloud/PREREG_REPLAY_ADDENDUM.md`, sha256
`b33ff2db…`). Units in this order: `wide`, `wide`, `stream`, `scout`, `wide-threads`. This
host was slower: the root's median token gap was 44 to 48 ms.

| | prediction | registered run | measured | |
|---|---|---|---|---|
| A1 | every unit exact; in the fork's arms no call launched twice, none evicted, none left to the real run | 1,042 twice, 128 left | 5 of 5 exact; 0, 0, 0 | held |
| A2 | the batch of 3,182: `wide` at most 0.45 of `stream` | 0.38 | 0.32 | held |
| A3 | the cap: `wide` recovers at least 50% | 63% | 64% | held |
| A4 | serial launches: `wide` recovers at least 85% | 96% | 95% | held |
| A5 | session time: `wide` at most 0.75 of `stream`; root stream seconds within 10% | 0.645, 0.986 | 0.709, 1.110 | **did not hold** |
| A6 | `wide-threads` within 25% of `wide` in session time | 0.987 | 0.918 | held |
| A7 | `wide`'s two units differ by less than 5% in session time | 1.9% | 15.5% | **did not hold** |
| A8 | the runaway guard cuts no shadow statement in the fork's arms | 1 per `scout` unit | 0 | held |

- The fix was put to the test on the engine, in every fork unit. The scout needed more
  than the old 3 s to launch the batch of 3,182 each time: 3.1 s in `scout`, 7.0 and 7.5 s
  in `wide`, 21.7 s in `wide-threads`. Each unit launched 11,455 calls, all by the scout,
  all adopted, all claimed.
- A5 and A7 failed for one reason, and it is a mistake in the addendum's design. The
  launch's first unit pays for a cold engine (section 6), and the addendum put the arm
  under test first: `wide`'s first unit had 72 s of root stalls and 1,038 s of root
  streams, its second 900 s. The second unit alone is at 0.658 of `stream` in session
  time and 1.031 in root streams.
- `scout` is where it was: 0.706 of `stream` in session time (0.721 before), 88% of
  the serial-launch seconds (87%).

| arm | units | session time s | root streams s | after-stream s | of `stream` |
|---|---|---|---|---|---|
| `stream` | 1 | 1,476.1 | 873.2 | 596.7 | - |
| `scout` | 1 | 1,042.7 | 857.0 | 179.1 | 0.706 |
| `wide` | 2 | 1,047.0 (1,122.4 and 971.6) | 969.3 (1,038.3 and 900.4) | 70.7 | 0.709 |
| `wide-threads` | 1 | 961.0 | 863.4 | 90.8 | 0.651 |

How fast the batch of 3,182 was launched, by arm (both runs, 7 units of the fork):

| arm | who launches | launches a second | seconds for the batch |
|---|---|---|---|
| `stream` (16 in flight) | the shadow | 2,115 to 3,376 | 0.9 to 1.5 |
| `scout` (16 in flight) | the scout | 1,016 to 1,584 | 2.0 to 3.1 |
| `wide` (128, as a batch) | the scout | 427 to 489 | 6.5 to 7.5 |
| `wide-threads` (128, a thread per prompt) | the scout | 147 to 183 | 17.4 to 21.7 |

- The launching thread shares one Python process with the calls already launched. With a
  thread per prompt they start work at once, and the launcher slows to 150 a second.
- In the registered run the launch took longer than the old 3 s in all three units at 128.
  It went wrong in one: whether it does depends on when the shadow reaches the statement.

## What it changes

- The scout clears the bar that was set for a live run (0.72 of `stream`; the bar
  was 0.85), and `wide` is at 0.65. Whether a live run of 8 tasks can show a ratio of 0.72
  under a noise of 1.9 per task is another question.
- How wide is limited by the client. One Python process holds all 8 sessions. At 128
  in flight per session it launches about 450 calls a second and sub-calls take 1.3 to
  1.6 times longer; the engine was at a quarter of its KV cache and took 1,024 at once.
  A window that follows the load has to watch the client as well as the root.
- The largest gain here answers a bug. The 319-call loop exists because rlms' batches
  failed and the model fell back to single calls. With rlms fixed the model would have
  batched, and on a loop of batches the shipped client already halves the time (45 s to
  24 s) and the scout at the same window adds little (22 s). The `stream` arm's own
  recordings do have serial loops unprovoked (160 calls, twice), but they cannot be
  replayed.

## Limits

- 8 sessions, one model, one workload, two launches. One session carries most of the
  gain.
- A corpus recorded without speculation. The turns of RESULTS.md section 3 came from
  the `stream` arm and could not be replayed: a claimed call left no record of its answer.
- 2,359 prompts return a recorded error at once. They are rlms' lost batch prompts.
  They cost no engine time in any arm, so a loop of batches is about half as heavy here
  as it would be with rlms fixed.
- Quality is not measured: answers are replayed.
- One session with long sub-calls is left out (`trec132k-17000237`: 566 s after its
  streams when recorded, one call per turn). No arm can touch those seconds within a
  turn; they are the case for bets across turns.
- The dry run's engine batches for free. It predicted single-call turns well and
  bursts badly, as stated beforehand.
- An eager server, as in the campaign: a decode step is mostly Python on the host.
