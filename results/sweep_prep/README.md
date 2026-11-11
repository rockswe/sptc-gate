# Baselines, a load sweep and scheduler overhead: preparing the second T4 run

**Update.** The sweep now runs from `kaggle/sptc_kaggle_v3.ipynb`, section C,
after the regression A/B; the stock and priority servers carry the plugin-fixed arm's
`--additional-config` so all three share one compiled artifact. For scoring, the
predictions here are replaced by `results/prereg_v2/` (same harness, plugin arms with
`plugin_semantics`). The run's results are in `../kaggle_t4_v3/RESULTS.md`. Where the
text below says "needs the GPU" or "not run yet", it describes the state before that run.

This prepares the GPU measurement that turns the plugin into an engineering
result. It compares the plugin against vLLM's own priority scheduling, sweeps load to
saturation with repeats and goodput, and measures scheduler overhead.

**No GPU was used.** Each item says what is:
- read from source: from the vendored vLLM 0.32.0 code;
- tested locally: run against fakes;
- measured locally: CPU-only numbers;
- predicted: from the simulator;
- needs the GPU: prepared for the Kaggle T4 run.

| item | where | status |
|---|---|---|
| how vLLM 0.32 priority scheduling works | `vllm_priority_semantics.md` | read from source, with file:line references |
| simulator policy `vllm-priority` | `sptc_sim/server.py` | 4 unit tests (`tests/test_sim.py`) |
| bench arms `prio/*` (stock vLLM, `--scheduling-policy priority`, speculative calls at priority 1) | `kaggle/vllm_bench.py` | tested locally against the fake server; **needs the GPU** |
| saturation sweep: 9 arms, a ladder of loads, 3 repeats, resume | `kaggle/vllm_bench.py sweep / report / plan` | tested locally end to end; **needs the GPU** |
| fake OpenAI-compatible server and tests | `kaggle/fake_openai_server.py`, `kaggle/tests/` | 34 tests, pass locally |
| scheduler overhead, vLLM | `kaggle/overhead_bench.py vllm` | **needs vLLM** (CPU is enough; runs in the notebook) |
| scheduler overhead, the plugin's own policy work | `overhead_pure.md` | measured locally |
| predictions for the sweep | `predictions.md`, `predictions_table.md`, `predictions.json`; seq_cap 32 sensitivity: `predictions_seqcap32_table.md`, `predictions_seqcap32.json` | predicted, committed before any GPU run |

## 1. Priority scheduling as a baseline

Summary of `vllm_priority_semantics.md`:
- vLLM's priority option only reorders the waiting queue: lower value first, then arrival.
- It never preempts on arrival.
- It does not reorder the running batch's token budget.
- It picks the lowest-priority request as the victim only when a running request needs
  KV blocks.
- It has no admission control. A low-priority request joins a batch whenever there is
  room.

So, before requests queue or KV runs out, it behaves like FCFS.

**Simulator:**
- The new `vllm-priority` policy implements exactly this.
- The old `priority` policy is kept as an idealized strict priority. That policy also
  reorders the token budget and promotes claimed calls, which vLLM does not.

**Bench arm:**
- server `vllm serve ... --scheduling-policy priority`;
- spec-ptc's speculative dispatches and the decoys sent with `"priority": 1`;
- everything else at the default 0.
- The plugin refuses priority scheduling, so the plugin arms run FCFS.

## 2. The sweep (`kaggle/vllm_bench.py sweep`)

- Arms. An arm is one line in `ARMS`: server setup, client tagging, workload. There
  are 9: `{fcfs, prio, plugin} × {nospec, spec, spec+bad}`.
  - "spec+bad" adds one decoy per speculative call: a raw completion forced to the
    maximum length, never used, cancelled at turn end. These are the same decoys as in
    the first T4 load test.
  - Servers are in `SERVERS`, workloads in `WORKLOADS`. A new arm is one line.
- Presets.

  | preset | arms | agents | repeats | estimated GPU time (P1 session times) |
  |---|---|---|---|---|
  | `quick` | 4 | 1, 4 | 1, 2 turns | 16 min |
  | `core` | 7 (no `prio/nospec`, `plugin/nospec`) | 1, 4, 8, 16, 24 | 3 | 100 min |
  | `full` | 9 | 1, 2, 4, 8, 12, 16, 24, 32 | 3 | 211 min (includes core) |

  - The estimates include 4 minutes per server start and 20 s of process start-up per
    run. They are upper bounds: an arm's ladder stops once a run times out or its
    session p50 exceeds 4× its own 1-agent value.
  - 48 agents were left out of the ladder. The simulator puts the no-speculation knee
    there (P1), but 48 client processes on Kaggle's 4 vCPUs would likely measure the
    client.
