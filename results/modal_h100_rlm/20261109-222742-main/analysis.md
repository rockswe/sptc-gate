# RLM campaign analysis (measured)

## Time budget of a finished task

Pooled shares of task wall time. Stream: the root's completions. After: from the end of each stream until that turn's code has run. Other: everything else (prompt building, REPL start, the final-answer call).

| arm | conc | finished / tasks | wall p50 s | turns | stream | after | other | root output tokens p50 | sub-calls p50 (max) | sub-call time p50 s (nospec) |
|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 8 | 2 / 8 | 171.5 | 11.5 | 0.814 | 0.183 | 0.003 | 2357 | 1590 (3179) | 31.20 |
| fanout | 8 | 6 / 8 | 205.6 | 7.2 | 0.424 | 0.574 | 0.002 | 1806 | 787 (3202) | - |
| stream | 8 | 4 / 8 | 122.3 | 7.5 | 0.903 | 0.093 | 0.004 | 1994 | 796 (807) | - |

## Sub-call work

From each task's usage summary: sub-calls the engine received (speculative ones that were never claimed included), their prompt and output tokens, and the sub-calls' share of all output tokens (root plus sub-calls).

| arm | conc | sub-calls p50 | prompt tokens p50 | output tokens p50 | share of output tokens |
|---|---|---|---|---|---|
| nospec | 8 | 1596 | 130166 | 5946 | 0.716 |
| fanout | 8 | 797 | 47064 | 7360 | 0.873 |
| stream | 8 | 420 | 37996 | 1234 | 0.387 |

## Root stalls

Gaps between the root's deltas. A stall is a gap above 4 times its stream's median gap and above 200 ms; stall share is the time lost in stalls over the root's total stream time.

| arm | conc | gap p50 ms | gap p99 ms | gap max ms | stalls per task | stall share |
|---|---|---|---|---|---|---|
| nospec | 8 | 52.6 | 59.6 | 1826 | 1.0 | 0.013 |
| fanout | 8 | 53.0 | 62.7 | 3837 | 0.3 | 0.007 |
| stream | 8 | 53.1 | 60.9 | 176 | 0.0 | 0.000 |

## What speculation did

| arm | conc | dispatched (peek / shadow) | hits | misses | evicted | shadow stops |
|---|---|---|---|---|---|---|
| fanout | 8 | 3914 (0 / 3914) | 3914 | 1682 | 0 | 3x RuntimeError: result of non-speculatable tool 'rlm_query_bat; 1x ShadowAborted: ; 1x RuntimeError: result of non-speculatable tool 'rlm_query' us; 1x AttributeError: 'set' object has no attribute 'count' |
| stream | 8 | 942 (0 / 942) | 942 | 1573 | 0 | 1x AttributeError: 'set' object has no attribute 'count' |

## Why the speculative arms still waited

Turns that waited at least 1 s after their stream, failed tasks' turns included, and the seconds waited, by cause (from each turn's events):

- not speculated: the real run made the calls itself. The shadow had stopped, its thread had ended, or it never reached them.
- partly speculated: some calls were claimed, some were not.
- serial launches: every call was claimed, but they were launched one after another: the shadow stalls wherever a result is used.
- burst over the cap: more than 16 calls launched at once, so they queued inside spec-ptc.
- still running at stream end: launched together, within the cap.
- not on the bus: no call went through spec-ptc's hooks (`rlm_query*` is never speculated), or the time is plain code.

| arm | conc | turns | seconds waited | not speculated | partly speculated | serial launches | burst over the cap | still running at stream end | not on the bus |
|---|---|---|---|---|---|---|---|---|---|
| fanout | 8 | 9 | 1061 | 0 s (0) | 157 s (1) | 0 s (0) | 173 s (3) | 2 s (1) | 729 s (4) |
| stream | 8 | 5 | 1048 | 30 s (2) | 0 s (0) | 997 s (1) | 12 s (1) | 9 s (1) | 0 s (0) |

The longest waits:

