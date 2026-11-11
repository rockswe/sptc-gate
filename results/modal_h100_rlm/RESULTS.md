# RLM campaign on a Modal H100, November 9–10, 2026 (measured)

Real RLM runs on OOLONG with spec-ptc, on one vLLM engine. This is the first run of
spec-ptc's **streaming** mode on real model-written RLM code: rlms 0.1.3 does not stream,
so spec-ptc's own campaign measured the fan-out mode only.

**The question** (`cloud/GATE.md`, fixed before the main run): after spec-ptc's streaming
mode, how much of a session is left for more speculation to hide, and what is it made of?

## In short

- Gate: go. In the `stream` arm at concurrency 8, the median task still spent 22% of
  its time after the root had finished writing a turn (14 finished tasks, bootstrap 95% CI
  8–42%; the rule's bar was 15%).
- What is left is not behind conditions. Of 3,431 s the stream arm waited after its
  streams: 73% was independent calls launched one after another, 19% was spec-ptc's cap
  of 16 calls in flight, and 8% was speculation that stopped, crashed or was bypassed.
- spec-ptc made no bets. 17,206 speculative calls, none evicted, none from its peek
  path, which is the only place it launches before a statement closes.
- Sub-calls did not slow the root's tokens. Within one server launch the root's median
  token gap was 52.7, 53.0 and 53.2 ms with no speculation, fan-out and streaming.
- No speed-up can be claimed from this design. The same arm's two repeats of one task
  differed by a typical factor of 1.9.
- The repository's server flags break the harness. With `--max-model-len 8192`, 12 of
  24 task runs failed, 11 of them on context overflow (Corrections 4).

## Corrections (November 10)

Four statements below were wrong or incomplete. The first three were found while building
the replay of these runs, the fourth while writing the README. The sections keep their
text; each carries a pointer here.

1. rlms runs a batch 16 prompts at a time. It does not send its whole list at once.
   `LMHandler.batch_max_concurrent` is 16 and `RLM()` has no argument for it. spec-ptc's
   pool is also 16. So both arms had the same width on a large fan-out, and section 3's
   comparison (3,188 speculated calls still running after 304 s, a batch of 3,182 done in
   57.5 s without speculation) is not a like-for-like one:
   - the 3,182 calls answered with about 7 tokens each (their recorded answers);
   - the 3,188 finished at 10.4 calls a second with 16 in flight: 1.5 s a call, about 30
     engine steps of 48 ms. Their answers were not recorded; the rate says they were
     several times longer.

   "The cap can make speculation slower than no speculation" does not follow from that.
   What stands: 16 in flight is far below what the engine takes, with or without
   speculation.
2. The per-request floor of section 6 (17.5–22 ms per call) is that width of 16: 16
   calls in flight, each about 0.3 s (some 8 engine steps).
3. rlms 0.1.3 loses prompts of every batch after a session's first. Each
   `llm_query_batched` runs in a new event loop (`asyncio.run`), but the client keeps one
   async HTTP client, whose idle connections belong to the previous, closed loop. The
   first prompts of the next batch are handed those connections and come back as the
   string `Error: llm() call failed - Event loop is closed`. It reproduces locally
   against a fake server (`cloud/tests/test_replay.py`). The model's code then counts
   those strings as labels.
   - In the rerun's `nospec` unit, 2,356 of the 7,938 batched prompts of the 7 finished
     tasks came back as that string (30%). Three tasks sent batches of 20 in a loop: 16 or
     4 of every batch after the first failed, 49–50% of their prompts. The failed eighth
     task lost 387 of 787 the same way.
   - A failed prompt returns at once. So a loop of batches took about half the time the
     work would have taken, and the `nospec` arm's sub-call seconds (sections 2 and 5)
     are low by that much on those tasks.
   - One root saw the strings in its output and switched to single calls in a loop
     ("since `llm_query_batched` is failing", its turn 7). The 319-call loop of section 5
     is that reaction.
   - A speculated call is not affected: spec-ptc sends a batch's prompts as single calls.
     A batch the real run sends itself is. The strings are in the REPL output of 3 of the
     16 `stream` task runs.
   - spec-ptc's own campaign pins the same rlms (`uv.lock`: 0.1.3), so its baseline arm
     runs the same code path.

   The gate's verdict does not depend on it: it is the `stream` arm's share. Any ratio of
   an arm against `nospec` on these tasks does.
4. 11 of the first main run's 12 failed task runs died of context overflow, not 12.
   "In short" said 12. The twelfth was a timeout in a serial loop, as section 7's table
   has it. "In short" is reworded.

## Setup

- Engine: one H100 80 GB on Modal, vLLM 0.32.0, `Qwen/Qwen3-30B-A3B-Instruct-2507`.
  Server flags from spec-ptc's campaign (`benchmark/experiments/model_sweep.py`):
  `--enforce-eager --gpu-memory-utilization 0.92 --tensor-parallel-size 1`, kernel
  warm-ups off, `--max-model-len 8192`. The rerun changes the last one to 65,536.
- Client: spec-ptc at `9b78b7d`, unmodified. rlms 0.1.3. spec-ptc's own campaign
  runner, tasks and scoring (`load_tasks(4, 4, seed=7)`: 4 OOLONG trec-coarse tasks at
  132k tokens, 4 OOLONG-Pairs tasks at 32k).
- Arms: `nospec` (stock rlms), `fanout` (spec-ptc's shadow pass over each finished
  block, the mode of its published numbers), `stream` (the root's tokens feed spec-ptc
  while they arrive). Roots stream in every arm, so their timing is logged the same way.
- A unit is one arm at one concurrency: the 8 tasks, 8 at a time.

| run | window | what finished | GPU time |
|---|---|---|---|
| `20261109-221230-smoke` | 8,192 | 1 TREC task per arm, concurrency 1 | 9 min |
| `20261109-222742-main` | 8,192 | `nospec`, `fanout`, `stream`, concurrency 8, repeat 1; then stopped | 39 min |
| `20261109-230918-main` | 65,536 | `nospec` repeat 1; `stream` repeats 1 and 2, concurrency 8 | 86 min |

- GPU time: 134 GPU-minutes.
- Integrity: the hashes are of the files as they were at run time; the gate documents and
  campaign scripts have since been edited (list formatting, and planning notes and costs
  in comments), so they hash differently.
  Every launch recorded the sha256 of `GATE.md` (`f5182144…`) before its
  first unit, and from the rerun on also `GATE_ADDENDUM.md` (`13ec7df5…`), next to the
  hashes of the campaign code and of spec-ptc's sources (`campaign.jsonl`, `begin`).
- Files here: per run, `summary.md` (the campaign's own tables and the gate),
  `analysis.md` and `oracle.md` (`cloud/analyze.py`, `cloud/oracle.py`), `campaign.jsonl`,
  `server.json`. Raw events and trajectories are not in the repository: sub-call prompts
  contain OOLONG text. The call-shape census is in `results/census_rlm_qwen/`.

### Deviations, in the order they were made

1. Roots stream in every arm; thread-safe REPLs (`cloud/README.md`). Before any run.
2. Warm-up before the first unit, after the smoke run (section 6).
3. Window 65,536 for the rerun, after the first main run's failures (section 7). The
   reason and what I had seen by then are in `cloud/GATE_ADDENDUM.md`, written before the
   rerun started.
4. On resuming the rerun: `nospec` and `stream` only, and a cap on root replies.
   - The rerun's first unit took 31 minutes, so the budget could not reach the stream arm
     in the planned order. `fanout` was dropped.
   - One root had written for 30 minutes without stopping (rlms sets no `max_tokens`; the
     large window lets a root that repeats itself run until the window is full). From the
     second launch on, a root reply is cut after 3,000 deltas. The `nospec` unit ran
     without the cap, and its one failed task is that runaway.
5. Three server launches for the rerun's three units. Their hosts differ: the root's
   median token gap was 33, 44 and 48 ms. Wall times are not comparable between these
   units. Shares are computed inside one unit.

## 1. The gate

Rule: go if the `stream` arm's median after-stream share is at least 0.15 at concurrency 8
or 4, in a cell with at least 12 finished tasks.

After-stream share: the part of a task's wall time between the end of each root stream
and the moment that turn's code has run (the shadow's wait plus the real run).

| window | arm | finished / run | after-stream share, median [95% CI] | pooled |
|---|---|---|---|---|
| 65,536 | `stream` | 14 / 16 | **0.224** [0.076, 0.418] | 0.277 |
| 65,536 | `nospec` | 7 / 8 | 0.214 [0.000, 0.724] | 0.613 |
| 8,192 | `stream` | 4 / 8 | 0.096 [0.003, 0.140] | 0.093 |
| 8,192 | `fanout` | 6 / 8 | 0.341 [0.077, 0.745] | 0.574 |
| 8,192 | `nospec` | 2 / 8 | 0.154 [0.000, 0.308] | 0.183 |

- Verdict: go, on the 65,536-token cell. The CI's lower end is below the bar.
- Concurrency 4 did not run (budget). The rule needs only one valid cell for a go.
- The 8,192-token cells are not valid: too few tasks finished.
- The two failed stream tasks waited the longest (about 790 s and 1,660 s after their
  streams) and are not in the median. Section 3 counts them.

## 2. Where the time goes

Window 65,536, concurrency 8, finished tasks, pooled shares of task wall time:

| arm | root streams | after the streams | sub-calls per task, median (max) | sub-calls' share of all output tokens |
|---|---|---|---|---|
| `nospec` | 0.384 | 0.613 | 400 (3,182) | 0.78 |
| `stream` | 0.714 | 0.277 | 787 (3,201) | 0.83 |

- Sub-calls are most of the work when the window lets the harness run: 61% of session
  time without speculation, and about 80% of all output tokens. (The `nospec` row is low
  on three tasks: half their batched prompts failed at once. See Corrections 3.)
- The tasks differ widely. One TREC task needs 13 sub-calls about one user's
  questions (1 s of a 2-minute session). Others label all 3,182 lines.
- Trajectories differ between arms and repeats, so the two rows are not a
  before-and-after. See section 9.

## 3. Why the stream arm still waited

Every turn of the stream arm that waited at least 1 s after its stream, failed tasks
included (window 65,536, two units, 24 turns, 3,431 s). Causes come from each turn's
speculation events (`analyze.py`, `turn_cause`).

| cause | seconds | share | turns |
|---|---|---|---|
| serial launches: every call claimed, but launched one after another | 2,499 | 73% | 6 |
| burst over the cap: more than 16 calls launched at once | 650 | 19% | 9 |
| partly speculated: some calls claimed, some not | 91 | 3% | 1 |
| not on the bus: `rlm_query_batched`, which spec-ptc never speculates | 89 | 3% | 1 |
| not speculated: the shadow had stopped or its thread had ended | 82 | 2% | 3 |
| still running when the stream ended | 20 | 1% | 4 |

**Serial launches.** The model writes a loop, uses each result inside it, and so the
shadow stalls at every call. The calls do not depend on each other. Two shapes from the
recorded code (the model's own code, shortened):

```python
def classify_all_questions(questions, batch_size=20):      # 160 calls, about 2.5 s each
    results = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i:i + batch_size]
        prompt = create_classification_prompt(batch)
        batch_results = llm_query(prompt).strip().split('\n')   # the result is used here
        results.extend(batch_results)
    return results
```

```python
for i in range(0, total_questions, batch_size):            # 51 batches of 20
    prompts = [f"Classify ... Question: {q}" for q in questions[i:i+batch_size]]
    results = llm_query_batched(prompts)
    for r in results:
        label_counts[r] += 1                                # hashing r needs its value
```

- The first ran for 398 s and again for 392 s in one task, which then timed out.
- spec-ptc's loop peek does not cover either: the prompt is assigned in the body, the
  call sits in a helper, or other calls follow in the body (`streaming.py:541`).
- A call's head start over the end of its stream was 0.1–12 s. The census agrees: a
  median of 43 tokens follow a call's closing parenthesis.

**Burst over the cap.** (Corrected: see Corrections 1. rlms' own `llm_query_batched` is
16 wide too, and the two bullets below compare calls of different lengths.) The model's
own `llm_query_batched` sends its whole list at once. spec-ptc launches the same calls
through 16 threads, and the real run then waits for them.
- 3,188 calls launched during one stream were still running 304 s after it. Without
  speculation, a batch of 3,182 took 57.5 s (another unit and launch).
- Batches of 787 waited 10 to 102 s after their streams; unspeculated ones took 13–16 s.
- So on large fan-outs the cap can make speculation slower than no speculation.

**Speculation that stopped.**
- A crash. In streaming mode the shadow thread dies when it peeks a loop whose call
  takes a list (`shadow.py:314`: a `Counter` keyed by the arguments). It happened 5 times
  in the three finished stream units at concurrency 8. The turn then runs with no
  speculation: 787 calls missed in one of them.
- `rlm_query` and `rlm_query_batched` are registered as not speculatable
  (`demo/rlm.py:48`). At depth 1 they are plain `llm_query` calls. Using their result
  stops the shadow for the turn.
- Model-code errors in the shadow (a `KeyError`, a `NameError`, the watchdog).

The 8,192-token round shows the same causes (`20261109-222742-main/analysis.md`): the
stream arm waited 1,048 s, 997 s of it in one serial loop of 100 calls; the fan-out arm
waited 1,061 s, 729 s of it on `rlm_query_batched`.

## 4. What speculation did

All speculative units of the three runs:

| dispatched | from peeks | claimed | evicted | calls the real run made itself |
|---|---|---|---|---|
| 17,206 | 0 | 17,206 | 0 | 5,137 |

- No waste. Not one speculative call went unused.
- No peeks. Every dispatch came from the shadow executing a closed statement.
  spec-ptc's loop unrolling, its only launch before a statement closes and its only bet,
  never applied to this code.
- About one call in four was not speculated (5,137 of the 22,343 that went through
  spec-ptc's hooks), for the reasons in section 3. Calls through `rlm_query_batched` are
  not in these counts.

## 5. How much of the sub-call time is serialisation

`cloud/oracle.py` on the `nospec` unit's recorded sub-calls (window 65,536, 7 finished
tasks, 5,908 sub-calls). It asks what the same calls would have cost if every call with
no dependency on another had started together, with no call starting before its turn's
stream had ended. A wave cannot be faster than its slowest call, or than the engine's
measured rate of 18.1 ms per call.

| sub-call share of session time | with independent calls together | difference |
|---|---|---|
| 0.592 | 0.392 | **0.200** |

- No dependency between sub-calls of one turn was found among 5,908. The check is by
  text (a response's first 48 characters in a later prompt) and misses dependencies
  through short answers.
- One task carries the difference: a loop of 319 calls of about 1 s each took 343 s
  and would take about 6 s together.
- What stays is mostly one task's four calls, each over a 100,000-character chunk and
  about 140 s long, one per turn. Only a guess across turns could overlap them: the same
  prompt on `chunks[1]`, `chunks[2]`, `chunks[3]`. That would be a bet. Each such call
  holds about 36,000 tokens, a quarter of this engine's KV cache.

## 6. What sub-calls cost the engine

**The root's tokens.** Gaps between the root's deltas, per unit:

| launch | unit | median gap ms | p99 ms |
|---|---|---|---|
| first main run | `nospec_c8_r1` | 52.7 | 59.9 |
| | `fanout_c8_r1` | 53.0 | 62.7 |
| | `stream_c8_r1` | 53.2 | 60.9 |
| rerun, launch 1 | `nospec_c8_r1` | 33.1 | 42.8 |
| rerun, launch 2 | `stream_c8_r1` | 44.3 | 55.9 |
| rerun, launch 3 | `stream_c8_r2` | 47.6 | 59.6 |

- Inside one launch the arms are equal. Thousands of concurrent short sub-calls did
  not move the root's token gap.
- Between launches it moves by 60%. The server runs eager, so a decode step is mostly
  Python on the host's CPU, and Modal's hosts differ.
- Long prompts do stall the root. With sub-calls of about 36,000 tokens (rerun), the
  longest gaps were 2.8–3.4 s in both arms, and stalls took 6% (`nospec`) and 3%
  (`stream`) of the root's stream time.

**A cold engine.** With `--enforce-eager`, vLLM 0.32 skips its kernel warm-up and compiles
kernels when a batch shape first appears.
- In the smoke run the first burst of 13 concurrent sub-calls stalled the root for 8.4 s
  and the calls took 6–9 s. The same burst took 1.1 s later in that run.
- The campaign now warms up first: a 48-token stream next to 1 to 128 short calls, twice.
  - First pass: most waves stalled the stream for 0.5–0.8 s, and a wave took 2.2–5.6 s.
  - Second pass: the longest gap was about 50 ms in most waves (0.5–0.7 s in one wave
    per launch), and a wave took 2.1–3.1 s whatever its size.
- spec-ptc's campaign runs all its no-speculation units before its speculation units on
  one launch. Without a warm-up, the no-speculation arm meets the cold engine.

**A floor per request.** Batches of 1,000 to 3,200 short calls ran at 17.5–22 ms per call
whatever their size, about 50 calls a second. Whether the engine or the request path sets
that floor was not measured. (It is the request path: rlms keeps 16 of a batch in flight.
See Corrections 2.)

## 7. The repository's 8,192-token window

| unit (first main run) | failed | why |
|---|---|---|
| `nospec_c8_r1` | 6 of 8 | the root's prompt passed 8,192 tokens |
| `fanout_c8_r1` | 2 of 8 | the same |
| `stream_c8_r1` | 4 of 8 | the same three times; one timeout |

- rlms tells the model that up to about 20,000 characters of REPL output come back to it
  and that a sub-call can take about 500,000 characters. OOLONG's lines run at about 2.4
  characters per token, so one full REPL output is about 8,000 tokens.
- With the 65,536-token window: 1 of 8 (`nospec`, the runaway root) and 2 of 16
  (`stream`, both timeouts in serial loops).
- In the smoke run (concurrency 1) the one task that finished in `nospec` spent 1.0% of
  its 118 s in sub-calls: 13 calls, 1.1 s.

## 8. Call shapes in the recorded code

`results/census_rlm_qwen/` (static, `experiments/census.py`): 32 task runs, 313 code
blocks, 56 sub-call sites.

| in a loop | in a branch arm | under a condition on a sub-call's result | literal arguments |
|---|---|---|---|
| 48% | 7% | 0% | 0% |

- Nothing to bet on inside a turn: no call waits on a condition over a pending result.
- A literal-only speculator would start none of these calls.
- The earlier RLM sample was 13 calls from another model (`results/census_rlm/`).

## 9. Noise

Task wall time, same arm and same task, repeat 1 against repeat 2 (`stream`, 6 pairs):
they differ by a typical factor of **1.94**. Between `stream` and `nospec` on the same
task the factor is 2.12 (6 pairs, mean ratio 1.31, different launches).

- The root samples at the model's default temperature, and a task can take 13 sub-calls
  or 3,000 depending on what the root decides to write.
- A speed-up of 1.0–1.2× is far below this with 8 tasks and a handful of repeats.

## 10. Defects found in spec-ptc at `9b78b7d`

| where | what |
|---|---|
| `src/engine/shadow.py:314` | A peek whose plan has a list argument raises `TypeError` and ends the shadow thread. Fixed in the `sptc-hints` fork, with a test that fails on the old code |
| `src/engine/streaming.py:541` | Loop unrolling never applied to real code: the prompt is built in the body, the call is in a helper or a `try`, or any call follows in the body |
| `demo/rlm.py:48` | `rlm_query` and `rlm_query_batched` are never speculated, though at depth 1 they are plain sub-calls; using their result stops the shadow |
| `demo/rlm.py:20` | 16 calls in flight, whatever the engine can take; a claimed batch waits for it |
| `demo/rlm.py:86`, `cloud/rlm_stream.py` | The real run waits up to 600 s for the shadow. Twice a turn waited the full 600 s |
| `src/engine/shadow.py:52` (`snapshot_ns`) | A module the model imported in an earlier turn cannot be copied into the shadow, so it becomes an opaque value, and the first `re.` of a later turn stops the shadow (3 times in the replay of 10 sessions, November 10) |

And in rlms 0.1.3, which both arms run on (see Corrections):

| where | what |
|---|---|
| `rlm/core/lm_handler.py`, `_handle_batched` | Every batch after a session's first loses its first prompts (16 or 4 of 20 here) to `Event loop is closed`: a new event loop per batch, one async client for all |
| `rlm/core/lm_handler.py`, `LMHandler.__init__` | `batch_max_concurrent` is 16, and `RLM()` cannot set it |
| `rlm/core/lm_handler.py`, `ThreadingLMServer` | Listens with a backlog of 5. Measured on Modal, 2,000 single calls: 1 a second late at 16 threads, 76 one to three seconds late at 128, none with a backlog of 1,024 |
| `rlm/core/comms_utils.py`, `send_lm_request` | A failed connection to the handler returns `Error: Request failed: ...` as the call's answer |

## What it changes

- More speculation is worth building, and it is not bets. The time is in calls that
  are certain to run: independent calls in loops, and fan-outs wider than the cap.
- The cap should follow the engine. Here the engine took 128 concurrent short calls at
  no cost to the root, and a fixed 16 made large fan-outs slower than not speculating.
  With 36,000-token prompts the same engine stalls. That is the load-aware half.
- Bets may matter across turns (section 5), on one task's evidence.

## Limits

- Small: 8 tasks, one model, one H100, concurrency 8 only, 16 stream runs and 8
  `nospec` runs with the large window.
- Not a speed comparison: arms ran on different launches, and trajectories differ.
- An eager server. Decode steps cost 33–53 ms whatever the batch. With CUDA graphs the
  root would be several times faster and the shares would move.
- The window was chosen after seeing the 8,192-token round, for the reason in
  `cloud/GATE_ADDENDUM.md`, and before any number it produced.
- Causes are read from events, by simple rules. Three of the longest waits were
  checked against the code.
- OOLONG is label-then-aggregate. Other workloads may hold conditions and early exits
  that this one does not.
