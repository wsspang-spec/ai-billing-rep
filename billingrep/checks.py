"""Daytona: the deterministic invoice comparison runs in a sandbox, not on the laptop.

The same script runs locally only if Daytona is unreachable, and the result says where it ran.
"""

import atexit
import json
import subprocess
import sys
import threading
import time

from billingrep import config

COMPARE = r'''
import atexit
import json
data = json.loads(INPUT)
inv, prior, terms = data["invoice"], data.get("prior") or {"lines": [], "total": 0}, data["terms"]
prior_by_service = {l.get("service_id"): l for l in prior["lines"] if l.get("service_id") and l.get("kind", "service") == "service"}
prior_by_desc = {l["description"].lower(): l for l in prior["lines"]}
rows, unsupported, new_lines = [], [], []
for l in inv["lines"]:
    sid = l.get("service_id")
    recurring = l.get("kind", "service") == "service"
    term = terms.get(sid) if sid and recurring else None  # a price term covers the recurring service line only
    p = prior_by_service.get(sid) if sid and recurring else prior_by_desc.get(l["description"].lower())
    expected = term["value"] if term else None
    if term is None:
        verdict = "no_term"
    elif abs(l["amount"] - expected) < 0.005:
        verdict = "matches_term"
    else:
        verdict = "differs_from_term"
    row = {"line_no": l["line_no"], "description": l["description"], "amount": round(l["amount"], 2),
           "expected": expected, "term_id": term["id"] if term else None,
           "prior_amount": round(p["amount"], 2) if p else None,
           "change_vs_prior": round(l["amount"] - p["amount"], 2) if p else round(l["amount"], 2),
           "new_line": p is None, "verdict": verdict}
    rows.append(row)
    if verdict != "matches_term":
        unsupported.append(row)
    if p is None:
        new_lines.append(l["line_no"])
sum_lines = round(sum(l["amount"] for l in inv["lines"]), 2)
out = {"lines": rows, "sum_of_lines": sum_lines, "billed_total": inv["total"],
       "totals_ok": abs(sum_lines - inv["total"]) < 0.005,
       "dates_ok": inv["period_start"] <= inv["period_end"] and inv["invoice_date"] <= inv["due_date"],
       "prior_total": prior["total"], "change_vs_prior": round(inv["total"] - prior["total"], 2),
       "unsupported_amount": round(sum(r["amount"] - (r["expected"] or 0) for r in unsupported), 2),
       "unsupported_lines": [r["line_no"] for r in unsupported], "new_lines": new_lines}
print("RESULT:" + json.dumps(out))
'''

_sandbox = None
_lock = threading.Lock()


def _get_sandbox():
    global _sandbox
    with _lock:
        if _sandbox is None:
            from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig
            import os

            d = Daytona(DaytonaConfig(api_key=os.environ["DAYTONA_API_KEY"], api_url="https://app.daytona.io/api"))
            _sandbox = d.create(CreateSandboxFromSnapshotParams(
                language="python", ephemeral=True, auto_stop_interval=120, labels={"app": "ai-billing-rep", "role": "checks"}))
            atexit.register(_cleanup, d, _sandbox)  # one sandbox per process, deleted on exit
        return _sandbox


def _cleanup(d, sandbox) -> None:
    try:
        d.delete(sandbox)
    except Exception:  # noqa: BLE001
        pass


def warm() -> None:
    """Create the sandbox early so the first check is fast."""
    if config.has("DAYTONA_API_KEY"):
        try:
            _get_sandbox()
        except Exception:  # noqa: BLE001 - a cold start later is fine
            pass


def _parse(output: str) -> dict:
    for line in output.splitlines():
        if line.startswith("RESULT:"):
            return json.loads(line[len("RESULT:"):])
    raise RuntimeError(f"no result in output: {output[-300:]}")


def compare(invoice: dict, prior: dict | None, terms: dict) -> dict:
    payload = json.dumps({"invoice": invoice, "prior": prior, "terms": terms})
    code = f"INPUT = {payload!r}\n" + COMPARE
    started = time.time()
    if config.has("DAYTONA_API_KEY"):
        try:
            try:
                sb = _get_sandbox()
                resp = sb.process.code_run(code, timeout=60)
            except Exception:  # noqa: BLE001 - the sandbox may have auto-stopped: start a fresh one once
                global _sandbox
                _sandbox = None
                sb = _get_sandbox()
                resp = sb.process.code_run(code, timeout=60)
            result = _parse(resp.result)
            result["_meta"] = {"ran_in": "Daytona sandbox", "sandbox_id": sb.id, "seconds": round(time.time() - started, 1), "exit_code": resp.exit_code}
            return result
        except Exception as e:  # noqa: BLE001
            err = str(e)[:200]
    else:
        err = "DAYTONA_API_KEY not set"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    result = _parse(proc.stdout)
    result["_meta"] = {"ran_in": "local (Daytona unavailable)", "error": err, "seconds": round(time.time() - started, 1)}
    return result
