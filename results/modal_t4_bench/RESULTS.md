# The T4 bench on Modal, November 10, 2026 (measured)

Two questions about the client changes in the `sptc-hints` fork of spec-ptc, on a real
engine with fixed programs:

1. Does a client that survives a refused call lose less when a gate refuses bets that are
   sometimes needed? (The third T4 run's `both` workload.)
2. Does the scout pass launch the loops that real RLM code writes?

**Setup.** One Tesla T4 on Modal per run, vLLM 0.32.0, Qwen3-1.7B fp16, 8 CPU cores.
`cloud/bench_app.py` runs `kaggle/vllm_bench.py` unchanged in how it measures.
- Old client: the fork's last commit `9a6c7af`, the client of the three Kaggle runs.
- New client: the fork's working tree of November 10 (refusal survival, the peek
  fix, the scout off unless asked for).
- GPU time: 51 T4-minutes.

## In short

- Surviving a refusal helps a little, not a lot. With bets that are needed half the
  time, the client-side cap cost 1.94× stock with the old client and 1.82× with the new
  one; the plugin 2.05× and 1.77×. No speculation costs 1.84×.
- The simulator's 1.03 did not appear. A refused call is re-run when the program
  reaches the use of its result, so the refused calls of a fan-out still run one after
  another.
- The scout halves the turn on the recorded loop shapes. Baseline 5.55, 3.41 and
  7.65 s; spec-ptc as shipped 5.25, 3.30 and 7.45 s; with the scout 2.82, 2.45 and 3.83 s.
  No call was wasted.

## 1. Refused bets that are sometimes needed (`both_default`)

The third T4 run's step 5, again: 4 agents, the `mix4` programs, every real speculative
call a bet with one decoy next to it, default servers. 3 repeats on 2 launches per server
(ABBA), 48 sessions per arm. Runs `20261110-012130-both_default-old` and
`20261110-005558-both_default-new`: two containers, so each client is compared with the
stock arm of its own run.

**Read per pattern.** The bench's pooled session p50 sits between the patterns' clusters
(4 to 16 s) and jumps: with the old client it reads 1.83× for the cap and 2.18× for the
plugin, which tie on every pattern but one. Below: the median per pattern, its ratio to
stock (`fcfs-d/spec+bad`), and the geometric mean over the four patterns
(`cloud/both_compare.py`, output in `both_per_pattern.txt`).

| arm | old client | new client |
|---|---|---|
| no speculation | 1.855 | 1.839 |
| stock, speculation with decoys | 1.000 | 1.000 |
| vLLM priority, bets only | 0.998 | 0.995 |
| client-side cap | 1.942 | **1.823** |
| plugin | 2.052 | **1.768** |

By pattern, ratio to stock:

| arm, client | map16 | map_reduce | side_branch_chain | two_stage |
|---|---|---|---|---|
| cap, old | 3.26 | 1.44 | 1.11 | 2.72 |
| cap, new | 3.29 | 1.11 | 1.12 | 2.69 |
| plugin, old | 3.28 | 1.50 | 1.33 | 2.71 |
| plugin, new | 3.31 | 1.09 | 1.11 | 2.43 |

What the client did, per session:

| | cap, old | cap, new | plugin, old | plugin, new |
|---|---|---|---|---|
| sessions whose shadow stopped at a refused bet | 34 of 48 | **0 of 48** | 36 of 48 | **0 of 48** |
| bets per call | 1.70 | 1.12 | 1.65 | 1.12 |
| bets sent | 14.5 | 11.2 | 13.9 | 11.2 |
| calls re-run for real | 7.1 | 8.9 | 7.4 | 9.0 |
| decoys that ran | 2.1 | 2.8 | 2.2 | 2.8 |

- The mechanism works: no shadow stops, and a refused call is hardly ever bet on a
  second time.
- The gain is 6% for the cap and 14% for the plugin. For the cap all of it is on
  `map_reduce`; for the plugin also on `side_branch_chain` and `two_stage`. With the new
  client a gate that refuses needed bets costs about what no speculation costs. With the
  old client it cost 5–11% more than that.
- A fan-out of refused bets stays serial. On `map16` both clients are at 3.3× stock.
  The refused calls are re-run one at a time, as the program reaches each result.
- Waiting still beats refusing. vLLM priority, which refuses nothing, is at 1.00×
  with either client.
- The old client's numbers match the Kaggle run (third T4 run: 35 and 34 shadow stops
  of 48, 1.72 and 1.66 bets per call, 355 and 362 re-runs), so the Modal T4 reproduces it.
- Launch effect: the reference arms are 1.2–2.1% slower in the new client's run.

**Against the simulator.** Its `reissue` variant put the gates at 1.03–1.04× stock on the
pressure servers (`results/pressure/README.md`). That variant was not simulated on these
default servers, and its re-run of a refused bet is not what a client can do: here the
re-run starts when the shadow needs the value, not when the bet is refused.

## 2. The scout on recorded loop shapes (`suite`)

Run `20261110-010635-suite-new`. Three programs taken from the RLM campaign's recorded
code and shortened (`benchmark/suite/patterns_v7.py` in the fork), on the suite's corpus.
The root's text is streamed at 60 tokens/s by the bench, not by the engine. Sub-calls are
real requests. 5 runs per cell, in ABBA order. Wall time of the turn, median [min–max]:

| program | calls | no speculation | spec-ptc as shipped | with the scout | calls launched before the first answer: shipped / scout |
|---|---|---|---|---|---|
| helper loop, each result used | 16 | 5.55 [5.53–6.46] | 5.25 [5.24–5.26] | **2.82** [2.81–2.84] | 1 / 16 |
| batches in a loop, results counted | 32 | 3.41 [3.40–3.47] | 3.30 [3.28–3.31] | **2.45** [2.44–2.47] | 4 / 32 |
| loop with `try` and a fallback | 8 | 7.65 [7.64–7.69] | 7.45 [7.45–7.46] | **3.83** [3.83–3.84] | 1 / 8 |

- As shipped, speculation gains 3–5% on these shapes. The shadow stalls at every
  result.
- With the scout: 0.51, 0.72 and 0.50 of the baseline. Every call was claimed, none
  was missed, none was evicted, and every program's answer check passed.
- A call takes longer when it runs next to the others (median 0.17 → 0.32 s,
  0.17 → 0.25 s, 0.59 → 0.82 s), and the turn is still shorter.
- A turn cannot be shorter than its stream: 2.7, 2.0 and 3.0 s here. After it the
  baseline needed another 2.9, 1.4 and 4.7 s, and the scout 0.1, 0.5 and 0.8 s.

## Limits

- Small: one T4, one 1.7B model, 4 agents (section 1), one program at a time
  (section 2).
- Section 2's root is not on the engine, so nothing competes with the sub-calls for
  the GPU except each other. The programs have 8 to 32 calls. The recorded ones had 160
  to 3,188, which the 16-call cap would throttle.
- Section 1's waste is synthetic: decoys, and real calls treated as bets.
- Two containers in section 1. Compare each client with its own run's stock arm.
- No pre-registration: neither sweep's outcome was predicted in writing before it ran.
