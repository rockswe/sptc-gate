# vLLM 0.32 priority scheduling, read from the source

The obvious objection to the sptc plugin is: "why not send speculative requests at low
priority with `--scheduling-policy priority`?" This note records what that option does in
vLLM 0.32.0. Every claim cites vLLM 0.32.0's source, read from a checkout kept next to
this repository (`vllm_src_v0.32.0/`, as in `integrations/README.md`; paths below are
relative to it). Nothing here was run on a GPU; it is read from the code.

## Summary

- Priority only reorders the waiting queue. Lower value runs first; ties go to the
  earlier arrival.
- It never preempts on arrival. A high-priority request that does not fit waits. It
  does not evict running low-priority work.
- Running requests are not reordered. The per-step token budget goes to running
  requests in the order they were admitted, whatever their priority. A low-priority
  prefill admitted earlier keeps its chunks ahead of a high-priority request admitted
  later.
- Priority matters for preemption victims. When a *running* request cannot get KV
  blocks, the victim is the running request with the largest `(priority, arrival_time)`.
  The victim is requeued for recompute, not dropped.
- No admission control. A low-priority request is admitted whenever there is token
  budget, a `max_num_seqs` slot and KV space. Nothing keeps it out of a busy batch.
- So, before the waiting queue builds up or KV runs out, priority scheduling behaves like
  FCFS. That is the regime of the T4 runs so far (no preemptions in either server log at
  8 agents; `../kaggle_t4/sptc_out/vllm.log`).

## 1. How a request carries its priority

| what | where |
|---|---|
| server flag `--scheduling-policy {fcfs,priority}`, default `fcfs` | `vllm/engine/arg_utils.py:1744-1746`, `vllm/config/scheduler.py:21,159-165` |
| OpenAI API body field `priority: int`, default 0, "lower means earlier handling" | completions: `vllm/entrypoints/openai/completion/protocol.py:136-145`; chat: `vllm/entrypoints/openai/chat_completion/protocol.py:388-397` |
| HTTP header `X-Vllm-Priority` overrides the body field | `vllm/entrypoints/generate/base/serving.py:42,258-269` |
| passed to the engine | `vllm/entrypoints/openai/completion/serving.py:209`, `vllm/entrypoints/openai/chat_completion/serving.py:395`, `vllm/v1/engine/input_processor.py:383,549` |
| stored on the scheduler's request | `vllm/v1/request.py:74,86`; `arrival_time` defaults to `time.time()` at input processing (`vllm/v1/engine/input_processor.py:414-415`, `vllm/v1/request.py:98`) |

- The bench sends it as a top-level body field: `extra_body={"priority": 1}`
  (`kaggle/vllm_bench.py`, tag scheme `priority`).
- Non-zero priority under FCFS. The field description says it "will raise an error if
  the served model does not use priority scheduling". No such check exists in the vendored
  request path (`input_processor.process_inputs`, the two serving modules, `async_llm`).
  It may live in a file that is not vendored. Under FCFS the value is ignored
  (`FCFSRequestQueue` is a plain deque, `vllm/v1/core/sched/request_queue.py:75-100`).
  The bench only sends a non-zero priority to the priority server, so this does not matter.
- The sptc plugin refuses to start under priority scheduling
  (`integrations/sptc_vllm/scheduler.py:54`). The two cannot be combined as shipped.

## 2. Ordering

- `Request.__lt__` compares `(priority, arrival_time, request_id)`, smaller first
  (`vllm/v1/request.py:357-367`).
- With `policy == "priority"`, both `waiting` and `kv_holding_waiting` are
  `PriorityRequestQueue` heaps (`vllm/v1/core/sched/scheduler.py:217-227`,
  `vllm/v1/core/sched/request_queue.py:131-199,200-207`).
- "Prepending" to a heap is just a push (`request_queue.py:159-172`). So a preempted
  request, or one skipped this step, re-enters at its priority position, not at the front.
- `self.running` is a plain list. It is appended to on admission
  (`scheduler.py:231,1345`) and never sorted by priority anywhere in `scheduler.py`.

## 3. One scheduling step (`Scheduler.schedule`)

1. Running loop (`scheduler.py:659-866`). It walks `self.running` in list order
   (admission order) while token budget remains. Each request gets
   `min(remaining tokens, token_budget, ...)` tokens. The long-prefill cap is off by
   default (`long_prefill_token_threshold = 0`, `vllm/config/scheduler.py:79`).
2. KV shortage in the running loop (`scheduler.py:780-844`). If `allocate_slots`
   fails for running request R:
   - priority policy: victim = `max(self.running, key=(priority, arrival_time))`
     (`scheduler.py:796-800`). This is the largest priority value, newest first. If the
     victim was already scheduled in this step, its tokens, blocks and encoder budget are
     given back, and the loop index is fixed up (`scheduler.py:808-832`).
   - FCFS: victim = `self.running[-1]`, the last admitted (`scheduler.py:801-834`).
   - Either way the victim is requeued with `num_computed_tokens = 0` (recompute) by
     `_preempt_request` (`scheduler.py:1571-1614`).
   - If the victim is R itself, R is not scheduled (`scheduler.py:841-846`).
