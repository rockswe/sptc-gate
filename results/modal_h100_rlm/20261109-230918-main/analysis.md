# RLM campaign analysis (measured)

## Time budget of a finished task

Pooled shares of task wall time. Stream: the root's completions. After: from the end of each stream until that turn's code has run. Other: everything else (prompt building, REPL start, the final-answer call).

| arm | conc | finished / tasks | wall p50 s | turns | stream | after | other | root output tokens p50 | sub-calls p50 (max) | sub-call time p50 s (nospec) |
|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 8 | 7 / 8 | 120.4 | 9.9 | 0.384 | 0.613 | 0.003 | 1964 | 400 (3182) | 12.86 |
| stream | 8 | 14 / 16 | 220.0 | 9.9 | 0.714 | 0.277 | 0.009 | 2607 | 787 (3201) | - |

## Sub-call work

From each task's usage summary: sub-calls the engine received (speculative ones that were never claimed included), their prompt and output tokens, and the sub-calls' share of all output tokens (root plus sub-calls).

| arm | conc | sub-calls p50 | prompt tokens p50 | output tokens p50 | share of output tokens |
|---|---|---|---|---|---|
| nospec | 8 | 400 | 60763 | 2946 | 0.780 |
| stream | 8 | 787 | 58096 | 6593 | 0.826 |

## Root stalls

Gaps between the root's deltas. A stall is a gap above 4 times its stream's median gap and above 200 ms; stall share is the time lost in stalls over the root's total stream time.

| arm | conc | gap p50 ms | gap p99 ms | gap max ms | stalls per task | stall share |
|---|---|---|---|---|---|---|
| nospec | 8 | 34.9 | 48.5 | 2846 | 6.9 | 0.063 |
| stream | 8 | 45.8 | 58.2 | 3370 | 3.1 | 0.028 |

## What speculation did

| arm | conc | dispatched (peek / shadow) | hits | misses | evicted | shadow stops |
|---|---|---|---|---|---|---|
| stream | 8 | 12337 (0 / 12337) | 12337 | 1882 | 0 | 3x KeyError: 'Error: llm() call failed - Event loop is closed'; 1x ShadowAborted: ; 1x RuntimeError: result of non-speculatable tool 'rlm_query_bat; 1x NameError: name 'user_label_counts' is not defined |

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
| stream | 8 | 24 | 3431 | 82 s (3) | 91 s (1) | 2499 s (6) | 650 s (9) | 20 s (4) | 89 s (1) |

The longest waits:

| unit | task | turn | waited s (shadow wait) | launched (in stream) | head start s | hits / misses | cause | shadow stop |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r2 | pairs32k-20 (failed) | 10 | 1071.2 (600.0) | 787 (14) | 11.9 | 787 / 0 | serial launches | - |
| stream_c8_r2 | pairs32k-20 (failed) | 6 | 550.4 (550.4) | 40 (1) | 1.7 | 40 / 0 | serial launches | - |
| stream_c8_r1 | trec132k-17000222 (failed) | 7 | 397.8 (397.8) | 160 (1) | 1.5 | 160 / 0 | serial launches | - |
| stream_c8_r1 | trec132k-17000222 (failed) | 11 | 392.4 (392.4) | 160 (2) | 5.5 | 160 / 0 | serial launches | - |
| stream_c8_r2 | trec132k-17000237 | 4 | 304.4 (304.0) | 3188 (3188) | 4.0 | 3188 / 0 | burst over the cap | - |
| stream_c8_r2 | pairs32k-1 | 4 | 102.2 (102.1) | 787 (787) | 3.8 | 787 / 0 | burst over the cap | - |
| stream_c8_r1 | trec132k-17000237 | 9 | 91.0 (85.7) | 1886 (20) | 0.1 | 1886 / 268 | partly speculated | ShadowAborted:  |
| stream_c8_r2 | trec132k-17000241 | 11 | 88.7 (0.0) | 0 (0) | - | 0 / 0 | not on the bus | RuntimeError: result of non-speculatable tool 'rlm |
| stream_c8_r2 | trec132k-17000222 | 3 | 83.3 (83.3) | 160 (160) | 3.4 | 160 / 0 | burst over the cap | - |
| stream_c8_r1 | pairs32k-16 | 4 | 77.9 (77.8) | 787 (787) | 2.7 | 787 / 0 | burst over the cap | - |
| stream_c8_r1 | trec132k-17000237 | 8 | 52.2 (52.0) | 1027 (20) | 0.1 | 1027 / 0 | serial launches | - |
| stream_c8_r2 | pairs32k-15 | 6 | 51.7 (0.0) | 0 (0) | - | 0 / 40 | not speculated | - |
| stream_c8_r2 | pairs32k-20 (failed) | 9 | 35.4 (35.4) | 28 (5) | 8.4 | 28 / 0 | serial launches | - |
| stream_c8_r2 | trec132k-17000222 | 9 | 28.9 (28.8) | 160 (160) | 1.4 | 160 / 0 | burst over the cap | - |

