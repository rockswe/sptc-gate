# Pre-registered predictions, addendum v4b: `both` on the default servers

**PREDICTED by the simulator, not measured.** Written 2026-10-29T16:08:47Z by `experiments/prereg_v4b.py`, before any GPU run of the `both_default` preset (step 5 of the pressure run). The predictions were not changed after the run (wording about the working process and list formatting were edited for publication); `experiments/prereg_compare.py --prereg results/prereg_v4 --also results/prereg_v4b` scores it next to v4.

- Code: commit `696c206252cfb3166d9b74e9e23c6707bf11de20` (clean tree).
- Based on `results/prereg_v4` (prereg commit 4d87117, written 2026-10-29T15:14:56Z), whose files match that commit's sha256: {'prereg_v4/predictions.json': 'match', 'prereg_v4/predictions.md': 'match', 'prereg_v4_fallback/predictions.json': 'match', 'prereg_v4_fallback/predictions.md': 'match'}. Nothing in prereg_v4 changes.
- The rows are `results/pressure`'s default-config rows: each arm is the pressure arm of the same name (fcfs-d/X is fcfs-p/X) on the default config, simulated for v4's three sets; P1 equals `results/pressure/grid.json` ({'fcfs-d/nospec': 'equal', 'fcfs-d/spec': 'equal', 'fcfs-d/spec+bad': 'equal', 'prio-d/both': 'equal', 'cap-d/both': 'equal', 'plugin-d/both': 'equal'}). Nothing fit.

## Arms (preset `both_default`, 4 agents, 3 repeats, 2 launches per server)

| arm | server | tags | client cap | speculative calls | simulated as |
|---|---|---|---|---|---|
| fcfs-d/nospec | fcfs | none | - | early (untagged) | fcfs-p/nospec, default config |
| fcfs-d/spec | fcfs | none | - | early (untagged) | fcfs-p/spec, default config |
| fcfs-d/spec+bad | fcfs | none | - | early (untagged) | fcfs-p/spec+bad, default config |
| prio-d/both | priority | priority_bets | - | bets | prio-p/both, default config |
| cap-d/both | fcfs | none | window:8 | bets | cap-p/both, default config |
| plugin-d/both | plugin | sptc_bets | - | bets | plugin-p/both, default config |

## Found after prereg_v4, before any GPU run

- spec-ptc bets again on a call whose bet failed. Seen while testing the bench on the fake server (kaggle/fake_openai_server.py), after prereg_v4 and before any GPU run. A speculation that raised SpeculationRejected is invisible to spec-ptc's store (SpecStore.existing), so the shadow peeks the call again and then dispatches it from its statement. In one traced map16 turn behind the window cap (1 agent), 16 calls got 32 bets (29 refused), and the 13 calls whose bets were all refused ran for real at their claim. The simulator sends one bet per call. So where bets are refused (the cap and the plugin in `both`), the T4 arms send more bets, and more decoys (one per bet), than simulated. This bears on v4's PR-13..16, PC-3/4, PP-2 and PF-3/4, and here on every claim with cap-d/both or plugin-d/both. The predictions stay as simulated; the bench reports bets per call (sweep/summary.md, Pressure table): read those claims next to it.

## Rows (P1; P0 in brackets)

| arm | session p50 s | vs fcfs-d/spec+bad | root TPOT p50 ms | decoys rejected | real bets refused | shadow stops | preemptions | KV peak blocks |
|---|---|---|---|---|---|---|---|---|
| fcfs-d/nospec | 7.14 [7.14] | 1.521 | 17.1 [17.1] | - | - | 0 | 0 | 35 |
| fcfs-d/spec | 3.49 [3.49] | 0.743 | 21.4 [21.5] | - | - | 0 | 0 | 140 |
| fcfs-d/spec+bad | 4.70 [5.39] | 1.000 | 28.5 [32.4] | 0.00 | - | 0 | 0 | 341 |
| prio-d/both | 4.70 [5.39] | 1.000 | 28.5 [32.4] | 0.00 | 0.00 | 0 | 0 | 341 |
| cap-d/both | 6.90 [6.90] | 1.469 | 18.2 [18.2] | 0.79 | 0.85 | 16 | 0 | 57 |
| plugin-d/both | 6.90 [6.90] | 1.469 | 18.3 [18.3] | 0.77 | 0.81 | 16 | 0 | 60 |

## Claims (P1 predicted; P0, P1-alt in brackets)

