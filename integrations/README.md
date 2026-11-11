# Speculation-aware scheduler plugins for vLLM v0.32.0 and SGLang v0.5.22

Two plugins, one policy (`sptc_vllm/policy.py`):
- `sptc_vllm` for vLLM v0.32.0, described first below;
- `sptc_sglang` for SGLang v0.5.22, in [its own section](#sglang-sptc_sglang). It differs
  from the vLLM plugin in how the plugin loads, in the request field that carries the tag,
  and in how the prefill allowance protects decoding streams.

The vLLM plugin implements the `agent` policy that the simulator (`sptc_sim/`) found best ([report](../docs/report.md)
sections 3 and 4.2; `sptc_sim/server.py`, policy `agent` with `reject_bets`). The simulator
now also models the plugin as built (`ServerConfig.plugin_semantics`: the gate inside the
waiting loop, the end-of-step re-gate and hold, no promotion; `results/t4_run1_analysis/root_cause.md`).
Measured results are in the top-level `README.md` and `results/kaggle_t4_v3/RESULTS.md` (the
October 19 light-load cost did not reproduce in the second T4 run). vLLM loads it
through its `scheduler_cls` setting, so there is no fork of vLLM. It subclasses vLLM's own
`Scheduler`/`AsyncScheduler` and overrides six narrow hooks, plus a property that observes
vLLM's DP prefill-throttle signal. No block of `schedule()` is copied.

## What it does

A request's class comes from `SamplingParams.extra_args["sptc_class"]`. Clients set it with
the OpenAI API field `vllm_xargs`:

| tag | meaning | treatment |
|---|---|---|
| `"bet"` | speculative call that may never be used (e.g. a literal launch in a branch arm) | admitted only on spare capacity, otherwise rejected at once; dropped first under KV pressure |
| `"early"` | dispatched ahead of the real run, almost surely used (spec-ptc shadow dispatches and loop peeks) | normal admission and preemption; its prefill shares the per-step allowance |
| absent or unknown | normal work | vanilla vLLM FCFS |

1. Bet admission. A waiting bet is admitted only when all three conditions (the gate)
   hold:
   - no non-bet request is waiting (early requests included);
   - one more running sequence still fits in the free window (`len(running) + 1 <= free_window`);
   - KV usage is at most `1 - kv_reserve`, measured before the bet's own allocation (as in
     the simulator).

   The gate runs when vLLM's waiting loop reaches the bet. If it fails, the bet is
   **rejected in the same step**: it is finished as aborted, and the client gets a final
   response with `stop_reason="sptc_bet_rejected"`.

   Every waiting bet that was not admitted and not already rejected is gated again at the
   end of the step, with the end-of-step state. That covers bets the loop never reached
   (token budget, `max_num_seqs`, an allocation failure, a preempting step) and bets vLLM
   skipped for a transient reason (prefill allowance spent, DP prefill throttling, encoder
   prefetch or KV-connector lookup still pending, LoRA slots).
   - Gate fails: rejected now, with the gate's reason.
   - Gate passes: there is spare capacity by the definition above, so the bet stays waiting
     and is re-gated next step, like the simulator, which keeps an accepted bet queued when
     the step budget runs out. After `bet_hold_steps` such steps (default 16) it is rejected
     as `held_too_long`. Not counted: steps where vLLM deferred prefills (DP throttle),
     steps that scheduled no tokens (idle engine iterations of about 1 ms), and steps where
     the bet was skipped for the allowance while another bet's prefill used it.
   - On a step where vLLM deferred prefills, a bet that fails only because non-bet work is
     waiting is held (not counted) instead of rejected: that work may be waiting for the DP
     cadence, not for capacity (a bet that arrives with its real call).
   - Blocked bets (grammar still compiling) are gated the same way but not counted. A
     blocked bet that is already ready (grammar compiled) but was not reached counts like
     any waiting bet. A bet whose grammar failed to compile is left to vLLM, which finishes
     it with an error (`FINISHED_ERROR`), not a rejection.
   - A bet that vLLM admitted into an async KV-connector load (P/D) holds its blocks: it is
     not gated again, also while paused, and it counts toward the free window while it
     loads (counter `bet_kv_load`).
   - While the scheduler is paused, waiting bets are rejected with `paused` (except those
     in an async KV load).
