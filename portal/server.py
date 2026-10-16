"""Synthetic carrier portal for the demo: "Harbor Demo Communications (synthetic)". STDLIB ONLY.

    PORT=8080 python server.py

Login demo/demo (cookie). /invoices lists invoices (PDFs from ./files if present),
/inquiry files a billing inquiry -> case NW-CASE-<4 digits> saved to cases.json.
GET /api/cases?invoice_number=... returns matching cases (used for idempotency).
Everything here is SYNTHETIC demo data.
"""

import html
import json
import os
import random
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HERE = Path(__file__).resolve().parent
FILES = HERE / "files"
CASES = HERE / "cases.json"
USER, PASSWORD = "demo", "demo"
COOKIE = "nw_session"
TOKEN = "synthetic-demo-session"
LOCK = threading.Lock()

INVOICES = [  # mirrors data/demo_dataset.json (synthetic)
    {"invoice_number": "H-SEP-202", "account": "ACCT-202", "period": "2026-09-01 to 2026-09-30",
     "invoice_date": "2026-09-01", "due_date": "2026-09-30", "total": 500.0, "file": "H-SEP-202.pdf"},
    {"invoice_number": "H-OCT-202", "account": "ACCT-202", "period": "2026-10-01 to 2026-10-31",
     "invoice_date": "2026-10-01", "due_date": "2026-10-30", "total": 620.0, "file": "H-OCT-202.pdf"},
]

CSS = """
body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:0;background:#f4f6f9;color:#1b2430}
header{background:#1f3a5f;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
header b{font-size:18px} .tag{background:#b00020;color:#fff;font-size:12px;padding:3px 8px;border-radius:4px}
main{max-width:760px;margin:28px auto;background:#fff;padding:24px 28px;border-radius:8px;box-shadow:0 1px 4px #0002}
label{display:block;margin-top:12px;font-weight:600;font-size:14px}
input,textarea{width:100%;box-sizing:border-box;padding:8px;margin-top:4px;border:1px solid #c5ccd6;border-radius:4px;font-size:14px}
button{margin-top:16px;background:#1f3a5f;color:#fff;border:0;padding:10px 18px;border-radius:4px;font-size:14px;cursor:pointer}
table{width:100%;border-collapse:collapse;margin-top:10px} th,td{text-align:left;padding:8px;border-bottom:1px solid #e3e7ee;font-size:14px}
nav a{color:#fff;margin-left:14px} .note{color:#667;font-size:13px} .case{font-size:22px;font-weight:700;color:#1f3a5f}
"""


def page(title: str, body: str, nav: bool = True) -> bytes:
    links = '<nav><a href="/invoices">Invoices</a><a href="/inquiry">Billing inquiry</a><a href="/cases">My cases</a><a href="/logout">Log out</a></nav>' if nav else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} - Harbor Communications · Customer portal</title><style>{CSS}</style></head>
<body><header><div><b>Harbor Communications</b> · Customer portal</div>{links}</header>
<main>{body}<p class="note">Harbor Communications · Customer service 1-800-555-0187</p></main></body></html>""".encode()


def load_cases() -> list:
    try:
        return json.loads(CASES.read_text())
    except (OSError, ValueError):
        return []


def save_case(case: dict) -> None:
    cases = load_cases()
    cases.append(case)
    CASES.write_text(json.dumps(cases, indent=1))


def new_case_id(existing: list) -> str:
    used = {c["case_id"] for c in existing}
    n = len(existing) + 1
    while f"DEMO-CASE-{n:03d}" in used:
        n += 1
    return f"DEMO-CASE-{n:03d}"


class Handler(BaseHTTPRequestHandler):
    server_version = "HarborSynthetic/1.0"

    def log_message(self, fmt, *args):  # quieter logs
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    # helpers
    def logged_in(self) -> bool:
        return f"{COOKIE}={TOKEN}" in (self.headers.get("Cookie") or "")

    def send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, to: str, headers: dict | None = None):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def json(self, code: int, obj) -> None:
        self.send(code, json.dumps(obj).encode(), "application/json")

    def form(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    # routes
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        p = url.path
        if p == "/health":
            return self.json(200, {"ok": True, "portal": "Harbor Demo Communications (synthetic)"})
        if p == "/api/cases":
            cases = load_cases()
            inv = q.get("invoice_number")
            if inv:
                cases = [c for c in cases if c.get("invoice_number") == inv]
            return self.json(200, {"synthetic": True, "cases": cases})
        if p == "/":
            if self.logged_in():
                return self.redirect("/invoices")
            err = '<p style="color:#b00020">Wrong user or password.</p>' if q.get("error") else ""
            nxt = html.escape(q.get("next", "/invoices"))
            return self.send(200, page("Sign in", f"""<h2>Sign in</h2><p class="note">User <code>demo</code>, password <code>demo</code>.</p>{err}
