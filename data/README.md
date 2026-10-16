# Synthetic demo data

All vendors, records, and amounts are fictional. No bank details or real customer data are included.

Start with demo_dataset.json. Money is integer USD cents, not floating-point dollars. Main demo: October A is 52500 cents, supported by the October amendment; October B is 62000 cents including an unexplained 12000-cent adjustment. C is 30000 cents and initially available only in the demo portal.

September current charges: 125000 cents. October: 144500 cents. Change: 19500 cents = supported recurring increase 7500 + unexplained adjustment 12000. A separate 60000-cent promised credit is NOT deducted. November baseline under stated assumptions: 132500; if the surcharge repeats: 144500. These are synthetic expected values, not measured financial impact.

Run python scripts/render_demo_documents.py to generate printable HTML invoices and supporting documents into data/documents. Those files are document-reading inputs. The normalized JSON is ground truth for development: do not hand it to the model when measuring extraction accuracy. This pack does not measure OCR accuracy or provide scanned PDFs.

For the missing-invoice demo, initially load only initial_upload_ids, then retrieve portal_only_invoice_ids. Do not silently pre-load the missing invoice into the agent context. Prior September records and contracts may be seeded.

Evaluation variants are independent cases, not additional invoices to add to the CFO totals. Never feed evals/expected.jsonl to the agent.