2. Bet dropping. When vLLM must preempt a running request for KV space, bets go first.
   `running` is kept in the order "bets last", so vLLM's FCFS victim `running[-1]` is the
   newest bet that still needs compute. The bet is finished as aborted with
   `stop_reason="sptc_bet_dropped"`; it is not requeued for recompute. Any tokens of the
   dropped bet still in flight under async scheduling are discarded by vLLM's own
   finished-request check.
   - Exception: a bet whose step in flight already reaches `max_tokens` is ordered before
     the other bets. If it is still chosen, vLLM's own requeue is kept: the in-flight tokens
     are delivered and the bet finishes normally instead of losing a finished result. Under
     async scheduling this is read from the output placeholders; under sync scheduling with
     a step in flight (pipeline parallelism) from the in-flight token count.
3. Prefill allowance. Prefill tokens of bet and early requests share an allowance of
   `spec_prefill_budget` tokens per step (default 512, across all such requests). Decodes and
   normal prefills are untouched. A waiting bet or early request that finds the allowance spent
   is skipped, never used as a `break`, so normal work queued behind it still runs. With
   multi-module MTP (prefill lookahead `L > 1`), fewer than `L` tokens left counts as spent:
   vLLM's lookahead rule could cut such a chunk to 0 tokens, and 0 means `break`. A
   budget below `L` is raised to `L` at startup, with a warning.
   - Early work first. vLLM schedules running requests before waiting ones. A running
     bet's prefill chunk therefore leaves the part of the allowance that waiting early
     prefills need (up to what is left), so a long bet cannot hold a waiting early request
     back for its whole prefill. The need is counted before the prefix-cache lookup, so it
     can keep back more than the early requests use; the rest of that step's allowance
     then goes unused rather than to a bet. Nothing is kept while vLLM cannot admit from
     `waiting` (paused, or every sequence slot taken). If a step cut a bet's chunk and the
     early request still was not admitted (its full prompt did not fit in KV, a normal
     request ahead of it did not fit, LoRA limit, ...), nothing is kept again until that
     request starts. A bet then loses at most one step per blocked early request. Before
     this rule, a bet that held the KV the early request needed was cut to 0 tokens on
     every step, and nothing ran again (tests below).

   `prefill_allowance` chooses when the allowance applies:
   - `fixed` (default, the behaviour so far): in every step.
   - `adaptive`: only while a more certain stream is decoding, so there is something to
     protect. A bet's prefill is limited while any non-bet request decodes. An early
     request's prefill is limited only while an untagged request decodes; other early work
     decoding does not count. The running set is scanned at most once per step, and only
     in a step with tagged prefill.
   - `off`: never (same as `spec_prefill_budget: 0`).

   Which one is best is open. In simulation (`results/t4_run1_analysis/allowance_ab.md`), `adaptive`
   stays within about 1% of `fixed`. `off` loses up to 15% session latency on dense models
   under load, but wins 5–9% on a MoE. At heavy load `fixed` keeps the root's worst token
   gaps (ITL p99) 3–7× smaller than `off`. At light load it costs the root: ITL p99 is
   18–34% worse than `off` on the H100 servers, and `adaptive` does not change that. All
   of this is simulated. Measured on the second T4 run (`results/kaggle_t4_v3/RESULTS.md`
   sections 4 and 6): at 1 agent the three modes are indistinguishable, so the default
   stays `fixed`; in smoke test S3, tagging the `early` calls cut a concurrent normal
   stream's longest stall from 892 ms to 468 ms (median over passes).
4. Everything else is vanilla FCFS. With no tagged traffic every hook passes straight
   through. `tests_vllm/test_sptc_differential.py` checks this step by step against stock
   vLLM: the full scheduler output, the queues and KV usage, and every client output, with
   async steps overlapped as on a real server and with prefix caching on.

There is no promotion. vLLM has no API to change a request's class once it is running, and
none is invented here. When a bet that was rejected or dropped turns out to be needed, the
client re-issues it as normal work. The spec-ptc patch below does exactly that.

## Install and launch

```bash
pip install -e integrations --no-deps     # or: export PYTHONPATH=$PWD/integrations
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --scheduler-cls sptc_vllm.scheduler.SptcScheduler \
  --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1, "spec_prefill_budget": 512}}'
```
(`bet_hold_steps` can be added to the same object; see the table below.)

