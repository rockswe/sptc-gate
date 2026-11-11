# Third T4 run: KV pressure and a real queue, vLLM 0.32, October 29, 2026 (measured)

This is the scored run of `kaggle/sptc_kaggle_v4.ipynb` with bundle v4 (pressure
`0f57918`), run in a Kaggle notebook session.

- Setup: Tesla T4, vLLM 0.32.0 with CUDA graphs, Qwen3-1.7B fp16. Every arm ran at 4
  agents: 3 repeats on 2 server launches in ABBA order, 48 sessions per arm. All
  servers of one KV config loaded the same compiled artifact.
- The plugin was unchanged since run 2's bundle (`53722e0`). The notebook checks this
  (`BUNDLE_INFO.json`).
- Files: the run's output is `sptc_out_v4.zip`, repacked for publication. The copies of
  the prediction files, `prereg_compare.md`, `sweep/summary.md` and `BUNDLE_INFO.json`
  inside it carry the published wording (no number in them changed; `BUNDLE_INFO.json`
  no longer names local paths and branches), and every other file is as the run wrote
  it. The zip the run produced had a sha256 starting `e1723b602e9a`; the repacked one
  hashes differently. Readable copies in this folder: `sweep_summary.md`,
  `prereg_compare.md`, `launches.jsonl`, `pressure_config.json`, `BUNDLE_INFO.json` and
  the test logs.
- Integrity: the prediction files match their prereg commits by sha256:
  prereg_v4 and prereg_v4_fallback (`4d87117`), and the step-5 addendum prereg_v4b
  (`b926d71`). Both were committed before the bundle was built (16:09 UTC) and before the
  first server launch (18:28 UTC).

**The question:** under KV pressure and a real queue, with bets that are
sometimes needed, does the plugin beat a client-side cap and vLLM priority? The rule, fixed
before the run: the plugin wins if its session p50 is at least 5% below the cap's at 4
agents, in either workload, with the pressure check passed.

**Workloads.**
- `decoys`: as in run 2. Every real speculative call comes with one decoy, forced to
  maximum length and never used.
- `both`: spec-ptc's real speculative calls are bets too, each with one decoy. This
  models "both arms of a branch launched, one used", so half the bets are needed. On stock
  FCFS, `both` is identical to `spec+bad` (tags are ignored and nothing is refused), so
  `fcfs-p/spec+bad` is the stock reference for both workloads.

**Servers.**
- `-p` (pressure): `--num-gpu-blocks-override 129 --max-num-seqs 256 --max-model-len
  512`. That is 2,064 tokens of KV cache.
- `-d` (default): vLLM's defaults, 85,904 tokens of KV cache.
- Cap: run 2's client-side window cap. A bet is sent only if every in-flight request,
  roots included, + 1 ≤ 8.
- Tags: the plugin and priority arms tag only the bets, the class as the RFC draft
  proposes it (tag schemes `sptc_bets` and `priority_bets`).

**Ratios** are numerator over denominator, pooled session p50 or root TPOT. Below 1 is
faster. "Root TPOT p99" is the slowest session's mean, as in run 2.

## 1. Answer: the plugin does not beat the cap

| workload | plugin vs cap, session p50 | plugin vs priority |
|---|---|---|
| decoys, pressure servers | **0.982** | 0.778 |
| both, pressure servers | **1.000** | 1.646 |
| both, default servers (reported, not part of the rule) | 0.992 | 1.758 |

- Pressure check: passed.
  - `fcfs-p/spec+bad` preempted 192 times per run and had a request waiting in 42% of the
    1-second samples (max 49 waiting). The threshold was 16 preemptions per run or a
    queue in 25% of samples.
  - `fcfs-p/spec` did neither: 0 preemptions, 0%.
- By the pre-registered rule, the plugin does not win.
- A first full sweep on the same config, lost in a Kaggle session restart (below), had
  read 0.980 and 0.974. Both are also above the 0.95 threshold.

## 2. Every arm (`sweep_summary.md`, Pressure table)

Ratios to the stock reference on the same servers (`fcfs-p/spec+bad` or
`fcfs-d/spec+bad`).

Column notes:
- Refused: the share logged rejected. A bet dropped before its first token is
  included, since the client cannot tell the two apart.
- Bets per call: real bets over the distinct calls they were for.
- Re-runs: calls run for real at their claim after their bets were refused.
- Shadow stops: sessions whose spec-ptc shadow stopped at a refused bet it forced.
- Preemptions: vLLM's counter, per run.
- Queue: the share of 1-second samples with a request waiting.