3. Waiting loop runs only if nothing was preempted in this step
   (`scheduler.py:900`). It pops from the heap in priority order while there is budget and
   `len(running) < max_num_active_reqs` (`scheduler.py:912-924`).
   - If the head request cannot get KV blocks, the loop **breaks**
     (`scheduler.py:1275-1281`). It does not preempt running requests, and nothing
     behind the head is tried. A high-priority waiting request blocks lower-priority
     waiting ones; it never displaces running ones.
4. Chunked prefill (on by default). A request admitted with only part of its prompt
   continues in later steps' running loops, in admission order (step 1). A low-priority
   prompt admitted before a high-priority one keeps first claim on the token budget until
   its prefill ends. Priority does not cap or reorder chunks.

The vendored test `tests/v1/core/test_scheduler.py:3712-3808`
(`test_priority_scheduling_preemption`) shows the preemption rule. The high-priority
request is admitted while space is still free. Only later, when it needs a block, is the
low-priority running request preempted.

## 4. What this means for speculative work

| property the plugin is meant to give | plugin (`sptc_vllm`) | stock vLLM, spec at low priority |
|---|---|---|
| speculative work runs only on spare capacity | bets gated by free window, no non-bet waiting, KV reserve | no gate: any request is admitted if it fits |
| a bet is refused at once when the server is busy | `sptc_bet_rejected` | waits in the queue, then runs (and is cancelled by the client at turn end) |
| dropped first under KV pressure | dropped, not recomputed (`sptc_bet_dropped`) | preempted first, then **recomputed** when space frees |
| does not slow the critical path inside a step | early/bet prefill shares a 512-token per-step allowance | none: running spec prefill takes budget ahead of a later-admitted root |
| normal work queued behind speculative work | bets sorted behind all non-bets | waiting heap puts priority-0 work first (this part is equivalent) |

**Prediction from the semantics alone** (before any simulation). Priority scheduling can
only help once requests actually wait: the `max_num_seqs` cap, a full token budget, or KV
exhaustion. On the T4 at up to 8 agents nothing waited for long, so priority should match
FCFS there. The simulator quantifies this for higher loads in `predictions.md`.

## 5. Simulator mapping (`sptc_sim/server.py`, policy `vllm-priority`)

| vLLM 0.32 | simulator |
|---|---|
| waiting heap by `(priority, arrival_time, request_id)` | `_order`: `(spec, arrival, rid)`, with root and normal both sent as 0 and spec as 1 |
| running list in admission order | `running` is not sorted for this policy |
| victim `max(running, key=(priority, arrival_time))`, scheduled tokens given back | `_victim()` plus the give-back in `_schedule` |
| victim is the request being scheduled: `break`, then `if new_blocks is None: break` (`scheduler.py:841-848`), so no later running request is scheduled that step | `_schedule` breaks out of the running loop. Before a fix on this branch it went on to later running requests. Under `fcfs` that never differed (the victim is the last running request); under `vllm-priority` it could. The predictions have 0 preemptions at every load, so none of them change |
| waiting head that does not fit: `break`, no preemption | same code path as `fcfs` |
| waiting loop skipped in a step that preempted | same as all policies (`if preempted: return batch`) |
| no API to change a request's priority | `promote()` is a no-op for this policy |

**Differences that remain:**
- The simulator's FCFS sorts `running` by arrival rather than admission order. They differ
  only after a preempted request is readmitted. This was left unchanged so earlier results
  stay reproducible.
- The old `priority` policy is kept as an *idealized* strict priority. It has three
  priority classes (root above normal above spec), sorts `running` so the token budget
  follows class too, and supports promotion. vLLM does none of these. Use
  `vllm-priority` to model the real option.
- vLLM admits a waiting request only if its whole prompt fits in free KV blocks
  (`scheduler_reserve_full_isl`, default on: `vllm/config/scheduler.py:190`,
  `scheduler.py:1270`, `vllm/v1/core/kv_cache_manager.py:522-533`). The simulator checks
  only the first chunk. This applies to every policy, and the sweep's prompts are under
  100 tokens, so it does not matter here.
- Not modeled, in either policy: the `X-Vllm-Priority` header, LoRA and encoder budgets,
  async-scheduling placeholders, DP throttling.

## 6. The bench arm (`kaggle/vllm_bench.py`, arms `prio/*`)

| | how |
|---|---|
| server | `vllm serve ... --scheduling-policy priority` (`SERVERS["priority"]`) |
| spec-ptc speculative dispatches (`early`) and decoys (`bet`) | body field `"priority": 1` (`tag_body("priority", ...)`, `SPEC_PRIORITY`) |
| root stream, normal calls, a re-run after a refusal | no field: priority 0 |
| claimed speculations | stay at priority 1: there is no API to raise it |

- The plugin arms (`plugin/*`) run with FCFS: the plugin refuses priority scheduling, so
  "plugin plus priority" is not an arm.
- `tests` in `kaggle/tests/test_bench.py` check that the field reaches the server for each
  kind of call, and that a waiting priority-0 request is admitted before an earlier
  priority-1 one (on the fake server, which imitates the waiting heap only).
