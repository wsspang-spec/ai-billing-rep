"""FastAPI app: sign in, inbox, invoice evidence, approve + send inquiry, CFO view, reset."""

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from billingrep import actions, agent, checks, config, db, llm, tracing

app = FastAPI(title="AI Billing Rep")
STATIC = Path(__file__).parent / "static"
INBOX = config.DATA / "samples" / "inbox"
UPLOADS = config.LOCAL / "uploads"
UPLOADS.mkdir(exist_ok=True)
COOKIE = "br_session"
_running: set[str] = set()
_errors: list[str] = []


@app.on_event("startup")
def _startup() -> None:
    tracing.setup()
    db.ensure_seeded()
    threading.Thread(target=checks.warm, daemon=True).start()


def _user(request: Request) -> dict:
    user = db.session_user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "sign in first")
    return user


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(), headers={"Cache-Control": "no-store"})  # always the latest UI


@app.post("/api/login")
async def login(request: Request, response: Response) -> dict:
    body = await request.json()
    result = db.login(body.get("email", ""), body.get("password", ""))
    if not result:
        raise HTTPException(401, "Wrong email or password")
    response.set_cookie(COOKIE, result["token"], httponly=True, samesite="lax")
    return {"user": result["user"]}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    db.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request) -> dict:
    import os

    return {"user": _user(request), "company": db.seed_data()["company"], "show_reset": os.environ.get("HIDE_RESET") != "1"}


def _summary(inv: dict) -> dict:
    d = inv.get("decision") or {}
    steps = [e["step"] for e in db.q("SELECT step, at FROM event WHERE invoice = $k ORDER BY at ASC", {"k": inv["key"]})]
    return {k: inv.get(k) for k in ("key", "invoice_number", "account", "vendor", "period_start", "period_end", "total", "delta", "status", "due_date")} | {
        "summary": d.get("summary"), "steps": steps, "why": _why(inv),
        "payment": db.one("SELECT amount, scheduled_on, status FROM payment WHERE invoice = $k", {"k": inv["key"]})}


def _why(inv: dict) -> str:
    """One line a rep can act on, shown under the status on the dashboard."""
    st, c = inv.get("status"), inv.get("checks") or {}
    open_lines = [l for l in c.get("lines", []) if l.get("verdict") != "matches_term"]
    used = (inv.get("terms_used") or [{}])[0]
    if st == "Explained":
        if inv.get("delta"):
            letter = str(used.get("source", "")).rsplit("-", 1)[-1].upper()
            return f"Increase checked: matches {'Amendment' if 'amendment' in str(used.get('source')) else 'Contract'} {letter} from {used.get('valid_from', '')}"
        return "Same as last month; matches the contract"
    if st == "Duplicate":
        return f"Already received as {inv.get('duplicate_of')}; not paid twice"
    if st == "Needs clarification" and open_lines:
        return f"“{open_lines[0]['description']}” (${open_lines[0]['amount']:,.2f}) isn’t in the contract"
    if st == "Needs review" and open_lines:
        l = open_lines[0]
        return f"Billed ${l['amount']:,.2f}; the price for that period was ${(l.get('expected') or 0):,.2f}"
    if st == "Approved":
        return "Approved; ready to send to the vendor"
    if st == "Awaiting vendor response":
        a = db.one("SELECT case_id FROM action WHERE invoice = $k", {"k": inv["key"]}) or {}
        return f"Asked on the vendor portal (case {a.get('case_id', '')}); rest scheduled"
    return ""


@app.get("/api/invoices")
def invoices(request: Request) -> dict:
    _user(request)
    rows = db.q("SELECT * FROM invoice WHERE run = true ORDER BY received_at ASC")
    order = {"Needs clarification": 0, "Needs review": 1, "Approved": 2, "Checking": 3, "Awaiting vendor response": 4, "Explained": 5, "Duplicate": 6}
    rows.sort(key=lambda r: order.get(r["status"], 9))
    pending = sorted(p.name for p in INBOX.glob("*.pdf") if not db.one("SELECT key FROM invoice WHERE source = 'inbox' AND file_name = $f", {"f": p.name}))
    return {"invoices": [_summary(r) for r in rows], "processing": sorted(_running), "inbox_waiting": pending, "errors": _errors[-3:]}