| arm | session p50 | root TPOT p50 / p99 | decoys refused | real bets refused | bets per call | re-runs | shadow stops | preemptions | max waiting | queue | KV peak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fcfs-p/nospec | 1.641 | 0.633 / 0.333 | - | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.27 |
| fcfs-p/spec | 0.667 | 0.773 / 0.435 | - | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.70 |
| fcfs-p/spec+bad (5.99 s) | 1.000 | 1.000 / 1.000 | 0% | - | - | 0 | 0/48 | 192 | 49 | 42% | 1.00 |
| prio-p/spec+bad | 0.870 | 1.022 / 0.597 | 0% | - | - | 0 | 0/48 | 148 | 31 | 42% | 1.00 |
| cap-p/spec+bad | 0.689 | 0.794 / 0.436 | 95% | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.90 |
| plugin-p/spec+bad | 0.676 | 0.782 / 0.435 | 97% | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.83 |
| prio-p/both | 0.915 | 1.005 / 0.570 | 0% | 0% | 1.12 | 0 | 0/48 | 240 | 40 | 52% | 1.00 |
| cap-p/both | **1.505** | 0.680 / 0.360 | 85% | 91% | 1.73 | 345 | 34/48 | 0 | 0 | 0% | 0.48 |
| plugin-p/both | **1.506** | 0.682 / 0.369 | 83% | 94% | 1.67 | 363 | 35/48 | 0 | 0 | 0% | 0.49 |
| fcfs-d/nospec | 1.947 | 0.629 / 0.573 | - | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.01 |
| fcfs-d/spec | 0.782 | 0.759 / 0.734 | - | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.02 |
| fcfs-d/spec+bad (5.04 s) | 1.000 | 1.000 / 1.000 | 0% | - | - | 0 | 0/48 | 0 | 0 | 0% | 0.04 |
| prio-d/both | 1.004 | 1.000 / 0.996 | 0% | 0% | 1.12 | 0 | 0/48 | 0 | 0 | 0% | 0.04 |
| cap-d/both | **1.780** | 0.675 / 0.616 | 86% | 92% | 1.72 | 355 | 35/48 | 0 | 0 | 0% | 0.01 |
| plugin-d/both | **1.766** | 0.677 / 0.621 | 83% | 92% | 1.66 | 362 | 34/48 | 0 | 0 | 0% | 0.01 |

## 3. With worthless bets, a cap does what the plugin does

In `decoys` under pressure:
- Both gates refused nearly every decoy: 95% for the cap, 97% for the plugin.
- Neither gate's arm preempted or queued. The decoys never built the KV pressure
  that preempted stock 192 times per run.
- Both ran close to stock without decoys: 0.689 (cap) and 0.676 (plugin), against
  0.667.

Priority now has a queue to reorder, unlike run 2:
- 0.870 of stock, with fewer preemptions (148 vs 192 per run) and a shorter maximum
  queue (31 vs 49). The slowest session's root TPOT is 0.597 of stock's, which is
  stock's preemption stalls showing.
- Priority's session ratio is unresolved: CI 0.713–1.021.
- The plugin was faster than priority: 0.778, CI 0.646–0.863.

## 4. With bets that are sometimes needed, refusing costs more than it saves

In `both`, the cap and the plugin made sessions **1.51× slower than stock** under
pressure, and 1.77–1.78× on the default servers. Stock admits every bet. The gates ended
close to no speculation (1.64× and 1.95×).

Why:
- They refused most real bets (91–94%). The window counts the four root streams, so at
  4 agents a burst of speculative calls finds it full.
- spec-ptc then stopped speculating for the rest of the turn. In this workload its
  shadow forces nearly every speculation. With the sptc-hints patch, a forced bet that
  was refused stops the shadow (34–35 of 48 sessions). The real run then re-runs the call
  at its claim (345–363 re-runs).
- spec-ptc also bet again on calls whose bet had failed: a peek first, then the
  statement. That gave about 1.7 bets per call, where the simulator assumed 1.0
  (`results/prereg_v4b`, "Found after prereg_v4").
- Root TPOT was lower (0.68), because fewer sub-calls decoded next to the roots. But the
  sub-calls started late, so the sessions took longer.

**Waiting beat refusing.** vLLM priority never refuses a bet; it only makes bets wait when
a queue forms.
- Plugin vs priority:
  - pressure servers: 1.646, CI 1.188–2.334 (predicted 1.089: refuted);
  - default servers: 1.758, CI 1.496–2.561.
- Priority vs stock: 0.915 under pressure, unresolved (CI 0.775–1.236). On the default
  servers it is 1.004, where nothing waits.

**Per-pattern geometric means tell the same story.** Each is the median session per
pattern, numerator over denominator, which cannot jump between pattern clusters as the
pooled p50 can:
- cap-p/both 1.442 and plugin-p/both 1.479 of stock;
- plugin vs priority 1.491 (pressure) and 1.905 (default).

**The simulator had isolated the mechanism before the run** (simulated, on the chosen
config, `results/pressure/README.md`). With 'reissue', where a forced refused bet re-runs
at once as normal work and the shadow keeps going, the gates ran at 1.026–1.036 of stock
in `both`, not 1.413. So most of the gates' loss here comes from the client stopping its
shadow at a refusal, not from the admission rule alone.

## 5. Pre-registered vs measured (`prereg_compare.md`)

