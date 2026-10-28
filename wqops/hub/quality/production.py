"""Production records, step 17i (ADR-0017; dee-qms PLAN-DHR).

The items, lots and work orders are ERPNext's; WenQuest Ops keeps what ERPNext does not: a controlled template of
steps for an item (activated with a signature by someone who did not edit it, then fixed; a new version retires the
old), and for each lot a production record started from the active template. Its steps are recorded in order with
the operator's password; measurements are judged by code against the limits; equipment named must be in
calibration; the operator must have confirmed reading the documents the template follows (a setting). A failed step
needs a nonconformance report. The material lots used come from released incoming inspections, never more than a
lot held. Quality releases or rejects the lot with a signature, someone who recorded nothing in it; nonconformances
must be closed and no out-of-tolerance assessment may be open on equipment it used. Nothing is deleted.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from psycopg.types.json import Jsonb

from wqops import i18n as I18N
from wqops.hub.ont import metrics as M
from wqops.hub.quality import cal_rules as CALR
from wqops.hub.quality import iqc as I
from wqops.hub.quality import prod_rules as PR
from wqops.hub.quality import records as Q
from wqops.i18n import say

STEP_FIELDS = {"name", "instruction", "kind", "low", "high", "unit", "gauge_required"}


class ProdError(ValueError):
    pass


def _plain(v):
    if isinstance(v, Decimal):
        return float(v)
    return v.isoformat() if hasattr(v, "isoformat") else v


def _iso(row: dict) -> dict:
    return {k: _plain(v) for k, v in row.items()}


def log(conn, kind: str, ref: int, email: str | None, action: str, note: str = "") -> None:  # noqa: PLR0917
    conn.execute("insert into prod_log (kind, ref_id, email, action, note) values (%s, %s, %s, %s, %s)",
                 (kind, ref, email, action, (note or "")[:2000]))


_STEP_EVENT = re.compile(r"step (\d+) (pass|fail|nonconformance)")


def _action(a: str) -> str:
    """An event name as stored (English) in the reader's language."""
    m = _STEP_EVENT.fullmatch(a or "")
    if m:
        return {"pass": say("step {seq} pass", seq=m[1]), "fail": say("step {seq} fail", seq=m[1]),
                "nonconformance": say("step {seq} nonconformance", seq=m[1])}[m[2]]
    return I18N.label(a)


def _history(conn, kind: str, ref: int) -> list[dict]:
    return [{**_iso(r), "action": _action(r["action"])} for r in conn.execute(
        "select at, email, action, note from prod_log where kind = %s and ref_id = %s order by id", (kind, ref))]


def _items(conn) -> set[str]:
    return {o["key"] for o in M._objs(conn, "Item")}


def _item(conn, code) -> str:
    code = str(code or "").strip()
    if not code:
        raise ProdError(say("choose the item"))
    known = _items(conn)
    if known and code not in known:
        raise ProdError(say("{code} is not an item in ERPNext", code=code))
    return code


# ---------------------------------------------------------------- templates

def template(conn, tid: int, lock: bool = False) -> dict:
    sql = "select * from prod_templates where id = %s"
    if lock:
        sql += " for update"
    row = conn.execute(sql, (tid,)).fetchone()
    if row is None:
        raise KeyError(tid)
    return row


def template_steps(conn, tid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from prod_template_steps where template_id = %s order by seq",
                                          (tid,))]


def create_template(conn, email: str, data: dict) -> dict:
    code = str(data.get("code") or "").strip().upper()
    if not code:
        raise ProdError(say("give the template a code"))
    item = _item(conn, data.get("item_code"))
    with conn.transaction():
        if conn.execute("select 1 from prod_templates where code = %s", (code,)).fetchone():
            raise ProdError(say("template {code} exists: start a new version of it", code=code))
        row = conn.execute("insert into prod_templates (code, item_code, title, editors, created_by) values "
                           "(%s, %s, %s, %s, %s) returning *", (code[:60], item, str(data.get("title") or "")[:300],
                                                                [email], email)).fetchone()
        log(conn, "template", row["id"], email, "drafted", say("{code} for {item}", code=code, item=item))
    return row


