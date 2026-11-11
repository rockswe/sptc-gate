# Limits that follow the load, on a T4 with 16 places and on a Modal H100, November 11, 2026 (measured)

spec-ptc holds speculation back with two constants: 16 calls in flight, and 120,000
characters of speculative prompts in flight per session. The replay of November 10 found
both below what an H100 took (`../modal_h100_record/RESULTS.md`): two more numbers set by
hand, for one engine. Here the client sets both from what the engine reports, and the
scout goes on past a test that cannot leave its loop. What the runs should show was
written down before them (`cloud/PREREG_GOVERN.md`, and `cloud/PREREG_GOVERN_ADDENDUM.md`
after a first launch that I stopped).

**The question:** can the client set both limits itself, be as good as the best hand-set
number where the engine has room, and hold back where it has not?

## In short

- The finish rule is met. It was set before anything was built. On the H100, over
  the 10 recorded sessions, the client that sets its own limits took 0.985 of the session
  time of the best hand-set client (the rule: at most 1.02). The roots' streams were 1.4%
  longer than with spec-ptc as shipped (the rule: at most 5%).
- All 21 predictions of the H100 run held, and 12 of the 13 on the small engine. The
  one that did not: on 16 places I had said the governed window would be within 1% of a
  fixed 128 in session time. It was 1.6% slower.
- Against spec-ptc as shipped, on the H100: 0.849 of its session time over the 10
  (the hand-set 128: 0.862), and 0.812 over all 11 sessions (the hand-set 128: 0.900).
  With the scout going on past tests: 0.820 and 0.791.
- It ties the hand-set number. It does not beat it. One unit per arm, and a replay
  repeats within 1 to 2%. The session with the largest loop is 27 s shorter; the other
  nine together are 0.6% longer.
- What it adds is that nobody set a number for either engine. On 16 places the same
  client closed its windows (189 cuts, none above 38). The root's first token came after
  1.8 s at the 90th percentile, where a fixed 128 made it 9.4 s.
- Long prompts. The KV pool ran the long turn in 354 s, where spec-ptc's character
  budget takes 537 s. A control with no budget at all took 184 s: the engine's KV cache
  went to 96% and nothing was preempted. Over all 11 sessions that control was the
  fastest client (0.752). The pool's caution cost more than it saved here.
- The scout past a test. The loop that tests each result went from 58 s to 14 s after
  its stream. No call was launched that the program did not make.
- Three things the limits do not see, each measured: a client that is itself the
  limit (two windows at 256 at once got 170 to 180 short calls back a second, where one
  window gets about 210), the prefill of long prompts in front of a root's turn (one turn
  waited 2.7 s), and a queue behind one long prompt (the governor reads it as a standing
  queue).
- A first launch was stopped after 16 minutes. My budget was wrong, and the
  thrown-away unit showed a defect in the governor. It was fixed (patch 6) before any
  measured unit of a governed arm.

## Setup

**What was built** (the client: `integrations/spec-ptc-fork/`, patches 5 and 6, off unless
asked for; the bench: `cloud/README.md`, "Limits that follow the load").

- A governor for the window. A session's window (speculative calls in flight) starts
  at spec-ptc's 16 and moves between 1 and 256, one step per sample of the engine's
  `/metrics`, four a second. Up while calls wait for a place and nothing says stop. Cut
  on a standing queue, a preemption or a KV cache above 97%. Held on any request waiting,
  a KV cache above 93%, tokens at twice their quiet time, or an engine that is not
  stepping.
- A KV pool for long prompts, one for all sessions of the process, in place of the
  character budget: a call is admitted if it fits into 88% of the engine's KV cache less
  what everything else holds.
- Batches in chunks of at most 32 prompts, so that the window bounds a batch of any
  size.
- The scout goes on past a test that cannot leave its loop.

**Arms** (`cloud/replay.py`): `stream` is spec-ptc as shipped at `9b78b7d`. `wide` is
November's best hand-set client, unchanged: the scout, 128 calls in flight, a batch
launched as a batch. `auto` is `wide` with the window governed, the KV pool, and chunks.
`auto-past` is `auto` with the scout going on past such tests. `wide-open` is a control:
`wide` with the character budget lifted and nothing following the load.

**Runs.** Every unit replays recorded sessions of the corpus of November 10
(`../modal_h100_record/corpus/`), 8 at a time; one unit per arm after a unit that is
thrown away.

