# The spec-ptc client changes, as patches

[spec-ptc](https://github.com/alexzhang13/spec-ptc) is the agent library every run in this
repository measures. The changes made to it here are a series of diffs against its commit
`9b78b7d`. Apply the series up to a patch to get the client a run measured.

| # | file | what it adds | the client of |
|---|---|---|---|
| 1 | `../spec-ptc-sptc-hints.patch` | request tags; a claim survives a call the server refused (`../README.md`) | the three Kaggle T4 runs; the old client of `results/modal_t4_bench` |
| 2 | `2-dbee0c2-refusal-survival-scout.patch` | the shadow survives a refused call; the list-argument peek crash fixed; the scout pass; `rlm_query` at depth 1; three loop shapes recorded from real runs (`benchmark/suite/patterns_v7.py`) | the new client of `results/modal_t4_bench` (committed after those runs; they recorded no hash) |
| 3 | `3-2555dd1-window-batch-launch.patch` | the in-flight window as a parameter; a batch launched as a batch; the scout no longer trusts a name whose statement raised | the registered replay, `results/modal_h100_replay/20261110-042602-replay` |
| 4 | `4-ac5d733-scout-shadow-handoff.patch` | the shadow lets the scout finish its launches; launching is not counted as a statement's computing | the follow-up, `results/modal_h100_replay/20261110-053243-replay`; the replay with rlms fixed, `results/modal_h100_record/20261110-191427-replay` |
| 5 | `5-e09ff01-limits-follow-the-load.patch` | limits that follow the load: a governor for the window, a KV pool for long prompts, batches in chunks; the scout goes on past a test that cannot leave its loop | a first launch that was stopped before a governed unit was measured, `results/modal_govern/stopped/20261111-083951-small` (`cloud/PREREG_GOVERN_ADDENDUM.md`) |
| 6 | `6-11b6d39-engine-not-stepping.patch` | the governor does not widen a window while the engine is not stepping | a T4 with 16 places, `results/modal_govern/20261111-090725-small`; the H100, `results/modal_govern/20261111-091523-replay` |
| 7 | `7-47f0b98-one-ceiling-per-process.patch` | the governed windows of one process on one engine share one ceiling | no run. It answers what the H100 run found (two windows at 256 at once), and has local tests only |

The names carry the commit of the local `sptc-hints` branch each patch ends at.

**What launches calls differently is off unless asked for** (the table below). The fixes
are always on: a peek whose call takes a list no longer ends the shadow thread, a refused
call no longer stops the shadow, and the runaway guard no longer counts launching as a
statement's computing.

| option (`SpeculativeLocalREPL`) | default | what it does |
|---|---|---|
| `spec_scout` | off | Each closed statement is run once more, ahead of the shadow, with tool calls that return at once. Every call whose arguments hold no unknown value is launched, and the shadow adopts it. No bets: a test on an unknown value ends the scout's statement |
| `spec_rlm_query` | off | `rlm_query` and `rlm_query_batched` can be speculated at depth 1, where they are plain sub-calls |
| `spec_max_inflight` | 16 | how many speculative calls are in flight at once, however they were launched |
| `spec_batch_launch` | off | a batch goes to rlms' handler as one request for the prompts nobody has launched yet. Each prompt keeps its own speculation |
| `spec_batch_chunk` | 0 | with `spec_batch_launch`: a batch goes out in requests of at most this many prompts, and never more than the window is wide, each sent as soon as its speculations exist. 0: the whole batch as one request |
| `spec_govern` | off | the window and the admission of long prompts follow the load (below). `True`, or a `GovernorConfig` |
| `spec_load_url` | none | the engine's `/metrics` (`spec_ptc.engine.load.metrics_url(base_url)` for a vLLM server). Without it a governed window reads the root's own token pace only |
| `spec_scout="past"` | off | the scout pass, and it goes on past a test on a result when no arm of the test can leave the loop it is in |

**Limits that follow the load** (`src/engine/load.py`, patch 5). spec-ptc holds speculation
back with two constants: 16 calls in flight, and 120,000 characters of speculative prompts
in flight per session. With `spec_govern` both are set from what the engine reports:

- The window starts at 16 and moves between 1 and 256, one step per sample of the
  engine's `/metrics` (four a second).
  - Up while calls wait for a place and nothing says stop: by half of itself until
    the first cut, by an eighth after it, and by half again after three samples with
    nothing waiting.
  - Cut to 0.7 on a standing queue: a quarter of what the engine runs was waiting,
    in three samples in a row. **Halved** when the engine preempted or its KV cache is
    above 97%. A session with no call in flight is not cut.
  - Held on any request waiting, with the KV cache above 93%, while tokens take
    twice their quiet time, or while the engine is not stepping: it has requests in its
    batch and wrote no token since the last sample, so its numbers say nothing about
    what was sent meanwhile (patch 6; a cold T4 spent two seconds in one step, and a
    window went from 16 to 256 on eight identical samples).
  - Back towards 16 after 2 s with no call waiting or in flight, or to where the
    last cut left it if that is lower.
  - Unchanged while the engine's numbers are missing or old.
  - Never above its share of the process's ceiling (patch 7). The governed windows
    of one process on one engine are at most 256 together (`GovernorConfig.w_process`;
    `None` is the ceiling of one window, 0 is no bound). A session has what the others
    leave of it, by what they have in flight or waiting: next to a session with four
    long calls it has 252, and two sessions that both launch a large batch have 128
    each. A share is never under 16. A window above its share is moved down to it, and
    grows again when the others are done. It is the one bound that the engine does not
    give: the engine's numbers do not show a client that is itself the limit.
- Long prompts are admitted by one pool for all sessions of the process, against the
  KV cache the engine has free: 88% of the cache, less what everything else holds. The
  client has no tokenizer and counts 2.5 characters a token, which is on the low side.
  A call that does not fit waits, as under the character budget. Three kinds do not: a
  small call (under 1% of the cache) is counted and never held, a call somebody is
  already waiting for is let through, and with nothing of the pool's in flight any call
  goes.
- Why the token pace only stops growth. A call that is certain to be used has to run
  anyway. On an engine whose step time grows linearly with its batch, each sub-call
  token costs every stream next to it the same delay whenever it runs. A wider window
  does not add to that sum; it ends the burst sooner. What costs the others is an engine
  past what it can admit.
- Without `spec_load_url` none of the engine's numbers are known: the character
  budget stays as shipped, and the window follows the root's token pace alone.

**What they gained, measured** (`../../README.md`). With rlms losing batch prompts, the
scout took session time to 0.72 of the shipped client's on 8 recorded sessions. With rlms
fixed it took it to 1.00 on 10: the model's loops of batches only store their results,
and the shipped client launches those whole. The scout's own case is a loop that uses
each result without testing it. The window took session time to 0.87 there.

**The limits that follow the load, measured** (`../../results/modal_govern/RESULTS.md`).
The rule set beforehand: within 2% of the hand-set 128 in session time on those 10
sessions, with root streams at most 5% longer than as shipped.

- The H100: 0.985 of the hand-set client's session time, root streams 1.4% longer
  than as shipped. Against spec-ptc as shipped: 0.85 (the hand-set 128: 0.86), and 0.82
  with `spec_scout="past"`. Windows went to 256 on every large burst.
- A T4 held to 16 places: 1.00 of the shipped client's session time. The windows
  closed (189 cuts, none above 38), and the root's first token came after 1.8 s at the
  90th percentile, where a fixed 128 made it 9.4 s. The fixed 128 was 1.6% faster in
  session time there.
- Long prompts: a turn with four calls on prompts of 36,000 tokens took 537 s as
  shipped and 354 s with the pool. With no budget at all it took 184 s, and the engine
  preempted nothing at 96% of its KV cache: the pool's 88% was more caution than that
  engine needed.
- What the governor did not see in those runs: its own process as the limit (two
  windows at 256 at once got fewer short calls back a second than one), the prefill of
  long prompts in front of a root's turn, and a queue behind one long prompt, which it
  reads as a standing queue.
- Since the runs, the first of these has a bound (patch 7, above): the two windows
  would have had 128 each, which is what the hand-set client had there. No run measured
  it. In a local dry run (six of the recorded sessions, four at a time, against
  `cloud/tests/fake_engine.py`; not kept) a loop of 3,181 calls at a window of 256 gave
  way to a loop of 787 that began beside it, in three moves over 0.6 s, to 128 each, and
  grew again when the other was done. The process had at most 264 sub-calls in flight,
  and the unit was exact. `GovernorConfig.cpu_hold`, a hold on the client's own CPU
  share, stays off: in the H100 run 19 of 50 growth steps were at 0.9 of a core or more,
  among them the first steps of a burst, where the launcher is what is busy.

**Not a parameter here:** spec-ptc's character budget (`Budget.max_inflight_chars`, at
most 120,000 characters of speculative prompts in flight per session). The replay's
`stream-open` and `wide-open` arms lift it from outside (`cloud/replay.py`). With
`spec_govern` and an engine that reports its KV cache, the pool above takes its place.