| unit | task | turn | waited s (shadow wait) | launched (in stream) | head start s | hits / misses | cause | shadow stop |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | trec132k-17000222 (failed) | 6 | 997.1 (600.0) | 100 (1) | 0.1 | 100 / 0 | serial launches | - |
| fanout_c8_r1 | trec132k-17000222 | 4 | 458.2 (0.0) | 0 (0) | - | 0 / 0 | not on the bus | RuntimeError: result of non-speculatable tool 'rlm |
| fanout_c8_r1 | pairs32k-20 (failed) | 7 | 206.1 (0.0) | 0 (0) | - | 0 / 0 | not on the bus | RuntimeError: result of non-speculatable tool 'rlm |
| fanout_c8_r1 | trec132k-17000237 | 7 | 157.3 (0.0) | 1500 (0) | -0.0 | 1500 / 1682 | partly speculated | ShadowAborted:  |
| fanout_c8_r1 | pairs32k-15 | 3 | 139.2 (0.0) | 787 (0) | -0.0 | 787 / 0 | burst over the cap | - |
| fanout_c8_r1 | pairs32k-20 (failed) | 6 | 49.9 (0.0) | 0 (0) | - | 0 / 0 | not on the bus | RuntimeError: result of non-speculatable tool 'rlm |
| fanout_c8_r1 | pairs32k-16 | 5 | 18.6 (0.0) | 787 (0) | -0.0 | 787 / 0 | burst over the cap | - |
| stream_c8_r1 | pairs32k-20 | 6 | 15.8 (0.0) | 0 (0) | - | 0 / 786 | not speculated | - |
| fanout_c8_r1 | pairs32k-1 | 9 | 14.8 (0.0) | 787 (0) | -0.0 | 787 / 0 | burst over the cap | - |
| stream_c8_r1 | pairs32k-1 | 4 | 14.3 (0.0) | 0 (0) | - | 0 / 787 | not speculated | - |
| fanout_c8_r1 | pairs32k-20 (failed) | 4 | 14.3 (0.0) | 0 (0) | - | 0 / 0 | not on the bus | RuntimeError: result of non-speculatable tool 'rlm |
| stream_c8_r1 | pairs32k-15 | 6 | 11.7 (11.6) | 787 (787) | 2.4 | 787 / 0 | burst over the cap | - |
| stream_c8_r1 | trec132k-17000222 (failed) | 5 | 9.4 (9.4) | 1 (1) | 1.3 | 1 / 0 | still running at stream end | - |
| fanout_c8_r1 | trec132k-17000232 | 3 | 2.2 (0.0) | 13 (0) | -0.0 | 13 / 0 | still running at stream end | - |

## Noise floor

Typical multiplicative difference in task wall time (the root mean square of the log ratio, as a factor). Same arm: one task's repeat 1 against its repeat 2. Between arms: the same task and repeat.

| conc | same arm, repeat 1 vs 2 (pairs) | stream vs nospec: mean, spread (pairs) | fanout vs nospec | stream vs fanout |
|---|---|---|---|---|
| 8 | x- (0) | -, x- (0) | 2.654, x2.65 (1) | 0.813, x1.41 (3) |

## By task

| task | nospec: runs, wall p50 s, after share, sub-calls p50, score | fanout | stream |
|---|---|---|---|
| pairs32k-1 | 0, -, -, -, - | 1, 127.1, 0.120, 807, 0.98 | 1, 101.8, 0.140, 807, 0.70 |
| pairs32k-15 | 0, -, -, -, - | 1, 247.9, 0.562, 787, 0.10 | 1, 145.0, 0.081, 787, 0.47 |
| pairs32k-16 | 0, -, -, -, - | 1, 164.3, 0.114, 787, 0.40 | 0, -, -, -, - |
| pairs32k-20 | 0, -, -, -, - | 0, -, -, -, - | 1, 142.9, 0.111, 806, 0.07 |
| trec132k-17000222 | 1, 203.3, 0.308, 3179, 0.00 | 1, 539.6, 0.849, 0, 0.00 | 0, -, -, -, - |
| trec132k-17000232 | 0, -, -, -, - | 1, 54.8, 0.040, 13, 1.00 | 1, 62.7, 0.003, 13, 1.00 |
| trec132k-17000237 | 0, -, -, -, - | 1, 246.9, 0.640, 3202, 0.00 | 0, -, -, -, - |
| trec132k-17000241 | 1, 139.7, 0.000, 0, 0.00 | 0, -, -, -, - | 0, -, -, -, - |

## Warm-up waves

One streamed request with n concurrent short-output requests next to it. Wall time of the wave and the stream's longest token gap, first pass and second.

| n | prompts | pass 1: wall s, longest gap ms | pass 2: wall s, longest gap ms |
|---|---|---|---|
| 1 | short | 5.55, 687 | 2.42, 53 |
| 2 | short | 2.94, 613 | 2.43, 53 |
| 4 | short | 3.60, 688 | 3.11, 714 |
| 8 | short | 3.04, 57 | 2.43, 56 |
| 16 | short | 3.78, 740 | 2.48, 60 |
| 32 | short | 2.46, 67 | 2.47, 168 |
| 64 | short | 2.51, 81 | 2.48, 68 |
| 128 | short | 3.35, 842 | 2.57, 84 |
| 1 | long | 2.43, 62 | 2.42, 54 |
| 4 | long | 2.58, 140 | 2.48, 91 |
| 16 | long | 3.60, 677 | 2.93, 144 |

## Failed tasks

- nospec, concurrency 8: 6x BadRequestError: Error code: 400 - This model's maximum context length
- fanout, concurrency 8: 2x BadRequestError: Error code: 400 - This model's maximum context length
- stream, concurrency 8: 3x BadRequestError: Error code: 400 - This model's maximum context length; 1x TimeoutExceededError: Timeout exceeded after iteration 6: 1099.6s of 9
