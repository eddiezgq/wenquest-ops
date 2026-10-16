"""ERPNext sync (ADR-0006): pull changes by ``modified``, record each change as an event, resume from a cursor.

    python -m wqops.hub.sync run [--page N] [--record DIR]   pull changes now (WQO_DB, WQO_ERP_* from the env)
    python -m wqops.hub.sync status                          cursors, document counts and the last run

Each page is written in one transaction together with its cursor, so an interrupted run resumes where it stopped.
Only one run at a time (PostgreSQL advisory lock). Comparisons of ``modified`` and names happen in ERPNext's database,
so many documents changed at the same instant are not skipped.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from psycopg.types.json import Jsonb

from wqops.erp import ErpClient, ErpError
from wqops.hub import db as DB


@dataclass(frozen=True)
class Spec:
    doctype: str
    full: bool = False  # fetch each document on its own, with its rows (orders, receipts, inspections)


SPECS: tuple[Spec, ...] = (
    Spec("Item"), Spec("Warehouse"), Spec("Customer"), Spec("Supplier"), Spec("Stock Ledger Entry"),
    Spec("Sales Order", full=True), Spec("Delivery Note", full=True), Spec("Purchase Order", full=True),
    Spec("Purchase Receipt", full=True), Spec("Quality Inspection", full=True),
    Spec("Sales Invoice"), Spec("Purchase Invoice"),          # ADR-0018: sales and receivables, payables
)
DELETED = "Deleted Document"
LOCK_ID = 0x5751_0006
PAGE = 100


class SyncBusy(RuntimeError):
    pass


def _hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()


def fetch_page(erp: ErpClient, doctype: str, cursor: tuple[str, str], n: int, *, fields: list[str],
               extra: list | None = None) -> list[dict]:
    """Documents after ``cursor`` (modified, name) in (modified, name) order, at most ``n``."""
    extra = extra or []
    modified, name = cursor
    rows: list[dict] = []
    if modified:
        rows = erp.list(doctype, filters=[*extra, ["modified", "=", modified], ["name", ">", name]], fields=fields,
                        order_by="name asc", limit=n)
    if len(rows) < n:
        later = [*extra, ["modified", ">", modified]] if modified else extra
        rows += erp.list(doctype, filters=later, fields=fields, order_by="modified asc, name asc", limit=n - len(rows))
    return rows


def _cursor(conn, doctype: str) -> tuple[str, str]:
    r = conn.execute("select cursor_modified, cursor_name from erp_sync_state where doctype = %s",
                     (doctype,)).fetchone()
    return (r["cursor_modified"], r["cursor_name"]) if r else ("", "")


def _save_cursor(conn, doctype: str, row: dict) -> None:
    conn.execute("insert into erp_sync_state (doctype, cursor_modified, cursor_name) values (%s, %s, %s) "
                 "on conflict (doctype) do update set cursor_modified = excluded.cursor_modified, "
                 "cursor_name = excluded.cursor_name, updated_at = now()",
                 (doctype, str(row["modified"]), str(row["name"])))


def record(conn, run_id: int | None, doctype: str, doc: dict) -> str | None:
    """Store one document; return the event kind, or None when nothing changed."""
    h = _hash(doc)
    prev = conn.execute("select hash, docstatus, deleted from erp_docs where doctype = %s and name = %s",
                        (doctype, doc["name"])).fetchone()
    if prev and prev["hash"] == h and not prev["deleted"]:
        return None
    ds = int(doc.get("docstatus") or 0)
    if prev is None or prev["deleted"]:
        kind = "created"
    elif ds == 1 and prev["docstatus"] == 0:
        kind = "submitted"
    elif ds == 2 and prev["docstatus"] != 2:
        kind = "cancelled"
    else:
        kind = "updated"
    modified = str(doc.get("modified") or "")
    conn.execute("insert into erp_events (doctype, name, kind, modified, docstatus, data, run_id) "
                 "values (%s, %s, %s, %s, %s, %s, %s)", (doctype, doc["name"], kind, modified, ds, Jsonb(doc), run_id))
    conn.execute("insert into erp_docs (doctype, name, modified, docstatus, deleted, hash, data) "
                 "values (%s, %s, %s, %s, false, %s, %s) on conflict (doctype, name) do update set "
                 "modified = excluded.modified, docstatus = excluded.docstatus, deleted = false, hash = excluded.hash, "
                 "data = excluded.data, synced_at = now()", (doctype, doc["name"], modified, ds, h, Jsonb(doc)))
    return kind


def record_deleted(conn, run_id: int | None, doctype: str, name: str, deleted_at: str) -> bool:
    """Mark a document deleted, unless a newer document with the same name was synced after the deletion."""
    prev = conn.execute("select modified, deleted from erp_docs where doctype = %s and name = %s",
                        (doctype, name)).fetchone()
    if prev is None or prev["deleted"] or prev["modified"] > deleted_at:
        return False
    conn.execute("insert into erp_events (doctype, name, kind, modified, run_id) values (%s, %s, 'deleted', %s, %s)",
                 (doctype, name, deleted_at, run_id))
    conn.execute("update erp_docs set deleted = true, modified = %s, synced_at = now() "
                 "where doctype = %s and name = %s", (deleted_at, doctype, name))
    return True


def _sync_doctype(conn, erp: ErpClient, run_id: int, spec: Spec, page: int) -> int:
    events = 0
    fields = ["name", "modified"] if spec.full else ["*"]
    while True:
        rows = fetch_page(erp, spec.doctype, _cursor(conn, spec.doctype), page, fields=fields)
        if not rows:
            return events
        docs = [erp.get(spec.doctype, r["name"]) for r in rows] if spec.full else rows
        with conn.transaction():
            for d in docs:
                if d is not None and record(conn, run_id, spec.doctype, d):  # None: deleted in between
                    events += 1
            _save_cursor(conn, spec.doctype, rows[-1])
        if len(rows) < page:
            return events


def _sync_deleted(conn, erp: ErpClient, run_id: int, doctypes: list[str], page: int) -> int:
    events = 0
    extra = [["deleted_doctype", "in", doctypes]]
    while True:
        rows = fetch_page(erp, DELETED, _cursor(conn, DELETED), page,
                          fields=["name", "modified", "creation", "deleted_doctype", "deleted_name"], extra=extra)
        if not rows:
            return events
        with conn.transaction():
            for r in rows:
                if record_deleted(conn, run_id, r["deleted_doctype"], r["deleted_name"],
                                  str(r.get("creation") or r["modified"])):
                    events += 1
            _save_cursor(conn, DELETED, rows[-1])
        if len(rows) < page:
            return events


@contextlib.contextmanager
def paused(conn):
    """Hold the sync lock so no run starts meanwhile (waits for a running one), e.g. while a tool writes many
    documents into ERPNext; a run in between would see the business half written."""
    conn.execute("select pg_advisory_lock(%s)", (LOCK_ID,))
    try:
        yield
    finally:
        conn.execute("select pg_advisory_unlock(%s)", (LOCK_ID,))


def run(conn, erp: ErpClient, *, trigger: str = "manual", page: int = PAGE, specs: tuple[Spec, ...] = SPECS) -> dict:
    """Pull every change since the last run. Raises SyncBusy when another run holds the lock."""
    if not conn.execute("select pg_try_advisory_lock(%s) as ok", (LOCK_ID,)).fetchone()["ok"]:
        raise SyncBusy("a sync is already running")
    try:
        run_id = conn.execute("insert into erp_sync_runs (trigger) values (%s) returning id",
                              (trigger,)).fetchone()["id"]
        counts: dict[str, int] = {}
        try:
            for spec in specs:
                counts[spec.doctype] = _sync_doctype(conn, erp, run_id, spec, page)
            counts["deleted"] = _sync_deleted(conn, erp, run_id, [s.doctype for s in specs], page)
        except Exception as exc:
            conn.execute("update erp_sync_runs set status = 'error', counts = %s, error = %s, finished_at = now() "
                         "where id = %s", (Jsonb(counts), f"{type(exc).__name__}: {exc}"[:1000], run_id))
            raise
        conn.execute("update erp_sync_runs set status = 'ok', counts = %s, finished_at = now() where id = %s",
                     (Jsonb(counts), run_id))
        return {"run": run_id, "events": counts}
    finally:
        conn.execute("select pg_advisory_unlock(%s)", (LOCK_ID,))


def status(conn) -> dict:
    cursors = {r["doctype"]: r for r in conn.execute("select * from erp_sync_state").fetchall()}
    docs = {r["doctype"]: r["n"] for r in conn.execute(
        "select doctype, count(*) as n from erp_docs where not deleted group by doctype").fetchall()}
    last = conn.execute("select id, trigger, status, counts, error, started_at, finished_at from erp_sync_runs "
                        "order by id desc limit 1").fetchone()
    if last:
        last = {**last, "started_at": last["started_at"].isoformat(),
                "finished_at": last["finished_at"].isoformat() if last["finished_at"] else None}
    return {
        "doctypes": [{"doctype": s.doctype, "documents": docs.get(s.doctype, 0),
                      "synced_up_to": cursors[s.doctype]["cursor_modified"] if s.doctype in cursors else None}
                     for s in SPECS],
        "events": conn.execute("select count(*) as n from erp_events").fetchone()["n"],
        "last_run": last,
    }


class RecordingTransport(httpx.BaseTransport):
    """Saves every ERPNext reply (not the request headers, so no keys) to numbered JSON files, for replay tests."""

    def __init__(self, out: Path, inner: httpx.BaseTransport | None = None):
        self.out, self.inner, self.n = Path(out), inner or httpx.HTTPTransport(), 0
        self.out.mkdir(parents=True, exist_ok=True)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        resp = self.inner.handle_request(request)
        body = resp.read()
        self.n += 1
        rec = {"method": request.method, "path": request.url.path,
               "params": dict(request.url.params), "status": resp.status_code, "body": json.loads(body or b"null")}
        (self.out / f"{self.n:04d}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n",
                                                     encoding="utf-8")
        headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "content-length",
                                                                                 "transfer-encoding")]
        return httpx.Response(resp.status_code, headers=headers, content=body, request=request)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wqops.hub.sync", description="ERPNext sync (ADR-0006)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="pull changes now")
    r.add_argument("--page", type=int, default=PAGE)
    r.add_argument("--record", type=Path, help="save ERPNext replies to this directory (tests)")
    sub.add_parser("status", help="cursors, document counts and the last run")
    a = ap.parse_args(argv)
    url = os.environ.get("WQO_DB")
    if not url:
        print("WQO_DB is not set", file=sys.stderr)
        return 2
    from wqops.erp_setup import client_from_env  # noqa: PLC0415

    with DB.connect(url) as conn:
        DB.migrate(conn)
        if a.cmd == "status":
            print(json.dumps(status(conn), indent=2, default=str))
            return 0
        erp = client_from_env(RecordingTransport(a.record) if a.record else None)
        try:
            print(json.dumps(run(conn, erp, trigger="command", page=a.page), indent=2))
        except (SyncBusy, ErpError, httpx.HTTPError) as exc:
            print(f"sync failed: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