## Apply

```bash
git clone https://github.com/alexzhang13/spec-ptc && cd spec-ptc && git checkout 9b78b7d
git apply ../sptc-gate/integrations/spec-ptc-sptc-hints.patch
for p in ../sptc-gate/integrations/spec-ptc-fork/[2-7]-*.patch; do git apply "$p"; done
```

`cloud/replay_campaign.py` and `cloud/bench_app.py` expect the patched tree next to this
repository as `spec-ptc-sptc-hints/` (or at `SPTC_HINTS_ROOT`), and the unpatched one as
`spec-ptc/`.

## Check

Each replay run recorded a sha256 over the Python sources of both clients before its first
unit (`campaign.jsonl`, `trees`). The series reproduces them:

| after | sha256 (`cloud/replay.py::tree_hash`) | recorded by |
|---|---|---|
| no patch | `f46414b0…` | every run, as `stock` |
| patch 3 | `33387f6a…` | the registered run, as `fork` |
| patch 4 | `7aa23f07…` | the follow-up and the replay with rlms fixed, as `fork` |
| patch 5 | `545d9505…` | the stopped launch `results/modal_govern/stopped/20261111-083951-small`, as `fork` |
| patch 6 | `a61ef323…` | `results/modal_govern/20261111-090725-small` and `20261111-091523-replay`, as `fork` |
| patch 7 | `9a5b714a…` | no run: `cloud/tests/test_fork_patches.py` holds the hash |

`cloud/tests/test_fork_patches.py` applies the series to a clean `9b78b7d` and compares
with the hashes in `results/modal_h100_replay/` and `results/modal_govern/`.

## Tests of the patched client

256 tests at patch 7 (243 at patch 6, 242 at patch 5, 170 at patch 4, 166 at patch 3),
with rlms 0.1.3 installed. From
the patched tree,
with `spec_ptc` pointing at its `src/`:

```bash
mkdir -p /tmp/sptc_shim && ln -sfn "$PWD/src" /tmp/sptc_shim/spec_ptc
PYTHONPATH=/tmp/sptc_shim python -m pytest tests -q --basetemp=/tmp/sptc-pt
```

`--basetemp` keeps the daemon test's socket path short enough for macOS.

## Licence

spec-ptc is MIT-licensed, copyright (c) 2026 Alex Zhang. These diffs contain parts of it
and are offered under the same terms. Its licence text is in its repository.
