# RLM campaign summary (measured)

Task wall ratios are geometric means over tasks paired by (task, repeat), against the same concurrency's nospec (or fanout) arm, with a bootstrap 95% CI over pairs. Root TPOT is per root completion (ms per token after the first). Engine columns come from vLLM's /metrics: queue share is the share of samples with a request waiting.

| arm | conc | units | tasks (err) | score | task wall p50 s | vs nospec | vs fanout | root TTFT p50 s | root TPOT p50 / p99 ms | queue | max wait | preempt/unit | KV peak | running mean / max | dispatch / hit / miss / evict | host CPU max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 8 | 1 | 8 (6) | 0.000 | 171.5 | - | 0.377 [0.377, 0.377] n=1 | 0.158 | 52.8 / 67.8 | 0.00 | 0 | 0.0 | 0.15 | 8.6 / 35 | 0 / 0 / 0 / 0 | 0.06 |
| fanout | 8 | 1 | 8 (2) | 0.310 | 205.6 | 2.654 [2.654, 2.654] n=1 | - | 0.155 | 52.5 / 83.6 | 0.00 | 0 | 0.0 | 0.13 | 12.0 / 57 | 3914 / 3914 / 1682 / 0 | 0.06 |
| stream | 8 | 1 | 8 (4) | 0.279 | 122.3 | - | 0.813 [0.585, 1.144] n=3 | 0.155 | 53.3 / 56.4 | 0.00 | 0 | 0.0 | 0.12 | 1.8 / 30 | 942 / 942 / 1573 / 0 | 0.05 |

## Where the time goes

Shares of a finished task's wall time. Root stream: the root's completions, from request to last token. After the stream: from the end of each stream until that turn's code has run (the shadow's wait plus the real run). In nospec that is all the tool time. In stream it is what speculation did not hide, and so the most that more speculation within a turn could still save. The median is over tasks, with a bootstrap 95% CI; pooled is total time over total time.

| arm | conc | finished tasks | turns per task | root stream share p50 (pooled) | after-stream share p50 [CI] | pooled |
|---|---|---|---|---|---|---|
| nospec | 8 | 2 | 11.5 | 0.843 (0.814) | 0.154 [0.000, 0.308] | 0.183 |
| fanout | 8 | 6 | 7.2 | 0.656 (0.424) | 0.341 [0.077, 0.745] | 0.574 |
| stream | 8 | 4 | 7.5 | 0.899 (0.903) | 0.096 [0.003, 0.140] | 0.093 |

**Gate: UNRESOLVED.** Rule (cloud/GATE.md): go if the stream arm's median after-stream share is at least 0.15 at concurrency 8 or 4, in a cell with at least 12 finished tasks.
- concurrency 8: share 0.096, 4 finished tasks, not valid
