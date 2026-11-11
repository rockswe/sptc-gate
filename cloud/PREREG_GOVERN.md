# Limits that follow the load: what the runs should show (fixed before the GPU runs)

Written 2026-11-11, before any run on a GPU. `replay_campaign.py` records this file's
sha256 in `campaign.jsonl` (`begin`, under `files`) before the first unit of each run, and
the sha256 of the run's design file (`design_govern_small.json`, `design_govern_h100.json`)
next to it. Never edit any of the three after a run.

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)). Where it names the README's
status table and its list of things not done, it means the README of that time.*

## The question

spec-ptc holds speculation back with two constants: 16 calls in flight, and 120,000
characters of speculative prompts in flight per session. The replay of November 10
(`../results/modal_h100_record/RESULTS.md`) found both below what the H100 took:

- 128 calls in flight took session time to 0.874 of the shipped client's;
- with the character budget lifted, one session's four long calls ran together: 178 s,
  where the shipped client takes about 530 s.

Both are hand-set numbers again, found for one engine by trying. On a small or a busy
engine the same numbers can be too high.

**Can the client set both limits itself, from what the engine reports, and be as good as
the best hand-set number where the engine has room, and hold back where it has not?**

A second, smaller question rides along: the recording had one loop that tests each result
(80 s), which neither client launches ahead. `PREREG_RECORD.md` said such a scout might
be built after seeing the recording. It is built now, as an arm of its own.

Bets across turns are not part of it.

## What was built

In the fork (`../integrations/spec-ptc-fork/`, patch 5), all of it off unless asked for:

1. A governor for the window (`spec_ptc.engine.load.Governor`). The window is the
   number of a session's speculative calls in flight. It starts at spec-ptc's 16 and moves
   between 1 and 256, one step per sample of the engine's `/metrics` (four a second):
   - up while calls wait for a place and nothing says stop: by half of itself until
     the first cut, by an eighth after it, and by half again after three samples in a
     row with nothing holding it;
   - cut to 0.7 on a standing queue: a quarter of what the engine runs was waiting,
     in three samples in a row. **Halved** when the engine preempted or its KV cache is
     above 97%. A session with no call in flight is not cut;
   - held (no growth) on any request waiting, with the KV cache above 93%, or while
     tokens take twice their quiet time;
   - back towards 16 after 2 s with no call waiting or in flight, or to where the
     last cut left it if that is lower;
   - unchanged while the engine's numbers are missing or old.