## Noise floor

Typical multiplicative difference in task wall time (the root mean square of the log ratio, as a factor). Same arm: one task's repeat 1 against its repeat 2. Between arms: the same task and repeat.

| conc | same arm, repeat 1 vs 2 (pairs) | stream vs nospec: mean, spread (pairs) | fanout vs nospec | stream vs fanout |
|---|---|---|---|---|
| 8 | x1.94 (6) | 1.312, x2.12 (6) | -, x- (0) | -, x- (0) |

## By task

| task | nospec: runs, wall p50 s, after share, sub-calls p50, score | fanout | stream |
|---|---|---|---|
| pairs32k-1 | 1, 93.4, 0.214, 400, 0.68 | 0, -, -, -, - | 2, 163.3, 0.403, 1180, 0.98 |
| pairs32k-15 | 1, 112.8, 0.128, 400, 0.08 | 0, -, -, -, - | 2, 162.4, 0.205, 414, 0.28 |
| pairs32k-16 | 0, -, -, -, - | 0, -, -, -, - | 2, 215.4, 0.220, 787, 0.23 |
| pairs32k-20 | 1, 93.2, 0.000, 0, 0.23 | 0, -, -, -, - | 1, 147.6, 0.161, 1554, 0.16 |
| trec132k-17000222 | 1, 548.0, 0.724, 1922, 0.00 | 0, -, -, -, - | 1, 288.2, 0.394, 322, 0.00 |
| trec132k-17000232 | 1, 128.8, 0.000, 0, 1.00 | 0, -, -, -, - | 2, 187.6, 0.000, 6, 1.00 |
| trec132k-17000237 | 1, 623.8, 0.907, 4, 1.00 | 0, -, -, -, - | 2, 377.6, 0.594, 3195, 0.00 |
| trec132k-17000241 | 1, 120.4, 0.478, 3182, 0.00 | 0, -, -, -, - | 2, 424.3, 0.105, 0, 0.00 |

## Warm-up waves

One streamed request with n concurrent short-output requests next to it. Wall time of the wave and the stream's longest token gap, first pass and second.

| n | prompts | pass 1: wall s, longest gap ms | pass 2: wall s, longest gap ms |
|---|---|---|---|
| 1 | short | 4.95, 602 | 2.23, 50 |
| 2 | short | 2.55, 530 | 2.13, 48 |
| 4 | short | 3.23, 615 | 2.17, 49 |
| 8 | short | 2.78, 59 | 2.21, 54 |
| 16 | short | 3.48, 670 | 2.15, 53 |
| 32 | short | 3.29, 832 | 2.65, 534 |
| 64 | short | 3.01, 686 | 2.12, 70 |
| 128 | short | 3.09, 783 | 2.31, 74 |
| 1 | long | 2.23, 64 | 2.06, 47 |
| 4 | long | 2.30, 142 | 2.15, 96 |
| 16 | long | 2.77, 144 | 2.71, 143 |

## Failed tasks

- nospec, concurrency 8: 1x BadRequestError: Error code: 400 - This model's maximum context length
- stream, concurrency 8: 1x TimeoutExceededError: Timeout exceeded after iteration 11: 910.4s of 9; 1x TimeoutExceededError: Timeout exceeded after iteration 10: 1827.5s of 
