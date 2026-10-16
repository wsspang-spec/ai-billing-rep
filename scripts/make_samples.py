"""Render the SYNTHETIC invoices in data/seed.json to one-page PDFs (+ .txt twins).

    uv run python scripts/make_samples.py

inbox entries -> data/samples/inbox/<file>, eval_invoices -> data/samples/eval/<file>.
All data is synthetic demo data.
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
OUT = ROOT / "data" / "samples"
LABEL = "SYNTHETIC DEMO INVOICE"


def money(x: float) -> str:
    return f"${x:,.2f}"


def text_twin(inv: dict) -> str:
    HEADER = inv["vendor"] + " (synthetic)"
    rows = [
        HEADER,
        LABEL,
        "All data on this invoice is synthetic demo data.",
        "",
        f"Invoice number: {inv['invoice_number']}",
        f"Account: {inv['account']}",
        f"Service period: {inv['period_start']} to {inv['period_end']}",
        f"Invoice date: {inv['invoice_date']}",
        f"Due date: {inv['due_date']}",
        "",
        "Line | Service | Type | Description | Amount",
    ]
    for ln in inv["lines"]:
        rows.append(f"{ln['line_no']} | {ln.get('service_id') or ''} | {ln.get('charge_type', '')} | {ln['description']} | {money(ln['amount'])}")
    rows += ["", f"Total due: {money(inv['total'])}", ""]
    return "\n".join(rows)


def render_pdf(inv: dict, path: Path) -> None:
    HEADER = inv["vendor"] + " (synthetic)"
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"{inv['invoice_number']} ({LABEL})", author=HEADER,
    )
    red = styles["Normal"].clone("red", textColor=colors.HexColor("#b00020"), fontName="Helvetica-Bold", fontSize=11)
    story = [
        Paragraph(HEADER, styles["Title"]),
        Paragraph(LABEL, red),
        Paragraph("All data on this invoice is synthetic demo data.", styles["Italic"]),
        Spacer(1, 14),
    ]
    meta = [
        ["Invoice number", inv["invoice_number"]],
        ["Account", inv["account"]],
        ["Service period", f"{inv['period_start']} to {inv['period_end']}"],
        ["Invoice date", inv["invoice_date"]],
        ["Due date", inv["due_date"]],
    ]
    mt = Table(meta, colWidths=[1.6 * inch, 4.4 * inch])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [mt, Spacer(1, 18)]
    lines = [["Line", "Service", "Type", "Description", "Amount"]]
    lines += [[str(ln["line_no"]), ln.get("service_id") or "", ln.get("charge_type", ""), ln["description"], money(ln["amount"])] for ln in inv["lines"]]
    lines.append(["", "", "", "Total due", money(inv["total"])])
    lt = Table(lines, colWidths=[0.5 * inch, 0.8 * inch, 1.0 * inch, 2.7 * inch, 1.1 * inch])
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("GRID", (0, 0), (-1, -2), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [lt, Spacer(1, 24), Paragraph(
        f"{LABEL}. {HEADER} is a fictional carrier; no real account, service or payment is involved.",
        styles["Italic"],
    )]
    doc.build(story)


def main() -> None:
    seed = json.loads(SEED.read_text())
    made = []
    for key, sub in (("inbox", "inbox"), ("eval_invoices", "eval"), ("portal_only", "portal")):
        folder = OUT / sub
        folder.mkdir(parents=True, exist_ok=True)
        for inv in seed.get(key, []):
            pdf = folder / inv["file"]
            render_pdf(inv, pdf)
            pdf.with_suffix(".txt").write_text(text_twin(inv))
            made.append(pdf.relative_to(ROOT))
    for p in made:
        print(p)


if __name__ == "__main__":
    main()