def _draft_template(conn, tid: int) -> dict:
    t = template(conn, tid, lock=True)
    if t["status"] != "draft":
        raise ProdError(say("the template is {status}: start a new version to change it", status=Q.word(t['status'])))
    return t


def _touch_template(conn, t: dict, email: str) -> None:
    conn.execute("update prod_templates set editors = (select array_agg(distinct e) from unnest(editors || %s::text) "
                 "e), updated_at = now() where id = %s", (email, t["id"]))


def update_template(conn, email: str, tid: int, data: dict) -> dict:
    bad = set(data) - {"title", "item_code", "documents", "materials"}
    if bad:
        raise ProdError(say("{bad} cannot be changed here", bad=Q.word(sorted(bad)[0])))
    with conn.transaction():
        t = _draft_template(conn, tid)
        d = {}
        if "title" in data:
            d["title"] = str(data["title"] or "")[:300]
        if "item_code" in data:
            d["item_code"] = _item(conn, data["item_code"])
        if "documents" in data:
            nums = data["documents"]
            if not isinstance(nums, list) or any(not isinstance(x, str) for x in nums):
                raise ProdError(say("the documents are document numbers"))
            nums = sorted({x.strip() for x in nums if x.strip()})
            known = {r["number"] for r in conn.execute("select distinct number from documents where number = any(%s) "
                                                       "and status = 'effective'", (nums,))}
            if set(nums) - known:
                raise ProdError(say("no revision in effect: {list}", list=Q.join(sorted(set(nums) - known))))
            d["documents"] = Jsonb(nums)
        if "materials" in data:
            codes = data["materials"]
            if not isinstance(codes, list) or any(not isinstance(x, str) for x in codes):
                raise ProdError(say("the materials are item codes"))
            d["materials"] = Jsonb(sorted({_item(conn, x) for x in codes if x.strip()}))
        d = {k: v for k, v in d.items() if (v.obj if isinstance(v, Jsonb) else v) != t[k]}
        if d:
            conn.execute("update prod_templates set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                         + ", updated_at = now() where id = %(id)s", {**d, "id": tid})
            _touch_template(conn, t, email)
            log(conn, "template", tid, email, "changed", Q.join(Q.word(k) for k in sorted(d)))
    return template(conn, tid)


def _step_values(data: dict, current: dict | None = None) -> dict:
    bad = set(data) - STEP_FIELDS
    if bad:
        raise ProdError(say("{bad} is not part of a step", bad=sorted(bad)[0]))
    s = {**(current or {"kind": "check", "low": None, "high": None, "unit": "", "gauge_required": False,
                        "instruction": "", "name": ""}), **data}
    if s["kind"] not in PR.KINDS:
        raise ProdError(say("a step is a check, a measurement or a record"))
    s["name"] = str(s.get("name") or "").strip()[:300]
    if not s["name"]:
        raise ProdError(say("name the step"))
    s["instruction"] = str(s.get("instruction") or "")[:4000]
    s["unit"] = str(s.get("unit") or "")[:40]
    for k in ("low", "high"):
        if s.get(k) in (None, ""):
            s[k] = None
        else:
            v = PR.stored(s[k])
            if v is None:
                raise ProdError(say("the lower limit is a number") if k == "low" else
                                say("the upper limit is a number"))
            s[k] = v
    s["gauge_required"] = bool(s.get("gauge_required"))
    if s["kind"] != "measure":
        s.update(low=None, high=None, gauge_required=False)
    elif s["low"] is not None and s["high"] is not None and s["low"] > s["high"]:
        raise ProdError(say("the lower limit is above the upper limit"))
    return {k: s[k] for k in STEP_FIELDS}


def add_step(conn, email: str, tid: int, data: dict) -> dict:
    with conn.transaction():
        t = _draft_template(conn, tid)
        s = _step_values(data)
        seq = conn.execute("select coalesce(max(seq), 0) + 1 as n from prod_template_steps where template_id = %s",
                           (tid,)).fetchone()["n"]
        cols = ["template_id", "seq", *s]
        row = conn.execute(f"insert into prod_template_steps ({', '.join(cols)}) values "  # noqa: S608
                           f"({', '.join(['%s'] * len(cols))}) returning *", [tid, seq, *s.values()]).fetchone()
        _touch_template(conn, t, email)
        log(conn, "template", tid, email, "step added", f"{seq}: {s['name']}")
    return row


def update_step(conn, email: str, tid: int, sid: int, data: dict) -> dict:
    with conn.transaction():
        t = _draft_template(conn, tid)
        cur = conn.execute("select * from prod_template_steps where id = %s and template_id = %s",
                           (sid, tid)).fetchone()
        if cur is None:
            raise KeyError(sid)
        s = _step_values(data, {k: cur[k] for k in STEP_FIELDS})
        row = conn.execute("update prod_template_steps set " + ", ".join(f"{k} = %({k})s" for k in s)  # noqa: S608
                           + " where id = %(id)s returning *", {**s, "id": sid}).fetchone()
        _touch_template(conn, t, email)
        log(conn, "template", tid, email, "step changed", f"{cur['seq']}: {s['name']}")
    return row


def remove_step(conn, email: str, tid: int, sid: int) -> None:
    with conn.transaction():
        t = _draft_template(conn, tid)
        row = conn.execute("delete from prod_template_steps where id = %s and template_id = %s returning *",
                           (sid, tid)).fetchone()
        if row is None:
            raise KeyError(sid)
        # keep the numbers continuous
        for i, s in enumerate(template_steps(conn, tid), 1):
            if s["seq"] != i:
                conn.execute("update prod_template_steps set seq = %s where id = %s", (i, s["id"]))
        _touch_template(conn, t, email)
        log(conn, "template", tid, email, "step removed", f"{row['seq']}: {row['name']}")


def activate(conn, user: dict, tid: int, password: str) -> dict:
    """Signed by someone who did not draft or edit it (a setting); fixed with its fingerprint; the version before
    it is retired."""
    t = template(conn, tid)
    if t["status"] != "draft":
        raise ProdError(say("activate a draft template"))
    by_other = I.settings(conn)["template_by_other"]
    if by_other and (user["email"] in t["editors"] or user["email"] == t["created_by"]):
        raise PermissionError(say("someone who did not draft or edit the template activates it"))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        t = _draft_template(conn, tid)
        if by_other and user["email"] in t["editors"]:
            raise PermissionError(say("someone who did not draft or edit the template activates it"))
        steps = template_steps(conn, tid)
        missing = PR.template_needs(t, steps)
        if missing:
            raise ProdError(say("still needed: {list}", list=Q.join(missing, "; ")))
        fp = PR.template_print(t, steps)
        old = conn.execute("select id, version from prod_templates where code = %s and status = 'active' for update",
                           (t["code"],)).fetchone()
        if old:
            conn.execute("update prod_templates set status = 'retired', updated_at = now() where id = %s", (old["id"],))
            log(conn, "template", old["id"], user["email"], "retired",
                say("by version {version}", version=t["version"]))
        Q._sign(conn, user, say("Production template activated"), "prod_template", tid, f"{t['code']} v{t['version']}")
        row = conn.execute("update prod_templates set status = 'active', activated_by = %s, activated_at = now(), "
                           "fingerprint = %s, updated_at = now() where id = %s returning *",
                           (user["email"], fp, tid)).fetchone()
        log(conn, "template", tid, user["email"], "activated", fp)
    return row


def new_version(conn, email: str, tid: int) -> dict:
    """From the active version; or from the latest one when none is active (all retired or withdrawn)."""
    with conn.transaction():
        t = template(conn, tid, lock=True)
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-template:{t['code']}",))
        if conn.execute("select 1 from prod_templates where code = %s and status = 'draft'", (t["code"],)).fetchone():
            raise ProdError(say("a new version is already being drafted"))
        latest = conn.execute("select max(version) as v, bool_or(status = 'active') as live from prod_templates "
                              "where code = %s", (t["code"],)).fetchone()
        if not (t["status"] == "active" or (not latest["live"] and t["version"] == latest["v"])):
            raise ProdError(say("start a new version from the active one"))
        v = conn.execute("select max(version) + 1 as v from prod_templates where code = %s",
                         (t["code"],)).fetchone()["v"]
        row = conn.execute("insert into prod_templates (code, version, previous_id, item_code, title, documents, "
                           "materials, editors, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (t["code"], v, tid, t["item_code"], t["title"], Jsonb(t["documents"]),
                            Jsonb(t["materials"]), [email], email)).fetchone()
        for s in template_steps(conn, tid):
            conn.execute("insert into prod_template_steps (template_id, seq, name, instruction, kind, low, high, unit, "
                         "gauge_required) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (row["id"], s["seq"], s["name"], s["instruction"], s["kind"], s["low"], s["high"], s["unit"],
                          s["gauge_required"]))
        log(conn, "template", row["id"], email, "new version", say("from version {version}", version=t["version"]))
    return row


