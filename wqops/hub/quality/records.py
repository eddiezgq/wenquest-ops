"""Nonconformance reports, 8D and corrective / preventive actions (ADR-0009 items 1-3, ADR-0010).

NCR: open -> contained -> dispositioned -> closed (signed). A disposition type that needs approval goes through
pending_approval and is approved, signed, by someone other than the person who submitted it. A major NCR closes only
when a linked CAPA is closed. Cancelled from any state before closed. 8D: eight sections; completing it is signed.
CAPA: draft -> investigation -> implementation -> effectiveness -> closed (signed by someone other than the owner),
or back to implementation when not effective; cancelled with a reason. One open CAPA per NCR; one CAPA may cover
several NCRs.

Signatures re-enter the signer's own password and are stored in ``signatures``; signatures and ``quality_log`` are
append-only in the database. Rules here are plain code: no AI, no network (ADR-0010; tests/test_isolation.py).
Permission checks by role are the API's job; separation of duties and action owners are checked here.
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub import accounts as A
from wqops.hub.quality import workflow as W

SECTIONS = {"d1": "D1 Team", "d2": "D2 Problem description", "d3": "D3 Containment", "d4": "D4 Root cause",
            "d5": "D5 Corrective actions", "d6": "D6 Implementation and verification", "d7": "D7 Prevent recurrence",
            "d8": "D8 Closure and recognition"}
RISKS = ("low", "medium", "high")
ACTION_KINDS = ("correction", "corrective", "preventive")
OPEN_CAPA = ("draft", "investigation", "implementation", "effectiveness")
SYSTEM = "WenQuest Ops (automatic)"


class QualityError(ValueError):
    pass


class SignatureError(PermissionError):
    pass


def log(conn, kind: str, ref_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into quality_log (kind, ref_id, email, action, note) values (%s, %s, %s, %s, %s)",
                 (kind, ref_id, email, action, (note or "")[:2000]))


def history(conn, kind: str, ref_id: int) -> list[dict]:
    rows = conn.execute("select at, email, action, note from quality_log where kind = %s and ref_id = %s order by id",
                        (kind, ref_id)).fetchall()
    return [dict(r, at=r["at"].isoformat()) for r in rows]


def signatures(conn, kind: str, ref_id: int) -> list[dict]:
    rows = conn.execute("select at, email, name, meaning from signatures where kind = %s and ref_id = %s order by id",
                        (kind, ref_id)).fetchall()
    return [dict(r, at=r["at"].isoformat()) for r in rows]


def check_signer(conn, user: dict, password: str) -> None:
    """The signer re-enters their own password; checked before anything changes."""
    if not user.get("password_hash"):
        raise SignatureError("set a password in WenQuest Ops first: signatures need your own password")
    if not A.check_password(password or "", user["password_hash"]):
        A.event(conn, user["email"], "signature_failed")
        raise SignatureError("password is wrong; nothing was signed")


def _sign(conn, user: dict, meaning: str, kind: str, ref_id: int, ref_name: str) -> None:
    conn.execute("insert into signatures (email, name, meaning, kind, ref_id, ref_name) "
                 "values (%s, %s, %s, %s, %s, %s)", (user["email"], user["name"], meaning, kind, ref_id, ref_name))


def _next_name(conn, table: str, prefix: str, digits: int = 5) -> str:
    """The next number. Called inside the creating transaction: the lock (held until it ends) keeps two records
    created at the same time from getting the same number (issue #52)."""
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-number:{table}",))
    n = conn.execute(f"select coalesce(max(id), 0) + 1 as n from {table}").fetchone()["n"]  # noqa: S608 - fixed names
    return f"{prefix}-{n:0{digits}d}"


def new_name(conn, kind: str) -> tuple[str, int]:
    """(number, workflow version id) for a new record of ``kind``: numbered and run by the enabled workflow."""
    v = W.ensure(conn, kind)
    num = v["config"]["numbering"]
    return _next_name(conn, W.KINDS[kind], num["prefix"], int(num["digits"])), v["id"]


def _step(conn, kind: str, row: dict, step: str, user: dict | None, facts: dict | None = None,
          explain: dict | None = None) -> tuple[dict, dict]:
    """The workflow of the record and the step's rules, after the workflow's checks (ADR-0015)."""
    cfg = W.of(conn, kind, row)
    who = {"email": user["email"]} if user else None     # roles are checked by the API (module docstring)
    try:
        return cfg, W.check(cfg, row, step, who, facts, explain=explain)
    except W.StepError as exc:
        raise QualityError(str(exc)) from exc


# ---------------------------------------------------------------- disposition types (configuration)

def disposition_types(conn, active_only: bool = True) -> dict[str, dict]:
    rows = conn.execute("select * from ncr_disposition_types where active or not %s order by sort, code",
                        (active_only,)).fetchall()
    return {r["code"]: r for r in rows}


def save_disposition_type(conn, email: str, code: str, name: str, requires_approval: bool, active: bool = True) -> dict:
    if not code.strip() or not code.replace("_", "").isalnum() or not name.strip():
        raise QualityError("a disposition type needs a code (letters, digits, _) and a name")
    row = conn.execute("insert into ncr_disposition_types (code, name, requires_approval, active, sort) values "
                       "(%s, %s, %s, %s, (select coalesce(max(sort), 0) + 1 from ncr_disposition_types)) "
                       "on conflict (code) do update set name = excluded.name, requires_approval = "
                       "excluded.requires_approval, active = excluded.active returning *",
                       (code.strip(), name.strip(), bool(requires_approval), bool(active))).fetchone()
    A.event(conn, email, "disposition_type_saved", f"{code}: {name}, approval {requires_approval}, active {active}")
    return row


# ---------------------------------------------------------------- NCR

def create_ncr(conn, email: str, *, title: str, description: str, severity: str = "minor", owner: str | None = None,
               inspection: str | None = None, item_code: str | None = None, receipt: str | None = None,
               supplier: str | None = None, quantity: float | None = None, draft_id: int | None = None) -> dict:
    if not title.strip() or not description.strip():
        raise QualityError("a nonconformance report needs a title and a description")
    if severity not in ("minor", "major"):
        raise QualityError("severity is minor or major")
    if quantity is not None and float(quantity) <= 0:
        raise QualityError("quantity must be above 0")
    with conn.transaction():
        if inspection and conn.execute("select 1 from ncr_records where inspection = %s and status <> 'cancelled'",
                                       (inspection,)).fetchone():
            raise QualityError(f"inspection {inspection} already has a nonconformance report")
        name, wf = new_name(conn, "ncr")
        row = conn.execute(
            "insert into ncr_records (name, draft_id, title, description, inspection, item_code, receipt, supplier, "
            "quantity, severity, owner, created_by, workflow_version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s) returning *",
            (name, draft_id, title.strip(), description.strip(), inspection, item_code, receipt, supplier, quantity,
             severity, owner if owner is not None or email == SYSTEM else email, email, wf)).fetchone()
        log(conn, "ncr", row["id"], email, "opened", title)
    return row


def ncr(conn, ncr_id: int) -> dict:
    row = conn.execute("select * from ncr_records where id = %s", (ncr_id,)).fetchone()
    if row is None:
        raise KeyError(ncr_id)
    return row


def _need(row: dict, *states: str) -> None:
    if row["status"] not in states:
        raise QualityError(f"{row['name']} is {row['status'].replace('_', ' ')}; this step needs it to be "
                           f"{' or '.join(s.replace('_', ' ') for s in states)}")


def _set(conn, table: str, row_id: int, **cols) -> dict:
    sets = ", ".join(f"{k} = %s" for k in cols)
    return conn.execute(f"update {table} set {sets}, updated_at = now() where id = %s returning *",  # noqa: S608
                        (*cols.values(), row_id)).fetchone()


def update_ncr(conn, ncr_id: int, email: str, **fields) -> dict:
    """Owner and severity can change while the report is not closed or cancelled."""
    row = ncr(conn, ncr_id)
    _step(conn, "ncr", row, "update", None)
    cols = {k: v for k, v in fields.items() if k in ("owner", "severity") and v is not None}
    if cols.get("severity") not in (None, "minor", "major"):
        raise QualityError("severity is minor or major")
    if not cols:
        return row
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, **cols)
        log(conn, "ncr", ncr_id, email, "updated", ", ".join(f"{k}: {v}" for k, v in cols.items()))
    return row


