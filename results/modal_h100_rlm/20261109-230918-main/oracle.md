# Sub-call time and its serialisation, `nospec` arm (measured, with one model)

Per-request floor of the engine in this run: 18.1 ms per call (the smallest in 1 batches of 50 calls or more).

Tool share: sub-call wall time over task wall time. Oracle: the same calls if every group with no dependency on another started together. Serialisation: the difference, the share of the session spent on calls waiting for unrelated calls.

| conc | finished tasks | sub-calls (single calls) | dependencies found | tool share | oracle | serialisation, pooled | per task p50 |
|---|---|---|---|---|---|---|---|
| 8 | 7 | 5908 (326) | 0 | 0.592 | 0.392 | 0.200 | 0.000 |

## By task

| unit | task | wall s | root stream s | sub-calls (single) | groups | deepest chain | sub-call time s | oracle s | serialisation share |
|---|---|---|---|---|---|---|---|---|---|
| nospec_c8_r1 | trec132k-17000232 | 128.8 | 127.3 | 0 (0) | 0 | 0 | 0.0 | 0.0 | 0.000 |
| nospec_c8_r1 | trec132k-17000241 | 120.4 | 62.1 | 3182 (0) | 1 | 1 | 57.5 | 57.5 | 0.000 |
| nospec_c8_r1 | trec132k-17000222 | 548.0 | 150.5 | 1922 (322) | 481 | 1 | 373.5 | 36.5 | 0.615 |
| nospec_c8_r1 | trec132k-17000237 | 623.8 | 57.6 | 4 (4) | 4 | 1 | 565.9 | 565.9 | 0.000 |
| nospec_c8_r1 | pairs32k-20 | 93.2 | 92.7 | 0 (0) | 0 | 0 | 0.0 | 0.0 | 0.000 |
| nospec_c8_r1 | pairs32k-1 | 93.4 | 72.8 | 400 (0) | 39 | 1 | 12.9 | 7.2 | 0.060 |
| nospec_c8_r1 | pairs32k-15 | 112.8 | 97.8 | 400 (0) | 39 | 1 | 8.6 | 7.2 | 0.012 |
