"""Human-approved actions. The approval gate is code: no inquiry leaves without an approval tied to it,
and no inquiry is marked Submitted without a confirmed case on the portal."""

import datetime as dt

from billingrep import config, db, tracing


class ApprovalRequired(Exception):
    pass


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def approve(invoice_id: str, approver: str) -> dict:
    action = db.one("SELECT * FROM action WHERE invoice = $k", {"k": invoice_id})
    if not action:
        raise ValueError("nothing to approve on this invoice")
    if action["status"] == "Proposed":
        db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": invoice_id, "m": {"status": "Approved", "approved_by": approver, "approved_at": _now()}})
        db.q("UPDATE invoice SET status = 'Approved' WHERE key = $k", {"k": invoice_id})
        inv = db.one("SELECT * FROM invoice WHERE key = $k", {"k": invoice_id})
        if action.get("undisputed", 0) > 0 and not db.one("SELECT * FROM payment WHERE invoice = $k", {"k": invoice_id}):
            from billingrep.agent import _pay_date

            db.q("CREATE payment CONTENT $p", {"p": {"invoice": invoice_id, "amount": action["undisputed"], "scheduled_on": _pay_date(inv["due_date"]),
                                                    "due_on": inv["due_date"], "status": "Scheduled (simulated), undisputed part", "simulated": True}})
        db.log_event(invoice_id, "Approved", f"{approver} approved the inquiry about ${action['amount']:,.2f}", "you")
    return db.one("SELECT * FROM action WHERE invoice = $k", {"k": invoice_id})


def require_approval(invoice_id: str) -> dict:
    """The gate, checked before anything starts."""
    action = db.one("SELECT * FROM action WHERE invoice = $k", {"k": invoice_id})
    if not action or action["status"] not in ("Approved", "Failed", "Submitted", "Sending"):
        db.log_event(invoice_id, "Blocked", "Inquiry submission refused: no approval recorded", "policy")
        raise ApprovalRequired("An approval tied to this inquiry is required before anything is sent.")
    return action


def submit_inquiry(invoice_id: str) -> dict:
    action = db.one("SELECT * FROM action WHERE invoice = $k", {"k": invoice_id})
    if not action or action["status"] not in ("Approved", "Failed", "Submitted", "Sending"):
        db.log_event(invoice_id, "Blocked", "Inquiry submission refused: no approval recorded", "policy")
        raise ApprovalRequired("An approval tied to this inquiry is required before anything is sent.")
    if action["status"] == "Submitted":
        return action
    db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": invoice_id, "m": {"status": "Sending", "live_view_url": None}})
    inv = db.one("SELECT * FROM invoice WHERE key = $k", {"k": invoice_id})
    with tracing.span("submit_inquiry", kind="TOOL", invoice=invoice_id):
        voice = None
        try:
            if not config.VOICE:
                raise RuntimeError("voice off")
            from billingrep import voice as voice_mod

            voice = voice_mod.generate_message(
                f"Hello, this is Atlas Demo Retail's billing team about account {inv['account']}. "
                f"Invoice {inv['invoice_number']} has a new charge of {action['amount']:.0f} dollars that we can't match to our contract. "
                f"We've opened inquiry on your portal. Could you explain it, or credit it? Thank you.",
                f"inquiry-{invoice_id}",
            )
            db.log_event(invoice_id, "Voice message", "Generated, not delivered", "ElevenLabs")
        except Exception as e:  # noqa: BLE001
            voice = None if str(e) == "voice off" else {"error": str(e)[:200]}
        try:
            from billingrep import anchor_actions, portal_deploy

            def live(url: str, session_id: str) -> None:
                db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": invoice_id, "m": {"live_view_url": url, "session_id": session_id}})
                db.log_event(invoice_id, "Browser opened", "Anchor started a cloud browser and is filling the vendor portal", "Anchor Browser")

            result = anchor_actions.submit_inquiry(portal_deploy.portal_url(), inv["account"], inv["invoice_number"], action["amount"], action["message"], on_session=live)
        except Exception as e:  # noqa: BLE001
            result = {"status": "failed", "error": str(e)[:300]}
    if result.get("status") == "submitted" and result.get("case_id"):
        db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": invoice_id, "m": {"status": "Submitted", "case_id": result["case_id"], "portal": result, "voice": voice, "submitted_at": _now()}})
        db.q("UPDATE invoice SET status = 'Awaiting vendor response' WHERE key = $k", {"k": invoice_id})
        db.log_event(invoice_id, "Submitted", f"Portal case {result['case_id']} confirmed" + (" (already existed, not resent)" if result.get("existing") else ""), "Anchor Browser")
    else:
        db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": invoice_id, "m": {"status": "Failed", "portal": result, "voice": voice}})
        db.log_event(invoice_id, "Not submitted", f"No portal confirmation: {result.get('error', 'unknown')}", "Anchor Browser")
    tracing.flush()
    return db.one("SELECT * FROM action WHERE invoice = $k", {"k": invoice_id})


def cfo_summary() -> dict:
    run = db.q("SELECT * FROM invoice WHERE run = true AND status != 'Duplicate'")
    billed = round(sum(i["total"] for i in run), 2)
    review_states = ("Needs review", "Needs clarification", "Approved", "Awaiting vendor response")
    exposure = round(sum((i.get("checks") or {}).get("unsupported_amount", 0) for i in run if i["status"] in review_states), 2)
    disputed = round(sum(a["amount"] for a in db.q("SELECT * FROM action WHERE status = 'Submitted'")), 2)
    payments = db.q("SELECT * FROM payment")
    credits = db.q("SELECT * FROM credit")
    promised = round(sum(c["amount"] for c in credits if c["state"] == "promised"), 2)
    applied = round(sum(c["amount"] for c in credits if c["state"] == "applied"), 2)
    changes = []
    for t in db.q("SELECT * FROM term WHERE valid_from > '2026-01-01' ORDER BY valid_from"):
        old = db.one("SELECT * FROM term WHERE superseded_by = $k", {"k": t["key"]})
        if old:
            changes.append({"service": t["service"], "from": old["value"], "to": t["value"], "monthly_change": round(t["value"] - old["value"], 2),
                            "effective": t["valid_from"], "source": t["source"], "next_12_months": round(12 * (t["value"] - old["value"]), 2)})
    return {
        "billed_this_month": billed,
        "scheduled_payments_simulated": round(sum(p["amount"] for p in payments), 2),
        "recurring_changes": changes,
        "billed_exposure_under_review": exposure,
        "disputed": disputed,
        "credits": {"promised": promised, "applied": applied, "items": credits},
        "realized_savings": applied,
        "note": "Savings count only credits that posted on an invoice. Promised credits and open disputes are not savings.",
    }