| launch | engine | sessions | units, in order | time | |
|---|---|---|---|---|---|
| `stopped/20261111-083951-small` | T4, 16 places | 8 (4 in the thrown-away unit) | `auto` thrown away, `stream`; stopped in `wide` | 16 min | stopped by me; the client at patch 5 |
| `20261111-090725-small` (run 1) | T4, 16 places | 8 (4 in the thrown-away unit) | `auto` thrown away, `stream`, `wide`, `auto` | 31 min | 12 of 13 predictions held |
| `20261111-091523-replay` (run 2) | H100 | 11 (6 in the thrown-away unit) | `auto-past` thrown away, `stream`, `wide`, `auto`, `auto-past`, `wide-open` | 49 min | 21 of 21 predictions held |

- Integrity. The hashes are of the files as they were at run time. The published
  pre-registration files and campaign scripts have since had planning notes, schedule
  notes and costs removed, so they hash differently.
  Each run wrote the sha256 of `PREREG_GOVERN.md` (`8d19b0ca…`), of its
  addendum (`548051b3…`), of its design file (`a61d7647…` for the small engine,
  `237408ea…` for the H100), of the replay code, of both client trees (`f46414b0…`, and
  `a61ef323…`: spec-ptc `9b78b7d` with patches 1 to 6) and of the corpus into its
  `campaign.jsonl` before its first unit. The stopped launch had done the same for the
  files it knew, with the client at patch 5 (`545d9505…`).
- Files here: per run `campaign.jsonl`, `design.json`, `launch.json`, `server.json`,
  `summary.md`, `summary.json`, and each unit's `replay.json` and `unit.json`;
  `stopped/` for the launch that was stopped. The H100 run also has `long_calls.md`
  (`cloud/long_calls.py`) and `width.md` (`cloud/width.py`), with their `.json`. Events hold OOLONG text and stay out of
  the repository.

## 1. The first launch, which I stopped

`stopped/20261111-083951-small`: run 1 as registered, the client at patch 5. It ran its
thrown-away unit and `stream`, and I stopped it 16 minutes in, for two reasons
(`cloud/PREREG_GOVERN_ADDENDUM.md`):

- My budget was wrong. A unit takes 490 s on that engine; my dry run had said 243 s,
  and the launch would have ended before `auto`.
- The thrown-away unit showed a defect in the governor. 47 s in, the cold engine
  spent two seconds in one step. Its numbers did not change: 4 requests running, none
  waiting. Eight samples in a row said so, and one session's window went from 16 to 256
  on them. Then 240 requests were waiting.

  The rule had taken a sample for new when the client had read again. An engine's
  numbers only change when it steps. Patch 6 adds one rule: no growth while the engine
  has requests in its batch and has written no token since the last sample. In the same
  unit of the relaunch, through the same cold step, the window stopped at 54 and the
  queue at 31.

No measured unit of a governed arm existed when the rule was changed. Both runs below use
the client at patch 6.

## 2. Run 1: an engine with 16 places

`20261111-090725-small`: one T4, vLLM 0.32.0, `Qwen/Qwen3-1.7B` in half precision, eager,
a 32,768-token window, `--max-num-seqs 16`. Eight of the ten sessions of November's
replay, 8 at a time. The sessions were recorded on the H100 with a 30B model: here they
are a load, and the run asks what each client does to an engine with 16 places.

| | prediction | dry run | measured | |
|---|---|---|---|---|
| S1 | every unit is exact | all | 3 of 3 (4 of 4 with the thrown-away unit) | held |
| S2 | no call is sent that the recorded run did not send, and none twice | 0 | 0 | held |
| S3 | no speculative call is evicted | 0 | 0 | held |
| S4 | a fixed 128 makes the root's turn wait: `wide`'s root TTFT at the 90th percentile is at least 2.5 times `stream`'s | 7.4 | 3.73 | held |
| S5 | the governed window does not: `auto`'s is at most 1.25 times `stream`'s | 0.66 | 0.69 | held |
| S6 | the engine's largest queue: `wide`'s is at least 3 times `stream`'s | 9.2 | 9.39 | held |
| S7 | the engine's largest queue: `auto`'s is at most 1.5 times `stream`'s | 0.74 | 0.89 | held |
| S8 | width buys nothing on 16 places: `wide` at least 0.98 of `stream` in session time | 1.031 | 0.981 | held |
| S9 | session time: `auto` at most 1.04 of `stream` | 1.018 | 0.996 | held |
| S10 | session time: `auto` at most 1.01 of `wide` | 0.987 | 1.016 | **did not hold** |
| S11 | the governed windows close: at least 10 cuts in `auto` | 63 | 189 | held |
| S12 | and no window of `auto` gets to 128 | widest 42 | widest 38 | held |
| S13 | root stream seconds: `auto` at most 1.03 of `stream` | 0.992 | 0.975 | held |

Summed over the 8 sessions:

