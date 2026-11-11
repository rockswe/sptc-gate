# Census classifier vs blind labels (113 sampled calls, 2 LLM labelers + a third as adjudicator)

The labelers are models given the classifier's own definitions (`SUMMARY.md`, Classifier
accuracy).

Items where the two labelers disagreed on any feature: 0/113.

| feature | labeler agreement | classifier errors vs consensus |
|---|---|---|
| literal | 100.0% | 1/113 (0.9%) |
| in_loop | 100.0% | 0/113 (0.0%) |
| in_helper | 100.0% | 0/113 (0.0%) |
| in_branch | 100.0% | 0/113 (0.0%) |
| cond_on_tool | 100.0% | 1/113 (0.9%) |
| dep_on_tool | 100.0% | 1/113 (0.9%) |

Items with at least one classifier error: 2/113 (1.8%, stratified sample); population-weighted by case frequency: 2.66%.

Classifier errors (item, feature, classifier -> consensus, labeler note):

- smolagents:72 [smolagents, C under a condition (not on a tool result)] cond_on_tool: False -> True. The else-arm test reads valid_populations, which comes from get_population() and so from web_search. The f-string argument uses most_populous_county, a conditional expression whose tests read the tool
- smolagents:72 [smolagents, C under a condition (not on a tool result)] dep_on_tool: False -> True. The else-arm test reads valid_populations, which comes from get_population() and so from web_search. The f-string argument uses most_populous_county, a conditional expression whose tests read the tool
- smolagents:90 [smolagents, D side effect] literal: False -> True. Argument -1 is a negative number literal (in the AST it is UnaryOp USub on Constant 1).
