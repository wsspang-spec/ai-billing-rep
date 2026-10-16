"""The billing rep's pipeline for one invoice: read → recall dated terms → compare → decide → guard → route.

Claude (on Bedrock) reads and decides. Code enforces the controls: totals and dates, duplicates,
no "Explained" when a line contradicts the term in effect, citations must point at real evidence,
and a payment instruction only for an explained, non-duplicate invoice.
"""

import datetime as dt
import shutil
from pathlib import Path

from billingrep import checks, config, db, llm, tracing

PAYMENT_LEAD_DAYS = 3


def _prior(account: str, period_start: str, exclude_key: str) -> dict | None:
    rows = db.q(
        "SELECT * FROM invoice WHERE account = $a AND period_end < $p AND key != $k AND status != 'Duplicate' ORDER BY period_end DESC LIMIT 1",
        {"a": account, "p": period_start, "k": exclude_key},
    )
    return rows[0] if rows else None


def _evidence_ids(invoice: dict) -> set[str]:
    ids = {d["key"] for d in db.q("SELECT key FROM document")} | {t["key"] for t in db.q("SELECT key FROM term")}
    ids |= {f"{invoice['invoice_number']}-L{l['line_no']}" for l in invoice["lines"]}
    ids |= {i["key"] for i in db.q("SELECT key FROM invoice")}
    return ids


def _pay_date(due: str) -> str:
    return (dt.date.fromisoformat(due) - dt.timedelta(days=PAYMENT_LEAD_DAYS)).isoformat()


