"""Adapter: run the official eval pack (evals/) against the REAL app. All data is SYNTHETIC.

    uv run python eval/run_eval.py              # run, write evals/outputs.jsonl, score, write eval/results.md
    uv run python eval/run_eval.py --trials 3   # also repeat E01 and E03 three times (reset before each)
    uv run python eval/run_eval.py --no-arize   # skip logging to Arize AX

The app never sees evals/expected.jsonl (neither does this adapter; only evals/score.py reads it).
For each case the app implements, this drives the real functions (db.reset_demo,
agent.process_invoice on the matching PDF, actions.approve / submit_inquiry / cfo_summary),
then maps the app's results and persisted state to the pack's field names (integer cents,
snake_case status). Cases the app does not implement are written as not run, never faked.
"""

import os

# Own in-memory database, set BEFORE billingrep is imported: the eval must never reset
# the live demo database (local-data/billing) that the running web app uses.
os.environ["BILLING_DB_URL"] = "mem://"

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evals"
INPUTS = PACK / "inputs.jsonl"
OUTPUTS = PACK / "outputs.jsonl"
SCORER = PACK / "score.py"
RESULTS_JSON = ROOT / "eval" / "results.json"
RESULTS_MD = ROOT / "eval" / "results.md"
INBOX, EVALDIR, PORTAL = ROOT / "data/samples/inbox", ROOT / "data/samples/eval", ROOT / "data/samples/portal"
CASE_TIMEOUT_S = float(os.environ.get("EVAL_CASE_TIMEOUT", "240"))
AX_PYTHON = Path.home() / ".local/share/uv/tools/arize-ax-cli/bin/python"  # ships the full `arize` SDK

STATUS = {
    "Explained": "explained",
    "Needs review": "needs_review",
    "Needs clarification": "needs_clarification",
    "Duplicate": "duplicate",
    "Awaiting vendor response": "awaiting_vendor_response",
    "Proposed": "awaiting_approval",
    "Approved": "approved",
}

NOT_RUN = {
    "E07": "needs a pre-existing portal case DEMO-CASE-001 plus a simulated browser timeout; the adapter cannot seed the portal",
    "E08": "app has no amount-due vs current-charges arithmetic check on a portal invoice with prior balance",
    "E09": "app has no missing-invoice coverage report",
    "E12": "app does not separate carried-forward balance from current expense",
    "E14": "app has no service-cancellation logic",
}


def cents(x) -> int | None:
    try:
        return int(round(float(x) * 100))
    except (TypeError, ValueError):
        return None


def snake(status: str | None) -> str | None:
    if status is None:
        return None
    return STATUS.get(status, re.sub(r"[^a-z0-9]+", "_", status.lower()).strip("_"))


def timed(fn, *args, **kw):
    t0 = time.perf_counter()
    ex = cf.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, *args, **kw)
    try:
        out, err = fut.result(timeout=CASE_TIMEOUT_S), None
    except cf.TimeoutError:
        out, err = None, TimeoutError(f"timed out after {CASE_TIMEOUT_S:.0f}s")
    except BaseException as e:  # noqa: BLE001 - recorded as the case's actual result
        out, err = None, e
    ex.shutdown(wait=False, cancel_futures=True)
    return out, err, round(time.perf_counter() - t0, 2)


def count(rows) -> int:
    while isinstance(rows, list) and rows:
        if isinstance(rows[0], dict):
            return int(rows[0].get("count", 0))
        rows = rows[0]
    return 0


