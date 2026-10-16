# AI Billing Rep

An AI billing rep for teams that pay telecom invoices across carriers and locations. It reads each invoice, checks every charge against the company's own **dated** records, explains what changed, schedules what is explained, and asks a human before anything leaves the building.

All companies, invoices, contracts, portals and amounts are **synthetic**. Payments are a **simulated** queue; no real money moves.

## What it does (the 2-minute version)

Two October bills went up. Which one should the billing team act on?

| Bill | What changed | What the agent does |
| --- | --- | --- |
| **N-OCT-101** (Northstar, ACCT-101) | $450 → $525 (+$75) | Recalls the price **in effect on Oct 1** from SurrealDB: an approved amendment moved SVC-A to $525 from October 1. Explained. Payment scheduled (simulated). The same $525 on a **September** bill is flagged *Needs review*, because the amendment wasn't in effect yet. |
| **H-OCT-202** (Harbor, ACCT-202) | New $120 "Interstate Service Adjustment" | No contract term or record covers it. *Needs clarification*, not "overbilling". Proposes an inquiry; nothing is sent until a person approves. After approval, Anchor Browser files it on the carrier portal and the app stores the portal's case number. |

The finance view keeps **billed**, **disputed**, **promised credit** and **applied credit** apart: the $600 credit the vendor promised is not counted as savings until it posts.

## Architecture

![Architecture](docs/architecture.svg)

| # | Step | Who does it |
| --- | --- | --- |
| 1 | **Bring in.** Fetch from the AP inbox (a sample folder; Gmail later) or drag and drop a PDF. | FastAPI app |
| 2 | **Read.** Claude reads the PDF into line items with a fixed schema. | Claude on AWS Bedrock (`us.anthropic.claude-opus-5-5`) |
| 3 | **Remember.** Invoices, contracts and prices with the date each took effect; users and sessions too. | SurrealDB |
| 4 | **Check.** The line-by-line comparison runs in a sandbox, not on the laptop. | Daytona |
| 5 | **Decide.** Explained → schedule payment (simulated). Unexplained → propose an inquiry and wait. | Claude on AWS Bedrock |
| 6 | **Act.** After approval: file the inquiry on the carrier portal and store the confirmation. | Anchor Browser (portal hosted on a Daytona preview link) |
| ∞ | **Watch.** Every step traced; the team's labeled cases scored as experiments. | Arize AX |

### Controls enforced in code (not by the model)
- **Approval gate:** `POST /api/invoices/{id}/inquiry` returns **403** until an approval tied to that inquiry exists. The UI has a "Try sending without approval" link to show it.
- **No "Submitted" without proof:** an inquiry is marked submitted only after the portal's own API shows the new case. A retry first checks for an existing case and never files twice.
- **Duplicates:** an invoice number already received gets status *Duplicate* and no payment instruction.
- **Model guard:** if Claude says *Explained* but a line doesn't match the price in effect for its period, the status is overridden to *Needs review*. Citations must point at real evidence ids, or they're dropped.
- **Totals and dates:** the sandbox checks that lines add up to the total and dates are valid.

## Run it

```bash
uv sync
cp .env.example .env        # fill in the keys (AWS Bedrock, Daytona, Anchor, Arize)
uv run python scripts/build_seed.py      # data/demo_dataset.json -> data/seed.json
uv run python scripts/make_samples.py    # invoice PDFs into data/samples/
uv run python -m billingrep.portal_deploy   # deploys the synthetic carrier portal to Daytona, prints its URL
uv run uvicorn billingrep.web:app --port 8010
```

Open http://localhost:8010 and sign in as `maria@atlas.example` / `demo-password` (synthetic demo user, checked by SurrealDB's `crypto::argon2`).

## Demo walkthrough

See [docs/demo-walkthrough.md](docs/demo-walkthrough.md).

## Evaluation (actual results)

The team's 14-case pack (`evals/`) is run against the **real app** by `eval/run_eval.py` (in-memory database, never the demo's). Latest run: **8 of 14 pass; 8 of the 9 cases the app implements.** E01 (explained increase) and E03 (unexplained surcharge) passed **3 of 3** repeat runs. Full table with times and trace ids: [eval/results.md](eval/results.md). Results are logged to Arize AX as dataset `billing-rep-eval-pack` with one experiment per run.

Not implemented yet, and scored as failures on purpose: E07 (browser-timeout retry case in the eval adapter; the app itself checks for an existing case before resubmitting), E08 (arithmetic with prior balance), E09 (missing-invoice coverage), E11 (known-but-unavailable amendment), E12 (carried-forward balance), E14 (cancellation).

```bash
uv run python eval/run_eval.py --trials 3
```

## Honest limits
- Synthetic data, n=1 per case plus 3 repeats of the two demo cases. No accuracy claim beyond that.
- Payment scheduling is a simulated queue. The carrier portal is ours, synthetic, and hosted on Daytona; real carrier portals need the customer's own logins.
- PDF reads are cached by file hash so a demo replay is fast; the cache is filled by Claude on Bedrock on the first read.
- ElevenLabs voice message (`billingrep/voice.py`) works but is off in the demo (`BILLINGREP_VOICE=1` turns it on); it is generated, never delivered.
- Gmail ingestion is not built; the inbox is a folder.

## Financial and action states
- Billed amounts, disputed amounts, promised credits and applied credits stay separate.
- An unexplained charge requires clarification; it is not automatically an overcharge.
- External inquiries require approval tied to the exact action.
- Portal confirmation is saved before an inquiry is marked submitted.

## Repo map

| Path | What |
| --- | --- |
| `billingrep/web.py` | FastAPI routes: login, inbox, fetch/upload, invoice detail, approve, inquiry, finance, reset |
| `billingrep/agent.py` | The pipeline for one invoice: read → recall → compare → decide → guard → route |
| `billingrep/llm.py` | Claude on Bedrock: PDF extraction and the decision, both as tool calls |
| `billingrep/db.py` | SurrealDB: schema-less tables, seed/reset, prices as of a date, argon2 sign-in |
| `billingrep/checks.py` | The comparison script, run in a Daytona sandbox |
| `billingrep/actions.py` | Approval gate, inquiry filing, finance summary |
| `billingrep/anchor_actions.py`, `portal_deploy.py`, `portal/` | Anchor Browser filing; the synthetic portal and its Daytona deploy |
| `billingrep/tracing.py` | Arize AX tracing (OpenInference) |
| `data/demo_dataset.json` | The team's ground-truth dataset (cents); `data/seed.json` is generated from it |
| `evals/`, `eval/` | The 14-case pack and scorer; the adapter that runs it against the app |
