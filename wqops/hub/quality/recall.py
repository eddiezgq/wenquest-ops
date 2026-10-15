"""Recalls, step 17i (ADR-0017; dee-qms PLAN-RECALL).

A recall is drafted with its production lots in scope (from a trace, or chosen), its reason, classification and
strategy, which people decide. Opening it (its owner or Quality) takes the consignee list from ERPNext's delivery
notes and fixes the scope. While open, each consignee's notification, confirmation and the quantity returned or
corrected are recorded; WenQuest Ops counts the effectiveness and lists any delivery of a lot in scope made after the
recall opened. Quality closes it with a signature (not its owner, nor whoever raised or opened it) once every
consignee is notified. A draft is cancelled with a reason; nothing is deleted.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal

from psycopg.types.json import Jsonb

from wqops.hub.quality import records as Q
from wqops.hub.quality import trace as TRC
from wqops.hub.quality import trace_rules as TR

DRAFT_FIELDS = {"title", "reason", "owner", "classification", "regulatory_decision", "strategy", "scope"}
OPEN_FIELDS = {"owner", "classification", "regulatory_decision", "strategy", "effectiveness", "unconfirmed_note"}


class RecallError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return TRC._iso(row)


def log(conn, rid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into recall_log (recall_id, email, action, note) values (%s, %s, %s, %s)",
                 (rid, email, action, (note or "")[:2000]))


def get(conn, rid: int, lock: bool = False) -> dict:
    sql = "select * from recalls where id = %s"
    if lock:
        sql += " for update"
    row = conn.execute(sql, (rid,)).fetchone()
    if row is None:
        raise KeyError(rid)
    return row


def consignees(conn, rid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from recall_consignees where recall_id = %s order by "
                                          "posting_date, delivery_note, id", (rid,))]


def _clean(conn, data: dict, allowed: set[str]) -> dict:
    out = {}
    for k, v in data.items():
        if k not in allowed:
            raise RecallError(f"{k.replace('_', ' ')} cannot be changed now")
        if k == "classification":
            if v not in TR.CLASSES:
                raise RecallError("the classification is one of: " + ", ".join(TR.CLASSES))
            out[k] = v
        elif k == "title":
            if not str(v or "").strip():
                raise RecallError("give the recall a title")
            out[k] = str(v).strip()[:300]
        elif k == "owner":
            o = str(v or "").strip().lower() or None
            if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
                raise RecallError(f"{o} is not a person in the company")
            out[k] = o
        elif k == "scope":
            if not isinstance(v, list) or any(type(x) is not int for x in v):
                raise RecallError("the scope is production records")
            ids = sorted(set(v))
            found = {r["id"] for r in conn.execute("select id from prod_records where id = any(%s) and status in "
                                                   "('released', 'qa_review', 'in_production', 'rejected')", (ids,))}
            if set(ids) - found:
                raise RecallError("no such production record: " + ", ".join(map(str, sorted(set(ids) - found))))
            out[k] = Jsonb(ids)
        else:
            out[k] = str(v or "").strip()[:4000]
    return out


def create(conn, email: str, data: dict) -> dict:
    d = _clean(conn, data, DRAFT_FIELDS)
    if not str(data.get("title") or "").strip():
        raise RecallError("give the recall a title")
    with conn.transaction():
        name = Q._next_name(conn, "recalls", "RCL")
        cols = ["name", "created_by", "owners", *d]
        row = conn.execute(f"insert into recalls ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *",
                           [name, email, [d["owner"]] if d.get("owner") else [], *d.values()]).fetchone()
        log(conn, row["id"], email, "drafted", row["title"])
    return row


def update(conn, user: dict, rid: int, data: dict) -> dict:
    from wqops.hub import permissions as P  # noqa: PLC0415 - permissions are a plain table

    with conn.transaction():
        r = get(conn, rid, lock=True)
        allowed = {"draft": DRAFT_FIELDS, "open": OPEN_FIELDS}.get(r["status"])
        if allowed is None:
            raise RecallError(f"the recall is {r['status']}")
        d = _clean(conn, data, allowed)
        if r["status"] == "open" and "owner" in d and not P.allows(user["roles"], "qms:configure"):
            raise PermissionError("Quality changes the owner of an open recall")
        d = {k: v for k, v in d.items() if (v.obj if isinstance(v, Jsonb) else v) != r[k]}
        if not d:
            return r
        if d.get("owner"):
            d["owners"] = sorted(set(r["owners"]) | {d["owner"]})   # a former owner never closes it
        row = conn.execute("update recalls set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + ", updated_at = now() where id = %(id)s returning *", {**d, "id": rid}).fetchone()
        log(conn, rid, user["email"], "changed", ", ".join(k.replace("_", " ") for k in sorted(d)))
    return row


def _scope(conn, r: dict) -> list[dict]:
    return [dict(x) for x in conn.execute("select * from prod_records where id = any(%s) order by id",
                                          ([int(i) for i in r["scope"] or []],))]


def preview(conn, r: dict) -> list[dict]:
    """Who would be on the list if it opened now."""
    return TRC.shipped(conn, _scope(conn, r))


def open_recall(conn, user: dict, rid: int, *, today: dt.date) -> dict:
    """Its owner or Quality opens it: the consignees are taken from ERPNext's delivery notes and fixed."""
    from wqops.hub import permissions as P  # noqa: PLC0415 - permissions are a plain table

    with conn.transaction():
        r = get(conn, rid, lock=True)
        if r["status"] != "draft":
            raise RecallError("open a draft recall")
        if user["email"] != r["owner"] and not P.allows(user["roles"], "qms:configure"):
            raise PermissionError("the owner or Quality opens the recall")
        gone = [x["name"] for x in _scope(conn, r) if x["status"] == "cancelled"]
        if gone:
            raise RecallError("cancelled production records cannot be recalled: " + ", ".join(gone))
        rows = preview(conn, r)
        missing = TR.to_open(r, len(rows))
        if missing:
            raise RecallError("still needed: " + "; ".join(missing))
        if conn.execute("select 1 from recall_consignees where recall_id = %s", (rid,)).fetchone():
            raise RecallError("the consignee list was already written: open it again")
        conn.execute("select set_config('wqo.recall_opening', %s, true)", (str(rid),))
        for x in rows:
            conn.execute("insert into recall_consignees (recall_id, delivery_note, posting_date, customer, "
                         "customer_name, item_code, lot_no, batch_match, qty) values (%s, %s, %s, %s, %s, %s, %s, %s, "
                         "%s)", (rid, x["delivery_note"], x["posting_date"], x["customer"], x["customer_name"],
                                 x["item_code"], x["lot_no"], x["batch_match"], x["qty"]))
        conn.execute("select set_config('wqo.recall_opening', '', true)")
        row = conn.execute("update recalls set status = 'open', opened_by = %s, opened_at = now(), opened_on = %s, "
                           "updated_at = now() where id = %s returning *", (user["email"], today, rid)).fetchone()
        log(conn, rid, user["email"], "opened", f"{len(rows)} consignee lines from ERPNext delivery notes")
    return row


