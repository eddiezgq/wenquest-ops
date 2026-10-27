"""Cause analysis, step 22b (ADR-0022): fishbone diagrams and 5 Why on a nonconformance report, a CAPA or a complaint.

A person starts an analysis on an open record, adds causes (with the records they rest on) and accepts, edits or
removes what the model suggested (``causes_ai``). The conclusion is signed with the person's password and added to
the record's root cause: section D4 of the report's 8D, the CAPA's root cause, or the complaint's. After that the
analysis is kept as it was (the database refuses changes) and only addenda are added.

The records the model may read are gathered here (``context``), and any record number a person cites is checked to
exist. Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.quality import causes_rules as CR
from wqops.hub.quality import complaints as CP
from wqops.hub.quality import records as Q
from wqops.i18n import say

CauseError = CR.CauseError
KINDS = {"ncr": "nonconformance report", "capa": "corrective action", "complaint": "complaint"}
OPEN = {"ncr": ("open", "contained", "pending_approval", "dispositioned"), "capa": ("draft", "investigation"),
        "complaint": ("new", "investigation")}
NAMED = ("ncr_records", "capas", "complaints", "iqc_inspections", "prod_records", "changes", "check_sheets",
         "cause_analyses", "recalls")
CONTEXT_DAYS = 365


def _iso(row: dict) -> dict:
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in row.items()}


def log(conn, aid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into cause_log (analysis_id, email, action, note) values (%s, %s, %s, %s)",
                 (aid, email, action, (note or "")[:2000]))


def subject(conn, kind: str, ref_id: int) -> dict:
    """The record analysed, as one text: what it says, and its item, supplier and root cause so far."""
    if kind == "ncr":
        r = Q.ncr(conn, ref_id)
        d8 = conn.execute("select sections, complete from eightd where ncr_id = %s", (ref_id,)).fetchone()
        return {"kind": kind, "id": r["id"], "name": r["name"], "status": r["status"], "title": r["title"],
                "text": f"{r['title']}. {r['description']}", "item_code": r["item_code"], "supplier": r["supplier"],
                "root_cause": ((d8 or {}).get("sections") or {}).get("d4") or "",
                "locked": bool(d8 and d8["complete"]), "containment": r["containment"] or ""}
    if kind == "capa":
        r = Q.capa(conn, ref_id)
        ncrs = conn.execute("select n.name, n.item_code, n.supplier from capa_ncrs l join ncr_records n on "
                            "n.id = l.ncr_id where l.capa_id = %s order by n.id", (ref_id,)).fetchall()
        items = sorted({n["item_code"] for n in ncrs if n["item_code"]})
        sups = sorted({n["supplier"] for n in ncrs if n["supplier"]})
        return {"kind": kind, "id": r["id"], "name": r["name"], "status": r["status"], "title": r["title"],
                "text": f"{r['title']}. {r['description'] or ''}".strip(), "item_code": items[0] if items else None,
                "items": items, "supplier": sups[0] if len(sups) == 1 else None, "root_cause": r["root_cause"] or "",
                "locked": False, "ncrs": [n["name"] for n in ncrs], "containment": r.get("containment") or ""}
    if kind == "complaint":
        r = CP.get(conn, ref_id)
        return {"kind": kind, "id": r["id"], "name": r["name"], "status": r["status"],
                "title": r["description"][:120], "text": f"From {r['customer']}: {r['description']}",
                "item_code": r["item_code"], "supplier": None, "root_cause": r["root_cause"] or "",
                "locked": False, "lot_no": r["lot_no"], "containment": ""}
    raise CauseError(say("an analysis is on a nonconformance report, a CAPA or a complaint"))


# ---------------------------------------------------------------- the records the model may read

def _add(out: dict, ref: str, kind: str, summary: str) -> None:
    if ref and ref not in out:
        out[ref] = {"ref": ref, "kind": kind, "summary": " ".join(summary.split())[:400]}


def context(conn, s: dict, *, today: dt.date) -> list[dict]:
    """Records related to the one analysed: the record itself, other reports, inspections, complaints and lots of the
    same item or supplier, the measuring equipment used on the item, recent changes and earlier conclusions. The
    model sees these and nothing else, and may cite only these. A subject without a name (the item of a process
    FMEA, 22c) gathers the related records only."""
    since = today - dt.timedelta(days=CONTEXT_DAYS)
    out: dict[str, dict] = {}
    if s.get("name"):
        _add(out, s["name"], KINDS[s["kind"]], f"(the record analysed) {s['text']}"
             + (f" Containment: {s['containment']}" if s.get("containment") else ""))
    items = s.get("items") or ([s["item_code"]] if s.get("item_code") else [])
    sup = s.get("supplier")
    for r in conn.execute(
            "select n.name, n.title, n.description, n.item_code, n.supplier, n.status, n.created_at, e.sections "
            "from ncr_records n left join eightd e on e.ncr_id = n.id where n.name is distinct from %s::text "
            "and n.created_at >= %s and (n.item_code = any(%s) or (%s::text is not null and n.supplier = %s)) "
            "order by n.created_at desc limit 25", (s.get("name"), since, items, sup, sup)).fetchall():
        d4 = (r["sections"] or {}).get("d4")
        _add(out, r["name"], "nonconformance report",
             f"{r['created_at']:%Y-%m-%d} {r['status']}; item {r['item_code'] or 'unknown'}, supplier "
             f"{r['supplier'] or 'unknown'}: {r['title']}. {r['description']}" + (f" Root cause: {d4}" if d4 else ""))
    if items:
        for r in conn.execute(
                "select name, item_code, supplier, lot_no, lot_qty, n, result, defectives, status, created_at "
                "from iqc_inspections where item_code = any(%s) and status <> 'void' and created_at >= %s "
                "order by created_at desc limit 20", (items, since)).fetchall():
            res = f"{r['result']}, {r['defectives']} defective of {r['n']} sampled" if r["result"] else r["status"]
            _add(out, r["name"], "incoming inspection",
                 f"{r['created_at']:%Y-%m-%d} item {r['item_code']}, supplier {r['supplier'] or 'unknown'}, lot "
                 f"{r['lot_no'] or 'unknown'} ({r['lot_qty']}): {res}")
        for r in conn.execute(
                "select name, item_code, lot_no, received_on, customer, description, root_cause, status from "
                "complaints where item_code = any(%s) and name is distinct from %s::text and received_on >= %s "
                "and status <> 'cancelled' "
                "order by received_on desc limit 10", (items, s.get("name"), since)).fetchall():
            _add(out, r["name"], "complaint",
                 f"{r['received_on']} from {r['customer']}, lot {r['lot_no'] or 'unknown'}, {r['status']}: "
                 f"{r['description']}" + (f" Root cause: {r['root_cause']}" if r["root_cause"] else ""))
        for r in conn.execute(
                "select name, item_code, lot_no, planned_qty, good_qty, scrap_qty, status, created_at from "
                "prod_records where item_code = any(%s) and status <> 'cancelled' and created_at >= %s "
                "order by created_at desc limit 10", (items, since)).fetchall():
            _add(out, r["name"], "production record",
                 f"{r['created_at']:%Y-%m-%d} lot {r['lot_no']}, {r['status']}: planned {r['planned_qty']}, good "
                 f"{r['good_qty']}, scrap {r['scrap_qty']}")
        for r in conn.execute(
                "select distinct on (g.id) g.code, g.name, g.status, g.next_due, c.result, c.done_on from iqc_gauges "
                "ig join iqc_inspections i on i.id = ig.inspection_id join gauges g on g.id = ig.gauge_id left join "
                "gauge_calibrations c on c.gauge_id = g.id and c.status = 'approved' where i.item_code = any(%s) "
                "order by g.id, c.done_on desc nulls last", (items,)).fetchall():
            due = r["next_due"]
            state = ("calibration overdue" if due and due < today else f"calibrated, next due {due}" if due
                     else "no calibration date")
            last = f"; last calibration {r['done_on']} {r['result']}" if r["result"] else ""
            _add(out, r["code"], "measuring equipment",
                 f"{r['name']} used to inspect this item: {r['status'].replace('_', ' ')}, {state}{last}")
    for r in conn.execute(
            "select name, title, kind, status, description, coalesce(implemented_at, approved_at, created_at) as at "
            "from changes where status <> 'cancelled' and created_at >= %s order by created_at desc limit 10",
            (since,)).fetchall():
        _add(out, r["name"], "change", f"{r['at']:%Y-%m-%d} {r['kind']} change, {r['status']}: {r['title']}. "
             f"{r['description']}")
    for r in conn.execute(
            "select name, method, ref_name, conclusion, concluded_at from cause_analyses where status = 'concluded' "
            "and (ref_name = %s or ref_name in (select name from ncr_records where item_code = any(%s))) "
            "order by concluded_at desc limit 5", (s.get("name"), items)).fetchall():
        _add(out, r["name"], "cause analysis",
             f"{r['concluded_at']:%Y-%m-%d} {CR.METHODS[r['method']]} on {r['ref_name']}: {r['conclusion']}")
    return list(out.values())


def exists(conn, names: list[str]) -> set[str]:
    """Which of these record numbers exist (any kind of record, or a measuring equipment code)."""
    if not names:
        return set()
    found: set[str] = set()
    for t in NAMED:
        found |= {r["name"] for r in conn.execute(f"select name from {t} where name = any(%s)",  # noqa: S608
                                                   (names,)).fetchall()}
    low = {n.lower(): n for n in names}
    found |= {low[r["c"]] for r in conn.execute("select lower(code) as c from gauges where lower(code) = any(%s)",
                                                 (list(low),)).fetchall()}
    return found


PAGES = {"ncr_records": "/quality/ncr/", "capas": "/quality/capa/", "complaints": "/quality/complaints/",
         "iqc_inspections": "/quality/iqc/", "prod_records": "/quality/production/", "changes": "/quality/changes/",
         "cause_analyses": "/quality/causes/", "recalls": "/quality/recalls/"}


def links(conn, names: list[str]) -> dict[str, str]:
    """The page of each cited record, so a person can open what a cause rests on."""
    names = sorted(set(names))
    if not names:
        return {}
    out = {}
    for t, path in PAGES.items():
        for r in conn.execute(f"select id, name from {t} where name = any(%s)", (names,)).fetchall():  # noqa: S608
            out[r["name"]] = f"{path}{r['id']}"
    low = {n.lower(): n for n in names}
    for r in conn.execute("select id, lower(code) as c from gauges where lower(code) = any(%s)", (list(low),)):
        out[low[r["c"]]] = f"/quality/gauges/{r['id']}"
    for r in conn.execute("select name from check_sheets where name = any(%s)", (names,)).fetchall():
        out[r["name"]] = "/quality/tools?tab=sheets"
    return out


# ---------------------------------------------------------------- analyses

def get(conn, aid: int) -> dict:
    row = conn.execute("select * from cause_analyses where id = %s", (aid,)).fetchone()
    if row is None:
        raise KeyError(aid)
    return row


def items(conn, aid: int) -> list[dict]:
    return conn.execute("select * from cause_items where analysis_id = %s order by id", (aid,)).fetchall()


def view(conn, aid: int) -> dict:
    a = get(conn, aid)
    its = items(conn, aid)
    return {"analysis": _iso(a), "items": [_iso(i) for i in its],
            "links": links(conn, [r for i in its for r in i["refs"]] + [a["ref_name"]]),
            "next_level": CR.frontier(its) if a["method"] == "five_why" else None,
            "to_conclude": CR.ready(a, its),
            "addenda": [_iso(r) for r in conn.execute("select * from cause_addenda where analysis_id = %s order by id",
                                                      (aid,)).fetchall()],
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from cause_log where "
                                                      "analysis_id = %s order by id", (aid,)).fetchall()],
            "signatures": Q.signatures(conn, "cause_analysis", aid)}


def for_record(conn, kind: str, ref_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute(
        "select id, name, method, status, problem, conclusion, created_by, created_at from cause_analyses "
        "where ref_kind = %s and ref_id = %s order by id", (kind, ref_id)).fetchall()]


def listing(conn, limit: int = 200) -> list[dict]:
    return [_iso(r) for r in conn.execute(
        "select a.id, a.name, a.method, a.status, a.ref_kind, a.ref_id, a.ref_name, a.problem, a.conclusion, "
        "a.created_by, a.created_at, count(i.id) filter (where i.status = 'accepted') as accepted, "
        "count(i.id) filter (where i.status = 'proposed') as proposed from cause_analyses a left join cause_items i "
        "on i.analysis_id = a.id group by a.id order by a.id desc limit %s", (limit,)).fetchall()]


def start(conn, email: str, kind: str, ref_id: int, method: str, *, problem: str | None = None,
          categories=None) -> dict:
    if method not in CR.METHODS:
        raise CauseError(say("the method is fishbone or five_why"))
    if kind not in KINDS:
        raise CauseError(say("an analysis is on a nonconformance report, a CAPA or a complaint"))
    s = subject(conn, kind, ref_id)
    if s["status"] not in OPEN[kind] or s["locked"]:
        why = "its 8D is complete" if s["locked"] else f"it is {s['status'].replace('_', ' ')}"
        raise CauseError(say("{name} cannot take a new root cause: {why}", name=s['name'], why=why))
    cats = CR.categories(categories) if method == "fishbone" else []
    p = CR.text(problem or s["title"], "the problem", 1000)
    with conn.transaction():
        name = Q._next_name(conn, "cause_analyses", "RCA")
        row = conn.execute("insert into cause_analyses (name, method, ref_kind, ref_id, ref_name, problem, categories, "
                           "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (name, method, kind, ref_id, s["name"], p, cats, email)).fetchone()
        log(conn, row["id"], email, "started", f"{CR.METHODS[method]} on {s['name']}")
        _note(conn, s, email, "cause analysis started", f"{name} ({CR.METHODS[method]})")
    return row


def _note(conn, s: dict, email: str, action: str, note: str) -> None:
    if s["kind"] == "complaint":
        CP.log(conn, s["id"], email, action, note)
    else:
        Q.log(conn, s["kind"], s["id"], email, action, note)


def _open(conn, aid: int) -> dict:
    a = conn.execute("select * from cause_analyses where id = %s for update", (aid,)).fetchone()
    if a is None:
        raise KeyError(aid)
    if a["status"] != "open":
        raise CauseError(say("{name} is {status}; add an addendum instead", name=a['name'], status=a['status']))
    return a


def add(conn, email: str, aid: int, data: dict) -> dict:
    """A person adds a cause (accepted as they wrote it). Record numbers it cites must exist."""
    with conn.transaction():
        a = _open(conn, aid)
        its = items(conn, aid)
        cat = data.get("category") if a["method"] == "fishbone" else None
        lv = data.get("level") if a["method"] == "five_why" else None
        CR.can_add(a, its, category=cat, level=lv)
        t = CR.text(data.get("text"))
        refs = CR.refs(data.get("refs"))
        missing = [r for r in refs if r not in exists(conn, refs)]
        if missing:
            raise CauseError(say("no record with the number: {missing}", missing=', '.join(missing)))
        if lv is not None and CR.accepted(its, lv):
            raise CauseError(say("why {lv} already has an accepted answer; remove it first", lv=lv))
        row = conn.execute("insert into cause_items (analysis_id, category, level, text, refs, origin, status, "
                           "decided_by, decided_at, created_by) values (%s, %s, %s, %s, %s, 'person', 'accepted', %s, "
                           "now(), %s) returning *", (aid, cat, lv, t, refs, email, email)).fetchone()
        log(conn, aid, email, "cause added", f"{cat or f'why {lv}'}: {t}" + (f" [{', '.join(refs)}]" if refs else ""))
    return row


def propose(conn, aid: int, run_id: int, email: str, proposals: list[dict]) -> list[dict]:
    """Store the model's checked suggestions as proposed, for a person to decide each (``causes_ai``)."""
    out = []
    with conn.transaction():
        a = _open(conn, aid)
        for p in proposals:
            out.append(conn.execute(
                "insert into cause_items (analysis_id, category, level, text, refs, origin, ai_run, status, "
                "created_by) values (%s, %s, %s, %s, %s, 'ai', %s, 'proposed', %s) returning *",
                (aid, p.get("category") if a["method"] == "fishbone" else None,
                 p.get("level") if a["method"] == "five_why" else None, p["text"], p["refs"], run_id,
                 email)).fetchone())
        log(conn, aid, email, "AI suggested", f"{len(out)} causes (run {run_id})")
    return out