def contain(conn, ncr_id: int, email: str, containment: str) -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "contain", None, {"containment": containment.strip()},
                   {"containment": "describe the containment (what was done to stop bad parts going further)"})
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "contain"), containment=containment.strip())
        log(conn, "ncr", ncr_id, email, "contained", containment)
    return row


def submit_disposition(conn, ncr_id: int, email: str, code: str, quantity: float | None, reason: str) -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "disposition", None,
                   {"disposition": code, "disposition_qty": quantity if quantity is None or float(quantity) > 0 else 0,
                    "disposition_reason": reason.strip()},
                   {"disposition_reason": "give the reason for this disposition",
                    "disposition_qty": "give the quantity this disposition covers"})
    types = disposition_types(conn)
    if code not in types:
        raise QualityError(f"disposition is one of: {', '.join(types)}")
    if row["quantity"] is not None and float(quantity) > float(row["quantity"]):
        raise QualityError(f"the quantity cannot exceed the report's {float(row['quantity']):g}")
    needs = types[code]["requires_approval"]
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "disposition", needs),
                   disposition=code, disposition_qty=quantity, disposition_reason=reason.strip(), disposition_by=email)
        log(conn, "ncr", ncr_id, email, "disposition submitted",
            f"{types[code]['name']}, {float(quantity):g}: {reason}" + (" (needs approval)" if needs else ""))
    return row


