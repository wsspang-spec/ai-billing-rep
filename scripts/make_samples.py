"""Render the invoices in data/seed.json as two-page telecom bills (PDF + .txt twin).

    uv run python scripts/make_samples.py

inbox -> data/samples/inbox/, eval_invoices -> data/samples/eval/,
portal_only -> data/samples/portal/ and data/samples/upload/ (extra bills for drag-and-drop).
Charge lines and totals are exactly the seed's; the app's checks depend on them.
"""

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
OUT = ROOT / "data" / "samples"
W, H = letter
M = 0.6 * inch

CARRIERS = {
    "Northstar Telecom": {
        "color": "#0b4f8a", "accent": "#f2a900", "mark": "star", "tagline": "Business Fiber & Voice",
        "remit": ["Northstar Telecom", "PO Box 4410", "Hartford, CT 06101-4410"],
        "office": "1 Constitution Plaza, Hartford, CT 06103",
        "phone": "1-800-555-0142", "web": "northstartelecom.example/business",
    },
    "Harbor Communications": {
        "color": "#0f6b66", "accent": "#7cc6c0", "mark": "wave", "tagline": "Managed Network Services",
        "remit": ["Harbor Communications", "PO Box 7720", "Boston, MA 02241-7720"],
        "office": "99 Atlantic Avenue, Boston, MA 02110",
        "phone": "1-800-555-0187", "web": "harborcomms.example/support",
    },
}
SITES = {
    "Hartford": ["200 Asylum Street, Suite 410", "Hartford, CT 06103"],
    "Boston": ["75 Summer Street, Floor 6", "Boston, MA 02110"],
    "Brooklyn": ["330 Jay Street, Unit 3B", "Brooklyn, NY 11201"],
}


def clean(name: str) -> str:
    return " ".join(name.replace("(synthetic)", "").replace("Demo", "").split())


def money(x: float) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def d(s: str) -> str:
    return date.fromisoformat(s).strftime("%b %d, %Y")


def facts(inv: dict, seed: dict) -> dict:
    vendor = clean(inv["vendor"])
    acct = next((a for a in seed.get("accounts", []) if a["id"] == inv["account"]), {})
    site = acct.get("site", "")
    prior = [h for h in seed.get("history", []) if h["account"] == inv["account"] and h["period_end"] < inv["period_start"]]
    prev = max(prior, key=lambda h: h["period_end"])["total"] if prior else 0.0
    return {
        "vendor": vendor, "c": CARRIERS.get(vendor, CARRIERS["Northstar Telecom"]),
        "company": clean(seed.get("company", "Atlas Retail")), "site": site,
        "site_addr": SITES.get(site, ["100 Main Street", site]), "prev": float(prev),
    }


def text_twin(inv: dict, seed: dict) -> str:
    f = facts(inv, seed)
    c = f["c"]
    rows = [
        f"{f['vendor']} - {c['tagline']}",
        "Remit to: " + ", ".join(c["remit"]),
        "",
        f"Bill to: {f['company']}, {f['site']} office, Attn: Accounts Payable, " + ", ".join(f["site_addr"]),
        f"Account number: {inv['account']}",
        f"Invoice number: {inv['invoice_number']}",
        f"Invoice date: {inv['invoice_date']}",
        f"Billing period: {inv['period_start']} to {inv['period_end']}",
        f"Due date: {inv['due_date']}",
        "",
        "ACCOUNT SUMMARY",
        f"Previous balance: {money(f['prev'])}",
        f"Payment received - thank you: {money(-f['prev'])}",
        "Balance forward: $0.00",
        f"Current charges: {money(inv['total'])}",
        f"TOTAL AMOUNT DUE: {money(inv['total'])} by {inv['due_date']}",
        "",
        "DETAIL OF CURRENT CHARGES",
        "Line | Service ID | Type | Description | Amount",
    ]
    for ln in inv["lines"]:
        rows.append(f"{ln['line_no']} | {ln.get('service_id') or ''} | {ln.get('charge_type', '')} | {ln['description']} | {money(ln['amount'])}")
    rows += [
        f"Total current charges: {money(inv['total'])}",
        "Taxes, surcharges and fees: included above",
        "",
        f"Customer service: {c['phone']} | {c['web']}",
        "",
    ]
    return "\n".join(rows)