| prediction set | supported | refuted | unresolved | strict: supported / refuted / unresolved |
|---|---|---|---|---|
| prereg_v4_fallback, simulator claims (P1), 26 | 14 | 8 | 4 | 5 / 6 / 11 |
| prereg_v4b, `both` on default servers (P1), 15 | 11 | 0 | 4 | 3 / 1 / 9 |

**The claims that decided the rule held.** Plugin vs cap was predicted 0.989 / 1.000
(PC-1, PC-3) and measured 0.982 / 1.000: supported. The strict rule supports the
root-TPOT versions (PC-2, PC-4) and leaves the session ones unresolved. Decoys refused
were within the tolerance in every gate arm (PF-1..4, DF-1..2).

**The point predictions missed, by more than in earlier runs.** Out of sample, the median
|log(predicted / measured)| was 0.144 for session p50 (max 0.320) and 0.101 for root TPOT
(max 0.150). That is about 15% on session p50, against a median error of 3% in the first
T4 run. Two errors explain most of it:
- No speculation was slower than predicted: 9.83 s and 9.81 s measured on the two
  server configs, against 7.14 s.
- Preemption cost less than predicted: stock with decoys on the pressure servers ran
  in 5.99 s at 192 preemptions per run, against 6.98 s predicted at 183. This was the
  simulator's first check under heavy preemption. Its preemption counts were close; their
  cost was too high.

Together they refuted the `both` predictions on the pressure servers. The simulator
predicted the gates at 0.988 of stock there, because it expected stock with decoys to be
almost as slow as no speculation (PR-1: 1.023 predicted, 1.641 measured). Measured, the
gates were at 1.505 and 1.506 (PR-13, PR-15: refuted, strict too).

## 6. What else the run shows

- The plugin's drop-first rule never fired, even here: no bet was dropped after its
  first token in any plugin arm. Admission kept KV usage at or under 0.83, so vLLM never
  needed a victim. KV-aware dropping still has no load measurement.
- Priority with only the bets at low priority ran for the first time with a queue.
  It is the one engine-side change that helped in `both`, but its gain over FCFS is
  unresolved.
- Tests: the plugin's tests passed (166, 82 skipped), and so did the bench's (67).
- Server logs: the only traceback is vLLM's output handler raising `EngineDeadError`
  while the bench stopped `plugin_p#2` in abort mode with a 0 s timeout, after its last
  run. The "FA2 is only supported on devices with compute capability >= 8" errors are the
  T4's usual notices.
- GPU clocks varied between launches, as in run 2: lowest SM clock 450–1065 MHz, peak
  82 °C. Compare within this run only.

## 7. How the config was chosen, and what was lost

- Fallback config. The probe on the chosen config (257 blocks) showed 2 preemptions
  and no queue on `fcfs-p/spec+bad`, far below the pressure check. So the run switched
  to the pre-registered fallback (129 blocks). That was decided on stock FCFS arms only,
  before any other arm ran (`pressure_config.json`), and the run is scored against
  `results/prereg_v4_fallback`. The simulator had predicted 57 preemptions per run on
  the chosen config. The T4 needed less KV than predicted, which is the case the
  fallback was for.
- Lost output. A Kaggle session restart deleted the first output directory: both
  probes' files, and a first full pressure sweep on the fallback config (all 27 runs ok;
  plugin vs cap 0.980 decoys, 0.974 both; pressure check passed). The probe values in
  `pressure_config.json` were copied from that session's output. The sweep was then rerun
  unchanged, and that rerun is what is scored here.

## 8. What it changes

- By the pre-registered rule: admission control matters, but it doesn't need a new
  scheduler. A client-side cap that counts every request in flight matched the plugin in
  every condition measured: run 2 without pressure, and here under KV pressure and a real
  queue. The plugin stays as the reference implementation and the test harness.
- The rule would turn the RFC's ask into a per-class admission limit. But a per-class
  limit is also a refusal, and `both` shows that refusing bets that are sometimes needed
  costs more than it saves, while letting them wait does not. So the RFC draft is held
  (`docs/related_work.md`).
- Deciding which bets to send matters more than how the server treats them. And a
  speculator that stops at a refusal turns every refused bet into lost speculation for
  the rest of the turn.

## Limits

- Small scale: one T4, one 1.7B model, 4 agents only, 3 repeats.
- An artificial squeeze: the pressure servers had 2,064 tokens of KV cache.
- Synthetic waste: every wasted call is a decoy, and in `both` every real speculative
  call was made a bet with a 50% hit rate. Real code-mode speculation makes far fewer bets
  (`results/census/SUMMARY.md`).
- The client is part of what's measured: spec-ptc with the sptc-hints patch stops its
  shadow at a refused bet it forces, and bets again on failed calls. A client that keeps
  going would lose much less. That is simulated only ('reissue', above).
- Pooled p50 jumps between pattern clusters in the `both` arms: launch-to-launch
  spread is 33–36%. Read the per-pattern geometric means alongside.