def end_template(conn, email: str, tid: int, reason: str) -> dict:
    """Withdraw a draft, or retire the active version (no new lots start from it), with a reason."""
    if not reason.strip():
        raise ProdError(say("give the reason"))
    with conn.transaction():
        t = template(conn, tid, lock=True)
        to = {"draft": "withdrawn", "active": "retired"}.get(t["status"])
        if to is None:
            raise ProdError(say("the template is {status}", status=Q.word(t['status'])))
        row = conn.execute("update prod_templates set status = %s, updated_at = now() where id = %s returning *",
                           (to, tid)).fetchone()
        log(conn, "template", tid, email, to, reason.strip())
    return row


def templates(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute(
        "select t.*, (select count(*) from prod_template_steps s where s.template_id = t.id) as steps from "
        "prod_templates t order by code, version desc")]


def template_view(conn, tid: int) -> dict:
    t = template(conn, tid)
    steps = template_steps(conn, tid)
    return {**_iso(t), "steps": [_iso(s) for s in steps],
            "to_activate": PR.template_needs(t, steps) if t["status"] == "draft" else [],
            "intact": None if not t["fingerprint"] else PR.template_print(t, steps) == t["fingerprint"],
            "versions": [_iso(r) for r in conn.execute(
                "select id, version, status, activated_by, activated_at from prod_templates where code = %s order by "
                "version", (t["code"],))],
            "history": _history(conn, "template", tid), "signatures": Q.signatures(conn, "prod_template", tid)}


