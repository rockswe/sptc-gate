# RLM campaign analysis (measured)

## Time budget of a finished task

Pooled shares of task wall time. Stream: the root's completions. After: from the end of each stream until that turn's code has run. Other: everything else (prompt building, REPL start, the final-answer call).

| arm | conc | finished / tasks | wall p50 s | turns | stream | after | other | root output tokens p50 | sub-calls p50 (max) | sub-call time p50 s (nospec) |
|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 1 | 1 / 1 | 118.0 | 7.0 | 0.987 | 0.010 | 0.003 | 2123 | 13 (13) | 1.14 |
| fanout | 1 | 0 / 1 | - | - | - | - | - | - | - (-) | - |
| stream | 1 | 1 / 1 | 147.0 | 9.0 | 0.993 | 0.000 | 0.006 | 2312 | 13 (13) | - |

## Sub-call work

From each task's usage summary: sub-calls the engine received (speculative ones that were never claimed included), their prompt and output tokens, and the sub-calls' share of all output tokens (root plus sub-calls).

| arm | conc | sub-calls p50 | prompt tokens p50 | output tokens p50 | share of output tokens |
|---|---|---|---|---|---|
| nospec | 1 | 13 | 797 | 39 | 0.018 |
| fanout | 1 | - | - | - | - |
| stream | 1 | 13 | 797 | 43 | 0.018 |

## Root stalls

Gaps between the root's deltas. A stall is a gap above 4 times its stream's median gap and above 200 ms; stall share is the time lost in stalls over the root's total stream time.

| arm | conc | gap p50 ms | gap p99 ms | gap max ms | stalls per task | stall share |
|---|---|---|---|---|---|---|
| nospec | 1 | 53.6 | 60.8 | 65 | 0.0 | 0.000 |
| fanout | 1 | - | - | - | - | - |
| stream | 1 | 54.8 | 63.5 | 5256 | 3.0 | 0.056 |

## What speculation did

| arm | conc | dispatched (peek / shadow) | hits | misses | evicted | shadow stops |
|---|---|---|---|---|---|---|
| fanout | 1 | 0 (0 / 0) | 0 | 0 | 0 | - |
| stream | 1 | 13 (0 / 13) | 13 | 0 | 0 | - |

## Noise floor

Typical multiplicative difference in task wall time (the root mean square of the log ratio, as a factor). Same arm: one task's repeat 1 against its repeat 2. Between arms: the same task and repeat.

| conc | same arm, repeat 1 vs 2 (pairs) | stream vs nospec: mean, spread (pairs) | fanout vs nospec | stream vs fanout |
|---|---|---|---|---|
| 1 | x- (0) | 1.245, x1.25 (1) | -, x- (0) | -, x- (0) |

## By task

| task | nospec: runs, wall p50 s, after share, sub-calls p50, score | fanout | stream |
|---|---|---|---|
| trec132k-17000232 | 1, 118.0, 0.010, 13, 1.00 | 0, -, -, -, - | 1, 147.0, 0.000, 13, 1.00 |

## Failed tasks

- fanout, concurrency 1: 1x BadRequestError: Error code: 400 - This model's maximum context length