def source_ids(inv: dict) -> list[str]:
    """What the app cited, normalized to pack ids (strip table prefixes; 'X line 2' -> X, X-L2)."""
    out: list[str] = []

    def add(s):
        if s and s not in out:
            out.append(s)

    cites = ((inv.get("decision") or {}).get("citations")) or []
    for c in cites:
        src = str((c or {}).get("source", "")).strip()
        bare = src.split(":", 1)[-1].strip("`'\" ⟨⟩")
        add(bare)
        m = re.match(r"([A-Z]-[A-Z]{3}-[A-Z0-9-]+?)(?:[\s#]+(?:line\s*)?(\d+))?$", bare, re.I)
        if m and m.group(2):
            add(m.group(1))
            add(f"{m.group(1)}-L{m.group(2)}")
    for t in inv.get("terms_used") or []:  # dated records the app retrieved and applied
        add(t.get("source"))
    return out


class Adapter:
    def __init__(self, db, agent, actions):
        self.db, self.agent, self.actions = db, agent, actions
        self.inv: dict[str, dict] = {}

    def payments(self) -> int:
        return count(self.db.q("SELECT count() FROM payment GROUP ALL"))

    def process(self, path: Path, source: str = "inbox"):
        out, err, secs = timed(self.agent.process_invoice, str(path), source=source)
        if err:
            raise RuntimeError(f"{type(err).__name__}: {str(err)[:200]}")
        return out, secs

    def invoice_case(self, cid, path, fields, source="inbox"):
        inv, secs = self.process(path, source)
        self.inv[cid] = inv
        chk = inv.get("checks") or {}
        o = {"status": snake(inv.get("status"))}
        if "delta_cents" in fields:
            o["delta_cents"] = cents(inv.get("delta"))
        if "recurring_delta_cents" in fields:
            rec = [ln for ln in chk.get("lines", []) if ln.get("term_id")]
            o["recurring_delta_cents"] = cents(sum(ln.get("change_vs_prior") or 0 for ln in rec)) if rec else None
        if "unexplained_cents" in fields:
            o["unexplained_cents"] = cents(chk.get("unsupported_amount", 0))
        if "confirmed_overcharge_cents" in fields:  # the app never confirms an overcharge on its own
            o["confirmed_overcharge_cents"] = cents(chk.get("unsupported_amount", 0)) if inv.get("status") == "Confirmed overcharge" else 0
        if "create_payment_instruction" in fields:
            o["create_payment_instruction"] = bool(inv.get("payment"))
        if "source_ids" in fields:
            o["source_ids"] = source_ids(inv)
        return o, {"secs": secs, "trace_id": inv.get("trace_id"), "app_status": inv.get("status"),
                   "summary": str((inv.get("decision") or {}).get("summary", ""))[:240]}

    def run_all(self, fields: dict[str, list[str]]) -> dict[str, dict]:
        db, actions = self.db, self.actions
        res: dict[str, dict] = {}

        def record(cid, fn):
            try:
                out, meta = fn()
                res[cid] = {"output": out, **meta}
            except Exception as e:  # noqa: BLE001
                res[cid] = {"output": {"error": f"{type(e).__name__}: {str(e)[:200]}"}, "secs": None, "trace_id": None}
            print(f"  {cid}: {json.dumps(res[cid]['output'], default=str)[:220]}  ({res[cid].get('secs')}s)", flush=True)

        db.reset_demo()
        # E01 explained October increase (also creates the simulated payment instruction E04 needs)
        record("E01", lambda: self.invoice_case("E01", INBOX / "N-OCT-101.pdf", fields["E01"]))
        # E03 unexplained surcharge
        record("E03", lambda: self.invoice_case("E03", INBOX / "H-OCT-202.pdf", fields["E03"]))

        # E04 duplicate: payment count must not grow
        def e04():
            before = self.payments()
            inv, secs = self.process(EVALDIR / "N-OCT-101-copy.pdf")
            after = self.payments()
            return ({"status": snake(inv.get("status")), "create_payment_instruction": after > before},
                    {"secs": secs, "trace_id": inv.get("trace_id"), "app_status": inv.get("status"), "payments": f"{before}->{after}"})

        record("E04", e04)

        # E05 credits from the CFO summary
        def e05():
            out, err, secs = timed(actions.cfo_summary)
            if err:
                raise err
            c = out.get("credits") or {}
            return ({"pending_credit_cents": cents(c.get("promised")), "realized_credit_cents": cents(out.get("realized_savings"))},
                    {"secs": secs, "trace_id": None})

        record("E05", e05)

        h_key = (self.inv.get("E03") or {}).get("id")

        def inquiry_state():
            a = db.one("SELECT * FROM action WHERE invoice = $k", {"k": h_key}) or {}
            inv = db.one("SELECT * FROM invoice WHERE key = $k", {"k": h_key}) or {}
            st = inv.get("status") if inv.get("status") == "Awaiting vendor response" else a.get("status")
            return snake(st), a

        # E06 submit with no approval: must be blocked, nothing sent
        def e06():
            if not h_key:
                raise RuntimeError("no H-OCT-202 invoice from E03")
            out, err, secs = timed(actions.submit_inquiry, h_key)
            blocked = isinstance(err, actions.ApprovalRequired)
            status, a = inquiry_state()
            return ({"status": status, "execute_action": not blocked and err is None},
                    {"secs": secs, "trace_id": None, "app": f"raised {type(err).__name__}" if err else "returned",
                     "action_status": a.get("status")})

        record("E06", e06)

        # E13 approval scoped to another invoice: must still be blocked
        def e13():
            if not h_key:
                raise RuntimeError("no H-OCT-202 invoice from E03")
            _, aerr, _ = timed(actions.approve, "OTHER-INVOICE", "eval-approver")
            out, err, secs = timed(actions.submit_inquiry, h_key)
            blocked = isinstance(err, actions.ApprovalRequired)
            status, a = inquiry_state()
            return ({"status": status, "execute_action": not blocked and err is None},
                    {"secs": secs, "trace_id": None,
                     "app": f"approve(OTHER-INVOICE): {type(aerr).__name__ if aerr else 'ok'}; submit: {type(err).__name__ if err else 'returned'}",
                     "action_status": a.get("status")})

        record("E13", e13)

        # E10 CFO month-to-month: add the portal-only October invoice, then read the CFO summary + persisted rows
        def e10():
            inv, secs1 = self.process(PORTAL / "N-OCT-303.pdf", source="portal")
            out, err, secs2 = timed(actions.cfo_summary)
            if err:
                raise err
            sep = db.q("SELECT * FROM invoice WHERE run = false AND period_start = '2026-09-01'")
            oct_run = db.q("SELECT * FROM invoice WHERE run = true AND status != 'Duplicate' AND period_start = '2026-10-01'")
            sep_c = cents(sum(i["total"] for i in sep))
            oct_c = cents(sum(i["total"] for i in oct_run))
            explained = cents(sum(c.get("monthly_change", 0) for c in out.get("recurring_changes") or []))
            unexpl = cents(out.get("billed_exposure_under_review"))
            # next month base = recurring terms in effect on 2026-11-01 for each billed service
            terms = db.q("SELECT * FROM term WHERE valid_from <= '2026-11-01' AND (valid_to = NONE OR valid_to = NULL OR valid_to >= '2026-11-01')")
            base = cents(sum(t["value"] for t in terms))
            c = out.get("credits") or {}
            return ({
                "september_current_charges_cents": sep_c,
                "october_current_charges_cents": oct_c,
                "delta_cents": (oct_c - sep_c) if None not in (oct_c, sep_c) else None,
                "explained_recurring_delta_cents": explained,
                "unexplained_cents": unexpl,
                "next_month_base_cents": base,
                "next_month_if_surcharge_repeats_cents": (base + unexpl) if None not in (base, unexpl) else None,
                "pending_credit_cents": cents(c.get("promised")),
                "realized_credit_cents": cents(out.get("realized_savings")),
            }, {"secs": round(secs1 + secs2, 2), "trace_id": inv.get("trace_id"),
                "note": "app: cfo_summary (exposure, recurring changes, credits); adapter sums persisted invoice rows and in-effect terms"})

        record("E10", e10)
        # E02 September invoice vs October amendment (after E10 so it doesn't count as October spend)
        record("E02", lambda: self.invoice_case("E02", EVALDIR / "N-SEP-EARLY.pdf", fields["E02"]))

        # E11 amendment known but its terms unavailable: fresh state with amendment-a removed
        def e11():
            db.reset_demo()
            db.q("DELETE document WHERE key = 'amendment-a'")
            db.q("DELETE term WHERE source = 'amendment-a'")
            db.q("UPDATE term SET valid_to = NONE, superseded_by = NONE WHERE key = 'term-contract-a'")
            return self.invoice_case("E11", INBOX / "N-OCT-101.pdf", fields["E11"])

        record("E11", e11)
        return res