# ---------------------------------------------------------------- production records

def record(conn, rid: int, lock: bool = False) -> dict:
    sql = "select * from prod_records where id = %s"
    if lock:
        sql += " for update"
    row = conn.execute(sql, (rid,)).fetchone()
    if row is None:
        raise KeyError(rid)
    return row


def steps(conn, rid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from prod_steps where record_id = %s order by seq", (rid,))]


def materials(conn, rid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from prod_materials where record_id = %s order by id", (rid,))]


def _int(v, what: str) -> int:
    if type(v) is not int:
        raise ProdError(say("{what} is a whole number", what=what))
    return v


def start(conn, email: str, data: dict) -> dict:
    """A lot started from an active template: its steps are copied (later versions do not change it)."""
    tid = data.get("template_id")
    if type(tid) is not int:
        raise ProdError(say("choose the template"))
    lot = str(data.get("lot_no") or "").strip()
    if not lot:
        raise ProdError(say("give the lot or serial number"))
    qty = _int(data.get("planned_qty"), say("the quantity planned"))
    if qty < 1:
        raise ProdError(say("the quantity planned is at least 1"))
    with conn.transaction():
        t = conn.execute("select * from prod_templates where id = %s for share", (tid,)).fetchone()
        if t is None or t["status"] != "active":
            raise ProdError(say("start a lot from an active template"))
        if conn.execute("select 1 from prod_records where item_code = %s and lower(btrim(lot_no)) = lower(%s) and "
                        "status <> 'cancelled'", (t["item_code"], lot)).fetchone():
            raise ProdError(say("lot {lot} of {item_code} already has a production record",
                                lot=lot, item_code=t['item_code']))
        name = Q._next_name(conn, "prod_records", "DHR")
        row = conn.execute("insert into prod_records (name, template_id, template_print, item_code, lot_no, "
                           "work_order, planned_qty, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (name, tid, t["fingerprint"], t["item_code"], lot[:100],
                            str(data.get("work_order") or "").strip()[:140] or None, qty, email)).fetchone()
        for s in template_steps(conn, tid):
            conn.execute("insert into prod_steps (record_id, seq, name, instruction, kind, low, high, unit, "
                         "gauge_required) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (row["id"], s["seq"], s["name"], s["instruction"], s["kind"], s["low"], s["high"], s["unit"],
                          s["gauge_required"]))
        log(conn, "record", row["id"], email, "started", say("{code} v{version}, lot {lot}, {qty} planned",
                                                             code=t["code"], version=t["version"], lot=lot, qty=qty))
    return row


