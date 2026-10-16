"""Management review, step 17j (ADR-0017; dee-qms PLAN-MR).

The inputs are counted from every module's records for the period (incoming inspection, nonconformances, CAPA,
suppliers, documents and reading, complaints, measuring equipment, changes, risk, production, recalls, delivery and
purchasing performance, and the actions of earlier reviews still open), frozen with a fingerprint, and can be
collected again until the review is signed (the old fingerprint is logged). Top management meets: the meeting's
assessment of each input, the conclusion and the actions decided are written down, and the chair signs with a
password; whoever prepared it (collected the inputs, wrote notes or actions) does not sign. Signed reviews are fixed
and appear in the management review register the ISO checks read. Nothing is deleted.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.ont import metrics as M
from wqops.hub.quality import records as Q
from wqops.hub.quality import review_rules as RR

SECTIONS = {
    "incoming": "Incoming inspection", "nonconformances": "Nonconformances",
    "capa": "Corrective and preventive action",
    "suppliers": "Approved suppliers", "documents": "Documents and reading", "complaints": "Customer complaints",
    "equipment": "Measuring equipment", "changes": "Changes", "risk": "Risk management", "production": "Production",
    "recalls": "Recalls", "performance": "Delivery and purchasing performance",
    "previous": "Actions of earlier reviews",
}
FIELDS = {"title", "period_start", "period_end", "meeting_on", "chair", "attendees", "notes", "conclusion"}


class ReviewError(ValueError):
    pass


def _iso(row: dict) -> dict:
    from wqops.hub.quality import production as PRD  # noqa: PLC0415 - the same conversion

    return PRD._iso(row)


def log(conn, rid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into mgmt_review_log (review_id, email, action, note) values (%s, %s, %s, %s)",
                 (rid, email, action, (note or "")[:2000]))


def _one(conn, sql: str, p: dict) -> dict:
    return conn.execute(sql, p).fetchone()


def _fig(label: str, value, unit: str = "") -> dict:
    return {"label": label, "value": value, "unit": unit}


def inputs(conn, start: dt.date, end: dt.date, today: dt.date, tz: str = "UTC") -> dict:
    """Every input of the review for the period, counted from the records (deterministic)."""
    p = {"a": start, "b": end, "t": today, "tz": tz}
    day = "(%s at time zone %%(tz)s)::date"
    within = lambda col: f"{day % col} between %(a)s and %(b)s"  # noqa: E731
    out: dict[str, dict] = {}

    r = _one(conn, f"select count(*) as n, count(*) filter (where result = 'reject') as rej from iqc_inspections "
                   f"where {within('signed_at')}", p)
    rel = [_iso(x) for x in conn.execute("select name, item_code, lot_no, decision_note from iqc_inspections where "
                                          f"status = 'released' and unverified and {within('decided_at')} "
                                          "order by id", p)]
    out["incoming"] = {"figures": [_fig("Lots inspected", r["n"]), _fig("Lots rejected", r["rej"]),
                                   _fig("Lot rejection rate", RR.rate(r["rej"], r["n"]), "%"),
                                   _fig("Released on an unchecked sampling row (exceptions)", len(rel))],
                       "lists": {"exceptions": rel}}

    r = _one(conn, f"select count(*) filter (where {within('created_at')}) as new, count(*) filter (where "
                   f"{within('closed_at')}) as closed, count(*) filter (where disposition = 'use_as_is' and "
                   f"{within('created_at')}) as as_is, count(*) filter (where status not in ('closed', 'cancelled')) "
                   "as open from ncr_records", p)
    out["nonconformances"] = {"figures": [_fig("Opened", r["new"]), _fig("Closed", r["closed"]),
                                          _fig("Used as is (concession)", r["as_is"]), _fig("Open now", r["open"])]}

    r = _one(conn, f"select count(*) filter (where {within('created_at')}) as new, count(*) filter (where "
                   f"{within('closed_at')}) as closed, count(*) filter (where verification_result = 'ineffective' "
                   f"and {within('verified_at')}) as ineffective, count(*) filter (where status not in "
                   "('closed', 'cancelled')) as open from capas", p)
    over = _one(conn, "select count(*) as n from capa_actions a join capas c on c.id = a.capa_id where not a.done and "
                      "a.due < %(t)s and c.status not in ('closed', 'cancelled')", p)["n"]
    out["capa"] = {"figures": [_fig("Opened", r["new"]), _fig("Closed", r["closed"]),
                               _fig("Found ineffective", r["ineffective"]), _fig("Open now", r["open"]),
                               _fig("Actions overdue", over)]}

    st = {x["status"]: x["n"] for x in conn.execute("select status, count(*) as n from asl_entries group by status")}
    late = _one(conn, "select count(*) as n from asl_entries where status in ('approved', 'conditional') and "
                      "review_due < %(t)s", p)["n"]
    out["suppliers"] = {"figures": [_fig(f"Entries {k}", v) for k, v in sorted(st.items())]
                        + [_fig("Re-evaluations overdue", late)]}

    from wqops.hub.docs import control as CTL  # noqa: PLC0415

    eff = _one(conn, "select count(*) as n from documents where effective_date between %(a)s and %(b)s", p)["n"]
    reviews = CTL.review_list(conn, today)
    post = _one(conn, f"select count(*) as n from doc_reviews where outcome = 'postponed' and "
                      f"{within('approved_at')}", p)["n"]
    tr = _one(conn, f"select count(*) filter (where {within('created_at')}) as assigned, count(*) filter (where "
                    f"status = 'acknowledged' and {within('done_at')}) as read, count(*) filter (where status = "
                    f"'waived' and {within('done_at')}) as waived, count(*) filter (where status = 'pending') as "
                    "pending, count(*) filter (where status = 'pending' and due < %(t)s) as late from doc_training", p)
    out["documents"] = {"figures": [_fig("Revisions taking effect", eff),
                                    _fig("Reviews overdue", sum(1 for x in reviews if x["overdue"])),
                                    _fig("Reviews postponed (exceptions)", post),
                                    _fig("Reading assigned", tr["assigned"]), _fig("Reading confirmed", tr["read"]),
                                    _fig("Reading waived (exceptions)", tr["waived"]),
                                    _fig("Reading pending", tr["pending"]), _fig("Reading overdue", tr["late"])]}

    r = _one(conn, "select count(*) filter (where received_on between %(a)s and %(b)s) as new, count(*) filter "
                   "(where reportable and received_on between %(a)s and %(b)s) as reportable, count(*) filter (where "
                   "status not in ('closed', 'cancelled')) as open, count(*) filter (where deadline_on < %(t)s and "
                   "report_ref = '' and status not in ('closed', 'cancelled')) as late from complaints", p)
    out["complaints"] = {"figures": [_fig("Received", r["new"]), _fig("Reportable", r["reportable"]),
                                     _fig("Open now", r["open"]), _fig("Report deadlines passed", r["late"])]}

    r = _one(conn, f"select count(*) filter (where status = 'approved' and {within('approved_at')}) as done, "
                   f"count(*) filter (where status = 'approved' and result = 'fail' and {within('approved_at')}) as "
                   "failed from gauge_calibrations", p)
    late = _one(conn, "select count(*) as n from gauges where status <> 'retired' and next_due < %(t)s", p)["n"]
    out["equipment"] = {"figures": [_fig("Calibrations", r["done"]), _fig("Found out of tolerance", r["failed"]),
                                    _fig("Calibrations overdue", late)]}

    r = _one(conn, f"select count(*) filter (where {within('created_at')}) as new, count(*) filter (where "
                   f"{within('approved_at')}) as approved, count(*) filter (where {within('closed_at')}) as closed, "
                   "count(*) filter (where status not in ('closed', 'cancelled')) as open from changes", p)
    out["changes"] = {"figures": [_fig("Raised", r["new"]), _fig("Approved", r["approved"]),
                                  _fig("Closed", r["closed"]), _fig("Open now", r["open"])]}

    from wqops.hub.quality import production as PRD  # noqa: PLC0415
    from wqops.hub.quality import recall as RC  # noqa: PLC0415
    from wqops.hub.quality import risk as RSK  # noqa: PLC0415

    rk = RSK.summary(conn, start, end, tz)
    out["risk"] = {"figures": [_fig("Risk files approved", rk["approved"]),
                               _fig("Hazards whose residual risk is not acceptable", rk["residual_not_acceptable"]),
                               _fig("Drafts not approved", rk["drafts"])]}
    pr = PRD.summary(conn, start, end, tz)
    out["production"] = {"figures": [_fig("Lots released", pr["released"]), _fig("Lots rejected", pr["rejected"]),
                                     _fig("First-pass yield", None if pr["first_pass"] is None
                                          else round(100 * pr["first_pass"], 1), "%"),
                                     _fig("In production or review now", pr["in_production"])]}
    rc = RC.summary(conn, start, end)
    out["recalls"] = {"figures": [_fig("Open now", rc["open"]), _fig("Closed", rc["closed"])]}

    days = (end - start).days + 1
    otd, sot = M.on_time_delivery(conn, end, days), M.supplier_on_time(conn, end, days)
    out["performance"] = {"figures": [_fig("On-time delivery to customers", otd["value"], "%"),
                                      _fig("Orders not counted (dates missing)", len(otd.get("unknown") or [])),
                                      _fig("Purchase order lines received on time", sot["value"], "%"),
                                      _fig("Lines not counted (dates missing)", len(sot.get("unknown") or []))]}

    prev = [_iso(x) for x in conn.execute(
        "select a.text, a.owner, a.due, r.name as review from mgmt_review_actions a join mgmt_reviews r on r.id = "
        "a.review_id where a.status = 'open' and r.status = 'closed' order by a.due")]
    out["previous"] = {"figures": [_fig("Still open", len(prev)), _fig("Overdue", sum(
        1 for x in prev if x["due"] < today.isoformat()))], "lists": {"open": prev}}
    return {"period": [start.isoformat(), end.isoformat()], "counted_on": today.isoformat(),
            "sections": {k: {"label": SECTIONS[k], **v} for k, v in out.items()}}


# ---------------------------------------------------------------- the review

def get(conn, rid: int, lock: bool = False) -> dict:
    sql = "select * from mgmt_reviews where id = %s"
    if lock:
        sql += " for update"
    row = conn.execute(sql, (rid,)).fetchone()
    if row is None:
        raise KeyError(rid)
    return row


def _date(v, what: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise ReviewError(f"{what} is a date like 2026-12-31") from exc


def _clean(conn, data: dict) -> dict:
    bad = set(data) - FIELDS
    if bad:
        raise ReviewError(f"{sorted(bad)[0].replace('_', ' ')} cannot be changed here")
    out = {}
    for k, v in data.items():
        if k in ("period_start", "period_end", "meeting_on"):
            out[k] = _date(v, k.replace("_", " "))
            if out[k] is None and k != "meeting_on":
                raise ReviewError("give the period")
        elif k == "chair":
            c = str(v or "").strip().lower() or None
            if c and not conn.execute("select 1 from users where email = %s and active", (c,)).fetchone():
                raise ReviewError(f"{c} is not a person in the company")
            out[k] = c
        elif k == "notes":
            if not isinstance(v, dict) or any(k2 not in SECTIONS or not isinstance(x, str) for k2, x in v.items()):
                raise ReviewError("notes are written per input")
            out[k] = Jsonb({k2: x.strip()[:4000] for k2, x in v.items()})
        else:
            out[k] = str(v or "").strip()[:4000]
    if "title" in out and not out["title"]:
        raise ReviewError("give the review a title")
    return out


def create(conn, email: str, data: dict) -> dict:
    d = _clean(conn, data)
    if not d.get("title") or not d.get("period_start") or not d.get("period_end"):
        raise ReviewError("give the title and the period")
    if d["period_start"] > d["period_end"]:
        raise ReviewError("the period starts before it ends")
    with conn.transaction():
        name = Q._next_name(conn, "mgmt_reviews", "MR")
        cols = ["name", "created_by", *d]
        row = conn.execute(f"insert into mgmt_reviews ({', '.join(cols)}) values "
                           f"({', '.join(['%s'] * len(cols))}) returning *", [name, email, *d.values()]).fetchone()
        log(conn, row["id"], email, "drafted", f"{d['period_start']} to {d['period_end']}")
    return row


def _open(conn, rid: int) -> dict:
    r = get(conn, rid, lock=True)
    if r["status"] not in ("draft", "frozen"):
        raise ReviewError(f"the review is {r['status']}")
    return r


def _involve(conn, r: dict, email: str) -> None:
    if email not in r["involved"]:
        conn.execute("update mgmt_reviews set involved = array_append(involved, %s) where id = %s", (email, r["id"]))


def update(conn, email: str, rid: int, data: dict) -> dict:
    """The period only before the inputs are collected; the meeting, notes and conclusion until it is signed."""
    with conn.transaction():
        r = _open(conn, rid)
        d = _clean(conn, data)
        if r["status"] == "frozen" and ({"period_start", "period_end"} & set(d)) and (
                d.get("period_start", r["period_start"]), d.get("period_end", r["period_end"])) != (
                r["period_start"], r["period_end"]):
            raise ReviewError("the inputs are collected for this period: cancel and start a new review to change it")
        if d.get("period_start", r["period_start"]) > d.get("period_end", r["period_end"]):
            raise ReviewError("the period starts before it ends")
        if "notes" in d:
            d["notes"] = Jsonb({k: v for k, v in {**r["notes"], **d["notes"].obj}.items() if v})
        d = {k: v for k, v in d.items() if (v.obj if isinstance(v, Jsonb) else v) != r[k]}
        if not d:
            return r
        conn.execute("update mgmt_reviews set " + ", ".join(f"{k} = %({k})s" for k in d)
                     + ", updated_at = now() where id = %(id)s", {**d, "id": rid})
        if {"notes", "conclusion"} & set(d):
            _involve(conn, r, email)
        log(conn, rid, email, "changed", ", ".join(k.replace("_", " ") for k in sorted(d)))
    return get(conn, rid)


def collect(conn, email: str, rid: int, *, today: dt.date, tz: str = "UTC") -> dict:
    """Count the inputs and freeze them; again until it is signed (the earlier fingerprint is logged)."""
    with conn.transaction():
        r = _open(conn, rid)
        data = inputs(conn, r["period_start"], r["period_end"], today, tz)
        fp = RR.fingerprint(data)
        row = conn.execute("update mgmt_reviews set inputs = %s, fingerprint = %s, collected_by = %s, collected_at = "
                           "clock_timestamp(), status = 'frozen', updated_at = now(), involved = case when %s = "
                           "any(involved) then involved else array_append(involved, %s) end where id = %s returning *",
                           (Jsonb(data), fp, email, email, email, rid)).fetchone()
        log(conn, rid, email, "inputs collected again" if r["fingerprint"] else "inputs collected",
            f"{fp}" + (f" (was {r['fingerprint']})" if r["fingerprint"] else ""))
    return row


def add_action(conn, email: str, rid: int, data: dict, *, today: dt.date) -> dict:
    text = str(data.get("text") or "").strip()
    owner = str(data.get("owner") or "").strip().lower()
    due = _date(data.get("due"), "the due date")
    if due is None:
        raise ReviewError("give the due date")
    missing = RR.check_action(text, owner, due, today)
    if missing:
        raise ReviewError("still needed: " + "; ".join(missing))
    if not conn.execute("select 1 from users where email = %s and active", (owner,)).fetchone():
        raise ReviewError(f"{owner} is not a person in the company")
    capa = data.get("capa_id")
    if capa not in (None, "") and (type(capa) is not int or not conn.execute("select 1 from capas where id = %s",
                                                                            (capa,)).fetchone()):
        raise ReviewError("no such corrective action")
    with conn.transaction():
        r = _open(conn, rid)
        row = conn.execute("insert into mgmt_review_actions (review_id, text, owner, due, capa_id, created_by) values "
                           "(%s, %s, %s, %s, %s, %s) returning *", (rid, text[:2000], owner, due, capa or None,
                                                                     email)).fetchone()
        _involve(conn, r, email)
        log(conn, rid, email, "action decided", f"{text[:200]} ({owner}, due {due})")
    return row


def action_done(conn, user: dict, aid: int, evidence: str) -> dict:
    """The action's owner or Quality marks it done, with what shows it."""
    from wqops.hub import permissions as P  # noqa: PLC0415

    if not evidence.strip():
        raise ReviewError("say what shows it is done")
    with conn.transaction():
        a = conn.execute("select * from mgmt_review_actions where id = %s for update", (aid,)).fetchone()
        if a is None:
            raise KeyError(aid)
        if a["status"] == "done":
            raise ReviewError("the action is already done")
        if get(conn, a["review_id"])["status"] == "cancelled":
            raise ReviewError("the review was cancelled")
        if user["email"] != a["owner"] and not P.allows(user["roles"], "qms:configure"):
            raise PermissionError("the action's owner or Quality marks it done")
        row = conn.execute("update mgmt_review_actions set status = 'done', evidence = %s, done_by = %s, done_at = "
                           "now() where id = %s returning *", (evidence.strip()[:2000], user["email"], aid)).fetchone()
        log(conn, a["review_id"], user["email"], "action done", f"{a['text'][:200]}: {evidence.strip()[:200]}")
    return row