def _item(conn, aid: int, iid: int) -> dict:
    it = conn.execute("select * from cause_items where id = %s and analysis_id = %s", (iid, aid)).fetchone()
    if it is None:
        raise KeyError(iid)
    return it


def decide(conn, email: str, aid: int, iid: int, action: str, *, new_text: str | None = None) -> dict:
    """accept, edit (accepts with the person's wording; the old wording stays in the history) or remove."""
    if action not in ("accept", "edit", "remove"):
        raise CauseError(say("accept, edit or remove"))
    with conn.transaction():
        a = _open(conn, aid)
        its = items(conn, aid)
        it = _item(conn, aid, iid)
        if it["status"] == "removed":
            raise CauseError(say("this cause was removed; add it again if it is needed"))
        if action == "remove":
            CR.can_remove(a, its, it)
            row = conn.execute("update cause_items set status = 'removed', decided_by = %s, decided_at = now() "
                               "where id = %s returning *", (email, iid)).fetchone()
            log(conn, aid, email, "cause removed", it["text"])
            return row
        CR.can_accept(a, its, it)
        t = CR.text(new_text) if action == "edit" else it["text"]
        edited = it["edited"] or t != it["text"]
        row = conn.execute("update cause_items set status = 'accepted', text = %s, edited = %s, decided_by = %s, "
                           "decided_at = now() where id = %s returning *", (t, edited, email, iid)).fetchone()
        log(conn, aid, email, "cause edited" if t != it["text"] else "cause accepted",
            f"{it['text']} -> {t}" if t != it["text"] else t)
    return row


