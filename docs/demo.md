# Demo specification

Status: proposed scenarios, not completed test results. All records are synthetic. Currency: USD.

## Scenario A: explained increase

Original contract: service DEMO-001 costs $450/month. Approved amendment: $525/month effective October 1, 2026. October invoice: $525.

1. Anchor retrieves the invoice from the demo portal.
2. Claude on Bedrock extracts fields with source references.
3. SurrealDB retrieves both terms and their effective dates.
4. Daytona calculates the $75 increase and checks the applicable period.
5. The frontend displays the amendment supporting the increase.
6. After required policy checks, add an instruction to the visibly simulated payment queue.

Variation: a September $525 invoice must not be justified by the October amendment. Avoid mid-period proration in this demo.

## Scenario B: unexplained charge

A separate account has a new $120 surcharge without an explanation in available records.

1. Retrieve and parse the invoice.
2. Compare it with prior charges and applicable records.
3. Mark Needs clarification, not Confirmed overcharge.
4. Present evidence and request human approval for a specific inquiry.
5. Generate an ElevenLabs voice message; label it generated, not delivered.
6. Anchor submits the approved inquiry in the demo portal.
7. Persist the confirmation and mark Awaiting vendor response.
8. Keep $120 as billed exposure under review; do not record savings.

## Acceptance cases

| Case | Expected result |
| --- | --- |
| October $525 with October amendment | Supported $75 increase |
| September $525 with October amendment | Needs review |
| Unexplained $120 surcharge | Needs clarification |
| Duplicate invoice | No second payment instruction |
| Promised $600 credit with no posting evidence | Pending credit, not realized savings |
| Inquiry without approval | Submission blocked |

Record actual pass/fail results, elapsed time, and trace references. Test completed actions by inspecting persisted state or portal confirmations, not only the agent's text.

## CFO view

Display recurring changes from their effective dates, one-time charges separately, unresolved billed exposure, applied credits, pending credits, and source links. Forecasts must expose assumptions and missing information.

## Recording outline (under two minutes)

- 0:00–0:15: User, problem, and one sourced impact statistic.
- 0:15–0:45: Explained increase and dated evidence.
- 0:45–1:20: Unexplained charge, approval, and inquiry confirmation.
- 1:20–1:40: CFO summary.
- 1:40–1:55: Actual evaluation results and integration overview.

Clearly identify any prerecorded sequence, synthetic portal, simulated payment, and unimplemented feature.
