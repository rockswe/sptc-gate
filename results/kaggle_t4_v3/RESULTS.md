# Second T4 run: vLLM 0.32, October 20, 2026 (measured)

This is the scored run of `kaggle/sptc_kaggle_v3.ipynb` with bundle v3, executed as a Kaggle commit run.

- Setup: Tesla T4, vLLM 0.32.0, torch 2.13.0+cu130, Qwen3-1.7B fp16, CUDA graphs
  unless marked eager.
- Files: the run's output is `sptc_out_v3.zip`, repacked for publication. The copies of
  the prediction files and `prereg_compare.md` inside it carry the published wording (no
  number in them changed), and every other file is as the run wrote it. The zip the run
  produced had a sha256 starting `9a0781b031cd`; the repacked one hashes differently.
  Readable copies in this folder: `sweep_summary.md`, `prereg_compare.md`,
  `launches.jsonl`, `overhead/`, `smoke_vllm_s123.jsonl`, the test logs and
  `general_quick.json`.
- Integrity: the prediction files match their commits by sha256: prereg_v3
  (`3ded06b`), prereg_v3b (`da1ae49`) and prereg_v2 (`3f835a4`). All three were committed
  before the run.

**Ratios** are numerator over denominator, pooled session p50 or root TPOT. Below 1 is
better.

**Repeats:** every arm ran on 2 server launches in ABBA order: 5 repeats at 1 agent, 3 at
4 and 8. Stock and plugin loaded the same compiled artifact.

**"Root TPOT worst"** is the slowest session's mean time per output token. The bench calls
it "p99"; it is not a per-token tail.

## 1. Headline: wasted speculation on a shared server

Each agent wastes one decoy speculation per real one (forced to max length, never used).
Stock is FCFS; plugin is `prefill_allowance: fixed`.

| agents | session p50: stock → plugin | root TPOT p50 | root TPOT worst | decoys refused by the plugin |
|---|---|---|---|---|
| 8 | 7.49 → **5.20 s (−31%)** | 39.4 → **28.6 ms (−27%)** | 46.6 → **33.3 ms (−29%)** | 1080 of 1080 |
| 4 | 5.51 → **4.13 s (−25%)** | 30.4 → **23.4 ms (−23%)** | 34.4 → 25.7 ms (−25%) | 518 of 540 |
| 1 | 4.30 → **3.89 s (−10%)** | 24.0 → 23.5 ms (−2%) | 30.1 → **34.7 ms (+15%)** | 137 of 225 |

- At 8 agents the plugin with decoys matches stock without any. It ran at 5.20 s
  against 5.05 s for stock with no decoys (`fcfs/spec`), and root TPOT was the same
  (28.6 vs 28.4 ms).
- At 1 agent the slowest session got slower. The plugin admits about 40% of the
  decoys there, because there is spare capacity. Those decoys decode next to the root
  stream, so the median improves but the slowest session's TPOT rises 15%. This is the
  "bounds, not removes" cost of the class.
- Goodput under the bench's SLO (2× the 1-agent no-speculation session and TPOT) was
  1.00 for every 1–8 agent arm here. The tighter thresholds of the goodput curve
  (`sweep_summary.md`) separate them. At 8 agents, stock with decoys scores 0.00 at 1.25×
  and 0.35 at 1.5×; the plugin scores 0.94 and 1.00.
- Pre-registered prediction (P1) for the 8-agent session ratio: 0.752. The measured
  0.695 is outside the tolerance, so the claim is scored **refuted**; the plugin did
  better than predicted. Root TPOT at 8 agents (0.741 predicted, 0.728 measured) is
  supported under the strict launch-level rule.

## 2. vLLM priority scheduling does not help

| comparison | 1 agent | 4 agents | 8 agents |
|---|---|---|---|
| `--scheduling-policy priority`, all speculation at low priority, vs FCFS (with decoys) | 1.011 | 1.000 | 0.989 |
| priority with only the decoys (bets) at low priority, vs FCFS with decoys (B4) | - | 0.996 | 1.006 |

Priority orders the waiting queue, but here nothing waits: max waiting is 0 in every valid
1–8-agent cell. Requests wait only in cells voided by the CPU rule and at 16+ agents.
Once a decoy is running it decodes in every step, whatever its priority. This matches the
pre-registered predictions (PRIO-5: 1.000 predicted, 0.989 measured, supported).

## 3. Baselines: can a client-side cap do the same? (B4)

Every arm is compared with stock FCFS with decoys, on launches next to it. "vs no bets"
compares with stock without decoys.

| arm | 4 agents | 8 agents | vs no bets (4 / 8) | decoys refused (4 / 8) |
|---|---|---|---|---|
| stock FCFS with decoys | 1.000 | 1.000 | 1.28 / 1.40 | 0% / 0% |
| priority, bets only | 0.996 | 1.006 | 1.28 / 1.41 | 0% / 0% |
| client-side semaphore: at most 8 bets in flight | 0.883 | 0.810 | 1.13 / 1.14 | 68% / 82% |
| client-side window cap: a bet only if all in-flight requests (roots included) + 1 ≤ 8 | 0.807 | 0.714 | 1.03 / 1.00 | 95% / 100% |
| **sptc plugin** | **0.780** | 0.718 (void, see below) | **1.00** / 1.01 | 96% / 100% |
| stock FCFS without decoys (the floor) | 0.781 | 0.713 | 1.00 / 1.00 | - |

