"""File a billing inquiry on the SYNTHETIC carrier portal with an Anchor cloud browser.

submit_inquiry() is idempotent: it checks the portal's /api/cases first and never files a
second case for the same invoice. It only reports "submitted" once the case is confirmed
through the API. The Anchor session is always closed.

A session's cdp_url carries the API key: it is never returned, logged or put in errors.
"""

import os
import re

import httpx

from billingrep import config  # noqa: F401  (loads .env)

MAX_MINUTES = 5
IDLE_MINUTES = 1


def _scrub(text: str) -> str:
    return re.sub(r"(apiKey=|api_key=|token=)[^&\s'\"]+", r"\1***", text, flags=re.I)


def _existing_case(portal_url: str, invoice_number: str) -> dict | None:
    r = httpx.get(f"{portal_url}/api/cases", params={"invoice_number": invoice_number}, timeout=15)
    r.raise_for_status()
    cases = r.json().get("cases", [])
    return cases[0] if cases else None


def submit_inquiry(portal_url: str, account: str, invoice_number: str, amount: float, message: str) -> dict:
    portal_url = portal_url.rstrip("/")
    try:
        found = _existing_case(portal_url, invoice_number)
    except Exception as exc:
        return {"status": "failed", "error": _scrub(f"portal API check failed: {type(exc).__name__}: {exc}")}
    if found:
        return {"status": "submitted", "case_id": found["case_id"], "existing": True, "portal_url": portal_url}

    key = os.environ.get("ANCHORBROWSER_API_KEY")
    if not key:
        return {"status": "failed", "error": "ANCHORBROWSER_API_KEY is not set"}

    from anchorbrowser import Anchorbrowser
    from playwright.sync_api import sync_playwright

    client = Anchorbrowser(api_key=key)
    session_id = live_view_url = None
    try:
        data = client.sessions.create_session(
            session={"timeout": {"max_duration": MAX_MINUTES, "idle_timeout": IDLE_MINUTES}}
        ).data
        if data is None or not data.id or not data.cdp_url:
            return {"status": "failed", "error": "Anchor returned no session"}
        session_id, live_view_url = data.id, data.live_view_url

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(data.cdp_url, timeout=60_000)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                # Daytona shows browsers a "Preview - Warning" interstitial unless this header is sent.
                page.set_extra_http_headers({"X-Daytona-Skip-Preview-Warning": "true"})
                page.set_default_timeout(30_000)
                page.goto(f"{portal_url}/", wait_until="domcontentloaded")
                page.fill("#username", "demo")
                page.fill("#password", "demo")
                page.click("#login")
                page.wait_for_url(re.compile(r"/invoices"))
                page.goto(f"{portal_url}/inquiry", wait_until="domcontentloaded")
                page.fill("#account", account)
                page.fill("#invoice_number", invoice_number)
                page.fill("#amount", f"{float(amount):.2f}")
                page.fill("#message", message)
                page.click("#submit")
                case_id = page.locator("#case-id").inner_text(timeout=30_000).strip()
            finally:
                browser.close()

        if not re.fullmatch(r"DEMO-CASE-\d{3,}", case_id or ""):
            return {"status": "failed", "error": f"unexpected confirmation: {case_id!r}", "session_id": session_id}
        confirmed = _existing_case(portal_url, invoice_number)
        if not confirmed or confirmed.get("case_id") != case_id:
            return {"status": "failed", "error": f"case {case_id} not found via portal API", "session_id": session_id}
        return {"status": "submitted", "case_id": case_id, "existing": False, "portal_url": portal_url,
                "session_id": session_id, "live_view_url": live_view_url}
    except Exception as exc:
        return {"status": "failed", "error": _scrub(f"{type(exc).__name__}: {exc}"), "session_id": session_id}
    finally:
        if session_id:
            try:
                client.sessions.delete_session(session_id)
            except Exception:
                pass


if __name__ == "__main__":
    import json
    import sys

    from billingrep.portal_deploy import portal_url

    inv = sys.argv[1] if len(sys.argv) > 1 else "H-OCT-202"
    print(json.dumps(submit_inquiry(
        portal_url(), "ACCT-B200", inv, 120.0,
        "SYNTHETIC DEMO: disputing line 2 'Network access recovery surcharge' ($120.00); "
        "contract C-1 section 4 allows no other charges.",
    ), indent=1))