| id | section | claim | predicted | tol |
|---|---|---|---|---|
| DB-1 | each arm vs fcfs-d/spec+bad (default servers) | fcfs-d/nospec / fcfs-d/spec+bad at 4: session_p50 | 1.521 [1.325, 1.429] | 0.05 |
| DB-2 | each arm vs fcfs-d/spec+bad (default servers) | fcfs-d/nospec / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.601 [0.529, 0.570] | 0.05 |
| DB-3 | each arm vs fcfs-d/spec+bad (default servers) | fcfs-d/spec / fcfs-d/spec+bad at 4: session_p50 | 0.743 [0.647, 0.698] | 0.05 |
| DB-4 | each arm vs fcfs-d/spec+bad (default servers) | fcfs-d/spec / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.750 [0.664, 0.714] | 0.05 |
| DB-5 | each arm vs fcfs-d/spec+bad (default servers) | prio-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.000 [1.000, 1.000] | 0.05 |
| DB-6 | each arm vs fcfs-d/spec+bad (default servers) | prio-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 1.000 [1.000, 1.000] | 0.05 |
| DB-7 | each arm vs fcfs-d/spec+bad (default servers) | cap-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.469 [1.279, 1.380] | 0.05 |
| DB-8 | each arm vs fcfs-d/spec+bad (default servers) | cap-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.639 [0.562, 0.605] | 0.05 |
| DB-9 | each arm vs fcfs-d/spec+bad (default servers) | plugin-d/both / fcfs-d/spec+bad at 4: session_p50 | 1.469 [1.279, 1.380] | 0.05 |
| DB-10 | each arm vs fcfs-d/spec+bad (default servers) | plugin-d/both / fcfs-d/spec+bad at 4: root_tpot_p50 | 0.642 [0.565, 0.609] | 0.05 |
| DC-1 | plugin vs the client-side cap, default servers | plugin-d/both / cap-d/both at 4: session_p50 | 1.000 [1.000, 1.000] | 0.05 |
| DC-2 | plugin vs the client-side cap, default servers | plugin-d/both / cap-d/both at 4: root_tpot_p50 | 1.006 [1.006, 1.006] | 0.05 |
| DP-1 | plugin vs vLLM priority, default servers | plugin-d/both / prio-d/both at 4: session_p50 | 1.469 [1.279, 1.380] | 0.05 |
| DF-1 | decoys rejected | cap-d/both at 4: share of decoys rejected | 0.794 [0.794, 0.794] | 0.1 |
| DF-2 | decoys rejected | plugin-d/both at 4: share of decoys rejected | 0.768 [0.768, 0.768] | 0.1 |

## Rules (v4's, unchanged)

- validity. A measured point counts only if every run has status ok and its row's cpu_ok is true (whole-host CPU < 0.85 mean, < 10% of seconds >= 95% busy). Otherwise every claim using it is 'invalid'.
- ratio. measured ratio m of two measured points vs predicted p: supported if |m - p| <= tol; refuted if |m - p| > tol and the numerator's 95% CI does not overlap p x the denominator's 95% CI (both from vllm_bench.summarize's bootstrap); otherwise unresolved. Eager ratios use eager points only.
- fraction. measured share of decoys logged 'rejected' vs predicted: supported if within tol (absolute), otherwise refuted.
- points. for every measured (arm, load), |log(predicted / measured)| of session p50 and root TPOT p50 for P1, P0 and P1-alt: median and max, P1's in-sample points (1/4/8 agents of fcfs/* and plugin/*) apart from the rest. Not pass/fail.
- step5. Claims DB, DC, DP use v3's ratio rule and DF v3's fraction rule. The denominators are fcfs-d/spec+bad (DB), cap-d/both (DC) and prio-d/both (DP), all at 4 agents on the default servers' launches.

## How to read these (fixed before the run)

- Not part of the decision rule. Step 5 has no KV pressure, and the rule needs the pressure check. It shows what a fixed window of 8 costs when half the bets are needed: on stock FCFS nothing is refused, so fcfs-d/spec+bad is `both` with every bet admitted, and fcfs-d/spec sends only the needed bets (the oracle).
- Why cap and plugin lose here (v4's reading rule, unchanged): in mix4 the shadow forces nearly every speculation, and spec-ptc's shadow stops for the rest of the turn when it forces a refused bet. The window of 8 refuses most real bets at 4 agents, so these arms run close to no speculation (fcfs-d/nospec).
- Pooled p50s sit on pattern clusters (v4's): read every session_p50 claim with prereg_compare.py's per-pattern ratios.

## GPU time (estimate)

Preset `both_default`: 18 runs on 6 launches (plus up to 1 cache-filling), about 48 min with `vllm_bench.plan`'s constants and P1's session times.
