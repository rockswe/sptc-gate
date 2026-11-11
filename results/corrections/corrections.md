# Simulator corrections: report and README headlines under vLLM 0.32 KV semantics

October 20, 2026. All numbers here are **simulated**. Nothing was measured on a GPU. This
file gives the old and corrected values; the report's "Correction (October 20)" section is
built from it.

## What changed in the simulator

The audit found three places where the
simulator's KV cache does not do what vLLM 0.32 does, and one workload assumption (#44).
Each is now a `ServerConfig` or workload option. The vLLM behaviour is the default.

| fix | audit | old model | vLLM 0.32 (vendored source) | option |
|---|---|---|---|---|
| full_isl | #32 | admits a waiting request if its first chunk fits | admits it only if the whole sequence fits in free + evictable blocks (`config/scheduler.py:190`, `kv_cache_manager.py:522-539`, `scheduler.py:1270`) | `ServerConfig.full_isl` |
| resume | #17 | a preempted request recomputes from scratch | its full blocks keep their hashes, and on resume (`num_computed_tokens == 0`, `scheduler.py:1593`) it looks them up again (`scheduler.py:960-967`) | `ServerConfig.resume_from_cache` |
| lru_queue | #18 | finished sub-calls' blocks are reused before any cached root context | one free queue: freed full blocks with a hash go to its tail in free order, tail block first (`block_pool.py:774-803`, `kv_cache_manager.py:620-629`) | `ServerConfig.cache_freed_blocks` |
| shared_sys | #44 | each session caches a private copy of its 2,000-token system prompt | the prefix cache is content-addressed (`kv_cache_manager.py:295-299`, `block_pool.py:752-768`): one copy for every request with the same text | `Request.prefix_key`; `run_session(sys_share=...)` |

- Old model. `LEGACY_KV` (`clog.py --legacy-sim`). Scripts without that switch
  (`general.py`, `freeride.py`, `allowance_ab.py`, `t4_validate.py`, `sweep_predict.py`)
  take `SPTC_LEGACY_KV=1` in the environment: `ServerConfig` then defaults to `LEGACY_KV`,
  and `GeneralServer` keeps the full-ISL admission it already had.
  - `experiments/corrections.py check-legacy` re-runs 15 committed cells
    (`kv_rtx4090`, `clog_graphs`, 3 seeds) and matches them exactly.
  - With `SPTC_LEGACY_KV=1`, 28 committed `results/general` rows (react_t4 0.3/s,
    react_h100 12/s, batch_t4 0.15/s, seed 0) reproduce exactly. Without it, 16 of the 28
    differ.