def approve_disposition(conn, ncr_id: int, user: dict, password: str) -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "approve", user)
    check_signer(conn, user, password)
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "approve"), approved_by=user["email"],
                   approved_at=dt.datetime.now(dt.UTC))
        _sign(conn, user, W.signed(cfg, "approve"), "ncr", ncr_id, row["name"])
        log(conn, "ncr", ncr_id, user["email"], "disposition approved")
    return row


def reject_disposition(conn, ncr_id: int, email: str, reason: str) -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "reject_disposition", None)
    if not reason.strip():
        raise QualityError("say why the disposition is not approved")
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "reject_disposition"), disposition=None,
                   disposition_qty=None,
                   disposition_reason=None, disposition_by=None)
        log(conn, "ncr", ncr_id, email, "disposition not approved", reason)
    return row


def close_ncr(conn, ncr_id: int, user: dict, password: str, note: str = "") -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "close", user)
    if row["severity"] is None:
        raise QualityError(f"{row['name']} has no severity (its ledger did not say); set minor or major first")
    if row["severity"] in W.rule(cfg, "capa_closed_before_close", []) and not conn.execute(
            "select 1 from capa_ncrs l join capas c on c.id = l.capa_id where l.ncr_id = %s and c.status = 'closed'",
            (ncr_id,)).fetchone():
        raise QualityError(f"{row['name']} is {row['severity']}: it closes when a linked corrective action is closed")
    if row["severity"] in W.rule(cfg, "eight_d_before_close", []) and not conn.execute(
            "select 1 from eightd where ncr_id = %s and complete", (ncr_id,)).fetchone():
        raise QualityError(f"{row['name']} is {row['severity']}: it closes when its 8D is complete")
    check_signer(conn, user, password)
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "close"), closed_by=user["email"],
                   closed_at=dt.datetime.now(dt.UTC))
        _sign(conn, user, W.signed(cfg, "close"), "ncr", ncr_id, row["name"])
        log(conn, "ncr", ncr_id, user["email"], "closed", note)
    return row