- Which class. `SptcScheduler` reads `scheduler_config.async_scheduling` and builds the
  matching variant: `SptcAsyncScheduler` when async scheduling is on (vLLM's default), the
  sync variant with `--no-async-scheduling`.
  - A plain `Scheduler` subclass under async scheduling would run without
    placeholder accounting, so the plugin refuses that mismatch.
  - Passing `SptcAsyncScheduler` explicitly while async scheduling is off raises an error.
- Python API. `LLM(model=..., scheduler_cls="sptc_vllm.scheduler.SptcScheduler",
  additional_config={"sptc": {...}})`.
- The package must be importable in the engine-core process. It is imported there by
  qualname, so install it or set `PYTHONPATH`.
- Check the log. The engine core logs `sptc scheduler (SptcAsyncScheduler): SptcConfig(...),
  prefill allowance 512 (fixed)` at startup. The plugin logs as `vllm.sptc_vllm.scheduler`;
  before this, its lines were dropped, because vLLM only configures the `vllm` logger.
- Scheduling policy. Only `--scheduling-policy fcfs` (the default) is supported; priority
  raises an error at startup.
- Compile cache. `additional_config` is part of vLLM's compile-cache hash, so changing a
  knob triggers a recompile. Use `--enforce-eager` for quick iterations.
  - It also means each knob setting runs its own compiled kernels, and two compiles need
    not be equally fast. When timing settings against each other, use `--enforce-eager`,
    or launches whose logs show the same `torch_compile_cache/<hash>` directory. Stock
    vLLM launched with the same `--additional-config` shares the plugin's artifact
    (`--scheduler-cls` is not hashed; `results/t4_run1_analysis/root_cause.md`).

| knob (`additional_config["sptc"]`) | default | meaning |
|---|---|---|
| `free_window` | 8 | max running sequences when admitting a bet; 0 rejects every bet. Report section 3 knees: about 8 for 4B at 8k context, about 4 for 30B-A3B. Tune it per deployment. A value `>= max_num_seqs` lets bets take every sequence slot (normal work then waits until a bet ends); it is kept as set, with a startup warning. |
| `kv_reserve` | 0.10 | a bet is admitted only while KV usage is at most `1 - kv_reserve` (`0 <= x < 1`). Checked before the bet's own allocation, as in the simulator: it is an admission threshold, not a cap on how far an admitted bet may grow. A bet that grows into the reserve is the first victim when KV runs out. |
| `spec_prefill_budget` | 512 | prefill tokens per step shared by bet+early; `<= 0` means unlimited |
| `prefill_allowance` | `"fixed"` | when the allowance applies: `"fixed"` every step, `"adaptive"` only while a more certain stream decodes, `"off"` never (rule 3) |
| `bet_hold_steps` | 16 | steps a bet may stay waiting while the gate passes but vLLM does not admit it; then it is rejected as `held_too_long`. `0` rejects every bet that is not admitted in the step it is first gated. |

Unknown knobs or wrong types raise an error at engine start. The allowance is switched off,
with a warning, when chunked prefill is off, and for hybrid "align" (mamba) and multimodal
models. Capping a chunk after vLLM's alignment and encoder planning could break their
invariants, so the plugin does not try.

## Tagging requests (client side)

```python
client.chat.completions.create(model=..., messages=..., stream=True,
                               extra_body={"vllm_xargs": {"sptc_class": "bet"}})   # or "early"
```

```bash
curl localhost:8000/v1/completions -d '{"model": "...", "prompt": "hi", "max_tokens": 16,
  "vllm_xargs": {"sptc_class": "bet"}}'
```

Vanilla vLLM accepts the tag and ignores it. Ollama ignores the unknown field; this was
checked with one 16-token call to `qwen3:1.7b`.

**spec-ptc.** `spec-ptc-sptc-hints.patch` is the diff of the `sptc-hints` branch at
`9a6c7af`, the client of the three T4 runs, against spec-ptc `main` (9b78b7d). Later
client changes (refusal survival, the scout pass, the window) are in `spec-ptc-fork/` and
apply on top of it. This patch makes these changes:
- `VLLMEngine` and the benchmark `SuiteEngine` tag every speculative dispatch (shadow and
  peek) as `early`. Real calls stay untagged. `sptc_tags=False` turns tagging off. The tag
  goes in `vllm_xargs`; set `SPTC_TAG_FIELD=custom_params` for SGLang. The rejection check
  reads vLLM's `stop_reason` or SGLang's `matched_stop`.
- A speculative call that the server rejects or drops raises `SpeculationRejected` inside
  the speculation. A speculation evicted by spec-ptc itself still raises
  `RuntimeError("evicted")`, also when the eviction lands after the last chunk, and is not
  counted as a server rejection (`spec_rejected`, `calls_rejected`).
- A claim of such a speculation re-runs the call for real, untagged, and emits
  `spec_fallback`. Without the patch such a claim would raise the error into the user
  program. The claim sites covered are:
  - sync, async and async-batched claims in `engine/speculation.py`;
  - sync batched claims, where all rejected elements re-run together in one call of the
    batched tool (one batch latency, and never an un-awaited coroutine from an async
    single-prompt twin);
  - the daemon's `resolve`, which answers `miss`, so the client runs the tool itself;
  - the Bun driver's real side. On its shadow side a forced rejected speculation fails that
    shadow statement.
- Hit metrics (`TurnMetrics.hits`, the suite's `RunResult.hits`, `benchmark/geometry.py`,
  `benchmark/failures.py`, `demo/oolong_race.py`) no longer count a claim that fell back as
  a hit (`spec_ptc.contracts.hints.net_hits`). The `claim_hit` event itself is unchanged,
  because `demo/ui.py` keys its rows on it. `TurnMetrics.fallbacks` counts the fallbacks.
- It also fixes a bug found while testing the Bun shadow side: `tool_force` sent its dispatch
  handle as `id`, which `repl.js` overwrote with the reply id, so any force in the Bun shadow
  twin killed the bun process (also on `main`).

## What the client sees

| case | non-streaming | streaming |
|---|---|---|
| bet rejected at admission | HTTP 200, `finish_reason="abort"`, `stop_reason="sptc_bet_rejected"`, empty text | stream ends **without any `finish_reason`** |
| running bet dropped, had produced tokens | HTTP 200, the text so far, `finish_reason="abort"`, `stop_reason="sptc_bet_dropped"` | text chunks, then `finish_reason="abort"`, `stop_reason="sptc_bet_dropped"` |
| running bet dropped before its first token | as rejected, with `stop_reason="sptc_bet_dropped"` | stream ends without any `finish_reason` |

Why a zero-token stream ends with no finish reason: vLLM's chat and completion streaming
skip any output with no text and no tokens ("chunked prefill case, don't return empty
chunks" in `chat_completion/serving.py` and `completion/serving.py`). That also swallows the
final chunk of a request that finishes with zero tokens, and nothing sends it later.

The rule for clients is therefore: a speculative call whose `finish_reason` is `"abort"` or
missing was refused, so re-issue it as normal work when it is needed. That is what
`spec_ptc.contracts.hints.raise_if_rejected` checks. `ABORT` is used rather than `ERROR`
because `ERROR` becomes HTTP 500.

Counters (`scheduler.sptc_counters`):
- `bet_admitted`
- `bet_kv_load` (admitted into an async KV-connector load; `bet_admitted` follows when it runs)
- `bet_dropped`
- `bet_requeued_finishing` (a victim bet that finishes on its in-flight tokens)
- `bet_readmitted` (a bet requeued by vLLM after admission, admitted again)
- `bet_dropped_requeued:<reason>` (such a bet that failed the re-gate; the client sees
  `sptc_bet_dropped`, since it may already have streamed tokens)
- `bet_rejected:<reason>`, where the reason is `nonbet_waiting`, `free_window`, `kv_reserve`,
  `paused` or `held_too_long`

## Deliberate choices and known differences

- When the gate runs. The gate runs at admission, inside vLLM's waiting loop, with live
  state: the running count and KV usage include this step's admissions. It runs again at
  the end of the step for bets that were not admitted (see rule 1). The simulator's plain
  `agent` policy gates at submit and lets accepted bets queue. Here a failed gate rejects at
  once, and a passed gate may hold the bet for at most `bet_hold_steps` steps. The
  simulator's `plugin_semantics` mode gates the way the plugin does.
- What counts as "non-bet waiting". Every non-bet request in `waiting`,
  `kv_holding_waiting` or `deferred_waiting` (skipped this step), including early requests
  held back by the allowance, as in the simulator, where early work is normal priority.
  Only idle streaming sessions are excluded.
- The non-bet check is cached at the first bet that comes from `waiting`. Bets are moved
  behind all non-bets there, so every non-bet has been admitted or skipped by then. vLLM
  drains `kv_holding_waiting` before `waiting`, so a bet there is checked with a fresh scan
  that is not cached. Non-bets still queued in `waiting` count for it, which is
  conservative. Such a bet is rejected only if non-bet work is actually queued.
- The free window is a sequence count, not the simulator's cost-model knee (`spec_knee`).
- Running bets are not evicted for waiting work (the simulator's `_preempt_for`). vLLM
  breaks on a waiting allocation failure, and copying that block would mean forking
  `schedule()`. A waiting normal request can therefore wait while bets hold KV, until the
  running loop has to preempt; at that point bets go first.
- No waiting work in a step that drops a bet. vLLM skips the waiting loop in any step
  that preempted, and the plugin keeps that behaviour.
- Prefix-cache reset. `reset_prefix_cache(reset_running_requests=True)` (also what
  `pause_generation` with the default `clear_cache` does) keeps vLLM's requeue for running
  bets and re-gates them next step. A requeued bet that fails the re-gate is finished with
  `sptc_bet_dropped`, not `sptc_bet_rejected`: it was admitted and may have streamed.
- While paused, waiting bets are rejected with `paused`: nothing new is admitted, for an
  unbounded time. Blocked bets are kept; they are gated once unblocked. Under `PAUSED_ALL`
  vLLM may not step at all, and then nothing happens until it resumes.
- DP prefill throttle. A bet rejected without being visited was counted in vLLM's
  `prefill_capacity_bound`, so the plugin recomputes that value after rejecting, as if the
  bet had never arrived.
- Known limits, kept on purpose:
  - The waiting-loop allowance check uses the computed-token count from before vLLM's
    prefix-cache lookup. A tagged request whose whole prompt but its last token is cached
    can then be skipped for one step while the allowance is spent (rare: needs a prompt of
    `k * block_size + 1` tokens fully cached). Peeking at the cache would mean a second
    lookup per tagged request.
  - Under async scheduling the free window counts running requests whose last token is
    already in flight, so a bet can be refused for one step that sync scheduling would
    admit. vLLM's own `max_num_seqs` check counts the same way.
  - An untagged request that vLLM preempted while its last token was in flight counts as
    non-bet work waiting until that token arrives (one step).
  - `kv_reserve` reads vLLM's KV usage, which counts evictable prefix-cache blocks as free.
    A bet can therefore evict idle agents' cached prefixes, as an untagged call would.
    Counting cached blocks as used would refuse almost every bet on a warm server.
  - A non-bet request in an async KV load counts as non-bet work waiting, so bets are
    refused while it loads.
  - The plugin cannot tell in advance whether vLLM will admit a waiting early request
    (KV fit with prefix hits, LoRA, a break on a request ahead of it). A running bet can
    therefore lose one step to an early request that does not start. After that, while
    the request stays queued, no allowance is kept for early work: early requests then
    wait behind a running bet's prefill as they did before the fix for audit #2 (the
    numbers are those of `results/corrections/ledger.md`).
- Untested on vLLM itself: P/D KV connectors, pipeline parallelism and DP throttling.
  These paths are covered by the static checks, by code reading, and by the local tests on
  a stand-in of vLLM's scheduler (`tests/_vllm_fake.py`, `tests/test_vllm_adapter_fake.py`),
  not by runs on vLLM.

## SGLang (`sptc_sglang`)

The same policy for SGLang v0.5.22. SGLang has no `--scheduler-cls`, but it has a general
plugin system: packages registered under the entry point group `sglang.srt.plugins` are
loaded in every SGLang process, including the scheduler process, before the scheduler is
built. `sptc_sglang` registers two hooks with SGLang's own `HookRegistry`, so there is no
fork:
- a class replacement of `sglang.srt.managers.scheduler.Scheduler` by a subclass that
  overrides five methods (`get_prefill_adder_class`, `_get_new_batch_prefill_raw`,
  `get_next_batch_to_run`, `update_running_batch`, `_add_request_to_queue`) and returns a
  `PrefillAdder` subclass that overrides two (`add_one_req`, `add_chunked_req`);
- a wrapper around `ScheduleBatch._get_decode_retraction_order` that puts bets last, so they
  are retracted first.

All of them call SGLang's own code; nothing is copied.

### Install and launch

```bash
pip install -e integrations --no-deps   # a real install: entry points need it
SPTC_SGLANG_CONFIG='{"free_window": 8, "kv_reserve": 0.1, "spec_prefill_budget": 512}' \
  python -m sglang.launch_server --model-path Qwen/Qwen3-1.7B
```

- Off unless configured. The plugin does nothing unless `SPTC_SGLANG_CONFIG` is set
  (`'{}'` for the defaults). Installing the package does not change other SGLang servers in
  the same environment.
- Check the log. The scheduler logs `sptc scheduler on: SptcConfig(...)` at startup.
  SGLang's plugin loader only logs exceptions from a plugin's `register()`, so if that line
  is missing, the plugin did not load.
- Same knobs as the vLLM table above. Unknown knobs, wrong types and invalid JSON stop
  the server at startup. `spec_prefill_budget` is rounded up to a whole KV page, and to a
  multiple of SGLang's chunk alignment when there is one (`--enable-deterministic-inference`
  on flashinfer: 4096; DeepSeek DSA). A smaller budget could never chunk a long tagged
  prompt. The startup log shows the rounded value.
  `prefill_allowance` works as on vLLM. With `"adaptive"`, the decoders it looks at are
  SGLang's running (decode) batch.
- If `SGLANG_PLUGINS` is set, it must include `sptc`.
- Not supported (startup error): `--enable-priority-scheduling`, a
  `--schedule-policy` other than `fcfs`, PD disaggregation, pipeline parallelism, DP
  attention, diffusion LLMs, HiSparse, LoRA, and hybrid SSM (mamba) models. (LoRA: SGLang
  adds a skipped request's adapter to the step's adapter set even though the request is not
  admitted.)
- Allowance off, gate and dropping on: without chunked prefill, and for hybrid SWA
  models.

### Tagging requests

```python
client.chat.completions.create(model=..., messages=..., stream=True,
                               extra_body={"custom_params": {"sptc_class": "bet"}})  # or "early"
```

`custom_params` is a standard SGLang request field that reaches
`SamplingParams.custom_params`. Stock SGLang accepts the tag and ignores it.

### What the client sees

Rejected and dropped bets are finished as aborted without an HTTP status code, and the
result goes through SGLang's normal output path (scheduler, then detokenizer, then API
server), as SGLang does for its own request-validation errors. A refusal therefore cannot
overtake the bet's last tokens. (A bet dropped in the middle of its chunked prefill has no
tokens yet; SGLang's chunked-request abort sends its reason straight to the API server.)
SGLang returns a normal response, not an error, so OpenAI clients do not retry
automatically.

