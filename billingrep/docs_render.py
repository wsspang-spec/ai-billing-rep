"""Render a seed document row as a signed business document (full HTML page)."""

from __future__ import annotations

import re
from datetime import date as _date
from html import escape

CUSTOMER = "Atlas Retail"
NORTHSTAR = "Northstar Telecom"
HARBOR = "Harbor Communications"

_VENDOR_BY_KEY = {
    "contract-a": NORTHSTAR,
    "amendment-a": NORTHSTAR,
    "contract-c": NORTHSTAR,
    "contract-b": HARBOR,
    "credit-promise-b": HARBOR,
}

_SIGNERS = {
    NORTHSTAR: ("Daniel Reyes", "VP, Enterprise Accounts, Northstar Telecom"),
    HARBOR: ("Priya Natarajan", "Director, Commercial Sales, Harbor Communications"),
}
_CUSTOMER_SIGNER = ("Margaret Chen", "Head of Procurement, Atlas Retail")

_BANNED = re.compile(r"\b(?:demo|synthetic)\b\s*", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
_STOP = {"the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "at", "by", "on", "per"}


def _clean(text: str | None) -> str:
    return _BANNED.sub("", str(text or "")).strip()


def _fmt_date(value) -> str:
    if not value:
        return ""
    s = str(value)[:10]
    try:
        d = _date.fromisoformat(s)
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except ValueError:
        return _clean(value)


def _letter(key: str) -> str:
    m = re.search(r"-([a-z])$", key or "", re.IGNORECASE)
    return m.group(1).upper() if m else "A"


def _vendor(doc: dict) -> str:
    key = str(doc.get("key") or doc.get("id") or "")
    if key in _VENDOR_BY_KEY:
        return _VENDOR_BY_KEY[key]
    return HARBOR if _letter(key) == "B" else NORTHSTAR


def _sentences(text: str) -> list[str]:
    # Split on sentence ends; keep decimals like 450.00 intact.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    return [p for p in parts if p]


def _best_sentence(sentences: list[str], highlight: str) -> int:
    h = highlight.strip().lower()
    if not h or not sentences:
        return -1
    for i, s in enumerate(sentences):
        if h in s.lower():
            return i
    hw = {w for w in _WORD.findall(h) if w not in _STOP}
    best, best_score = -1, 0
    for i, s in enumerate(sentences):
        score = len(hw & set(_WORD.findall(s.lower())))
        if score > best_score:
            best, best_score = i, score
    return best


def _text_html(text: str, highlight: str) -> tuple[str, bool]:
    sents = _sentences(text)
    idx = _best_sentence(sents, highlight)
    out = []
    for i, s in enumerate(sents):
        out.append(f'<mark id="cited">{escape(s)}</mark>' if i == idx else escape(s))
    return " ".join(out), idx >= 0


def _sig_block(left: tuple[str, str, str], right: tuple[str, str, str], signed_on: str) -> str:
    def one(party: str, name: str, title: str) -> str:
        return (
            '<div class="sig">'
            f'<div class="sig-party">{escape(party)}</div>'
            f'<div class="sig-script">{escape(name)}</div>'
            '<div class="sig-line"></div>'
            f'<div class="sig-meta"><strong>{escape(name)}</strong><br>{escape(title)}'
            f"<br>Date: {escape(signed_on)}</div>"
            "</div>"
        )

    return (
        '<section class="signatures"><h3>Signatures</h3>'
        "<p class=\"small\">IN WITNESS WHEREOF, the parties have executed this document by their "
        "duly authorized representatives.</p>"
        f'<div class="sig-row">{one(*left)}{one(*right)}</div></section>'
    )


def _contract(doc: dict, highlight: str) -> tuple[str, bool]:
    vendor = _vendor(doc)
    letter = _letter(str(doc.get("key") or doc.get("id") or ""))
    number = f"MSA-2026-{letter}"
    eff = _fmt_date(doc.get("valid_from") or doc.get("date"))
    body, hit = _text_html(_clean(doc.get("text")), highlight)
    svc = escape(_clean(doc.get("service_id")))
    vname, vtitle = _SIGNERS[vendor]
    cname, ctitle = _CUSTOMER_SIGNER
    html = f"""
<header class="doc-head">
  <div class="eyebrow">Agreement No. {escape(number)}</div>
  <h1>Master Services Agreement</h1>
  <div class="sub">Service {svc} &middot; Effective {escape(eff)}</div>
</header>
<section class="parties">
  <div><div class="label">Customer</div><div class="party">{escape(CUSTOMER)}</div>
    <div class="small">Accounts Payable &middot; ap@atlasretail.example</div></div>
  <div><div class="label">Provider</div><div class="party">{escape(vendor)}</div>
    <div class="small">Enterprise Services Division</div></div>
</section>
<p>This Master Services Agreement (the &ldquo;Agreement&rdquo;) is entered into by and between
{escape(CUSTOMER)} (&ldquo;Customer&rdquo;) and {escape(vendor)} (&ldquo;Provider&rdquo;).</p>
<ol class="sections">
  <li><h2>Services</h2><p>Provider shall deliver service {svc} to Customer as described in this
  Agreement, on a recurring monthly basis.</p></li>
  <li><h2>Pricing</h2><p>{body}</p></li>
  <li><h2>Term</h2><p>This Agreement is effective {escape(eff)} and continues month to month until
  terminated by either party on 30 days&rsquo; written notice.</p></li>
  <li><h2>Changes</h2><p>Prices change only by a signed amendment.</p></li>
  <li><h2>Disputes</h2><p>Either party may dispute a charge within 30 days of the invoice date.</p></li>
</ol>
{_sig_block((vendor, vname, vtitle), (CUSTOMER, cname, ctitle), eff)}
"""
    return html, hit


def _amendment(doc: dict, highlight: str) -> tuple[str, bool]:
    vendor = _vendor(doc)
    letter = _letter(str(doc.get("key") or doc.get("id") or ""))
    number = f"MSA-2026-{letter}"
    eff = _fmt_date(doc.get("valid_from") or doc.get("date"))
    signed = _fmt_date(doc.get("date") or doc.get("valid_from"))
    body, hit = _text_html(_clean(doc.get("text")), highlight)
    svc = escape(_clean(doc.get("service_id")))
    vname, vtitle = _SIGNERS[vendor]
    cname, ctitle = _CUSTOMER_SIGNER
    html = f"""
<header class="doc-head">
  <div class="eyebrow">Amendment &middot; {escape(number)}</div>
  <h1>Amendment No. 1 to Master Services Agreement {escape(number)}</h1>
  <div class="sub">Service {svc} &middot; Effective {escape(eff)}</div>
</header>
<section class="parties">
  <div><div class="label">Customer</div><div class="party">{escape(CUSTOMER)}</div></div>
  <div><div class="label">Provider</div><div class="party">{escape(vendor)}</div></div>
</section>
<h2 class="plain">Recitals</h2>
<p><strong>WHEREAS</strong>, {escape(CUSTOMER)} and {escape(vendor)} are parties to Master
Services Agreement {escape(number)} (the &ldquo;Agreement&rdquo;);</p>
<p><strong>WHEREAS</strong>, Section 4 of the Agreement provides that prices change only by a
signed amendment; and</p>
<p><strong>WHEREAS</strong>, the parties wish to amend the pricing of service {svc};</p>
<p><strong>NOW, THEREFORE</strong>, the parties agree as follows:</p>
<ol class="sections">
  <li><h2>Change</h2><p>{body}</p></li>
  <li><h2>Effective Date</h2><p>This Amendment takes effect on {escape(eff)}.</p></li>
  <li><h2>No Other Changes</h2><p>Except as set out above, the Agreement remains in full force
  and effect.</p></li>
</ol>
{_sig_block((vendor, vname, vtitle), (CUSTOMER, cname, ctitle), signed)}
"""
    return html, hit


def _message(doc: dict, highlight: str) -> tuple[str, bool]:
    vendor = _vendor(doc)
    sent = _fmt_date(doc.get("date"))
    body, hit = _text_html(_clean(doc.get("text")), highlight)
    domain = "harborcomms.example" if vendor == HARBOR else "northstartelecom.example"
    sender_name = "Jordan Whitaker"
    html = f"""
<header class="mail-head">
  <div class="mail-subject">Goodwill credit request for ACCT-202</div>
  <table class="mail-meta">
    <tr><th>From</th><td>{escape(sender_name)}, Account Manager, {escape(vendor)}
      &lt;j.whitaker@{escape(domain)}&gt;</td></tr>
    <tr><th>To</th><td>ap@atlasretail.example</td></tr>
    <tr><th>Date</th><td>{escape(sent)}</td></tr>
    <tr><th>Subject</th><td>Goodwill credit request for ACCT-202</td></tr>
  </table>
</header>
<div class="mail-body">
  <p>Hello Atlas Retail Accounts Payable team,</p>
  <p>{body}</p>
  <p>Best regards,<br>{escape(sender_name)}<br>Account Manager, {escape(vendor)}</p>
</div>
"""
    return html, hit


_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #0B0B0C; color: #E8E8EA; }
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  padding: 0 16px 64px; }
.bar { max-width: 760px; margin: 0 auto; display: flex; justify-content: space-between;
  align-items: center; padding: 14px 2px; font-size: 13px; }
.bar a { color: #C9C9CF; text-decoration: none; }
.bar a:hover { color: #fff; }
.cited-label { background: rgba(255, 214, 102, .14); color: #FFD666; border: 1px solid rgba(255,214,102,.35);
  padding: 3px 10px; border-radius: 999px; font-size: 12px; }
.paper { max-width: 760px; margin: 0 auto; background: #fff; color: #1C1C1E; border-radius: 4px;
  padding: 56px 64px; box-shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 40px rgba(0,0,0,.45);
  font-family: Georgia, "New York", "Times New Roman", serif; font-size: 16px; line-height: 1.65; }
.paper h1, .paper h2, .paper h3, .eyebrow, .sub, .label, .party, .sig-party, .sig-meta,
.mail-head, .small { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif; }
.doc-head { border-bottom: 2px solid #1C1C1E; padding-bottom: 18px; margin-bottom: 24px; }
.eyebrow { font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #6B6B70; }
h1 { font-size: 26px; line-height: 1.25; margin: 6px 0 6px; font-weight: 700; }
.sub { font-size: 13px; color: #6B6B70; }
.parties { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; background: #F6F6F4;
  border: 1px solid #E6E6E2; border-radius: 4px; padding: 14px 18px; margin-bottom: 20px; }
.label { font-size: 10px; letter-spacing: .14em; text-transform: uppercase; color: #8A8A8F; }
.party { font-weight: 600; font-size: 15px; }
.small { font-size: 12px; color: #6B6B70; }
ol.sections { padding-left: 1.4em; margin: 18px 0 0; }
ol.sections > li { margin-bottom: 14px; }
ol.sections > li::marker { font-weight: 700; font-family: -apple-system, sans-serif; }
ol.sections h2, h2.plain { font-size: 15px; margin: 0 0 4px; font-weight: 700; }
h2.plain { margin-top: 8px; }
p { margin: 0 0 10px; }
mark#cited { background: #FFF3B0; color: inherit; padding: 1px 2px; border-radius: 2px;
  box-shadow: 0 0 0 2px #FFF3B0; }
mark#cited.pulse { animation: pulse 1.6s ease-out 1; }
@keyframes pulse { 0% { box-shadow: 0 0 0 2px #FFF3B0, 0 0 0 0 rgba(255,196,0,.7); }
  60% { box-shadow: 0 0 0 2px #FFF3B0, 0 0 0 14px rgba(255,196,0,0); }
  100% { box-shadow: 0 0 0 2px #FFF3B0, 0 0 0 0 rgba(255,196,0,0); } }
.signatures { margin-top: 36px; border-top: 1px solid #E0E0DC; padding-top: 18px; }
.signatures h3 { font-size: 13px; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 6px; }
.sig-row { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; margin-top: 18px; }
.sig-party { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #6B6B70; }
.sig-script { font-family: "Snell Roundhand", "Brush Script MT", "Segoe Script", cursive;
  font-size: 28px; color: #1F3A8A; margin: 10px 0 -4px; }
.sig-line { border-bottom: 1px solid #1C1C1E; margin-bottom: 6px; }
.sig-meta { font-size: 12px; color: #3A3A3C; line-height: 1.5; }
.mail-head { border-bottom: 1px solid #E0E0DC; padding-bottom: 14px; margin-bottom: 20px; }
.mail-subject { font-size: 22px; font-weight: 700; margin-bottom: 12px; }
.mail-meta { border-collapse: collapse; font-size: 13px; }
.mail-meta th { text-align: left; color: #8A8A8F; font-weight: 500; padding: 2px 16px 2px 0; vertical-align: top; }
.mail-meta td { color: #1C1C1E; padding: 2px 0; }
@media (max-width: 600px) {
  .paper { padding: 32px 22px; }
  .parties, .sig-row { grid-template-columns: 1fr; }
  h1 { font-size: 21px; }
}
"""

_SCRIPT = """
<script>
(function(){
  var m = document.getElementById('cited');
  if (!m) return;
  setTimeout(function(){
    m.scrollIntoView({behavior: 'smooth', block: 'center'});
    setTimeout(function(){ m.classList.add('pulse'); }, 350);
  }, 120);
})();
</script>
"""


def render_document(doc: dict, highlight: str = "") -> str:
    """Return a full HTML page showing `doc` as a signed business document."""
    doc = dict(doc or {})
    if not doc.get("key") and doc.get("id"):
        doc["key"] = str(doc["id"]).split(":")[-1].strip("`⟨⟩")
    kind = str(doc.get("kind") or "contract")
    highlight = highlight or ""
    if kind == "approved_amendment":
        inner, hit = _amendment(doc, highlight)
        page_title = "Amendment No. 1"
    elif kind == "vendor_message":
        inner, hit = _message(doc, highlight)
        page_title = "Goodwill credit request for ACCT-202"
    else:
        inner, hit = _contract(doc, highlight)
        page_title = f"Master Services Agreement MSA-2026-{_letter(str(doc.get('key') or ''))}"
    label = '<span class="cited-label">Cited by the agent</span>' if hit else "<span></span>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(page_title)}</title>
<style>{_CSS}</style>
</head>
<body>
<nav class="bar"><a href="javascript:history.back()">&lsaquo; Back to the bill</a>{label}</nav>
<article class="paper">
{inner}
</article>
{_SCRIPT if hit else ""}
</body>
</html>
"""