def cancel_ncr(conn, ncr_id: int, email: str, reason: str) -> dict:
    row = ncr(conn, ncr_id)
    cfg, _ = _step(conn, "ncr", row, "cancel", None)
    if not reason.strip():
        raise QualityError("say why the report is cancelled")
    with conn.transaction():
        row = _set(conn, "ncr_records", ncr_id, status=W.target(cfg, "cancel"), cancel_reason=reason.strip())
        log(conn, "ncr", ncr_id, email, "cancelled", reason)
    return row


# ---------------------------------------------------------------- 8D

def save_8d(conn, ncr_id: int, email: str, sections: dict) -> dict:
    row = ncr(conn, ncr_id)
    if row["status"] in ("closed", "cancelled"):
        raise QualityError(f"{row['name']} is {row['status']}; its 8D cannot change")
    bad = [k for k in sections if k not in SECTIONS]
    if bad:
        raise QualityError(f"unknown 8D sections: {', '.join(bad)}")
    cur = conn.execute("select * from eightd where ncr_id = %s", (ncr_id,)).fetchone()
    if cur and cur["complete"]:
        raise QualityError("this 8D is complete; it cannot be changed")
    merged = {**(cur["sections"] if cur else {}), **{k: str(v).strip() for k, v in sections.items()}}
    with conn.transaction():
        out = conn.execute("insert into eightd (ncr_id, sections) values (%s, %s) on conflict (ncr_id) do update set "
                           "sections = excluded.sections, updated_at = now() returning *",
                           (ncr_id, Jsonb(merged))).fetchone()
        log(conn, "ncr", ncr_id, email, "8d saved", ", ".join(sorted(sections)))
    return out


def complete_8d(conn, ncr_id: int, user: dict, password: str) -> dict:
    row = ncr(conn, ncr_id)
    cur = conn.execute("select * from eightd where ncr_id = %s", (ncr_id,)).fetchone()
    if cur and cur["complete"]:
        raise QualityError("this 8D is already complete")
    cfg, _ = _step(conn, "ncr", row, "complete_8d", user)
    missing = [SECTIONS[k] for k in SECTIONS if not (cur and cur["sections"].get(k))]
    if missing:
        raise QualityError("still to write: " + ", ".join(missing))
    check_signer(conn, user, password)
    with conn.transaction():
        out = conn.execute("update eightd set complete = true, completed_by = %s, completed_at = now() "
                           "where ncr_id = %s returning *", (user["email"], ncr_id)).fetchone()
        _sign(conn, user, W.signed(cfg, "complete_8d"), "ncr", ncr_id, row["name"])
        log(conn, "ncr", ncr_id, user["email"], "8d complete")
    return out


# ---------------------------------------------------------------- CAPA

def create_capa(conn, email: str, *, kind: str, title: str, description: str = "", ncr_ids: list[int] | None = None,
                owner: str | None = None, risk: str | None = None) -> dict:
    if kind not in ("corrective", "preventive"):
        raise QualityError("kind is corrective or preventive")
    if not title.strip():
        raise QualityError("a corrective / preventive action needs a title")
    if risk is not None and risk not in RISKS:
        raise QualityError(f"risk is one of: {', '.join(RISKS)}")
    with conn.transaction():
        name, wf = new_name(conn, "capa")
        initial = W.version(conn, "capa", wf)["config"]["initial"]
        row = conn.execute("insert into capas (name, kind, title, description, owner, risk, created_by, status, "
                           "workflow_version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (name, kind, title.strip(), description, owner or email, risk, email, initial,
                            wf)).fetchone()
        log(conn, "capa", row["id"], email, "opened", title)
        for n in ncr_ids or []:
            _link(conn, row, n, email)
    return row


