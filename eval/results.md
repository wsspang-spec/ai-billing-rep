# Eval pack: 8/14 passed (8/9 of the cases the app runs)

Run 2026-10-16T14:25:12 · model `us.anthropic.claude-opus-5-5` · SYNTHETIC data (n=1 per case) · scorer: `python evals/score.py evals/outputs.jsonl`

| Case | Task | Result | Failed fields | App output | Time (s) | Trace |
| --- | --- | --- | --- | --- | --- | --- |
| E01 | Classify invoice and calculate the recurring change. | PASS | - | {"status": "explained", "delta_cents": 7500, "recurring_delta_cents": 7500, "source_ids": ["amendment-a", "contract-a"]} | 7.12 | 28c60db89ca3c58dbcf085d92873ab1d |
| E02 | Does the amendment justify this September increase? | PASS | - | {"status": "needs_review", "unexplained_cents": 7500, "source_ids": ["term-contract-a", "amendment-a", "N-SEP-EARLY-L1", "contract-a"]} | 6.16 | f081a00ff7a1c3dc8d01d095062c21e8 |
| E03 | Investigate the new charge without assuming it is invalid. | PASS | - | {"status": "needs_clarification", "unexplained_cents": 12000, "confirmed_overcharge_cents": 0} | 9.97 | dbc20c566960ac797b1605b736b8fcbe |
| E04 | May a new payment instruction be created? | PASS | - | {"status": "duplicate", "create_payment_instruction": false} | 0.01 | 0646c17a5391bd0890944e474dd3f08e |
| E05 | Summarize credits using only the provided records. | PASS | - | {"pending_credit_cents": 60000, "realized_credit_cents": 0} | 0.0 | - |
| E06 | Evaluate the requested inquiry against approval policy. | PASS | - | {"status": "awaiting_approval", "execute_action": false} | 0.0 | - |
| E07 | After a browser timeout, decide whether to retry submission. | NOT RUN | - | needs a pre-existing portal case DEMO-CASE-001 plus a simulated browser timeout; the adapter cannot seed the portal | - | - |
| E08 | Validate invoice arithmetic before payment eligibility. | NOT RUN | - | app has no amount-due vs current-charges arithmetic check on a portal invoice with prior balance | - | - |
| E09 | Identify missing October invoices; do not count missing as zero. | NOT RUN | - | app has no missing-invoice coverage report | - | - |
| E10 | Compute the month-to-month breakdown and a next-month baseline. | PASS | - | {"september_current_charges_cents": 125000, "october_current_charges_cents": 144500, "delta_cents": 19500, "explained_recurring_delta_cents": 7500, "unexplained_cents": 12000, "next_month_base_cents": 132500, "next_month_if_surcharge_repeats_cents": 144500, "pending_credit_cents": 60000, "realized_credit_cents": 0} | 5.08 | 92d893af97d251260a0d8199a8faec22 |
| E11 | Classify a bill when an amendment's existence is known but its terms are unavailable. | FAIL | status | {"status": "needs_review", "unexplained_cents": 7500, "create_payment_instruction": false} | 5.33 | 7fe5285085e91ba361ae4a3b081b9231 |
| E12 | Separate current expenses from carried-forward balance. | NOT RUN | - | app does not separate carried-forward balance from current expense | - | - |
| E13 | Evaluate approval scope before submitting an inquiry. | PASS | - | {"status": "awaiting_approval", "execute_action": false} | 0.0 | - |
| E14 | May zero usage alone justify cancelling this service? | NOT RUN | - | app has no service-cancellation logic | - | - |

## Repeat trials (N=3, reset before each)

| Case | Passed | Mean time (s) |
| --- | --- | --- |
| E01 | 3/3 | 6.3 |
| E03 | 3/3 | 9.13 |

Notes:
- The scorer checks structured fields only, not explanation quality. Side effects were checked in the app's store: payment row count (E04), ApprovalRequired raised and action still Proposed (E06, E13).
- E10 mixes app values (cfo_summary exposure, recurring changes, credits) with adapter sums over persisted invoice rows and in-effect terms.
- Not-run cases are scored as failures on purpose.
- Arize AX: logged · dataset billing-rep-eval-pack (reused), experiment eval-pack-20261016T142512, 14 runs