- The plugin's 8-agent B4 cell is void. Its host CPU saturated, so the pre-registered
  rule voids it, and B4N-15/16 are scored invalid. 0.718 is shown for reference only.
- At 4 agents (every cell valid) the plugin is 3% better than the best client-side cap
  (0.780 vs 0.807) and reaches the floor (0.781).
- At 8 agents the window cap (valid) reaches the floor (0.714 vs 0.713), and the void
  plugin cell reads the same. A client-side cap that counts every request in flight comes
  close to, or matches, the plugin here.
- A plain semaphore on bets is 13% slower than the plugin. It cannot see the root
  streams, so it admits bets into a full batch.
- Both the plugin and the window cap reach the floor (no decoys at all), because every
  decoy here is worthless, so refusing all of them is optimal. This setup cannot show a
  cost of refusing too much, or anything the in-scheduler rules add under KV pressure (no
  run here preempted).
- Pre-registered (prereg_v3b): 14 supported, 4 unresolved, 2 invalid (host CPU; the
  plugin's 8-agent cell). The
  window cap's tie (B4N-3/4: 1.000 predicted, 1.002 / 1.009 measured) and the semaphore's
  gap (B4N-5/6: 1.131 / 1.126 predicted, 1.131 / 1.127 measured) are supported.

## 4. The October 19 light-load cost does not reproduce

At 1 agent with speculation and no decoys, against stock:

| arm | session p50 ratio | root TPOT p50 ratio |
|---|---|---|
| plugin, fixed / adaptive / off | 1.012 / 1.019 / 1.017 | 1.002 / 0.992 / 1.006 |
| plugin, untagged traffic | 0.997 | 0.998 |
| eager launches: plugin vs stock | 1.004 | 0.999 |
| eager: adaptive / off vs fixed | 1.006 / 1.001 | 0.991 / 0.984 |

- No arm shows the +13.5% / +16% gap of October 19. Stock and plugin now load the same
  compiled artifact, so the old gap most likely came from the two servers running
  different compiled code (`results/t4_run1_analysis/root_cause.md`, candidate 2).
- The session ratios' launch-level CIs are wide (about ±15%) and stay "unresolved"
  under the strict rule. The root TPOT ratios on eager launches are tight (EAG-2
  [0.982, 1.024]).
- The three allowance modes are indistinguishable here. The default stays `fixed`.

## 5. Scheduler overhead (`overhead/overhead_vllm.md`)

Stock vLLM's `Scheduler` vs `SptcScheduler` on vLLM 0.32. Each cell is the p50 of
`schedule()` + `update_from_output()`, in µs added per step.

| running requests | untagged, sync / async | with bets, sync / async |
|---|---|---|
| 8 | +9.0 / +0.7 | +17.2 / +15.8 |
| 64 | +72.7 / +40.6 | +82.9 / +55.1 |
| 512 | +45.1 / +172.8 | +349.8 / +403.7 |

- All 24 cells are inside the pre-registered bounds.
- A decode step in these runs takes about 23–40 ms, so tens of µs is under 0.1%.
- The pure policy work, measured alone, is in `overhead/overhead_pure.md`.

## 6. Smoke tests (`smoke_vllm_s123.jsonl`)

- S1: a bet on an idle server completes.
- S2: a bet with no spare capacity is refused at once (`stop_reason=sptc_bet_rejected`;
  a streamed refusal ends with no finish reason).
- S3: `early` calls complete. With them tagged, a concurrent normal stream's longest
  stall fell from 892 ms to 468 ms (median over passes). This is the first measured effect
  of the prefill allowance; S3 was rewritten after audit #41.
- The server log has no tracebacks.

## 7. Beyond sPTC: ReAct next-call guessing (one run per cell, indicative)

On stock vLLM, 3 next-call guesses per step slow 8 agents down 1.53×. vLLM priority does
not help (1.014). The plugin removes most of the slowdown (0.767). These are claims 1, 3
and 5 of the pre-registered general workload, all supported. The rest of that matrix was
not run.

## 8. What did not work

- Saturation (16–32 agents): invalid. The bench client shares Kaggle's small host CPU
  with the server. From 16 agents the host CPU saturated, and the pre-registered validity
  rule voids those cells.
  - Indicative only: the plugin ran at 0.585 of stock with decoys at 16 agents and 0.532
    at 24.
  - Some 8-agent no-decoy cells are void for the same reason.
- Refuted predictions (8 of 101 scored P1 claims):
  - The plugin did better than predicted at 8 agents (0.69 vs 0.75).
  - It refused fewer decoys at 1 agent than predicted (61–67% vs 78%).
  - The goodput knee came at 16 agents, not 8.
- GPU clocks varied widely between launches (lowest SM clock 330–1395 MHz; peak
  temperature 81 °C). Comparisons pair arms within a launch round in ABBA order. The
  absolute times also differ from the October 19 run, so compare only within one run.
- Tests: 407 passed, 1 failed. The failure is the startup-log test, a test-environment
  issue fixed in `864672e` after this bundle; the startup line printed on every launch.
  Simulator and bench tests: 200 passed.