def _link(conn, c: dict, ncr_id: int, email: str) -> None:
    n = ncr(conn, ncr_id)
    other = conn.execute("select c.name from capa_ncrs l join capas c on c.id = l.capa_id where l.ncr_id = %s and "
                         "c.status = any(%s) and c.id <> %s", (ncr_id, list(OPEN_CAPA), c["id"])).fetchone()
    if other:
        raise QualityError(f"{n['name']} already has an open corrective action, {other['name']}; use that one")
    conn.execute("insert into capa_ncrs (capa_id, ncr_id) values (%s, %s) on conflict do nothing", (c["id"], ncr_id))
    log(conn, "capa", c["id"], email, "nonconformance linked", n["name"])
    log(conn, "ncr", ncr_id, email, "capa linked", c["name"])


def link_ncr(conn, capa_id: int, ncr_id: int, email: str) -> dict:
    c = capa(conn, capa_id)
    _need(c, *OPEN_CAPA)
    with conn.transaction():
        _link(conn, c, ncr_id, email)
    return c


def capa(conn, capa_id: int) -> dict:
    row = conn.execute("select * from capas where id = %s", (capa_id,)).fetchone()
    if row is None:
        raise KeyError(capa_id)
    return row


def capa_ncrs(conn, capa_id: int) -> list[dict]:
    return conn.execute("select n.id, n.name, n.title, n.status from capa_ncrs l join ncr_records n on n.id = l.ncr_id "
                        "where l.capa_id = %s order by n.id", (capa_id,)).fetchall()


def actions(conn, capa_id: int) -> list[dict]:
    return conn.execute("select * from capa_actions where capa_id = %s order by id", (capa_id,)).fetchall()


EDITABLE = {"draft": ("title", "description", "owner", "risk"),
            "investigation": ("description", "owner", "risk", "containment", "root_cause"),
            "implementation": ("owner",)}


def update_capa(conn, capa_id: int, email: str, **fields) -> dict:
    c = capa(conn, capa_id)
    allowed = EDITABLE.get(c["status"], ())
    cols = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items() if v is not None}
    bad = [k for k in cols if k not in allowed]
    if bad:
        raise QualityError(f"{c['name']} is {c['status']}: {', '.join(bad)} cannot change now")
    if cols.get("risk") not in (None, *RISKS):
        raise QualityError(f"risk is one of: {', '.join(RISKS)}")
    if not cols:
        return c
    with conn.transaction():
        c = _set(conn, "capas", capa_id, **cols)
        log(conn, "capa", capa_id, email, "updated", ", ".join(sorted(cols)))
    return c


def _move(conn, c: dict, to: str, email: str, note: str = "", **cols) -> dict:
    out = _set(conn, "capas", c["id"], status=to, **cols)
    log(conn, "capa", c["id"], email, to, note)
    return out


def submit_capa(conn, capa_id: int, email: str) -> dict:
    """Draft -> investigation: needs the problem, an owner and a risk level."""
    c = capa(conn, capa_id)
    cfg, _ = _step(conn, "capa", c, "submit", None)
    with conn.transaction():
        return _move(conn, c, W.target(cfg, "submit"), email)


def plan_actions(conn, capa_id: int, email: str) -> dict:
    """Investigation -> implementation: needs containment, root cause and at least one action."""
    c = capa(conn, capa_id)
    cfg, _ = _step(conn, "capa", c, "plan", None, {"actions": bool(actions(conn, capa_id))})
    with conn.transaction():
        return _move(conn, c, W.target(cfg, "plan"), email)


