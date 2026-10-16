# AI Billing Rep

An AI telecom billing assistant for teams managing invoices across carriers and locations. The proposed workflow collects invoices, checks charges against dated company records, routes exceptions for human review, and turns reviewed information into CFO reporting.

## Project status

Hackathon planning scaffold. This repository currently contains documentation, not a working application. Integrations below are planned; mark them implemented only after end-to-end verification. No production payments or carrier actions are implemented.

## Demo

See [docs/demo.md](docs/demo.md) for two scenarios and acceptance checks. All demo invoices, companies, accounts, and portals must be labeled synthetic.

## Planned architecture

| Tool | Role |
| --- | --- |
| AWS Bedrock / Claude | Extract invoice information and choose investigation steps |
| SurrealDB Agent Memory | Retrieve sourced contract terms and amendments by effective date |
| Daytona | Run agent code and deterministic invoice comparisons in a sandbox |
| Anchor Browser | Fetch invoices and submit approved inquiries in a demo portal |
| ElevenLabs | Generate a voice clarification message from reviewed evidence |
| Arize AX | Trace executions and evaluate results against labeled cases |

The frontend has a billing queue, an invoice evidence panel, and a finance summary. The backend coordinates tools, validates amounts and dates, enforces approval requirements, and records action confirmations.

## Financial and action states

- Keep billed amounts, disputed amounts, promised credits, and applied credits separate.
- An unexplained charge requires clarification; it is not automatically an overcharge.
- Payment eligibility requires configured policy checks, not just a matching prior amount.
- Demo payment scheduling must be visibly labeled simulated.
- External inquiries require approval tied to the exact action.
- Save portal confirmation before marking an inquiry submitted.
- Preserve original values and sources when recording reviewed corrections.

## Development handoff

Add application code and actual setup instructions here as the team implements the prototype. Record required environment-variable names in an example configuration without secret values. Never commit credentials, real invoices, or customer information.

## Submission checklist

- [ ] Working demo and accurate implemented/planned status
- [ ] Public repository with runnable setup instructions
- [ ] Under-two-minute video with accessible playback
- [ ] Measured results on labeled test cases
- [ ] Sponsor integrations explained with actual evidence
- [ ] Devpost summary, impact sources, architecture, and team information
