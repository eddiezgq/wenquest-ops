"""Document control and training acknowledgement, step 17d (ADR-0017; dee-qms PLAN-DOC, PLAN-TRAINING).

- Periodic review: each document type the company reviews has an interval (months). The next review of a document
  in effect is due its interval after it took effect, or after its last approved review. A review is recorded by the
  reviewer (no change, a change with the new revision it started, or postponed with a reason and a new date) and
  approved with a signature by someone else; only then does the next due date move.
- Read and understood: a document names who must read it (roles and people, carried to its next revisions). When a
  revision that needs it takes effect, each of them gets a record due a set number of days later; records still open
  for the revision it replaces are superseded. People confirm with their password; Quality may waive a record for
  someone else, with a reason.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops import i18n as I18N
from wqops.hub.quality import records as Q
from wqops.i18n import say

OUTCOMES = {"no_change": "No change needed", "change": "A change is needed (new revision started)",
            "postponed": "Postponed"}


class ControlError(ValueError):
    pass


def _iso(row: dict | None) -> dict | None:
    return None if row is None else {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def _log(conn, doc_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into doc_log (document_id, email, action, note) values (%s, %s, %s, %s)",
                 (doc_id, email, action, (note or "")[:2000]))


def _doc(conn, doc_id: int) -> dict:
    row = conn.execute("select * from documents where id = %s", (doc_id,)).fetchone()
    if row is None:
        raise KeyError(doc_id)
    return row


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last))


# ---------------------------------------------------------------- settings per document type

def type_settings(conn) -> dict[str, dict]:
    return {r["doc_type"]: _iso(r) for r in conn.execute("select * from doc_type_settings order by doc_type")}


def set_type(conn, email: str, doc_type: str, review_months, training_days) -> dict:
    if not doc_type or len(doc_type) > 40:
        raise ControlError(say("which document type?"))
    if review_months is not None and (type(review_months) is not int or not 1 <= review_months <= 120):
        raise ControlError(say("review every 1 to 120 months, or not at all"))
    if type(training_days) is not int or not 1 <= training_days <= 365:
        raise ControlError(say("people have 1 to 365 days to read a new revision"))
    conn.execute("insert into doc_type_settings (doc_type, review_months, training_days, email) values "
                 "(%s, %s, %s, %s) on conflict (doc_type) do update set review_months = excluded.review_months, "
                 "training_days = excluded.training_days, email = excluded.email, at = now()",
                 (doc_type, review_months, training_days, email))
    return type_settings(conn)


# ---------------------------------------------------------------- periodic review

def next_review(conn, doc: dict) -> dt.date | None:
    """When the document in effect is next due for review: its interval after it took effect, or after the last
    approved review (a postponement sets its own date). None: its type is not reviewed periodically."""
    st = type_settings(conn).get(doc.get("doc_type") or "")
    if not st or not st["review_months"] or doc["status"] != "effective" or not doc.get("effective_date"):
        return None
    due = add_months(doc["effective_date"], st["review_months"])
    last = conn.execute("select outcome, reviewed_on, next_due from doc_reviews where document_id = %s and status = "
                        "'approved' order by approved_at desc, id desc limit 1", (doc["id"],)).fetchone()
    if last:
        due = last["next_due"] if last["outcome"] == "postponed" else add_months(last["reviewed_on"],
                                                                                   st["review_months"])
    return due


def record_review(conn, email: str, doc_id: int, outcome: str, note: str, *, today: dt.date,
                  revision_id: int | None = None, next_due=None) -> dict:
    """The reviewer records a review of the revision in effect; someone else approves it."""
    doc = _doc(conn, doc_id)
    if doc["status"] != "effective":
        raise ControlError(say("only a document in effect is reviewed"))
    if outcome not in OUTCOMES:
        raise ControlError(say("the outcome is no change, a change, or postponed"))
    if outcome == "change":
        rev = conn.execute("select id from documents where id = %s and supersedes = %s and status in ('draft', "
                           "'in_review', 'approved')", (revision_id, doc_id)).fetchone() if revision_id else None
        if rev is None:
            raise ControlError(say("a change review names the new revision of this document that it started"))
    else:
        revision_id = None
    due = None
    if outcome == "postponed":
        if not note.strip():
            raise ControlError(say("say why the review is postponed"))
        try:
            due = dt.date.fromisoformat(str(next_due or "")[:10])
        except ValueError as exc:
            raise ControlError(say("a postponed review sets the new date it is due")) from exc
        if due <= today:
            raise ControlError(say("the new date is after today"))
    with conn.transaction():
        if conn.execute("select 1 from doc_reviews where document_id = %s and status = 'submitted'",
                        (doc_id,)).fetchone():
            raise ControlError(say("a review of this document is waiting for approval"))
        row = conn.execute("insert into doc_reviews (document_id, outcome, note, revision_id, next_due, reviewed_by, "
                           "reviewed_on) values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (doc_id, outcome, note.strip()[:2000], revision_id, due, email, today)).fetchone()
        _log(conn, doc_id, email, "reviewed", say("{outcome}: {note}", outcome=say(OUTCOMES[outcome]),
                                                  note=note.strip()) if note.strip() else say(OUTCOMES[outcome]))
    return row


def decide_review(conn, user: dict, review_id: int, approve: bool, *, password: str = "", note: str = "") -> dict:
    """Quality approves (signed) or sends back a review; not the reviewer."""
    r = conn.execute("select * from doc_reviews where id = %s", (review_id,)).fetchone()
    if r is None:
        raise KeyError(review_id)
    if r["status"] != "submitted":
        raise ControlError(say("the review is already {status}", status=I18N.label(f"review status::{r['status']}")))
    if r["reviewed_by"] == user["email"]:
        raise PermissionError(say("someone other than the reviewer approves the review"))
    if not approve and not note.strip():
        raise ControlError(say("say why it is sent back"))
    if approve:
        Q.check_signer(conn, user, password)
    with conn.transaction():
        if approve and conn.execute("select status from documents where id = %s for update",
                                    (r["document_id"],)).fetchone()["status"] != "effective":
            raise ControlError(say("the document is no longer in effect: send the review back"))
        row = conn.execute("update doc_reviews set status = %s, approved_by = %s, approved_at = now(), "
                           "decision_note = %s where id = %s and status = 'submitted' returning *",
                           ("approved" if approve else "rejected", user["email"], note.strip()[:2000],
                            review_id)).fetchone()
        if row is None:
            raise ControlError(say("the review changed meanwhile: open it again"))
        doc = _doc(conn, r["document_id"])
        if approve:
            Q._sign(conn, user, say("Document review approved"), "document", doc["id"],
                    " ".join(x for x in (doc["number"], doc["title"]) if x) or doc["original_name"])
        _log(conn, doc["id"], user["email"], "review approved" if approve else "review sent back", note.strip())
    return row


def reviews(conn, doc_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select * from doc_reviews where document_id = %s order by id desc",
                                          (doc_id,)).fetchall()]


def review_list(conn, today: dt.date) -> list[dict]:
    """Every document in effect whose type is reviewed: when it is due, overdue or not, and any review waiting."""
    waiting = {r["document_id"]: _iso(r) for r in conn.execute("select * from doc_reviews where status = 'submitted'")}
    out = []
    for d in conn.execute("select * from documents where status = 'effective' order by number, id").fetchall():
        due = next_review(conn, d)
        if due is None:
            continue
        out.append({"id": d["id"], "number": d["number"], "title": d["title"], "revision": d["revision"],
                    "doc_type": d["doc_type"], "effective_date": d["effective_date"].isoformat(),
                    "due": due.isoformat(), "overdue": due < today, "waiting": waiting.get(d["id"])})
    return sorted(out, key=lambda x: x["due"])


# ---------------------------------------------------------------- read and understood

def clean_trainees(conn, raw) -> dict:
    if not isinstance(raw, dict):
        raise ControlError(say("say which roles and people must read it"))
    roles = raw.get("roles") or []
    people = raw.get("people") or []
    if not isinstance(roles, list) or not isinstance(people, list):
        raise ControlError(say("roles and people are lists"))
    known = {r["email"] for r in conn.execute("select email from users")}
    people = sorted({str(p).strip().lower() for p in people if str(p).strip()})
    bad = [p for p in people if p not in known]
    if bad:
        raise ControlError(say("not a person in the company: {bad}", bad=', '.join(bad)))
    return {"roles": sorted({str(r).strip() for r in roles if str(r).strip()}), "people": people}


def set_training(conn, email: str, doc_id: int, trainees, needs_training: bool, *,
                 today: dt.date | None = None) -> dict:
    """Who must read the document, and whether this revision needs it (fixed once it is approved). The list carries
    to later revisions; people added to a revision in effect that needs reading are asked to read it at once."""
    doc = _doc(conn, doc_id)
    if doc["status"] not in ("draft", "in_review", "approved", "effective", "confirmed"):
        raise ControlError(say("not a document in the library"))
    t = clean_trainees(conn, trainees)
    if type(needs_training) is not bool:
        raise ControlError(say("needs training is yes or no"))
    if doc["status"] in ("approved", "effective") and needs_training != doc["needs_training"]:
        raise ControlError(say("this revision is approved: whether it needs reading was set before approval"))
    with conn.transaction():
        row = conn.execute("update documents set trainees = %s, needs_training = %s, updated_at = now() where id = %s "
                           "returning *", (Jsonb(t), needs_training, doc_id)).fetchone()
        roles, people = ", ".join(t["roles"]) or "-", ", ".join(t["people"]) or "-"
        _log(conn, doc_id, email, "readers set",
             say("roles: {roles}; people: {people}; this revision needs reading", roles=roles, people=people)
             if needs_training else
             say("roles: {roles}; people: {people}; this revision does not need reading", roles=roles, people=people))
        if row["status"] == "effective" and row["needs_training"]:
            _assign(conn, row, email, today or dt.datetime.now(dt.UTC).date())
    return row


def readers(conn, trainees: dict) -> list[str]:
    """Active people with one of the roles, and the people named."""
    roles = list((trainees or {}).get("roles") or [])
    named = set((trainees or {}).get("people") or [])
    out = {r["email"] for r in conn.execute("select email from users where active and (roles && %s::text[])",
                                            (roles,))}
    out |= {r["email"] for r in conn.execute("select email from users where active and email = any(%s)",
                                             (list(named),))}
    return sorted(out)


def on_effective(conn, doc: dict, email: str, today: dt.date) -> int:
    """A revision took effect: records still open for the revision it replaces are superseded; if it needs reading,
    each reader gets a record. Called inside the transaction that makes it effective."""
    if doc.get("supersedes"):
        conn.execute("update doc_training set status = 'superseded', done_at = now(), note = %s where document_id = "
                     "%s and status = 'pending'", (say("replaced by revision {revision} (document {id})",
                                                       revision=doc["revision"], id=doc["id"]), doc["supersedes"]))
    if not doc.get("needs_training"):
        return 0
    return _assign(conn, doc, email, today)


def _assign(conn, doc: dict, email: str, today: dt.date) -> int:
    """A record for each reader who has none for this revision yet."""
    days = (type_settings(conn).get(doc.get("doc_type") or "") or {}).get("training_days") or 30
    due = today + dt.timedelta(days=days)
    people = readers(conn, doc.get("trainees") or {})
    added = 0
    for p in people:
        added += conn.execute("insert into doc_training (document_id, email, due) values (%s, %s, %s) on conflict do "
                              "nothing", (doc["id"], p, due)).rowcount
    if added:
        _log(conn, doc["id"], email, "reading assigned", say("{n} people, due {date}", n=added, date=due))
    return added


def acknowledge(conn, user: dict, record_id: int, password: str) -> dict:
    """The person confirms, with their own password, that they have read and understood the revision."""
    r = conn.execute("select * from doc_training where id = %s", (record_id,)).fetchone()
    if r is None:
        raise KeyError(record_id)
    if r["email"] != user["email"]:
        raise PermissionError(say("only the person confirms their own reading"))
    if r["status"] != "pending":
        raise ControlError(say("it is already {status}", status=I18N.label(f"reading status::{r['status']}")))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute("update doc_training set status = 'acknowledged', done_at = now(), done_by = %s where id = "
                           "%s and status = 'pending' returning *", (user["email"], record_id)).fetchone()
        if row is None:
            raise ControlError(say("it changed meanwhile"))
        doc = _doc(conn, r["document_id"])
        Q._sign(conn, user, say("Read and understood"), "doc_training", record_id,
                " ".join(x for x in (doc["number"], doc["title"], f"rev {doc['revision']}") if x))
    return row


def waive(conn, email: str, record_id: int, reason: str) -> dict:
    if not reason.strip():
        raise ControlError(say("give the reason"))
    r = conn.execute("select * from doc_training where id = %s", (record_id,)).fetchone()
    if r is None:
        raise KeyError(record_id)
    if r["email"] == email:
        raise PermissionError(say("someone else waives your reading"))
    with conn.transaction():
        row = conn.execute("update doc_training set status = 'waived', done_at = now(), done_by = %s, note = %s where "
                           "id = %s and status = 'pending' returning *", (email, reason.strip()[:1000],
                                                                         record_id)).fetchone()
        if row is None:
            raise ControlError(say("it is already {status}", status=I18N.label(f"reading status::{r['status']}")))
        _log(conn, r["document_id"], email, "reading waived", f"{r['email']}: {reason.strip()}")
    return row


def training(conn, *, email: str | None = None, document_id: int | None = None, today: dt.date) -> list[dict]:
    rows = conn.execute(
        "select t.*, d.number, d.title, d.revision from doc_training t join documents d on d.id = t.document_id "
        "where (%s::text is null or t.email = %s) and (%s::bigint is null or t.document_id = %s) "
        "order by t.status <> 'pending', t.due, t.id", (email, email, document_id, document_id)).fetchall()
    return [{**_iso(r), "overdue": r["status"] == "pending" and r["due"] < today} for r in rows]


def training_facts(conn) -> list[dict]:
    """For the ISO checks: every reading record with what it is about."""
    return [dict(r) for r in conn.execute(
        "select t.id, t.email, t.status, t.due, t.done_at, d.number, d.title, d.revision from doc_training t "
        "join documents d on d.id = t.document_id order by t.id")]