| case | non-streaming | streaming |
|---|---|---|
| bet rejected at admission | `finish_reason="abort"`, `matched_stop="sptc_bet_rejected"`, empty text | a final chunk with the same `finish_reason` and `matched_stop` |
| running bet dropped | the text so far, `finish_reason="abort"`, `matched_stop="sptc_bet_dropped"` | text chunks, then the same final chunk |

From the SGLang source, a zero-token stream also gets its final chunk, unlike on vLLM. Smoke
test S2 checks this on a real server. The client rule is the same either way: a speculative
call whose `finish_reason` is `"abort"` (or missing) was refused.

### How the policy maps onto SGLang

1. Bet admission. Before each prefill pass, bets are moved behind all other waiting
   requests (FCFS keeps that order). Inside SGLang's admission loop, each bet is gated with
   the live state: running requests plus those admitted earlier in the same pass, KV usage
   plus the tokens they will take, and the live waiting queue. The queue matters because
   SGLang appends requests whose grammar just compiled during the pass, behind the bets. A bet that fails the gate is skipped, never turned
   into a loop `break`, so certain work behind it still runs. After the pass, every bet
   still waiting is gated again with the end-of-step state. If the gate fails, the bet is
   rejected now. If it passes, the bet is held, for at most `bet_hold_steps` steps.
