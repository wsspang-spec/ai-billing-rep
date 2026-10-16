"""FastAPI app: sign in, inbox, invoice evidence, approve + send inquiry, CFO view, reset."""

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from billingrep import actions, agent, checks, config, db, tracing

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
    return {"user": _user(request), "company": db.seed_data()["company"]}


def _summary(inv: dict) -> dict:
    d = inv.get("decision") or {}
    return {k: inv.get(k) for k in ("key", "invoice_number", "account", "vendor", "period_start", "period_end", "total", "delta", "status", "due_date")} | {
        "summary": d.get("summary"), "payment": db.one("SELECT amount, scheduled_on, status FROM payment WHERE invoice = $k", {"k": inv["key"]})}


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
    except Exception as e:  # noqa: BLE001
        _errors.append(f"{path.name}: {str(e)[:200]}")
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
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF only")
    body = await request.body()
    if len(body) > 5_000_000:
        raise HTTPException(413, "PDF over 5 MB")
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
    return actions.cfo_summary()


@app.post("/api/reset")
def reset(request: Request) -> dict:
    _user(request)
    out = db.reset_demo()
    _errors.clear()
    try:
        import httpx

        from billingrep import portal_deploy

        url = config.PORTAL_URL or portal_deploy._read_cache().get("url")  # never deploy inside a request
        r = httpx.post(url.rstrip("/") + "/api/reset", headers={"X-Daytona-Skip-Preview-Warning": "true"}, timeout=10)
        out["portal_reset"] = "ok" if r.status_code == 200 else f"failed ({r.status_code})"
    except Exception as e:  # noqa: BLE001
        out["portal_reset"] = f"failed ({type(e).__name__})"
    return out


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
