# Sub-call time and its serialisation, `nospec` arm (measured, with one model)

Per-request floor of the engine in this run: 20.0 ms per call (the smallest in 0 batches of 50 calls or more; none found, so the default is used).

Tool share: sub-call wall time over task wall time. Oracle: the same calls if every group with no dependency on another started together. Serialisation: the difference, the share of the session spent on calls waiting for unrelated calls.

| conc | finished tasks | sub-calls (single calls) | dependencies found | tool share | oracle | serialisation, pooled | per task p50 |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 13 (0) | 0 | 0.010 | 0.010 | 0.000 | 0.000 |

## By task

| unit | task | wall s | root stream s | sub-calls (single) | groups | deepest chain | sub-call time s | oracle s | serialisation share |
|---|---|---|---|---|---|---|---|---|---|
| nospec_c1_r1 | trec132k-17000232 | 118.0 | 116.5 | 13 (0) | 1 | 1 | 1.1 | 1.1 | 0.000 |
