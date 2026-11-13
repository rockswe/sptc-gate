# The governor on a TensorRT-LLM server (client patches 8 and 9)

`cloud/trtllm_probe_app.py`, November 13, 2026. One NVIDIA L4 on Modal, TensorRT-LLM
1.4.0rc3 in its own container (`nvcr.io/nvidia/tensorrt-llm/release:1.4.0rc3`), PyTorch
backend, Qwen3-1.7B, `max_batch_size` 64, the default scheduler (`GUARANTEED_NO_EVICT`).
Five launches. Each has its `summary.json`, the server's log, and, from the third on, the
metrics text before and after. The last has every sample (`samples.json`).

This is a check of what the client reads, not a benchmark: one unit per arm, no repeats,
one model, calls of 32 tokens.

## The launches

| launch | client | what happened |
|---|---|---|
| `20261113-130917` | patch 8 | the server did not start: it spawns its engine with MPI, and in Modal's sandbox UCX finds no transport between the two |
| `20261113-133044` | patch 8 | with the engine in the server's process (`TLLM_WORKER_USE_SINGLE_PROCESS=1`) the engine came up, and the server stopped: its 8 frontends need the engine in a process of its own |
| `20261113-140922` | patch 8 | one frontend: the server ran, and `/prometheus/metrics` had no gauge of the engine. The client refused every read, warned once, and its window stayed at 16 |
| `20261113-143508` | patch 8 | the engine in its own process again, MPI over shared memory and TCP (`OMPI_MCA_pml=ob1`, `OMPI_MCA_btl=self,sm,tcp`): the gauges are there |
| `20261113-144800` | patch 9 | the same server |

## A burst of 300 short calls

| launch | client | at the window of 16 | governed | the window |
|---|---|---|---|---|
| `20261113-140922` | patch 8, no gauges | 11.7 s | 11.9 s | 16 throughout |
| `20261113-143508` | patch 8 | 11.4 s | 13.9 s | cut from 16 to 1 between 3.0 and 8.8 s, then up to 141 |
| `20261113-144800` | patch 9 | 12.9 s | 11.6 s | one cut, from 16 to 11, then up to 49 |

- Patch 8 made the burst slower. It counted the requests in the engine's active set
  and not in its step as waiting. At its cuts it read 8, 4, 2, 2 and 2 waiting, next to
  11, 11, 6, 3 and 1 running, on an engine whose queue was empty.
- With patch 9 the governed burst was not slower. It was 1.2 s faster in that launch,
  and the window of 16 differed by 1.5 s between the two launches: no speed-up is
  shown.
- No call failed in any burst.

## What the engine's gauges say

- They are written when a request ends. Four calls of 256 tokens, 4.8 s, 87 reads: the
  gauges changed twice, while the engine wrote 211 tokens a second. In the bursts they
  changed 33 and 51 times in about 12 s.
- A sample is of a step in which a request ended. An idle engine reads 4 running and 3
  scheduled after four calls, and 7 and 6 after the bursts.
- The queue reads above 0 on an engine with room: in 103 of 115 samples at the window
  of 16 (up to 12), and in 62 of 104 in the governed burst (up to 8). Most samples of
  the burst at 16 read 15 running, 3 scheduled and 12 in the queue: the calls of a
  window come back together, and their successors have arrived and are not in a step
  yet.
- The KV cache reads 0 on an idle engine, after 600 calls: blocks kept for reuse are
  not counted as used. It read at most 1.8% in a burst (4,635 blocks of 32 tokens).
- A step took 28 ms with four calls and 55 to 69 ms in the bursts. No request was
  paused.
- The server was ready after 146 to 245 s.

## Limits

- One unit per arm and no repeats: the two bursts at 16 differ by 13%.
- Short calls on a small model, far below the engine's KV cache: nothing here shows
  the window on an engine under pressure.
- The burst of the last launch was read ten times a second by the run itself, in both
  arms, and the bursts of the launch before were not.
- The settings that made the server run are Modal's (MPI over shared memory and TCP,
  one frontend). The one that matters elsewhere is the engine in a process of its own.
