# Real agent workload on an H100

The T4 benchmarks in the [README](../README.md#benchmarks) waste speculative calls on
purpose. This study asks what real speculation needs from an engine, and how much of a
session is left to win.

**Setup.** [spec-ptc](https://github.com/alexzhang13/spec-ptc)'s own OOLONG campaign: 8
tasks solved by a recursive language model (rlms 0.1.3), whose root model writes Python
that calls `llm_query` on pieces of a long context. Qwen3-30B-A3B on one vLLM 0.32 engine
on a Modal H100, 8 sessions at a time. The question and its rule were fixed before the
main run.

**Terms.** The run records under `results/` use a few words differently; both are given
here.

| term | meaning |
|---|---|
| root, sub-call | the agent's main model stream, which a user waits on, and an `llm_query` its program makes |
| stock spec-ptc | Alex Zhang's client, unmodified, at commit `9b78b7d` ("as shipped" in the records). On the H100 it runs in its streaming mode, through an adapter in `cloud/`, because rlms does not stream its root model |
| window | how many sub-calls a session may have in flight. Stock spec-ptc caps it at 16 |
| scout | a pass added by the patches: it runs each finished statement once more with tool calls that return a placeholder at once, and launches every call whose arguments are already known |
| bet | a speculative call that may never be used |
| hand-tuned | a limit set by hand for one engine ("hand-set" in the records) |
| adaptive limits | limits the client sets from the engine's load ("limits that follow the load") |
| batch slots | how many sequences an engine decodes at once, vLLM's `--max-num-seqs` ("places") |
| unit | one pass of one arm over the recorded sessions |

## Summary: patched client vs. stock spec-ptc

This project does not replace spec-ptc. The scheduler plugin sits under it, in the
engine, and the client changes are
[patches on top of it](../integrations/spec-ptc-fork/README.md), all off by default.

Session time relative to stock spec-ptc on one H100, summed over replayed sessions. Below
1 is faster:

| client | 8 sessions recorded while rlms lost batch prompts | 10 sessions recorded with rlms fixed | the same 10, a second launch |
|---|---|---|---|
| no speculation | 1.05 | 1.12 | - |
| stock spec-ptc | 1.00 | 1.00 | 1.00 |
| patched: scout, 16 calls in flight as in stock | 0.72 | **1.00** | - |
| patched: scout, 128 calls in flight | 0.65 | **0.87** | 0.86 |
| patched: scout, adaptive limits | - | - | **0.85** |
| patched: the same, and the scout continues past a test that cannot leave its loop | - | - | **0.82** |

- The two right-hand columns are the ones to read. They are the code the model writes
  when nothing is failing under it. There the scout adds nothing to stock spec-ptc, and
  the patches' gain is the wider window: 13% off session time, most of it in one session.
- The client can set that window itself (0.85 against the hand-tuned 0.86: a tie, with
  one unit per arm). The 0.82 is one loop in one session
  ([below](#adaptive-limits)).
- The 0.72 comes from a bug in rlms, not from a gap in spec-ptc. The loop it removed was the
  model's way around lost batch prompts ([below](#after-fixing-rlms)).
- Stock spec-ptc is 11% faster than no speculation there, and none of the 17,206
  speculative calls it launched in the live campaign was wasted.
- None of these numbers is comparable with spec-ptc's published 1.0–1.2×. That is its
  fan-out mode, live, on its own campaign. This project measured the streaming mode, on
  replays, and dropped the fan-out arm from the large-window run for budget. Its campaign
  also pins rlms 0.1.3, so its no-speculation baseline loses batch prompts and looks
  faster than it is.

## Where the time goes

What is left after spec-ptc's streaming mode:

- A fifth of a session. With the root's tokens feeding spec-ptc as they stream, the
  median task still spent 22% of its time waiting for sub-calls after the root had
  finished writing a turn (14 tasks, 95% CI 8–42%; the bar set beforehand was 15%).
- It is not behind conditions, so bets would not reach it. Of the 3,431 s waited:

  | why the client still waited | share |
  |---|---|
  | independent calls launched one after another, because the model's loop uses each result | 73% |
  | more than 16 calls at once, spec-ptc's cap on calls in flight | 19% |
  | the rest: speculation that stopped, crashed or was bypassed, and calls still running when the stream ended | 8% |

  Nearly all of the 73% is two of the 16 sessions: loops of single calls, in five turns,
  that ran into the task timeout. The largest of them tests each result (1,071 s).
- No bets, no waste. All 17,206 speculative calls were claimed. None came from
  spec-ptc's peek path, the only place it launches before a statement closes.
- The root did not pay. Within one server launch its median token gap was 52.7, 53.0 and
  53.2 ms with no speculation, fan-out and streaming.
- A live run of this size cannot show a speed-up. The same arm's two repeats of one task
  differed by a typical factor of 1.9.

Details: [`results/modal_h100_rlm/RESULTS.md`](../results/modal_h100_rlm/RESULTS.md),
with each run's summaries next to it. Raw events hold OOLONG text and are not in the
repository.

## Replay benchmark

Most of the gain in this section came from a bug in rlms. The
[next section](#after-fixing-rlms) repeats the measurement with the bug fixed.

With that noise a live run cannot compare two policies, so 8 recorded sessions were run
again on the engine with everything fixed but the policy:

- The root is a real stream forced to the recorded length. A sub-call is a real request
  of the recorded size that returns the recorded answer.
- A unit counts only if every turn sends the root the recorded message history (sha256).
  All 15 units of the two runs did. Such a unit is called exact below.
- The client changes are [patches on spec-ptc](../integrations/spec-ptc-fork/README.md),
  off by default: a scout pass that launches every call whose arguments are already
  known, and a wider window.
- What they should recover was written down before the H100 run.

How the bench works: [`cloud/README.md`](../cloud/README.md#the-replay-bench).

Summed over the 8 sessions, in the registered run (one server launch, 10 units):

| arm | session time | relative to stock spec-ptc | waiting after the root's streams |
|---|---|---|---|
| no speculation | 1,237 s | 1.05 | 496 s |
| stock spec-ptc | 1,180 s | - | 466 s |
| scout, 16 calls in flight as in stock | 851 s | **0.72** | 147 s |
| scout, 128 in flight, a batch launched as a batch | 761 s | **0.65** | 57 s |
| control: scout, 128 in flight, a thread per prompt | 751 s | 0.64 | 68 s |
| control: no speculation, rlms' batches 128 wide | 1,138 s | 0.96 | 441 s |

- The serial loop goes away. A loop of 319 single calls took 327 s without speculation,
  333 s with stock spec-ptc, 23 s with the scout and 4 s at 128 in flight. Over the turns
  the stock client launched serially, the scout recovered 87% of the waiting (predicted:
  at least 75%).
- The window is a separate lever, and on a batch it needs no speculation. 128 in flight
  recovered 63% of the seconds lost to the cap, and the scout alone none, both as
  predicted. rlms' own batches at 128 recovered 60% with no speculation at all. Width
  does nothing for a loop.
- The root pays nothing. Its median token gap was 35–38 ms in every arm.
- A replay repeats within 1–2%, where live repeats differed by a factor of 1.9.
- 8 of 11 pre-registered predictions held.
  - In one unit the patched client sent 1,042 calls twice: a defect in its handoff from
    scout to shadow, which failed two predictions. It is fixed, with tests that fail on
    the code of that run.
  - One arm's two units differed by 5.2%, not under 5%: the first unit of a launch pays
    for a cold engine.
  - A follow-up run on another launch checked the fix: no call sent twice in 4 units. 6
    of its 8 predictions held. The two misses are a mistake in that run's design, which
    put the arm under test first, on the cold engine.

Caveats for the 0.72:

- One session carries most of it (505 s to 192 s). Three of the 8 make almost no
  sub-calls.
- That session's loop answers a bug. rlms 0.1.3 loses prompts of every batch after a
  session's first. The model saw the error strings and fell back to single calls. The
  next section is the same measurement with rlms fixed.
- 8 sessions, one model, one workload, recorded without speculation. Answers are
  replayed, so quality is not measured.
- At 128 in flight the limit is the Python client, not the engine. Launching 3,182
  speculative calls took 6.5 to 22 s in a busy process.

Details: [`results/modal_h100_replay/RESULTS.md`](../results/modal_h100_replay/RESULTS.md).
What was fixed beforehand: [`cloud/PREREG_REPLAY.md`](../cloud/PREREG_REPLAY.md).

## After fixing rlms

The 0.72 leaned on a loop the model wrote because rlms was failing under it. So rlms'
batch path was fixed in the harness, 16 sessions were recorded without speculation, and
those that can be replayed were replayed. What each step should show was written down
before it: the recording's predictions before the recording, the replay's numbers before
the replay.

- The fix held. 14,361 batched prompts, none lost. On the same engine stock rlms lost 21
  of 80 probe prompts.
- With its batches answered, the model batched. 13 single calls and 644 batches. No
  session wrote a loop of 20 single calls. The prediction was 1 to 5 of the 16.

Summed over the 10 sessions that could be replayed (one server launch, one unit per arm
after a warm-up unit that was discarded, every unit exact):

| arm | session time | relative to stock spec-ptc | waiting after the root's streams |
|---|---|---|---|
| no speculation | 1,728 s | 1.12 | 572 s |
| stock spec-ptc | 1,538 s | - | 367 s |
| scout, 16 calls in flight as in stock | 1,542 s | **1.00** | 363 s |
| scout, 128 in flight, a batch launched as a batch | 1,345 s | **0.87** | 143 s |
| control: no speculation, rlms' batches 128 wide | 1,593 s | 1.04 | 426 s |

- The scout launches nothing the stock client does not. The model's loops of batches
  only store their results. spec-ptc launches such a loop whole, because a result's
  placeholder does not make its shadow wait until the result is used. The scout's case is
  narrower: a loop that uses each result without testing it. In these 16 sessions that
  came up once, for 30 s.
- The stock client is at 0.89 of no speculation (0.95 on the first corpus).
- The window is what is left, and on small batches it needs speculation. A loop of 159
  batches of 20 took 334 s without speculation, 270 s with rlms' batches 128 wide, 208 s
  with the stock client and 53 s with the scout at 128. A batch of 20 cannot fill 128
  slots; launching the next batches ahead can.
- One loop tests each result, and neither client launches it ahead (80 s in both). The
  scout places no bet, so it stops at the test. The test cannot leave the loop, so a
  scout that went on past it would be launching certain work. That was built next
  ([below](#adaptive-limits)).
- spec-ptc holds long prompts back itself. It keeps at most 120,000 characters of
  speculative prompts in flight per session. One session called `llm_query` on four
  chunks of 100,000 characters in a loop: 700 s without speculation, and about 530 s
  with the stock client by the recorded call times. With the budget lifted the four calls
  ran together in 178 s. The KV cache reached 88%, nothing was preempted, and the other
  ten sessions ran within 1% of their time without it. That is one session on one launch,
  outside the registered comparison.
- The predictions: 4 of 6 held for the recording, 14 of the 15 that could be tested for
  the replay. The one that failed there is my own: I expected the scout to gain on loops
  of batches.

Caveats for the 1.00:

- 10 of the 16 sessions could be replayed. Three of the others are roots that wrote
  until cut and made no sub-call. One hit a deadline of the recording. Two could not be
  rebuilt, through a mistake in the recording harness, and one of those holds the one
  loop the scout would have helped.
- The scout's case does occur unprovoked. Two of 16 sessions in the first campaign's
  streaming arm wrote loops of single calls without having seen an error. With this
  recording that is 2 sessions in 32.
- One launch, one unit per arm, 16 sessions, one model, one workload.

Details: [`results/modal_h100_record/RESULTS.md`](../results/modal_h100_record/RESULTS.md).
What was fixed beforehand: [`cloud/PREREG_RECORD.md`](../cloud/PREREG_RECORD.md) and
[its addendum](../cloud/PREREG_RECORD_ADDENDUM.md).

## Adaptive limits

The replay above left two numbers set by hand, for one engine: spec-ptc's 16 calls in
flight (128 was better on the H100) and its 120,000 characters of speculative prompts.
So the client was changed to set both itself, from what the engine reports:

- A governor for the window. A session's window starts at 16 and moves between 1 and
  256, four times a second, on the engine's `/metrics`. Up while calls wait and the
  engine shows no queue. Down on a standing queue, a preemption or a full KV cache.
- A KV pool for long prompts, in place of the character budget. A call goes if it fits
  into 88% of the engine's KV cache less what everything else holds.
- The scout continues past a test that cannot leave its loop.

They are [patches 5 and 6](../integrations/spec-ptc-fork/README.md), off by default. The
rule for "done" was fixed before anything was built: within 2% of the best hand-tuned
client in session time on the 10 recorded sessions, with root streams at most 5% longer
than the stock client's. Two runs, each written down beforehand: an engine with room (the
H100) and one without (a T4 started with `--max-num-seqs 16`, so that its batch holds 16
sequences).

### On the H100

The 10 sessions, and an 11th that makes four calls on prompts of 36,000 tokens. One
launch, one unit per arm after a warm-up unit that was discarded, every unit exact:

| arm | the 10: session time | relative to stock | all 11 | relative to stock | root streams, the 10, relative to stock |
|---|---|---|---|---|---|
| stock spec-ptc | 1,547 s | - | 2,186 s | - | - |
| scout, 128 in flight: the best hand-tuned client | 1,333 s | 0.86 | 1,968 s | 0.90 | 1.012 |
| adaptive limits | 1,314 s | **0.85** | 1,775 s | **0.81** | 1.014 |
| adaptive limits, and the scout continues past tests | 1,269 s | **0.82** | 1,728 s | **0.79** | 1.012 |
| control: 128 in flight, no budget for long prompts | 1,350 s | 0.87 | 1,643 s | 0.75 | 1.026 |

### On a T4 with 16 batch slots

Eight of the sessions, as a load. One unit per arm:

| arm | session time | relative to stock | root's first token, 90th percentile | root turns that waited over 5 s | the engine's queue, mean / largest |
|---|---|---|---|---|---|
| stock spec-ptc, 16 in flight | 2,590 s | - | 2.5 s | 2 of 81 | 8 / 38 |
| scout, 128 in flight | 2,541 s | 0.98 | 9.4 s | 21 of 81 | 60 / 357 |
| adaptive limits | 2,580 s | **1.00** | 1.8 s | 2 of 81 | 3 / 34 |

### What the two runs showed

- The rule is met. On the H100 the adaptive client took 0.985 of the hand-tuned client's
  session time, and its root streams were 1.4% longer than the stock client's. All 21
  predictions of that run held, and 12 of the 13 on the T4.
- It ties the hand-tuned number on each engine and beats it on neither. On the H100 its
  windows opened to 256 on every large burst. The largest loop took 33 s where 128 takes
  54 s, and the other nine sessions together were 0.6% slower. On the T4 the windows
  closed: 189 cuts, none above 38.
- The prediction that failed: on the T4 I had said the adaptive window would be within 1%
  of a fixed 128 in session time. The fixed 128 was 1.6% faster. A long queue gives the
  sub-calls the engine first. The roots pay with their first token, and session time does
  not count that.
- The KV pool beat the character budget and lost to no budget. The turn with the four
  long calls took 537 s with the stock client, 354 s with the pool, and 184 s with no
  budget at all. There the engine's KV cache went to 96% and nothing was preempted; the
  other ten sessions paid 1.3%. Over all 11 sessions the control with no budget was the
  fastest client. My dry run had the engine preempt 103 times in that case.
- Past the test, the loop that tests each result went from 58 s to 14 s after its
  stream. No call was launched that the program did not make.
- Three things these limits do not see, each measured:
  - A client that is itself the limit. Calls of 3 tokens come back at about 210 a second
    whether 90 or 220 are in flight, with 13 to 48 requests running in an engine that has
    room for 256. Two sessions opened to 256 at once: 170 to 180 calls a second, each
    after 1.7 to 2.0 s. Since the runs the windows of one process share one ceiling
    (patch 7), so the two would have 128 each. No run has measured that.
  - The prefill of long prompts in front of a root's turn. One root turn began 0.2 s
    after the long calls left and waited 2.7 s for its first token (4.4 s with no
    budget).
  - A queue behind one long prompt. The governor reads it as a standing queue. All 4 of
    its cuts on the H100 were that.

Caveats for the 0.85:

- One unit per arm. A replay repeats within 1–2%, and the margin against the hand-tuned
  client is that size.
- Two engines, one model each, one workload. The T4's 16 batch slots are a server flag,
  and its sessions were recorded on the H100.
- The adaptive arm differs from the hand-tuned one in three things: the window, the
  pool, and batches sent in chunks of 32. The runs cannot tell the third from the first.
- A first launch was stopped after 16 minutes. My budget for it was wrong, and its
  warm-up unit showed the governor widening a window from 16 to 256 on a cold engine's
  unchanged numbers. That was fixed before any measured unit of an adaptive arm.
- No bets. Every call in these sessions is certain to be used.

Details: [`results/modal_govern/RESULTS.md`](../results/modal_govern/RESULTS.md).
What was fixed beforehand: [`cloud/PREREG_GOVERN.md`](../cloud/PREREG_GOVERN.md) and
[its addendum](../cloud/PREREG_GOVERN_ADDENDUM.md).

## Bugs found

In the projects this one builds on:

| in | what |
|---|---|
| rlms 0.1.3 | Every `llm_query_batched` after a session's first loses its first prompts (16 or 4 of 20 here). They come back as the string `Error: llm() call failed - Event loop is closed`, which the model's code then counts as a label: 30% of one unit's batched prompts. A local test reproduces it (`cloud/tests/test_replay.py`) |
| rlms 0.1.3 | A batch runs 16 prompts at a time, a constant that `RLM()` cannot set. The LM handler listens with a backlog of 5: at 128 threads, 76 of 2,000 calls were one to three seconds late |
| rlms 0.1.3 | Its last answer call, made when a session runs out of turns, is not streamed and has no length limit: one took 321 s |
| spec-ptc `9b78b7d` | The shadow thread dies on a peek whose call takes a list (`shadow.py:314`). The runaway guard counts launching as a statement's computing (`shadow.py:273`). A module imported in an earlier turn stops the shadow at its first use (`shadow.py:52`) |
| spec-ptc `9b78b7d` | Next to its cap of 16 calls it has a character budget: at most 120,000 characters of speculative prompts in flight per session (`speculation.py:353`). The number is fixed, and a bit over a third of what the H100 took at once without slowing anyone |
| spec-ptc's campaign | With its `--max-model-len 8192`, 12 of 24 task runs failed, 11 of them on context overflow |
| vLLM 0.32 | `num_requests_waiting` counts what the scheduler holds. With about 500 calls in flight at the client it read 0, and about 30 were running: the others stood between the client and the engine's batch. A prompt of 36,000 tokens holds everything sent after it for about 1.5 s |

In this project:

| in | what |
|---|---|
| the first H100 write-up | Four statements were wrong or incomplete, among them that rlms sends a batch all at once. They are [corrected in place](../results/modal_h100_rlm/RESULTS.md#corrections-november-10) |
| the first replay | Its 0.72 was mostly a bug's ([above](#after-fixing-rlms)) |
| the recording | It ran without a fixed hash seed, so two sessions that print Python sets could not be rebuilt. And its pre-registration expected the scout to gain on loops of batches, which the stock client already launches whole |
| the governor | It took a sample for new when the client had read again. A cold engine spent two seconds in one step, its numbers stood still, and a window went from 16 to 256 on them. Found by a warm-up unit; the launch was stopped and the rule fixed before any measured unit |
| the dry runs | The fake engine was twice as fast as the T4, so the first launch's budget would have ended before the arm it was for. And it preempts when its cache is full, where the H100 took four long prompts at 96% without preempting |

## Limitations

- The runs are small: 8 tasks, one model, one workload, concurrency 8, an eager server.
  OOLONG is label-then-aggregate; other workloads may hold the conditions and early
  exits that this one does not. The first replay's gain was a bug's, and the replay that
  says so has 10 sessions.
- The adaptive limits watch the engine. They were measured on two engines with one unit
  per arm. They do not see the prefill of long prompts in front of a root's turn, and
  the one bound they have for a client that is itself the limit was added after the runs
  and has local tests only.
- Two things were not put to a test, and they are where these results are thinnest.
  - Several clients on one engine, with a load that changes. Every H100 run had 8
    sessions from one client process, and the engine was never the limit. On each engine
    one fixed window was right; a load that changes is where an adaptive window could
    beat a fixed one, and that is not measured.
  - A second workload. "spec-ptc placed no bet" is measured on OOLONG, with one model.
- Also not done: a GPU run of the per-process ceiling, a live run with the patched client
  as a fourth arm, limits that watch the prefill of long prompts, bets across turns, and
  a server with CUDA graphs.