# ---------------------------------------------------------------- Arize AX


def arize_upload(payload: dict) -> dict:
    """Dataset 'billing-rep-eval-pack' (task + inputs only) and one experiment of this run's outputs."""
    from arize import ArizeClient
    from arize.experiments.evaluators.types import EvaluationResultFieldNames
    from arize.experiments.types import ExperimentTaskFieldNames

    space = os.environ["ARIZE_SPACE_ID"]
    name = "billing-rep-eval-pack"
    client = ArizeClient(api_key=os.environ["ARIZE_API_KEY"])
    try:
        ds, created = client.datasets.get(dataset=name, space=space), False
    except Exception:
        examples = [{"case_id": r["id"], "task": r["task"], "inputs": json.dumps(r["inputs"])} for r in payload["inputs"]]
        ds, created = client.datasets.create(name=name, space=space, examples=examples), True
    ex = client.datasets.list_examples(dataset=ds.id, limit=100)
    ids = {}
    for e in ex.examples or []:
        p = e.to_dict()
        if p.get("case_id"):
            ids[p["case_id"]] = p.get("id") or e.id
    runs = []
    for c in payload["cases"]:
        if c["id"] not in ids:
            continue
        label = "not_run" if c["not_run"] else ("pass" if c["passed"] else "fail")
        runs.append({"example_id": ids[c["id"]], "output": json.dumps(c["output"]),
                     "score": 1.0 if c["passed"] else 0.0, "label": label,
                     "explanation": c.get("reason") or json.dumps(c.get("checks") or {}),
                     "elapsed_s": float(c.get("secs") or 0), "trace_id": c.get("trace_id") or ""})
    exp_name = "eval-pack-" + re.sub(r"[^0-9T]", "", payload["run_at"])
    exp = client.experiments.create(
        name=exp_name, dataset=ds.id, experiment_runs=runs,
        task_fields=ExperimentTaskFieldNames(example_id="example_id", output="output"),
        evaluator_columns={"score_py": EvaluationResultFieldNames(score="score", label="label", explanation="explanation")},
        force_http=True,
    )
    return {"status": "logged", "detail": f"dataset {name} ({'created' if created else 'reused'}), experiment {exp_name}, {len(runs)} runs",
            "dataset_id": ds.id, "experiment_id": getattr(exp, "id", None)}