| arm | session time s | of `stream` | root streams s | after-stream s | root TTFT s, median / 90th / 99th / longest | root turns that waited over 5 s | the engine's queue, mean / 90th percentile / largest | sub-call ms, median / 90th |
|---|---|---|---|---|---|---|---|---|
| `stream` | 2,590.1 | - | 2,119.8 | 464.4 | 1.23 / 2.53 / 5.32 / 6.17 | 2 of 81 | 8.0 / 35 / 38 | 742 / 2,263 |
| `wide` | 2,540.5 | 0.981 | 2,156.9 | 375.6 | 1.25 / 9.43 / 12.95 / 13.06 | 21 of 81 | 60.5 / 251 / 357 | 1,939 / 12,047 |
| `auto` | 2,580.1 | 0.996 | 2,066.7 | 506.6 | 1.04 / 1.76 / 5.32 / 6.17 | 2 of 81 | 3.1 / 9 / 34 | 630 / 1,328 |

- A window of 128 fills the engine's queue, and the root's next turn waits behind it.
  357 requests waiting at most, 60 on average. One root turn in four waited more than
  5 s for its first token, up to 13 s. As shipped it is 2 turns in 81, and those two
  wait in every arm: their prompts are long and new.
- The governed window kept the queue short and the roots moving. 3 requests waiting
  on average, where the shipped client's 16 leave 8. The root's first token came after
  1.8 s at the 90th percentile, against 2.5 s as shipped and 9.4 s at 128, and the root
  streams were 2.5% shorter than as shipped.
- It did so by closing. 189 cuts in one unit, no window above 38. The sessions with
  bursts held windows of 8 to 11 at the median, some down to 1. The engine's places were
  as full as in the other arms (13.4 requests running while there was work, 13.7 as
  shipped).
- In summed session time the three clients are within 2% of each other. The engine
  does the same work in each: what a client changes is who waits. At 128 the sub-calls
  go first and the bursts end sooner (376 s after the streams, 464 s as shipped, 507 s
  governed); the roots pay with their first token.
- S10 did not hold: the fixed 128 was the faster client in session time, by 1.6%. I
  had said the governed window would be within 1% of it. One unit per arm, and a replay
  repeats within 1 to 2%, so the two are not told apart; but the sign is against me, and
  the reason is above: a long queue is a way of giving sub-calls the engine first.
- The shipped client's 16 is about right for an engine with 16 places, and the
  governed window does not beat it in session time there (0.996). What it adds over the
  constant is on the other engine.
- The real engine is about half as fast as the dry run's fake one (a root token every
  84 ms where the fake engine had 44; prefill at about 2,000 tokens a second). Every
  ratio the predictions name came out on the predicted side but S10.

## 3. Run 2: the H100, and its predictions

`20261111-091523-replay`: one H100, vLLM 0.32.0, `Qwen/Qwen3-30B-A3B-Instruct-2507`, the
settings of the replay of November 10. Eleven sessions, 8 at a time: the 10 of the
registered replay, and `trec132k-17000222.fix2`, whose turn 7 makes four calls on chunks
of 100,000 characters (three prompts of 36,000 tokens and one of 6,000). That session
runs first, next to seven others. 49 minutes.

| | prediction | dry run | measured | |
|---|---|---|---|---|
| H1 | every unit is exact | all | 5 of 5 (6 of 6 with the thrown-away unit) | held |
| H2 | no call is sent that the recorded run did not send, and none twice | 0 | 0 | held |
| H3 | no speculative call is evicted: past a test too, the scout places no bet | 0 | 0 | held |
| **F1** | **the finish rule, 1:** over the 10, `auto`'s session time is at most 1.02 of `wide`'s | 1.002 | **0.985** | held |
| **F2** | **the finish rule, 2:** over the 10, `auto`'s root stream seconds are at most 1.05 of `stream`'s | 1.038 | **1.014** | held |
| H4 | over the 10, `wide` is at 0.84 to 0.93 of `stream` in session time (November 10: 0.874) | 0.885 | 0.862 | held |
| H5 | over the 10, `auto` is at 0.78 to 0.93 of `stream` | 0.887 | 0.849 | held |
| H6 | the largest loop (3,181 calls): `auto` spends at most 1.10 of `wide`'s seconds after the stream | 0.695 | 0.600 | held |
| H7 | a window of `auto` gets wider than 128 | 256 | 256 | held |
| H8 | at least half of `auto`'s sub-calls are sent at a window above 16 | 0.99 | 0.99 | held |
| H9 | the long turn as shipped: `stream` spends at least 450 s after its stream | 563.6 | 536.7 | held |
| H10 | the long turn: a wider window does nothing for it, `wide` at 0.90 to 1.10 of `stream` | 0.993 | 0.983 | held |
| H11 | the long turn: `auto` spends at most 0.80 of `stream`'s seconds | 0.668 | 0.659 | held |
| H12 | in `auto` the engine's KV cache stays at or under 97% | 0.87 | 0.74 | held |
| H13 | in `auto` the engine preempts nothing | 0 | 0 | held |
| H14 | control: with the budget lifted, the four long calls take the KV cache to at least 95% | 1.00 | 0.96 | held |
| H15 | control: and the 10 pay for it, at least 1.01 of their session time in `wide` | 1.029 | 1.013 | held |
| H16 | the loop that tests each result: `auto-past` spends at most 0.60 of `auto`'s seconds after the stream | 0.245 | 0.237 | held |
| H17 | over the 10, `auto-past` is at most 1.00 of `auto` in session time | 0.968 | 0.966 | held |
| H18 | all 11 sessions: `auto` at most 0.90 of `stream` | 0.841 | 0.812 | held |
| H19 | all 11 sessions: `auto-past` at most 0.88 of `stream` | 0.821 | 0.791 | held |

