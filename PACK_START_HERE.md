# Start here: demo + evaluation + submission pack

This is a repository handoff, not a live sponsor-integrated application. All data is synthetic.

## Commands (Python 3, standard library only)

```sh
python scripts/render_demo_documents.py
python evals/score.py --self-test
# After your agent produces actual outputs:
python evals/score.py outputs.jsonl
```

Open data/documents/index.html in a browser for printable invoices and contracts. Commit generated HTML if your demo portal needs it. A browser's Print can export PDFs; this package does not claim to include PDF/OCR evaluation.

## Handoff map

- data/demo_dataset.json: normalized fixtures and supporting records.
- data/documents/: generated source documents for ingestion/demo portal.
- evals/inputs.jsonl: 14 independent tasks; feed only these inputs to the agent.
- evals/expected.jsonl: scorer-only references; never put them in agent context.
- evals/score.py: exact structured-output checks.
- submission/devpost.md: editable description with explicit status placeholders.
- submission/scripts-and-qa.md: video, stage outline, and Q&A.
- submission/sources.md: sources and financial-claim boundaries.

## Start with these cases

E01: October increase justified by an effective amendment.
E03: unexplained surcharge requires clarification.
E02: September variation demonstrates effective-date reasoning.
E10: all-period CFO totals and forecast assumptions.

This small fixture replaces the earlier illustrative $20,000/$23,400 narrative. Do not mix those figures with this dataset. Here September is $1,250; October $1,445; next-month baseline $1,325 excluding the unresolved surcharge, or $1,445 if it repeats. The $600 promised credit remains pending.

## Output contract

One JSONL row per task: {"id":"E01","output":{...}}. Match field names/types in the scorer-only reference when implementing your adapter, but do not expose reference values to the model. Dollar values are cents. Use the documented status enums in expected cases. A passed offline assertion does not prove real action enforcement; inspect backend state and portal confirmations separately.

## Submission readiness

Record only implemented integrations and actual results. Replace/remove all placeholders. Keep credentials out of commits. Link a public, playable video under two minutes. Verify the repository's application instructions match what your team actually builds.
