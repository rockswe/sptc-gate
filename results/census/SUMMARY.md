# Call-shape census: how often does real model-written code give speculation something to do?

`experiments/census.py` statically analyzes every code block in
three public corpora of model-written agent code; no code from them was run. Per-call
data is in each `calls.csv`, and the per-source tables are in `census.md`,
`../census_smol/census.md` and `../census_rlm/census.md`.

## Corpora

| Corpus | Models | Trajectories | Code blocks | Tool calls | Tools |
|---|---|---|---|---|---|
| CodeAct (`xingyaoww/code-act`, Apache-2.0) | gpt-3.5-turbo, claude-instant-1, claude-2, gpt-4 (2023) | 5,427 with declared tools | 14,815 (240 unparsable) | 24,663 | HotpotQA: `wikipedia_search` (read-only). ALFWorld: household actions (side effects) plus `look()` |
| smolagents CodeAgent traces (`smolagents/codeagent-traces`, one of two shards; no license tag, so aggregates only) | DeepSeek-V3-0324, Qwen3-235B-A22B (2025) | 16,483 | 39,171 (127 unparsable) | 39,883 | `web_search`, `visit_webpage` (read-only); `final_answer` (ends the run) |
| RLM call traces (`reasoning-degeneration-dev/...rlm_call_traces`, MIT) | gpt-5-nano | 3 tasks, 17 iterations | 13 | 13 | `llm_query` and family. Tiny: shown for its *shape* only |

## Results

**Speculable** calls are reads (read-only tools) that do not come after a side-effecting
call earlier in the same block, or anywhere in an enclosing loop that has one. Starting
such a read early would see the world before the write. Shares below are of speculable
calls.

Columns:
- "≥2 in block": among blocks with at least one speculable call, the share with two or
  more.
- "Tokens after": tokens the model still streams after the call's closing
  parenthesis, measured to the end of its message (characters ÷ 4). Stop sequences can
  shorten this. It is the overlap window.

| source | calls | side effects | reads after a write | literal | in loop | in branch | dep on tool | cond on tool | ≥2 in block | literal launches that are bets | tokens after (median / p90) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CodeAct ALFWorld | 20,840 | 94.3% | 4.7% | 100% | 0% | 2.8% | 0% | 2.8% | 4.5% | 2.8% | 3 / 192 |
| CodeAct HotpotQA | 3,804 | 0% | 0% | 99.9% | 0% | 0% | 0% | 0% | 5.6% | 0% | 3 / 3 |
| smolagents Frames | 17,554 | 29.5% | 0% | 94.1% | 1.7% | 0.3% | 1.1% | 0.3% | 13.6% | 0.2% | 9 / 84 |
| smolagents SimpleQA | 16,393 | 37.7% | 0% | 94.6% | 0.3% | 0% | 0% | 0% | 1.7% | 0% | 7 / 10 |
| smolagents SciBench | 2,815 | 95.7% | 0% | 92.6% | 4.1% | 0% | 0% | 0% | 20.2% (18/89) | 0% | 8 / 89 |
| RLM, gpt-5-nano (13 calls) | 13 | 0% | 0% | 15% | 8% | 23% | **46%** | 15% | **71% (5/7)** | 50% (1 of 2) | **86 / 221** |

Notes on the side-effect columns:
- ALFWorld's speculable calls are `look()` calls that do not follow an action.
- smolagents' side-effecting calls are `final_answer`.
- smolagents MATH (3,121 calls, 99.9% `final_answer`) is omitted.

## What this says about speculation

1. Wasted speculation is rare in the agent corpora.
   - Among speculable reads, 0–0.3% sit in a branch arm on web research and math. So a
     literal-only speculator (Pydantic, pi-fabric) launches bets on 0–0.2% of its launches.
   - ALFWorld's `look()` is the exception at 2.8%.
   - spec-ptc waits on conditions and launches no branch bets. Its only waste is retracted
     peeks, on mutation or early exit.

   The simulator's "one bad guess per real call" stress setting is about 35× (ALFWorld)
   to more than 100× (web research) above these rates. Waste-driven clogging (report §4.2)
   is a risk for *prediction-based* speculation, not for code-mode speculation on these
   workloads.
2. There is little to overlap in these agents. In the 2025 traces the tool call is
   close to the end of the message: a median of 7–9 tokens remain, about 0.1–0.2 s at
   20 ms/token. Only 2–14% of web-research blocks (and 20% of SciBench's few) contain two
   or more speculable calls that could run in parallel.
3. RLM code looks different, but the sample is tiny. In 13 sub-calls from gpt-5-nano:
   - 71% of blocks hold two or more sub-calls;
   - 46% of calls depend on an earlier result;
   - a median of 86 tokens follow each call.

   That is the fan-out-with-dependencies shape where speculation should pay off, and where
   spec-ptc's dependency handling (case A) matters. A real RLM corpus is the missing piece.
4. Side effects block more than waste does. In ALFWorld:
   - 94% of tool calls change the world;
   - another 4.7% are reads that follow a write in the same block or loop;
   - only 1% are safely speculable.

   The blocker there is case D, not load.
5. Dependent calls (case A) are rare in the agent corpora: 0–1.1% of speculable calls.
   Models usually write arguments out as literals and act on results in the next turn.
   Where results do steer code within a block, it is mostly through conditions: ALFWorld
   `look()` calls under a condition on an earlier `look()`, and Frames' 0.3%.

## Classifier accuracy

**Method.** Two independent, blind LLM labelers, with a third to settle
disagreements, labeled six features of stratified samples (10 calls per case per corpus).
Two limitations:
- Not fully blind. Item keys followed the case-grouped sampling order before shuffling,
  so in principle they leaked group structure.
- Not validated: the "read after a write" feature was added after both rounds.

**Round 1** (112 calls, `handcheck.md`):
- The labelers agreed on everything.
- The classifier erred on 2 items, both false "depends on a tool result".
- Fixed. A regression introduced by the first fix was caught and fixed too.

**Round 2** (113 calls with a fresh seed; 92 not in round 1; `handcheck_v2.md`):
- The classifier erred on **2 items: 1.8% of the stratified sample**, which is **2.7%
  when weighted by how common each case is.**
- Causes: a model-defined helper that calls `web_search`, which the analysis did not
  follow across functions, and `-1` not counted as a literal.
- Both were fixed afterwards. These rates describe the version that was tested.

**Caveat.** The labelers are models given the classifier's own definitions. This checks
that the analysis implements those definitions. It does not check that the definitions
capture everything a speculation engine needs, such as aliasing or which branch actually
ran.

## Limits

- Tasks. CodeAct is 2023 models on short tasks. smolagents is two 2025 models on
  question answering and math, and only one of its two shards was used.
- RLM. The RLM sample is 13 calls from one model.
- Method. Static analysis only. "Bets" counts calls in branch arms, not arms that were
  actually skipped.