def log_to_arize(payload_path: Path) -> dict:
    if not (os.environ.get("ARIZE_SPACE_ID") and os.environ.get("ARIZE_API_KEY")):
        return {"status": "skipped", "detail": "ARIZE_SPACE_ID / ARIZE_API_KEY not set"}
    try:
        import arize.datasets  # noqa: F401  (full SDK, not just arize-otel)

        return arize_upload(json.loads(payload_path.read_text()))
    except ImportError:
        pass
    except Exception as e:
        return {"status": "failed", "detail": f"{type(e).__name__}: {str(e)[:300]}"}
    if not AX_PYTHON.exists():
        return {"status": "skipped", "detail": "arize SDK not installed and no ax CLI venv"}
    try:  # same code under the ax CLI's interpreter; keys pass via env, never argv
        p = subprocess.run([str(AX_PYTHON), "-I", str(Path(__file__).resolve()), "--arize-upload", str(payload_path)],
                           capture_output=True, text=True, timeout=120, env=os.environ.copy())
        last = (p.stdout.strip().splitlines() or [""])[-1]
        try:
            return json.loads(last)
        except json.JSONDecodeError:
            return {"status": "failed", "detail": (p.stderr or p.stdout)[-300:]}
    except Exception as e:
        return {"status": "failed", "detail": f"{type(e).__name__}: {str(e)[:300]}"}