def _date(v, what: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise RecallError(f"{what} is a date like 2026-10-15") from exc


def _qty(v, what: str) -> Decimal:
    if v in (None, ""):
        return Decimal(0)
    from wqops.hub.quality import prod_rules as PR  # noqa: PLC0415 - the same number rule

    x = PR.stored(v)
    if x is None or x < 0:
        raise RecallError(f"{what} is a number, not negative")
    return x


def record_contact(conn, email: str, cid: int, data: dict, *, today: dt.date) -> dict:  # noqa: PLR0912
    """Notification (date and method together), confirmation, quantities returned or corrected, a note."""
    bad = set(data) - {"notified_on", "method", "confirmed_on", "returned_qty", "corrected_qty", "note"}
    if bad:
        raise RecallError(f"{sorted(bad)[0].replace('_', ' ')} is not recorded here")
    with conn.transaction():
        c = conn.execute("select * from recall_consignees where id = %s for update", (cid,)).fetchone()
        if c is None:
            raise KeyError(cid)
        r = get(conn, c["recall_id"], lock=True)
        if r["status"] != "open":
            raise RecallError(f"the recall is {r['status']}")
        new = dict(c)
        if "notified_on" in data or "method" in data:
            new["notified_on"] = _date(data.get("notified_on", c["notified_on"]), "the notification date")
            new["method"] = str(data.get("method", c["method"]) or "").strip()[:200]
            if (new["notified_on"] is None) != (new["method"] == ""):
                raise RecallError("give the notification date and how together")
        if "confirmed_on" in data:
            new["confirmed_on"] = _date(data["confirmed_on"], "the confirmation date")
        for k, what in (("returned_qty", "the quantity returned"), ("corrected_qty", "the quantity corrected")):
            if k in data:
                new[k] = _qty(data[k], what)
        if "note" in data:
            new["note"] = str(data["note"] or "").strip()[:2000]
        opened = r["opened_on"]
        if new["notified_on"] and not opened <= new["notified_on"] <= today:
            raise RecallError(f"the notification date is between the opening ({opened}) and today")
        if new["confirmed_on"] and not (new["notified_on"] and new["notified_on"] <= new["confirmed_on"] <= today):
            raise RecallError("the confirmation comes after the notification, and not after today")
        if new["returned_qty"] + new["corrected_qty"] > c["qty"]:
            raise RecallError(f"returned and corrected together are at most the {c['qty'].normalize():f} delivered")
        if new["notified_on"] and not c["notified_on"]:
            new["notified_by"] = email
        if not new["notified_on"]:
            new["notified_by"] = None
        d = {k: new[k] for k in ("notified_on", "notified_by", "method", "confirmed_on", "returned_qty",
                                 "corrected_qty", "note") if new[k] != c[k]}
        if not d:
            return c
        row = conn.execute("update recall_consignees set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *", {**d, "id": cid}).fetchone()
        log(conn, r["id"], email, "consignee", f"{c['delivery_note']} {c['customer_name']}: "
            + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items() if k != "notified_by"))
    return row


