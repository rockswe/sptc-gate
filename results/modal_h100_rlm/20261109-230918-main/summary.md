# RLM campaign summary (measured)

Task wall ratios are geometric means over tasks paired by (task, repeat), against the same concurrency's nospec (or fanout) arm, with a bootstrap 95% CI over pairs. Root TPOT is per root completion (ms per token after the first). Engine columns come from vLLM's /metrics: queue share is the share of samples with a request waiting.

| arm | conc | units | tasks (err) | score | task wall p50 s | vs nospec | vs fanout | root TTFT p50 s | root TPOT p50 / p99 ms | queue | max wait | preempt/unit | KV peak | running mean / max | dispatch / hit / miss / evict | host CPU max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nospec | 8 | 1 | 8 (1) | 0.373 | 120.4 | - | - | 0.116 | 36.2 / 65.5 | 0.00 | 1 | 0.0 | 0.46 | 2.6 / 56 | 0 / 0 / 0 / 0 | 0.06 |
| stream | 8 | 2 | 16 (2) | 0.320 | 220.0 | 1.312 [0.808, 2.417] n=6 | - | 0.145 | 46.8 / 62.9 | 0.00 | 5 | 0.0 | 0.26 | 5.6 / 73 | 12337 / 12337 / 1882 / 0 | 0.05 |

## Where the time goes

Shares of a finished task's wall time. Root stream: the root's completions, from request to last token. After the stream: from the end of each stream until that turn's code has run (the shadow's wait plus the real run). In nospec that is all the tool time. In stream it is what speculation did not hide, and so the most that more speculation within a turn could still save. The median is over tasks, with a bootstrap 95% CI; pooled is total time over total time.

| arm | conc | finished tasks | turns per task | root stream share p50 (pooled) | after-stream share p50 [CI] | pooled |
|---|---|---|---|---|---|---|
| nospec | 8 | 7 | 9.9 | 0.780 (0.384) | 0.214 [0.000, 0.724] | 0.613 |
| stream | 8 | 14 | 9.9 | 0.768 (0.714) | 0.224 [0.076, 0.418] | 0.277 |

**Gate: GO.** Rule (cloud/GATE.md): go if the stream arm's median after-stream share is at least 0.15 at concurrency 8 or 4, in a cell with at least 12 finished tasks.
- concurrency 8: share 0.224, 14 finished tasks, valid