- Resume.
  - Each (arm, load, repeat) is one JSON file, written atomically as soon as the run
    ends. A rerun skips finished files.
  - The notebook copies the runs of an earlier session's zip back in.
  - A failed run (worker error, dead process, an empty root stream) is retried once.
- Fair runs.
  - All agents of a run are released together, after every process has imported
    spec-ptc.
  - Arm order rotates per repeat.
  - Every run, and every retry, gets its own prompt prefix, so no run gets prefix-cache
    hits from another.
- Metrics (`report`; the same `summarize()` scores the predictions):
  - session p50/p99 and root TPOT p50/p99. The p50s get 95% two-level bootstrap CIs
    (resample repeats, then sessions);
  - the p99s get no CI. They are nearest rank across sessions, so below 100 sessions
    (up to 8 agents × 4 turns × 3 repeats) the p99 is the slowest session. The table
    marks those cells "(max)". A bootstrap of a maximum collapses to a zero-width bracket;
  - root TPOT is each session's mean (span / (tokens − 1)). Its p99 is a tail across
    sessions, not a token-level tail;
  - median of per-session root inter-token-gap p99 (reported, not part of the SLO);
  - sessions per minute;
  - goodput, each half of its SLO alone, and the goodput curve for multipliers 1–5×;
  - knee against the arm's own 1-agent p50, and against stock FCFS's 1-agent p50 of the
    same mode (`knee_ref`), with the growth ratio at every load;
  - decoy outcomes, preemptions, peak waiting requests and peak KV use (from `/metrics`);
  - CPU: the agents' own share (`client_cpu_util`) and the whole host's, from
    `/proc/stat` (`host_cpu_util`, `host_cpu_sat_frac`). Only the second includes vLLM's
    API server and engine core, which share Kaggle's 4 vCPUs with the agents. A row is
    `cpu ok` if every run averaged under 0.85 of the host with under 10% of its seconds
    at ≥ 95%.
- Goodput.
  - Definition: the fraction of sessions with wall ≤ 2× and root TPOT ≤ 2× the
    `fcfs/nospec` 1-agent median of the same pattern.
  - Thresholds: `--slo-session`, `--slo-tpot`, `--slo-ref`.
  - It is not a capacity measure for the speculative arms. Their sessions are about
    2.4× shorter than the no-speculation references, so the wall half almost never binds
    inside the ladder. For them goodput is in effect "root TPOT ≤ 2× the stock 1-agent
    root TPOT". Speculation beside the root raises root TPOT by design. Use the knee and
    throughput for saturation, and read goodput as the root stream's SLO.
- Decoy outcomes. Every decoy is logged as completed, rejected
  (`sptc_bet_rejected`, or a stream with no token and no finish reason), dropped
  (`sptc_bet_dropped`) or cancelled. This removes the old caveat "the client does not log
  decoys".
  - One limit: vLLM's completion streamer skips any chunk with no text and no tokens
    (`vllm/entrypoints/openai/completion/serving.py:372-379`). So a running bet that the
    plugin drops before its first token reaches the client exactly like a rejected one.
    "Rejected" therefore means refused *or dropped before its first token*; "dropped"
    counts only drops after at least one token. The simulator's predictions use the same
    split. The fake server behaves like vLLM here, so the tests cannot separate them
    either.

**Changes from the first T4 load test:**
- The HTTP client is now the standard library, not the openai package. It reads
  `stop_reason` directly and can cancel a stream that is still queued.
- Speculative calls stop when spec-ptc evicts them, as spec-ptc's own engine does.
- Agents start together, behind a barrier.
- Prompts carry a per-run prefix.
- Decoys still queued at turn end are cancelled at once. Before, they stayed queued until
  their first token.

Because of these changes, the sweep's 1/4/8-agent points are not the old rows rerun.
They are close, but not identical, conditions.

## 3. Robustness

The first Kaggle load test failed silently inside its worker processes.
`kaggle/fake_openai_server.py` is a stdlib asyncio server that imitates what the bench
relies on:
- vLLM's streaming format: per-chunk logprob tokens, `finish_reason` and `stop_reason`,
  usage, `[DONE]`;