def logo(cv: canvas.Canvas, f: dict, x: float, y: float) -> None:
    c = f["c"]
    cv.setFillColor(colors.HexColor(c["color"]))
    cv.roundRect(x, y - 30, 38, 38, 6, stroke=0, fill=1)
    cv.setFillColor(colors.HexColor(c["accent"]))
    if c["mark"] == "star":
        p = cv.beginPath()
        cx, cy, r1, r2 = x + 19, y - 11, 13, 5.5
        import math
        for i in range(10):
            r = r1 if i % 2 == 0 else r2
            a = math.pi / 2 + i * math.pi / 5
            (p.moveTo if i == 0 else p.lineTo)(cx + r * math.cos(a), cy + r * math.sin(a))
        p.close()
        cv.drawPath(p, stroke=0, fill=1)
    else:
        cv.setStrokeColor(colors.HexColor(c["accent"]))
        cv.setLineWidth(3)
        for k in range(3):
            p = cv.beginPath()
            yy = y - 22 + k * 9
            p.moveTo(x + 6, yy)
            p.curveTo(x + 13, yy + 6, x + 19, yy - 6, x + 26, yy)
            p.curveTo(x + 29, yy + 3, x + 31, yy + 3, x + 33, yy)
            cv.drawPath(p, stroke=1, fill=0)
    cv.setFillColor(colors.HexColor(c["color"]))
    cv.setFont("Helvetica-Bold", 20)
    cv.drawString(x + 48, y - 10, f["vendor"])
    cv.setFillColor(colors.HexColor("#5b6675"))
    cv.setFont("Helvetica", 9)
    cv.drawString(x + 48, y - 24, c["tagline"] + "  |  " + c["office"])


def footer(cv: canvas.Canvas, f: dict, page: int) -> None:
    c = f["c"]
    cv.setStrokeColor(colors.HexColor("#c9d0da"))
    cv.setLineWidth(0.5)
    cv.line(M, 0.55 * inch, W - M, 0.55 * inch)
    cv.setFillColor(colors.HexColor("#5b6675"))
    cv.setFont("Helvetica", 7.5)
    cv.drawString(M, 0.4 * inch, f"Customer service {c['phone']}  |  {c['web']}  |  Mon-Fri 8am-8pm ET")
    cv.drawRightString(W - M, 0.4 * inch, f"Page {page} of 2")


def kv(cv, x, y, label, value, bold=False, size=9):
    cv.setFont("Helvetica", size)
    cv.setFillColor(colors.HexColor("#5b6675"))
    cv.drawString(x, y, label)
    cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    cv.setFillColor(colors.HexColor("#1b2430"))
    cv.drawRightString(x + 2.55 * inch, y, value)


