# Call-shape census: smolagents CodeAgent traces, one shard (2025 models) (static analysis of model-written code)

16483 trajectories with declared tools, 39171 <execute> blocks (127 unparsable), 39883 tool calls.

## Frames: 17554 tool calls, tools ['final_answer', 'visit_webpage', 'web_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 66.2% (11615) |
| D side effect | 29.5% (5183) |
| straight-line, argument from local values | 2.3% (396) |
| B in a loop/helper/comprehension | 1.2% (202) |
| A argument depends on a tool result | 0.7% (121) |
| C under a condition on a tool result | 0.2% (36) |
| C under a condition (not on a tool result) | 0.0% (1) |

| feature (any combination) | share |
|---|---|
| literal | 87.5% |
| in_loop | 1.2% |
| in_helper | 0.1% |
| in_branch | 0.5% |
| cond_on_tool | 0.4% |
| dep_on_tool | 2.0% |
| side_effect | 29.5% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 9, p75 26, p90 84; share with <10 tokens 53%.

Calls per block: mean 1.14; blocks with >=2 tool calls 9.8%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 66.3% | 0.2% |
| literal-only, if every tool were read-only | 87.5% | 0.4% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 70.5% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| DeepSeek-V3-0324 | 6379 | 88% | 1% | 0% | 2% |
| Qwen3-235B-A22B | 11175 | 87% | 2% | 1% | 1% |

## MATH: 3121 tool calls, tools ['final_answer', 'visit_webpage', 'web_search']

| case | share of calls |
|---|---|
| D side effect | 99.9% (3117) |
| literal or local-only argument, straight-line | 0.1% (4) |

| feature (any combination) | share |
|---|---|
| literal | 20.5% |
| in_loop | 1.6% |
| in_helper | 0.2% |
| in_branch | 2.6% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 99.9% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 7, p75 15, p90 30; share with <10 tokens 75%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.5%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 0.1% | 0.0% |
| literal-only, if every tool were read-only | 20.5% | 1.4% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 0.1% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| DeepSeek-V3-0324 | 2348 | 19% | 0% | 3% | 2% |
| Qwen3-235B-A22B | 773 | 27% | 0% | 1% | 1% |

## SciBench: 2815 tool calls, tools ['final_answer', 'visit_webpage', 'web_search']

| case | share of calls |
|---|---|
| D side effect | 95.7% (2693) |
| literal or local-only argument, straight-line | 4.0% (113) |
| B in a loop/helper/comprehension | 0.2% (5) |
| straight-line, argument from local values | 0.1% (4) |

| feature (any combination) | share |
|---|---|
| literal | 22.9% |
| in_loop | 0.2% |
| in_helper | 0.0% |
| in_branch | 0.2% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.1% |
| side_effect | 95.7% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 8, p75 40, p90 89; share with <10 tokens 58%.

Calls per block: mean 1.01; blocks with >=2 tool calls 0.9%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 4.0% | 0.0% |
| literal-only, if every tool were read-only | 22.9% | 0.2% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 4.3% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| DeepSeek-V3-0324 | 2288 | 24% | 0% | 0% | 0% |
| Qwen3-235B-A22B | 527 | 18% | 0% | 0% | 0% |

## SimpleQA: 16393 tool calls, tools ['final_answer', 'visit_webpage', 'web_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 58.9% (9659) |
| D side effect | 37.7% (6177) |
| straight-line, argument from local values | 3.2% (518) |
| B in a loop/helper/comprehension | 0.2% (31) |
| C under a condition on a tool result | 0.0% (4) |
| A argument depends on a tool result | 0.0% (3) |
| C under a condition (not on a tool result) | 0.0% (1) |

| feature (any combination) | share |
|---|---|
| literal | 94.6% |
| in_loop | 0.2% |
| in_helper | 0.0% |
| in_branch | 0.2% |
| cond_on_tool | 0.1% |
| dep_on_tool | 0.4% |
| side_effect | 37.7% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 7, p75 8, p90 10; share with <10 tokens 90%.

Calls per block: mean 1.01; blocks with >=2 tool calls 1.3%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 58.9% | 0.0% |
| literal-only, if every tool were read-only | 94.6% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 62.3% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| DeepSeek-V3-0324 | 9128 | 93% | 1% | 0% | 0% |
| Qwen3-235B-A22B | 7265 | 96% | 0% | 0% | 0% |
