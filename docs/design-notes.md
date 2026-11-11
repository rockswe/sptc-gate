# Design notes: the scheduler plugin and the simulator

How the scheduler plugin behaves, how its policy was chosen in a simulator before any GPU
run, and what an audit of both found. Measured results are in the
[README](../README.md) and in the run records under `results/`. The H100 study is in
[h100-study.md](h100-study.md).

Numbers here are labelled **measured** (with their source file), **simulated** or
**predicted**.

The class bounds the cost of opportunistic work; it does not remove it. A bet admitted
inside the window still decodes in every step, and on the T4 each extra decoding sequence
cost about 0.44 ms per step (measured).

## What is new and what is not

`bet` is a known idea, a best-effort or scavenger class
(as in RFC 8622, llm-d's sheddable traffic and flex API tiers), applied to a new kind of
work: speculative LLM sub-calls, inside the engine's per-step scheduler. Near-certain
speculation (`early`) is exempt from the gate and the drop: it is admitted and preempted
as normal work, but its prefill shares the per-step allowance with bets (table below).
Admitting low-class work only on spare capacity is not new either: Echo admits offline work
only after every online request is batched, under a KV threshold, and HyGen fills a
per-step leftover budget. Per-class token caps exist too (vLLM RFC #30256, HyGen's offline
prefill budget). Refusing inside vLLM's scheduler with a normal response, and handing
preempted work back instead of recomputing it, were proposed before (vLLM RFC #24256 / PR
#24520, not merged), and "drop instead of preempt" was asked for in #17736. What is new is
narrow: refusing at once, and dropping instead of requeueing, one class of speculative
sub-calls, as a no-fork plugin. Dropping is implemented for vLLM (seen to fire only in a
smoke test) and SGLang (never run on SGLang); nothing measured or simulated yet shows what
it buys over requeueing. Prior work and upstream status:
[docs/related_work.md](../docs/related_work.md).

## The problem

Some requests to a model server are opportunistic: work that may help but is not needed
yet. How common they are in production is not known; nothing here measures it, and the
census below found that today's code-mode agents make almost no bets. Agents start tool
calls and sub-calls before the model has finished deciding on them (speculative
programmatic tool calling, sPTC), guess the next LLM call while a tool runs, or
prefetch. Batch jobs fill the gaps between interactive sessions. A stock
vLLM server cannot tell this work from the requests a user is waiting on. Continuous
batching admits it as soon as it fits, and from then on every decode step carries it.
When a guess is wrong, the server spent capacity on nothing, and every user's tokens came
slower. On the T4 with 8 agents and one wrong guess per speculative call, the agents'
root streams (each agent's own model output, the stream a user waits on) ran at 39 ms per
token, against 26 ms with correct speculation and 20 ms with none, and 25.9 ms on the
plugin with the same wrong guesses (measured, first T4 run:
`results/kaggle_t4/RESULTS.md`). vLLM's `--scheduling-policy priority` does not fix this:
it orders the waiting queue, but a running low-priority request still decodes in every
step. The second T4 run measured that, next to two fairer baselines: priority with only
the bets deprioritised, and a client-side cap on bets
(`results/kaggle_t4_v3/RESULTS.md`, sections 2 and 3).

## What the plugin does

A request's class comes from one field, `vllm_xargs={"sptc_class": ...}` (SGLang:
`custom_params`):

| tag | meaning | treatment |
|---|---|---|
| `bet` | speculative call that may never be used | admitted only on spare capacity, otherwise refused at once; dropped first under KV pressure, never recomputed |
| `early` | sent ahead of time, almost surely used | normal admission and preemption; its prefill shares a per-step allowance |
| none | normal work | stock vLLM FCFS, step for step |

- Admission on spare capacity. A bet is admitted only if no non-bet request is
  waiting, one more running sequence fits in the free window (default 8), and KV usage is
  at most 90%. If the gate fails, the bet is refused in the same step
  (`finish_reason="abort"`, `stop_reason="sptc_bet_rejected"`). A bet that passes but is
  not reached is re-gated at the end of each step, for at most 16 steps.
- Dropped first. Running bets are kept last, so vLLM's own preemption victim is a bet.
  It is aborted (`sptc_bet_dropped`), not requeued for recompute.
- Prefill allowance. Bet and early prefill share 512 tokens per step, so a long
  speculative prompt cannot fill a step that decoding streams need. The
  `prefill_allowance` knob picks when it applies: `fixed` (default, every step),
  `adaptive` (only while a more certain stream is decoding) or `off`.
- No promotion. A refused bet that turns out to be needed is re-sent as normal work.
  The [spec-ptc patch](../integrations/spec-ptc-sptc-hints.patch) does this on the client.

Full rules, knobs, edge cases and the SGLang mapping: [integrations/README.md](../integrations/README.md).

## Install and launch

```bash
pip install -e integrations --no-deps          # must be importable in vLLM's engine-core process
vllm serve Qwen/Qwen3-1.7B \
  --scheduler-cls sptc_vllm.scheduler.SptcScheduler \
  --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1, "spec_prefill_budget": 512}}'
```

```python
client.chat.completions.create(model=..., messages=..., stream=True,
                               extra_body={"vllm_xargs": {"sptc_class": "bet"}})   # or "early"
```

- Streamed refusals have no finish reason. vLLM 0.32 drops empty stream chunks, so a
  bet refused or dropped before its first token ends the stream with no `finish_reason`
  at all (smoke test S2). A streaming client must treat "abort or missing" as a refusal.
  Non-streamed requests get `finish_reason="abort"` as described above.
- Stock vLLM accepts the tag and ignores it. Only `--scheduling-policy fcfs` is supported.
- Expect a vLLM warning at startup: "Using custom scheduler class ... If you have
  subclassed Scheduler instead of AsyncScheduler, you will see degraded performance due
  to async scheduling being disabled." vLLM prints it for every scheduler class outside
  `vllm.`. `SptcScheduler.__new__` returns `SptcAsyncScheduler` when async scheduling is
  on, so the warning does not mean async is off.
- The plugin then logs `sptc scheduler (SptcAsyncScheduler): SptcConfig(...),
  prefill allowance 512 (fixed)`. That line did not appear in the first T4 run's logs,
  so that run has no log evidence of which variant ran. The logger has since moved under
  vLLM's namespace, and the line printed on every launch of the second run.

## Measured runs

The plugin ran on a Tesla T4 three times. The README's tables come from the second and
third runs.

| run | what it measured | record |
|---|---|---|
| first, October 19–20 | the plugin against stock vLLM, with and without wasted speculation; the simulator's predictions | [results/kaggle_t4/RESULTS.md](../results/kaggle_t4/RESULTS.md) |
| second, October 20 | vLLM priority scheduling, client-side caps, scheduler overhead, the plugin's tests on real vLLM | [results/kaggle_t4_v3/RESULTS.md](../results/kaggle_t4_v3/RESULTS.md) |
| third, October 29 | KV-cache pressure and a real queue, with bets that are sometimes needed | [results/kaggle_t4_v4/RESULTS.md](../results/kaggle_t4_v4/RESULTS.md) |

The notebooks that ran them are in `kaggle/` (`sptc_kaggle.ipynb`, `sptc_kaggle_v3.ipynb`
and `sptc_kaggle_v4.ipynb`), and `kaggle/make_bundle.sh` builds the bundle they load.
The second run is also scored against `results/prereg_v2`, the predictions written for
an earlier version of its notebook (`sptc_kaggle_v2.ipynb`), which the v3 notebook
replaced before the run and which is not kept.

**The first run's light-load gap did not reproduce.** With 1 agent and no bets at all,
sessions took 3.10 s on the plugin against 2.73 s on stock (+13.5%). No arm of the second
run shows that gap: with stock and plugin loading the same compiled artifact, the ratio
was 1.01. `--additional-config` is part of vLLM's compile hash, so in the first run the
plugin server had compiled from scratch while stock loaded a cached artifact, and the gap
most likely came from the two servers running different compiled code
(`results/t4_run1_analysis/root_cause.md`; second-run record, section 4). The three
`prefill_allowance` modes were indistinguishable there, and the default stays `fixed`.

## Scheduler overhead

- Measured locally, policy work only (`results/sweep_prep/overhead_pure.md`): the
  plugin's own per-step work is 3.3 µs at 8 running requests untagged, 7.5 µs with bets,
  and 206 / 376 µs at 512. Low-power CPU cores; vLLM's own scheduling is not included.
- It grows linearly with the running batch, untagged traffic included (206 µs at 512),
  so "untagged traffic is scheduled exactly as stock" holds for decisions, not for cost.
  One cell is unexplained: 256 running with tags has p90 1,152 µs against p50 201 µs.
- No fast path. With no tags at all, the cost comes from classifying every running
  request in the prefill hook (`_reserve_prefill_lookahead`) and scanning `running` at
  step start. Skipping all sptc work while no tagged request exists would make an
  untagged deployment pay almost nothing; it is not implemented.
- Measured on vLLM 0.32 (second T4 run, `kaggle/overhead_bench.py`): the plugin adds
  1–17 µs to `schedule()` + `update_from_output()` per step at 8 running requests, where
  a decode step takes about 23–40 ms. All 24 cells are inside the pre-registered bounds
  (`results/kaggle_t4_v3/RESULTS.md`, section 5).

## How the policy was designed: the simulator

The policy came out of a GPU-free replay simulator (`sptc_sim/`). It runs spec-ptc's own
segmenter, shadow and claim code on a virtual clock, against a vLLM-V1-style server:
continuous batching, chunked prefill under a token budget, paged KV, recompute
preemption, prefix cache. Step time is a roofline plus framework overheads. Method and
results are in [report.md](report.md), the research appendix.

What it found, and what the plugin took from it (simulated):
- Correct speculation does not clog a server. Calls issued together get batched. The
  cost lands on other agents' root streams.
- Wasted speculation does. With one bad guess per call it is a net loss on the H100
  4B with CUDA graphs at 0.8/s (1.30×; median drift 1.19, just under the 1.2 cut for
  steady state, and one of three seeds is not steady), and on the RTX 4090 only at the
  edge of its capacity (1.41× at 0.15/s); 1.46× with batched programs on the H100 eager server,
  a cell not in steady state. Private system prompts per session, as in the bench.
  *Corrected October 20:* these read 1.22×, 1.47× (at 0.14/s, now 1.01×, break-even) and
  1.43× before the simulator's KV cache followed vLLM 0.32
  ([report, Correction](report.md#correction-october-20-the-simulators-kv-cache)).
- Admission control fixes it; ordering does not. Continuous batching admits work at
  once, so the cost shows up as slower steps for everyone, not as a queue to reorder.
  This is consistent with co-location work that serves best-effort work from leftover
  capacity (HyGen, Echo, ConServe, BROS, Niyama) and with vLLM issue #40004; it is not a
  new insight. Those papers are not claimed to have compared admission against
  ordering (Niyama's own mechanism is per-iteration relegation, an ordering policy).
- Separate bets from near-certain early work. Deprioritising all speculation throttles
  the critical path.
- The free window is a decode-cost knee: about 8 sequences for a 4B model at 8k
  context on an H100, about 4 for a 30B-A3B MoE.

How well it predicts real vLLM, after the T4 run (not pre-registered;
`results/kaggle_t4/RESULTS.md` section 5). The inputs taken from that run: the solo decode
and prefill measurements (`calib.json`), decode step time against the number of concurrent
decoders (`concur.json` M3, which gives the 0.44 ms per-sequence slope), per-call prompt
and output tokens from the suite runs (`suite.json`), and one client overhead fit on the
no-speculation suite. The load rows were not fitted.

| predicted quantity | median error | worst |
|---|---|---|
| spec-ptc suite wall time, 8 patterns (relative error) | 2.5% | 5.7% |
| load test session p50, 18 rows (stock and plugin), \|log(sim / measured)\| | 3% | 21% |
| load test root TPOT p50, 18 rows, \|log(sim / measured)\| | 5% | 22% |

- The worst row is stock vLLM with 8 agents and bad guesses: 8.21 s simulated vs 6.62 s
  measured, +24% as a plain relative error (root TPOT 48.6 vs 39.0 ms, +25%). It also
  misses the first run's light-load gap (above).
- This model has no `seq_cap`. The pre-registered P1 predictions for the second run
  (`results/prereg_v3/predictions.md`) add one, fitted on these same 18 rows.
- The predictions written *before* that run missed twice: each extra decoding sequence
  costs about 0.44 ms per step, and T4 prefill stalls were over-predicted 1.3–2.3×.
- An earlier version of this comparison reported worst errors of 16% and 17%. Part of
  that fit came from a replay bug, since fixed (`results/t4_run1_analysis/sim_vs_t4_compare.md`).
- The simulator now also models the plugin as built (`ServerConfig.plugin_semantics`: the
  gate inside vLLM's waiting loop, the end-of-step re-gate, the hold, no promotion), and
  vLLM's own priority scheduling as read from the source (policy `vllm-priority`).

## Why it matters beyond sPTC (simulated)

The census of 64,546 real tool calls
([report](report.md#update-first-checks-against-real-agent-code)) found that today's
code-mode agents make almost no bets, so the code-mode workload alone is a weak case for
a new request class. `results/general/general.md` simulates three workloads where
opportunistic work is common, on the T4 fit, an H100 with Qwen3-4B and an H100 with
Qwen3-30B-A3B. It was computed before the October 20 KV fixes; the numbers below are from
its re-run on the corrected simulator (`results/corrections/general/`, same sizes; old
values there).

- ReAct agents that guess the next LLM call (hit rates from SPAgent and PASTE, other
  settings). On the H100 4B config at 4–8 sessions/s, stock FCFS with 3 guesses per step
  is 46–119% slower than no speculation (with 1 guess, 3–37%). The plugin brings both to
  within 0.4%, and wasted work falls from 19–58% of tokens to 0.3–5%.
- vLLM priority with guesses at priority 1 is within ±0.3% of FCFS on every ReAct and
  branch cell except the top rate of each ladder and the T4 cells with 3 guesses from
  0.1/s (−3.2% to +5.8%), where stock FCFS is already 32–266% slower than no speculation.
- Where the plugin hurts:
  - On the T4 a window of 8 is not spare capacity: with 3 next-call guesses the plugin is
    still 3–28% slower than no speculation (though 8–81% faster than FCFS from 0.1/s).
    With 1 guess it is 5–12% slower from 0.15/s, and with action candidates 2–5%; at
    0.05/s both are faster than no speculation.
  - On the MoE, cheap action candidates already save 4–10% on stock vLLM; the plugin
    refuses most of them and is 4–9% slower than FCFS.
  - Launching both arms of an `if`: refused arms are re-run only after the condition is
    known, so the plugin is 6–31% slower than FCFS. Those calls should be tagged `early`
    (not simulated).
- Background batch jobs need their own class. With long jobs next to interactive
  agents on the T4 (0.05 sessions/s), interactive p50 is 1,087 s untagged, 126 s at
  priority 1 and 41 s with gated bets (24 s with no batch at all). But bets cost about
  50,300 refused requests per run, and the re-send rule turns a refused job back into
  normal work. The proposed `background` class queues instead of refusing and requeues
  instead of dropping (design only, not implemented).
- No cap arm. None of these workloads compares the plugin with a client-side or
  router cap on bets, so they do not show that the in-scheduler rules beat one. The T4
  runs measured that comparison later: a cap that counts every request in flight ties
  the plugin ([README](../README.md#benchmarks)).

Limits: 3 seeds and small runs; in the original run
the seed spread of session p50 is under 5% of the mean in only 37% of cells; no sweep of
free window or hit rate.

## Hardening (audit, October 20)

An audit of the plugins and the simulator found 44 issues: 3 high, 10 medium, 31 low.
Each was re-checked against the current code and decided:
- 37 fixed: defects in code, each with a local test that fails on the old code, and
  test gaps with new tests. All three high ones are fixed: a chunked bet that SGLang
  could never retract (#7), SGLang early requests starved when its truncation alignment
  exceeds the allowance (#22, deterministic inference on flashinfer), and the simulator
  admitting a request when only its first chunk fits (#32).
- 4 documented as one-step or by-design effects (#6, #20, #36, #40).
- 3 partly open: #2 is fixed in the vLLM plugin and mirrored in the simulator's model
  of the plugin (`plugin_semantics` with `plugin_fixes`; the report's idealised `agent`
  policy keeps the old order), but not in SGLang, so the two plugins now differ on that
  rule; #26 was left to the second run's allowance A/B, where the three modes were
  indistinguishable; #43
  (no recorded `tests_sglang` run) needs a GPU box with SGLang.
- The simulator fixes moved some of the report's headlines (the RTX 4090 loss is gone at
  the report's load):
  [report, Correction](report.md#correction-october-20-the-simulators-kv-cache).
- The smoke test's "45 → 39 ms" was withdrawn as evidence for the allowance (#41). The
  rewritten S3 ran in the second run: with `early` calls tagged, a concurrent normal
  stream's longest stall fell from 892 ms to 468 ms.
- The vLLM fixes have run on a GPU since the second T4 run. The SGLang fixes have not
  run on SGLang.

Per-finding decisions: [results/corrections/ledger.md](../results/corrections/ledger.md);
corrected simulator numbers in
[results/corrections/corrections.md](../results/corrections/corrections.md).

## Tests

```bash
uv venv --python 3.13 .venv
uv pip install -p .venv numpy pandas matplotlib scipy pytest
uv pip install -p .venv -e ../spec-ptc     # the local clone (pinned 9b78b7d)
uv pip install -p .venv -e .
.venv/bin/python -m pytest -q                       # simulator, workloads, comparison scripts
.venv/bin/python -m pytest -q integrations/tests    # scheduler plugins, no vLLM or SGLang needed
.venv/bin/python -m pytest -q kaggle/tests          # bench clients on the fake server (~1 min)
bash run_all.sh                                     # every number and figure in docs/report.md
```

The tool-latency sweep reads one day of the
[Copilot coding-agent dataset](https://github.com/Azure/AzurePublicDataset/releases/tag/ghcp-coding-agent-2026)
(CC-BY): put `date.2026-06-06.tar.gz` somewhere and set `COPILOT=/path/to/it`. It is
streamed, never extracted.

## The simulator

| Layer | Model | Validated against |
|---|---|---|
| Agent side | spec-ptc 0.1.1's own segmenter, peek planner, shadow and claim hooks, run single-threaded on a virtual clock (`trace.py`, `agent.py`); plus literal-only (Pydantic / pi-fabric), baseline, and a never-stall "dataflow" shadow | real spec-ptc with a deterministic mock LM: all 44 pattern×mode wall times within 1.2% |
| Server | continuous batching, chunked prefill under a token budget, paged KV with block accounting, recompute preemption, LRU prefix cache / TTL pinning / no cache, request abort; FCFS, vLLM priority, and agent-aware scheduling with or without the plugin's exact semantics (`server.py`); ReAct, branch and batch workloads (`general.py`) | spec-ptc's committed suite results (`runs.csv`, real vLLM): leave-one-out median error 2.3%; the T4 load test (table above) |
| Step cost | roofline over weight bytes touched (MoE expert loading included), KV bytes and FLOPs, plus framework overheads (`hardware.py`) | NVIDIA's Llama-3.1-8B H100 ITL-vs-concurrency table (within 6.5%); a published Qwen3-30B-A3B vLLM point (within 6.5%) |
| Workloads | spec-ptc's 22 suite programs; RLM-style multi-turn sessions over a long context (`workloads.py`); tool latencies from the GitHub Copilot 2026 agent dataset | — |

```
sptc_sim/
  des.py        event kernel (processes on a heap)
  hardware.py   GPUs, model shapes, step-cost roofline, overhead regimes
  server.py     the continuous-batching server
  general.py    ReAct / branch / batch workloads and their server
  trace.py      response -> timing-free op trace, using spec-ptc's own code
  agent.py      virtual-time replay of a turn under a policy
  session.py    multi-turn sessions, load generators, metrics
  workloads.py  RLM-style programs
  calib.py      calibration helpers;  suite.py  spec-ptc suite loader
  plots.py      figures
experiments/    validation, calibration, sweeps, T4 comparison, predictions and scoring
results/        CSV/JSON outputs, markdown tables, figures
```

Using it for your own question:

```python
from sptc_sim.des import Sim
from sptc_sim.hardware import GPUS, MODELS, GRAPHS, StepCost
from sptc_sim.server import Server, ServerConfig
from sptc_sim.agent import OutputModel, PolicyCfg, ServerBackend
from sptc_sim.session import run_session
from sptc_sim.workloads import session_turns, output_weight

sim = Sim()
server = Server(sim, StepCost(GPUS["RTX4090"], MODELS["Qwen3-4B"], ov=GRAPHS),
                ServerConfig(max_batched_tokens=2048))
backend = ServerBackend(sim, server, OutputModel(mean=1.0, weight=output_weight))
p = sim.process(run_session(sim, server, backend, session_turns("rlm_map"),
                            PolicyCfg("shadow"), sid=0))
sim.run(until=p)
print(p.value.latency, [r.tpot for r in p.value.roots])
```

Any code-mode program can be a workload: write the model's response text with
` ```repl ` blocks and pass it to `trace.compile_turn`.