def page_one(cv: canvas.Canvas, inv: dict, f: dict) -> None:
    c = f["c"]
    brand = colors.HexColor(c["color"])
    ink = colors.HexColor("#1b2430")
    grey = colors.HexColor("#5b6675")
    top = H - M
    logo(cv, f, M, top)
    # invoice meta (top right)
    cv.setFillColor(ink)
    cv.setFont("Helvetica-Bold", 13)
    cv.drawRightString(W - M, top - 6, "INVOICE")
    y = top - 22
    for label, val in (
        ("Account number", inv["account"]), ("Invoice number", inv["invoice_number"]),
        ("Invoice date", d(inv["invoice_date"])),
        ("Billing period", f"{d(inv['period_start'])} - {d(inv['period_end'])}"),
        ("Due date", d(inv["due_date"])),
    ):
        cv.setFont("Helvetica", 8.5); cv.setFillColor(grey); cv.drawRightString(W - M - 1.75 * inch, y, label)
        cv.setFont("Helvetica-Bold", 8.5); cv.setFillColor(ink); cv.drawRightString(W - M, y, val)
        y -= 12
    cv.setStrokeColor(brand); cv.setLineWidth(2)
    cv.line(M, top - 90, W - M, top - 90)

    # customer + remit blocks
    y0 = top - 112
    cv.setFont("Helvetica-Bold", 8); cv.setFillColor(grey)
    cv.drawString(M, y0, "BILL TO")
    cv.drawString(W / 2 + 10, y0, "REMIT PAYMENT TO")
    cv.setFillColor(ink); cv.setFont("Helvetica-Bold", 10)
    cv.drawString(M, y0 - 14, f["company"])
    cv.setFont("Helvetica", 9.5)
    for i, ln in enumerate([f"{f['site']} office - Attn: Accounts Payable", *f["site_addr"]]):
        cv.drawString(M, y0 - 27 - i * 12, ln)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawString(W / 2 + 10, y0 - 14, c["remit"][0])
    cv.setFont("Helvetica", 9.5)
    for i, ln in enumerate(c["remit"][1:]):
        cv.drawString(W / 2 + 10, y0 - 27 - i * 12, ln)

    # account summary box
    bx, by, bw, bh = M, top - 352, 3.55 * inch, 170
    cv.setStrokeColor(colors.HexColor("#c9d0da")); cv.setLineWidth(0.8)
    cv.rect(bx, by, bw, bh, stroke=1, fill=0)
    cv.setFillColor(brand); cv.rect(bx, by + bh - 22, bw, 22, stroke=0, fill=1)
    cv.setFillColor(colors.white); cv.setFont("Helvetica-Bold", 10)
    cv.drawString(bx + 10, by + bh - 15, "ACCOUNT SUMMARY")
    sx, sy = bx + 12, by + bh - 42
    kv(cv, sx, sy, "Previous balance", money(f["prev"]))
    kv(cv, sx, sy - 16, "Payment received - thank you", money(-f["prev"]))
    kv(cv, sx, sy - 32, "Balance forward", money(0))
    cv.setStrokeColor(colors.HexColor("#e3e7ee")); cv.line(sx, sy - 41, sx + 2.55 * inch, sy - 41)
    kv(cv, sx, sy - 56, "Current charges (see page 2)", money(inv["total"]))
    cv.setStrokeColor(ink); cv.setLineWidth(1); cv.line(sx, sy - 66, sx + 2.55 * inch, sy - 66)
    kv(cv, sx, sy - 84, "TOTAL AMOUNT DUE", money(inv["total"]), bold=True, size=11.5)
    cv.setFont("Helvetica", 8.5); cv.setFillColor(grey)
    cv.drawString(sx, sy - 102, f"Payment due by {d(inv['due_date'])}")

    # amount due callout + messages (right column)
    rx, rw = W / 2 + 10, W - M - (W / 2 + 10)
    cv.setFillColor(colors.HexColor("#f4f6f9")); cv.rect(rx, by + 80, rw, 90, stroke=0, fill=1)
    cv.setFillColor(grey); cv.setFont("Helvetica-Bold", 8)
    cv.drawString(rx + 12, by + 150, "AMOUNT DUE")
    cv.setFillColor(brand); cv.setFont("Helvetica-Bold", 24)
    cv.drawString(rx + 12, by + 120, money(inv["total"]))
    cv.setFillColor(ink); cv.setFont("Helvetica", 9)
    cv.drawString(rx + 12, by + 96, f"Due {d(inv['due_date'])}")
    cv.setFillColor(grey); cv.setFont("Helvetica-Bold", 8)
    cv.drawString(rx, by + 60, "MESSAGES")
    cv.setFillColor(ink); cv.setFont("Helvetica", 8.5)
    for i, ln in enumerate([
        "Thank you for your business. Your previous payment",
        "has been applied to this account.",
        f"Questions about this bill? Call {c['phone']}",
        f"or visit {c['web']}.",
    ]):
        cv.drawString(rx, by + 46 - i * 11, ln)

    # service at a glance
    gy = by - 26
    cv.setFillColor(grey); cv.setFont("Helvetica-Bold", 8)
    cv.drawString(M, gy, "SERVICE LOCATION")
    cv.setFillColor(ink); cv.setFont("Helvetica", 9)
    svcs = sorted({ln.get("service_id") or "" for ln in inv["lines"]} - {""})
    cv.drawString(M, gy - 13, f"{f['company']} - {f['site']}, {f['site_addr'][-1]}   |   Service ID(s): {', '.join(svcs)}")

    # tear-off payment stub
    sy0 = 2.55 * inch
    cv.setDash(4, 3); cv.setStrokeColor(grey); cv.setLineWidth(0.6)
    cv.line(M - 10, sy0, W - M + 10, sy0)
    cv.setDash()
    cv.setFont("Helvetica-Oblique", 7.5); cv.setFillColor(grey)
    cv.drawCentredString(W / 2, sy0 + 5, "Please detach and return this portion with your payment. Make checks payable to " + f["vendor"] + ".")
    logo(cv, f, M, sy0 - 18)
    yy = sy0 - 68
    for label, val in (("Account number", inv["account"]), ("Invoice number", inv["invoice_number"]),
                       ("Payment due date", d(inv["due_date"])), ("Amount due", money(inv["total"]))):
        cv.setFont("Helvetica", 9); cv.setFillColor(grey); cv.drawString(M, yy, label)
        cv.setFont("Helvetica-Bold", 9); cv.setFillColor(ink); cv.drawRightString(M + 2.7 * inch, yy, val)
        yy -= 14
    cv.setFont("Helvetica", 9); cv.setFillColor(grey); cv.drawString(M, yy, "Amount enclosed")
    cv.setStrokeColor(ink); cv.line(M + 1.4 * inch, yy - 2, M + 2.7 * inch, yy - 2)
    cv.setFont("Helvetica-Bold", 8); cv.setFillColor(grey)
    cv.drawString(W / 2 + 10, sy0 - 64, "REMIT TO")
    cv.setFillColor(ink); cv.setFont("Helvetica", 10)
    for i, ln in enumerate(c["remit"]):
        cv.drawString(W / 2 + 10, sy0 - 78 - i * 13, ln)
    footer(cv, f, 1)


