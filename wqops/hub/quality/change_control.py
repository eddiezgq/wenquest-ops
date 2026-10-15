"""Change control, step 17g (ADR-0017; dee-qms PLAN-CHANGE).

A change of product, process, supplier, document, software or equipment is raised as a draft, assessed against four
questions a person answers, submitted (its content is then fixed; Quality may send it back with a reason), approved
with a signature by someone who did not raise, own, submit or edit it, implemented once the new revisions of the
documents it affects are in effect (and validated when needed), and closed with a signature by someone other than
its owner once its effectiveness is confirmed. Cancelled with a reason before it is implemented; never deleted.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.quality import change_rules as CR
from wqops.hub.quality import records as Q

DRAFT_FIELDS = {"title", "kind", "description", "reason", "owner", "target_date", "capa_id", "documents",
                "q_product", "q_regulatory", "q_risk", "q_validation", "assessment", "regulatory_decision",
                "validation_plan"}
APPROVED_FIELDS = {"target_date", "revisions", "validation_result", "implementation"}
IMPLEMENTED_FIELDS = {"target_date", "effectiveness"}


class ChangeError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, cid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into change_log (change_id, email, action, note) values (%s, %s, %s, %s)",
                 (cid, email, action, (note or "")[:2000]))


def get(conn, cid: int) -> dict:
    row = conn.execute("select * from changes where id = %s", (cid,)).fetchone()
    if row is None:
        raise KeyError(cid)
    return row


def _ids(conn, v, what: str, statuses: tuple[str, ...]) -> list[int]:
    if not isinstance(v, list) or any(type(x) is not int for x in v):
        raise ChangeError(f"{what} are document numbers")
    found = {r["id"]: r["status"] for r in conn.execute("select id, status from documents where id = any(%s)",
                                                         (list(v),))}
    bad = [x for x in v if found.get(x) not in statuses]
    if bad:
        raise ChangeError(f"{what}: documents {', '.join(map(str, bad))} are not " + " or ".join(statuses))
    return sorted(set(v))


def _clean(conn, data: dict, allowed: set[str]) -> dict:  # noqa: PLR0912 - one branch per kind of field
    out = {}
    for k, v in data.items():
        if k not in allowed:
            raise ChangeError(f"{k.replace('_', ' ')} cannot be changed now")
        if k == "kind":
            if v not in CR.KINDS:
                raise ChangeError("the kind is one of: " + ", ".join(CR.KINDS))
            out[k] = v
        elif k in CR.QUESTIONS:
            if v not in ("yes", "no", None, ""):
                raise ChangeError("answer yes or no")
            out[k] = v or None
        elif k == "target_date":
            try:
                out[k] = dt.date.fromisoformat(str(v)[:10]) if v not in (None, "") else None
            except ValueError as exc:
                raise ChangeError("the target date is a date like 2026-12-31") from exc
        elif k == "owner":
            o = str(v or "").strip().lower() or None
            if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
                raise ChangeError(f"{o} is not a person in the company")
            out[k] = o
        elif k == "capa_id":
            if v is not None and (type(v) is not int or not conn.execute("select 1 from capas where id = %s",
                                                                         (v,)).fetchone()):
                raise ChangeError("no such corrective action")
            out[k] = v
        elif k == "documents":
            out[k] = Jsonb(_ids(conn, v, "the documents it changes", ("effective",)))
        elif k == "revisions":
            out[k] = Jsonb(_ids(conn, v, "the new revisions", ("draft", "in_review", "approved", "effective")))
        else:
            out[k] = str(v or "").strip()[:4000]
    return out


def create(conn, email: str, data: dict) -> dict:
    d = _clean(conn, data, DRAFT_FIELDS)
    if not str(data.get("title") or "").strip():
        raise ChangeError("give the change a title")
    d.setdefault("kind", "other")
    with conn.transaction():
        name = Q._next_name(conn, "changes", "CHG")
        cols = ["name", "created_by", "editors", *d]
        row = conn.execute(f"insert into changes ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *",
                           [name, email, [email], *d.values()]).fetchone()
        log(conn, row["id"], email, "raised", row["title"])
    return row


def update(conn, email: str, cid: int, data: dict) -> dict:
    """Change what the current step allows: everything in a draft; after approval the new revisions, validation and
    implementation; after implementation the effectiveness check; the target date at any time (logged)."""
    c = get(conn, cid)
    allowed = {"draft": DRAFT_FIELDS, "submitted": {"target_date"}, "approved": APPROVED_FIELDS,
               "implemented": IMPLEMENTED_FIELDS}.get(c["status"])
    if allowed is None:
        raise ChangeError(f"the change is {c['status']}")
    d = _clean(conn, data, allowed)
    d = {k: v for k, v in d.items() if (v.obj if isinstance(v, Jsonb) else v) != c[k]}
    if not d:
        return c
    content = set(d) - {"target_date"}
    with conn.transaction():
        row = conn.execute("update changes set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + (", editors = array_append(editors, %(by)s)" if content and email not in c["editors"]
                              else "") + ", updated_at = now() where id = %(id)s and status = %(st)s returning *",
                           {**d, "by": email, "id": cid, "st": c["status"]}).fetchone()
        if row is None:
            raise ChangeError("the change moved on meanwhile: open it again")
        log(conn, cid, email, "changed", "; ".join(
            f"target date: {c['target_date'] or '-'} -> {d['target_date'] or '-'}" if k == "target_date" else k
            for k in sorted(d)))
    return row


def _move(conn, c: dict, to: str, email: str, action: str, note: str = "", **cols) -> dict:  # noqa: PLR0917
    sets = ", ".join(["status = %(to)s", *(f"{k} = %({k})s" for k in cols), "updated_at = now()"])
    row = conn.execute(f"update changes set {sets} where id = %(id)s and status = %(st)s returning *",  # noqa: S608
                       {"to": to, "id": c["id"], "st": c["status"], **cols}).fetchone()
    if row is None:
        raise ChangeError("the change moved on meanwhile: open it again")
    log(conn, c["id"], email, action, note)
    return row


def submit(conn, email: str, cid: int) -> dict:
    c = get(conn, cid)
    if c["status"] != "draft":
        raise ChangeError(f"the change is {c['status']}")
    missing = CR.to_submit(c)
    if missing:
        raise ChangeError("still needed: " + "; ".join(missing))
    with conn.transaction():
        return _move(conn, c, "submitted", email, "submitted", submitted_by=email)


def send_back(conn, email: str, cid: int, reason: str) -> dict:
    c = get(conn, cid)
    if c["status"] != "submitted":
        raise ChangeError("only a submitted change is sent back")
    if not reason.strip():
        raise ChangeError("say what needs to change")
    with conn.transaction():
        return _move(conn, c, "draft", email, "sent back", reason.strip())


def approve(conn, user: dict, cid: int, password: str) -> dict:
    c = get(conn, cid)
    if c["status"] != "submitted":
        raise ChangeError("approve a submitted change")
    if user["email"] in {c["owner"], c["created_by"], c["submitted_by"], *c["editors"]}:
        raise PermissionError("someone who did not raise, own, submit or edit the change approves it")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        Q._sign(conn, user, "Change approved", "change", cid, c["name"])
        return _move(conn, c, "approved", user["email"], "approved", approved_by=user["email"],
                     approved_at=dt.datetime.now(dt.UTC))


def docs_of(conn, c: dict) -> dict[int, dict]:
    ids = [int(x) for x in (c["documents"] or []) + (c["revisions"] or [])]
    return {r["id"]: dict(r) for r in conn.execute(
        "select id, number, title, revision, status, supersedes from documents where id = any(%s)", (ids,))}


def implement(conn, user: dict, cid: int) -> dict:
    """The owner or Quality marks it implemented: the new revisions in effect, validation done when needed."""
    from wqops.hub import permissions as P  # noqa: PLC0415 - permissions are a plain table

    c = get(conn, cid)
    if c["status"] != "approved":
        raise ChangeError("implement an approved change")
    if user["email"] != c["owner"] and not P.allows(user["roles"], "qms:configure"):
        raise PermissionError("the owner or Quality marks it implemented")
    missing = CR.to_implement(c, docs_of(conn, c))
    if missing:
        raise ChangeError("still needed: " + "; ".join(missing))
    with conn.transaction():
        return _move(conn, c, "implemented", user["email"], "implemented", implemented_by=user["email"],
                     implemented_at=dt.datetime.now(dt.UTC))


def close(conn, user: dict, cid: int, password: str) -> dict:
    c = get(conn, cid)
    if c["status"] != "implemented":
        raise ChangeError("close an implemented change")
    if user["email"] == c["owner"]:
        raise PermissionError("someone other than the owner closes it")
    missing = CR.to_close(c)
    if missing:
        raise ChangeError("still needed: " + "; ".join(missing))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        Q._sign(conn, user, "Change closed", "change", cid, c["name"])
        return _move(conn, c, "closed", user["email"], "closed", closed_by=user["email"],
                     closed_at=dt.datetime.now(dt.UTC))


def cancel(conn, email: str, cid: int, reason: str) -> dict:
    c = get(conn, cid)
    if c["status"] not in ("draft", "submitted", "approved"):
        raise ChangeError(f"a {c['status']} change cannot be cancelled")
    if not reason.strip():
        raise ChangeError("give the reason")
    with conn.transaction():
        return _move(conn, c, "cancelled", email, "cancelled", reason.strip(), cancel_reason=reason.strip()[:1000])


def listing(conn, status: str, today: dt.date) -> list[dict]:
    where = {"open": "status not in ('closed', 'cancelled')", "closed": "status = 'closed'",
             "cancelled": "status = 'cancelled'", "all": "true"}.get(status, "true")
    rows = conn.execute(f"select * from changes where {where} order by id desc limit 500").fetchall()  # noqa: S608
    return [{**_iso(r), "overdue": bool(r["target_date"] and r["target_date"] < today
                                        and r["status"] not in ("closed", "cancelled"))} for r in rows]


def view(conn, cid: int, today: dt.date) -> dict:
    c = get(conn, cid)
    docs = docs_of(conn, c)
    return {**_iso(c), "questions": CR.QUESTIONS, "kinds": CR.KINDS, "docs": {str(k): v for k, v in docs.items()},
            "to_submit": CR.to_submit(c) if c["status"] == "draft" else [],
            "to_implement": CR.to_implement(c, docs) if c["status"] == "approved" else [],
            "to_close": CR.to_close(c) if c["status"] == "implemented" else [],
            "overdue": bool(c["target_date"] and c["target_date"] < today and c["status"] not in ("closed",
                                                                                                  "cancelled")),
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from change_log where "
                                                      "change_id = %s order by id", (cid,)).fetchall()],
            "signatures": Q.signatures(conn, "change", cid)}