- Gate at schedule time (#45). `ServerConfig.bet_gate="schedule"` gates bets in the
  waiting loop, as the plugin does. The default is still `submit` (the report's
  idealised policy).
- Determinism. Replays no longer depend on `PYTHONHASHSEED`.
  - Before this fix, `trace.py` forced a statement's reads in set order.
  - That moved some agent-policy cells by up to 1.4% between processes. Example: eager
    0.8/s, 40% wrong labels, seed 2 gave 0.627 or 0.636 depending on the hash seed.
  - The old set order is not restored by `--legacy-sim` or `SPTC_LEGACY_KV`. So
    committed agent-policy cells (`clog_eager`) reproduce only up to that variation.

## Which workload the corrected numbers use

Whether sessions share their system prompt is a workload question, not a vLLM one.

- Corrected (below) = the three vLLM KV fixes on the report's own workload: a private
  system prompt per session. In `runs.csv` this is variant `all-shared_sys`.
  - It is also what `kaggle/bench_general.py` sends: a per-agent tag leads every prompt.
  - `run_session` and now `clog.py` default to it (`sys_share="session"`).
- Prompt shared per program = the same plus one cached system prompt per program
  (variant `all`; `clog.py --sys-share program`). The 4 programs share 1,984 tokens
  (124 blocks) of the 2,000-token first prompt across 240 sessions.
  - This is the most favourable sharing short of one prompt for all sessions.
  - It is a sensitivity column, not the headline.
- An earlier version of this file used the per-program variant as "corrected". That
  mixed a workload change into the vLLM fixes. On the 4090 headline cell the difference
  is 0.93× (shared) against 1.01× (private).

## Run sizes

- `experiments/corrections.py`; rows in `results/corrections/runs.csv`; tables in
  `results/corrections/tables.md`.
- Every cell has 240 sessions and seeds 0, 1, 2: the report's own sizes, because one run
  takes 2-5 s.
- Ran in batches of 2-12 minutes, on 2 worker processes.
- Ratios are session p50 over the paired no-speculation FCFS p50 of the same seed. They
  are shown as median [min-max] over the 3 seeds. † marks median drift > 1.2 (not in
  steady state).
- Cells re-run:
  - RTX 4090 at 0.14/s, all variants;
  - the 4090 load ladder 0.02-0.20/s (0.15 and 0.16 added), legacy, corrected and
    prompt shared per program;
  - the H100 headline cells, with legacy, corrected, every fix's single and leave-one-out
    variant, and the sensitivity variants;
  - not re-run: the full rate sweeps and the figures.

## Headlines: old vs corrected

| headline (where) | old | corrected: vLLM KV, private prompts (simulated) | prompt shared per program | which fix moved it | conclusion |
|---|---|---|---|---|---|
| RTX 4090 wasted-speculation loss at its highest load, 0.14/s, FCFS (report summary, §4.2 table, README "two of four servers") | **1.47×** [1.07-1.71], drift 1.03 | **1.01×** [0.95-1.32], drift 0.96 (per seed 0.95 / 1.32 / 1.01; seed 1 drift 1.46) | 0.93× [0.85-1.04] (per seed 0.85 / 1.04 / 0.93) | Alone, from the old model: resume 1.04, full_isl 1.13, lru_queue 1.51, shared prompt 0.95. resume and full_isl both cut the cost of preemption and overlap | **Break-even at 0.14/s, not a loss.** With a shared prompt, a small gain, but one seed of three is above 1. Waste still costs most of the gain (shadow alone 0.45×) |
| same server, above the report's loads (new cells) | 0.15/s: 2.47× [1.41-2.71]†; 0.17/s: 4.40×† | 0.15/s: **1.41×** [1.08-1.80], drift 1.07 (per seed 1.07 / 2.05 / 0.96). 0.16/s: 2.17× [1.35-2.33]†. 0.17/s: 2.97×† | 0.15/s: 1.02× [0.97-1.33]. 0.16/s: **1.33×** [1.10-1.68], drift 1.02 (per seed 1.02 / 1.74 / 0.89). 0.17/s: 1.85× [1.29-2.22]† (drift 1.08 / 2.36 / 1.21) | - | **A steady-state loss exists, but 0.01-0.02/s above the report's range**: at 0.15/s with private prompts, 0.16/s with a shared one. In both, 2 of 3 seeds are steady (drift ≤ 1.2) with a ratio above 1, and the third is not steady. This is a narrow band at the server's capacity edge: the median drift passes 1.2 from 0.16/s (private prompts) or 0.17/s (shared). Busy time does not show the edge by itself: the no-speculation baseline is busy 99-100% from 0.14/s, but already 97-99% at 0.11/s, where waste is still a clear gain (0.79x). Above it (0.16/s+ with private prompts, 0.17/s+ shared) waste pushes the server into overload, a weaker claim than a steady-state loss |
| H100 4B with CUDA graphs, 0.8/s, FCFS + waste1 (report summary, §4.2, README) | **1.22×** [1.11-1.57] | **1.30×** [1.18-1.64], drift 1.19 (just under the 1.2 cut) | 1.16× [1.09-1.51] | lru_queue alone 1.30 (freed sub-call blocks push root contexts out: baseline root hit 0.68 → 0.53). Shared prompt alone 1.14. full_isl and resume: no effect (no preemption in this cell) | **Holds, and is larger** with private prompts |
| `agent` policy at 0.8/s, H100 eager, waste1: agent vs FCFS (report summary, §4.2) | **0.36× vs 0.97×**† | **0.36× vs 0.96×**† | 0.36× vs 0.93×† | FCFS: each KV fix alone 0.96-0.97 (preemptions 46 → 29-38), shared prompt 0.93. agent unchanged under every variant | **Holds** |
| same, 20% / 40% of bet labels wrong | 0.47× / 0.63× | 0.48× / 0.66× | 0.47× / 0.63× | lru_queue (0.48 / 0.66 alone); full_isl and resume none | **Holds**, 40% case slightly worse. A legacy re-run gives 0.64 for 40%; the old 0.63 came from a hash-seed-dependent seed 2 |
| batched programs, H100 eager, FCFS + waste1 at 0.6 / 0.8/s (report summary, §4.3, README) | 1.18× / 1.43×† | 1.20× / 1.46×† | 1.18× / 1.42×† | lru_queue +0.02-0.03; shared prompt 0 to −0.02; full_isl and resume none | **Holds** |
| MoE 30B-A3B never a net loss, 0.4/s FCFS + waste1 (report summary 0.66-0.74×, §4.2 0.67) | 0.67× | 0.68× | 0.67× | None by more than 0.01, although this cell preempts (median 177 legacy, 175-184 under each KV fix alone, 132 with all fixes and a shared prompt): full_isl 0.68, resume 0.67, lru_queue 0.68 alone | **Holds** (only 0.4/s re-run) |
| correct speculation, 0.8/s FCFS p50 (§4.1): eager / graphs; MoE 0.4/s | 0.45 / 0.45; 0.47 | 0.45 / 0.45; 0.48 | 0.45 / 0.44; 0.48 | none | **Holds** |
| `agent` with correct speculation, eager 0.8/s (§4.1: "0.36× vs 0.45×") | 0.36× | 0.36× | 0.36× | none | **Holds** |
| eager 0.4/s, waste1: FCFS / agent (§4.2 table) | 0.54 / 0.36 | 0.54 / 0.36 | 0.54 / 0.36 | none | **Holds** |
| §4.5 "correct speculation barely touches the root cache: hit 0.65 → 0.63" (4090, 0.14/s) | 0.65 → 0.63 | 0.38 → 0.54 | 0.80 → 0.85 | lru_queue (0.38 → 0.54 alone, as the audit found) | **Wording wrong**: under vLLM's eviction order correct speculation raises the root hit rate. "0.65 → 0.63" should not be quoted |
| §4.5 "one bad guess per call pushes it down to 0.29" | 0.29 | 0.26 | 0.72 | lru_queue 0.23 alone, full_isl 0.34, resume 0.35 | **Holds** with private prompts (from 0.54 with correct speculation to 0.26). With a shared prompt the drop is much smaller (0.85 → 0.72) |
| §4.5 "preemptions go from 20 to 524" (shadow → waste1, median seed) | 20 → 524 | 9 → 228 | 0 → 117 | full_isl (7 → 226 alone); resume alone raises them (22 → 699) because resumed requests come back faster | **Direction holds, size does not** (about 2.3× smaller) |
| §4.5 "5 s TTL pinning recovers nothing (hit 0.29) and makes latency worse: p50 92 s vs 80 s with LRU" | 91.9 vs 79.8 s (per seed pin/LRU 1.01 / 1.02 / 1.18); hit 0.29 | 58.0 vs 57.0 s (per seed 1.02 / 1.01 / 1.02); hit 0.30 | 49.0 vs 49.7 s (0.99-1.00); hit 0.75 | resume and full_isl remove the large seed-2 penalty (alone: 1.00-1.06 and 1.01-1.11) | **Half holds**: pinning recovers nothing and is 1-2% slower, not 15%. The penalty came from recompute after preemption, which vLLM avoids. The old 15% was mostly one seed |
| §4.5 "disabling prefix caching costs 1-9%" (4090, baseline, 0.02-0.14/s) | baseline 1.8-8.9%; shadow 3.2-11.1%; waste1 at 0.14/s 12.5% | baseline 1.5-5.4%; shadow 3.2-9.1%; waste1 at 0.14/s 17.5% | baseline 2.1-11.1%; shadow 4.0-14.5%; waste1 35% | shared prompt raises it (a cached shared prompt is lost too); lru_queue lowers it for the baseline | **Roughly holds**: about 2-5% without speculation, up to 9% with it |
| §4.5 "root TTFT p99 rises with correct speculation, 0.36 s → 2.1 s" | 0.36 → 2.13 s | 0.44 → 2.08 s | 0.29 → 1.94 s | lru_queue raises the baseline | **Holds** |
| §4.5 summary: "keeping the root's KV between tool calls matters much less than not wasting KV on bad guesses" | - | 4090 0.14/s: waste1 costs 0.45 → 1.01 of baseline; prefix caching off costs waste1 another 17.5% | shared: 0.46 → 0.93; another 35% | - | **Holds** |

Sensitivity, one system prompt for every session (`all+sys_all`):
- 4090 at 0.14/s: 0.91× [0.83-1.00].
- H100 graphs: 1.16×.
- No other headline moves by more than 0.01 from the per-program column.

Bets gated at schedule time (#45, `all+gate_sched`, prompt shared per program):
- The agent cells move by at most 0.01: graphs 0.36 → 0.37, eager 0.4/s 0.36 → 0.37, 40%
  wrong 0.63 → 0.62.
- That fits the audit's "≤1.4%, no published ratio changes".
- The report §4.2 explanation (decoys refused by their own sibling) describes the
  submit-time gate. It is not what the plugin does.

## What still holds, in one paragraph

Correct speculation helps on every server. Admission control (`agent`) fixes waste, and
ordering does not. Waste costs most of the gain at high load. On the CUDA-graph H100 it is
still a steady-state net loss at 0.8/s (1.30× with private prompts, 1.16× shared).

Three things change:
- The RTX 4090 at 0.14/s is break-even (1.01×), not a 1.47× loss. In words:
  "about 1.0× at 0.14/s (0.93× if sessions share their system prompt); a steady-state
  loss from 0.15/s (1.41×, private prompts) or 0.16/s (1.33×, shared), where the server
  is at capacity". "Two of four servers" stays true only with that higher 4090 load
  named.
- §4.5's TTL-pin penalty (15%) and preemption counts came mostly from the old model's
  recompute-from-scratch preemption. "0.65 → 0.63" is wrong under vLLM's eviction order.
  The report corrects them in a note at §4.5; its body text there is the original.
- Which workload a number assumes (private or shared system prompt) must be stated next
  to it. The report and the T4 bench use private prompts.

## Known limits of the corrected model

- A failed admission refreshes LRU order. When a waiting request's
  full-ISL check fails, the simulator hands its hit blocks back to the cache as most
  recently used. vLLM's `allocate_slots` returns before `touch()`
  (`kv_cache_manager.py:522-539`), so they keep their place. A scratch patch
  that restores the old position moved the 4090 headline waste1 p50 by at most 0.4%
  (49.656 → 49.453 s, seed 2, prompt shared per program). Baseline and shadow did not
  change. Not fixed.
- Two concurrent computations of one shared prefix. The second drops its copy as soon
  as it finishes the prefix; vLLM keeps both until they are freed. Only matters with a
  shared prompt.

## Other results that use the changed server (not re-run here)

All of these can be regenerated in the old model with `SPTC_LEGACY_KV=1` (see above).

- `results/prereg_v2` (second T4 run): the predictions are unchanged except C2.
  - Regenerated into a scratch directory; the prediction files were not touched.
  - B (A/B) and C1 (saturation sweep): every claim and every row's session p50 is
    identical in P0, P1 and P1-alt.
  - C2 (ReAct, `general_predictions.json`) moves only through `cache_freed_blocks`
    (#18): claim 1 1.627 → 1.628, claim 5 0.714 → 0.697, claim 7 1.000 → 1.001. All
    three stay inside their bounds.
  - Cell values move by up to 2.4% on session p50. The largest move is root TPOT p99 of
    `fcfs`/`priority` `next` at 16 agents: +7.4% (117.8 → 126.5 ms).
- `results/general` (H100 ReAct/branch workloads, `experiments/general.py`) uses
  `GeneralServer`, which already had full_isl. It now also gets resume_from_cache and
  cache_freed_blocks. Not re-run then. 16 of the 28 rows checked above move; the T4 C2
  shifts suggest changes of a few percent. *Re-run later*, at the same
  sizes, into `results/corrections/general/` (simulated): stock FCFS cells under load get
  worse (ReAct H100, 3 guesses, 8/s: +109% → +119% vs no speculation), plugin cells barely
  move. `results/general` is kept as it was.
- `results/kaggle_t4/sim_vs_t4*`, `freeride`, `allowance_ab` are not re-run.
  - The T4 replays send roots without a session key, and their B/C1 predictions are
    unchanged, so no effect is expected.
- Figures (`fig_clog_*`, `kv_rtx4090.*`) still show the old model. Re-running the
  full `run_all.sh` sweep is about 2 h of CPU and was not done.
  A re-run with `clog.py`'s new defaults uses private prompts.