2. A KV pool for long prompts (`KvPool`), one for all sessions of the process, in
   place of 120,000 characters per session. A call is admitted if its prompt, with a tenth
   more for its answer, fits into 88% of the engine's KV cache less what everything else
   holds. The client has no tokenizer: it counts 2.5 characters a token, on the low side
   (OOLONG's context text runs at 2.8). A call that does not fit waits. Three kinds do
   not wait: a small call (under 1% of the cache) is counted and never held; a call
   somebody is already waiting for is let through; and with nothing of the pool's in
   flight any call goes.
3. Batches in chunks: a batch goes to rlms' handler in requests of at most 32 prompts,
   and never more than the window, each sent as soon as its speculations exist.
4. The scout goes on past a test that cannot leave its loop (`spec_scout="past"`): an
   `if` on a result whose arms hold no `return`, `raise`, `break`, `continue` or
   `assert`. The scout runs neither arm, the names an arm sets are unknown from there
   on, and a call inside an arm is not launched.

In the bench: the arms `auto` (1 to 3) and `auto-past` (1 to 4), the controls `wide-open`
and `wide-past`, a load model in the fake engine, and a report of what the limits did.

## The rule the limits follow, and why

This is an argument. The runs test what follows from it.

- A call that is certain to be used has to be run anyway. spec-ptc launched 17,206
  speculative calls in the campaign and every one was used.
- On an engine whose step time grows linearly with its batch, running such a call
  sooner does not cost the other requests more in total. A step with k requests takes
  c0 + c1 k and gives each of them a token. One more request makes that step c1 longer
  for every stream next to it, and yields one token. So each sub-call token costs each
  stream beside it c1 of delay, whenever it runs. A wider window does not add to that
  sum. It ends the burst sooner.
- What does cost the others is an engine past what it can admit. Requests wait in
  its queue, first come first served, and the root's next turn waits behind them. Or the
  KV cache overflows: a prompt at the head of the queue holds up everything behind it,
  and running requests are preempted and computed again.
- So the window is cut by the engine's queue, its KV cache and its preemptions, and
  the pace of tokens only stops it from growing: twice the quiet time is where a linear
  engine gives half of the most it can.

What would count against the argument: an engine that queues nothing, preempts nothing,
and still makes the roots' streams clearly longer under a wide window (F2 below).

## What I have seen when writing this

- The recordings and their replays (`../results/modal_h100_record/`,
  `../results/modal_h100_replay/`), and from their raw events:
  - The root's median token gap was 42.0 ms with at most 8 requests running and 44.7 ms
    with 97 to 128 (`wide`). Its stalls grew: 52 s against 23 s as shipped.
  - At a window of 128 the engine had 60 to 128 requests running during the largest
    loop, the roots among them: a good third of the 128 calls in flight were on their
    way to the engine's batch or back. It had a request waiting in 4 of 468 samples.
  - That loop (3,181 calls of 20 tokens) is bound by decoding: 53 s at 128 in flight.
    The loops of 3-token calls are bound by prefill and by the client.
- vLLM 0.32.0's source for the names of its metrics (`vllm/v1/metrics/loggers.py`).
  I have not seen a real server's `/metrics` text with a governed client on it.
- Local dry runs of both designs below: the corpus against
  `tests/fake_engine.py`, each speculative launch slowed to 2 ms as in a busy process on
  Modal (`/tmp`, not kept). The numbers are in the tables below.
  - The fake engine for the H100: 43 ms a step, 0.05% longer per running request, 256
    places, 154,816 tokens of KV cache. Over the 10 it gives `stream` and `wide` within
    5% of the session times measured on November 10, and their ratio at 0.885, where
    0.874 was measured.
  - The fake engine for the small one: 38 ms a step, 1.2% longer per running request, 16
    places, 89,072 tokens.
- Two flaws in my first design of the KV pool, both found before any GPU. One pool
  for all sessions let one session's long calls hold back another session's short ones:
  found by reasoning, and a small call is now never held. And it could hold a call that a
  session's shadow was already waiting for: found by the dry run, which lost 277 s in
  one turn to it (below).
- What the fake engine does not have: the client's and the API server's own limits.
  On the H100 a call spent a third of its time outside the engine's batch at 128 in
  flight. Above 128 the fake engine promises more than I expect the H100 to give.

## The finish rule

Said on November 11, before anything was built: the automatic limits must be as good as
the best fixed setting on the 10 recorded sessions, and the root's streams must not
become more than 5% longer. As numbers, on the H100 run below, over the 10 sessions of
the registered replay of November 10:

- F1: `auto`'s summed session time is at most 1.02 of `wide`'s. (A replay repeats
  within 1 to 2%.)
- F2: `auto`'s summed root stream seconds are at most 1.05 of `stream`'s.

What follows from them is in "What the result changes".

## Run 1: a small engine (a T4)

**Why.** On the H100 the engine was never the limit, so a run there shows the limits
opening and little else. Whether they close needs an engine with less room than the
client asks for.

- Engine: one T4 on Modal, vLLM 0.32.0, `Qwen/Qwen3-1.7B` in half precision, eager, a
  32,768-token window, and **`--max-num-seqs 16`: 16 places in its batch.** Without the
  flag this engine ran 131 requests at once in November's smoke run.
  `replay_app.py::small`.
- Sessions: 8 of the 10 registered ones, 8 at a time: all but
  `trec132k-17000241.fix2` (its 37,000-token prompts do not fit the window) and
  `trec132k-17000237.fix1` (its 6,362 calls would take a unit to 10 minutes here).
- Units, one each, in this order: `auto` on four sessions, thrown away; then
  `stream`, `wide`, `auto`.
- What it is not: a measurement of spec-ptc on a T4. The sessions were recorded on
  the H100 with a 30B model. The run asks one thing: what each client does to an engine
  with 16 places.

## Run 2: the H100

- Engine and settings: as the replay of November 10: one H100 launch, vLLM 0.32.0,
  `Qwen/Qwen3-30B-A3B-Instruct-2507`, the campaign's flags with `--max-model-len 65536`,
  sessions 8 at a time, rlms' handler with a backlog of 1,024, a salt per unit, no task
  timeout, `PYTHONHASHSEED=0`. Clients: spec-ptc at `9b78b7d`, and the fork at patch 5.
- Sessions: 11. The 10 registered ones, and `trec132k-17000222.fix2` replayed up to
  its turn 10: the session with four calls on chunks of 100,000 characters. It was an
  extra in November because the recording's deadline had stopped it. It is in every unit
  here, because the KV pool has nothing to decide without it. **It runs first,** next to
  seven others: in November it ran last, almost alone on the engine, and that is why
  lifting the budget cost nobody anything.
- Units, one each, in this order: `auto-past` on six sessions, thrown away; then
  `stream`, `wide`, `auto`, `auto-past`; then the control `wide-open`, last, so that a
  budget stop costs it first.
- `wide` is the best fixed setting so far and the arm of November, unchanged. `auto`
  differs from it in three things: the governed window, the KV pool, and batches in
  chunks of 32. This run cannot tell the third from the first.

## Definitions

As `PREREG_RECORD.md` and its addendum. In addition:

- The 10: the sessions of the registered replay of November 10. **The 11th:**
  `trec132k-17000222.fix2`. **The long turn:** its turn 7.
- The window at a call: the window of its session when a sub-call was sent.
- A cut: a move of a window down because the engine queued, preempted or was short of
  KV cache.
- TTFT: the time from sending a root's turn to its first token.

## The dry runs

One unit per arm against `tests/fake_engine.py`, each speculative launch slowed to 2 ms.
Not kept. Seconds are the fake engine's.

**The small engine** (38 ms a step, 1.2% longer per running request, 16 places, 89,072
tokens of KV cache; the 8 sessions):

| arm | session time s | of `stream` | root streams s | root TTFT s, median / 90th / 99th / longest | the engine's largest queue | sub-call ms, median / 90th |
|---|---|---|---|---|---|---|
| `stream` | 1,208.6 | - | 1,024.3 | 0.16 / 0.67 / 0.96 / 1.15 | 39 | 318 / 872 |
| `wide` | 1,246.4 | 1.031 | 1,064.2 | 0.15 / 4.96 / 6.34 / 7.43 | 358 | 471 / 5,685 |
| `auto` | 1,230.1 | 1.018 | 1,016.5 | 0.14 / 0.44 / 0.64 / 1.31 | 29 | 278 / 428 |

- A window of 128 buys nothing there and makes the roots wait. The engine runs 16
  requests whatever the client sends. The rest queue, and a root's next turn queues
  behind them: 5 s at the 90th percentile, where the shipped client's 16 gives 0.7 s.
- The governed windows closed: 63 cuts, no window above 42, a third of the sub-calls
  sent at a window below 16. They start at 16, so the first second of a burst is as
  shipped.
- It is not faster than the shipped client there, and I do not expect it to be. 16 is
  about right for an engine with 16 places. The run asks whether one client can be right
  on both engines.
- Two rules changed after first dry runs, both on this engine:
  - A standing queue was "a request waiting in three samples in a row". That cut until
    nothing waited and left places of the engine empty: 1.043 of `stream`. It is now a
    quarter of what the engine runs, waiting: 1.020.
  - After a cut, a session's next burst started at 16 again. It now starts where the cut
    left the window: 1.018.

**The H100** (43 ms a step, 0.05% longer per running request, 256 places, 154,816 tokens;
context prompts of more than 20,000 characters at 2.8 characters a token; the 11 sessions,
the 11th first):

| arm | session time s, the 11 | of `stream` | the 10 | of `stream` | root streams s, the 10 | the long turn s | the largest loop s | KV cache, peak | preemptions | unit s |
|---|---|---|---|---|---|---|---|---|---|---|
| `stream` | 2,265.7 | - | 1,590.6 | - | 1,240.9 | 563.6 | 211.9 | 0.55 | 0 | 675 |
| `wide` | 2,080.0 | 0.918 | 1,407.0 | 0.885 | 1,268.4 | 559.9 | 57.6 | 0.58 | 0 | 673 |
| `auto` | 1,904.7 | 0.841 | 1,410.3 | 0.887 | 1,287.9 | 376.3 | 40.1 | 0.87 | 0 | 494 |
| `auto-past` | 1,860.2 | 0.821 | 1,365.7 | 0.859 | 1,288.2 | 378.1 | 40.0 | 0.87 | 0 | 495 |
| `wide-open` (control) | 1,763.6 | 0.778 | 1,448.4 | 0.911 | 1,301.8 | 197.5 | 62.1 | 1.00 | 103 | 315 |

The long turn and the largest loop: seconds after the turn's stream. Every unit exact, no
call sent twice, none evicted.

- Over the 10 the governed window ties the fixed 128: 1.002 of `wide`. It opens to
  256 with no cut and sends 60% of the sub-calls at a window above 128. The largest loop
  takes 40 s where 128 takes 58 s. The roots give the difference back: their streams are
  3.8% longer than as shipped, 2.2% at 128.
- The long turn: the pool admits two of the three long calls and the short one
  together, then the third: 376 s where the shipped budget takes 564 s. The KV cache
  peaks at 87%.
- Lifting the budget is faster than the pool in this dry run, in summed session time:
  0.778 against 0.841 over the 11. It runs all four calls at once. The price is the other
  ten sessions' (1.029 of their time in `wide`, 103 preemptions, a root TTFT of 4 s). The
  pool's case is what it spares them, and whether a real engine charges more for a full
  KV cache than this fake one does. H14 and H15 say what I expect; I hold H15 loosely.
- Past the test the loop of 160 batches goes from 58 s to 14 s after its stream.
- A defect found by this dry run, and fixed before any GPU. In its first pass `auto`
  lost 277 s in one turn of `trec132k-17000237.fix2`. A statement used the result of a
  call with a 308,000-character prompt. The shadow waited for that result, the call
  waited in the pool for room that another session's long calls held, and the real run
  waited for the shadow. The rule "a call somebody is already waiting for is let
  through" came from there, with a test that blocks without it.
- The shipped client left 2,485 calls unspeculated in these dry runs (its runaway
  guard counts launching, and a launch is slowed to 2 ms here). On the H100 in November
  it left none. They are in the loop that tests each result, which it runs one batch
  after another in both cases.
- `wide`'s unit ran before the fake engine counted long prompts at 2.8 characters a
  token. `stream`'s unit before and after that change: 2,252.5 and 2,265.7 s.

## Predictions, in numbers

Scored by `replay_report.py` from the design files (`checks`): the number, its bounds,
held or not. "Dry run" is the number above.

**Run 1, the small engine** (`design_govern_small.json`):

| | prediction | counts against it |
|---|---|---|
| S1 | Every unit is exact (units that are not: 0) | Any unit not exact: it does not count |
| S2 | No call is sent that the recorded run did not send, and none twice (dry run: 0) | Any |
| S3 | No speculative call is evicted (dry run: 0) | Any |
| S4 | A fixed 128 makes the root's turn wait: `wide`'s root TTFT, 90th percentile, is at least 2.5 times `stream`'s (dry run: 7.4) | Below 2.5: a window of 128 does not make roots wait on an engine with 16 places, and the argument above is wrong about its queue |
| S5 | The governed window does not: `auto`'s root TTFT, 90th percentile, is at most 1.25 times `stream`'s (dry run: 0.66) | Above 1.25: the governed window makes roots wait more than the shipped client does |
| S6 | The engine's largest queue: `wide`'s is at least 3 times `stream`'s (dry run: 9.2) | Below 3 |
| S7 | The engine's largest queue: `auto`'s is at most 1.5 times `stream`'s (dry run: 0.74) | Above 1.5: the governed window does not keep the queue short |
| S8 | Width buys nothing on an engine with 16 places: `wide` at least 0.98 of `stream` in session time (dry run: 1.031) | Below 0.98: a wider window is faster even here |
| S9 | Session time: `auto` at most 1.04 of `stream` (dry run: 1.018) | Above 1.04: closing the window costs more session time than the shipped 16 does |
| S10 | Session time: `auto` at most 1.01 of `wide` (dry run: 0.987) | Above 1.01: on a small engine too, a fixed 128 is the faster setting |
| S11 | The governed windows close: at least 10 cuts in `auto` (dry run: 63) | Fewer than 10: the engine's queue did not reach the client |
| S12 | And no window of `auto` gets to 128 (dry run: the widest is 42) | 128 or more |
| S13 | Root stream seconds: `auto` at most 1.03 of `stream` (dry run: 0.992) | Above 1.03 |

**Run 2, the H100** (`design_govern_h100.json`):

| | prediction | dry run | counts against it |
|---|---|---|---|
| H1 | Every unit is exact (units that are not: 0) | 0 | Any unit not exact: it does not count |
| H2 | No call is sent that the recorded run did not send, and none twice | 0 | Any: the scout launched a call the program does not make |
| H3 | No speculative call is evicted: past a test too, the scout places no bet | 0 | Any |
| F1 | **the finish rule, 1:** over the 10, `auto`'s session time is at most 1.02 of `wide`'s | 1.002 | Above 1.02: a hand-set 128 is better than the governed window on this engine |
| F2 | **the finish rule, 2:** over the 10, `auto`'s root stream seconds are at most 1.05 of `stream`'s | 1.038 | Above 1.05: the wider window is paid for by the root's own stream |
| H4 | Over the 10, `wide` is at 0.84 to 0.93 of `stream` in session time (measured on November 10: 0.874) | 0.885 | Outside: this launch does not repeat November's |
| H5 | Over the 10, `auto` is at 0.78 to 0.93 of `stream` in session time | 0.887 | Outside |
| H6 | The largest loop (`trec132k-17000237.fix1` turn 4, 3,181 calls): `auto` spends at most 1.10 of `wide`'s seconds after the stream | 0.695 | Above 1.10: the window's way up from 16 costs more than its width gains |
| H7 | A window of `auto` gets wider than 128 | 256 | 128 or less: the engine or the client stopped it below the best hand-set number |
| H8 | At least half of `auto`'s sub-calls are sent at a window above 16 | 0.99 | Fewer: the window hardly opened |
| H9 | The long turn (`trec132k-17000222.fix2` turn 7) as shipped: `stream` spends at least 450 s after its stream (November: about 530 s, worked out from recorded call times) | 563.6 | Less: the character budget does not hold the long calls back as I worked out |
| H10 | The long turn: a wider window does nothing for it, `wide` at 0.90 to 1.10 of `stream` | 0.993 | Outside |
| H11 | The long turn: `auto` spends at most 0.80 of `stream`'s seconds | 0.668 | Above 0.80: the KV pool admitted no more than the character budget does |
| H12 | In `auto` the engine's KV cache stays at or under 97% | 0.87 | Above: the pool admitted more than the cache holds |
| H13 | In `auto` the engine preempts nothing | 0 | Any preemption |
| H14 | Control: with the character budget lifted and nothing following the load, the four long calls take the KV cache to at least 95% (`wide-open`) | 1.00 | Below 95%: on this engine and this load the four calls fit, as they did in November next to idle sessions |
| H15 | Control: and the 10 pay for it, their session time in `wide-open` at least 1.01 of `wide`'s | 1.029 | Below 1.01: lifting the budget cost the others nothing here, and the pool's caution bought nothing |
| H16 | The loop that tests each result (`trec132k-17000237.fix2` turn 9): `auto-past` spends at most 0.60 of `auto`'s seconds after the stream | 0.245 | Above 0.60: going on past the test did not launch the loop ahead |
| H17 | Over the 10, `auto-past` is at most 1.00 of `auto` in session time | 0.968 | Above 1.00 |
| H18 | All 11 sessions: `auto` at most 0.90 of `stream` in session time | 0.841 | Above 0.90 |
| H19 | All 11 sessions: `auto-past` at most 0.88 of `stream` in session time | 0.821 | Above 0.88 |

How sure I am, for the ones that decide something:

- F1: about 2 chances in 3. The dry run says 1.002, the margin is 2%, and each arm
  has one unit. Above 128 the fake engine promises more than the H100 is likely to
  give; the way up from 16 costs a second or two per burst that starts after its stream.
- F2: about 3 in 5. November's `wide` was at 1.027, and this window goes wider.
- H11: about 3 in 4. It needs the engine to report its KV cache in the way the
  source says.
- H15: 1 in 2. The fake engine's preemption is cheap; I do not know the real one's
  price.
- H16: about 4 in 5.

## Not predicted

- How far above 128 the H100 lets a window go, and what it gains there. The fake
  engine has no client and no API server in it. I expect less than its number.
- How often the H100 queues at these windows. In November it had a request waiting in
  4 of 468 samples at a fixed 128.
- What the lifted budget does to the other sessions on a real engine beyond H14 and
  H15: the root's TTFT, stalls, preemptions. That is what the control is for.
- What the real `/metrics` look like to the client: whether the cache's size is in
  `cache_config_info` as the source says, and how the time between tokens behaves under a
  burst. Run 1 is also the first look at that. If the engine does not report its KV
  cache, the pool is not used and the long turn of `auto` will be as shipped: that would
  fail H11 and be said as what it is.

## Budget

| run | units | dry run s | cap |
|---|---|---|---|
| small engine | `auto` on four sessions (thrown away), `stream`, `wide`, `auto` | about 240 each | `--max-minutes 26`, hard timeout 30 minutes |
| H100 | `auto-past` on six sessions (thrown away), `stream`, `wide`, `auto`, `auto-past`, `wide-open` | 675, 673, 494, 495 and 315; the thrown-away unit about 250 | `--max-minutes 55`, hard timeout 63 minutes |

If the H100 run's budget stop strikes, it costs `wide-open` first, then `auto-past`.
The finish rule needs `stream`, `wide` and `auto`.

## What the result changes

In the README, under the H100 runs, and in the status table.

- F1 and F2 hold: on this engine the limits set themselves as well as the best
  hand-set window. The README says so, with the ratio, and takes "a window and a
  character budget that follow the load" off its list of things not done. The number
  that is reported first: `auto` over `stream` in summed session time over the 10, next
  to `wide` over `stream` from the same launch.
- F1 fails: a hand-set 128 was better here by the measured amount. The README says
  that, and what cost it.
- F2 fails: the governed window pays with the root's stream. The README says so, and
  the argument above loses its footing: an engine that queued nothing still made the
  roots slower.
- The small engine (S4 to S10): whether a fixed 128 is too high there and the
  governed window is not. If S4 fails, the README does not claim that a fixed window can
  be too high.
- The long turn (H9 to H15): reported with the 11 sessions, next to the 10, and as
  one session's one turn. If `wide-open` shows no cost to the others (H15 fails), the
  README says that lifting the budget beat the pool here.
- The scout past a test (H16, H17): one loop in one session. Reported as that.

## What this cannot say

- Two engines, one model each, one workload, 11 sessions. One unit per arm: a replay
  repeats within 1 to 2%, and F1's margin is that size.
- The sessions were recorded without speculation on the H100. On the T4 they are a
  load, not a measurement of that model.
- A small engine made small on purpose: 16 places are a server flag. An engine that
  is small because its GPU is, or busy because other tenants are, is not measured.
- One process holds every session. The KV pool counts what its own process sent.
  Clients in several processes each see the engine's numbers but not each other's calls
  that are on their way.
- Bets. Every call here is certain to be used. A client that places bets needs more
  than this: a bet that is not used is not work that had to be done anyway.
- Quality. Answers are replayed.