def add_action(conn, capa_id: int, email: str, text: str, owner: str | None = None, due: str | None = None,
               kind: str = "corrective", today: dt.date | None = None) -> dict:
    c = capa(conn, capa_id)
    if c["status"] not in ("draft", "investigation", "implementation"):
        raise QualityError(f"{c['name']} is {c['status']}; actions can be added during investigation and "
                           "implementation")
    if not text.strip():
        raise QualityError("describe the action")
    if kind not in ACTION_KINDS:
        raise QualityError(f"action kind is one of: {', '.join(ACTION_KINDS)}")
    try:
        due_d = dt.date.fromisoformat(due) if due else None
    except ValueError as exc:
        raise QualityError("due must be a date like 2026-10-31") from exc
    if due_d and due_d < (today or dt.datetime.now(dt.UTC).date()):
        raise QualityError("the due date cannot be in the past")
    with conn.transaction():
        row = conn.execute("insert into capa_actions (capa_id, text, owner, due, kind) values (%s, %s, %s, %s, %s) "
                           "returning *", (capa_id, text.strip(), owner, due_d, kind)).fetchone()
        log(conn, "capa", capa_id, email, "action added", f"{kind}: {text}")
    return row


def action_done(conn, action_id: int, email: str, may_edit: bool, evidence: str) -> dict:
    a = conn.execute("select * from capa_actions where id = %s", (action_id,)).fetchone()
    if a is None:
        raise KeyError(action_id)
    if not may_edit and a["owner"] != email:
        raise PermissionError("only the action's owner or Quality can mark it done")
    if a["done"]:
        raise QualityError("already done")
    c = capa(conn, a["capa_id"])
    if c["status"] not in ("investigation", "implementation"):
        raise QualityError(f"{c['name']} is {c['status']}; actions are done during investigation or implementation")
    if not (evidence or "").strip():
        raise QualityError("describe the evidence that the action was done")
    with conn.transaction():
        a = conn.execute("update capa_actions set done = true, done_by = %s, done_at = now(), evidence = %s "
                         "where id = %s returning *", (email, evidence.strip(), action_id)).fetchone()
        log(conn, "capa", a["capa_id"], email, "action done", f"{a['text']}: {evidence}")
    return a


def to_effectiveness(conn, capa_id: int, email: str) -> dict:
    c = capa(conn, capa_id)
    open_ = [a["text"] for a in actions(conn, capa_id) if not a["done"]]
    cfg, _ = _step(conn, "capa", c, "to_effectiveness", None, {"actions_done": not open_},
                   {"actions_done": "actions not done yet: " + "; ".join(open_)})
    with conn.transaction():
        return _move(conn, c, W.target(cfg, "to_effectiveness"), email)


def effectiveness(conn, capa_id: int, user: dict, password: str, result: str, evidence: str) -> dict:
    """Effective: closed, signed by someone other than the owner. Not effective: back to implementation."""
    c = capa(conn, capa_id)
    if result not in ("effective", "ineffective"):
        _step(conn, "capa", c, "effective", None, {"evidence": "-"})      # the state first, as for every step
        raise QualityError("result is effective or ineffective")
    step = "effective" if result == "effective" else "not_effective"
    cfg, _ = _step(conn, "capa", c, step, user, {"evidence": evidence.strip()},
                   {"evidence": "give the evidence (data, period) for the effectiveness check"})
    now = dt.datetime.now(dt.UTC)
    if result == "ineffective":
        with conn.transaction():
            return _move(conn, c, W.target(cfg, step), user["email"], f"Not effective. Reason: {evidence}",
                         verification_result="ineffective", verification_method=evidence.strip(),
                         verified_by=user["email"], verified_at=now)
    check_signer(conn, user, password)
    with conn.transaction():
        out = _move(conn, c, W.target(cfg, step), user["email"], f"Effective: {evidence}",
                    verification_result="effective", verification_method=evidence.strip(), verified_by=user["email"],
                    verified_at=now, closed_by=user["email"], closed_at=now)
        _sign(conn, user, W.signed(cfg, step), "capa", capa_id, c["name"])
    return out


def cancel_capa(conn, capa_id: int, email: str, reason: str) -> dict:
    c = capa(conn, capa_id)
    cfg, _ = _step(conn, "capa", c, "cancel", None)
    if not reason.strip():
        raise QualityError("say why it is cancelled")
    with conn.transaction():
        return _move(conn, c, W.target(cfg, "cancel"), email, reason, cancel_reason=reason.strip())
