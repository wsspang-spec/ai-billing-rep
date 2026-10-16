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
def index() -> str:
    return (STATIC / "index.html").read_text()


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
        "summary": d.get("summary"), "steps": steps,
        "payment": db.one("SELECT amount, scheduled_on, status FROM payment WHERE invoice = $k", {"k": inv["key"]})}


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
    _sending.add(key)
    try:
        return actions.submit_inquiry(key)
    except actions.ApprovalRequired as e:
        return JSONResponse({"blocked": True, "error": str(e)}, status_code=403)
    finally:
        _sending.discard(key)


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
    d = db.one("SELECT * FROM document WHERE key = $k", {"k": doc_id})
    if not d:
        raise HTTPException(404, "no such document")
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
