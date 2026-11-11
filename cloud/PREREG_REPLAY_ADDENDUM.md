# Addendum: the fork after two fixes, on the engine (fixed before the follow-up run)

Written 2026-11-10, after the registered replay (`20261110-042602-replay`) and before its
follow-up. `replay_campaign.py` records this file's sha256 in `campaign.jsonl` before the
first unit. Never edit it after a run. `PREREG_REPLAY.md` is unchanged.

*Published copy: wording about the working process was removed after the runs, so this
text no longer hashes to the sha256 the campaign recorded. No prediction, bound or rule
was changed ([README](../README.md#design-and-testing)).*

## Why a follow-up

The registered run was exact in all 10 units, and 8 of its 11 checks held. Three did not:

- P1 and P2: `wide` launched 1,042 calls twice in one of its two units, and evicted
  them. In that unit one session's batch of 3,182 prompts took the scout 6.6 s to launch
  (456 launches a second: the process was busy with 128 calls in flight per session). The
  shadow waited 3 s for the scout, then ran the statement itself. It adopted the 1,977
  calls launched by then and launched the rest, and the scout launched the rest too. The
  turn's dispatch cap (4,096) then ran out, and the real run made 128 calls itself.
- P9: `nospec`'s two units differ by 5.2% (the bar was 5%). The first unit of the
  launch had 25 s of root stalls. The other three arms repeat within 1.0 to 1.9%.

In the same run spec-ptc as shipped lost 422 calls in one of its two units: its runaway
guard cut the shadow in a statement that launches 3,182 calls. The guard budgets a
statement's own computing (2 s), and it counted the launching.

## What changed in the fork since the registered run

Working tree of `spec-ptc-sptc-hints`; the hash is in `campaign.jsonl`.

1. The shadow lets the scout finish a statement's launches before it runs the
   statement (up to 60 s; it was 3 s).
2. Launching is not a statement's computing. The scout's and the shadow's runaway
   guards do not count the time spent launching or adopting, and do not cut a launch in
   two.
3. A batch launch that is interrupted still runs what it announced.

Each has a test that fails on the code of the registered run (`tests/test_scout.py`). A
dry run with every launch slowed to 2 ms, the rate measured above, reproduces the defect
with the old handoff (1,318 calls sent twice) and not with the new one (none).

## What is run

One H100 launch, same engine flags, corpus (8 sessions) and settings as the registered
run. Units in this order: `wide`, `wide`, `stream`, `scout`, `wide-threads`. `stream` is
the reference for this launch's host: hosts differ by up to 60% in token speed.

## Predictions

Definitions as in `PREREG_REPLAY.md`. The registered run's value is next to each.

| | prediction | registered run | counts against it |
|---|---|---|---|
| A1 | Every unit exact. In the fork's arms no call is launched twice, none is evicted, none is left to the real run | `wide` unit 1: 1,042 twice, 128 left | any of the three |
| A2 | The batch of 3,182 (`trec132k-17000241` turn 12): `wide` at most 0.45 of `stream` | 0.38 (0.41 in the unit with the defect) | above 0.45 |
| A3 | The cap: `wide` recovers at least 50% of `stream`'s seconds | 63% | below 50% |
| A4 | Serial launches: `wide` recovers at least 85% | 96% | below 85% |
| A5 | Sum of session times: `wide` at most 0.75 of `stream`. Sum of root stream seconds within 10% of `stream`'s | 0.645, 0.986 | either outside |
| A6 | `wide-threads` within 25% of `wide` in summed session time | 0.987 | outside |
| A7 | `wide`'s two units differ by less than 5% in summed session time | 1.9% | 5% or more |
| A8 | The runaway guard cuts no shadow statement in the fork's arms | 1 per `scout` unit | any cut |

Not a prediction, but watched: `scout` should be where it was (0.72 of `stream` in summed
session time, 87% of the serial-launch seconds).

## What this run cannot show

The defect needs a slow launch, and a slow launch needs a busy process: it showed in one
of two `wide` units. Three clean units here would not prove the fix. The tests and the
slowed dry run do that. This run checks that the fixed fork behaves on the engine as the
registered one did where the defect did not strike, before any live run uses it.