All 21 held. Two of them held and still read differently from what I expected: H14 and
H15, in section 8.

## 4. Arms and sessions

**The 10 sessions of the registered replay,** summed:

| arm | session time s | of `stream` | of `wide` | root streams s | of `stream` | after-stream s |
|---|---|---|---|---|---|---|
| `stream` | 1,547.1 | - | - | 1,170.8 | - | 369.8 |
| `wide` | 1,333.4 | 0.862 | - | 1,184.8 | 1.012 | 141.3 |
| `auto` | 1,313.8 | 0.849 | 0.985 | 1,187.5 | 1.014 | 119.0 |
| `auto-past` | 1,268.6 | 0.820 | 0.951 | 1,184.8 | 1.012 | 75.8 |
| `wide-open` (control) | 1,350.4 | 0.873 | 1.013 | 1,201.0 | 1.026 | 142.6 |

**All 11,** with the session that makes the long calls:

| arm | session time s | of `stream` | of `wide` | root streams s | of `stream` | after-stream s |
|---|---|---|---|---|---|---|
| `stream` | 2,185.5 | - | - | 1,272.0 | - | 906.5 |
| `wide` | 1,967.7 | 0.900 | - | 1,290.7 | 1.015 | 669.1 |
| `auto` | 1,775.2 | 0.812 | 0.902 | 1,294.6 | 1.018 | 472.9 |
| `auto-past` | 1,727.9 | 0.791 | 0.878 | 1,290.9 | 1.015 | 428.5 |
| `wide-open` (control) | 1,643.2 | 0.752 | 0.835 | 1,309.2 | 1.029 | 326.7 |

- The finish rule holds. Over the 10, the governed client took 0.985 of the fixed
  128's session time (the bound: 1.02). Its root streams were 1.4% longer than as shipped
  (the bound: 5%); at a fixed 128 they were 1.2% longer.
- It is a tie with the fixed 128, not a win. One unit per arm, and a replay repeats
  within 1 to 2%. The 1.5% is one session: `trec132k-17000237.fix1`, with the largest
  loop, is 27 s shorter. The other nine together are 0.6% longer (1,185.0 against
  1,177.6 s).
- Two pairs of units agree on both halves of that. `auto` and `auto-past` have the
  same window; `wide` and `wide-open` have the same fixed 128. The session with the
  largest loop took 128.8 and 130.5 s governed, 155.8 and 160.9 s at 128.
- This launch repeats November's. Over the 10, `stream` took 1,547.1 s (1,537.9 on
  November 10) and `wide` 1,333.4 s (1,344.8).