def conclude(conn, user: dict, aid: int, conclusion: str, password: str, *, today: dt.date) -> dict:
    """Sign the conclusion and add it to the record's root cause. Kept as it was from then on."""
    c = CR.text(conclusion, "the conclusion", 2000)
    a = get(conn, aid)
    left = CR.ready(a, items(conn, aid))
    if left:
        raise CauseError("; ".join(left))
    s = subject(conn, a["ref_kind"], a["ref_id"])
    Q.check_signer(conn, user, password)
    text = CR.write_back(s["root_cause"], c, a["name"], a["method"])
    with conn.transaction():
        a = _open(conn, aid)
        if CR.ready(a, items(conn, aid)):
            raise CauseError(say("the analysis changed meanwhile: open it again"))
        try:
            if a["ref_kind"] == "ncr":
                Q.save_8d(conn, a["ref_id"], user["email"], {"d4": text})
                where = f"8D D4 of {a['ref_name']}"
            elif a["ref_kind"] == "capa":
                Q.update_capa(conn, a["ref_id"], user["email"], root_cause=text)
                where = f"root cause of {a['ref_name']}"
            else:
                CP.update(conn, user, a["ref_id"], {"root_cause": text}, today=today)
                where = f"root cause of {a['ref_name']}"
        except (Q.QualityError, CP.ComplaintError) as exc:
            raise CauseError(say("the root cause of {ref_name} cannot be written now: {exc}",
                                 ref_name=a['ref_name'], exc=exc)) from exc
        row = conn.execute("update cause_analyses set status = 'concluded', conclusion = %s, written_to = %s, "
                           "concluded_by = %s, concluded_at = now() where id = %s returning *",
                           (c, where, user["email"], aid)).fetchone()
        Q._sign(conn, user, "Root cause concluded", "cause_analysis", aid, a["name"])
        log(conn, aid, user["email"], "concluded", f"{c} (written to {where})")
        _note(conn, s, user["email"], "root cause concluded", f"{a['name']}: {c}")
    return row


def addendum(conn, email: str, aid: int, text: str) -> dict:
    a = get(conn, aid)
    if a["status"] == "open":
        raise CauseError(say("the analysis is open: change it directly"))
    t = CR.text(text, "the addendum", 2000)
    with conn.transaction():
        row = conn.execute("insert into cause_addenda (analysis_id, text, email) values (%s, %s, %s) returning *",
                           (aid, t, email)).fetchone()
        log(conn, aid, email, "addendum", t)
    return row


def cancel(conn, email: str, aid: int, reason: str) -> dict:
    r = CR.text(reason, "why it is cancelled", 1000)
    with conn.transaction():
        a = _open(conn, aid)
        row = conn.execute("update cause_analyses set status = 'cancelled', cancel_reason = %s where id = %s "
                           "returning *", (r, aid)).fetchone()
        log(conn, aid, email, "cancelled", r)
        _note(conn, subject(conn, a["ref_kind"], a["ref_id"]), email, "cause analysis cancelled", f"{a['name']}: {r}")
    return row
