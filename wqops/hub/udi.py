"""Unique device identification, scanning and labels (ADR-0020, 20b). Plain code: no AI, no network.

The device identifier of an item is the company's, from its issuing agency (GS1 or HIBCC); it is checked, never made
up. A label is made for a released production lot: the lot number and the production date come from the production
record, an expiry date only if the person gives it. A scanned code is read and matched to the item, the production
lots and the incoming lots it may be.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from wqops.hub import udi_rules as U


class UdiError(ValueError):
    pass


def items(conn) -> list[dict]:
    return [dict(r, set_at=r["set_at"].isoformat()) for r in conn.execute("select * from udi_items order by item_code")]


def item(conn, item_code: str) -> dict | None:
    return conn.execute("select * from udi_items where item_code = %s", (item_code,)).fetchone()


def set_di(conn, email: str, item_code: str, data: dict) -> dict:
    """Record (or change) an item's device identifier: a GTIN for GS1, or LIC, product number and unit for HIBC."""
    item_code = str(item_code or "").strip()
    if not conn.execute("select 1 from ont_objects where type = 'Item' and key = %s and not deleted",
                        (item_code,)).fetchone():
        raise UdiError(f"{item_code or 'the item'} is not an item in ERPNext")
    agency = data.get("agency")
    try:
        if agency == "gs1":
            di = U.gtin14(data.get("gtin"))
        elif agency == "hibcc":
            di = U.hibc_di(data.get("lic"), data.get("pcn"), data.get("unit"))
        else:
            raise UdiError("choose GS1 or HIBCC")
    except U.UdiError as exc:
        raise UdiError(str(exc)) from exc
    with conn.transaction():
        other = conn.execute("select item_code from udi_items where di = %s and item_code <> %s",
                             (di, item_code)).fetchone()
        if other:
            raise UdiError(f"{di} is already the identifier of {other['item_code']}")
        old = item(conn, item_code)
        row = conn.execute("insert into udi_items (item_code, agency, di, set_by) values (%s, %s, %s, %s) on conflict "
                           "(item_code) do update set agency = excluded.agency, di = excluded.di, set_by = "
                           "excluded.set_by, set_at = now() returning *", (item_code, agency, di, email)).fetchone()
        conn.execute("insert into udi_log (item_code, email, action, note) values (%s, %s, %s, %s)",
                     (item_code, email, "changed" if old else "set", f"{old['di']} -> {di}" if old else di))
    return row


def history(conn, item_code: str) -> list[dict]:
    return [dict(r, at=r["at"].isoformat()) for r in conn.execute(
        "select email, action, note, at from udi_log where item_code = %s order by id", (item_code,))]


def label(conn, record_id: int, *, expiry: dt.date | None = None, tz: str = "UTC") -> dict:
    """What goes on the label of a released production lot: the code to print and the lines beside it."""
    r = conn.execute("select * from prod_records where id = %s", (record_id,)).fetchone()
    if r is None:
        raise KeyError(record_id)
    if r["status"] != "released":
        raise UdiError(f"{r['name']} is {r['status'].replace('_', ' ')}: labels are printed for released lots")
    u = item(conn, r["item_code"])
    if u is None:
        raise UdiError(f"{r['item_code']} has no device identifier yet: add it under Device identifiers")
    made = (r["submitted_at"] or r["created_at"]).astimezone(ZoneInfo(tz)).date()   # when the lot was finished
    if expiry and expiry <= made:
        raise UdiError("the expiry date is after the production date")
    try:
        if u["agency"] == "gs1":
            data, text = U.gs1_data(u["di"], lot=r["lot_no"], production=made, expiry=expiry)
        else:
            data = text = U.hibc_data(u["di"], lot=r["lot_no"], expiry=expiry)
    except U.UdiError as exc:
        raise UdiError(str(exc)) from exc
    lines = [r["item_code"], f"LOT {r['lot_no']}", f"MFG {made.isoformat()}"] + \
        ([f"EXP {expiry.isoformat()}"] if expiry else [])
    return {"record": r["name"], "item_code": r["item_code"], "agency": u["agency"], "di": u["di"], "data": data,
            "text": text, "lines": lines, "production_date": made.isoformat(),
            "expiry_date": expiry.isoformat() if expiry else None}


def printed(conn, email: str, record_id: int, lab: dict, *, fmt: str, copies: int) -> dict:
    return conn.execute(
        "insert into label_prints (record_id, item_code, agency, udi, format, copies, expiry, printed_by) values "
        "(%s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (record_id, lab["item_code"], lab["agency"], lab["text"], fmt, copies, lab["expiry_date"], email)).fetchone()


def prints(conn, record_id: int) -> list[dict]:
    return [dict(r, at=r["at"].isoformat(), expiry=r["expiry"].isoformat() if r["expiry"] else None)
            for r in conn.execute("select * from label_prints where record_id = %s order by id", (record_id,))]


def look_up(conn, code: str, today: dt.date) -> dict:
    """A scanned code read, and what it may be in WenQuest Ops: the item, its production lots, its incoming lots."""
    try:
        p = U.parse(code, today)
    except U.UdiError as exc:
        raise UdiError(str(exc)) from exc
    it = None
    if p.get("di"):
        row = conn.execute("select item_code from udi_items where di = %s", (p["di"],)).fetchone()
        it = row["item_code"] if row else None
    lot = p.get("lot") or p.get("serial")
    found: dict = {"item_code": it, "production": [], "incoming": []}
    if lot:
        cond, args = ("item_code = %s and ", [it]) if it else ("", [])
        found["production"] = [dict(r) for r in conn.execute(
            f"select id, name, item_code, lot_no, status from prod_records where {cond}lower(btrim(lot_no)) = "  # noqa: S608
            "lower(btrim(%s)) and status <> 'cancelled' order by id", [*args, lot])]
        found["incoming"] = [dict(r) for r in conn.execute(
            f"select id, name, item_code, lot_no, status from iqc_inspections where {cond}lower(btrim(lot_no)) = "  # noqa: S608
            "lower(btrim(%s)) and status <> 'void' order by id", [*args, lot])]
    return {"read": p, "found": found}