def process_invoice(pdf_path: str, source: str = "inbox") -> dict:
    path = Path(pdf_path)
    with tracing.span("process_invoice", file=path.name, source=source) as root:
        trace_id = tracing.trace_id(root)

        # 1. Read the PDF (Claude on Bedrock)
        with tracing.span("read_invoice", kind="LLM", file=path.name):
            fields = llm.extract_invoice(path)
        meta = fields.pop("_meta", {})
        number = fields["invoice_number"]

        # 2. Duplicate control (code, before anything else is written)
        existing = db.one("SELECT * FROM invoice WHERE invoice_number = $n AND account = $a", {"n": number, "a": fields["account"]})
        key = number if not existing else f"{number}-dup{len(db.q('SELECT key FROM invoice WHERE invoice_number = $n', {'n': number}))}"
        files = config.LOCAL / "files"
        files.mkdir(exist_ok=True)
        shutil.copy(path, files / f"{key}.pdf")
        base = fields | {"key": key, "file": f"/files/{key}.pdf", "source": source, "run": True, "trace_id": trace_id,
                         "read": meta, "received_at": dt.datetime.now().isoformat(timespec="seconds")}
        db.log_event(key, "Received", f"{path.name} from the {source}", "FastAPI")
        db.log_event(key, "Read", f"{len(fields['lines'])} lines, total ${fields['total']:,.2f}" + (" (cached read)" if meta.get("cached") else f" in {meta.get('seconds')}s"), "Claude on AWS Bedrock")
        if existing:
            decision = {"status": "Duplicate", "summary": f"Same invoice number as {existing['key']}, already received. No second payment instruction was created.",
                        "citations": [{"source": existing["key"], "quote": f"Invoice {number}, total ${existing['total']:,.2f}"}],
                        "findings": [], "recommended_action": "hold_for_review"}
            db.q("CREATE invoice CONTENT $i", {"i": base | {"status": "Duplicate", "decision": decision, "duplicate_of": existing["key"]}})
            db.log_event(key, "Duplicate", f"Matches {existing['key']}; payment blocked", "SurrealDB")
            return detail(key)

        db.q("CREATE invoice CONTENT $i", {"i": base | {"status": "Checking", "decision": None}})

        # 3. Recall the terms in effect for the service period (SurrealDB, time-aware)
        with tracing.span("recall_terms", kind="RETRIEVER", as_of=fields["period_start"]):
            services = sorted({l["service_id"] for l in fields["lines"] if l.get("service_id")})
            in_effect = {}
            history = {}
            for s in services:
                found = db.terms_as_of(s, fields["period_start"])
                if found:
                    in_effect[s] = found[0] | {"id": found[0]["key"]}
                history[s] = db.term_history(s)
        db.log_event(key, "Recalled", "; ".join(f"{s}: ${t['value']:,.2f} in effect on {fields['period_start']} ({t['source']})" for s, t in in_effect.items()) or "no terms", "SurrealDB")

        # 4. Compare (Daytona sandbox)
        prior = _prior(fields["account"], fields["period_start"], key)
        with tracing.span("compare_in_daytona", kind="TOOL"):
            check = checks.compare(fields, prior, in_effect)
        db.log_event(key, "Compared", f"change vs prior ${check['change_vs_prior']:+,.2f}; lines not backed by a term: {check['unsupported_lines'] or 'none'}; totals {'ok' if check['totals_ok'] else 'MISMATCH'}", check["_meta"]["ran_in"])

        # 5. Decide (Claude on Bedrock), given only the evidence
        documents = db.q("SELECT key, kind, title, date, text FROM document")
        evidence = {
            "today": config.TODAY,
            "invoice": fields | {"line_ids": [f"{number}-L{l['line_no']}" for l in fields["lines"]]},
            "prior_invoice": prior and {k: prior[k] for k in ("key", "period_start", "period_end", "total", "lines")},
            "terms_in_effect_for_period": in_effect,
            "term_history": history,
            "documents": documents,
            "comparison": {k: v for k, v in check.items() if k != "_meta"},
        }
        with tracing.span("decide", kind="LLM"):
            try:
                decision, dmeta = llm.decide(evidence)
            except Exception as e:  # noqa: BLE001
                decision, dmeta = {"status": "Needs review", "summary": f"The model could not decide ({str(e)[:80]}); a person should look.",
                                   "findings": [], "citations": [], "recommended_action": "hold_for_review"}, {"error": str(e)[:200]}

        # 6. Guards (code, not the model)
        guards = []
        valid = _evidence_ids(fields)
        cites = [c for c in decision.get("citations", []) if c.get("source") in valid]
        if len(cites) < len(decision.get("citations", [])):
            guards.append("dropped citations that point at unknown evidence")
        if not cites:
            cites = [{"source": t["key"], "quote": t["quote"]} for t in in_effect.values()]
            cites += [{"source": f"{number}-L{n}", "quote": "line has no supporting term"} for n in check["unsupported_lines"]]
            guards.append("added citations from the comparison")
        status = decision["status"]
        if status == "Explained" and (check["unsupported_lines"] or not check["totals_ok"] or not check["dates_ok"]):
            status = "Needs review"
            guards.append("model said Explained, but a line is not backed by the term in effect: overridden to Needs review")
        decision |= {"status": status, "citations": cites, "guards": guards, "model_status": decision["status"], "meta": dmeta}
        db.log_event(key, "Decided", f"{status}: {decision['summary']}", "Claude on AWS Bedrock")

        # 7. Route
        payment = None
        if status == "Explained":
            payment = db.one("CREATE payment CONTENT $p RETURN AFTER", {"p": {
                "invoice": key, "amount": fields["total"], "scheduled_on": _pay_date(fields["due_date"]), "due_on": fields["due_date"],
                "status": "Scheduled (simulated)", "simulated": True}})
            db.log_event(key, "Routed", f"Payment of ${fields['total']:,.2f} scheduled {payment['scheduled_on']} (simulated queue)", "policy")
        elif status == "Needs clarification":
            disputed = check["unsupported_amount"]
            db.q("CREATE action CONTENT $a", {"a": {
                "key": f"inq-{key}", "invoice": key, "kind": "inquiry", "status": "Proposed",
                "amount": disputed, "undisputed": round(fields["total"] - disputed, 2),
                "message": decision.get("inquiry_message") or f"Please explain line(s) {check['unsupported_lines']} on invoice {number}; our contract lists no such charge.",
            }})
            db.log_event(key, "Routed", f"Inquiry about ${disputed:,.2f} proposed; waiting for your approval", "policy")
        else:
            db.log_event(key, "Routed", "Held for review; no payment, no outside action", "policy")

        db.q("UPDATE invoice MERGE $m WHERE key = $k", {"k": key, "m": {
            "status": status, "decision": decision, "checks": check, "prior_key": prior and prior["key"],
            "delta": check["change_vs_prior"], "terms_used": list(in_effect.values()), "term_history": history}})
    tracing.flush()
    return detail(key) | {"payment": payment}


def detail(key: str) -> dict | None:
    inv = db.one("SELECT * FROM invoice WHERE key = $k", {"k": key})
    if not inv:
        return None
    inv["events"] = db.q("SELECT step, detail, sponsor, at FROM event WHERE invoice = $k ORDER BY at ASC", {"k": key})
    inv["payment"] = db.one("SELECT * FROM payment WHERE invoice = $k", {"k": key})
    inv["action"] = db.one("SELECT * FROM action WHERE invoice = $k", {"k": key})
    inv["documents"] = db.q("SELECT key, kind, title, date, text FROM document")
    inv["id"] = key
    return inv
