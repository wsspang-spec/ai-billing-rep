"""SurrealDB: one store for users, sessions, invoices, dated contract terms, checks, approvals and actions.

Embedded on disk by default (local-data/billing), so the demo needs no server. Set BILLING_DB_URL
for a SurrealDB server (then SURREALDB_USER / SURREALDB_PASS too).
"""

import datetime as dt
import json
import os
import threading
from typing import Any

from surrealdb import Surreal

from billingrep import config

EMBEDDED = ("mem://", "memory://", "surrealkv://", "file://")
RUN_TABLES = ["invoice", "payment", "action", "event"]  # sessions survive a demo reset
SEED_TABLES = ["user", "account", "document", "term", "credit"]

_lock = threading.RLock()
_db: Any = None


def _connect() -> Any:
    db = Surreal(config.DB_URL)
    if not config.DB_URL.startswith(EMBEDDED):
        db.signin({"username": os.environ["SURREALDB_USER"], "password": os.environ["SURREALDB_PASS"]})
    db.use("billing_rep", "demo")
    return db


def _clean(value: Any) -> Any:
    """Record ids and datetimes into plain JSON values."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)  # RecordID and friends


def q(sql: str, vars: dict | None = None) -> list:
    """Run one SurrealQL statement; always returns a list of plain dicts."""
    global _db
    with _lock:
        if _db is None:
            _db = _connect()
        result = _db.query(sql, vars or {})
    result = _clean(result)
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def one(sql: str, vars: dict | None = None) -> dict | None:
    rows = q(sql, vars)
    return rows[0] if rows and isinstance(rows[0], dict) else None


def seed_data() -> dict:
    return json.loads((config.DATA / "seed.json").read_text())


def reset_demo() -> dict:
    """Delete this run's rows and reload the seed: September bills, contract, amendment, terms, the user."""
    seed = seed_data()
    for table in RUN_TABLES + SEED_TABLES:
        q(f"DELETE {table}")
    u = seed["user"]
    q(
        "CREATE user SET email = $email, name = $name, role = $role, password_hash = crypto::argon2::generate($pw)",
        {"email": u["email"], "name": u["name"], "role": u["role"], "pw": u["password"]},
    )
    for a in seed["accounts"]:
        q("CREATE type::thing('account', $id) CONTENT $a", {"id": a["id"], "a": {k: v for k, v in a.items() if k != "id"} | {"key": a["id"]}})
    for d in seed["documents"]:
        q("CREATE type::thing('document', $id) CONTENT $d", {"id": d["id"], "d": {k: v for k, v in d.items() if k != "id"} | {"key": d["id"]}})
    for t in seed["terms"]:
        q("CREATE type::thing('term', $id) CONTENT $t", {"id": t["id"], "t": {k: v for k, v in t.items() if k != "id"} | {"key": t["id"]}})
    for c in seed["credits"]:
        q("CREATE type::thing('credit', $id) CONTENT $c", {"id": c["id"], "c": {k: v for k, v in c.items() if k != "id"} | {"key": c["id"]}})
    for inv in seed["history"]:
        q(
            "CREATE invoice CONTENT $inv",
            {"inv": inv | {"key": inv["invoice_number"], "source": "history", "run": False, "decision": None}},
        )
    return {"ok": True, "seeded": {"terms": len(seed["terms"]), "documents": len(seed["documents"]), "history": len(seed["history"])}}


def ensure_seeded() -> None:
    if not one("SELECT * FROM user LIMIT 1"):
        reset_demo()


def log_event(invoice_key: str, step: str, detail: str, sponsor: str = "") -> None:
    q(
        "CREATE event SET invoice = $k, step = $s, detail = $d, sponsor = $sp, at = time::now()",
        {"k": invoice_key, "s": step, "d": detail, "sp": sponsor},
    )


# ---- time-aware terms (the "memory" the agent recalls) ----

def terms_as_of(service: str, as_of: str) -> list[dict]:
    """The contract term in effect for this service on this date, with its source."""
    return q(
        "SELECT * FROM term WHERE service = $s AND valid_from <= $d AND (valid_to = NONE OR valid_to = NULL OR valid_to >= $d)"
        " ORDER BY valid_from DESC",
        {"s": service, "d": as_of},
    )


def term_history(service: str) -> list[dict]:
    return q("SELECT * FROM term WHERE service = $s ORDER BY valid_from ASC", {"s": service})


# ---- auth ----

def login(email: str, password: str) -> dict | None:
    user = one(
        "SELECT email, name, role FROM user WHERE email = $e AND crypto::argon2::compare(password_hash, $pw)",
        {"e": email, "pw": password},
    )
    if not user:
        return None
    session = one("CREATE session SET token = rand::uuid::v4(), email = $e, created = time::now() RETURN AFTER", {"e": email})
    return {"user": user, "token": session["token"]}


def session_user(token: str | None) -> dict | None:
    if not token:
        return None
    s = one("SELECT * FROM session WHERE token = <uuid> $t", {"t": token}) or one("SELECT * FROM session WHERE token = $t", {"t": token})
    if not s:
        return None
    return one("SELECT email, name, role FROM user WHERE email = $e", {"e": s["email"]})


def logout(token: str | None) -> None:
    if token:
        q("DELETE session WHERE token = $t", {"t": token})
