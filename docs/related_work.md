# Related work

Prior work as of October 20, 2026: papers, vLLM and SGLang issues and PRs, docs, and the
vLLM 0.32.0 and SGLang 0.5.22 sources. "Not found" means not found in the sources read,
not "does not exist anywhere". Issue and PR states are as of that date. Three later
additions, checked on November 8, are marked "(added November 8)": TAO, and vLLM PRs
#63350 and #63351.

## The claim, narrowed

Every mechanism in the plugin already exists somewhere, and some were proposed inside vLLM
itself. The combination was not found. The fair claim:

> `bet` is a known idea, a best-effort / scavenger class (as in RFC 8622, llm-d sheddable
> traffic and flex API tiers), applied to a new kind of work, speculative LLM sub-calls,
> inside the engine's per-step scheduler. It follows the principle vLLM already applies to
> draft tokens (speculation is turned down under load), at request granularity. `early`,
> the near-certain half of speculation, is exempt from the gate and the drop: it is
> admitted and preempted as normal work, but its prefill shares the per-step allowance
> with bets.

It is not a new scheduling primitive. What is new is mostly *why* and *for which requests*
the engine refuses or drops work, not *how* it signals it.

What appears new (within these sources):
1. Exempting near-certain speculation from the low class (from the gate and the drop;
   its prefill is still capped). Grading speculation by likelihood is not new (PASTE
   ranks by expected utility including confidence; SPAgent ranks earlier-step speculation
   higher). But in both, all speculative work stays speculative. The simulator's finding
   that throttling *all* speculation hurts the critical path is the reason for the
   exemption. The one unexplained measured cost (+13.5% at 1 agent) came from a row with
   only `early` tags, so the exemption is not shown to be free.
2. A spare-capacity gate for one class, inside the engine step, with an immediate
   refusal: no non-bet request waiting, one more sequence fits the free window, KV usage
   at most 1 - reserve. Only the immediate refusal is new. The capacity test is not: Echo
   admits offline work only after all online requests are batched, under a KV threshold
   (the same two rules), and HyGen fills a per-step leftover budget. The signal is not new
   either (vLLM RFC #24256 / PR #24520 refused inside the scheduler with HTTP 200 and a
   finish reason), nor is rejecting when no decode slot will be free (Mooncake,
   class-blind and cluster-level).
3. Drop-not-requeue for one request class, as code for vLLM 0.32 and SGLang 0.5.22.
   Released engines always requeue. The idea was asked for in vLLM #17736 and proposed for
   P/D in #24256 / #24520; neither was merged, and neither is about speculation. On vLLM
   a drop has been seen only in a smoke test (S4), never in a measured row, and the audit
   fixes to that path have not run on vLLM; the SGLang plugin has never run on SGLang. No
   measurement or simulation shows what dropping buys over requeueing with a prefix-cache
   resume (the bet vs background rows in `results/general` mix drop with eviction for
   waiting work and with queueing vs polling).
4. A prefill allowance shared only by tagged (bet + early) requests. Normal prefill and
   decode are untouched. Per-class token caps are not new (RFC #30256, HyGen's offline
   prefill budget); new is only which class it caps.
5. Packaging: the same policy as no-fork plugins for vLLM (`--scheduler-cls`) and
   SGLang (`HookRegistry`), with untagged traffic checked step by step against stock.
6. A serving-side measurement for sPTC: wasted speculation clogs a shared engine;
   admission control fixes it and reordering does not (simulated), with one small real-GPU
   check (T4, 8 agents, one bad guess per call: 6.62 s -> 4.41 s session p50, measured,
   `results/kaggle_t4/RESULTS.md`). The qualitative observation is not new: SPORK reports
   that "under heavy batching, probe traffic competes with foreground decode", and
   Zhang's blog names a clogged serving engine as the worst case.

### What is not new, and what the evidence does not show

- Speculation has been studied on the serving side before: SPAgent, Nichols et al.,
  PASTE v3 and SPORK all touch it.