def _run(path: Path, source: str) -> None:
    _running.add(path.name)
    try:
        d = agent.process_invoice(str(path), source=source)
        db.q("UPDATE invoice SET file_name = $f WHERE key = $k", {"f": path.name, "k": d["key"]})
    except llm.NotAnInvoice as e:
        _errors.append(f"{path.name} isn't an invoice: {e}. Nothing was saved.")
    except Exception as e:  # noqa: BLE001
        _errors.append(f"{path.name} couldn't be checked: {str(e)[:160]}")
    finally:
        _running.discard(path.name)


@app.post("/api/fetch")
def fetch(request: Request) -> dict:
    """Read every invoice waiting in the sample AP inbox (Gmail later), one after another, in the background."""
    _user(request)
    waiting = [p for p in sorted(INBOX.glob("*.pdf"))
               if p.name not in _running and not db.one("SELECT key FROM invoice WHERE source = 'inbox' AND file_name = $f", {"f": p.name})]

    def work() -> None:
        for p in waiting:
            _run(p, "inbox")

    for p in waiting:
        _running.add(p.name)
    threading.Thread(target=work, daemon=True).start()
    return {"started": [p.name for p in waiting]}


@app.post("/api/upload")
async def upload(request: Request) -> dict:
    """Drop a PDF: raw body, file name in X-Filename."""
    _user(request)
    name = Path(request.headers.get("x-filename", "upload.pdf")).name
    body = await request.body()
    if not name.lower().endswith(".pdf") or not body.startswith(b"%PDF"):
        raise HTTPException(415, f"{name} isn't a PDF. Drop a PDF invoice.")
    if len(body) > 5_000_000:
        raise HTTPException(413, f"{name} is over 5 MB.")
    path = UPLOADS / name
    path.write_bytes(body)
    _running.add(name)
    threading.Thread(target=_run, args=(path, "upload"), daemon=True).start()
    return {"started": [name]}


@app.get("/api/invoices/{key}")
def invoice(key: str, request: Request) -> dict:
    _user(request)
    d = agent.detail(key)
    if not d:
        raise HTTPException(404, "no such invoice")
    return d


@app.post("/api/invoices/{key}/approve")
def approve(key: str, request: Request) -> dict:
    user = _user(request)
    try:
        return actions.approve(key, user["name"])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


_sending: set[str] = set()


@app.post("/api/invoices/{key}/inquiry")
def inquiry(key: str, request: Request):
    _user(request)
    if key in _sending:
        return JSONResponse({"error": "Already sending this inquiry; wait for the portal confirmation."}, status_code=409)
    try:
        action = actions.require_approval(key)
    except actions.ApprovalRequired as e:
        return JSONResponse({"blocked": True, "error": str(e)}, status_code=403)
    if action["status"] == "Submitted":
        return action
    _sending.add(key)
    # mark it before the job starts, so the page that reloads next already sees "Sending" and streams the live view
    db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": key, "m": {"status": "Sending", "live_view_url": None}})

    def work() -> None:
        try:
            actions.submit_inquiry(key)
        except Exception as e:  # noqa: BLE001
            db.q("UPDATE action MERGE $m WHERE invoice = $k", {"k": key, "m": {"status": "Failed", "portal": {"error": str(e)[:200]}}})
        finally:
            _sending.discard(key)

    threading.Thread(target=work, daemon=True).start()
    return {"status": "Sending"}


@app.get("/api/cfo")
def cfo(request: Request) -> dict:
    _user(request)
    out = actions.cfo_summary()
    vendors = {i["key"]: i.get("vendor") for i in db.q("SELECT key, vendor FROM invoice")}
    out["payments"] = [p | {"vendor": vendors.get(p["invoice"]), "part": "undisputed" in p.get("status", "")}
                       for p in db.q("SELECT * FROM payment ORDER BY scheduled_on ASC")]
    return out


@app.post("/api/errors/clear")
def clear_errors(request: Request) -> dict:
    _user(request)
    _errors.clear()
    return {"ok": True}