# ---------------------------------------------------------------- main


def expected_fields() -> dict[str, list[str]]:
    """Field NAMES only, from the scorer's own output on empty rows (no expected values are read)."""
    ids = [json.loads(x)["id"] for x in INPUTS.read_text().splitlines() if x.strip()]
    tmp = RESULTS_JSON.with_name(".empty_outputs.jsonl")
    tmp.write_text("".join(json.dumps({"id": i, "output": {}}) + "\n" for i in ids))
    p = subprocess.run([sys.executable, str(SCORER), str(tmp)], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    return {r["id"]: list(r["checks"]) for r in json.loads(p.stdout)["results"]}


def write_md(payload: dict) -> str:
    sc = payload["score"]
    ran = [c for c in payload["cases"] if not c["not_run"]]
    rows = [
        f"# Eval pack: {sc['passed']}/{sc['case_count']} passed ({sum(c['passed'] for c in ran)}/{len(ran)} of the cases the app runs)",
        "",
        f"Run {payload['run_at']} · model `{payload['model']}` · SYNTHETIC data (n=1 per case) · scorer: `python evals/score.py evals/outputs.jsonl`",
        "",
        "| Case | Task | Result | Failed fields | App output | Time (s) | Trace |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in payload["cases"]:
        res = "NOT RUN" if c["not_run"] else ("PASS" if c["passed"] else "FAIL")
        failed = ", ".join(k for k, v in (c.get("checks") or {}).items() if not v) or "-"
        out = c.get("reason") if c["not_run"] else json.dumps(c["output"], default=str)
        rows.append(f"| {c['id']} | {c['task']} | {res} | {failed if not c['not_run'] else '-'} | {str(out).replace('|', '/')} "
                    f"| {c.get('secs') if c.get('secs') is not None else '-'} | {c.get('trace_id') or '-'} |")
    t = payload.get("trials")
    if t:
        rows += ["", f"## Repeat trials (N={t['n']}, reset before each)", "", "| Case | Passed | Mean time (s) |", "| --- | --- | --- |"]
        for cid, s in t["by_case"].items():
            rows.append(f"| {cid} | {s['passed']}/{s['runs']} | {s['mean_s']} |")
    a = payload.get("arize") or {}
    rows += ["", "Notes:",
             "- The scorer checks structured fields only, not explanation quality. Side effects were checked in the app's store: payment row count (E04), ApprovalRequired raised and action still Proposed (E06, E13).",
             "- E10 mixes app values (cfo_summary exposure, recurring changes, credits) with adapter sums over persisted invoice rows and in-effect terms.",
             "- Not-run cases are scored as failures on purpose.",
             f"- Arize AX: {a.get('status', 'not run')}" + (f" · {a['detail']}" if a.get("detail") else "")]
    md = "\n".join(rows) + "\n"
    RESULTS_MD.write_text(md)
    return md


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=0, help="repeat E01 and E03 N times (reset before each)")
    ap.add_argument("--no-arize", action="store_true")
    ap.add_argument("--arize-upload", metavar="RESULTS_JSON", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.arize_upload:  # child mode under the ax CLI interpreter
        try:
            out = arize_upload(json.loads(Path(args.arize_upload).read_text()))
        except Exception as e:
            out = {"status": "failed", "detail": f"{type(e).__name__}: {str(e)[:300]}"}
        print(json.dumps(out, default=str))
        return 0

    sys.path.insert(0, str(ROOT))
    from billingrep import config  # loads .env

    try:
        from billingrep import actions, agent, db, tracing
    except Exception as e:
        print(f"core not importable: {type(e).__name__}: {e}")
        return 2
    try:
        tracing.setup()  # spans to Arize AX so each case records a real trace id
    except Exception as e:
        print(f"tracing off: {type(e).__name__}: {e}")

    inputs = [json.loads(x) for x in INPUTS.read_text().splitlines() if x.strip()]
    fields = expected_fields()
    run_at = dt.datetime.now().isoformat(timespec="seconds")
    ad = Adapter(db, agent, actions)
    res = ad.run_all(fields)

    trials = None
    if args.trials > 0:
        by = {"E01": [], "E03": []}
        for n in range(args.trials):
            db.reset_demo()
            for cid, pdf in (("E01", INBOX / "N-OCT-101.pdf"), ("E03", INBOX / "H-OCT-202.pdf")):
                try:
                    o, meta = ad.invoice_case(cid, pdf, fields[cid])
                except Exception as e:  # noqa: BLE001
                    o, meta = {"error": str(e)[:200]}, {"secs": None}
                by[cid].append((o, meta))
                print(f"  trial {n + 1} {cid}: {json.dumps(o, default=str)[:200]}", flush=True)
        trials = {"n": args.trials, "rows": by}

    rows = []
    for r in inputs:
        cid = r["id"]
        if cid in res:
            rows.append({"id": cid, "output": res[cid]["output"]})
        else:
            rows.append({"id": cid, "output": {"not_run": True, "reason": NOT_RUN.get(cid, "not implemented")}})
    OUTPUTS.write_text("".join(json.dumps(x) + "\n" for x in rows))
    p = subprocess.run([sys.executable, str(SCORER), str(OUTPUTS)], capture_output=True, text=True)
    score = json.loads(p.stdout)
    checks = {x["id"]: x for x in score["results"]}

    def trial_pass(cid, o):  # score one trial row with the same scorer
        tmp = RESULTS_JSON.with_name(".trial.jsonl")
        tmp.write_text("".join(json.dumps(x if x["id"] != cid else {"id": cid, "output": o}) + "\n" for x in rows))
        q = subprocess.run([sys.executable, str(SCORER), str(tmp)], capture_output=True, text=True)
        tmp.unlink(missing_ok=True)
        return next(x["passed"] for x in json.loads(q.stdout)["results"] if x["id"] == cid)

    if trials:
        trials["by_case"] = {
            cid: {"runs": len(v), "passed": sum(trial_pass(cid, o) for o, _ in v),
                  "mean_s": round(sum(m.get("secs") or 0 for _, m in v) / max(len(v), 1), 2)}
            for cid, v in trials.pop("rows").items()
        }

    cases = []
    for r in inputs:
        cid = r["id"]
        meta = res.get(cid, {})
        cases.append({"id": cid, "task": r["task"], "not_run": cid not in res, "reason": None if cid in res else NOT_RUN.get(cid),
                      "passed": checks[cid]["passed"], "checks": checks[cid]["checks"], "output": meta.get("output"),
                      "secs": meta.get("secs"), "trace_id": meta.get("trace_id"),
                      "app": {k: v for k, v in meta.items() if k not in ("output", "secs", "trace_id")}})
    try:
        tracing.flush()
    except Exception:
        pass
    payload = {"run_at": run_at, "model": config.MODEL, "synthetic": True, "inputs": inputs, "cases": cases,
               "score": {k: score[k] for k in ("case_count", "passed", "unknown_case_ids")}, "trials": trials}
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, default=str))
    payload["arize"] = {"status": "skipped", "detail": "--no-arize"} if args.no_arize else log_to_arize(RESULTS_JSON)
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, default=str))
    print()
    print(write_md(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
