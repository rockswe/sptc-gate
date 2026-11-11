# Census classifier vs blind labels (112 sampled calls, 2 LLM labelers + a third as adjudicator)

The labelers are models given the classifier's own definitions (`SUMMARY.md`, Classifier
accuracy).

Items where the two labelers disagreed on any feature: 0/112.

| feature | labeler agreement | classifier errors vs consensus |
|---|---|---|
| literal | 100.0% | 0/112 (0.0%) |
| in_loop | 100.0% | 0/112 (0.0%) |
| in_helper | 100.0% | 0/112 (0.0%) |
| in_branch | 100.0% | 0/112 (0.0%) |
| cond_on_tool | 100.0% | 0/112 (0.0%) |
| dep_on_tool | 100.0% | 2/112 (1.8%) |

Items with at least one classifier error: 2/112 (1.8%).

Classifier errors (item, feature, classifier -> consensus, labeler note):

- smolagents:58 [smolagents, A argument depends on a tool result] dep_on_tool: True -> False. f-string over a state from a literal list
- smolagents:75 [smolagents, C under a condition on a tool result] dep_on_tool: True -> False. else arm of 'if temp:', where temp comes from re.search on web_search results; the f-string uses only island, which comes from a literal list
