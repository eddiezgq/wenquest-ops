"""Traceability, step 17i (ADR-0017; dee-qms PLAN-TRACE, PLAN-SHIP). Read only: it changes nothing.

Forward, from an incoming lot: the production lots that used it, who received them (ERPNext delivery notes) and the
complaints about them. Backward, from a production lot: the incoming lots, suppliers, equipment and nonconformance
reports behind it, the other lots that used the same incoming lots, who received it and the complaints. From a
complaint: the production lot it names (same item, same lot number), then backward from there.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.ont import metrics as M
from wqops.hub.quality import trace_rules as TR
from wqops.i18n import say


def _iso(row: dict) -> dict:
    from wqops.hub.quality import production as PRD  # noqa: PLC0415 - the same conversion

    return PRD._iso(row)


def bundles(conn) -> dict[str, list[dict]]:
    """The entries of each submitted, not cancelled Serial and Batch Bundle read from ERPNext."""
    return {o["key"]: o["props"].get("entries") or [] for o in M._objs(conn, "BatchBundle")
            if int(o["props"].get("docstatus") or 0) == 1 and not o["props"].get("is_cancelled")}


def notes(conn) -> list[dict]:
    """ERPNext delivery notes with their customer."""
    cust = {r["src_key"]: r["dst_key"] for r in conn.execute(
        "select src_key, dst_key from ont_links where src_type = 'DeliveryNote' and type = 'customer'")}
    return [{"key": o["key"], "props": o["props"], "customer": cust.get(o["key"])}
            for o in M._objs(conn, "DeliveryNote")]


def _records(conn, where: str, args) -> list[dict]:
    return [dict(r) for r in conn.execute(f"select * from prod_records where status <> 'cancelled' and {where} "  # noqa: S608
                                          "order by id", args)]


def complaints_about(conn, item_code: str, lot_no: str) -> list[dict]:
    return [_iso(r) for r in conn.execute(
        "select id, name, received_on, customer, status, description from complaints where item_code = %s and "
        "lower(btrim(lot_no)) = %s and lot_no <> '' and status <> 'cancelled' order by id",
        (item_code, TR.lot_key(lot_no)))]


def shipped(conn, recs: list[dict], dns: list[dict] | None = None) -> list[dict]:
    dns = notes(conn) if dns is None else dns
    out = []
    held = bundles(conn)
    for r in recs:
        since = (r["created_at"] - dt.timedelta(days=1)).date().isoformat()    # a day early: any time zone
        for d in TR.deliveries(dns, r["item_code"], r["lot_no"], since, held):
            out.append({**d, "record_id": r["id"], "record": r["name"]})
    return TR.merge(out)


def _summary(recs: list[dict], ships: list[dict], comps: list[dict]) -> dict:
    return {"lots": [{"id": r["id"], "name": r["name"], "item_code": r["item_code"], "lot_no": r["lot_no"],
                      "status": r["status"], "good_qty": r["good_qty"]} for r in recs],
            "shipments": ships, "complaints": comps,
            "customers": sorted({s["customer_name"] or s["customer"] or "" for s in ships} - {""}),
            "item_only": sum(1 for s in ships if s["batch_match"] != "batch")}


def from_incoming(conn, inspection_id: int) -> dict:
    ins = conn.execute("select id, name, item_code, lot_no, supplier, lot_qty, status from iqc_inspections where "
                       "id = %s", (inspection_id,)).fetchone()
    if ins is None:
        raise KeyError(inspection_id)
    recs = _records(conn, "id in (select record_id from prod_materials where inspection_id = %s)", (inspection_id,))
    used = conn.execute("select coalesce(sum(m.qty), 0) as q from prod_materials m join prod_records r on r.id = "
                        "m.record_id where m.inspection_id = %s and r.status <> 'cancelled'",
                        (inspection_id,)).fetchone()["q"]
    ships = shipped(conn, recs)
    comps = [c | {"lot": r["name"]} for r in recs for c in complaints_about(conn, r["item_code"], r["lot_no"])]
    return {"start": {"kind": "incoming", **_iso(ins), "used_qty": float(used)}, **_summary(recs, ships, comps)}


def from_record(conn, rid: int) -> dict:
    rec = conn.execute("select * from prod_records where id = %s", (rid,)).fetchone()
    if rec is None:
        raise KeyError(rid)
    mats = [_iso(r) for r in conn.execute(
        "select m.inspection_id, m.item_code, m.lot_no, m.supplier, m.qty, i.name as inspection, i.ncr_id, "
        "n.name as ncr from prod_materials m join iqc_inspections i on i.id = m.inspection_id left join ncr_records n "
        "on n.id = i.ncr_id where m.record_id = %s order by m.id", (rid,))]
    gauges = [_iso(r) for r in conn.execute(
        "select distinct gauge_id, gauge_code, gauge_due from prod_steps where record_id = %s and gauge_id is not "
        "null order by gauge_code", (rid,))]
    ncrs = [_iso(r) for r in conn.execute(
        "select s.seq, n.id, n.name, n.status from prod_steps s join ncr_records n on n.id = s.ncr_id where "
        "s.record_id = %s order by s.seq", (rid,))]
    siblings = _records(conn, "id <> %s and id in (select record_id from prod_materials where inspection_id in "
                              "(select inspection_id from prod_materials where record_id = %s))", (rid, rid))
    ships = shipped(conn, [rec])
    comps = complaints_about(conn, rec["item_code"], rec["lot_no"])
    recalls = [_iso(r) for r in conn.execute(
        "select id, name, status from recalls where scope @> %s::jsonb and status <> 'cancelled' order by id",
        (f"[{rid}]",))]
    return {"start": {"kind": "record", **_iso(rec)}, **_summary([rec], ships, comps),
            "materials": mats, "suppliers": sorted({m["supplier"] for m in mats if m["supplier"]}),
            "gauges": gauges, "ncrs": ncrs, "recalls": recalls,
            "siblings": [{"id": r["id"], "name": r["name"], "item_code": r["item_code"], "lot_no": r["lot_no"],
                          "status": r["status"]} for r in siblings]}


def from_complaint(conn, cid: int) -> dict:
    c = conn.execute("select id, name, item_code, lot_no, customer, status from complaints where id = %s",
                     (cid,)).fetchone()
    if c is None:
        raise KeyError(cid)
    start = {"kind": "complaint", **_iso(c)}
    if not c["item_code"] or not c["lot_no"].strip():
        return {"start": start, "note": say("the complaint does not name both the item and the lot: nothing to match"),
                **_summary([], [], [])}
    recs = _records(conn, "item_code = %s and lower(btrim(lot_no)) = %s", (c["item_code"], TR.lot_key(c["lot_no"])))
    if not recs:
        return {"start": start,
                "note": say("no production record of {item_code} lot {lot_no}", item_code=c["item_code"],
                            lot_no=c["lot_no"]),
                **_summary([], [], [])}
    back = from_record(conn, recs[0]["id"])
    return {**back, "start": start}