- a batch loop with deterministic timing;
- FCFS or priority admission;
- the plugin's reject and drop, including vLLM's zero-token stream for a rejected bet;
- aborts on client disconnect;
- `/metrics`;
- a fault injector for an empty root stream.

`kaggle/tests/` has three files:
- `test_bench.py` (31 tests, ~8 s): the client and every outcome, the request fields
  per tag scheme, cancellation of running and queued streams, the statistics, goodput,
  the saturation rule and the resume bookkeeping.
- `test_bench_e2e.py` (~50 s): runs `sweep --launch` with the fake server in place of
  `vllm serve`, 4 arms × 2 loads, with spec-ptc's real harness in spawned agent
  processes. It checks:
  - each arm's request fields;
  - each decoy's outcome;
  - that an injected silent failure is caught and retried;
  - resume: nothing redone, then exactly one lost file redone.
- `test_overhead_bench.py` (2 tests, under a second): the overhead benchmark without
  vLLM. It runs the pure-policy case for real and checks the vLLM case's plumbing on a
  stand-in scheduler.

What the fake cannot show:
- real vLLM timing;
- vLLM's actual priority heap and preemption;
- the plugin's real gate.

Those need the GPU run. `integrations/tests_vllm/test_overhead_bench.py` checks the
overhead benchmark's setup on real vLLM.

## 4. Scheduler overhead

- `overhead_bench.py vllm` (needs vLLM, CPU only). It times `schedule()` and
  `update_from_output()` per step:
  - three schedulers: stock vLLM, the plugin with untagged traffic, and the plugin with a
    quarter of the running requests as bets;
  - 8 to 512 running decodes, plus half as many waiting;
  - sync and async scheduling.
  - Reported in microseconds per step. **Not run yet.**
- `overhead_bench.py pure`. It times the plugin's own per-step work, following its
  hooks' code paths, on plain objects (`overhead_pure.md`):
  - Source: measured locally on low-power CPU cores (so slow), 300 steps per row.
  - Result: about 0.4 µs per running request per step with untagged traffic. The
    plugin's prefill-allowance hook classifies every running request. With running bets
    it is about 0.75 µs, because the running list is also re-ranked.
  - In context: that is 3–8 µs at 8 requests and 0.2–0.4 ms at 512. A T4 decode
    step is 16 ms at batch 1 and longer at large batches, so this is under 0.1% at 8
    and under 1% at 512, even on these slow cores.
  - Not included: vLLM's own scheduling cost and the cost of calling the hooks.
- Possible cheap fix (not made). In
  `_reserve_prefill_lookahead`, check `is_prefill` before classifying. Decodes would
  then skip the classification entirely.

## 5. Predictions

See `predictions.md`. In short, for the primary set P1:
- vLLM's priority scheduling should not help anywhere in the ladder.
- Stock speculation with bad guesses should become a net loss at 24 agents.
- With the plugin, bad guesses should cost nothing from 8 agents on.
- The plugin should not delay saturation itself: its knee differs from stock FCFS's
  only on a knife edge.

These hold for `seq_cap` 24 and 32 alike. The fit cannot choose between the two,
and some knee and goodput loads do depend on it; `predictions.md` marks them.

Set P0, which has no load-row calibration, already fails one known row. That is why P1
exists.

## Open issues

- `experiments/t4_validate.py`'s `MeasuredBackend` shares per-call token counts through
  the backend object. Calls started at the same instant take the last one's values. A
  decoy usually ran at its real call's length, not 96 tokens. This affects the
  bad-guess rows of `results/kaggle_t4/sim_vs_t4.md`. It is not fixed there;
  `experiments/sweep_predict.py` avoids it.
- `kaggle/make_bundle.sh` excludes `results/` except `calibration.json`, so the
  bundle lacks `results/sweep_prep/predictions.json`. On Kaggle, `plan` then falls back to a
  rule of thumb. The numbers above are the real estimate.
- The simulator's `agent` policy also orders work by agent-program start. The
  vLLM plugin is plain FCFS there. In these predictions it changes `plugin/spec`
  relative to `fcfs/spec` by about 1%.
- The decoys are still the synthetic "one per call, forced to maximum length".
  Workloads where bets are common are in `results/general/`. A new workload is one
  `WORKLOADS` entry plus arms.
