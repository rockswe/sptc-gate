# Call-shape census: RLM replies from the Modal H100 campaign (Qwen3-30B-A3B-Instruct-2507 on OOLONG, 32 task runs, November 9, 2026) (static analysis of model-written code)

32 trajectories with declared tools, 313 <execute> blocks (0 unparsable), 56 tool calls.

## rlm-Qwen3-30B-A3B-Instruct-2507: 56 tool calls, tools ['llm_query', 'llm_query_batched', 'rlm_query_batched']

| case | share of calls |
|---|---|
| straight-line, argument from local values | 48.2% (27) |
| B in a loop/helper/comprehension | 33.9% (19) |
| A argument depends on a tool result | 16.1% (9) |
| C under a condition (not on a tool result) | 1.8% (1) |

| feature (any combination) | share |
|---|---|
| literal | 0.0% |
| in_loop | 48.2% |
| in_helper | 1.8% |
| in_branch | 7.1% |
| cond_on_tool | 0.0% |
| dep_on_tool | 16.1% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 43, p75 62, p90 189; share with <10 tokens 5%.

Calls per block: mean 1.04; blocks with >=2 tool calls 3.7%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 0.0% | 0.0% |
| literal-only, if every tool were read-only | 0.0% | nan% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| Qwen3-30B-A3B-Instruct-2507 | 56 | 0% | 16% | 7% | 48% |
