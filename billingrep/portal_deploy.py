"""Deploy the SYNTHETIC carrier portal (portal/server.py) to a public Daytona sandbox.

    uv run python -m billingrep.portal_deploy          # prints the portal URL (deploys if needed)
    uv run python -m billingrep.portal_deploy --new    # force a fresh sandbox

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


def deploy() -> str:
    """Create a public python sandbox, upload the portal + inbox PDFs, start it on 8080, return the URL."""
    from daytona import CreateSandboxFromSnapshotParams, FileUpload, SessionExecuteRequest

    daytona = _client()
    params = CreateSandboxFromSnapshotParams(
        language="python", public=True, auto_stop_interval=0,
        labels={"app": "ai-billing-rep", "role": "synthetic-portal"},
    )
    sandbox = daytona.create(params, timeout=180)
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
            break
        time.sleep(2)
    else:
        raise RuntimeError(f"portal did not answer at {url}/api/cases (sandbox {sandbox.id})")
    CACHE.write_text(json.dumps({"url": url, "sandbox_id": sandbox.id, "deployed_at": time.time()}, indent=1))
    return url


def portal_url() -> str:
    if config.PORTAL_URL:
        return config.PORTAL_URL.rstrip("/")
    cached = _read_cache().get("url")
    if cached and _alive(cached):
        return cached
    return deploy()


if __name__ == "__main__":
    print(deploy() if "--new" in sys.argv else portal_url())