def page_two(cv: canvas.Canvas, inv: dict, f: dict) -> None:
    c = f["c"]
    brand = colors.HexColor(c["color"])
    ink = colors.HexColor("#1b2430")
    grey = colors.HexColor("#5b6675")
    top = H - M
    cv.setFillColor(brand); cv.setFont("Helvetica-Bold", 12)
    cv.drawString(M, top - 8, f["vendor"])
    cv.setFillColor(grey); cv.setFont("Helvetica", 8.5)
    cv.drawRightString(W - M, top - 8, f"Account {inv['account']}  |  Invoice {inv['invoice_number']}  |  "
                       f"Billing period {d(inv['period_start'])} - {d(inv['period_end'])}")
    cv.setStrokeColor(brand); cv.setLineWidth(1.5); cv.line(M, top - 16, W - M, top - 16)
    cv.setFillColor(ink); cv.setFont("Helvetica-Bold", 14)
    cv.drawString(M, top - 44, "Detail of current charges")
    cv.setFont("Helvetica", 9); cv.setFillColor(grey)
    cv.drawString(M, top - 58, f"{f['company']} - {f['site']} office")

    cols = [M, M + 0.5 * inch, M + 1.45 * inch, M + 2.6 * inch]
    right = W - M
    y = top - 86
    cv.setFillColor(brand); cv.rect(M, y - 6, right - M, 20, stroke=0, fill=1)
    cv.setFillColor(colors.white); cv.setFont("Helvetica-Bold", 9)
    for x, h in zip(cols, ["Line", "Service ID", "Type", "Description"]):
        cv.drawString(x + 6, y, h)
    cv.drawRightString(right - 6, y, "Amount")
    y -= 24
    cv.setFont("Helvetica", 9.5)
    for i, ln in enumerate(inv["lines"]):
        if i % 2:
            cv.setFillColor(colors.HexColor("#f4f6f9")); cv.rect(M, y - 6, right - M, 20, stroke=0, fill=1)
        cv.setFillColor(ink)
        cv.drawString(cols[0] + 6, y, str(ln["line_no"]))
        cv.drawString(cols[1] + 6, y, ln.get("service_id") or "")
        cv.drawString(cols[2] + 6, y, (ln.get("charge_type") or "").capitalize())
        cv.drawString(cols[3] + 6, y, ln["description"])
        cv.drawRightString(right - 6, y, money(ln["amount"]))
        y -= 20
    cv.setStrokeColor(ink); cv.setLineWidth(1); cv.line(M, y + 8, right, y + 8)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawString(cols[3] + 6, y - 6, "Total current charges")
    cv.drawRightString(right - 6, y - 6, money(inv["total"]))
    cv.setFont("Helvetica-Oblique", 8.5); cv.setFillColor(grey)
    cv.drawString(M, y - 30, "Taxes, surcharges and fees: included above.")
    cv.drawString(M, y - 43, "Charges are billed in advance for the billing period shown. Usage, if any, is billed in arrears.")
    footer(cv, f, 2)


def render_pdf(inv: dict, seed: dict, path: Path) -> None:
    f = facts(inv, seed)
    cv = canvas.Canvas(str(path), pagesize=letter)
    cv.setTitle(f"{f['vendor']} invoice {inv['invoice_number']}")
    cv.setAuthor(f["vendor"])
    cv.setSubject(f"Account {inv['account']}, billing period {inv['period_start']} to {inv['period_end']}")
    page_one(cv, inv, f)
    cv.showPage()
    page_two(cv, inv, f)
    cv.showPage()
    cv.save()


def main() -> None:
    seed = json.loads(SEED.read_text())
    made = []
    for key, subs in (("inbox", ["inbox"]), ("eval_invoices", ["eval"]), ("portal_only", ["portal", "upload"])):
        for sub in subs:
            folder = OUT / sub
            folder.mkdir(parents=True, exist_ok=True)
            for inv in seed.get(key, []):
                pdf = folder / inv["file"]
                render_pdf(inv, seed, pdf)
                pdf.with_suffix(".txt").write_text(text_twin(inv, seed))
                made.append(pdf.relative_to(ROOT))
    for p in made:
        print(p)


if __name__ == "__main__":
    main()
