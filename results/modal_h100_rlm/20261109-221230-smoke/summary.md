# RLM campaign summary (measured)

Task wall ratios are geometric means over tasks paired by (task, repeat), against the same concurrency's nospec (or fanout) arm, with a bootstrap 95% CI over pairs. Root TPOT is per root completion (ms per token after the first). Engine columns come from vLLM's /metrics: queue share is the share of samples with a request waiting.

| arm | conc | units | tasks (err) | score | task wall p50 s | vs nospec | vs fanout | root TTFT p50 s | root TPOT p50 / p99 ms | queue | max wait | preempt/unit | KV peak | running mean / max | dispatch / hit / miss / evict | host CPU max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 1 | 1 | 1 (0) | 1.000 | 118.0 | - | - | 0.138 | 54.4 / 54.8 | 0.00 | 0 | 0.0 | 0.03 | 1.0 / 1 | 0 / 0 / 0 / 0 | 0.06 |
| fanout | 1 | 1 | 1 (1) | 0.000 | - | - | - | 0.129 | 52.3 / 53.9 | 0.00 | 0 | 0.0 | 0.05 | 1.0 / 1 | 0 / 0 / 0 / 0 | 0.05 |
| stream | 1 | 1 | 1 (0) | 1.000 | 147.0 | 1.245 [1.245, 1.245] n=1 | - | 0.727 | 54.3 / 90.2 | 0.00 | 0 | 0.0 | 0.04 | 1.0 / 14 | 13 / 13 / 0 / 0 | 0.05 |

## Where the time goes

Shares of a finished task's wall time. Root stream: the root's completions, from request to last token. After the stream: from the end of each stream until that turn's code has run (the shadow's wait plus the real run). In nospec that is all the tool time. In stream it is what speculation did not hide, and so the most that more speculation within a turn could still save. The median is over tasks, with a bootstrap 95% CI; pooled is total time over total time.

| arm | conc | finished tasks | turns per task | root stream share p50 (pooled) | after-stream share p50 [CI] | pooled |
|---|---|---|---|---|---|---|
| nospec | 1 | 1 | 7.0 | 0.987 (0.987) | 0.010 [0.010, 0.010] | 0.010 |
| fanout | 1 | 0 | - | - (-) | - [-, -] | - |
| stream | 1 | 1 | 9.0 | 0.993 (0.993) | 0.000 [0.000, 0.000] | 0.000 |

**Gate: UNRESOLVED.** Rule (cloud/GATE.md): go if the stream arm's median after-stream share is at least 0.15 at concurrency 8 or 4, in a cell with at least 12 finished tasks.
- concurrency 1: share 0.000, 1 finished tasks, not valid
