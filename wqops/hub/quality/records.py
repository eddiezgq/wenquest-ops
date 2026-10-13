"""Nonconformance reports, 8D and corrective / preventive actions (ADR-0009 items 1-3).

NCR: open -> contained -> dispositioned -> closed; cancelled from any state before closed. A major NCR closes only
when a linked CAPA is closed. 8D: eight sections; complete when all are written, D6 (verification) included.
CAPA: open -> in_progress -> verification -> closed (effective) or back to in_progress (ineffective).
Every step is written to quality_log. Permission checks are the caller's job (the API), except action owners.
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

DISPOSITIONS = {"use_as_is": "Use as is", "rework": "Rework", "return_to_supplier": "Return to supplier",
                "scrap": "Scrap"}
SECTIONS = {"d1": "D1 Team", "d2": "D2 Problem description", "d3": "D3 Containment", "d4": "D4 Root cause",
            "d5": "D5 Corrective actions", "d6": "D6 Implementation and verification", "d7": "D7 Prevent recurrence",
            "d8": "D8 Closure and recognition"}


class QualityError(ValueError):
    pass


def log(conn, kind: str, ref_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into quality_log (kind, ref_id, email, action, note) values (%s, %s, %s, %s, %s)",
                 (kind, ref_id, email, action, (note or "")[:2000]))


def history(conn, kind: str, ref_id: int) -> list[dict]:
    rows = conn.execute("select at, email, action, note from quality_log where kind = %s and ref_id = %s order by id",
                        (kind, ref_id)).fetchall()
    return [dict(r, at=r["at"].isoformat()) for r in rows]


def _next_name(conn, table: str, prefix: str) -> str:
    n = conn.execute(f"select coalesce(max(id), 0) + 1 as n from {table}").fetchone()["n"]  # noqa: S608 - fixed names
    return f"{prefix}-{n:05d}"


# ---------------------------------------------------------------- NCR

def create_ncr(conn, email: str, *, title: str, description: str, severity: str = "minor", owner: str | None = None,
               inspection: str | None = None, item_code: str | None = None, receipt: str | None = None,
               supplier: str | None = None, quantity: float | None = None, draft_id: int | None = None) -> dict:
    if not title.strip() or not description.strip():
        raise QualityError("a nonconformance report needs a title and a description")
    if severity not in ("minor", "major"):
        raise QualityError("severity is minor or major")
    if quantity is not None and float(quantity) < 0:
        raise QualityError("quantity cannot be negative")
    with conn.transaction():
        name = _next_name(conn, "ncr_records", "NCR")
        row = conn.execute(
            "insert into ncr_records (name, draft_id, title, description, inspection, item_code, receipt, supplier, "
            "quantity, severity, owner, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "returning *",
            (name, draft_id, title.strip(), description.strip(), inspection, item_code, receipt, supplier, quantity,
             severity, owner or email, email)).fetchone()
        log(conn, "ncr", row["id"], email, "opened", title)
    return row


def ncr(conn, ncr_id: int) -> dict:
    row = conn.execute("select * from ncr_records where id = %s", (ncr_id,)).fetchone()
    if row is None:
        raise KeyError(ncr_id)
    return row


def _move(conn, ncr_id: int, frm: tuple[str, ...], to: str, email: str, note: str, **cols) -> dict:
    row = ncr(conn, ncr_id)
    if row["status"] not in frm:
        raise QualityError(f"{row['name']} is {row['status']}; this step needs it to be {' or '.join(frm)}")
    sets = ", ".join(f"{k} = %s" for k in cols)
    with conn.transaction():
        row = conn.execute(f"update ncr_records set status = %s, updated_at = now(){', ' + sets if sets else ''} "  # noqa: S608
                           "where id = %s returning *", (to, *cols.values(), ncr_id)).fetchone()
        log(conn, "ncr", ncr_id, email, to, note)
    return row


def contain(conn, ncr_id: int, email: str, containment: str) -> dict:
    if not containment.strip():
        raise QualityError("describe the containment (what was done to stop bad parts going further)")
    return _move(conn, ncr_id, ("open",), "contained", email, containment, containment=containment.strip())


def disposition(conn, ncr_id: int, email: str, how: str, quantity: float | None = None, note: str = "") -> dict:
    if how not in DISPOSITIONS:
        raise QualityError(f"disposition is one of: {', '.join(DISPOSITIONS)}")
    if quantity is not None and float(quantity) < 0:
        raise QualityError("quantity cannot be negative")
    return _move(conn, ncr_id, ("contained",), "dispositioned", email, f"{DISPOSITIONS[how]}. {note}".strip(),
                 disposition=how, disposition_qty=quantity, disposition_by=email)


def close_ncr(conn, ncr_id: int, email: str, note: str = "") -> dict:
    row = ncr(conn, ncr_id)
    if row["severity"] == "major":
        done = conn.execute("select 1 from capas where ncr_id = %s and status = 'closed'", (ncr_id,)).fetchone()
        if not done:
            raise QualityError(f"{row['name']} is major: it closes when a linked corrective action is closed")
    return _move(conn, ncr_id, ("dispositioned",), "closed", email, note, closed_at=dt.datetime.now(dt.UTC))


def cancel_ncr(conn, ncr_id: int, email: str, reason: str) -> dict:
    if not reason.strip():
        raise QualityError("say why the report is cancelled")
    return _move(conn, ncr_id, ("open", "contained", "dispositioned"), "cancelled", email, reason,
                 cancel_reason=reason.strip())


# ---------------------------------------------------------------- 8D

def save_8d(conn, ncr_id: int, email: str, sections: dict) -> dict:
    ncr(conn, ncr_id)
    bad = [k for k in sections if k not in SECTIONS]
    if bad:
        raise QualityError(f"unknown 8D sections: {', '.join(bad)}")
    cur = conn.execute("select * from eightd where ncr_id = %s", (ncr_id,)).fetchone()
    if cur and cur["complete"]:
        raise QualityError("this 8D is complete; it cannot be changed")
    merged = {**(cur["sections"] if cur else {}), **{k: str(v).strip() for k, v in sections.items()}}
    with conn.transaction():
        row = conn.execute("insert into eightd (ncr_id, sections) values (%s, %s) on conflict (ncr_id) do update set "
                           "sections = excluded.sections, updated_at = now() returning *",
                           (ncr_id, Jsonb(merged))).fetchone()
        log(conn, "ncr", ncr_id, email, "8d saved", ", ".join(sorted(sections)))
    return row


def complete_8d(conn, ncr_id: int, email: str) -> dict:
    cur = conn.execute("select * from eightd where ncr_id = %s", (ncr_id,)).fetchone()
    missing = [SECTIONS[k] for k in SECTIONS if not (cur and cur["sections"].get(k))]
    if missing:
        raise QualityError("still to write: " + ", ".join(missing))
    with conn.transaction():
        row = conn.execute("update eightd set complete = true, completed_by = %s, completed_at = now() "
                           "where ncr_id = %s returning *", (email, ncr_id)).fetchone()
        log(conn, "ncr", ncr_id, email, "8d complete")
    return row


# ---------------------------------------------------------------- CAPA

def create_capa(conn, email: str, *, kind: str, title: str, description: str = "", ncr_id: int | None = None,
                owner: str | None = None, actions: list[dict] | None = None) -> dict:
    if kind not in ("corrective", "preventive"):
        raise QualityError("kind is corrective or preventive")
    if not title.strip():
        raise QualityError("a corrective / preventive action needs a title")
    if ncr_id is not None:
        ncr(conn, ncr_id)
    with conn.transaction():
        name = _next_name(conn, "capas", "CAPA")
        row = conn.execute("insert into capas (name, kind, title, description, ncr_id, owner, created_by) values "
                           "(%s, %s, %s, %s, %s, %s, %s) returning *",
                           (name, kind, title.strip(), description, ncr_id, owner or email, email)).fetchone()
        log(conn, "capa", row["id"], email, "opened", title)
        if ncr_id is not None:
            log(conn, "ncr", ncr_id, email, "capa linked", name)
        for a in actions or []:
            add_action(conn, row["id"], email, a.get("text", ""), a.get("owner"), a.get("due"))
    return row


def capa(conn, capa_id: int) -> dict:
    row = conn.execute("select * from capas where id = %s", (capa_id,)).fetchone()
    if row is None:
        raise KeyError(capa_id)
    return row


def actions(conn, capa_id: int) -> list[dict]:
    return conn.execute("select * from capa_actions where capa_id = %s order by id", (capa_id,)).fetchall()


def add_action(conn, capa_id: int, email: str, text: str, owner: str | None = None, due: str | None = None) -> dict:
    c = capa(conn, capa_id)
    if c["status"] in ("verification", "closed"):
        raise QualityError(f"{c['name']} is {c['status']}; actions can no longer be added")
    if not text.strip():
        raise QualityError("describe the action")
    try:
        due_d = dt.date.fromisoformat(due) if due else None
    except ValueError as exc:
        raise QualityError("due must be a date like 2026-10-31") from exc
    row = conn.execute("insert into capa_actions (capa_id, text, owner, due) values (%s, %s, %s, %s) returning *",
                       (capa_id, text.strip(), owner, due_d)).fetchone()
    log(conn, "capa", capa_id, email, "action added", text)
    return row


def action_done(conn, action_id: int, email: str, may_edit: bool) -> dict:
    a = conn.execute("select * from capa_actions where id = %s", (action_id,)).fetchone()
    if a is None:
        raise KeyError(action_id)
    if not may_edit and a["owner"] != email:
        raise PermissionError("only the action's owner or Quality can mark it done")
    if a["done"]:
        raise QualityError("already done")
    with conn.transaction():
        a = conn.execute("update capa_actions set done = true, done_by = %s, done_at = now() where id = %s "
                         "returning *", (email, action_id)).fetchone()
        log(conn, "capa", a["capa_id"], email, "action done", a["text"])
    return a


def _capa_move(conn, capa_id: int, frm: tuple[str, ...], to: str, email: str, note: str = "", **cols) -> dict:
    c = capa(conn, capa_id)
    if c["status"] not in frm:
        raise QualityError(f"{c['name']} is {c['status']}; this step needs it to be {' or '.join(frm)}")
    sets = "".join(f", {k} = %s" for k in cols)
    with conn.transaction():
        c = conn.execute(f"update capas set status = %s, updated_at = now(){sets} where id = %s returning *",  # noqa: S608
                         (to, *cols.values(), capa_id)).fetchone()
        log(conn, "capa", capa_id, email, to, note)
    return c


def start_capa(conn, capa_id: int, email: str) -> dict:
    return _capa_move(conn, capa_id, ("open",), "in_progress", email)


def to_verification(conn, capa_id: int, email: str) -> dict:
    c = capa(conn, capa_id)
    if c["status"] != "in_progress":
        raise QualityError(f"{c['name']} is {c['status']}; this step needs it to be in_progress")
    acts = actions(conn, capa_id)
    if not acts:
        raise QualityError("add at least one action first")
    open_ = [a["text"] for a in acts if not a["done"]]
    if open_:
        raise QualityError("actions not done yet: " + "; ".join(open_))
    return _capa_move(conn, capa_id, ("in_progress",), "verification", email)


def verify(conn, capa_id: int, email: str, result: str, method: str) -> dict:
    if result not in ("effective", "ineffective"):
        raise QualityError("result is effective or ineffective")
    if not method.strip():
        raise QualityError("say how effectiveness was checked")
    now = dt.datetime.now(dt.UTC)
    to = "closed" if result == "effective" else "in_progress"
    extra = {"closed_at": now} if to == "closed" else {}
    return _capa_move(conn, capa_id, ("verification",), to, email, f"{result}: {method}", verification_method=method,
                      verification_result=result, verified_by=email, verified_at=now, **extra)