Per session, seconds (and seconds after the turns' streams):

| session | `stream` | `wide` | `auto` | `auto-past` | `wide-open` |
|---|---|---|---|---|---|
| `pairs32k-1.fix1` | 75.2 (1.4) | 76.4 (0.1) | 76.2 (0.1) | 75.9 (0.1) | 76.0 (0.1) |
| `pairs32k-1.fix2` | 80.7 (10.6) | 74.7 (5.1) | 76.3 (7.4) | 75.8 (7.2) | 72.5 (2.5) |
| `pairs32k-15.fix1` | 236.3 (0.0) | 237.0 (0.1) | 237.7 (0.1) | 236.9 (0.0) | 239.0 (0.1) |
| `pairs32k-16.fix1` | 154.5 (7.4) | 153.3 (2.1) | 154.4 (2.7) | 153.7 (2.5) | 156.4 (2.2) |
| `pairs32k-16.fix2` | 107.6 (14.2) | 93.8 (3.1) | 96.1 (4.1) | 95.5 (4.0) | 94.4 (3.8) |
| `trec132k-17000222.fix2` (the 11th) | 638.5 (536.7) | 634.2 (527.8) | 461.5 (353.9) | 459.3 (352.7) | 292.8 (184.1) |
| `trec132k-17000232.fix1` | 101.2 (0.0) | 105.4 (0.0) | 105.2 (0.0) | 105.6 (0.0) | 108.0 (0.2) |
| `trec132k-17000237.fix1` | 338.7 (257.4) | 155.8 (72.7) | 128.8 (46.3) | 130.5 (47.9) | 160.9 (77.1) |
| `trec132k-17000237.fix2` | 236.2 (78.7) | 213.4 (58.0) | 213.4 (58.3) | 168.5 (13.9) | 214.0 (56.6) |
| `trec132k-17000241.fix1` | 108.6 (0.0) | 111.9 (0.0) | 112.8 (0.0) | 113.5 (0.0) | 114.8 (0.0) |
| `trec132k-17000241.fix2` | 108.1 (0.0) | 111.7 (0.0) | 112.8 (0.0) | 112.9 (0.0) | 114.3 (0.0) |

- A session with nothing to gain pays a little. Three sessions spend nothing after
  their streams and ran next to the largest loop. Each is 3 to 5 s longer than as shipped
  (3 to 5%), at a fixed 128 as with the governed window, and 6 to 7 s with no budget.

## 5. The turns

Every turn with at least 2 s after its stream in some arm. Seconds after the stream:

| session | turn | sub-calls | `stream` | `wide` | `auto` | `auto-past` | `wide-open` |
|---|---|---|---|---|---|---|---|
| `pairs32k-1.fix2` | 4 | 786 | 10.5 | 5.1 | 7.3 | 7.1 | 2.5 |
| `pairs32k-16.fix1` | 8 | 40 | 7.3 | 2.1 | 2.7 | 2.5 | 2.1 |
| `pairs32k-16.fix2` | 5 | 787 | 7.1 | 2.4 | 0.1 | 0.1 | 3.7 |
| `pairs32k-16.fix2` | 6 | 787 | 7.1 | 0.7 | 4.0 | 3.9 | 0.1 |
| `trec132k-17000222.fix2` | 7 | 4 | 536.7 | 527.8 | 353.9 | 352.7 | 184.1 |
| `trec132k-17000237.fix1` | 4 | 3,181 | 211.1 | 54.4 | 32.7 | 33.8 | 56.9 |
| `trec132k-17000237.fix1` | 6 | 3,181 | 46.3 | 18.3 | 13.7 | 14.1 | 20.1 |
| `trec132k-17000237.fix2` | 9 | 3,185 | 78.6 | 57.9 | 58.2 | 13.8 | 56.5 |

- The largest loop (`trec132k-17000237.fix1`, turn 4): 33 s governed, 54 to 57 s at a
  fixed 128, 211 s as shipped.
- The long turn (`trec132k-17000222.fix2`, turn 7): 354 s with the KV pool, 528 to
  537 s with the character budget, 184 s with no budget. Section 8.
- The loop that tests each result (`trec132k-17000237.fix2`, turn 9): 14 s when the
  scout goes on past the test, 57 to 58 s when it stops there. Section 9.
- The three loops of 786 and 787 calls take 11.1 and 11.4 s in the two governed
  units together, and 6.3 and 8.2 s in the two at a fixed 128. Section 7 says why.

## 6. What the limits did

| unit | moves (by reason) | window at a call, median / mean | calls sent above 16 / above 128 | widest / narrowest window | cuts | KV pool, smallest / largest (tokens) |
|---|---|---|---|---|---|---|
| `auto` | 134 (80 idle, 50 grow, 4 queue) | 256 / 177 | 12,610 / 8,357 of 12,775 | 256 / 11 | 4 | 99,802 / 136,238 |
| `auto-past` | 149 (91 idle, 56 grow, 2 queue) | 256 / 231 | 12,610 / 11,330 of 12,775 | 256 / 11 | 2 | 111,089 / 135,059 |

- A window opened to its ceiling on every large burst: from 16 to 256 in 7 steps,
  1.5 s, six times in `auto`. 65% of the sub-calls were sent at a window above 128 (89%
  in `auto-past`), 99% above 16.
- It closed again when its session had nothing to send. 80 of the 134 moves are a
  window on its way back to 16.
- Four cuts, all behind a long prompt (`width.md`). A prompt of 36,000 tokens takes the engine
  about 1.5 s to read. The requests sent after it wait that long: 40 behind 151 running,
  61 s into the unit; 3 behind 10 at 77 s. The governor read a standing queue each time
  and cut the two windows that had calls in flight to 0.7 of their width. The loop's
  window was back at 256 1.7 s later.
- The H100 queued behind long prompts and at no other time. 7 of the 922 samples of
  `auto` have a request waiting (9 of 1,266 in `wide`): each within 2.5 s after a prompt
  of 36,000 tokens was sent.
- The KV pool had 99,802 to 136,238 tokens for speculative calls: 88% of the engine's
  154,816, less what the engine held for everything else.

## 7. Width: where it pays, and where the client is the limit

Every burst of sub-calls is in `width.md` in the run's folder (`cloud/width.py`). In
flight: sent and not yet back, by the client's clock. The engine's count is its own
(`/metrics`), roots included.

**The largest loop: 3,181 calls that write 20 tokens each** (`trec132k-17000237.fix1`,
turn 4):

| arm | lasted s | calls a second | in flight at the client, mean / most | sub-call ms, median | requests running in the engine, median / most |
|---|---|---|---|---|---|
| `stream` | 211.4 | 15 | 16 / 16 | 1,006 | 22 / 43 |
| `wide` | 54.8 | 58 | 71 / 120 | 1,103 | 64 / 119 |
| `auto` | 33.0 | 96 | 125 / 241 | 1,179 | 120 / 236 |
| `auto-past` | 34.0 | 93 | 125 / 226 | 1,159 | 126 / 220 |

In `wide-open` the long prompts cut it in two parts, at 51 and 58 calls a second.

**The loops of calls that write 2 or 3 tokens** (786 to 3,185 calls each), grouped by how
many sub-calls the whole process had in flight while a loop ran. The loop that tests each
result is left out where it goes batch after batch:

| sub-calls in flight in the process, mean | bursts | sub-calls back a second, whole process | sub-call ms, median | requests running in the engine, median |
|---|---|---|---|---|
| 17 to 39: `stream`, one loop or two | 4 | 68 to 107 | 207 to 224 | 11 to 32 |
| 91 to 223: one loop at 128 or governed, or two at 128 | 13 | 175 to 264 | 390 to 1,314 | 13 to 48 |
| 342 to 351: two loops, both windows at 256 | 4 | 169 to 182 | 1,652 to 2,000 | 28 to 35 |

- Where a call is long enough for the engine to be the limit, width pays. A call
  that writes 20 tokens takes 1.0 to 1.2 s whether 16 or 241 are in flight, and the
  engine runs what the client has in flight (120 running with 125 in flight). The loop
  goes at 15, 58 and 96 calls a second: 33 s at a window of 256, 54 s at 128.
- Where a call writes 3 tokens, the client is the limit. With 91 to 223 in flight
  the process gets 175 to 264 calls back a second, with no trend inside that range. The
  engine has 256 places and ran 13 to 48 requests: the other calls in flight stood
  between the client and the engine's batch. The client's process was using a full core
  (0.96 to 1.26 of one at the governor's moves in such a burst).
- Two windows of 256 at once were too many. In both governed units two sessions
  launched a loop of 787 calls within 0.1 s of each other, and both windows went to 256:
  340 to 350 calls in flight on average, 515 at most. The process got 169 to 182 calls
  back a second, each after 1.7 to 2.0 s. The engine reported 28 to 35 requests running
  at the median and none waiting. The loops took 8.6 to 9.0 s each. At a fixed 128 the
  same two loops overlapped for 3 s and took 6.0 and 5.3 s. In the control they ran one
  after the other and took 3.7 and 3.0 s.
- Nothing the governor reads shows that. It reads the engine, and the engine had
  room. Each session has its own window, and nothing bounds their sum.
- I had built a hold on the client's own CPU share and left it off (`cpu_hold`), on
  an argument this run refutes: that a client at its limit has no call waiting for a
  place, so its window does not grow anyway. A batch's prompts do wait for places while
  the process is at a full core, and both windows grew to the ceiling. The hold has not
  run on a GPU.
- The way up costs about a second per burst. A governed burst had 100 calls in flight
  1.1 to 1.4 s after its first call; at a fixed 128, after 0.05 to 0.35 s.
- What this cost here: about 4 s of 1,314.

## 8. Long prompts: the pool, the character budget, and no budget

The four calls of the long turn (`long_calls.md` in the run's folder). "Other roots": the
token gaps of the other sessions' root streams while the long calls were in flight.

| arm | long calls in flight at once | from the first call out to the last one back, s | KV cache, peak | preemptions | largest queue in that time | other roots: gap median / 99th ms |
|---|---|---|---|---|---|---|
| `stream` (budget of 120,000 characters) | 2 | 539 | 0.45 | 0 | 16 | 45.5 / 55.9 |
| `wide` (the same budget) | 2 | 530 | 0.48 | 0 | 21 | 44.3 / 70.7 |
| `auto` (the KV pool) | 3 | 358 | 0.74 | 0 | 3 | 44.1 / 80.3 |
| `auto-past` (the KV pool) | 3 | 357 | 0.73 | 0 | 3 | 44.2 / 79.8 |
| `wide-open` (no budget) | 4 | 189 | 0.96 | 0 | 83 | 44.6 / 83.0 |

- A long call takes about 180 s however many run at once. Its answer runs to the cap
  of 4,096 tokens, at 44 ms a token. So the turn takes one round of 180 s for each group
  of calls that leave together: three rounds with the character budget (one prompt of
  100,000 characters fits into 120,000), two with the pool, one with no budget.
- The pool sent two of the three long calls and the short one together, and the third
  when they came back: 354 s after the stream, 0.66 of the shipped client's 537 s. The KV
  cache peaked at 74%. Nothing was preempted.
- With no budget all four went at once: 184 s. The KV cache reached 96%, and the engine
  preempted nothing. My dry run had 103 preemptions there. The fake engine charges for
  a full cache; this engine, on this load, did not fill it.
- What the lifted budget cost the other ten sessions: 17 s of session time against
  `wide`, the same client with the budget (1,350.4 against 1,333.4 s, 1.3%). Their root
  streams were 2.6% longer than as shipped, where `wide` has 1.2%. One root turn waited
  4.4 s for its first token (below).
- What it gained: 341 s for the long session against `wide`. The pool gained 173 s of
  those.
- So the pool's caution cost more than it saved here. Over all 11 sessions the
  control with no budget is the fastest client of this run: 0.752 of `stream`, against
  0.812 for `auto`. H15 held (the ten paid 1.3%; my bound was 1%), by less than a replay
  repeats within.
- How near 96% is to the edge, one unit does not say. 4% of this cache is 6,200
  tokens. A root prompt in these sessions has 3,500 tokens at the median and 11,300 at
  the most. The pool keeps 12% free.
- One root turn waited, the same one in every arm of the fork: turn 1 of
  `trec132k-17000237.fix2` began 0.2 s after the long calls left, and its first token
  waited for the engine to read them. 1.3 s behind one long prompt (`wide`), 2.7 s behind
  two (`auto`), 4.4 s behind three (`wide-open`): 25,000 to 30,000 prompt tokens a
  second, first come first served. As shipped the first long call left 2.7 s before that
  turn began, the engine had read it, and the turn's first token came after 0.13 s.
  Whether a root's turn falls behind a long prompt is a matter of 3 s. **Neither limit
  looks at this.** The pool counts memory and the window counts calls.

## 9. The scout past a test

Turn 9 of `trec132k-17000237.fix2` is a loop of 160 batches, 3,185 calls. After each
batch the program tests the result, and neither arm of the test can leave the loop. The
scout used to stop at the first test, and the shadow then launched batch after batch.

| | `stream` | `wide` | `auto` | `auto-past` |
|---|---|---|---|---|
| seconds after the turn's stream | 78.6 | 57.9 | 58.2 | 13.8 |
| the session, s | 236.2 | 213.4 | 213.4 | 168.5 |
| calls launched by the scout, the whole unit | - | 9,612 of 12,777 | 9,612 of 12,777 | 12,777 of 12,777 |

- Going on past the test launched the loop ahead: 13.8 s where `auto` has 58.2
  (0.24). The scout passed 3,972 tests, in two statements of two sessions.
- It placed no bet. No call was sent that the recorded run did not send, none twice,
  none evicted (H2, H3). The scout runs neither arm of such a test and marks the names an
  arm sets as unknown; a call that needs one of them is not launched.
- Over the 10 sessions: 0.966 of `auto`, all of it this turn.
- One loop in one session.

## 10. The roots and the engine

| arm | unit s | root token gap, median / 99th ms | root TTFT s, median / 90th / 99th / longest | sub-call ms, median / 90th | requests running, mean / most | largest queue (share of samples with a request waiting) | KV cache, peak | preemptions |
|---|---|---|---|---|---|---|---|---|
| `stream` | 638 | 44.0 / 55.8 | 0.14 / 0.16 / 0.21 / 0.23 | 248 / 1,082 | 10.4 / 43 | 16 (0.01) | 0.45 | 0 |
| `wide` | 634 | 44.3 / 79.8 | 0.14 / 0.19 / 0.24 / 1.28 | 488 / 1,305 | 10.8 / 141 | 40 (0.01) | 0.48 | 0 |
| `auto` | 461 | 44.2 / 116.0 | 0.14 / 0.20 / 0.31 / 2.73 | 805 / 1,716 | 15.5 / 236 | 40 (0.01) | 0.74 | 0 |
| `auto-past` | 459 | 44.0 / 109.3 | 0.14 / 0.19 / 0.23 / 2.80 | 874 / 1,947 | 15.6 / 220 | 40 (0.01) | 0.73 | 0 |
| `wide-open` | 293 | 44.3 / 120.8 | 0.14 / 0.18 / 0.28 / 4.39 | 511 / 1,346 | 23.7 / 128 | 83 (0.02) | 0.96 | 0 |

- The root's median token gap is 44 ms in every arm. Its 99th percentile is 56 ms as
  shipped, 80 ms at a fixed 128 and 116 ms governed.
- The roots' streams are 1.2 to 1.4% longer in the fork's arms over the 10 (2.6% with
  no budget). That is F2, and the argument the limits rest on: an engine that queued
  nothing and preempted nothing did not make the roots clearly slower under a window of
  256.
- The first token: 0.14 s at the median and at most 0.31 s at the 99th percentile in
  every arm. One turn in 112 waited longer than half a second in each arm of the fork,
  behind the long prompts (section 8).
- The engine's own time between tokens was 2 to 3% above its quiet time at the
  median of the governor's moves, and at most 19% in `auto` (64% at one move of
  `auto-past`). Part of the tail of the root's gaps may be the client's own: the process
  that reads the root's stream is the one that was using a full core. I did not separate
  the two.

## What it changes

- The finish rule is met, so this stage is done as it was set out. The README reports
  `auto` over `stream` (0.849 over the 10) next to `wide` over `stream` from the same
  launch (0.862), and "a window and a character budget that follow the load" comes off
  the list of things not done (`docs/h100-study.md`, Limitations).
- What the limits are for is one client for two engines, not a faster H100. On the
  H100 it ties the hand-set 128. On 16 places it ties the shipped 16 in session time and
  keeps the root's first token where the shipped client has it, where a fixed 128 makes
  one root turn in four wait more than 5 s.
- On 16 places a fixed 128 was still the faster client in session time, by 1.6% (S10
  did not hold). A long queue gives the sub-calls the engine first. The roots pay with
  their first token, and session time does not count that.
- The KV pool beats the character budget and loses to no budget, on this engine: 0.66
  of the shipped client's time for the long turn, where no budget gives 0.34 at a cost of
  1.3% to the other sessions.
- The scout past a test is worth 0.24 on its loop and placed no bet.
- Three things to build before the limits are trusted on a third engine, none of them
  built: a bound on what one process sends when the client is the limit; long prompts
  paced by what the engine can read while a root's turn waits; and a queue behind one
  long prompt told apart from a standing one.
- Bets across turns, the other half of this stage (`cloud/README.md`), were not started.

## Bugs found

- A governor that grew on unchanged numbers (section 1): found by a thrown-away unit
  on a cold engine, fixed as patch 6 with a test from the measured case.
- My dry run was twice as fast as the T4. Every ratio the predictions name came out
  on the predicted side but one; the launch's budget did not.
- My fake engine preempts when its cache is full, and the H100's cache did not fill.
  The dry run's 103 preemptions with the budget lifted were 0 on the engine.
- The engine's queue counts what its scheduler holds. With about 500 calls in flight
  at the client the engine reported none waiting. A client that watches only that queue
  does not see its own.

## Limits

- One unit per arm. A replay repeats within 1 to 2%, and F1's margin is that size.
  The governed and the fixed windows each have two units that agree (section 4).
- Two engines, one model each, one workload, 11 sessions (8 on the T4).
- `auto` differs from `wide` in three things: the governed window, the KV pool, and
  batches in chunks of 32. These runs cannot tell the third from the first.
- The sessions were recorded without speculation on the H100. On the T4 they are a
  load, not a measurement of that model, and its 16 places are a server flag.
- One process holds every session. The KV pool counts what its own process sent.
- No bets. Every call here is certain to be used.
- Quality: answers are replayed.

## Since the runs

- One of the three things has a bound now (`integrations/spec-ptc-fork/`, patch 7):
  the governed windows of one process on one engine share one ceiling of 256, by what
  each session has in flight or waiting. The two loops of section 7 would have had 128
  each, which is what `wide` had there. No run measured it: it has local tests only.
  In a dry run against the fake engine, two loops that met had 128 each, the process
  had at most 264 sub-calls in flight, and the unit was exact.
- Nothing else changed in the client. The prefill of long prompts in front of a
  root's turn and the queue behind one long prompt are as in the runs.