@app.get("/samples/next")
def sample_next(request: Request):
    """A fresh bill for the drag-and-drop demo: new invoice number every time, rotating outcomes."""
    _user(request)
    from billingrep import samples

    path = samples.next_sample()
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/stats")
def stats(request: Request) -> dict:
    """What the agent did this month, per sponsor, and what it saved the rep. All counted from stored events."""
    _user(request)
    import datetime as dt
    import json

    def ts(x: str) -> dt.datetime:
        return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))

    ev = db.q("SELECT step, sponsor, invoice, at FROM event")
    run = db.q("SELECT * FROM invoice WHERE run = true")
    n = lambda step: sum(1 for e in ev if e["step"] == step)  # noqa: E731
    per = {}
    for e in ev:
        per.setdefault(e["invoice"], []).append(ts(e["at"]))
    secs = [(max(v) - min(v)).total_seconds() for k, v in per.items() if len(v) > 2]
    review = ("Needs review", "Needs clarification", "Approved", "Awaiting vendor response")
    held = sum((i.get("checks") or {}).get("unsupported_amount", 0) for i in run if i["status"] in review)
    pays = db.q("SELECT * FROM payment")
    today = dt.date.fromisoformat(config.TODAY)
    windows = [(dt.date.fromisoformat(i["invoice_date"]) + dt.timedelta(days=30) - today).days for i in run if i["status"] in review[1:]]
    ev_file = config.ROOT / "eval" / "results.json"
    score = json.loads(ev_file.read_text()).get("score", {}) if ev_file.exists() else {}
    return {
        "bills": len([i for i in run if i["status"] != "Checking"]),
        "secs_per_bill": round(sum(secs) / len(secs), 1) if secs else None,
        "held": round(held, 2),
        "paid_on_time": sum(1 for p in pays if p["scheduled_on"] < p["due_on"]), "payments": len(pays),
        "dispute_days_left": min(windows) if windows else None,
        "duplicates_stopped": n("Duplicate"), "blocked": n("Blocked"),
        "sponsors": {
            "claude": {"reads": n("Read"), "decisions": n("Decided")},
            "surreal": {"recalls": n("Recalled"), "users": 1},
            "daytona": {"checks": sum(1 for e in ev if e["step"] == "Compared" and "Daytona" in (e.get("sponsor") or "")), "portal": 1},
            "anchor": {"filed": n("Submitted")},
            "arize": {"traces": len(per) , "eval_passed": score.get("passed"), "eval_total": score.get("case_count")},
        },
    }


@app.get("/api/quality")
def quality(request: Request) -> dict:
    """The latest eval run (the team's labeled cases, scored against the real app and logged to Arize)."""
    _user(request)
    import json

    f = config.ROOT / "eval" / "results.json"
    if not f.exists():
        return {"cases": []}
    r = json.loads(f.read_text())
    return {"run_at": r.get("run_at"), "model": r.get("model"), "score": r.get("score"), "trials": r.get("trials"),
            "arize": r.get("arize"), "cases": [{k: v for k, v in c.items() if k not in ("inputs", "output")} for c in r.get("cases", [])]}


@app.get("/samples/{name}")
def sample(name: str, request: Request):
    """Extra bills for the drag-and-drop demo."""
    _user(request)
    path = config.DATA / "samples" / "upload" / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.post("/api/reset")
def reset(request: Request) -> dict:
    _user(request)
    out = db.reset_demo()
    _errors.clear()
    threading.Thread(target=_reset_portal, daemon=True).start()  # don't make the user wait on the portal
    try:
        from billingrep import samples

        samples.reset_counter()
    except Exception:  # noqa: BLE001
        pass
    return out


def _portal_base() -> str:
    from billingrep import portal_deploy

    return (config.PORTAL_URL or portal_deploy._read_cache().get("url") or "").rstrip("/")  # never deploy in a request


def _reset_portal() -> None:
    try:
        import httpx

        httpx.post(_portal_base() + "/api/reset", headers={"X-Daytona-Skip-Preview-Warning": "true"}, timeout=10)
    except Exception:  # noqa: BLE001
        pass


@app.get("/files/{name}")
def files(name: str, request: Request):
    _user(request)
    path = config.LOCAL / "files" / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf")


@app.get("/audio/{name}")
def audio(name: str, request: Request):
    _user(request)
    path = config.LOCAL / "audio" / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


