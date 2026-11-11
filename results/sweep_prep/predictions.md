# Pre-registered predictions for the T4 saturation sweep

**Everything here is PREDICTED by the simulator. Nothing is measured.** It was written
on October 20, 2026, before any GPU run of the sweep (`kaggle/vllm_bench.py sweep`).
- Numbers: `predictions_table.md` (generated) and `predictions.json`. The seq_cap 32
  sensitivity set: `predictions_seqcap32_table.md` and `predictions_seqcap32.json`.
- Code: `experiments/sweep_predict.py`.

**Revision (still before any GPU run of the sweep).** A review found errors and
weak spots. Changed:
- Section 1 merged two arms with different P0 knees (plugin/spec is 12, not 16). Fixed.
- `seq_cap` 24 and 32 tie in the fit. Several answers depend on the choice. The answers
  under 32 are now recorded too (P1-32, a sensitivity set beside the primary P1), and
  the answers that depend on the choice are marked.
- The knee comparison between arms now also uses `knee_ref`, a threshold shared by
  every arm of a client mode. Knife-edge knees are flagged.
- Goodput is described as what it is for the speculative arms: a root TPOT test.
- Scoring rules 1, 3, 4 and 5 were tightened (see "How the measured sweep will be
  scored").
- `predictions.json` was regenerated to add the new fields. Every number of the first
  version came out identical (checked field by field: 0 differences).

## How the predictions were made

- Workload. The sweep's: the first T4 load test's 4-pattern mix (`map16`, `map_reduce`,
  `two_stage`, `side_branch_chain`), 4 sessions per agent, the root stream served by the
  same vLLM. All agents start together.
- Arms. The sweep's 9 arms map to simulator policies as follows:
  - `fcfs/*`: `fcfs`;
  - `prio/*`: `vllm-priority`, with every speculative call at priority 1 (semantics in
    `vllm_priority_semantics.md`);
  - `plugin/*`: `agent` with bet rejection, as in `experiments/t4_validate.py`.
- Loads. 1 to 32 agents, plus 48 and 64, which are beyond the sweep's ladder.
- Calibration. It is that of `experiments/t4_validate.py`, unchanged:
  - the cost model comes from the T4's solo calibration and its decode-concurrency
    measurement;
  - per-call tokens come from the no-speculation suite runs;
  - one client overhead (30 ms) was fit on the no-speculation suite medians.
- Server facts from the T4 server log: KV capacity 85,904 tokens, a 2,048-token step
  budget, `max_num_seqs` 256.
- Two sets, plus a sensitivity set. P0 and P1 were written at the same time:
  - P0: that calibration alone.
  - P1 (primary): P0 plus one parameter. The per-sequence step cost (0.44 ms,
    measured with at most 16 sequences) stops growing past `seq_cap` sequences.
    `seq_cap` = 24 was fit on the first T4 load test's 18 root TPOT medians (1/4/8 agents).
    The grid is in `predictions_table.md`. 24 and 32 tie (mean |log error| 0.0440 and
    0.0441). 24 was taken only because it comes first in the grid; the data cannot
    separate them.
  - P1-32 (sensitivity): P1 with `seq_cap` = 32. Same code, run with
    `--seq-cap 32 --sets P1 --name predictions_seqcap32`. It is not a third prediction.
    It shows which P1 answers rest on the tie-break.
- Why P1 exists. P0 over-predicts a row we already have. At 8 agents with bad
  guesses on stock vLLM, P0 gives a root TPOT of 51.0 ms against 39.0 ms measured, and a
  session time of 8.56 s against 6.62 s. That suggests the linear per-sequence cost is
  wrong past ~16 sequences. P0 is kept so that the second T4 run can show whether the
  extra parameter was right.
- In-sample points. For P1, the sweep's points at 1, 4 and 8 agents are in-sample
  (its parameter was fit on the same arms and loads). Its other loads, and all
  priority-arm points, are not.
- Determinism. The simulator is deterministic, so each point is one run: there are
  no repeats and no CIs on the predictions.

Two changes from `t4_validate.py`'s load replay were decided before any of this was run:
- Each call's prompt and output tokens are looked up by the call's own identity.
  `t4_validate`'s `MeasuredBackend` keeps them on the shared backend object and reads them
  after the client delay. So calls started in the same instant take the last call's
  values. In particular, a decoy usually ran at its real call's length instead of the
  96-token maximum. This is reported as an open issue for that script; it is not changed
  here.
- Prompts carry the sweep's ~8-token per-run prefix.

## The pre-registered answers

Definitions are in `kaggle/vllm_bench.py` (`derived`), applied unchanged to the measured
runs:
- knee: the first load where session p50 is at least 2× the arm's own 1-agent p50;
- knee_ref: the same, against the 1-agent p50 of stock FCFS with the same client
  mode (`fcfs/spec` for `plugin/spec`, and so on). Every arm of a mode then shares one
  absolute threshold;
- goodput: the fraction of sessions with wall time ≤ 2× and root TPOT ≤ 2× the
  `fcfs/nospec` 1-agent value of the same pattern. Root TPOT is each session's mean.

### 1. Where each arm saturates

Each cell: P1 / P1-32 / P0. Bold: the answer depends on `seq_cap`.

| arm | knee | knee_ref | goodput < 0.5 first at | throughput peak in the ladder (P1) |
|---|---|---|---|---|
| fcfs/nospec, prio/nospec, plugin/nospec | **48** / 32 / 32 | **48** / 32 / 32 | **48** / 32 / 32 | still rising at 32 |
| fcfs/spec, prio/spec | 16 / 16 / 12 | 16 / 16 / 12 | **16** / 12 / 12 | still rising at 32 |
| plugin/spec | **24** / 16 / 12 | **24** / 16 / 12 | **16** / 12 / 12 | still rising at 32 |
| plugin/spec+bad | 24 / 24 / 16 | **32** / 24 / 16 | **16** / 12 / 12 | still rising at 32 |
| fcfs/spec+bad | 12 / 12 / 8 | 12 / 12 / 8 | 8 / 8 / 4 | **24 agents** (141 sessions/min; 136 at 32) |
| prio/spec+bad | 12 / 12 / 8 | 12 / 12 / 8 | 8 / 8 / 4 | **24 agents** (141 sessions/min; 139 at 32) |

- Only stock speculation with bad guesses stops gaining throughput inside the ladder.
  It does so in all three sets.
- The plugin does not delay saturation in these predictions. The P1 table's
  "plugin/spec 24, fcfs/spec 16" is a knife edge. At 16 agents fcfs/spec is at 2.000×
  its 1-agent p50 and plugin/spec at 1.989×. Their growth curves differ by under 1% at
  every load of the ladder (`derived.growth`). Under P1-32 both knee at 16. This difference is not
  claimed.
- Self-normalization. `knee` divides by the arm's own 1-agent p50. On the T4 the
  plugin was slower at 1 agent (3.10 s against 2.73 s, see section 4). That alone would
  move its own knee later. Arm-to-arm knee comparisons are therefore made on `knee_ref`.
- Goodput is a root TPOT test for the speculative arms, not a capacity measure.
  Their sessions are about 2.4× shorter than the no-speculation references. So the wall
  half of the SLO never fails inside the ladder for `*/spec` and `plugin/spec+bad`, and
  fails only at 32 for stock `spec+bad` (24 in P0; `good50_wall`). The "goodput < 0.5" column is
  therefore where the root stream passes 2× the stock 1-agent root TPOT (about 31.6 ms).
  Example: `fcfs/spec+bad` fails it at 8 agents while its sessions are 26% faster than
  without speculation (5.81 s against 7.89 s) and its throughput is still rising. Use
  the knee and throughput for saturation.

### 2. Does stock-FCFS speculation with bad guesses become a net loss?

- P1: yes, at 24 agents. Session p50: 11.93 s against 11.70 s with no speculation.
  At 32 agents: 14.57 s against 12.53 s. P1-32 agrees: 24 agents (12.39 s against
  11.70 s).
- Below that it still wins: 5.81 s against 7.89 s at 8 agents, and 8.76 s against
  9.74 s at 16.
- P0 puts the crossover at 8 agents. The first T4 run already contradicts that: it
  measured 6.62 s against 8.01 s, a gain.
- Correct speculation without bad guesses stays a net gain through 32 agents in both
  sets.

### 3. Does vLLM's priority scheduling help?

**No, not within the ladder.**
- Through 24 agents, `prio/*` is identical to `fcfs/*`: ratios 1.000 to 1.001 on session
  p50 and root TPOT p99, in both sets. No KV preemption happens at any load (0
  predicted), and the waiting queue never holds normal work behind speculative work
  long enough to matter. Priority only reorders that queue.
- At 32 agents: session p50 ratio 0.999, and root TPOT p99 is 12% *worse* (P1;
  P1-32: 0.996 and 12% worse). That p99 is a tail across sessions of each session's mean
  TPOT, not a token-level tail.
- Only beyond the ladder, at 48 to 64 agents, does priority cut session p50 by 5% (P1)
  to 10% (P0). There `max_num_seqs` fills and requests do wait.
- The reason is in the semantics. Priority never keeps a low-priority request out of a
  batch that has room. So low-priority bad guesses still decode alongside every root
  stream, and they still slow it down.

### 4. The plugin

- Bad guesses cost nothing from 8 agents on. `plugin/spec+bad` equals `plugin/spec`
  at every load from 8 agents: every decoy is refused (360 of 360 at 8 agents).
- At 1 agent, 5 of 45 decoys are refused. At 4 agents, 142 of 180.
- Against stock FCFS with bad guesses, the plugin's session p50 ratio is:

  | agents | 1 | 4 | 8 | 16 | 24 | 32 |
  |---|---|---|---|---|---|---|
  | P1 ratio | 0.92 | 0.77 | 0.75 | 0.63 | 0.55 | 0.53 |
  | P1-32 ratio | 0.92 | 0.72 | 0.71 | 0.63 | 0.57 | 0.54 |

  Its root TPOT p99 ratio is 0.59–0.85 (P1-32: 0.59–0.83).
- Known miss carried over. The simulator predicts no light-load cost for the plugin
  at 1 agent: 2.78 s, the same as stock, without bad guesses, and 3.10 s against 3.37 s
  with them. The first T4 run measured it *slower*: 3.10 s against 2.73 s without bad
  guesses, and 3.38 s against 3.38 s with them.
  That problem is analysed in `results/t4_run1_analysis/root_cause.md`. This prediction does not correct
  for it.

### 5. Decoy outcomes (now logged by the bench)

| arms | predicted outcomes |
|---|---|
| stock FCFS and stock priority | every decoy completes (~38%) or is cancelled at turn end (~62%); none rejected or dropped |
| plugin | rejected as above; 0 dropped (no KV pressure at these loads) |

"Rejected" means refused, or dropped before its first token. vLLM never streams the
finish of a zero-token request, so the client cannot tell the two apart. The simulator's
outcomes use the same split.

## How the measured sweep will be scored

These rules are fixed now. They are applied to the core and full presets' measured
runs, with the definitions above. They were tightened in the revision, before any data.

1. Points. For every (arm, load) measured with 3 repeats, report |log(predicted /
   measured)| for session p50 and root TPOT p50: the median and the maximum, for P1,
   P1-32 and P0. P1's in-sample points (1/4/8 agents) are reported separately from the
   rest. Root TPOT p99 errors are reported in a separate table, not in the headline.
   Below 100 sessions (up to 8 agents with 3 repeats) a p99 is the slowest session, and
   the table says so.
2. Thresholds. A predicted knee, `knee_ref`, goodput-0.5 load or net-loss load
   counts as right if the measured one is the same ladder step or the adjacent one. Above
   the ladder: right if no measured point reaches it.
   - P1 is scored. The answers in bold in section 1 depend on `seq_cap`. For those, the
     report also says whether P1-32 matched. They are counted apart: the calibration data
     could not decide them.
   - Knife-edge knees are scored but flagged: a growth ratio within 3% of 2.0 at the
     predicted knee or the step before. In P1 that is fcfs/spec and prio/spec at 16
     (2.000) and plugin/spec at 16 (1.989).
   - Differences between arms are judged on `knee_ref`, not `knee`.
3. Priority. The claim "no help within the ladder", per load:
   - up to 24 agents: *supported* if `prio/spec+bad` session p50 is within ±5% of
     `fcfs/spec+bad`; *refuted* if it is outside ±5% and the 95% CIs do not overlap;
     otherwise *unresolved*;
   - at 32: *supported* if the ratio is at least 0.95; *refuted* if it is below 0.90 with
     non-overlapping CIs; otherwise *unresolved*.
   - The claim holds if every load is supported. Overlapping CIs no longer count as
     support: with 3 repeats, noisier data would pass more easily.
4. Plugin. The claim holds if both conditions hold at every load from 8 agents on:
   - `plugin/spec+bad` session p50 is within 5% of `plugin/spec`;
   - at least 95% of decoys are logged as rejected (refused, or dropped before their
     first token).
5. Validity. A point counts only if every run has status ok and the row's `cpu_ok`
   is true. That is: whole-host CPU from `/proc/stat` (every process, the vLLM API server
   and engine core included) averaged under 0.85 over each run, with under 10% of 1-s
   intervals at ≥ 95% busy. The agents' own `client_cpu_util` is reported but is not the
   test: it leaves out vLLM's processes. A point without host CPU data is reported as
   unchecked.

## What the predictions leave out

- Client CPU. The simulator has no client. On Kaggle's 4 vCPUs, 32 agent processes
  plus vLLM's API server and engine core may saturate the CPU. The bench records the
  whole host's CPU use for this reason (rule 5).
- Inputs outside the data. Per-sequence cost past 16 sequences (P0) or past
  `seq_cap` (P1) is an extrapolation. The batches at 24–32 agents with bad guesses are
  far larger than anything either set was fit on.
- Engine details. Prefix-cache sharing between a call and its decoy, CUDA-graph
  padding, and vLLM's full-prompt admission check are not modeled.