<form method="post" action="/login"><input type="hidden" name="next" value="{nxt}">
<label for="username">User</label><input id="username" name="username" autocomplete="off">
<label for="password">Password</label><input id="password" name="password" type="password">
<button id="login" type="submit">Sign in</button></form>""", nav=False))
        if p == "/logout":
            return self.redirect("/", {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})
        if not self.logged_in():
            return self.redirect("/?next=" + quote(p))
        if p == "/invoices":
            rows = ""
            for inv in INVOICES:
                f = FILES / inv["file"]
                link = f'<a href="/files/{inv["file"]}">PDF</a>' if f.exists() else "-"
                rows += (f"<tr><td>{inv['invoice_number']}</td><td>{inv['account']}</td><td>{inv['period']}</td>"
                         f"<td>{inv['due_date']}</td><td>${inv['total']:,.2f}</td><td>{link}</td>"
                         f"<td><a href=\"/inquiry?invoice_number={inv['invoice_number']}&account={inv['account']}\">Dispute</a></td></tr>")
            return self.send(200, page("Invoices", f"""<h2>Invoices</h2><table><tr><th>Invoice</th><th>Account</th><th>Period</th><th>Due</th><th>Total</th><th>File</th><th></th></tr>{rows}</table>"""))
        if p == "/cases":
            rows = ""
            for c in sorted(load_cases(), key=lambda c: c.get("created_at", ""), reverse=True):
                rows += (f"<tr><td class=\"case-id\">{html.escape(str(c.get('case_id', '')))}</td><td>{html.escape(str(c.get('invoice_number', '')))}</td>"
                         f"<td>{html.escape(str(c.get('account', '')))}</td><td>${float(c.get('amount') or 0):,.2f}</td>"
                         f"<td>{html.escape(str(c.get('status') or 'Open'))}</td><td>{html.escape(str(c.get('created_at', '')))}</td></tr>")
            if not rows:
                rows = '<tr><td colspan="6" class="note">No cases yet.</td></tr>'
            return self.send(200, page("My cases", f"""<h2>My cases</h2><table id="cases"><tr><th>Case</th><th>Invoice</th><th>Account</th><th>Amount</th><th>Status</th><th>Created</th></tr>{rows}</table>
<p><a href="/inquiry">Open a new billing inquiry</a></p>"""))
        if p.startswith("/files/"):
            name = Path(p[len("/files/"):]).name
            f = FILES / name
            if not name or not f.is_file():
                return self.send(404, page("Not found", "<h2>File not found</h2>"))
            return self.send(200, f.read_bytes(), "application/pdf" if name.endswith(".pdf") else "text/plain; charset=utf-8")
        if p == "/inquiry":
            v = {k: html.escape(q.get(k, "")) for k in ("account", "invoice_number", "amount")}
            return self.send(200, page("Billing inquiry", f"""<h2>Billing inquiry</h2><p class="note">Open a dispute case on an invoice.</p>
<form method="post" action="/inquiry">
<label for="account">Account</label><input id="account" name="account" value="{v['account']}">
<label for="invoice_number">Invoice number</label><input id="invoice_number" name="invoice_number" value="{v['invoice_number']}">
<label for="amount">Disputed amount (USD)</label><input id="amount" name="amount" value="{v['amount']}">
<label for="message">Message</label><textarea id="message" name="message" rows="6"></textarea>
<button id="submit" type="submit">Submit inquiry</button></form>"""))
        return self.send(404, page("Not found", "<h2>Page not found</h2>"))

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/reset":  # demo replay: clear the synthetic cases
            with LOCK:
                CASES.write_text("[]")
            return self.json(200, {"ok": True, "synthetic": True})
        if p == "/login":
            f = self.form()
            if f.get("username") == USER and f.get("password") == PASSWORD:
                nxt = f.get("next") or "/invoices"
                if not nxt.startswith("/"):
                    nxt = "/invoices"
                return self.redirect(nxt, {"Set-Cookie": f"{COOKIE}={TOKEN}; Path=/; HttpOnly; SameSite=Lax"})
            return self.redirect("/?error=1")
        if p == "/inquiry":
            if not self.logged_in():
                return self.redirect("/?next=/inquiry")
            f = self.form()
            missing = [k for k in ("account", "invoice_number", "amount") if not f.get(k, "").strip()]
            if missing:
                return self.send(400, page("Billing inquiry", f"<h2>Missing fields</h2><p>{', '.join(missing)}</p><a href=\"/inquiry\">Back</a>"))
            try:
                amount = round(float(f["amount"].replace("$", "").replace(",", "")), 2)
            except ValueError:
                return self.send(400, page("Billing inquiry", "<h2>Amount must be a number</h2><a href=\"/inquiry\">Back</a>"))
            with LOCK:
                cases = load_cases()
                case = {
                    "case_id": new_case_id(cases), "account": f["account"].strip(),
                    "invoice_number": f["invoice_number"].strip(), "amount": amount,
                    "message": f.get("message", ""), "status": "Open",
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": True,
                }
                save_case(case)
            return self.send(200, page("Inquiry received", f"""<h2>Inquiry received</h2>
<p>Your case number is <span id="case-id" class="case">{case['case_id']}</span></p>
<table><tr><th>Account</th><td>{html.escape(case['account'])}</td></tr><tr><th>Invoice</th><td>{html.escape(case['invoice_number'])}</td></tr>
<tr><th>Amount</th><td>${amount:,.2f}</td></tr><tr><th>Status</th><td>Open</td></tr></table>
<p><a href="/cases">View all my cases</a></p>"""))
        return self.send(404, page("Not found", "<h2>Page not found</h2>"))


def main():
    port = int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Harbor Communications customer portal on :{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
