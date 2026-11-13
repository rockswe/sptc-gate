# cloud/: the OOLONG RLM campaign and the replay benchmark, on Modal

Runs spec-ptc's own OOLONG campaign (`benchmark/oolong_campaign`, unmodified, commit
`9b78b7d`) three ways on one vLLM engine with the campaign's server flags. Results of the first
runs (November 9–10, 2026): `../results/modal_h100_rlm/RESULTS.md`. The replay of those
runs: `../results/modal_h100_replay/RESULTS.md`. A recording with rlms' batch path fixed,
and its replay: `../results/modal_h100_record/RESULTS.md`.

The commands in this file run from `cloud/`, inside the environment set up under
[Local tests](#local-tests). `../../_modal_runs/` is a directory next to the repository
where runs are downloaded: raw events hold OOLONG text, so they stay out of git.

The work came in stages. Each has its own record:

| stage | what | result |
|---|---|---|
| 1 | the campaign, and the gate (`GATE.md`) | `../results/modal_h100_rlm/RESULTS.md` |
| 2 | spec-ptc survives a refused call | the client patches; `../results/modal_t4_bench/RESULTS.md` |
| 3 | the scout pass, the window as a parameter, a batch launched as a batch | the client patches, off by default |
| 4 | a replay of the recorded runs | `../results/modal_h100_replay/RESULTS.md` |
| 5 | a recording with rlms' batch path fixed, and its replay, in place of a live run with the patched client | `PREREG_RECORD.md`; `../results/modal_h100_record/RESULTS.md` |
| 6 | a window and a KV admission that follow the engine's load, and a scout that goes on past a test that cannot leave its loop. Bets across turns were not started | `PREREG_GOVERN.md`; `../results/modal_govern/RESULTS.md` |
| 7 | the window that follows the load, on a TensorRT-LLM server in place of vLLM. A check of what the client reads there, with no rule fixed before it | client patches 8 and 9; `../results/modal_trtllm/RESULTS.md` |

The client patches are in `../integrations/spec-ptc-fork/`. "The fork" below is spec-ptc
`9b78b7d` with all of them applied.

| arm | REPL | what speculation does |
|---|---|---|
| `nospec` | rlms `LocalREPL` | nothing: sub-calls run when the program reaches them |
| `fanout` | spec-ptc `SpeculativeLocalREPL` | a shadow pass over each finished block, then the real run. This is the mode behind spec-ptc's published 1.0–1.2×, because rlms 0.1.3 doesn't stream |
| `stream` | `rlm_stream.StreamingSpecREPL` | the root's tokens feed spec-ptc while they stream: sPTC as the blog describes it |

Files:

- `GATE.md`: the question this run decides and its rule, fixed before the main run. The
  campaign records the file's sha256 before its first unit. Never edit it after a run.
  (The published copies of this file and of the `PREREG_*.md` files were reworded after
  the runs, so they no longer match the recorded hashes:
  [README](../README.md#design-and-testing).)
- `GATE_ADDENDUM.md`: why the rerun uses a 65,536-token window, written before it started
  and recorded the same way.
- `rlm_stream.py`: `StreamingRLM`, which streams the root call with the same request
  rlms sends, and `StreamingSpecREPL`. Per turn it logs root TTFT and TPOT, the arrival
  time of every delta, the shadow's wait after the stream, and the real run's time.
- `rlm_campaign.py`: the driver.
  - `tasks` builds `tasks.json` from the campaign's `load_tasks(4, 4, seed=7)`.
  - `run` runs the units (arm × concurrency × repeat, in ABBA order), with a warm-up, a
    0.5 s `/metrics` poller per unit, a budget stop, and resume.
  - `summarize` writes the tables, the time shares and the gate's verdict.
  - `compact` writes `trajs_compact/` for each unit (the campaign does it as each unit
    finishes): the trajectories without the REPL's variables and the message history.
- `analyze.py`: offline, from a downloaded run: time budget, sub-call work, root stalls,
  what speculation did, why the speculative arms still waited (turn by turn), and the
  noise floor between repeats.
- `oracle.py`: offline, from the `nospec` trajectories: how much of the sub-call time is
  independent calls waiting on each other.
- `to_census.py`: the recorded replies as input for `../experiments/census.py`.
- `bench_app.py`: `../kaggle/vllm_bench.py` on a Modal T4, in place of the Kaggle
  notebooks. `bench` runs a sweep preset with the old or the new spec-ptc client; `suite`
  runs fixed programs with and without the scout. First runs:
  `../results/modal_t4_bench/RESULTS.md` (a 6-arm sweep took 23 minutes).
- `trtllm_probe_app.py`: the governed client against TensorRT-LLM 1.4.0rc3 on a Modal L4
  (`check`, `mpi`, `probe`). Below, under "On a TensorRT-LLM server".
- `both_compare.py`: two `both_default` sweeps, per pattern.
- `repl_fix.py`: makes rlms' `LocalREPL` safe as concurrent threads. Below.
- `app.py`: the Modal app (`probe`, `prepare`, `campaign`, `compact`).
- The replay bench, below: `replay_corpus.py`, `replay.py`,
  `replay_campaign.py`, `replay_report.py`, `replay_app.py`. `PREREG_REPLAY.md` is what
  the fork should recover, fixed before the H100 run, and `PREREG_REPLAY_ADDENDUM.md` the
  same for its follow-up. Results: `../results/modal_h100_replay/RESULTS.md`.
- Recording with rlms fixed, below: `batch_fix.py`, `rlm_record.py`, `record_app.py`,
  `record_report.py`. `PREREG_RECORD.md` is what the recording and its replay should show,
  fixed before the recording; `PREREG_RECORD_ADDENDUM.md` adds the replay's numbers, fixed
  before the replay. Results: `../results/modal_h100_record/RESULTS.md`.
- Limits that follow the load, below: the arms `auto` and `auto-past` of
  `replay.py`, and `replay_app.py::small`. `PREREG_GOVERN.md` is what they should show,
  fixed before the GPU runs, with `design_govern_small.json` and `design_govern_h100.json`;
  `PREREG_GOVERN_ADDENDUM.md` is what a first launch showed and what changed before both.
  Results: `../results/modal_govern/RESULTS.md`.
- `tests/`: everything above, end to end against a fake OpenAI server (`fake_rlm_server.py`,
  scripted root) or a fake engine (`fake_engine.py`, a stepping clock with a prefix cache,
  a batch that costs time, a number of places and a KV cache that can fill).

## Deviations from spec-ptc's campaign, all recorded in `campaign.jsonl`

- Roots stream in every arm, so root TTFT and TPOT are measured the same way. Only
  `stream` feeds the tokens to spec-ptc. The text is the same: a test checks that the
  iterations match stock rlms.
- Thread-safe REPLs (`repl_fix.py`, on by default; `--no-repl-fix` turns it off).
  rlms 0.1.3's `LocalREPL` swaps the process-wide `sys.stdout` and working directory on
  every execution. spec-ptc's runner runs concurrent tasks as threads, and there:
  - a task's printed output can land in another task's buffer or get lost;
  - a REPL can fail with `FileNotFoundError` after another task removes its temp dir.

  `tests/test_repl_fix.py` reproduces both on stock rlms. The fix gives each thread its
  own output buffer and no `chdir`.
- Run plan: ABBA order within each concurrency, concurrency {8, 4} only, 2 repeats
  (budget). One server launch for the whole campaign.
- Warm-up before the first unit (`--warmup-passes`, 2 on Modal). With
  `--enforce-eager`, vLLM 0.32 skips its kernel warm-up and compiles kernels the first
  time a batch shape appears. In the smoke run the first burst of 13 concurrent sub-calls
  stalled the root's stream for 8.4 s; the same burst took 1.1 s later in that run. So the
  campaign first sends waves of 1 to 128 concurrent short requests and 1 to 16 long ones,
  each next to a streamed request, twice. `campaign.jsonl` keeps every wave's wall time
  and the stream's longest token gap (`warmup_wave`).
- `--kernel-config`: keys this vLLM's `KernelConfig` doesn't define are dropped and
  listed in `server.json`. The campaign's set came from an unknown vLLM version.
- Context window, when asked for (`--serve-extra="--max-model-len 65536"`). With the
  campaign's own `--max-model-len 8192`, half the tasks die of context overflow
  (`GATE_ADDENDUM.md`).
- A cap on root replies (`SPTC_ROOT_MAX_DELTAS`, 3,000 by default; 0 turns it off).
  rlms sets no `max_tokens` on the root. With a large window a root that repeats itself
  writes until the window is full: one did so for 30 minutes. A reply is cut after 3,000
  deltas and the turn is logged as `truncated`. The longest healthy reply so far was
  about 1,000 tokens.

## The replay bench

A live run cannot show what a speculation policy does: one arm's two repeats of a task
differ by a factor of 1.9. The replay runs the recorded sessions again with everything
fixed but the policy.

- Corpus (`replay_corpus.py build`). Built from finished `nospec` tasks: only that arm
  records every sub-call's prompt and answer. Each session is run again offline while it
  is built, and kept only if every block prints what it printed in the recorded run and
  every turn's message history has the recorded sha256. All 10 recorded sessions pass.
  The corpus holds OOLONG text: it lives in `../../_modal_runs/replay/corpus` and on the
  private volume, not in the repository.
- A unit (`replay.py unit`): every session, 8 at a time, in one arm.
  - The root is a real streamed request with the message history rlms builds, forced to
    the recorded number of tokens. Each engine token releases the next recorded delta.
  - A sub-call is a real request with the recorded prompt and output length, and returns
    the recorded answer. A prompt the recorded run got an error string for returns that
    string at once.
  - Between them runs the campaign's own stack: rlms, spec-ptc's runner, the arm's REPL.
- Arms (`replay.ARMS`): `nospec` (stock rlms), `stream` (spec-ptc at 9b78b7d),
  `scout` (the fork, scout pass on), `wide` (the fork: scout, 128 calls in flight, a batch
  launched as a batch). Controls: `wide-threads` (128 in flight, one thread per prompt),
  `nospec-wide` (no speculation, rlms' batches 128 wide), `stream-open` (spec-ptc at
  9b78b7d with its character budget lifted: as shipped it keeps at most 120,000 characters
  of speculative prompts in flight per session).
- A campaign (`replay_campaign.py run`): one server launch, units one after another in
  ABBA order, each in its own process with its arm's spec-ptc tree on the path. Every unit
  salts its prompts, so no unit finds another's prompts in the prefix cache.
- Exactness. `replay.json` per unit: a unit is exact if every session ran the recorded
  turns, sent the root the recorded message history in every turn, and ended with the
  recorded answer. On the fake engine all six arms are exact on all 10 sessions.
- Report (`replay_report.py`): arms compared turn by turn, the same turn's seconds
  after its stream in each arm, grouped by why spec-ptc as shipped still waited there,
  and each pre-registered prediction next to what was measured.
- On Modal (`replay_app.py`): `probe_handler` (CPU), `smoke` (a T4 and a 1.7B model:
  the plumbing on a real vLLM), `replay` (the H100; its defaults are the registered
  design, 61 minutes on November 10).
- The first unit of a launch pays for a cold engine (25 to 72 s of root stalls in both
  runs). Put a unit you do not need first.

```bash
python replay_corpus.py build --runs ../../_modal_runs \
    --tasks ../../_modal_runs/replay/tasks.json --out ../../_modal_runs/replay/corpus
# a local dry run: the fake engine in one shell, the campaign in another
python tests/fake_engine.py --port 8397 --step-ms 45
python replay_campaign.py run --out /tmp/replay-sim \
    --corpus ../../_modal_runs/replay/corpus --arms nospec,stream,scout,wide \
    --handler-backlog 1024 --base-url http://localhost:8397/v1 --model fake-model
# --launch-delay-ms 2 makes each speculative launch as slow as in a busy process on
# Modal: a local client launches ten times faster and hides what that does

# on Modal
modal volume put -f sptc-results ../../_modal_runs/replay/corpus replay/corpus
modal run --detach replay_app.py::smoke
SPTC_REPLAY_TIMEOUT_MIN=110 modal run --detach replay_app.py::replay
modal volume get sptc-results replay/<run>/summary.md .
```

### What the replay changes in every arm

- rlms' LM handler listens with a backlog of 1,024 (`--handler-backlog`; rlms: 5,
  Python's default). Each single sub-call is a connection to the handler. Measured on
  Modal (`replay_app.py::probe_handler`, 2,000 calls of 150 ms): with a backlog of 5, 1
  call was a second late at 16 threads, and 76 were one to three seconds late at 128. With
  1,024 none was. On macOS the dropped connections time out, and rlms returns
  `Error: Request failed: ...` as the call's answer.
- A salt in front of every prompt sent, one per unit (above).
- No task timeout (the campaign's is 900 s): a replay's work is fixed.
- `PYTHONHASHSEED=0`: recorded code iterates over sets.

## Recording with rlms' batch path fixed

The replay's gain leans on one session whose root had given up on batches: rlms 0.1.3
loses prompts of every batch after a session's first (`../results/modal_h100_rlm/RESULTS.md`,
Corrections 3). `PREREG_RECORD.md` asks what the model writes when that does not happen.

- The fix (`batch_fix.py`). rlms runs each batch in a new event loop but keeps one
  async HTTP client, whose kept connections belong to the previous, closed loop. `apply()`
  runs a client's async requests on one event loop of its own, for the client's whole
  life. The request and rlms' width of 16 prompts in flight are unchanged.
  `tests/test_batch_fix.py` has the defect on stock rlms and its absence with the fix.
- The probe (`batch_fix.probe`): four batches of 20 through rlms' own path against a
  running engine, the last after 6 s without a request (uvicorn closes a kept connection
  after 5 s). Measured on an H100 and on a T4, November 10: stock rlms loses 21 of 80
  prompts (0, 16, 4 and 1 by batch), the fixed path none.
- A recording (`rlm_record.py run`): the campaign of `rlm_campaign.py`, which it does
  not change, with `nospec` as its only arm unless told otherwise, and around it:
  - the fix, for every arm;
  - the probe after the warm-up, with stock rlms and then with the fix. A prompt lost with
    the fix on stops the run before any unit;
  - a deadline for a task's sub-calls (`SPTC_SUBCALL_DEADLINE_S`, 1,200 s). rlms checks
    its 900 s timeout between turns only, so one block can hold a unit: past the deadline
    the task's LM handler refuses sub-calls and the task counts as failed.
- The census (`record_report.py <run> --corpus <corpus>`): what each session wrote
  (single calls, batches, loops of either), which sessions are replayed, and the
  recording's predictions next to what was measured. Counts and timings only.
- On Modal (`record_app.py`): `smoke` (a T4 and a 1.7B model, 5 minutes) and
  `record` (the H100).

```bash
modal run --detach record_app.py::smoke
SPTC_RECORD_TIMEOUT_MIN=58 modal run --detach record_app.py::record
modal volume get sptc-results record/<run> ../../_modal_runs/record/
# a corpus of its own, with names that cannot be taken for the first corpus's
python replay_corpus.py build --runs ../../_modal_runs/record \
    --tasks ../../_modal_runs/replay/tasks.json --out ../../_modal_runs/record/corpus --tag fix
python record_report.py ../../_modal_runs/record/<run> \
    --corpus ../../_modal_runs/record/corpus --design-out design_fixed.json
# the replay of November 10 (46 H100-minutes): a unit thrown away, five units, one extra
modal volume put -f sptc-results ../../_modal_runs/record/corpus replay/corpus_fix
SPTC_REPLAY_TIMEOUT_MIN=75 modal run --detach replay_app.py::replay \
    --corpus replay/corpus_fix --sessions <the 10 of design_fixed.json> \
    --units stream:1,scout:1,wide:1,nospec:1,nospec-wide:1 --warm-arm scout \
    --design-file design_fixed.json --max-minutes 66 \
    --estimates stream=400,scout=400,wide=300,nospec=600,nospec-wide=500,extra-stream-open=520 \
    --extra-units stream-open:1 --extra-sessions <the 10 and trec132k-17000222.fix2>
python long_calls.py <run>/extra/units/stream-open_c8_r1 \
    <run>/units/stream_c8_r1 --session trec132k-17000222.fix2 --min-prompt-tokens 5000
```

`design_fixed.json` is that replay's design as its `campaign.jsonl` hashed it: the 10
sessions, the turns its predictions name, and the addendum's numeric checks.

### What its replay adds to the bench

- A session its timeout stopped is replayed up to that turn boundary. rlms stops a
  task between two turns, so such a session's recorded turns are whole. Where it was
  stopped, the replay hands rlms a reply that sets the session's answer, with no request
  to the engine: the session ends there in every arm, however fast the arm was. The
  message history of that step is hashed and checked like a turn's. These are the
  sessions with the longest serial loops; without them a corpus has only the sessions
  that were fast enough.
- A session the recording's deadline stopped is replayable up to the last turn that
  ended before the deadline. The turn in which it struck got error strings in place of
  answers and is dropped; the message history that turn was sent is compared with the
  rebuilt one. `PREREG_RECORD.md` keeps such a session out of its registered comparison.
- `--units stream:1,scout:1` gives the order of the units outright.
- `--warm-arm scout` runs one unit first and throws it away (kept under `warm/`).
- `--design-file`: a pre-registered design as data (sessions left out, the turns its
  predictions name, numeric checks). It is hashed in `campaign.jsonl` before the first
  unit, and `replay_report.py` scores it.
- `--estimates stream=600,scout=300`: what the budget stop assumes for an arm that has
  not run yet.
- `--extra-units stream-open:1 --extra-sessions ...`: units that run after all the
  others, on their own list of sessions, kept under `extra/` with a summary of their own
  and no prediction of a pre-registration in it.
- `long_calls.py <unit> ...`: the sub-calls with long prompts of a unit, what the
  engine did while they ran (KV usage, waiting, preemptions), and the root token gaps of
  the other sessions inside that window and outside it.
- `width.py <unit> ...`: each burst of a session's sub-calls (how long it took, calls
  in flight at the client, calls back a second for the session and for the whole process,
  what the engine counted as running meanwhile), the root turns that waited for their
  first token with the long prompts sent just before, and a governed unit's cuts and
  ramps.
- A recording should run with `PYTHONHASHSEED=0`, as every replay does. This one did
  not: two of its sessions print Python sets, whose order follows the hash seed, and
  could not be rebuilt.

## Limits that follow the load

spec-ptc holds speculation back with two constants: 16 calls in flight, and 120,000
characters of speculative prompts in flight per session. The replay of November 10 found
both below what the H100 took (128 in flight: 0.87 of the shipped client's session time;
the character budget lifted: one session's four long calls together). Two more hand-set
numbers would be the wrong answer: the right ones differ by engine and by what else runs
on it. The fork's fifth patch sets them from what the engine reports
(`spec_ptc.engine.load`; `../integrations/spec-ptc-fork/README.md`).

- What the client reads. A vLLM server's `/metrics`, four times a second: requests
  running and waiting, the KV cache's size (`cache_config_info`) and how full it is,
  preemptions, and the time between two tokens (`inter_token_latency_seconds`).
- The window (calls in flight, per session) starts at spec-ptc's 16 and moves between
  1 and 256, one step per sample:
  - up while calls wait for a place and nothing says stop: by half until the first cut,
    by an eighth after it, by half again after three samples with nothing holding it;
  - cut to 0.7 on a standing queue (a quarter of what the engine runs was waiting, in
    three samples in a row), and halved when the engine preempted or its KV cache is
    above 97%. A request or two waiting are an engine with its places full, or a burst
    arriving between two steps: they only stop growth;
  - no growth while the KV cache is above 93%, while tokens take twice their quiet
    time, or while the engine is not stepping (requests in its batch and no token since
    the last sample: its numbers have not changed, whatever was sent meanwhile);
  - back towards 16 after 2 s with no call waiting or in flight, or to where the last
    cut left it if that is lower;
  - never above the session's share of the process's ceiling (patch 7, after the runs):
    the governed windows of one process are at most 256 together, shared by what each
    session has in flight or waiting.
- Why the token pace only stops growth. A call that is certain to be used has to run
  anyway. On an engine whose step time grows linearly with its batch, each sub-call token
  costs every stream next to it the same delay whenever it runs: a wider window does not
  add to that sum, it only ends the burst sooner. What does cost the others is an engine
  past what it can admit: the root's next turn queues behind sub-calls, or the KV cache
  overflows and work is thrown away. This is an argument; `PREREG_GOVERN.md` says what
  would count against it.
- Long prompts are admitted against the KV cache the engine has free, by one pool for
  all sessions of the process: 88% of the cache, less what everything else holds. The
  client counts 2.5 characters a token. A call that does not fit waits, as under the
  character budget. A small call is counted and never held, and a call somebody is
  already waiting for (the real run, or the shadow) is let through.
- A batch goes out in requests of at most 32 prompts (and never more than the window),
  each sent as soon as its speculations exist: the window then bounds a batch of any size.
- The scout goes on past a test that cannot leave its loop (`auto-past`): an `if` on
  a result whose arms hold no `return`, `raise`, `break`, `continue` or `assert`. Neither
  arm is run by the scout, the names an arm sets are unknown from there on, and a call
  inside an arm is not launched.
- Arms (`replay.ARMS`): `auto` (as `wide`, with the window and the KV admission
  governed and batches in chunks), `auto-past` (`auto` and the scout past such tests).
  Controls: `wide-past` (that scout at a fixed 128), `wide-open` (a fixed 128 with the
  character budget lifted: long prompts with nothing holding them back).
- The fake engine's load (`tests/fake_engine.py`): `--alpha` (the share of a step's
  time each running request adds), `--max-seqs` (places in the batch; the rest queue,
  first come first served), `--kv-tokens` (a prompt that does not fit waits and holds
  up the queue behind it; a full cache preempts the request admitted last) and
  `--long-chars-per-token` (context prompts at their own rate: OOLONG's run at 2.8
  characters a token). Its `/metrics` has what the client reads.
- The report (`replay_report.py`): "Limits that followed the load" (how often each
  session's window moved and why, the window at each sub-call, cuts, the KV pool), and a
  design file of `kind: checks`, whose checks are the run's predictions. `width.py` reads
  a unit's raw events for what the report does not have: each burst against the calls in
  flight, and where the client was the limit.
- On Modal (`replay_app.py`): `small` (a T4 and a 1.7B model, started with
  `--max-num-seqs 16`: a window the H100 took without noticing is more than this engine
  can admit), and `replay` with `--units`, `--warm-arm`, `--warm-sessions` and the design
  file.

```bash
# a local dry run of the H100 design
python tests/fake_engine.py --port 8397 --step-ms 43 --alpha 0.0005 \
    --max-seqs 256 --kv-tokens 154816 --long-chars-per-token 2.8
python replay_campaign.py run --out /tmp/replay-sim \
    --corpus ../../_modal_runs/record/corpus --handler-backlog 1024 --launch-delay-ms 2 \
    --units stream:1,wide:1,auto:1,auto-past:1,wide-open:1 \
    --sessions <the 11 of design_govern_h100.json, in its order> \
    --base-url http://localhost:8397/v1 --model fake-model \
    --design-file design_govern_h100.json
# the small engine: --step-ms 38 --alpha 0.012 --max-seqs 16 --kv-tokens 89072, the 8
# sessions and the units of design_govern_small.json
```

**Measured** (`../results/modal_govern/RESULTS.md`; 12 of 13 predictions held on the T4,
21 of 21 on the H100):

- The H100: `auto` at 0.985 of `wide` in session time over the 10 sessions and 0.849
  of `stream`; windows at 256 on every large burst; 4 cuts.
- 16 places: `auto` at 0.996 of `stream` and 1.016 of `wide` in session time; 189
  cuts, no window above 38; the root's first token at 1.8 s at the 90th percentile, where
  `wide` has 9.4 s.
- The long turn: 354 s with the pool, 537 s with the character budget, 184 s in
  `wide-open`, where the KV cache reached 96% and nothing was preempted.
- What the dry runs had wrong:
  - The fake engine is twice as fast as the T4 with its places full. A first launch's
    budget would have ended before `auto`.
  - It preempts when its cache is full (103 times in `wide-open`); the H100 did not fill
    its cache.
  - It has no client and no API server. On the H100, calls of 3 tokens come back at
    about 210 a second whether 90 or 220 are in flight, with 13 to 48 requests running in
    the engine (`width.py`).
- What the governor did not see, as measured: two sessions' windows at 256 at once
  (up to 515 calls in flight at the client, none waiting in the engine's count, fewer
  calls back a second than with one window; patch 7 bounds this since, and no run has
  measured it), the
  prefill of long prompts in front of a root's turn, and a queue behind one long prompt,
  which it reads as a standing queue. `GovernorConfig.cpu_hold` (no growth while the
  client's process uses that share of a core) exists and is off; it has not run on a GPU.

## On a TensorRT-LLM server

`trtllm_probe_app.py` runs the governed client (client patches 8 and 9) against
TensorRT-LLM 1.4.0rc3 on one L4. It checks what the governor reads from that engine. It is
not a benchmark: one unit per arm, no repeats, and nothing was registered before it.
Results: `../results/modal_trtllm/RESULTS.md`.

```bash
modal run trtllm_probe_app.py::check   # CPU: the server's CLI, the model in the volume
modal run trtllm_probe_app.py::mpi     # CPU: with which MPI settings a spawned process answers
modal run trtllm_probe_app.py::probe --client <commit of the patched client>   # one L4
modal volume get sptc-results trtllm_probe/<run> ../results/modal_trtllm/
```

- The image is the engine's own container (`nvcr.io/nvidia/tensorrt-llm/release:1.4.0rc3`,
  17 GB), with nothing installed into it. Modal's Python is added next to the
  container's and runs the app only. The server is started as a process of the
  container's Python, without Modal's `PYTHONPATH`.
- The model is `Qwen/Qwen3-1.7B` from the `sptc-hf` volume, where the T4 runs put it.
  The GPU container downloads nothing.
- `probe` has a hard timeout of 12 minutes. The server was ready after 146 to 245 s,
  and the phases take under a minute:
  - four calls of 256 tokens, with the engine's metrics read 20 times a second;
  - a burst of 300 calls of 32 tokens through the client's launcher at the window of
    16, and the same burst with the window governed;
  - the metrics of the idle engine, after each.

  It writes `summary.json`, every sample (`samples.json`), the metrics text before and
  after, and the server's log.
- What the server needs before it writes a gauge of its engine:
  - `return_perf_metrics: true` and `enable_iter_perf_stats: true` in its config. The
    first mounts `/prometheus/metrics`, and the second makes the engine keep a record of
    each step.
  - Its engine in a process of its own, which is the default. With
    `TLLM_WORKER_USE_SINGLE_PROCESS=1` the server runs and the page has no gauge.
- What Modal needs, and another host may not:
  - MPI over shared memory and TCP: `OMPI_MCA_pml=ob1`, `OMPI_MCA_btl=self,sm,tcp`. The
    server spawns its engine with MPI. Open MPI's default, UCX, finds no transport
    between the two in the sandbox, which has no `/sys/class/net`: the spawned side
    aborts and the server waits for it for good. `mpi` tries the settings on a CPU
    container, where the default fails the same way.
  - `--num_serve_frontends 1`, in place of the default of 8.
- `check` cannot start the server: a CPU container has no `libcuda`, and the server's
  CLI does not import without it. It shows where the CLI is, in which Python, and that
  the model and the client's sources are there.
- The first three launches did not get to the gauges, and each cost the time until the
  server was known not to come up. The first waited the whole start timeout, seven
  minutes: `wait_ready` now ends when the server's log says it will not start.

## Local tests

```bash
uv venv ../../.venv-modal --python 3.12      # next to the repository, like the spec-ptc clones
source ../../.venv-modal/bin/activate
uv pip install "rlms==0.1.3" datasets huggingface_hub psutil modal pytest -e ../../spec-ptc
python -m pytest tests -q
```

The replay tests run each arm with its own client: they need the unpatched spec-ptc at
`../../spec-ptc` and the patched one at `../../spec-ptc-sptc-hints`
(`../integrations/spec-ptc-fork/README.md`). `tests/test_fork_patches.py` checks that the
patches give the trees the H100 runs hashed.

## Running on Modal

```bash
modal setup                         # once, browser login
modal run app.py::probe             # H100, about 2 min
modal run app.py::prepare           # CPU, 10–20 min
SPTC_CAMPAIGN_TIMEOUT_MIN=35 modal run --detach app.py::campaign \
    --preset smoke --arms stream,fanout,nospec --max-minutes 30
SPTC_CAMPAIGN_TIMEOUT_MIN=105 modal run --detach app.py::campaign \
    --preset main --max-minutes 90 --unit-estimate-min 20 \
    --serve-extra="--max-model-len 65536"
# resume a run (finished units are skipped), or run chosen arms only:
#   ... app.py::campaign --preset main --run <run> --arms nospec,stream --conc 8 --repeats 2
modal run app.py::compact --run <run>      # CPU; older runs only
modal volume get sptc-results rlm/<run>/units/<unit>/events.jsonl ...
python analyze.py ../../_modal_runs/<run>
python oracle.py ../../_modal_runs/<run>
```

- Two limits on a campaign call. `--max-minutes` stops before any unit that would
  pass it. `SPTC_CAMPAIGN_TIMEOUT_MIN` (default 180) is the function's hard timeout, read
  when `modal run` starts: it kills a unit that hangs. Finished units are already
  committed to the volume.
- Measured (2026-11-09):
  - vLLM is up in 1–2 minutes and the warm-up takes 1 more.
  - The smoke run took 9 minutes end to end: 90 to 150 s per task at concurrency 1.
  - With the 65,536-token window a unit of 8 tasks at concurrency 8 took 15 to 31
    minutes. Plan a run by units, not by the preset.
  - Launches land on different hosts, and the root's token gap follows the host (33 to
    53 ms). Compare arms inside one launch only.
- Downloading: fetch `events.jsonl`, `unit_stats.json`, `unit.json`, `DONE`,
  `metrics.csv` and `trajs_compact/` per unit. A unit's raw `rlm_trajs/` is 50–100 MB,
  mostly the context repeated in every block.
- Weights: `prepare` downloads them on a CPU container, and the campaign runs with
  `HF_HUB_OFFLINE=1`.
- Data: sub-call prompts contain OOLONG context, so raw `rlm_trajs/` are not in this
  repository; only structure and timings are.
  - One question of its TREC set is in the repository: the warm-up's short prompt quotes
    it (`rlm_campaign.py`, `warmup`).
  - Checked on November 10: no other six-word sequence of the 8 tasks' contexts,
    questions or answers is in a tracked file.
