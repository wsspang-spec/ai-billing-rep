"""Generate synthetic printable HTML inputs. Standard library only."""
import html
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "data/demo_dataset.json").read_text())
out = ROOT / "data/documents"
out.mkdir(parents=True, exist_ok=True)
def esc(x): return html.escape(str(x))
def money(n): return f"USD {n / 100:,.2f}"
def page(title, body):
    return '<!doctype html><html><head><meta charset="utf-8"><title>'+esc(title)+'''</title><style>
body{font:16px Arial,sans-serif;max-width:850px;margin:40px auto;color:#172334;padding:24px}
header{border-bottom:3px solid #185b75;padding-bottom:18px}small{color:#615800}
table{border-collapse:collapse;width:100%;margin:24px 0}td,th{text-align:left;padding:12px;border-bottom:1px solid #ccd4dc}
.amount{text-align:right}footer{margin-top:32px;color:#54616e}@media print{body{margin:0;padding:20px}}
</style></head><body><header><small>SYNTHETIC HACKATHON DEMO — NOT PAYABLE</small><h1>'''+esc(title)+'</h1></header>'+body+'<footer>Fictional document. No real carrier, customer, payment, or tax determination.</footer></body></html>'
vendors={v["id"]:v["name"] for v in data["vendors"]}
for inv in data["invoices"]:
    body=f'<h2>{esc(vendors[inv["vendor_id"]])}</h2><p>Customer: {esc(data["company"])}<br>Account: {esc(inv["account_id"])}<br>Invoice date: {esc(inv["invoice_date"])}<br>Due: {esc(inv["due_date"])}<br>Service period: {esc(inv["period_start"])} to {esc(inv["period_end"])}</p>'
    body+='<table><tr><th>Service</th><th>Description</th><th class="amount">Amount</th></tr>'
    for line in inv["lines"]:
        body+=f'<tr><td>{esc(line["service_id"])}</td><td>{esc(line["description"])}</td><td class="amount">{money(line["amount_cents"])}</td></tr>'
    body+='</table>'
    for key in ["current_charges_cents","prior_balance_cents","applied_credit_cents","amount_due_cents"]:
        body+=f'<p><strong>{esc(key.replace("_cents","").replace("_"," ").title())}:</strong> {money(inv[key])}</p>'
    (out / (inv["id"]+".html")).write_text(page("Invoice "+inv["invoice_number"],body),encoding="utf-8")
for doc in data["documents"]:
    body=f'<p>Record ID: {esc(doc["id"])}<br>Type: {esc(doc["type"])}<br>Recorded: {esc(doc["recorded_at"])}</p><p>{esc(doc["text"])}</p>'
    (out / (doc["id"]+".html")).write_text(page(doc["id"],body),encoding="utf-8")
links=''.join(f'<li><a href="{esc(p.name)}">{esc(p.stem)}</a></li>' for p in sorted(out.glob("*.html")) if p.name!="index.html")
(out/"index.html").write_text(page("Demo document index","<ul>"+links+"</ul>"),encoding="utf-8")
print(f"Generated {len(data['invoices'])} invoices and {len(data['documents'])} supporting documents in {out}")