2. Bet dropping. SGLang retracts decoding requests when the KV pool runs out. With the
   plugin, bets are retracted first, and a retracted bet is aborted (`sptc_bet_dropped`)
   instead of being requeued for recompute.
   - A bet in the middle of a chunked prefill is not in the decode batch, so SGLang cannot
     retract it. Before a decode step that would retract, the plugin drops it through
     SGLang's own chunked-request abort, which frees its KV. SGLang then retracts only if
     KV is still short.
   - An early request in the middle of a chunked prefill is never dropped. In a decode step
     the plugin forced between its chunks (see 3) that would retract, it is retracted
     itself: KV freed, requeued, as `pause_generation(mode="retract")` does with the chunked
     request. Stock SGLang runs the chunks back to back and then retracts in its own order,
     where a long prompt with no output yet goes first. So this happens only when SGLang's
     order would pick the early request first; with a bet decoding, SGLang retracts the
     bet first.
   - `pause_generation(mode="retract")` also retracts every running request. Running bets
     are dropped there too (detail `retracted`), not gated again on resume.
3. Prefill allowance. It applies only in a step that starts with no untagged request
   waiting. In such a step, the prefill tokens of bet and early requests share
   `spec_prefill_budget`.
   - Why only then. By default SGLang runs a prefill step *instead of* a decode step.
     Once normal work is waiting, the step stalls the decoding streams for a full chunk
     anyway, so tagged work is left to SGLang's FCFS in that step.
   - One decode step after each limited step. When tagged requests were prefilled under
     the allowance while other sequences were decoding, the plugin forces one decode step,
     using SGLang's own `prefill_decode_interval` counter. A long early prompt is therefore
     prefilled in chunks of at most `spec_prefill_budget` tokens, and the decoding streams
     get a token between chunks. Without the forced step, the chunks would run back to
     back and the decoders would stall just as long as with no allowance.
   - With `--enable-mixed-chunk` decodes ride along in the prefill step, so no decode
     step is forced. SGLang cannot always mix (a request with logprobs, input embeddings,
     beams, or too little KV for the decodes). After such a prefill-only step a decode
     step is forced, as without mixed chunks.
   - One chunked request at a time. SGLang keeps at most one partially prefilled
     request. When the allowance leaves a tagged request partially prefilled, nothing else
     is admitted in that step, as when a chunk fills SGLang's own step budget.
