"""Complaints, step 17e (ADR-0017; dee-qms PLAN-COMPLAINT).

A complaint is recorded, investigated (or, with an approved reason, not), assessed for reporting by someone other
than its owner who answers three questions and decides, signed (WenQuest Ops only shows the deadline and asks the
questions; it never decides), reported by a person outside WenQuest Ops with the reference entered here, answered,
and closed with a signature by someone other than the owner. A nonconformance report or a corrective action can be
opened from it. Nothing is deleted; a duplicate or something that is not a complaint is cancelled with a reason.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.quality import complaint_rules as CR
from wqops.hub.quality import records as Q

SOURCES = ("customer", "distributor", "field", "other")
YNU = ("yes", "no", "unknown")
EDITABLE = {"received_on", "aware_on", "source", "customer", "contact", "item_code", "lot_no", "quantity",
            "description", "injury", "malfunction", "owner", "root_cause", "investigation", "response", "report_ref",
            "reported_on"}
BEFORE_ASSESSMENT = {"received_on", "aware_on", "description", "injury", "malfunction", "item_code", "root_cause",
                     "investigation"}


class ComplaintError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return {k: (float(v) if k == "quantity" and v is not None else v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in row.items()}


def log(conn, cid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into complaint_log (complaint_id, email, action, note) values (%s, %s, %s, %s)",
                 (cid, email, action, (note or "")[:2000]))


def history(conn, cid: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select at, email, action, note from complaint_log where complaint_id = %s "
                                          "order by id", (cid,)).fetchall()]


def get(conn, cid: int) -> dict:
    row = conn.execute("select * from complaints where id = %s", (cid,)).fetchone()
    if row is None:
        raise KeyError(cid)
    return row


def _day(v, what: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise ComplaintError(f"{what} is a date like 2026-10-31") from exc


def _clean(conn, data: dict, today: dt.date) -> dict:  # noqa: PLR0912 - one branch per kind of field
    out = {}
    for k, v in data.items():
        if k not in EDITABLE:
            raise ComplaintError(f"a complaint has no field {k!r} to change")
        if k in ("received_on", "aware_on", "reported_on"):
            out[k] = _day(v, k.replace("_", " "))
            if out[k] and out[k] > today:
                raise ComplaintError(f"{k.replace('_', ' ')} cannot be after today")
        elif k == "source":
            if v not in SOURCES:
                raise ComplaintError("the source is customer, distributor, field or other")
            out[k] = v
        elif k in ("injury", "malfunction"):
            if v not in YNU:
                raise ComplaintError(f"{k}: yes, no or unknown")
            out[k] = v
        elif k == "quantity":
            if v in (None, ""):
                out[k] = None
            else:
                try:
                    q = float(v)
                except (TypeError, ValueError) as exc:
                    raise ComplaintError("the quantity is a number") from exc
                if not q > 0:
                    raise ComplaintError("the quantity is above 0")
                out[k] = q
        elif k == "owner":
            o = str(v or "").strip().lower() or None
            if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
                raise ComplaintError(f"{o} is not a person in the company")
            out[k] = o
        else:
            out[k] = str(v or "").strip()[:4000] or ("" if k != "item_code" else None)
    return out


def create(conn, email: str, data: dict, *, today: dt.date) -> dict:
    d = _clean(conn, data, today)
    for need, what in (("received_on", "the day it was received"), ("customer", "the customer"),
                       ("description", "what happened")):
        if not d.get(need):
            raise ComplaintError(f"give {what}")
    d.setdefault("aware_on", d["received_on"])
    if d["aware_on"] is None:
        d["aware_on"] = d["received_on"]
    with conn.transaction():
        name = Q._next_name(conn, "complaints", "CMP")
        cols = ["name", "created_by", *d]
        row = conn.execute(f"insert into complaints ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *", [name, email, *d.values()]).fetchone()
        log(conn, row["id"], email, "received", f"from {row['customer']} on {row['received_on']}")
    return row


def update(conn, user: dict, cid: int, data: dict, *, today: dt.date) -> dict:
    """Change details while the complaint is open; what the reporting decision rests on is fixed once assessed;
    the owner changes, once the investigation has started, only by someone who configures the quality system."""
    from wqops.hub import permissions as P  # noqa: PLC0415 - permissions are a plain table

    c = get(conn, cid)
    if c["status"] in ("closed", "cancelled"):
        raise ComplaintError(f"the complaint is {c['status']}")
    d = _clean(conn, data, today)
    if c["status"] == "assessed" and set(d) & BEFORE_ASSESSMENT:
        raise ComplaintError("the complaint is assessed: what the decision rests on is fixed")
    if "owner" in d and d["owner"] != c["owner"] and c["status"] != "new" and not P.allows(user["roles"],
                                                                                         "qms:configure"):
        raise PermissionError("once the investigation has started, Quality changes the owner")
    d = {k: v for k, v in d.items() if v != c[k]}
    if not d:
        return c
    with conn.transaction():
        row = conn.execute("update complaints set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + ", updated_at = now() where id = %(id)s and status = %(st)s returning *",
                           {**d, "id": cid, "st": c["status"]}).fetchone()
        if row is None:
            raise ComplaintError("the complaint changed meanwhile: open it again")
        log(conn, cid, user["email"], "changed", ", ".join(sorted(d)))
    return row


def start(conn, email: str, cid: int) -> dict:
    c = get(conn, cid)
    if c["status"] != "new":
        raise ComplaintError(f"the complaint is {c['status']}")
    missing = CR.to_investigate(c)
    if missing:
        raise ComplaintError("still needed: " + ", ".join(missing))
    with conn.transaction():
        row = conn.execute("update complaints set status = 'investigation', updated_at = now() where id = %s and "
                           "status = 'new' returning *", (cid,)).fetchone()
        log(conn, cid, email, "investigation started", f"owner {c['owner']}")
    return row


def no_investigation(conn, email: str, cid: int, reason: str) -> dict:
    """Quality approves not investigating, with the reason (for example, the same event was already investigated)."""
    c = get(conn, cid)
    if c["status"] != "investigation":
        raise ComplaintError("only a complaint under investigation")
    if not reason.strip():
        raise ComplaintError("give the reason")
    with conn.transaction():
        row = conn.execute("update complaints set investigate = false, no_investigation_reason = %s, "
                           "no_investigation_by = %s, updated_at = now() where id = %s returning *",
                           (reason.strip()[:2000], email, cid)).fetchone()
        log(conn, cid, email, "no investigation", reason.strip())
    return row


def deadlines(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from complaint_deadlines order by sort, id")]


def save_deadline(conn, email: str, did: int | None, label: str, days, *, active: bool = True) -> list[dict]:
    if not label.strip() or type(days) is not int or not 1 <= days <= 365 or type(active) is not bool:
        raise ComplaintError("a deadline has a name and 1 to 365 days")
    if did is None:
        conn.execute("insert into complaint_deadlines (label, days, active, sort) values (%s, %s, %s, "
                     "(select coalesce(max(sort), 0) + 1 from complaint_deadlines))", (label.strip()[:200], days,
                                                                                      active))
    elif conn.execute("update complaint_deadlines set label = %s, days = %s, active = %s where id = %s returning id",
                      (label.strip()[:200], days, active, did)).fetchone() is None:
        raise KeyError(did)
    return deadlines(conn)


def assess(conn, user: dict, cid: int, password: str, *, answers: dict, reportable, reason: str,
           deadline_id: int | None = None) -> dict:
    """Someone other than the owner answers the three questions and decides, signed. When a question is answered
    yes, the deadline the assessor chooses (company configuration) is counted from the day the company knew."""
    c = get(conn, cid)
    if c["status"] != "investigation":
        raise ComplaintError("assess a complaint under investigation")
    if user["email"] == c["owner"]:
        raise PermissionError("someone other than the owner assesses it")
    a = CR.assessment(answers or {}, reportable, reason)
    if a["errors"]:
        raise ComplaintError("; ".join(a["errors"]))
    if c["investigate"] and not c["investigation"].strip():
        raise ComplaintError("record the investigation's conclusion first (or have not investigating approved)")
    dl = None
    if a["any_yes"]:
        dl = next((x for x in deadlines(conn) if x["active"] and (deadline_id is None or x["id"] == deadline_id)), None)
        if dl is None:
            raise ComplaintError("choose the reporting deadline that applies (set them up under the deadlines)")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute(
            "update complaints set status = 'assessed', q_harm = %s, q_malfunction = %s, q_recall = %s, "
            "reportable = %s, reportable_reason = %s, exception = %s, deadline_label = %s, deadline_days = %s, "
            "deadline_on = %s, assessed_by = %s, assessed_at = now(), updated_at = now() where id = %s and "
            "status = 'investigation' returning *",
            (answers["q_harm"], answers["q_malfunction"], answers["q_recall"], reportable, reason.strip()[:2000],
             a["exception"], dl["label"] if dl else None, dl["days"] if dl else None,
             c["aware_on"] + dt.timedelta(days=dl["days"]) if dl else None, user["email"], cid)).fetchone()
        if row is None:
            raise ComplaintError("the complaint changed meanwhile: open it again")
        Q._sign(conn, user, "Reportable" if reportable else "Not reportable", "complaint", cid, c["name"])
        log(conn, cid, user["email"], "assessed", ("reportable" if reportable else "not reportable")
            + (" (a question was answered yes)" if a["exception"] else "") + f": {reason.strip()}")
    return row


def close(conn, user: dict, cid: int, password: str) -> dict:
    c = get(conn, cid)
    missing = CR.to_close(c)
    if missing:
        raise ComplaintError("still needed: " + "; ".join(missing))
    if user["email"] == c["owner"]:
        raise PermissionError("someone other than the owner closes it")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute("update complaints set status = 'closed', closed_by = %s, closed_at = now(), updated_at = "
                           "now() where id = %s and status = 'assessed' returning *", (user["email"], cid)).fetchone()
        if row is None:
            raise ComplaintError("the complaint changed meanwhile: open it again")
        Q._sign(conn, user, "Complaint closed", "complaint", cid, c["name"])
        log(conn, cid, user["email"], "closed")
    return row


def cancel(conn, email: str, cid: int, reason: str) -> dict:
    if not reason.strip():
        raise ComplaintError("give the reason (a duplicate, or not a complaint)")
    with conn.transaction():
        row = conn.execute("update complaints set status = 'cancelled', cancel_reason = %s, updated_at = now() where "
                           "id = %s and status not in ('closed', 'cancelled') returning *",
                           (reason.strip()[:1000], cid)).fetchone()
        if row is None:
            raise ComplaintError(f"a {get(conn, cid)['status']} complaint cannot be cancelled")
        log(conn, cid, email, "cancelled", reason.strip())
    return row


def open_ncr(conn, email: str, cid: int) -> dict:
    c = get(conn, cid)
    if c["ncr_id"]:
        raise ComplaintError("it already has a nonconformance report")
    if c["status"] in ("closed", "cancelled"):
        raise ComplaintError(f"the complaint is {c['status']}")
    with conn.transaction():
        n = Q.create_ncr(conn, email, title=f"Complaint {c['name']}: {c['customer']}",
                         description=f"From complaint {c['name']} received {c['received_on']}: {c['description']}",
                         item_code=c["item_code"], quantity=float(c["quantity"]) if c["quantity"] else None,
                         severity="major" if c["injury"] == "yes" else "minor")
        conn.execute("update complaints set ncr_id = %s, updated_at = now() where id = %s", (n["id"], cid))
        log(conn, cid, email, "nonconformance opened", n["name"])
    return n


def open_capa(conn, email: str, cid: int) -> dict:
    c = get(conn, cid)
    if c["capa_id"]:
        raise ComplaintError("it already has a corrective action")
    if c["status"] in ("closed", "cancelled"):
        raise ComplaintError(f"the complaint is {c['status']}")
    with conn.transaction():
        cp = Q.create_capa(conn, email, kind="corrective", title=f"Complaint {c['name']}: {c['customer']}",
                           description=c["description"], ncr_ids=[c["ncr_id"]] if c["ncr_id"] else None)
        conn.execute("update complaints set capa_id = %s, updated_at = now() where id = %s", (cp["id"], cid))
        log(conn, cid, email, "corrective action opened", cp["name"])
    return cp


def listing(conn, status: str = "open", today: dt.date | None = None) -> list[dict]:
    where = {"open": "status in ('new', 'investigation', 'assessed')", "closed": "status = 'closed'",
             "cancelled": "status = 'cancelled'", "all": "true"}.get(status, "true")
    rows = conn.execute(f"select * from complaints where {where} order by id desc limit 500").fetchall()  # noqa: S608
    out = []
    for r in rows:
        late = bool(r["deadline_on"] and r["reportable"] and not r["reported_on"] and today
                    and r["deadline_on"] < today)
        out.append({**_iso(r), "report_late": late})
    return out


def view(conn, cid: int, today: dt.date) -> dict:
    c = get(conn, cid)
    ncr = conn.execute("select id, name, status from ncr_records where id = %s", (c["ncr_id"],)).fetchone() \
        if c["ncr_id"] else None
    capa = conn.execute("select id, name, status from capas where id = %s", (c["capa_id"],)).fetchone() \
        if c["capa_id"] else None
    return {**_iso(c), "history": history(conn, cid), "signatures": Q.signatures(conn, "complaint", cid),
            "questions": CR.QUESTIONS, "to_investigate": CR.to_investigate(c), "to_close": CR.to_close(c),
            "deadlines": deadlines(conn), "ncr": ncr, "capa": capa,
            "report_late": bool(c["deadline_on"] and c["reportable"] and not c["reported_on"]
                                and c["deadline_on"] < today)}


def register_view(conn) -> list[dict]:
    """The complaints as the ISO checks read the complaints register (wqops/hub/system/rules.py): each one an entry
    with the register's fields, so the checks need no change."""
    out = []
    for c in conn.execute("select * from complaints where status <> 'cancelled' order by id").fetchall():
        v = {"received_on": c["received_on"].isoformat(), "customer": c["customer"], "kind": "complaint",
             "description": c["description"], "response": c["response"] or None,
             "answered_on": c["closed_at"].date().isoformat() if c["closed_at"] else None,
             "investigation": c["investigation"] or c["no_investigation_reason"] or None,
             "reportable": c["reportable"], "reportable_reason": c["reportable_reason"] or None,
             "reportable_by": c["assessed_by"], "reported_on": c["reported_on"].isoformat() if c["reported_on"]
             else None, "report_ref": c["report_ref"] or None}
        out.append({"id": f"c{c['id']}", "complaint": c["name"], "values": {k: x for k, x in v.items()
                                                                            if x is not None},
                    "signed": c["status"] == "closed", "imported": False})
    return out
