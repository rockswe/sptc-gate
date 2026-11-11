# Audit findings and decisions

An audit of the plugins and the simulator raised 44 findings: 3 high, 10 medium, 31 low
(numbered 1-45; there is no #9). Each was re-checked against the code and decided.

"Fixed" means fixed in code, with a local test that fails on the old code (or, for
`tests_vllm` / `tests_sglang`, a test traced by hand against the vendored sources). The
vLLM tests ran in section A of `kaggle/sptc_kaggle_v3.ipynb`, in the second T4 run. The
SGLang tests have not run on SGLang.

| # | sev. | area | decision |
|---|---|---|---|
| 1 | medium | vLLM | fixed: a bet in an async KV load is never gated again |
| 2 | medium | vLLM, SGLang, sim | vLLM: fixed (a running bet's prefill leaves waiting early prefill its allowance). Simulator: mirrored (`ServerConfig.plugin_fixes`). SGLang: open, documented; the two plugins now differ on this rule |
| 3 | low | vLLM | fixed: grammar-error bets left to vLLM (FINISHED_ERROR) |
| 4 | low | vLLM | fixed: budget raised to the MTP lookahead at startup, with a warning |
| 5 | low | vLLM | fixed: hold counter uses vLLM's real `defer_prefills` test |
| 6 | low | vLLM | documented: at most a one-step deferral |
| 7 | high | SGLang | fixed: a chunked bet is dropped before a retracting decode step; a chunked early request is retracted (requeued) instead of a decoder when SGLang's order would pick it |
| 8 | medium | SGLang | fixed: forced decode decided per step, after unmixed tagged prefill steps |
| 10 | low | vLLM, sim | fixed: hold not counted when another bet's prefill took the allowance. The simulator mirrors it |
| 11 | low (test) | vLLM tests | fixed: differential test overlaps async steps (batch queue of 2). Runs on vLLM only |
| 12 | low (test) | SGLang tests | fixed: untagged differential against SGLang's own scheduling code (vendored), the audit mutant fails |
| 13 | low (test) | vLLM tests | fixed: full SchedulerOutput compared, EOS, default-like config with prefix caching, and a 16-token-budget case that catches capped untagged prefill. Runs on vLLM only |
| 14 | low (test) | SGLang tests | fixed: page size and alignment on SGLang's own admission code |
| 15 | low (test) | vLLM, SGLang tests | fixed: local stand-in of vLLM 0.32's scheduler (34 tests) and SGLang's vendored code |
| 16 | low (test) | SGLang tests | fixed locally; the real-SGLang half is pending a GPU run |
| 17 | medium | sim | fixed: resume from the prefix cache after preemption (`resume_from_cache`) |
| 18 | medium | sim | fixed: one LRU free queue (`cache_freed_blocks`). The only fix that moves the second run's predictions (C2) |
| 19 | low | vLLM | fixed: a requeued, then refused bet ends `sptc_bet_dropped`; readmissions counted apart |
| 20 | low | vLLM | documented: one-step effect; vLLM's own `max_num_seqs` counts the same way |
| 21 | medium | SGLang | fixed: a bet SGLang's reservation refuses is skipped and held, no `batch_is_full` |
| 22 | high | SGLang | fixed: tagged prompts that fit the cap admitted whole; budget rounded to page and chunk alignment |
| 23 | low | SGLang | fixed: bets SGLang already failed are left to SGLang |
| 24 | low | SGLang | fixed: gate inputs computed once per admission (O(N) pass) |
| 25 | low | vLLM, sim | fixed: steps that schedule no tokens do not count toward `bet_hold_steps`. The simulator mirrors it (it only matters there for a bet that can never fit) |
| 26 | low | vLLM | handled by `prefill_allowance: adaptive`, not the default; the second run's A/B found the modes indistinguishable, so the default stays `fixed` |
| 27 | low (test) | SGLang tests | fixed: a chunk continuation is charged to the allowance |
| 28 | low (test) | SGLang tests | fixed: finished requests left in the running batch tested |
| 29 | low (test) | vLLM tests | fixed: the three async in-flight guards have tests (stand-in and on vLLM) |
| 30 | low (test) | SGLang tests | fixed: the fake can park the chunked request |
| 31 | low (test) | SGLang tests | fixed: the late-bet test starts below the KV threshold |
| 32 | high | sim | fixed: full-sequence admission (`full_isl`, default True) |
| 33 | low | vLLM | fixed with #1: a ready KV-holding bet is not rejected as paused; README wording |
| 34 | medium | vLLM | fixed: on a DP-deferred step a bet that fails only `nonbet_waiting` is held, not rejected |
| 35 | low | vLLM | fixed: `finishes_in_flight` covers sync scheduling with a step in flight (PP) |
| 36 | low | vLLM | documented: one-step effect |
| 37 | medium | SGLang | fixed: bets requeued by `pause_generation(mode=retract)` are dropped |
| 38 | low | SGLang | fixed: the hold rule follows vLLM #10 (a step in which the allowance kept the bet out while a bet prefilled is not counted) |
| 39 | low | vLLM | fixed as a startup warning, not a clamp (a clamp would break `kaggle/overhead_bench.py`'s tagged arm) |
| 40 | low | vLLM, sim | documented: counting evictable blocks as used would refuse nearly every bet; matches vLLM's own free-block count |
| 41 | medium | vLLM, SGLang | vLLM smoke S3 rewritten (fresh prompt per pass, repeats, longest-stall check); the 45 -> 39 ms gap is no longer credited to the allowance. The rewritten S3 ran in the second T4 run. SGLang smoke S3 was ported the same way and has not run on a server |
| 42 | low (test) | SGLang tests | fixed: end-of-step gate inputs tested |
| 43 | low | evidence | vLLM: not applicable now (the notebook saves the full `tests_vllm` output). SGLang: open, no `tests_sglang` run recorded (needs a GPU box with sglang 0.5.22) |
| 44 | medium | sim | fixed: content-shared, reference-counted prefixes (`sys_share` option; default private prompt, as the bench) |
| 45 | low | sim | fixed as an option (`bet_gate="schedule"`); default `submit` keeps the report's policy; `plugin_semantics` gates at schedule time |

Also fixed (not in the audit): replays depended on `PYTHONHASHSEED` (trace.py read order),
up to 1.4% on agent-policy cells.

## Notes on individual findings

- #2 / #10 / #25 in the simulator: modelled, so that `results/prereg_v3` predicts the code
  that ran. Regenerating with `plugin_fixes=False` gives identical predictions in every
  section: on this workload no running bet is ever mid-prefill with early work waiting
  (sub-call prompts are 15-47 tokens).
- #38: the SGLang plugin follows the vLLM decision on #10.
- #2 in SGLang: left open (the fix needs `chunked_req_limit` work on the vendored
  harness). Documented as a difference between the plugins.
- The simulator fixes changed some of the report's numbers (4.5, the RTX 4090 headline,
  4.2's explanation for #45). The report's "Correction (October 20)" section and its notes
  at 4.2, 4.5 and 6 give the corrected values; the figures and the original 4.2 / 4.5 body
  text still show the old model.