def _producing(conn, rid: int) -> dict:
    r = record(conn, rid, lock=True)
    if r["status"] != "in_production":
        raise ProdError(say("the production record is {status}", status=Q.word(r['status'])))
    return r


def _involve(conn, r: dict, email: str) -> None:
    if email not in r["involved"]:
        conn.execute("update prod_records set involved = array_append(involved, %s), updated_at = now() where id = %s",
                     (email, r["id"]))


def _trained(conn, email: str, t: dict) -> None:
    """The operator confirmed reading the revision in effect of each document the template follows."""
    for num in t["documents"] or []:
        d = conn.execute("select id, number, revision, needs_training from documents where number = %s and "
                         "status = 'effective' order by id desc limit 1", (num,)).fetchone()
        if d is None:
            raise ProdError(say("{num} has no revision in effect", num=num))
        if not d["needs_training"]:
            continue
        ok = conn.execute("select 1 from doc_training where document_id = %s and email = %s and status in "
                          "('acknowledged', 'waived')", (d["id"], email)).fetchone()
        if not ok:
            raise ProdError(say("confirm reading {num} rev {revision} first (My reading)",
                                num=num, revision=d['revision'] or '-'))


def record_step(conn, user: dict, rid: int, seq: int, password: str, data: dict, *,  # noqa: PLR0917
                today: dt.date) -> dict:
    """The operator records the next step with their password; a measurement is judged by code."""
    Q.check_signer(conn, user, password)
    with conn.transaction():
        r = _producing(conn, rid)
        ss = steps(conn, rid)
        nxt = PR.next_step(ss)
        if nxt is None:
            raise ProdError(say("every step is recorded"))
        if seq != nxt:
            raise ProdError(say("record step {nxt} first", nxt=nxt))
        s = next(x for x in ss if x["seq"] == seq)
        if I.settings(conn)["production_training"]:
            _trained(conn, user["email"], template(conn, r["template_id"]))
        verdict, why = PR.judge(s, value=data.get("value"), result=data.get("result"), text=data.get("text"))
        if verdict is None:
            raise ProdError(why)
        gid, gcode, gdue = data.get("gauge_id"), None, None
        if gid not in (None, ""):
            if s["kind"] != "measure" or type(gid) is not int:
                raise ProdError(say("equipment is named for a measurement"))
            # shared lock: an out-of-tolerance approval (which locks it) waits, or comes first and is seen here
            g = conn.execute("select * from gauges where id = %s for share", (gid,)).fetchone()
            if g is None:
                raise KeyError(gid)
            ok, msg = CALR.usable(g, today)
            if not ok:
                raise ProdError(say("{code}: {msg}; measure with equipment in calibration", code=g['code'], msg=msg))
            gcode, gdue = g["code"], g["next_due"]
        else:
            gid = None
            if s["gauge_required"]:
                raise ProdError(say("name the equipment used"))
        conn.execute("update prod_steps set result = %s, value = %s, text_value = %s, verdict = %s, gauge_id = %s, "
                     "gauge_code = %s, gauge_due = %s, done_by = %s, done_at = now() where id = %s",
                     (data.get("result") if s["kind"] == "check" else None,
                      PR.stored(data.get("value")) if s["kind"] == "measure" else None,
                      data["text"].strip()[:4000] if s["kind"] == "record" else None,
                      verdict, gid, gcode, gdue, user["email"], s["id"]))
        _involve(conn, r, user["email"])
        Q._sign(conn, user, say("Step {seq} recorded (pass)", seq=seq) if verdict == "pass" else
                say("Step {seq} recorded (fail)", seq=seq), "prod_step", s["id"],
                say("{name} step {seq}", name=r["name"], seq=seq))
        log(conn, "record", rid, user["email"], f"step {seq} {verdict}", why)
    return record(conn, rid)


