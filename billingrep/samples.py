"""Fresh demo invoices for live drag-and-drop: each call renders a NEW PDF with a new invoice number.

Rotates by counter: %3==1 Explained (ACCT-303), %3==2 Needs clarification (unclassified fee),
%3==0 Needs review (ACCT-101 September billed at the post-amendment rate).
"""

import importlib.util
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
OUT = ROOT / "local-data" / "samples"
COUNTER = OUT / "counter.json"
START = 304
VENDOR = "Northstar Demo Telecom (synthetic)"
_lock = threading.Lock()
_ms = None


def _make_samples():
    global _ms
    if _ms is None:
        spec = importlib.util.spec_from_file_location("make_samples", ROOT / "scripts" / "make_samples.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ms = mod
    return _ms


def _read_counter() -> int:
    try:
        return int(json.loads(COUNTER.read_text())["counter"])
    except Exception:
        return START


def reset_counter(value: int = START) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(json.dumps({"counter": value}))


def _line(num: str, no: int, desc: str, svc, kind: str, ctype: str, amount: float) -> dict:
    return {"line_no": no, "line_id": f"{num}-L{no}", "description": desc, "service_id": svc,
            "kind": kind, "charge_type": ctype, "amount": amount}


def _invoice(n: int) -> dict:
    variant = n % 3
    if variant == 0:  # ACCT-101 September at $525 (before Amendment A's Oct 1 effective date) -> Needs review
        num = f"N-SEP-{n}"
        account, start, end, due = "ACCT-101", "2026-09-01", "2026-09-30", "2026-09-30"
        lines = [_line(num, 1, "Monthly connectivity service", "SVC-A", "service", "recurring", 525.0)]
    else:
        num = f"N-OCT-{n}"
        account, start, end, due = "ACCT-303", "2026-10-01", "2026-10-31", "2026-10-30"
        lines = [_line(num, 1, "Monthly connectivity service", "SVC-C", "service", "recurring", 300.0)]
        if variant == 2:  # fee no contract term covers -> Needs clarification
            lines.append(_line(num, 2, "Regulatory cost recovery fee", None, "other", "unclassified", 18.40))
    return {
        "invoice_number": num, "account": account, "vendor": VENDOR,
        "period_start": start, "period_end": end, "invoice_date": start, "due_date": due,
        "total": round(sum(ln["amount"] for ln in lines), 2), "lines": lines, "file": f"{num}.pdf",
    }


def next_sample() -> Path:
    """Render the next demo invoice PDF into local-data/samples/ and return its path."""
    with _lock:
        OUT.mkdir(parents=True, exist_ok=True)
        n = _read_counter()
        inv = _invoice(n)
        path = OUT / inv["file"]
        seed = json.loads(SEED.read_text())
        _make_samples().render_pdf(inv, seed, path)
        reset_counter(n + 1)
        return path
