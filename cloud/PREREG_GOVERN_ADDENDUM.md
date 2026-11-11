# Addendum: after a first launch of run 1 that I stopped (fixed before both runs)

Written 2026-11-11, after the launch `20261111-083951-small` and before any measured unit
of a governed arm has run. `replay_campaign.py` records this file's sha256 in
`campaign.jsonl` next to `PREREG_GOVERN.md`'s, before the first unit of each run. Never
edit it after a run. `PREREG_GOVERN.md` and both design files are unchanged (sha256
`8d19b0ca…`, `a61d7647…`, `237408ea…`).

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)).*

## What happened

Run 1 was launched as registered: a T4 with 16 places, the fork at patch 5 (tree
`545d9505…`). It ran the thrown-away `auto` unit on four sessions (276 s, exact) and the
`stream` unit (490 s, exact). `wide` had begun when I stopped the launch, 16 minutes in.

**Two reasons, both mine.**

1. The budget. A unit takes 490 s on this engine. The dry run had said 243 s, and
   the launch was allowed 26 minutes: it would have stopped before `auto`, the arm the
   run is for.
2. A defect in the governor, which the thrown-away unit showed (below).

**What I have seen of it:** the thrown-away unit's events, and the `stream` unit. No
measured unit of `wide` or `auto` exists.

## What the thrown-away unit showed

- The client reads what it needs from a real vLLM 0.32. Requests running and waiting,
  the KV cache's use, its size from `cache_config_info` (89,072 tokens), and the time
  between tokens. The KV pool was live: 66,000 to 80,000 tokens free for speculation.
- The governor grew a window on numbers that had not changed. 47 s into the unit a
  cold engine spent two seconds in one step: its token count stood still, with 4
  requests running and none waiting. Eight samples in a row said so, and one session's
  window went from 16 to 256 in 1.5 s on them. Then 240 requests were waiting, and it
  took seven cuts and 5 s to bring the window back to 20.
- The gap in the rule: "one step per new sample" took a sample for new when the
  client had read again. The engine's numbers only change when the engine steps.
- The unit's root TTFT (14 s at the 90th percentile) is the cold engine's: every session's
  first turn waited 14 s. That is why the unit is thrown away.

## What `stream` showed: the shipped client on 16 places

| | measured | the dry run's fake engine |
|---|---|---|
| session time, the 8 sessions | 2,625 s | 1,209 s |
| root streams | 2,149 s | 1,024 s |
| root token gap, median / 99th | 86 / 452 ms | 44 / 96 ms |
| root TTFT, median / 90th / 99th / longest | 1.27 / 2.47 / 5.36 / 6.20 s | 0.16 / 0.67 / 0.96 / 1.15 s |
| sub-call, median / 90th | 758 / 2,290 ms | 318 / 872 ms |
| the engine's largest queue; share of samples with a request waiting | 38; 0.48 | 39; 0.42 |

- The real engine with its places full is about half as fast as the fake one. A token
  takes 86 ms where the fake engine has 44, and prefill is slow: 16 prompts of 3,400
  tokens took 28 s in the warm-up.
- The queue is as the fake engine had it: 38 requests at most, one waiting about half
  the time. As shipped, 16 calls in flight are already more than this engine has places
  for.

## What changes

1. One rule is added to the governor (patch 6, fork `11b6d39`, tree `a61ef323…`):
   **no growth while the engine is not stepping.** If the engine has requests in its
   batch and has written no token since the last sample, its numbers say nothing about
   what was sent meanwhile, and the window stays where it is. One test, from the
   measured case. Nothing else in the client changes.
2. Run 1's budget: `--max-minutes 36`, hard timeout 40 minutes, 500 s assumed per
   unit.
3. Run 2's budget: `--max-minutes 53`, hard timeout 60 minutes. The
   budget stop still costs `wide-open` first.
4. Nothing else. Sessions, units, their order, the checks and their bounds are as
   registered. Both runs use the fork at patch 6.

## Dry runs with the new rule

The fake engine steps every 40 ms, so the rule has little to act on there.

| | before | with the rule |
|---|---|---|
| small engine: `auto` over `stream`, session time | 1.018 | 1.022 |
| small engine: root TTFT of `auto`, 90th percentile | 0.44 s | 0.45 s |
| small engine: cuts; widest window | 63; 42 | 81; 42 |
| H100: `auto` over `wide`, session time over the 10 (F1) | 1.002 | 1.004 |
| H100: `auto`'s root streams over `stream`'s, the 10 (F2) | 1.038 | 1.039 |
| H100: the long turn in `auto` | 376 s | 378 s |
| H100: the loop that tests each result, `auto-past` | 14.3 s | 13.1 s |
| H100: `auto-past` over `stream`, session time over the 11 | 0.821 | 0.821 |

Every check of both design files still holds on them.

## The predictions

S1 to S13, F1, F2 and H1 to H19 stand as registered, with their bounds. What I expect
differently after seeing the real engine, without changing a check:

- S4 (`wide`'s root TTFT at the 90th percentile is at least 2.5 times `stream`'s):
  less sure than the dry run made it. `stream`'s own is 2.5 s on the real engine, so
  `wide` has to reach 6.2 s. A queue of 110 sub-calls at 0.76 s each through about ten
  free places is about that. I give it 2 chances in 3.
- S9 (`auto` at most 1.04 of `stream` in session time): about 2 in 3. The real engine
  is slower than the fake one in ways the dry run did not have.
- S12 (no window of `auto` reaches 128): with the new rule I expect it to hold in a
  measured unit. Without the rule a cold engine would have failed it.
- The absolute numbers of run 1 will be about twice the dry run's. The checks are
  ratios, and counts.