def step_ncr(conn, email: str, rid: int, seq: int) -> dict:
    """A nonconformance report for a failed step, with the item, lot and what was found."""
    with conn.transaction():
        r = record(conn, rid, lock=True)
        if r["status"] not in ("in_production", "qa_review"):
            raise ProdError(say("the production record is {status}", status=Q.word(r['status'])))
        s = conn.execute("select * from prod_steps where record_id = %s and seq = %s for update",
                         (rid, seq)).fetchone()
        if s is None:
            raise KeyError(seq)
        if s["verdict"] != "fail":
            raise ProdError(say("a nonconformance report is opened for a failed step"))
        if s["ncr_id"] and Q.ncr(conn, s["ncr_id"])["status"] != "cancelled":
            raise ProdError(say("this step already has a nonconformance report"))
        found = (say("reading {value} {unit}, limits {limits}", value=s["value"], unit=s["unit"],
                     limits=PR.fmt_limits(s)) if s["kind"] == "measure" else say("the check failed"))
        n = Q.create_ncr(conn, email, title=say("{item_code} lot {lot_no}: step {seq} {step} failed",
                                                item_code=r["item_code"], lot_no=r["lot_no"], seq=seq, step=s["name"]),
                         description=say("Production record {name}, step {seq} ({step}): {found}.", name=r["name"],
                                         seq=seq, step=s["name"], found=found),
                         item_code=r["item_code"], quantity=r["planned_qty"])
        conn.execute("update prod_steps set ncr_id = %s where id = %s", (n["id"], s["id"]))
        log(conn, "record", rid, email, f"step {seq} nonconformance", n["name"])
    return n


