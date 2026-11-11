# Call-shape census: RLM call traces (gpt-5-nano on CodeQA; one small public run) (static analysis of model-written code)

3 trajectories with declared tools, 13 <execute> blocks (0 unparsable), 13 tool calls.

## rlm-gpt-5-nano: 13 tool calls, tools ['llm_query', 'llm_query_batched', 'rlm_query']

| case | share of calls |
|---|---|
| A argument depends on a tool result | 38.5% (5) |
| straight-line, argument from local values | 30.8% (4) |
| C under a condition on a tool result | 15.4% (2) |
| C under a condition (not on a tool result) | 7.7% (1) |
| literal or local-only argument, straight-line | 7.7% (1) |

| feature (any combination) | share |
|---|---|
| literal | 15.4% |
| in_loop | 7.7% |
| in_helper | 0.0% |
| in_branch | 23.1% |
| cond_on_tool | 15.4% |
| dep_on_tool | 46.2% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 86, p75 144, p90 221; share with <10 tokens 0%.

Calls per block: mean 1.86; blocks with >=2 tool calls 71.4%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 15.4% | 50.0% |
| literal-only, if every tool were read-only | 15.4% | 50.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-5-nano | 13 | 15% | 46% | 23% | 8% |
