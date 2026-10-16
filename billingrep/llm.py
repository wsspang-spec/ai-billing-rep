"""Claude on AWS Bedrock: reads invoice PDFs into structured lines, then decides what each change means."""

import base64
import hashlib
import json
import time
from pathlib import Path

from anthropic import AnthropicBedrock

from billingrep import config

_client = None
CACHE = config.LOCAL / "parse_cache"
CACHE.mkdir(exist_ok=True)


def client() -> AnthropicBedrock:
    global _client
    if _client is None:
        _client = AnthropicBedrock(aws_region=config.REGION)
    return _client


INVOICE_TOOL = {
    "name": "record_invoice",
    "description": "Record the fields read from one telecom invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_invoice": {"type": "boolean", "description": "false if this document is not a telecom/utility invoice"},
            "not_invoice_reason": {"type": "string", "description": "If is_invoice is false: what the document is, in a few words"},
            "vendor": {"type": "string"},
            "account": {"type": "string", "description": "Account id, e.g. ACCT-A100"},
            "invoice_number": {"type": "string"},
            "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
            "period_start": {"type": "string", "description": "YYYY-MM-DD"},
            "period_end": {"type": "string", "description": "YYYY-MM-DD"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            "total": {"type": "number"},
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line_no": {"type": "integer"},
                        "description": {"type": "string"},
                        "service_id": {"type": ["string", "null"], "description": "Service code like DEMO-001 if the line names one, else null"},
                        "kind": {"type": "string", "enum": ["service", "tax", "fee", "surcharge", "credit", "other"]},
                        "amount": {"type": "number"},
                    },
                    "required": ["line_no", "description", "service_id", "kind", "amount"],
                },
            },
        },
        "required": ["is_invoice"],
    },
}


class NotAnInvoice(Exception):
    pass


DECISION_TOOL = {
    "name": "record_decision",
    "description": "Record your decision about this invoice, with the evidence for it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["Explained", "Needs review", "Needs clarification"]},
            "summary": {"type": "string", "description": "One or two plain sentences for the AP specialist."},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line_no": {"type": "integer"},
                        "finding": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}, "description": "Evidence ids from the list given"},
                    },
                    "required": ["line_no", "finding", "sources"],
                },
            },
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"source": {"type": "string"}, "quote": {"type": "string"}},
                    "required": ["source", "quote"],
                },
            },
            "recommended_action": {"type": "string", "enum": ["schedule_payment", "hold_for_review", "request_clarification"]},
            "inquiry_message": {"type": "string", "description": "If asking the vendor: a short, polite, factual question citing the line and the contract. Never accuse."},
        },
        "required": ["status", "summary", "findings", "citations", "recommended_action"],
    },
}


def _tool_input(resp, name: str) -> dict | None:
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == name:
            return dict(block.input)
    for block in resp.content:  # fallback: JSON in text
        text = getattr(block, "text", "")
        if text and "{" in text:
            try:
                return json.loads(text[text.index("{"): text.rindex("}") + 1])
            except ValueError:
                pass
    return None


def extract_invoice(path: Path, use_cache: bool = True) -> dict:
    """Claude reads the PDF. Cached by file hash so a demo replay is instant (marked cached)."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    cached = CACHE / f"{sha}.json"
    if use_cache and cached.exists():
        out = json.loads(cached.read_text())
        out["_meta"] |= {"cached": True}
        return out
    started = time.time()
    content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(raw).decode()}},
        {"type": "text", "text": "Read this document. If it is an invoice, call record_invoice with is_invoice=true and every field and every charge line (the total is the amount due; previous balance and payments are not charge lines). Use YYYY-MM-DD dates and plain numbers. If it is not an invoice, call record_invoice with is_invoice=false and say what it is."},
    ]
    resp = client().messages.create(
        model=config.MODEL,
        max_tokens=4000,
        tools=[INVOICE_TOOL],
        system="You extract telecom invoice data exactly as printed. Always answer by calling record_invoice.",
        messages=[{"role": "user", "content": content}],
    )
    data = _tool_input(resp, "record_invoice")
    if not data:
        raise NotAnInvoice("Claude found no invoice fields in it")
    if data.get("is_invoice") is False or not data.get("lines") or "total" not in data:
        raise NotAnInvoice(data.get("not_invoice_reason") or "no invoice number, total or charge lines found")
    data["_meta"] = {"model": config.MODEL, "seconds": round(time.time() - started, 1), "sha": sha, "cached": False, "via": "Claude on AWS Bedrock"}
    cached.write_text(json.dumps(data))
    return data


def decide(evidence: dict) -> tuple[dict, dict]:
    """Claude weighs the evidence and proposes a status + action. Code checks it afterwards."""
    started = time.time()
    system = (
        "You are a careful billing analyst for a company's accounts-payable team. Decide what a telecom invoice change means "
        "using ONLY the evidence given. Rules: a contract term or amendment applies only from its valid_from date; compare each "
        "line with the term in effect for the invoice's service period (comparison.lines[].verdict tells you which). "
        "'Needs review': a service is billed at a price that differs from the term in effect for that period (verdict differs_from_term), "
        "e.g. a new price billed before its amendment takes effect; hold it for a person. "
        "'Needs clarification': a charge that no term or record covers (verdict no_term), e.g. a new surcharge; ask the vendor what it is. "
        "Contract clauses about other charges support the question; they do not prove overbilling, and never call anything fraud. "
        "'Explained': every line matches the term in effect. Cite only the 2-3 pieces of evidence that matter, with ids exactly as given "
        "(document ids, term ids, or line ids like H-OCT-202-L2). Always answer by calling record_decision."
    )
    resp = client().messages.create(
        model=config.MODEL,
        max_tokens=4000,
        tools=[DECISION_TOOL],
        system=system,
        messages=[{"role": "user", "content": "Evidence (JSON):\n" + json.dumps(evidence, indent=1, default=str)}],
    )
    data = _tool_input(resp, "record_decision")
    if not data:
        raise RuntimeError("Claude did not return a decision")
    return data, {"model": config.MODEL, "seconds": round(time.time() - started, 1), "via": "Claude on AWS Bedrock"}