DOC_NAMES = {"contract": "Contract", "approved_amendment": "Amendment", "vendor_message": "Vendor message"}


def _doc_title(d: dict) -> str:
    letter = d["key"].rsplit("-", 1)[-1].upper()
    return f"{DOC_NAMES.get(d.get('kind'), 'Document')} {letter}"


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def document(doc_id: str, request: Request):
    """The contract, amendment or message a citation points at."""
    _user(request)
    if "-L" in doc_id and doc_id.rsplit("-L", 1)[-1].isdigit():  # an invoice line → the invoice PDF
        from fastapi.responses import RedirectResponse

        return RedirectResponse(f"/files/{doc_id.rsplit('-L', 1)[0]}.pdf")
    doc_id = doc_id.removeprefix("term-")
    if db.one("SELECT key FROM invoice WHERE key = $k", {"k": doc_id}):  # a cited invoice → its PDF
        from fastapi.responses import RedirectResponse

        return RedirectResponse(f"/files/{doc_id}.pdf")
    d = db.one("SELECT * FROM document WHERE key = $k", {"k": doc_id})
    if not d:
        raise HTTPException(404, "no such document")
    try:
        from billingrep import docs_render

        return docs_render.render_document(d, request.query_params.get("q", ""))
    except ImportError:
        pass
    import html

    rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in
                   (("Service", d.get("service_id")), ("Effective", d.get("valid_from")), ("Recorded", d.get("date"))) if v)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(_doc_title(d))}</title>
<style>body{{margin:0;background:#F5F5F7;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Helvetica Neue',sans-serif;color:#1D1D1F}}
.page{{max-width:720px;margin:40px auto;background:#fff;border-radius:16px;padding:48px 56px;box-shadow:0 8px 24px rgba(0,0,0,.06)}}
h1{{margin:0 0 4px;font-size:28px}}.k{{color:#6E6E73;font-size:14px}}p{{font-size:17px;line-height:1.6}}table{{border-collapse:collapse;margin:20px 0}}
th{{text-align:left;color:#6E6E73;font-weight:500;padding:6px 24px 6px 0}}td{{padding:6px 0}}a{{color:#0066CC}}</style></head>
<body><div class="page"><div class="k">Atlas Retail · document on file</div><h1>{html.escape(_doc_title(d))}</h1><table>{rows}</table>
<p>{html.escape(d.get("text", ""))}</p><p class="k"><a href="javascript:history.back()">‹ Back</a></p></div></body></html>"""


@app.api_route("/portal/{path:path}", methods=["GET", "POST"])
async def portal_proxy(path: str, request: Request):
    """The carrier portal through our own domain (no Daytona preview warning page in the demo)."""
    _user(request)
    import httpx

    headers = {"X-Daytona-Skip-Preview-Warning": "true",
               "cookie": "nw_session=synthetic-demo-session"}  # Maria is already signed in to her carrier portal
    body = None
    if request.method == "POST":
        headers["content-type"] = request.headers.get("content-type", "application/x-www-form-urlencoded")
        body = await request.body()
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
        r = await c.request(request.method, f"{_portal_base()}/{path}", params=dict(request.query_params), content=body, headers=headers)
    ctype = r.headers.get("content-type", "")
    content = r.content
    if "text/html" in ctype:
        content = content.replace(b'href="/', b'href="/portal/').replace(b'action="/', b'action="/portal/')
    resp = Response(content, status_code=r.status_code, media_type=ctype.split(";")[0] or None)
    if r.headers.get("location"):
        loc = r.headers["location"]
        resp.headers["location"] = "/portal" + loc if loc.startswith("/") else loc
    for cookie in r.headers.get_list("set-cookie"):
        resp.headers.append("set-cookie", cookie)
    return resp


@app.get("/static/{name}")
def static_file(name: str):
    path = STATIC / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "bedrock_model": config.MODEL, "db": config.DB_URL.split("://")[0],
            "daytona": config.has("DAYTONA_API_KEY"), "arize": config.has("ARIZE_SPACE_ID", "ARIZE_API_KEY"),
            "anchor": config.has("ANCHORBROWSER_API_KEY"), "elevenlabs": config.has("ELEVENLABS_API_KEY")}


def main() -> None:
    uvicorn.run("billingrep.web:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