def sign(conn, user: dict, rid: int, password: str, *, today: dt.date) -> dict:
    """The chair signs: someone who did not prepare it, the meeting held, the inputs as counted; then it is fixed."""
    r = get(conn, rid)
    missing = RR.to_sign(r, user["email"], today)
    if missing:
        raise ReviewError("still needed: " + "; ".join(missing))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        r = _open(conn, rid)
        missing = RR.to_sign(r, user["email"], today)
        if missing:
            raise ReviewError("still needed: " + "; ".join(missing))
        if RR.fingerprint(r["inputs"]) != r["fingerprint"]:
            raise ReviewError("the inputs no longer match their fingerprint: collect them again")
        Q._sign(conn, user, "Management review approved", "mgmt_review", rid, r["name"])
        row = conn.execute("update mgmt_reviews set status = 'closed', signed_by = %s, signed_at = now(), updated_at = "
                           "now() where id = %s returning *", (user["email"], rid)).fetchone()
        log(conn, rid, user["email"], "signed", r["fingerprint"])
    return row


def cancel(conn, email: str, rid: int, reason: str) -> dict:
    if not reason.strip():
        raise ReviewError("give the reason")
    with conn.transaction():
        _open(conn, rid)
        row = conn.execute("update mgmt_reviews set status = 'cancelled', cancel_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], rid)).fetchone()
        log(conn, rid, email, "cancelled", reason.strip())
    return row


def actions(conn, rid: int) -> list[dict]:
    return [_iso(a) for a in conn.execute("select * from mgmt_review_actions where review_id = %s order by id", (rid,))]


def listing(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute(
        "select id, name, title, period_start, period_end, meeting_on, chair, status, signed_at from mgmt_reviews "
        "order by id desc limit 200")]


def view(conn, rid: int, user: dict, today: dt.date) -> dict:
    r = get(conn, rid)
    return {**_iso(r), "sections": SECTIONS, "actions": actions(conn, rid),
            "intact": None if r["inputs"] is None else RR.fingerprint(r["inputs"]) == r["fingerprint"],
            "to_sign": RR.to_sign(r, user["email"], today) if r["status"] in ("draft", "frozen") else [],
            "history": [_iso(x) for x in conn.execute("select at, email, action, note from mgmt_review_log where "
                                                      "review_id = %s order by id", (rid,))],
            "signatures": Q.signatures(conn, "mgmt_review", rid)}


def register_view(conn) -> list[dict]:
    """Signed reviews as the ISO checks read the management review register (wqops/hub/system/rules.py)."""
    out = []
    for r in conn.execute("select * from mgmt_reviews where status = 'closed' order by id").fetchall():
        acts = actions(conn, r["id"])
        decisions = r["conclusion"] + "".join(f"\n- {a['text']} ({a['owner']}, due {a['due']})" for a in acts)
        out.append({"id": f"m{r['id']}", "values": {
            "review_date": r["meeting_on"].isoformat(), "attendees": r["attendees"],
            "inputs": ", ".join(s["label"] for s in (r["inputs"] or {}).get("sections", {}).values()),
            "decisions": decisions}, "signed": True, "imported": False})
    return out
