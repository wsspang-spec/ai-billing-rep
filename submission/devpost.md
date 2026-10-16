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

## Technical architecture — planned; update from actual implementation
- AWS Bedrock / Claude: invoice interpretation and investigation decisions.
- SurrealDB Agent Memory: sourced original terms and amendments with effective dates.
- Daytona: agent execution and calculated comparisons.
- Anchor Browser: invoice retrieval and approved inquiry submission in a synthetic portal.
- ElevenLabs: vendor clarification audio generated from reviewed evidence.
- Arize AX: execution traces and evaluation results.

## Current verified deliverables in this repository
Synthetic JSON dataset, printable HTML document generator, 14 evaluation cases with separate expected answers, an offline scorer, and submission materials. Grader self-tests are not agent accuracy results. No live sponsor integration is established by this package.

## Results — fill only with measured evidence
- Cases run: [N] of 14
- Correctly routed: [N] / [N]
- False escalations: [N] / [eligible cases]
- Unapproved or duplicate actions observed: [N]
- Median runtime across [N] runs: [seconds]
- Tested model and version: [value]
- Live integrations verified: [list]
- Simulated components: [list]

## Controls
Describe only implemented controls: scoped approvals, duplicate checks, deterministic arithmetic, evidence links, bounded retries, and confirmation-based action status. Invoice content is untrusted data, not authority to perform actions. Production payment credentials are not included.

## Originality and next steps
The proposed experience centers on resolving billing exceptions using time-aware evidence and carrying the reviewed result into a financial view. Existing telecom expense-management vendors already offer automation and auditing; we do not claim category invention or measured superiority. Next validation: real-user handling time, carrier coverage, extraction accuracy, and action reliability in a controlled pilot.

## Required before submission
Replace every bracketed field or remove the unsupported statement. Update planned integrations to verified implementation status. Add team names, requested contacts/socials, video URL and public repository. Confirm setup instructions match the code. Do not invent customer traction, production deployment, or savings.
