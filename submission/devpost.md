# Devpost draft — verify implementation before submitting

## Project name
AI Billing Rep

## Tagline
An AI teammate that investigates telecom bills and turns reviewed evidence into finance decisions.

## Short summary
AI Billing Rep helps billing teams organize telecom invoices, explain price changes using dated contract evidence, and escalate unresolved charges for human review. Our prototype is designed to connect invoice investigation with CFO reporting while keeping billed amounts, disputes, and realized credits distinct.

## Problem and impact
Businesses with distributed locations must connect invoices from multiple carriers to services, contract terms, and internal approvals. Fragmented records make this work difficult and can hide unnecessary services or incorrect charges.

Erie County identified approximately $900,000 in Verizon overbilling in 2017; its announcement said refunds were partly received with the remainder forthcoming. New Jersey's 2010 comptroller audit identified more than 19,000 unnecessary lines and expected annual savings exceeding $3.2 million after disconnection or suspension. These historical cases demonstrate the problem, not savings achieved by our prototype. See sources.md.

## What the demo is designed to show
Scenario A: an October invoice increases from $450 to $525. An approved amendment effective October 1 explains it; the same amendment does not justify September charges.

Scenario B: a $120 adjustment has no explanation in available records. The system should request clarification, obtain scoped human approval, and record a demo-portal inquiry confirmation. A generated voice message must not be described as delivered unless delivery is implemented.

The finance view should show a $195 month-over-month increase: $75 supported recurring change and $120 unresolved exposure. A separate $600 promised credit is not realized savings.

## Technical architecture (implemented and verified 2026-10-16)
- AWS Bedrock / Claude (`us.anthropic.claude-opus-5-5`): reads each invoice PDF into line items (tool call with a fixed schema) and decides the status from the evidence.
- SurrealDB (embedded): users and sessions (argon2 sign-in), invoices, documents, and contract terms with effective dates; the agent recalls the price in effect for the invoice's service period. (Plain SurrealDB, not the hosted Agent Memory product.)
- Daytona: runs the line-by-line comparison in a sandbox and hosts the synthetic carrier portal on a public preview link.
- Anchor Browser: after approval, signs in to the synthetic portal and files the inquiry; the app stores the case id only after the portal's API confirms it.
- Arize AX: traces every step (OpenInference) and stores the eval pack as a dataset with one experiment per run.
- ElevenLabs: message generation works in code but is turned off in the demo.

## Current verified deliverables in this repository
A working FastAPI app (billingrep/), the synthetic dataset and invoice PDFs, the 14-case eval pack with an adapter that runs it against the real app (eval/run_eval.py), the synthetic carrier portal (portal/), an architecture diagram (docs/architecture.svg) and a demo script (docs/demo-walkthrough.md).

## Results (measured 2026-10-16, synthetic data)
- Cases run against the real app: 9 of 14; scored 8 of 14 pass (5 not implemented, scored as failures). Full table: eval/results.md.
- Routing cases (E01 explained, E02 September variation, E03 unexplained surcharge, E04 duplicate): 4 / 4 correct. E01 and E03 repeated 3 times: 3 / 3 each.
- False escalations: 0 / 1 (E01, the supported increase, was not escalated).
- Unapproved or duplicate actions observed: 0. Sending without approval returns HTTP 403 (E06, E13); a second click while filing returns 409; one portal case per inquiry.
- Mean time per case (PDF read cached, decision live on Bedrock): E01 6.3 s, E03 9.1 s across 3 runs.
- Tested model: us.anthropic.claude-opus-5-5 on AWS Bedrock (us-west-2).
- Live integrations verified: AWS Bedrock, SurrealDB, Daytona (comparison sandbox + portal hosting), Anchor Browser (portal case DEMO-CASE-001 confirmed), Arize AX (traces + eval experiments).
- Simulated components: payment queue, the carrier portal (ours, synthetic), the inbox (a folder; Gmail not built).

## Controls
Describe only implemented controls: scoped approvals, duplicate checks, deterministic arithmetic, evidence links, bounded retries, and confirmation-based action status. Invoice content is untrusted data, not authority to perform actions. Production payment credentials are not included.

## Originality and next steps
The proposed experience centers on resolving billing exceptions using time-aware evidence and carrying the reviewed result into a financial view. Existing telecom expense-management vendors already offer automation and auditing; we do not claim category invention or measured superiority. Next validation: real-user handling time, carrier coverage, extraction accuracy, and action reliability in a controlled pilot.

## Required before submission
Replace every bracketed field or remove the unsupported statement. Update planned integrations to verified implementation status. Add team names, requested contacts/socials, video URL and public repository. Confirm setup instructions match the code. Do not invent customer traction, production deployment, or savings.