4. Untagged traffic goes through every hook unchanged. The local tests check this step
   by step against SGLang 0.5.22's own scheduling code (the vendored sources, compiled
   locally by `tests/sglang_vendored.py`), with page size 16, chunk alignment, NO_TOKEN,
   retraction, mixed chunks and a pause.

### Differences from the vLLM plugin

- Loading: an entry point plus an environment variable, instead of `--scheduler-cls`
  plus `--additional-config`.
- Tag field: `custom_params`, not `vllm_xargs`.
- Rejection marker: `matched_stop`, not `stop_reason`.
- Admission reservations: SGLang reserves KV at admission for the prompt plus an
  estimate of the output (`new_token_ratio`), so SGLang's own budget can refuse a bet
  that passed the plugin's gate. Stock SGLang would then stop the pass and set
  `batch_is_full`, which holds back certain work until a running request finishes. The
  plugin skips the bet instead. The end-of-step gate then decides: held and retried, up
  to `bet_hold_steps`.
- Invalid bets: a bet SGLang has already failed (a grammar that did not compile, a
  prompt that is too long) is left to SGLang, so the client gets SGLang's own error, not
  `sptc_bet_rejected`.
- Known limits:
  - A bet's chunked prefill is continued first in every step, as SGLang does for any
    chunked request. With the allowance on, an early request that arrives meanwhile waits
    until the bet's prompt is done, and every bet that arrives in that window is rejected
    `nonbet_waiting`. With `adaptive`, the bet's chunks are capped only while a non-bet
    decodes, so otherwise it finishes sooner. This is fixable in SGLang without a second
    chunked request: cap the bet's continuation (`chunked_req_limit`) to leave room for
    waiting early prompts that fit whole, as SGLang's own shortest-prefill-first does.
    `sptc_vllm` now does the equivalent (audit #2); this plugin does not yet, so the two
    differ on this rule until it is ported.
  - With a bet decoding while an early request is chunked, SGLang retracts the bet first.
    If that is not enough KV, it retracts a decoder next, while the early request keeps its
    KV (it is not in the decode batch).
  - A small bet behind a long early prompt that takes the whole allowance is rejected
    `held_too_long` after `bet_hold_steps` steps. Behind another bet's prefill it is held
    without counting those steps, as in `sptc_vllm` (audit #38 / #10).
- Prefill allowance: decode steps are forced, as described above. vLLM mixes prefill
  and decode in one step, so it needs no forced steps.
- No counters endpoint. `scheduler._sptc.counts` keeps `admitted`, `rejected` and
  `dropped` in the scheduler process; rejected and dropped bets are logged at debug level.

## Files

```
sptc_vllm/policy.py        pure (no vLLM): SptcConfig, classify, admit_bet, bets_last, PrefillAllowance
sptc_vllm/scheduler.py     vLLM adapter: SptcScheduler (auto-selects) and SptcAsyncScheduler
tests/                     local, no vLLM: pure policy tests, a static AST check of the adapter
                           against the v0.32.0 sources (override names/signatures, attributes, imports),
                           and the adapter run on a small stand-in of vLLM 0.32's scheduler
                           (_vllm_fake.py, test_vllm_adapter_fake.py; skipped where vLLM is installed)
tests_vllm/                needs vllm==0.32.0 (Kaggle): scheduler behaviour, a differential test against stock vLLM,
                           per-step scheduler CPU time vs stock (test_sptc_overhead.py), and a check
                           of kaggle/overhead_bench.py (test_overhead_bench.py)
kaggle/sptc_vllm_smoke.py  end-to-end OpenAI-API smoke test (S1-S4)
sptc_sglang/core.py        SGLang logic against injected base classes (testable without SGLang)
sptc_sglang/plugin.py      SGLang v0.5.22 glue: register() (entry point), startup checks
tests/test_sglang_*.py     local, no SGLang: the logic on fakes of SGLang's control flow, the
                           plugin on SGLang's own scheduling code compiled from the v0.5.22
                           sources (sglang_vendored.py), and a static AST check of those sources
tests_sglang/              needs sglang==0.5.22 (Kaggle): entry point, hook application, class wiring
kaggle/sptc_sglang_smoke.py  end-to-end OpenAI-API smoke test for SGLang (S1-S4)
spec-ptc-sptc-hints.patch  the spec-ptc client change of the T4 runs
spec-ptc-fork/             the client changes since, as patches on top of it (README.md there)
```

## Tests

```bash
# local, milliseconds, no vLLM or SGLang. Run from the repository root, in the environment
# of the top-level README's Tests section. The static checks read vllm_src_v0.32.0/ and
# sglang_src_v0.5.22/python/ next to this repository (or SPTC_VLLM_SRC / SPTC_SGLANG_SRC)
# and are skipped if those are missing.
.venv/bin/python -m pytest integrations/tests -q

# the spec-ptc client changes have their own tests, run from the patched tree:
# spec-ptc-fork/README.md, "Tests of the patched client"

# on Kaggle, with vLLM installed
pip install vllm==0.32.0 pytest && pip install -e sptc-bundle/sptc-sim/integrations --no-deps
pytest sptc-bundle/sptc-sim/integrations/tests_vllm -q -s -p no:cacheprovider   # -s prints the overhead numbers
# SGLang, in a fresh session (it pins another torch): kaggle/sptc_sglang_kaggle.ipynb
pip install sglang==0.5.22 pytest && pip install -e sptc-bundle/sptc-sim/integrations --no-deps
pytest sptc-bundle/sptc-sim/integrations/tests_sglang -q -p no:cacheprovider
```

- The `tests_vllm` helpers rebuild vLLM's `create_scheduler` test factory (same configs), so
  no vLLM test checkout is needed. The `facebook/opt-125m` config is fetched from the HF hub;
  set `SPTC_TEST_MODEL` to use another model.
- Run the smoke test after that. Its docstring gives the two `vllm serve` command lines; one
  is needed for S1-S3 and one for S4. Then run `kaggle/vllm_bench.py` with `--tag-bets`.
