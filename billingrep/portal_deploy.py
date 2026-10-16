"""Deploy the SYNTHETIC carrier portal (portal/server.py) to a public Daytona sandbox.

    uv run python -m billingrep.portal_deploy          # prints the portal URL (deploys if needed)
    uv run python -m billingrep.portal_deploy --new    # replace it with a fresh sandbox

portal_url() order: config.PORTAL_URL, else the cached URL in local-data/portal.json if it
still answers, else a new deploy. The sandbox is public so Anchor's cloud browser can reach it.
"""

import json
import os
import sys
import time

import httpx

from billingrep import config

PORT = 8080
CACHE = config.LOCAL / "portal.json"
PORTAL_DIR = config.ROOT / "portal"
INBOX_DIR = config.DATA / "samples" / "inbox"
API_URL = "https://app.daytona.io/api"


def _client():
    from daytona import Daytona, DaytonaConfig

    key = os.environ.get("DAYTONA_API_KEY")
    if not key:
        raise RuntimeError("DAYTONA_API_KEY is not set")
    return Daytona(DaytonaConfig(api_key=key, api_url=API_URL))


def _alive(url: str, timeout: float = 8.0) -> bool:
    try:
        r = httpx.get(url.rstrip("/") + "/api/cases", timeout=timeout, follow_redirects=True)
        return r.status_code == 200 and "cases" in r.json()
    except Exception:
        return False


def _read_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _delete_cached(daytona) -> None:
    """Delete the sandbox local-data/portal.json points at, if it still exists, so it never runs beside a new one.

    Only "not found" is swallowed: any other error stops the deploy instead of starting a second portal.
    """
    from daytona import DaytonaNotFoundError

    old_id = _read_cache().get("sandbox_id")
    if not old_id:
        return
    try:
        old = daytona.get(old_id)
        if old.labels.get("role") == "synthetic-portal":  # only ever our own portal
            daytona.delete(old, wait=True)
    except DaytonaNotFoundError:
        pass  # already gone


def deploy() -> str:
    """Create a public python sandbox, upload the portal + inbox PDFs, start it on 8080, return the URL.

    Deletes the previously cached portal sandbox first. Never auto-stops: delete it after the event.
    """
    from daytona import CreateSandboxFromSnapshotParams

    daytona = _client()
    _delete_cached(daytona)
    params = CreateSandboxFromSnapshotParams(
        language="python", public=True, auto_stop_interval=0,
        labels={"app": "ai-billing-rep", "role": "synthetic-portal"},
    )
    sandbox = daytona.create(params, timeout=180)
    try:
        url = _serve(sandbox)
    except Exception:
        try:
            daytona.delete(sandbox)  # never leave a public, never-stopping sandbox that no cache points at
        except Exception:  # noqa: BLE001
            pass
        raise
    CACHE.write_text(json.dumps({"url": url, "sandbox_id": sandbox.id, "deployed_at": time.time()}, indent=1))
    return url


def _serve(sandbox) -> str:
    """Upload the portal + inbox PDFs, start it on 8080, wait until it answers, return the URL."""
    from daytona import FileUpload, SessionExecuteRequest

    try:
        base = sandbox.get_work_dir().rstrip("/") + "/portal"
    except Exception:
        base = "portal"
    sandbox.process.exec(f"mkdir -p {base}/files")
    uploads = [FileUpload(source=str(PORTAL_DIR / "server.py"), destination=f"{base}/server.py")]
    if INBOX_DIR.exists():
        uploads += [FileUpload(source=str(p), destination=f"{base}/files/{p.name}")
                    for p in sorted(INBOX_DIR.glob("H-*.pdf"))]
    sandbox.fs.upload_files(uploads)

    sandbox.process.create_session("portal")
    sandbox.process.execute_session_command("portal", SessionExecuteRequest(
        command=f"cd {base} && PORT={PORT} python3 server.py > server.log 2>&1", run_async=True,
    ))
    if not getattr(sandbox, "public", False):
        try:
            sandbox.set_public(True)
        except Exception:
            pass

    link = sandbox.get_preview_link(PORT)
    url = link.url.rstrip("/")
    for _ in range(30):
        if _alive(url, timeout=5):
            return url
        time.sleep(2)
    raise RuntimeError(f"portal did not answer at {url}/api/cases (sandbox {sandbox.id})")


def portal_url() -> str:
    if config.PORTAL_URL:
        return config.PORTAL_URL.rstrip("/")
    cached = _read_cache().get("url")
    if cached and (_alive(cached) or _alive(cached, timeout=20)):  # look twice: a redeploy deletes this portal
        return cached
    return deploy()


if __name__ == "__main__":
    print(deploy() if "--new" in sys.argv else portal_url())
