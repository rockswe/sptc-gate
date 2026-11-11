# Call-shape census: CodeAct (2023 models) (static analysis of model-written code)

5427 trajectories with declared tools, 14815 <execute> blocks (240 unparsable), 24663 tool calls.

## decision_making/alfworld: 20840 tool calls, tools ['clean', 'close_receptacle', 'cool', 'goto', 'heat', 'look', 'open_receptacle', 'put', 'take_from', 'toggle', 'use']

| case | share of calls |
|---|---|
| D side effect | 94.3% (19645) |
| B in a loop/helper/comprehension | 3.1% (655) |
| literal or local-only argument, straight-line | 2.1% (435) |
| C under a condition on a tool result | 0.5% (97) |
| C under a condition (not on a tool result) | 0.0% (8) |

| feature (any combination) | share |
|---|---|
| literal | 64.6% |
| in_loop | 36.3% |
| in_helper | 0.0% |
| in_branch | 18.2% |
| cond_on_tool | 15.6% |
| dep_on_tool | 1.8% |
| side_effect | 94.3% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 73, p90 192; share with <10 tokens 68%.

Calls per block: mean 2.94; blocks with >=2 tool calls 88.1%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 1.0% | 2.8% |
| literal-only, if every tool were read-only | 64.6% | 5.8% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 1.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 4.7% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| claude-2 | 4363 | 62% | 6% | 24% | 36% |
| claude-instant-1 | 9015 | 70% | 1% | 13% | 33% |
| gpt-3.5-turbo-0613 | 7462 | 60% | 0% | 21% | 41% |

## reasoning/algebra: 2 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (2) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-3.5-turbo-0613 | 2 | 100% | 0% | 0% | 0% |

## reasoning/counting_and_probability: 4 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (4) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-3.5-turbo-0613 | 4 | 100% | 0% | 0% | 0% |

## reasoning/geometry: 1 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (1) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-3.5-turbo-0613 | 1 | 100% | 0% | 0% | 0% |

## reasoning/hotpotqa: 3804 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 99.9% (3802) |
| straight-line, argument from local values | 0.1% (2) |

| feature (any combination) | share |
|---|---|
| literal | 99.9% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 93%.

Calls per block: mean 1.06; blocks with >=2 tool calls 5.6%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 99.9% | 0.0% |
| literal-only, if every tool were read-only | 99.9% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| claude-2 | 568 | 100% | 0% | 0% | 0% |
| claude-instant-1 | 1206 | 100% | 0% | 0% | 0% |
| gpt-3.5-turbo-0613 | 1913 | 100% | 0% | 0% | 0% |
| gpt-4-0613 | 117 | 100% | 0% | 0% | 0% |

## reasoning/intermediate_algebra: 2 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (2) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-3.5-turbo-0613 | 2 | 100% | 0% | 0% | 0% |

## reasoning/number_theory: 5 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (5) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| gpt-3.5-turbo-0613 | 5 | 100% | 0% | 0% | 0% |

## reasoning/prealgebra: 4 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (4) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| claude-instant-1 | 1 | 100% | 0% | 0% | 0% |
| gpt-3.5-turbo-0613 | 3 | 100% | 0% | 0% | 0% |

## reasoning/precalculus: 1 tool calls, tools ['wikipedia_search']

| case | share of calls |
|---|---|
| literal or local-only argument, straight-line | 100.0% (1) |

| feature (any combination) | share |
|---|---|
| literal | 100.0% |
| in_loop | 0.0% |
| in_helper | 0.0% |
| in_branch | 0.0% |
| cond_on_tool | 0.0% |
| dep_on_tool | 0.0% |
| side_effect | 0.0% |

Tokens the model still streams after a speculable call's closing paren, to the end of its message (stop sequences aside, the overlap window): median 3, p75 3, p90 3; share with <10 tokens 100%.

Calls per block: mean 1.00; blocks with >=2 tool calls 0.0%.

| design | can start early | of those, bets (in a branch arm: may not run) |
|---|---|---|
| literal-only (Pydantic, pi-fabric) | 100.0% | 0.0% |
| literal-only, if every tool were read-only | 100.0% | 0.0% |
| shadow (spec-ptc; reads not after a write, waits on conditions) | 100.0% | ~0% (peeks retract only on mutation/early exit) |
| reads excluded because they follow a write in the block/loop | 0.0% | |

| model | calls | literal | dep_on_tool | in_branch | in_loop |
|---|---|---|---|---|---|
| claude-instant-1 | 1 | 100% | 0% | 0% | 0% |
