"""Measuring equipment and calibration, step 17f (ADR-0017; dee-qms PLAN-CAL).

Equipment is registered out of service and goes into service with its first good calibration, approved (signed)
by someone other than whoever recorded or last changed the record. A failed calibration, once approved, takes the
equipment out of service and lists the incoming inspections it measured since its last good calibration; Quality
assesses them (signed, a nonconformance report may be opened) and the equipment returns to service only with that
assessment done and a good calibration after the failure. Incoming inspection names the equipment for each measured
characteristic; it is checked when the inspector signs.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.quality import cal_rules as CR
from wqops.hub.quality import records as Q

FIELDS = {"name", "kind", "range_text", "location", "owner", "interval_months", "acceptance", "traceability"}


class CalError(ValueError):
    pass


def _iso(row: dict | None) -> dict | None:
    return None if row is None else {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, gid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into gauge_log (gauge_id, email, action, note) values (%s, %s, %s, %s)",
                 (gid, email, action, (note or "")[:2000]))


def get(conn, gid: int) -> dict:
    row = conn.execute("select * from gauges where id = %s", (gid,)).fetchone()
    if row is None:
        raise KeyError(gid)
    return row


def _fields(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if k not in FIELDS:
            raise CalError(f"equipment has no field {k!r} to change")
        if k == "interval_months":
            if type(v) is not int or not 1 <= v <= 120:
                raise CalError("the calibration interval is 1 to 120 months")
            out[k] = v
        else:
            out[k] = str(v or "").strip()[:1000] or (None if k == "owner" else "")
    return out


def add(conn, email: str, code: str, data: dict) -> dict:
    code = str(code or "").strip()
    if not code:
        raise CalError("give the equipment its ID")
    f = _fields(data)
    if not f.get("name"):
        raise CalError("give the equipment a name")
    if "interval_months" not in f:
        raise CalError("how many months between calibrations?")
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-gauges'))")
        if conn.execute("select 1 from gauges where lower(code) = lower(%s)", (code,)).fetchone():
            raise CalError(f"equipment {code} already exists")
        cols = ["code", "created_by", *f]
        row = conn.execute(f"insert into gauges ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *", [code, email, *f.values()]).fetchone()
        log(conn, row["id"], email, "registered", "out of service until its first good calibration is approved")
    return row


def change(conn, email: str, gid: int, data: dict) -> dict:
    g = get(conn, gid)
    if g["status"] == "retired":
        raise CalError("the equipment is retired")
    f = {k: v for k, v in _fields(data).items() if v != g[k]}
    if not f:
        return g
    if "interval_months" in f and g["last_pass"]:
        f["next_due"] = CR.add_months(g["last_pass"], f["interval_months"])
    with conn.transaction():
        row = conn.execute("update gauges set " + ", ".join(f"{k} = %({k})s" for k in f)  # noqa: S608
                           + ", updated_at = now() where id = %(id)s returning *", {**f, "id": gid}).fetchone()
        log(conn, gid, email, "changed", "; ".join(f"{k}: {g[k] if k in g else '-'} -> {v}" for k, v in f.items()))
    return row


def retire(conn, email: str, gid: int, reason: str) -> dict:
    if not reason.strip():
        raise CalError("give the reason")
    with conn.transaction():
        row = conn.execute("update gauges set status = 'retired', retired_reason = %s, updated_at = now() where id = "
                           "%s and status <> 'retired' returning *", (reason.strip()[:1000], gid)).fetchone()
        if row is None:
            raise CalError("it is already retired")
        log(conn, gid, email, "retired", reason.strip())
    return row


# ---------------------------------------------------------------- calibrations

def _cal(conn, cid: int) -> dict:
    row = conn.execute("select * from gauge_calibrations where id = %s", (cid,)).fetchone()
    if row is None:
        raise KeyError(cid)
    return row


def _cal_fields(data: dict, today: dt.date) -> dict:
    out = {}
    if "done_on" in data:
        try:
            out["done_on"] = dt.date.fromisoformat(str(data["done_on"])[:10])
        except ValueError as exc:
            raise CalError("the calibration date is a date like 2026-10-31") from exc
        if out["done_on"] > today:
            raise CalError("the calibration date cannot be after today")
    if "result" in data:
        if data["result"] not in ("pass", "fail"):
            raise CalError("the result is pass or fail (out of tolerance)")
        out["result"] = data["result"]
    for k in ("done_by", "certificate", "as_found", "as_left"):
        if k in data:
            out[k] = str(data[k] or "").strip()[:2000]
    return out


def record(conn, email: str, gid: int, data: dict, *, today: dt.date) -> dict:
    g = get(conn, gid)
    if g["status"] == "retired":
        raise CalError("the equipment is retired")
    f = _cal_fields(data, today)
    for need, what in (("done_on", "the date"), ("done_by", "who calibrated it"), ("result", "the result")):
        if not f.get(need):
            raise CalError(f"give {what}")
    with conn.transaction():
        row = conn.execute("insert into gauge_calibrations (gauge_id, done_on, done_by, certificate, result, as_found, "
                           "as_left, recorded_by, changed_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (gid, f["done_on"], f["done_by"], f.get("certificate", ""), f["result"],
                            f.get("as_found", ""), f.get("as_left", ""), email, email)).fetchone()
        log(conn, gid, email, "calibration recorded", f"{f['done_on']}: {f['result']}")
    return row


def change_calibration(conn, user: dict, cid: int, data: dict, *, today: dt.date) -> dict:
    """A draft is changed by whoever recorded it, or by Quality."""
    from wqops.hub import permissions as P  # noqa: PLC0415 - permissions are a plain table

    c = _cal(conn, cid)
    if c["status"] != "draft":
        raise CalError("the calibration is approved: it cannot change")
    if user["email"] != c["recorded_by"] and not P.allows(user["roles"], "qms:configure"):
        raise PermissionError("whoever recorded it, or Quality, changes it")
    f = _cal_fields(data, today)
    if not f:
        return c
    with conn.transaction():
        row = conn.execute("update gauge_calibrations set " + ", ".join(f"{k} = %({k})s" for k in f)  # noqa: S608
                           + ", changed_by = %(by)s where id = %(id)s and status = 'draft' returning *",
                           {**f, "by": user["email"], "id": cid}).fetchone()
        log(conn, c["gauge_id"], user["email"], "calibration changed", ", ".join(sorted(f)))
    return row


def measured_since(conn, gid: int, since: dt.date | None) -> list[dict]:
    """The incoming inspections this equipment measured, signed on or after a day (all of them if None)."""
    rows = conn.execute(
        "select i.id, i.name, i.item_code, i.supplier, i.lot_no, i.signed_at, i.result, i.status from iqc_gauges g "
        "join iqc_inspections i on i.id = g.inspection_id where g.gauge_id = %s and i.signed_at is not null and "
        "(%s::date is null or i.signed_at >= %s::date - 1) group by i.id order by i.signed_at",   # a day early: any
        (gid, since, since)).fetchall()                                                           # time zone
    return [_iso(r) for r in rows]


def approve(conn, user: dict, cid: int, password: str, *, today: dt.date) -> dict:
    """Approve a calibration, signed, by someone other than whoever recorded or last changed it. A pass puts the
    equipment in service (unless an out-of-tolerance assessment is open) and sets its next due date; a fail takes
    it out of service and lists what it measured since its last good calibration for assessment."""
    c = _cal(conn, cid)
    if c["status"] != "draft":
        raise CalError("the calibration is already approved")
    if user["email"] in (c["recorded_by"], c["changed_by"]):
        raise PermissionError("someone other than whoever recorded or last changed it approves it")
    _date_rules(conn, c, get(conn, c["gauge_id"]))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        g = conn.execute("select * from gauges where id = %s for update", (c["gauge_id"],)).fetchone()
        _date_rules(conn, c, g)                       # again, under the lock: another approval may have come first
        Q._sign(conn, user, f"Calibration approved ({c['result']})", "calibration", cid, g["code"])
        if conn.execute("update gauge_calibrations set status = 'approved', approved_by = %s, approved_at = now() "
                        "where id = %s and status = 'draft' returning id", (user["email"], cid)).fetchone() is None:
            raise CalError("the calibration changed meanwhile: open it again")
        if c["result"] == "pass":
            due = CR.add_months(c["done_on"], g["interval_months"])
            open_ = conn.execute("select 1 from gauge_impacts where gauge_id = %s and status = 'open'",
                                 (g["id"],)).fetchone()
            conn.execute("update gauges set last_pass = %s, next_due = %s, status = %s, updated_at = now() where "
                         "id = %s", (c["done_on"], due, "out_of_service" if open_ else "in_service", g["id"]))
            log(conn, g["id"], user["email"], "calibration approved", f"pass on {c['done_on']}; next due {due}"
                + ("; stays out of service until the out-of-tolerance assessment is signed" if open_ else ""))
        else:
            # what it measured since its last good calibration before this one
            prev = conn.execute("select max(done_on) as d from gauge_calibrations where gauge_id = %s and status = "
                                "'approved' and result = 'pass' and done_on < %s", (g["id"], c["done_on"])).fetchone()
            since = prev["d"]
            hit = measured_since(conn, g["id"], since)
            from wqops.hub.quality import production as PRD  # noqa: PLC0415 - production imports this module

            lots = PRD.measured_since(conn, g["id"], since)
            conn.execute("update gauges set status = 'out_of_service', updated_at = now() where id = %s", (g["id"],))
            conn.execute("insert into gauge_impacts (gauge_id, calibration_id, since, inspections, production) values "
                         "(%s, %s, %s, %s, %s)", (g["id"], cid, since, Jsonb(hit), Jsonb(lots)))
            log(conn, g["id"], user["email"], "out of tolerance", f"on {c['done_on']}: out of service; "
                f"{len(hit)} inspections and {len(lots)} production lots measured since "
                f"{since or 'it was registered'} to assess")
    return get(conn, g["id"])


def _date_rules(conn, c: dict, g: dict) -> None:
    if g["status"] == "retired":
        raise CalError("the equipment is retired")
    if c["result"] == "pass":
        if g["last_pass"] and c["done_on"] < g["last_pass"]:
            raise CalError(f"a good calibration on {g['last_pass']} is already approved: this one is older")
        fail = conn.execute("select max(done_on) as d from gauge_calibrations where gauge_id = %s and status = "
                            "'approved' and result = 'fail'", (g["id"],)).fetchone()["d"]
        if fail and c["done_on"] <= fail:
            raise CalError(f"it was found out of tolerance on {fail}: a good calibration must be after that")


def assess(conn, user: dict, impact_id: int, password: str, conclusion: str, *, open_ncr: bool = False) -> dict:
    """Quality's signed conclusion on what an out-of-tolerance instrument measured; a nonconformance report may
    be opened. With a good calibration after the failure, the equipment returns to service."""
    imp = conn.execute("select * from gauge_impacts where id = %s", (impact_id,)).fetchone()
    if imp is None:
        raise KeyError(impact_id)
    if imp["status"] != "open":
        raise CalError("it is already assessed")
    if not conclusion.strip():
        raise CalError("write the conclusion: were the results it measured still valid?")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        g = conn.execute("select * from gauges where id = %s for update", (imp["gauge_id"],)).fetchone()
        if conn.execute("select status from gauge_impacts where id = %s for update",
                        (impact_id,)).fetchone()["status"] != "open":
            raise CalError("it is already assessed")
        ncr = None
        if open_ncr:
            ncr = Q.create_ncr(conn, user["email"], title=f"Out-of-tolerance equipment {g['code']}",
                               description=f"{g['code']} {g['name']} was found out of tolerance. "
                                           f"{len(imp['inspections'])} incoming inspections measured with it since "
                                           f"{imp['since'] or 'it was registered'}: "
                                           + ", ".join(x["name"] for x in imp["inspections"][:30])
                                           + (". Production lots: " + ", ".join(
                                               f"{x['item_code']} lot {x['lot_no']}" for x in imp["production"][:30])
                                              if imp.get("production") else "")
                                           + f". Assessment: {conclusion.strip()}")
        Q._sign(conn, user, "Out-of-tolerance assessment", "calibration_impact", impact_id, g["code"])
        conn.execute("update gauge_impacts set status = 'assessed', conclusion = %s, ncr_id = %s, assessed_by = %s, "
                     "assessed_at = now() where id = %s", (conclusion.strip()[:4000], ncr["id"] if ncr else None,
                                                            user["email"], impact_id))
        log(conn, g["id"], user["email"], "out-of-tolerance assessed", conclusion.strip()
            + (f" ({ncr['name']})" if ncr else ""))
        good_after = conn.execute(
            "select 1 from gauge_calibrations p join gauge_calibrations f on f.id = %s where p.gauge_id = %s and "
            "p.status = 'approved' and p.result = 'pass' and p.done_on > f.done_on",
            (imp["calibration_id"], g["id"])).fetchone()
        still = conn.execute("select 1 from gauge_impacts where gauge_id = %s and status = 'open'",
                             (g["id"],)).fetchone()
        if good_after and not still and g["status"] == "out_of_service":
            conn.execute("update gauges set status = 'in_service', updated_at = now() where id = %s", (g["id"],))
            log(conn, g["id"], user["email"], "back in service")
    return get(conn, g["id"])


# ---------------------------------------------------------------- reading

def listing(conn, today: dt.date) -> list[dict]:
    out = []
    for g in conn.execute("select * from gauges order by status = 'retired', code").fetchall():
        ok, why = CR.usable(g, today)
        out.append({**_iso(g), "usable": ok, "why": why,
                    "overdue": bool(g["next_due"] and g["next_due"] < today and g["status"] != "retired"),
                    "open_impacts": conn.execute("select count(*) as n from gauge_impacts where gauge_id = %s and "
                                                 "status = 'open'", (g["id"],)).fetchone()["n"]})
    return out


def view(conn, gid: int, today: dt.date) -> dict:
    g = get(conn, gid)
    ok, why = CR.usable(g, today)
    cals = conn.execute("select * from gauge_calibrations where gauge_id = %s order by done_on desc, id desc",
                        (gid,)).fetchall()
    imps = conn.execute("select * from gauge_impacts where gauge_id = %s order by id desc", (gid,)).fetchall()
    return {**_iso(g), "usable": ok, "why": why, "calibrations": [_iso(c) for c in cals],
            "impacts": [_iso(i) for i in imps],
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from gauge_log where gauge_id = "
                                                      "%s order by id", (gid,)).fetchall()],
            "used_by": measured_since(conn, gid, None)[-50:]}


def usable_gauges(conn, today: dt.date) -> list[dict]:
    return [{"id": g["id"], "code": g["code"], "name": g["name"], "next_due": g["next_due"]}
            for g in listing(conn, today) if g["usable"]]


def in_use(conn) -> bool:
    """Measuring equipment is registered (so incoming inspection names it)."""
    return conn.execute("select 1 from gauges where status <> 'retired' limit 1").fetchone() is not None


def register_view(conn) -> list[dict]:
    """The equipment as the ISO calibration check reads the calibration register: one entry per piece with an
    approved calibration; a piece out of service after a failure reads as failed, dated by that failure."""
    out = []
    for g in conn.execute("select * from gauges where status <> 'retired' order by id").fetchall():
        last = conn.execute("select done_on, result from gauge_calibrations where gauge_id = %s and status = "
                            "'approved' order by done_on desc, approved_at desc limit 1", (g["id"],)).fetchone()
        if last is None:
            continue
        failed = g["status"] == "out_of_service"
        on = last["done_on"] if failed else g["last_pass"]
        out.append({"id": f"g{g['id']}", "values": {"equipment": g["code"], "description": g["name"],
                                                     "calibrated_on": on.isoformat(),
                                                     "next_due": g["next_due"].isoformat() if g["next_due"] and
                                                     not failed else None,
                                                     "result": "fail" if failed else "pass"},
                    "signed": True, "imported": False})
    return out
