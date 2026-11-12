# sptc-gate

Admission control for speculative LLM calls on a shared vLLM/SGLang/Tensor-RT LLM server.

Agents increasingly fire LLM sub-calls before they know they need them: speculative tool
calls, guessed next steps, prefetches. On a shared vLLM server that work is
indistinguishable from the requests users are waiting on, so every wrong guess slows every
stream. This repository contains:

- a scheduler plugin for vLLM 0.32 (`--scheduler-cls`, no fork), with a port to SGLang
  0.5.22. It adds a best-effort request class: a request tagged `bet`, a speculative call
  that may never be used, runs only on spare capacity, is refused at once when there is
  none, and is dropped first under KV-cache pressure;
- benchmarks of that plugin on an NVIDIA Tesla T4 against stock vLLM, vLLM's priority scheduling
  and a client-side cap;
- a record/replay benchmark for agent sessions, and patches to
  [spec-ptc](https://github.com/alexzhang13/spec-ptc), Alex Zhang's client for
  speculative programmatic tool calling, measured with it on an NVIDIA H100;
- the discrete-event simulator that picked the policy before any GPU time was spent.

## Findings

1. Wasted speculation is expensive on a shared server, and admission control removes the
   cost. With 8 agents each wasting one speculative call per real one, the plugin cut
   median session latency by 31%, to within 3% of the same agents with no waste. vLLM's
   priority scheduling did nothing.
2. Admission control does not need a new scheduler. A client-side cap that counts every
   request in flight did as well as the plugin in every condition measured, including
   KV-cache pressure and a real queue. The plugin stays as a reference implementation and
   test harness, and the upstream RFC that was drafted was never posted
   ([why](docs/related_work.md#the-rfc-that-was-drafted-and-held)).
3. Refusing bets that are sometimes needed costs more than it saves. Letting them wait
   does not.
4. Real agent code placed no bets. On an NVIDIA H100, spec-ptc launched 17,206 speculative calls
   on its own benchmark and every one was used. What held sessions back was the client's
   cap of 16 calls in flight, and a client that sets its limits from the engine's
   `/metrics` did as well as the best hand-tuned number.

## Benchmarks

### sptc-gate scheduler plugin vs. stock vLLM (NVIDIA Tesla T4)

NVIDIA Tesla T4, Qwen3-1.7B fp16, vLLM 0.32. Agents share one server, and each wastes one
speculative call per real one. Every arm runs the same spec-ptc client, with request tags
added, so the comparison is between engines. 2 server launches per arm, 3–5 repeats.

With 8 agents:

| | stock vLLM | vLLM priority scheduling | plugin |
|---|---|---|---|
| session latency, p50 | 7.49 s | 7.41 s (no change) | **5.20 s (−31%)** |
| time per output token, p50 | 39.4 ms | 39.5 ms | **28.6 ms (−27%)** |
| worst session's time per output token | 46.6 ms | 46.4 ms | **33.3 ms (−29%)** |

- Priority scheduling orders the waiting queue, but continuous batching admits everything
  at once, so in these runs nothing waits. Once a wasted request is running, it slows
  every decode step.
- With the plugin, 8 agents with wasted speculation ran within 3% of 8 agents without any
  (5.20 vs 5.05 s).
- At 4 agents the plugin cuts session latency 25%. At 1 agent the median improves 10%,
  but the slowest session got 15% slower, because bets admitted into spare capacity
  decode next to the user's stream.
- Untagged traffic is scheduled exactly as stock: a step-by-step differential test
  against vLLM's own scheduler checks this, and the measured ratio is 0.997.

Could a client-side cap do the same? Yes, in every condition measured. Session p50
relative to stock vLLM with wasted speculation:

| approach | 4 agents | 8 agents | 4 agents, KV pressure |
|---|---|---|---|
| vLLM priority, only speculative calls deprioritised | 0.996× (no help) | 1.006× (no help) | 0.870× |
| client-side semaphore: at most 8 speculative calls in flight | 0.883× | 0.810× | - |
| client-side cap that counts every in-flight request, user streams included | 0.807× | **0.714×** | 0.689× |
| plugin | **0.780×** | 0.718×* | **0.676×** |
| no wasted speculation at all (the floor) | 0.781× | 0.713× | 0.667× |

\* Void under the pre-registered validity rule: the benchmark's host CPU saturated in that
cell. Shown for reference.

- A cap that sees every request in flight ties the plugin. Without pressure, the plugin
  is 3% better at 4 agents and sits on the floor, and at 8 agents the cap reaches the
  floor too. Under KV pressure the plugin is 1.8% faster with worthless bets (0.982) and
  equal with useful ones (1.000). The pre-registered bar for an engine-side win was 5%.
- A naive semaphore that only counts speculative calls is 13% slower than the plugin,
  because it admits them into a batch that is already full.
- The reasons for putting the rule in the engine are still arguments, not measurements.
  The cap ran inside one benchmark process that saw every agent's requests, which is a
  best case for a cap; across clients it would need a proxy with that view. Dropping
  running bets never fired in a load run, and decisions made per scheduler step did no
  better than the cap under pressure.

Details and raw data: [`results/kaggle_t4_v3/RESULTS.md`](results/kaggle_t4_v3/RESULTS.md).

### Under KV-cache pressure

4 agents share a server squeezed to 2,064 tokens of KV cache. There, stock vLLM with
wasted speculation preempted 192 times per run and had a request waiting 42% of the time.
Session p50 relative to stock vLLM, which admits every bet. 3 repeats on 2 server launches
per arm:

| workload | client-side cap | plugin | vLLM priority, bets only | no speculation |
|---|---|---|---|---|
| one worthless bet per real speculative call | 0.689× | **0.676×** | 0.870× | 1.641× |
| real speculative calls are bets too; half of all bets are needed | 1.505× | 1.506× | **0.915×** | 1.641× |

- Worthless bets: the cap and the plugin both refuse nearly all of them, and run close to
  no waste at all (0.667×).
- Bets that are sometimes needed: both gates are 1.5× slower than stock. They refused
  91–94% of the real bets, and spec-ptc stops speculating for the rest of a turn when a
  bet it needs is refused, so most of the speculation was lost.
- Priority, which only makes bets wait, was 1.65× faster than the plugin there. Waiting
  beats refusing when bets may be needed.

Details and raw data: [`results/kaggle_t4_v4/RESULTS.md`](results/kaggle_t4_v4/RESULTS.md).

### Client patches vs. stock spec-ptc (NVIDIA H100)

One NVIDIA H100, Qwen3-30B-A3B, vLLM 0.32, spec-ptc's own OOLONG campaign, 8 sessions at a time.
Live repeats of one task differed by a factor of 1.9, so recorded sessions were run again
on the engine with everything fixed but the client's policy. A replay repeats within
1–2%. "Stock spec-ptc" is the client unmodified at commit `9b78b7d`.

Session time relative to stock spec-ptc, summed over 10 replayed sessions. Below 1 is
faster:

| client | first launch | second launch |
|---|---|---|
| no speculation | 1.12 | - |
| stock spec-ptc | 1.00 | 1.00 |
| patched: scout, 16 calls in flight as in stock | 1.00 | - |
| patched: scout, 128 calls in flight | **0.87** | 0.86 |
| patched: scout, adaptive limits | - | **0.85** |
| patched: the same, and the scout continues past a test that cannot leave its loop | - | **0.82** |

The scout is a pass that launches every call whose arguments are already known. With
adaptive limits the client sets its own window from the engine's `/metrics`.

- On the code the model writes when nothing is failing under it, the scout adds nothing
  to stock spec-ptc at the stock window (1.00): the model batches its calls, and spec-ptc
  already launches those batches ahead.
- The first replay, registered on 8 sessions, had the scout at 0.72. That gain came from a
  bug in rlms, which lost batch prompts: the loop the scout removed was the model's way
  around it. The 1.00 is the same measurement with rlms fixed, on 10 sessions.
- What is left to win is the window: 128 in flight takes 13% off session time, most of it
  in one session. On loops of small batches the window needs speculation to use it.
- The client can set the window itself. With adaptive limits it took 0.985 of the
  hand-tuned client's session time (0.85 against 0.86 of stock: a tie, with one unit per
  arm), and its root streams were 1.4% longer than the stock client's. The root is the
  agent's own model stream, which a user waits on. On an engine limited to 16 concurrent
  sequences the same client closed its windows, where a fixed 128 made one root turn in
  four wait more than 5 s for its first token.
- The 0.82 is one loop in one session: a loop that tests each result went from 58 s to
  14 s once the scout continued past the test.
- Long prompts are held back by a second limit in stock spec-ptc, a budget of 120,000
  characters in flight. One turn with four long calls took 537 s with stock spec-ptc,
  354 s with the adaptive client's KV pool and 184 s with no budget at all: lifting the
  budget beat the pool here. With that session included (11 sessions), the adaptive
  client is at 0.81 of stock and the control with no budget at 0.75.
- The engine was never the limit.
- None of these numbers is comparable with spec-ptc's published 1.0–1.2×. That is its
  fan-out mode, measured live; this is its streaming mode, on replays.

The full study, with the replay method, the caveats and the bugs found in rlms, spec-ptc
and vLLM: [`docs/h100-study.md`](docs/h100-study.md).

## How it works

One request field picks the class:

```python
client.chat.completions.create(..., extra_body={"vllm_xargs": {"sptc_class": "bet"}})
```

| class | meaning | scheduling |
|---|---|---|
| `bet` | may never be used | admitted only on spare capacity, otherwise refused at once; dropped first under KV pressure, never recomputed |
| `early` | sent ahead, almost surely used | normal admission; its prefill shares a small per-step token allowance |
| *(none)* | normal work | stock vLLM, step for step |

Spare capacity is checked every scheduler step. A bet is admitted only if:

- no normal request is waiting;
- one more sequence fits the decode "free window";
- KV usage is under 90%.

A refused bet returns at once with `stop_reason="sptc_bet_rejected"`. The client re-sends
it as normal work if it turns out to be needed.

## Quick start

```bash
pip install -e integrations --no-deps
vllm serve Qwen/Qwen3-1.7B --scheduler-cls sptc_vllm.scheduler.SptcScheduler \
  --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1}}'
```

The full rules, the knobs and the SGLang port are in
[`integrations/README.md`](integrations/README.md).

## Design and testing

- No fork. The plugin subclasses vLLM's scheduler and overrides six narrow hooks. No
  block of `schedule()` is copied.
- Identical for normal traffic. A differential test runs seeded random workloads, with
  preemption under a full KV cache, through stock vLLM and the plugin in lockstep, and
  compares every step's scheduler output. On vLLM 0.32, 407 of 408 tests pass; the one
  failure was a bug in a logging test, since fixed.
- Low overhead. The plugin adds 1–17 µs per scheduler step at 8 running requests. A
  decode step on the T4 takes 23–40 ms.
- Designed with a performance model. A discrete-event simulator of vLLM-V1 continuous
  batching (chunked prefill, paged KV, preemption, prefix caching, roofline step costs)
  picked the policy before any GPU time was spent. It predicted the first T4 load tests
  with 3% median error.
- Pre-registered. Predictions for every GPU measurement were written down before the
  run, with their sha256 recorded, and the refutations are reported:

  | run | outcome | scorecard |
  |---|---|---|
  | second T4 run | 74 supported, 8 refuted | [`prereg_compare.md`](results/kaggle_t4_v3/prereg_compare.md) |
  | third T4 run, under KV pressure | the claims that decided the outcome held, but the point predictions missed by a median 15%: the simulator overestimated what preemption costs | [`prereg_compare.md`](results/kaggle_t4_v4/prereg_compare.md) |
  | NVIDIA H100 replay, and its follow-up | 8 of 11 held, then 6 of 8 | [`RESULTS.md`](results/modal_h100_replay/RESULTS.md#1-the-predictions) |
  | NVIDIA H100 recording with rlms fixed, and its replay | 4 of 6, then 14 of 15 | [`RESULTS.md`](results/modal_h100_record/RESULTS.md#5-the-replays-predictions) |
  | adaptive limits, on a T4 and on the NVIDIA H100 | 12 of 13, and 21 of 21 | [`RESULTS.md`](results/modal_govern/RESULTS.md#3-run-2-the-h100-and-its-predictions) |

  This repository is a single snapshot of the finished project. The records cite commit
  ids from the working history, such as the commits that fixed each run's predictions.
  That history is not included, so those ids do not resolve here and the timing rests on
  the records themselves. The pre-registration documents, the prediction files and the
  campaign scripts were also edited for publication: wording about the working process
  (schedule, planning notes, costs) was removed and list formatting was simplified. No
  prediction, bound or rule was changed, and the two T4 output zips were repacked with
  the edited prediction files. File hashes quoted in the run records are of the files
  as they were at run time, so they differ from the published copies.

- Audited. An audit of the plugins and the simulator found 44 issues; 37 are fixed, each
  with a regression test ([ledger](results/corrections/ledger.md)). The audit also
  corrected an earlier simulated headline (1.47× → 1.01×), published as a correction.
- A suspected regression, settled. A light-load slowdown seen in the first run (+13.5%)
  did not reproduce once stock and the plugin ran the same compiled code (ratio 1.01).

### Tests

The simulator replays spec-ptc's own code, so it needs a clone of spec-ptc at commit
`9b78b7d` next to this repository:

```bash
uv venv --python 3.13 .venv
uv pip install -p .venv numpy pandas matplotlib scipy pytest
uv pip install -p .venv -e ../spec-ptc
uv pip install -p .venv -e .
.venv/bin/python -m pytest -q                      # simulator: 159 tests
.venv/bin/python -m pytest -q integrations/tests   # both plugins, no vLLM or SGLang installed: 284 tests
.venv/bin/python -m pytest -q kaggle/tests         # benchmark clients on a fake server: 67 tests, about 2 minutes
```

81 of the plugin tests check the plugins against the vLLM 0.32 and SGLang 0.5.22 source
trees and are skipped when those are not next to the repository
([`integrations/README.md`](integrations/README.md#tests)). The campaign and the replay
benchmark have 89 more tests, with their own environment:
[`cloud/README.md`](cloud/README.md#local-tests).

## Limitations

- Small scale: one T4, one 1.7B model, at most 8 agents (4 under KV pressure). Runs at
  16+ agents saturated the benchmark's host CPU and are void under the pre-registered
  validity rule.
- The NVIDIA H100 runs are small too: 8 tasks, one model, one workload, 8 sessions at a time,
  one unit per arm. Two things were not put to a test, and they are where these results
  are thinnest: several clients on one engine with a load that changes, and a second
  workload ([more](docs/h100-study.md#limitations)).
- Synthetic waste: the wasted calls on the T4 are decoys that are never used. Real
  code-mode speculation makes far fewer bets ([census](results/census/SUMMARY.md)), and
  on real RLM code spec-ptc made none.
- The agent library is part of what was measured. In the T4 runs spec-ptc stopped
  speculating for the rest of a turn when a bet it needed was refused. A client that
  keeps going was built and measured since, on a T4, and it helps a little: refusing bets
  that are needed half the time cost 1.94× stock with the old client and 1.82× with the
  new one for the cap, 2.05× and 1.77× for the plugin (geometric mean over four
  programs). No speculation costs 1.84×
  ([T4 check](results/modal_t4_bench/RESULTS.md)).
- The SGLang port is tested against SGLang's own scheduling code, not yet on a live
  SGLang server.
- sptc-gate was only measured on the vLLM engine, although both SGLang and Tensor-RT LLM
  ports have been tested against their own scheduling code and is working.
- Novelty is narrow. Best-effort / scavenger classes are a known idea (Echo, HyGen, vLLM
  RFC #24256). What is new is applying one to speculative LLM sub-calls inside the
  per-step scheduler, with near-certain speculation exempted
  ([related work](docs/related_work.md)).

## Repository layout

```
integrations/sptc_vllm/      the vLLM plugin (policy.py is pure; scheduler.py is the adapter)
integrations/sptc_sglang/    the SGLang port
integrations/spec-ptc-fork/  the spec-ptc client changes, as patches
sptc_sim/, tests/            the simulator used to design the policy, and its tests
experiments/                 simulator experiments, pre-registered predictions and their scoring
kaggle/                      T4 benchmarks and notebooks
cloud/                       the NVIDIA H100 campaign and the replay benchmark, on Modal
results/                     every measured and simulated number, with sources
docs/                        the write-ups below
```

## Documentation

| document | contents |
|---|---|
| [`docs/h100-study.md`](docs/h100-study.md) | the NVIDIA H100 study: the replay method, adaptive limits, bugs found |
| [`docs/design-notes.md`](docs/design-notes.md) | design notes: how the plugin behaves, the simulator, the audit |
| [`docs/report.md`](docs/report.md) | the simulation study behind the design |
| [`docs/related_work.md`](docs/related_work.md) | prior work, what is new here, and the vLLM RFC that was drafted and held |
| [`integrations/spec-ptc-fork/README.md`](integrations/spec-ptc-fork/README.md) | what each client patch does |
| [`cloud/README.md`](cloud/README.md) | running the campaign and the replay benchmark |

## License

MIT. See [`LICENSE`](LICENSE).
