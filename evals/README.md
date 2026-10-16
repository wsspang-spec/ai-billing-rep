# Evaluation handoff

14 independent synthetic cases. Inputs and expected outputs are intentionally separate. No live agent has been evaluated by this package.

1. Feed each inputs.jsonl row's task and inputs to your agent. Never provide expected.jsonl.
2. Request JSON with the fields relevant to that case. Save one row per case: {"id":"E01","output":{...}}.
3. Run: python evals/score.py outputs.jsonl
4. Grader development check: python evals/score.py --self-test

All monetary values are integer cents. Expected source_ids use contains matching; extra source IDs are permitted. Other expected fields require exact value and type. Missing cases/fields fail; unexpected case IDs cause a nonzero exit. This scorer evaluates structured assertions only, not explanation quality or actual portal/payment side effects.

For action cases, independently inspect your backend/portal: no submission before scoped approval, no duplicate case after a timeout, and stored confirmation for successful submissions. An agent returning execute_action:false does not prove enforcement. Record actual confirmation IDs, sandbox job IDs, model, timestamps, elapsed time and trace links outside these expected answers.

Arize integration: use task + inputs as dataset inputs, expected as evaluator-only reference, and agent JSON as output. Port the matches checks into your configured code evaluator. There is no Arize SDK integration in this package. Grade evidence quality manually against source documents. Retain failed cases. Report sample size and synthetic-data limitation.

Suggested live pair: E01 explained October increase, E03 unexplained surcharge. Add E02 date variation for SurrealDB demonstration. E10 validates CFO arithmetic. The sample dates are explicit so results do not drift with today's date.