- "Admission control, not ordering" is not a new insight. Co-location work (HyGen, Echo,
  ConServe, BROS, Niyama) already serves best-effort work from leftover capacity, and the
  sPTC result is consistent with that line of work. Nor is it claimed that those papers
  showed it: whether they compare admission with ordering was not examined, and Niyama's
  mechanism (per-iteration relegation) is itself an ordering policy, compared only with
  ordering baselines (Sarathi-FCFS, EDF, SRPF, Silo).
- "Finish reason instead of HTTP error" and "return to caller instead of requeue" are not
  new in vLLM: see #24256 / #24520 and #17736.
- vLLM already ties speculation to load for draft tokens (`disable_by_batch_size`,
  `num_speculative_tokens_per_batch_size`). TurboSpec does it by predicted goodput, and
  vLLM's Q4 2026 roadmap lists "adaptive speculative decoding".
- vLLM RFC #42185 is not proof that ordering fails under continuous batching: it shows a
  cache-affinity reordering plugin gained about nothing on one shared-prefix workload, and
  its author explains that by prefix caching.
- The simulator's `agent` policy is not the plugin: the simulated policy promotes claimed
  bets, and the plugin has no promotion (PASTE and B-PASTE also promote).
- The evidence is small: one simulator, one T4 with a 1.7B model and one H100 workload
  ([limitations](../README.md#limitations)).

## What exists

| sPTC mechanism | closest existing work | how it differs |
|---|---|---|
| admit low-class work only on spare capacity | HyGen, Echo, ConServe, BROS, OmniServe, Niyama, llm-d Flow Control, Red Hat priority holdback, RFC 8622 LE PHB, Kubernetes BestEffort | low-class work waits in a queue; it is not refused or dropped. None is about speculative LLM sub-calls. Niyama relegates a request that has missed, or is about to miss in the current iteration, its deadline: not a capacity test. llm-d works at the gateway. Inside vLLM, load-aware speculation exists at draft-token level only |
| refuse at once when there is no spare capacity | Mooncake early rejection (429), vLLM RFC #24256 / PR #24520 (HTTP 200 + `finish_reason="cache_threshold"`, unmerged), llm-d legacy admission (429), Groq / OpenAI / Gemini flex (498 / 429 / 503), vLLM `--max-num-queued-reqs` (503), SGLang `--max-queued-requests` (503) | Mooncake is class-blind and cluster-level, and found that rejecting on *current* decode load makes load oscillate (§7.3). #24520 gates on cache-hit rate. vLLM's cap counts waiting + running requests for all traffic; SGLang's counts the waiting queue. None gates one class per step |
| drop admitted low-class work instead of requeueing | vLLM #24256 / #24520 (preempted P/D request sent back to the router; unmerged), vLLM #17736 ("drop instead of preempt", closed not planned), llm-d `enableEviction`, Gemini flex, spot VMs, PASTE v1, SPAgent (drop after t_w), B-PASTE | in released vLLM 0.32 and SGLang 0.5.22, every preempted or retracted request is requeued and recomputed |
| low-class work is the first preemption victim | vLLM priority policy, SGLang `--retraction-policy priority`, vLLM RFC #54644, draft PR #51601 `PreemptionPlugin`, RFC #30256 | victims are requeued, not dropped |
| per-step prefill cap | Sarathi-Serve token budget, vLLM `long_prefill_token_threshold` and (0.32) `long_prefill_token_threshold_adaptive`, P-PAS RFC #52906, RFC #30256, HyGen; SPORK staggers dispatch on the client | none caps only the prefill of tagged speculative work |
| load-aware handling of speculative LLM requests | SPAgent, PASTE v3, SPORK | SPAgent puts speculative requests *ahead* of main ones. PASTE gates all LLM turns; its speculation is tool execution. SPORK is client-side only |
| per-request class tag from the agent | Dynamo `nvext.agent_hints.priority`, llm-d-router PR #2265, vLLM agent hints (roadmap), Niyama hints, Parrot, Google SRE criticality | integer priority, tier, session identity or criticality, not speculation semantics |

## Closest prior work

**Speculative agent work**

| work | how it differs |
|---|---|
| [Zhang, sPTC blog and spec-ptc](https://alexzhang13.github.io/blog/2026/spec-ptc/) (Aug 2026) | The origin. Names a clogged serving engine as the worst case, which "can be controlled with how aggressive speculation is and how these tools are queued". The plugin is one concrete form of that queueing control. No engine-side admission or tagging |
| [SPAgent](https://arxiv.org/html/2511.20048v1) (Nov 2025) | Closest prior art: load-aware admission of speculative LLM requests, dropped after t_w; earlier-step speculation ranked higher. But speculative requests go *ahead* of main ones; no KV-pressure drop, no prefill allowance, no immediate refusal |
| [PASTE](https://arxiv.org/abs/2603.18897) (v1 Mar, v3 Jun 2026) | Speculative *tool* jobs on slack, ranked by expected utility, preempted first, promoted on match. v3 adds a vLLM startup hook that gates all LLM turns by decode + KV pressure. No speculative LLM class in the engine |
| [SPORK](https://arxiv.org/html/2607.03333) (Jul 2026) | Speculative forks to the same vLLM endpoint as the main stream; reports "2.5x prefill contention" and staggers dispatch on the client. No engine priority, admission or drop. A client-side baseline |
| [Nichols et al.](https://arxiv.org/abs/2512.15834) (Dec 2025) | vLLM fork with a tool-cache endpoint; speculative calls run on separate GPUs, so there is no contention to schedule |
| [Speculative Actions](https://arxiv.org/abs/2510.04371) (ICLR 2026) | Assumes concurrent calls are nearly free under continuous batching. SPAgent reports it up to 49.3% slower than naive above 2 rps |
| [B-PASTE](https://arxiv.org/abs/2604.16469) (Apr 2026) | Slack-budget admission, preempt first, promotion; edge tool execution, no KV or decode window; preliminary evaluation only |
| [pi-fabric](https://github.com/fabric-runtime/pi-fabric/blob/main/docs/speculation.md); [Pydantic AI Code Mode](https://pydantic.dev/docs/ai/harness/code-mode/) | Client-side caps (pi-fabric `maxConcurrent` 4; Pydantic 32 early starts per `run_code`). pi-fabric excludes `agents.*` sub-calls. Pydantic does not address LLM sub-calls, and starts eligible calls in both arms of an `if/else`, discarding the loser: a shipping source of branch bets |

**Co-location of best-effort and latency-critical work**

| work | how it differs |
|---|---|
| [HyGen](https://arxiv.org/html/2501.14808v4) (NeurIPS 2025) | Offline work fills the leftover predicted-latency budget; it waits, never refused, and keeps its state when preempted |
| [Echo](https://arxiv.org/abs/2504.03651) | Offline work only after all online requests are batched, plus a mu + 2 sigma KV threshold; preempted offline work is recomputed |
| [ConServe](https://arxiv.org/html/2410.01228v2) (ICML 2026) | Harvests idle capacity with layer-level preemption, and works to *keep* offline work (host KV checkpoints). The opposite of dropping |
| [BROS](https://arxiv.org/html/2504.09590v1) | Best-effort work in leftover slack, swapped out first under memory shortage, not discarded |
| [Niyama](https://arxiv.org/html/2503.22562v1) (Mar 2025) | Per-iteration relegation inside a Sarathi / vLLM scheduler, chosen by application hints; relegated work is kept and runs later. Deadline-driven, not speculative |
| [OmniServe](https://arxiv.org/html/2603.12831) (SIGMOD 2026) | Rejects only the latency-sensitive class. Calls "reserving headroom to constrain BE resource usage" too coarse, which bears on a static `kv_reserve` |
| [Mooncake](https://arxiv.org/html/2407.00079v4) | Early rejection (429) when no decode slot is predicted after prefill. Rejecting on current load oscillates (§7.3); fixed by prediction (§7.4). Class-blind, cluster-level. Whether the per-step bet gate oscillates has not been checked |
| [Sarathi-Serve](https://arxiv.org/html/2403.02310) (OSDI 2024) | Token budget over all tokens of a step. The plugin caps only bet + early prefill; its 512 default is not derived from Sarathi |

**Agent-aware serving schedulers (added November 8)**

| work | how it differs |
|---|---|
| [TAO](https://arxiv.org/abs/2610.37230) (Li et al., Oct 27, 2026) | Tool-aware joint scheduling for agentic serving: a value function (near-term tool readiness, cache credit with time decay, token footprint) and a dynamic program choose and place waiting agent sessions on GPUs under capacity limits. Reports up to 26.8% lower latency, 36.3% lower TTFT and 29.5% higher decode throughput against the best baseline per metric, over 12 model, workload and concurrency settings. It admits whole sessions by predicted value: no speculative calls, no best-effort class, no refusal or drop. Read from the abstract only, which does not say whether it runs on vLLM or SGLang |

**Upstream engines and gateways**

| work | how it differs |
|---|---|
| [vLLM RFC #24256](https://github.com/vllm-project/vllm/issues/24256) + PR #24520 | Nearest in-engine precedent for both refusal and hand-back: a per-request cache-hit threshold checked in the scheduler, refused requests get HTTP 200 with `finish_reason="cache_threshold"`, preempted P/D requests go back to the router instead of re-prefilling. Gate is cache-hit rate, not capacity. RFC closed not planned 2026-05-31, PR closed unmerged 2026-06-02 |
| [vLLM issue #17736](https://github.com/vllm-project/vllm/issues/17736) | A user asked for "dropping requests instead of preempting them". Only bot comments; closed not planned |
| [vLLM issue #40004](https://github.com/vllm-project/vllm/issues/40004) + PR #54530 | Priority cannot preempt at `max_num_seqs`: ordering alone fails once slots are full. The fix PRs requeue victims |
| [vLLM PR #63350](https://github.com/vllm-project/vllm/pull/63350) (added November 8) | "Priority scheduling: preempt for a waiting request under KV pressure". Adds an off-by-default `--max-priority-preemptions-per-step N`: a waiting request may preempt up to N running requests of strictly lower priority when the KV cache has no room for it. It also keeps preempted requests from resuming into blocks that a higher-priority prefill still needs, and adds a `vllm:num_priority_preemptions` counter. Its author reports a priority-0 request's median TTFT falling from 4,968 to 290 ms in one KV-pressure test on an RTX 5060 Ti. Opened Oct 23, 2026; closed unmerged Nov 3, 2026. It targets #40004's KV case, where priority never preempts for a waiting request, and it makes priority a better way to make low-class work *wait*, which the third T4 run found better than refusal for bets that may be needed |
| [vLLM PR #63351](https://github.com/vllm-project/vllm/pull/63351) (added November 8) | "Priority scheduling: hold lower-priority prefill for first tokens", stacked on #63350. Adds an off-by-default `--priority-prefill-budget-cap`: lower-priority prefill chunks sit out the steps in which a higher-priority request produces its first tokens (16 by default); decodes are never held. Opened Oct 23, 2026; closed unmerged Nov 3, 2026. A priority-based form of the plugin's prefill allowance |
| [vLLM RFC #51608](https://github.com/vllm-project/vllm/issues/51608) + [draft PR #51601](https://github.com/vllm-project/vllm/pull/51601) | Scheduler plugin framework (Filter, Score, QueueSort, PreemptionPlugin). A filter rejection means "not eligible in this cycle"; filtered requests stay queued; the core requeues preemption victims. So refusal and drop are not covered |
| [vLLM RFC #54644](https://github.com/vllm-project/vllm/issues/54644) + PR #53723 | Victim-selection extension point. Victims are still requeued |
| [vLLM PR #49445](https://github.com/vllm-project/vllm/pull/49445) | `--max-num-queued-reqs` / `--max-num-queued-tokens`: class-blind 503 when waiting + running requests (or tokens) exceed a cap, enforced in the API server |
| [vLLM RFC #6077](https://github.com/vllm-project/vllm/issues/6077) / PR #5958 | Priority scheduling: ordering plus forced preemption with requeue, with the same co-location motivation |
| [vLLM RFC #30256](https://github.com/vllm-project/vllm/issues/30256) | Per-request tiers and a per-class token cap. Auto-closed, no maintainer engagement |
| [vLLM speculative config](https://docs.vllm.ai/en/stable/api/vllm/config/speculative/); [TurboSpec](https://arxiv.org/abs/2406.14066) | Draft-token speculation turned down by batch size or predicted goodput. The same principle as `bet`, at token granularity |
| [SGLang PR #8746](https://github.com/sgl-project/sglang/pull/8746) + [PR #7565](https://github.com/sgl-project/sglang/pull/7565) | Priority scheduling, queue-cap rejection (503), preemption at a priority gap above 10. Preempted requests are requeued |
| [llm-d Flow Control](https://llm-d.ai/docs/0.10/architecture/core/router/epp/flow-control) | Sheddable class: 429 on saturation (legacy mode), optional eviction with caller retry. Gateway level; no per-step decode window or prefill allowance |
| [Dynamo agent hints](https://docs.nvidia.com/dynamo/v1.5.0/agents/priority-scheduling.md) | Agent-aware priority plumbing to vLLM and SGLang; "not ... a hard admission control policy". Its `speculative_prefill` is next-turn cache warming |

**Commercial tiers and classic analogies**

| work | how it differs |
|---|---|
| [Groq](https://console.groq.com/docs/flex-processing) / [OpenAI](https://developers.openai.com/api/docs/guides/flex-processing) / [Gemini](https://ai.google.dev/gemini-api/docs/flex-inference) flex tiers | Best-effort pricing tiers with fast failure (498 / 429 / 503) at the API layer; Gemini flex can also preempt. No speculation semantics |
| [RFC 8622 LE PHB](https://www.rfc-editor.org/rfc/rfc8622.html) ("scavenger") | Residual capacity, dropped first, may starve; packet level, no admission |
| [Google SRE Book ch. 21](https://sre.google/sre-book/handling-overload/) | A sheddable criticality class; child requests *inherit* criticality, while sPTC tags sub-calls *lower* |

## Upstream status (October 2026)

**vLLM** (the plugin targets 0.32):

| capability | status |
|---|---|
| priority scheduling | `--scheduling-policy priority`; lower value first, arrival time breaks ties |
| preemption victim | priority: `max(running, key=(priority, arrival_time))`; FCFS: `running[-1]` |
| what happens to a victim | always requeued and recomputed; never dropped. Hand-back (#24256 / #24520) not merged; "drop instead of preempt" (#17736) closed not planned |
| priority preemption at `max_num_seqs` | missing; #40004 open, fix PR #54530 open |
| priority preemption for a waiting request under KV pressure; holding lower-priority prefill (added November 8) | missing. Proposed as PRs #63350 and #63351, opened Oct 23 and closed unmerged Nov 3, 2026 |
| admission rejection | `--max-num-queued-reqs` / `--max-num-queued-tokens` (PR #49445, merged Aug 31, 2026): 503, default off, class-blind, counts waiting + running |
| per-request reject inside the scheduler | not in a release |
| prefill limits | `long_prefill_token_threshold` (per request); `long_prefill_token_threshold_adaptive` (0.32, default off). Issue [#60476](https://github.com/vllm-project/vllm/issues/60476) (short requests no longer protected) is present in 0.32.0 |
| load-aware speculative decoding | token level only (`disable_by_batch_size`, `num_speculative_tokens_per_batch_size`) |
| custom scheduler | `--scheduler-cls`, with a warning that the interface "is not public and compatibility may not be maintained" |
| plugin framework | RFC #51608 open; draft PR #51601 (Filter, Score, QueueSort, PreemptionPlugin). No maintainer reply on the RFC yet. Its phase 5 is "Evaluate lifecycle and preemption extensions" |
| agent hints | Q3 2026 roadmap done: Session-ID, Correlation-ID; [Q4 roadmap #61024](https://github.com/vllm-project/vllm/issues/61024): "richer agent hints". Neither roadmap mentions priority, preemption, admission control or QoS |

**SGLang** (the plugin targets 0.5.22):

| capability | status |
|---|---|
| priority scheduling | `--enable-priority-scheduling` (default off); preemption needs a priority gap above `--priority-scheduling-preemption-threshold` (10); preempted requests are requeued |
| queue-limit rejection | `--max-queued-requests`, waiting queue only, 503 |
| KV retraction | `--retraction-policy length|priority`; retracted requests are requeued |
| plugins | `sglang.srt.plugins` entry points and `HookRegistry`, which `sptc_sglang` uses |
| tracking | issue [#8743](https://github.com/sgl-project/sglang/issues/8743), auto-closed, lists "Priority based abort request" with no linked PR. No open SGLang RFC to attach to |

Around the engines: llm-d (Flow Control; PR #2265 propagates an integer `priority`, so it
would not carry `sptc_class` without new code), Dynamo (priority hints, no refusal or drop),
Mooncake (Conductor-level early rejection), TensorRT-LLM (pluggable `CapacityScheduler`).

### The RFC that was drafted and held

A vLLM RFC for the class was drafted and never posted. It was held after the third T4 run
(October 29), because no ask in it is supported by the measurements:

- The engine-side class did not beat a client cap. Under KV pressure and a real queue it
  was at 0.982 and 1.000 of a client-side cap, below the pre-registered 5% bar.
- The fallback ask, a per-class admission limit, is also a refusal. With bets that are
  needed half the time, refusing them made sessions 1.5× slower than admitting them all,
  while priority, which only makes them wait, was 1.65× faster than the class.

If the question is reopened, the plan was not to open a new RFC first but to comment on
the scheduler-plugin framework,
[RFC #51608](https://github.com/vllm-project/vllm/issues/51608) and
[draft PR #51601](https://github.com/vllm-project/vllm/pull/51601). The ask there would be
small: a filter outcome that finishes the request with a finish reason, and a victim
outcome "drop" next to "requeue". The next venue would be
[RFC #54644](https://github.com/vllm-project/vllm/issues/54644), on victim selection.

## Baselines, and where they stand

| baseline | status |
|---|---|
| stock vLLM priority with bets at low priority | done.<br>- **Second run (B3, B4):** equal to FCFS when nothing waits: 0.996 / 1.006 at 4 / 8 agents, bets only (`results/kaggle_t4_v3/RESULTS.md`).<br>- **Third run, with a queue:** 0.870 (`decoys`) and 0.915 (`both`) of FCFS, both unresolved. 1.65× faster than the plugin in `both` (`results/kaggle_t4_v4/RESULTS.md`) |
| class-blind client-side cap on bets | done.<br>- **Second run (B4):** the cap that counts every request in flight tied the plugin (0.807 / 0.714 vs 0.780 / 0.718, the plugin's 8-agent cell void); the bets-only semaphore was 13% slower.<br>- **Third run, under KV pressure:** the in-flight cap tied again (plugin vs cap 0.982 / 1.000).<br>- **Caveat:** the cap runs inside the bench client, a best case for a proxy |
| `--max-num-queued-reqs` | not run: it refuses root streams and normal calls too, so the bench's sessions would fail |
| a no-bets reference | done. B4 `fcfs-b4/spec` in the second run, `fcfs-p/spec` in the third. With decoys only, the gates reach it, so refusing every bet is optimal there |
| prefill allowance off / adaptive vs fixed; the 1-agent regression | done (second run, B1 and B2). The three modes are indistinguishable, and the October 19 gap did not reproduce on a shared compiled artifact (session ratios 0.99–1.02) |
| simulated policy without promotion | done: `ServerConfig.plugin_semantics` models the plugin as built |
| a cap (client-side, router, or per-class `check_admission`) under KV pressure or a waiting queue, with bets that are sometimes used | done for the client-side cap.<br>- **Simulated** (`results/pressure/`) and **measured** (third run): the plugin vs the cap was 0.982 (`decoys`) and 1.000 (`both`), with no engine-side win.<br>- **Refusing hurt:** with bets that are needed half the time, both gates were 1.5× slower than stock FCFS.<br>- **Not run:** a router cap and a per-class `check_admission` limit |
| the class as proposed in the RFC draft (bets tagged, `early` calls untagged) | done (third run): every plugin and priority arm tagged only the bets |
| drop vs requeue ablation; gate ablation and oscillation; HyGen-, Echo-, SPAgent- or SPORK-style policies; SGLang on a GPU; seeds on larger GPUs | not run. The plugin's drop never fired in a load run, even under KV pressure |