def close(conn, user: dict, rid: int, password: str, *, today: dt.date) -> dict:
    r = get(conn, rid)
    if r["status"] != "open":
        raise RecallError("close an open recall")
    if user["email"] in (r["owner"], r["created_by"], r["opened_by"], *r["owners"]):
        raise PermissionError("someone who does not own it and did not raise or open it closes the recall")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        r = get(conn, rid, lock=True)
        if r["status"] != "open":
            raise RecallError("the recall changed meanwhile: open it again")
        missing = TR.to_close(r, consignees(conn, rid))
        if missing:
            raise RecallError("still needed: " + "; ".join(missing))
        Q._sign(conn, user, "Recall closed", "recall", rid, r["name"])
        row = conn.execute("update recalls set status = 'closed', closed_by = %s, closed_at = now(), closed_on = %s, "
                           "updated_at = now() where id = %s returning *", (user["email"], today, rid)).fetchone()
        log(conn, rid, user["email"], "closed", r["effectiveness"])
    return row


def cancel(conn, email: str, rid: int, reason: str) -> dict:
    if not reason.strip():
        raise RecallError("give the reason")
    with conn.transaction():
        r = get(conn, rid, lock=True)
        if r["status"] != "draft":
            raise RecallError("only a draft recall is cancelled")
        row = conn.execute("update recalls set status = 'cancelled', cancel_reason = %s, updated_at = now() where "
                           "id = %s returning *", (reason.strip()[:1000], rid)).fetchone()
        log(conn, rid, email, "cancelled", reason.strip())
    return row


def after_opening(conn, r: dict) -> list[dict]:
    """Deliveries in ERPNext of a lot in scope that are not on the fixed list (submitted, or backdated, after the
    recall opened), whatever their date."""
    if r["status"] != "open":
        return []
    have = {(x["delivery_note"], x["item_code"]) for x in consignees(conn, r["id"])}
    return [x for x in preview(conn, r) if (x["delivery_note"], x["item_code"]) not in have]


def on_recall(conn, record_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select id, name, status from recalls where status = 'open' and "
                                          "scope @> %s::jsonb", (f"[{record_id}]",))]


def listing(conn, status: str) -> list[dict]:
    where = {"open": "status in ('draft', 'open')", "closed": "status = 'closed'", "cancelled": "status = 'cancelled'",
             "all": "true"}.get(status, "true")
    return [_iso(r) for r in conn.execute(f"select * from recalls where {where} order by id desc limit 500")]  # noqa: S608


def view(conn, rid: int) -> dict:
    r = get(conn, rid)
    rows = consignees(conn, rid)
    lots = _scope(conn, r)
    return {**_iso(r), "classes": TR.CLASSES,
            "lots": [{"id": x["id"], "name": x["name"], "item_code": x["item_code"], "lot_no": x["lot_no"],
                      "status": x["status"]} for x in lots],
            "consignees": [_iso(x) for x in rows],
            "preview": preview(conn, r) if r["status"] == "draft" else [],
            "to_open": TR.to_open(r, len(preview(conn, r))) if r["status"] == "draft" else [],
            "to_close": TR.to_close(r, rows) if r["status"] == "open" else [],
            "effectiveness_counts": TR.effectiveness(rows), "after_opening": after_opening(conn, r),
            "history": [_iso(x) for x in conn.execute("select at, email, action, note from recall_log where "
                                                      "recall_id = %s order by id", (rid,))],
            "signatures": Q.signatures(conn, "recall", rid)}


def csv_text(conn, rid: int) -> str:
    get(conn, rid)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Delivery note", "Date", "Customer", "Item", "Lot", "Matched by", "Quantity", "Notified on",
                "Notified by", "Method", "Confirmed on", "Returned", "Corrected", "Note"])
    for x in consignees(conn, rid):
        w.writerow([TR.csv_cell(v) for v in (x["delivery_note"], x["posting_date"], x["customer_name"] or x["customer"],
                                             x["item_code"], x["lot_no"], x["batch_match"], x["qty"], x["notified_on"],
                                             x["notified_by"], x["method"], x["confirmed_on"], x["returned_qty"],
                                             x["corrected_qty"], x["note"])])
    return out.getvalue()


def summary(conn, since: dt.date, until: dt.date) -> dict:
    """For management review: recalls open now, recalls closed in the period."""
    return {"open": conn.execute("select count(*) as n from recalls where status = 'open'").fetchone()["n"],
            "closed": conn.execute("select count(*) as n from recalls where status = 'closed' and closed_on "
                                   "between %s and %s", (since, until)).fetchone()["n"]}
