# Sub-call time and its serialisation, `nospec` arm (measured, with one model)

Per-request floor of the engine in this run: 17.5 ms per call (the smallest in 4 batches of 50 calls or more).

Tool share: sub-call wall time over task wall time. Oracle: the same calls if every group with no dependency on another started together. Serialisation: the difference, the share of the session spent on calls waiting for unrelated calls.

| conc | finished tasks | sub-calls (single calls) | dependencies found | tool share | oracle | serialisation, pooled | per task p50 |
|---|---|---|---|---|---|---|---|
| 8 | 2 | 3179 (0) | 0 | 0.182 | 0.182 | 0.000 | 0.000 |

## By task

| unit | task | wall s | root stream s | sub-calls (single) | groups | deepest chain | sub-call time s | oracle s | serialisation share |
|---|---|---|---|---|---|---|---|---|---|
| nospec_c8_r1 | trec132k-17000241 | 139.7 | 139.3 | 0 (0) | 0 | 0 | 0.0 | 0.0 | 0.000 |
| nospec_c8_r1 | trec132k-17000222 | 203.3 | 139.8 | 3179 (0) | 4 | 1 | 62.4 | 62.4 | 0.000 |