def add_material(conn, email: str, rid: int, inspection_id, qty) -> dict:
    """A material lot used: a released incoming inspection; all lots of the record together never use more than the
    incoming lot held."""
    if type(inspection_id) is not int:
        raise ProdError(say("choose the incoming lot"))
    q = PR.stored(qty)
    if q is None or q <= 0:
        raise ProdError(say("the quantity used is a number above 0"))
    with conn.transaction():
        r = _producing(conn, rid)
        ins = conn.execute("select * from iqc_inspections where id = %s for update", (inspection_id,)).fetchone()
        if ins is None or ins["status"] != "released":
            raise ProdError(say("use a lot that incoming inspection released"))
        used = conn.execute("select coalesce(sum(qty), 0) as q from prod_materials where inspection_id = %s",
                            (inspection_id,)).fetchone()["q"]
        if used + q > ins["lot_qty"]:
            raise ProdError(say("lot {lot_no} held {lot_qty}; {used} is already used",
                                lot_no=ins['lot_no'] or ins['name'], lot_qty=ins['lot_qty'],
                                used=format(Decimal(used).normalize(), 'f')))
        row = conn.execute("insert into prod_materials (record_id, item_code, inspection_id, lot_no, supplier, qty, "
                           "added_by) values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (rid, ins["item_code"], inspection_id, ins["lot_no"], ins["supplier"], q, email)).fetchone()
        _involve(conn, r, email)
        log(conn, "record", rid, email, "material", say("{item_code} lot {lot_no}: {qty}", item_code=ins["item_code"],
                                                        lot_no=ins["lot_no"] or ins["name"], qty=f"{q.normalize():f}"))
    return row


def set_quantities(conn, email: str, rid: int, data: dict) -> dict:
    bad = set(data) - {"good_qty", "scrap_qty", "work_order"}
    if bad:
        raise ProdError(say("{bad} cannot be changed here", bad=Q.word(sorted(bad)[0])))
    with conn.transaction():
        r = _producing(conn, rid)
        d = {}
        for k in ("good_qty", "scrap_qty"):
            if k in data:
                d[k] = _int(data[k], say("good qty") if k == "good_qty" else say("scrap qty"))
                if d[k] < 0:
                    raise ProdError(say("the good quantity is not negative") if k == "good_qty" else
                                    say("the scrap quantity is not negative"))
        if "work_order" in data:
            d["work_order"] = str(data["work_order"] or "").strip()[:140] or None
        if d.get("good_qty", r["good_qty"]) + d.get("scrap_qty", r["scrap_qty"]) > r["planned_qty"]:
            raise ProdError(say("good and scrapped together are at most the quantity planned"))
        d = {k: v for k, v in d.items() if v != r[k]}
        if d:
            conn.execute("update prod_records set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                         + ", updated_at = now() where id = %(id)s", {**d, "id": rid})
            log(conn, "record", rid, email, "changed", "; ".join(f"{k}: {r[k]} -> {v}" for k, v in d.items()))
    return record(conn, rid)


def _ncr_status(conn, ss: list[dict]) -> dict[int, str]:
    ids = [s["ncr_id"] for s in ss if s["ncr_id"]]
    return {n["id"]: n["status"] for n in conn.execute("select id, status from ncr_records where id = any(%s)", (ids,))}


def on_hold(conn, rid: int) -> list[str]:
    """Equipment it used whose out-of-tolerance assessment is still open."""
    return [r["code"] for r in conn.execute(
        "select distinct g.code from gauge_impacts i join gauges g on g.id = i.gauge_id where i.status = 'open' and "
        "exists (select 1 from jsonb_array_elements(i.production) p where (p ->> 'id')::bigint = %s) order by g.code",
        (rid,))]


def submit(conn, email: str, rid: int) -> dict:
    with conn.transaction():
        r = _producing(conn, rid)
        ss = steps(conn, rid)
        missing = PR.to_submit(r, ss, materials(conn, rid), template(conn, r["template_id"])["materials"] or [],
                               _ncr_status(conn, ss))
        missing += [say("the out-of-tolerance assessment of {code} signed", code=g) for g in on_hold(conn, rid)]
        if missing:
            raise ProdError(say("still needed: {list}", list=Q.join(missing, "; ")))
        row = conn.execute("update prod_records set status = 'qa_review', submitted_by = %s, submitted_at = now(), "
                           "updated_at = now() where id = %s returning *", (email, rid)).fetchone()
        log(conn, "record", rid, email, "submitted for review")
    return row


def send_back(conn, email: str, rid: int, reason: str) -> dict:
    if not reason.strip():
        raise ProdError(say("say what needs to change"))
    with conn.transaction():
        r = record(conn, rid, lock=True)
        if r["status"] != "qa_review":
            raise ProdError(say("a record in review is sent back"))
        row = conn.execute("update prod_records set status = 'in_production', updated_at = now() where id = %s "
                           "returning *", (rid,)).fetchone()
        log(conn, "record", rid, email, "sent back", reason.strip())
    return row


def decide(conn, user: dict, rid: int, password: str, release: bool, note: str = "") -> dict:  # noqa: PLR0917
    """Quality releases or rejects the lot with a signature: someone who recorded nothing in it; to release, its
    nonconformances closed and no open out-of-tolerance assessment on equipment it used. Fixed with a fingerprint."""
    r = record(conn, rid)
    if r["status"] != "qa_review":
        raise ProdError(say("decide a record in review"))
    if user["email"] in r["involved"]:
        raise PermissionError(say("someone who recorded no step or material releases or rejects the lot"))
    if not release and not note.strip():
        raise ProdError(say("give the reason for rejecting it"))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        r = record(conn, rid, lock=True)
        if r["status"] != "qa_review":
            raise ProdError(say("the record changed meanwhile: open it again"))
        ss, mm = steps(conn, rid), materials(conn, rid)
        if release:
            missing = PR.to_release(ss, _ncr_status(conn, ss), on_hold(conn, rid))
            if missing:
                raise ProdError(say("still needed: {list}", list=Q.join(missing, "; ")))
        fp = PR.record_print(r, ss, mm)
        Q._sign(conn, user, say("Lot released") if release else say("Lot rejected"), "prod_record", rid,
                say("{name} {item_code} lot {lot_no}", name=r["name"], item_code=r["item_code"], lot_no=r["lot_no"]))
        row = conn.execute("update prod_records set status = %s, decided_by = %s, decided_at = now(), "
                           "decision_note = %s, fingerprint = %s, updated_at = now() where id = %s returning *",
                           ("released" if release else "rejected", user["email"], note.strip()[:2000], fp,
                            rid)).fetchone()
        log(conn, "record", rid, user["email"], "released" if release else "rejected", note.strip())
    return row


def cancel(conn, email: str, rid: int, reason: str) -> dict:
    if not reason.strip():
        raise ProdError(say("give the reason"))
    with conn.transaction():
        _producing(conn, rid)
        row = conn.execute("update prod_records set status = 'cancelled', cancel_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], rid)).fetchone()
        log(conn, "record", rid, email, "cancelled", reason.strip())
    return row


def listing(conn, status: str) -> list[dict]:
    where = {"open": "status in ('in_production', 'qa_review')", "released": "status = 'released'",
             "rejected": "status = 'rejected'", "cancelled": "status = 'cancelled'", "all": "true"}.get(status, "true")
    return [_iso(r) for r in conn.execute(f"select * from prod_records where {where} order by id desc "  # noqa: S608
                                          "limit 500")]


def view(conn, rid: int) -> dict:
    r = record(conn, rid)
    ss, mm = steps(conn, rid), materials(conn, rid)
    t = template(conn, r["template_id"])
    ncr = _ncr_status(conn, ss)
    hold = on_hold(conn, rid)
    return {**_iso(r), "template": {"id": t["id"], "code": t["code"], "version": t["version"],
                                    "documents": t["documents"], "materials": t["materials"]},
            "steps": [{**_iso(s), "limits": PR.fmt_limits(s) if s["kind"] == "measure" else "",
                       "ncr_status": ncr.get(s["ncr_id"]),
                       "ncr_name": Q.ncr(conn, s["ncr_id"])["name"] if s["ncr_id"] else None} for s in ss],
            "next_step": PR.next_step(ss), "materials": [_iso(m) for m in mm], "on_hold": hold,
            "to_submit": (PR.to_submit(r, ss, mm, t["materials"] or [], ncr)
                          + [say("the out-of-tolerance assessment of {code} signed", code=g) for g in hold])
            if r["status"] == "in_production" else [],
            "to_release": PR.to_release(ss, ncr, hold) if r["status"] == "qa_review" else [],
            "intact": None if not r["fingerprint"] else PR.record_print(r, ss, mm) == r["fingerprint"],
            "recalls": [_iso(x) for x in conn.execute("select id, name, status from recalls where status in "
                                                      "('draft', 'open') and scope @> %s::jsonb", (f"[{rid}]",))],
            "history": _history(conn, "record", rid), "signatures": Q.signatures(conn, "prod_record", rid)}


def lots_released(conn) -> list[dict]:
    """Incoming lots that can be used, with what is left of each."""
    return [_iso(r) for r in conn.execute(
        "select i.id, i.name, i.item_code, i.lot_no, i.supplier, i.lot_qty, i.lot_qty - coalesce((select sum(qty) "
        "from prod_materials m where m.inspection_id = i.id), 0) as left_qty from iqc_inspections i where "
        "i.status = 'released' order by i.id desc limit 500")]


def measured_since(conn, gid: int, since: dt.date | None) -> list[dict]:
    """Production lots this equipment measured on or after a day (all of them if None)."""
    return [_iso(r) for r in conn.execute(
        "select r.id, r.name, r.item_code, r.lot_no, r.status from prod_steps s join prod_records r on r.id = "
        "s.record_id where s.gauge_id = %s and s.done_at is not null and (%s::date is null or s.done_at >= "
        "%s::date - 1) group by r.id order by r.id", (gid, since, since))]


def summary(conn, since: dt.date, until: dt.date, tz: str = "UTC") -> dict:
    """For management review: lots released and rejected in the period, the first-pass share of those released
    (no failed step), and lots in production."""
    rel = conn.execute("select r.id, exists (select 1 from prod_steps s where s.record_id = r.id and s.verdict = "
                       "'fail') as failed from prod_records r where status = 'released' and "
                       "(decided_at at time zone %s)::date between %s and %s", (tz, since, until)).fetchall()
    return {"released": len(rel),
            "rejected": conn.execute("select count(*) as n from prod_records where status = 'rejected' and "
                                     "(decided_at at time zone %s)::date between %s and %s",
                                     (tz, since, until)).fetchone()["n"],
            "first_pass": round(sum(not r["failed"] for r in rel) / len(rel), 4) if rel else None,
            "in_production": conn.execute("select count(*) as n from prod_records where status in ('in_production', "
                                          "'qa_review')").fetchone()["n"]}
