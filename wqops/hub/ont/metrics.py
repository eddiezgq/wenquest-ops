"""Ops hub metrics (ADR-0007 item 3). Computed from the objects; each says how it is counted and what is unknown.

A metric with no data is ``None`` (shown as "unknown"), never 0. Each result lists the objects behind it so a
person can check the number by hand.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict


def days(n: int) -> str:
    """'1 day', '3 days' (titles and causes people read)."""
    return f"{n} day" if n == 1 else f"{n} days"


OPEN_SO = ("To Deliver and Bill", "To Deliver")  # ERPNext statuses with goods still to ship
DOI_DAYS = 90

DEFINITIONS = {
    "on_time_delivery": "Sales orders fully delivered in the period whose last delivery note is dated on or before "
                        "the order's delivery date, out of all sales orders fully delivered in the period.",
    "shortages": "Stock items whose quantity on hand (all warehouses except quarantine) is less than what open "
                 "sales orders still have to ship.",
    "inventory_value": "Sum of the stock ledger's value changes, cancelled entries left out, by warehouse.",
    "days_of_inventory": f"Inventory value divided by the average daily value shipped on delivery notes over the "
                         f"last {DOI_DAYS} days.",
    "supplier_on_time": "Purchase receipt lines in the period received on or before the required-by date of their "
                        "purchase order line, out of all receipt lines in the period that name their order line.",
    "open_nonconformances": "Nonconformance reports not yet closed or cancelled, plus submitted quality inspections in "
                            "the period with the result Rejected that have no nonconformance report yet.",
}


def _objs(conn, type_: str) -> list[dict]:
    return conn.execute("select key, title, props from ont_objects where type = %s and not deleted order by key",
                        (type_,)).fetchall()


def _d(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _pct(n: int, total: int) -> float | None:
    return round(100.0 * n / total, 1) if total else None


def window(as_of: dt.date, days: int) -> tuple[dt.date, dt.date]:
    return as_of - dt.timedelta(days=days - 1), as_of


def _submitted(p: dict) -> bool:
    return p.get("docstatus") == 1


def on_time_delivery(conn, as_of: dt.date, days: int) -> dict:
    start, end = window(as_of, days)
    last_dn: dict[str, dt.date] = {}
    for r in conn.execute("select l.dst_key as so, o.props from ont_links l join ont_objects o on o.type = l.src_type "
                          "and o.key = l.src_key where l.src_type = 'DeliveryNote' and l.type = 'sales_orders' "
                          "and not o.deleted").fetchall():
        p = r["props"]
        d = _d(p.get("posting_date"))
        if _submitted(p) and not p.get("is_return") and d:
            last_dn[r["so"]] = max(d, last_dn.get(r["so"], d))
    rows, unknown = [], []
    for o in _objs(conn, "SalesOrder"):
        p = o["props"]
        if not _submitted(p) or (p.get("per_delivered") or 0) < 100:
            continue
        done, due = last_dn.get(o["key"]), _d(p.get("delivery_date"))
        if done is None or due is None:
            unknown.append({"key": o["key"], "missing": "delivery note date" if done is None else "delivery date"})
            continue
        if start <= done <= end:
            rows.append({"key": o["key"], "title": o["title"], "due": str(due), "delivered": str(done),
                         "on_time": done <= due, "days_late": max(0, (done - due).days)})
    on_time = sum(r["on_time"] for r in rows)
    return {"value": _pct(on_time, len(rows)), "unit": "%", "on_time": on_time, "total": len(rows),
            "late": [r for r in rows if not r["on_time"]], "orders": rows, "unknown": unknown,
            "period": [str(start), str(end)]}


def _quarantine(conn) -> set[str]:
    return {o["key"] for o in _objs(conn, "Warehouse") if o["props"].get("kind") == "quarantine"}


def on_hand(conn) -> dict[str, float]:
    q = _quarantine(conn)
    out: dict[str, float] = defaultdict(float)
    for o in _objs(conn, "StockLevel"):
        if o["props"]["warehouse"] not in q:
            out[o["props"]["item"]] += o["props"].get("actual_qty") or 0.0
    return out


def open_demand(conn) -> dict[str, list[dict]]:
    """item -> open sales order lines still to ship"""
    out: dict[str, list[dict]] = defaultdict(list)
    for o in _objs(conn, "SalesOrder"):
        p = o["props"]
        if not _submitted(p) or p.get("status") not in OPEN_SO:
            continue
        for ln in p.get("lines", []):
            left = (ln.get("qty") or 0) - (ln.get("delivered_qty") or 0)
            if ln.get("item_code") and left > 0:
                out[ln["item_code"]].append({"order": o["key"], "qty": left,
                                             "due": ln.get("delivery_date") or p.get("delivery_date")})
    return out


def shortages(conn) -> dict:
    have, need = on_hand(conn), open_demand(conn)
    items = {o["key"]: o for o in _objs(conn, "Item")}
    rows = []
    for code, lines in sorted(need.items()):
        if code in items and items[code]["props"].get("is_stock_item") is False:
            continue
        demand = sum(x["qty"] for x in lines)
        if demand > have.get(code, 0.0):
            rows.append({"item": code, "title": items[code]["title"] if code in items else code,
                         "on_hand": have.get(code, 0.0), "demand": demand, "short": demand - have.get(code, 0.0),
                         "orders": sorted({x["order"] for x in lines})})
    return {"value": len(rows), "unit": "items", "items": rows}


def inventory_value(conn) -> dict:
    by_wh: dict[str, float] = defaultdict(float)
    missing = []
    for o in _objs(conn, "StockLevel"):
        p = o["props"]
        if "stock_value" not in p:
            missing.append(o["key"])
            continue
        by_wh[p["warehouse"]] += p["stock_value"]
    value = None if missing else round(sum(by_wh.values()), 2)
    return {"value": value, "unit": "currency", "by_warehouse": {k: round(v, 2) for k, v in sorted(by_wh.items())},
            "unknown": missing}


def days_of_inventory(conn, as_of: dt.date) -> dict:
    inv = inventory_value(conn)["value"]
    start, end = window(as_of, DOI_DAYS)
    shipped = 0.0
    for o in _objs(conn, "StockMove"):
        p = o["props"]
        d = _d(p.get("posting_date"))
        if (p.get("voucher_type") == "Delivery Note" and not p.get("is_cancelled") and (p.get("actual_qty") or 0) < 0
                and d and start <= d <= end and p.get("stock_value_difference") is not None):
            shipped -= p["stock_value_difference"]
    daily = shipped / DOI_DAYS
    value = round(inv / daily, 1) if inv is not None and daily > 0 else None
    return {"value": value, "unit": "days", "inventory_value": inv, "shipped_value": round(shipped, 2),
            "period": [str(start), str(end)]}


def supplier_on_time(conn, as_of: dt.date, days: int) -> dict:
    start, end = window(as_of, days)
    po_lines = {}
    for o in _objs(conn, "PurchaseOrder"):
        for ln in o["props"].get("lines", []):
            if ln.get("name"):
                po_lines[ln["name"]] = (o["key"], _d(ln.get("schedule_date") or o["props"].get("schedule_date")))
    sup: dict[str, dict] = {}
    unknown = []
    for o in _objs(conn, "PurchaseReceipt"):
        p = o["props"]
        d = _d(p.get("posting_date"))
        if not _submitted(p) or p.get("is_return") or not d or not start <= d <= end:
            continue
        name = p.get("supplier_name") or "unknown supplier"
        for i, ln in enumerate(p.get("lines", []), start=1):
            ref = po_lines.get(ln.get("purchase_order_item") or "")
            if ref is None or ref[1] is None:
                unknown.append({"receipt": o["key"], "line": i})
                continue
            s = sup.setdefault(name, {"supplier": name, "on_time": 0, "total": 0, "late": []})
            s["total"] += 1
            if d <= ref[1]:
                s["on_time"] += 1
            else:
                s["late"].append({"receipt": o["key"], "order": ref[0], "required_by": str(ref[1]),
                                  "received": str(d), "days_late": (d - ref[1]).days})
    for s in sup.values():
        s["value"] = _pct(s["on_time"], s["total"])
    on_time, total = sum(s["on_time"] for s in sup.values()), sum(s["total"] for s in sup.values())
    return {"value": _pct(on_time, total), "unit": "%", "on_time": on_time, "total": total,
            "suppliers": sorted(sup.values(), key=lambda s: (s["value"], s["supplier"])), "unknown": unknown,
            "period": [str(start), str(end)]}


def open_nonconformances(conn, as_of: dt.date, days: int) -> dict:
    """Open NCRs (any age) plus inspections rejected in the period that have no NCR yet (ADR-0009 item 7)."""
    start, end = window(as_of, days)
    with_ncr = {}
    rows = []
    for o in _objs(conn, "Nonconformance"):
        p = o["props"]
        insp = conn.execute("select dst_key from ont_links where src_type = 'Nonconformance' and src_key = %s and "
                            "type = 'inspection'", (o["key"],)).fetchone()
        if insp:
            with_ncr[insp["dst_key"]] = o["key"]
        if p.get("status") not in ("closed", "cancelled"):
            rows.append({"key": o["key"], "type": "Nonconformance", "title": o["title"], "status": p.get("status"),
                         "date": p.get("opened"), "inspection": insp["dst_key"] if insp else None})
    inspections = []
    for o in _objs(conn, "QualityInspection"):
        p = o["props"]
        d = _d(p.get("report_date"))
        if _submitted(p) and p.get("status") == "Rejected" and d and start <= d <= end and o["key"] not in with_ncr:
            inspections.append({"key": o["key"], "title": o["title"], "item": p.get("item_code"), "date": str(d),
                                "reference": p.get("reference_name")})
    return {"value": len(rows) + len(inspections), "unit": "open", "ncrs": rows, "inspections": inspections,
            "period": [str(start), str(end)]}


# metric -> permission needed to see it (ADR-0005)
VIEW = {"on_time_delivery": "sales:view", "shortages": "inventory:view", "inventory_value": "inventory:view",
        "days_of_inventory": "inventory:view", "supplier_on_time": "purchasing:view",
        "open_nonconformances": "quality:view"}
LABELS = {"on_time_delivery": "On-time delivery", "shortages": "Items short", "inventory_value": "Inventory value",
          "days_of_inventory": "Days of inventory", "supplier_on_time": "Supplier on-time",
          "open_nonconformances": "Open nonconformances"}


def compute(conn, name: str, as_of: dt.date, days: int) -> dict:
    fn = {"on_time_delivery": lambda: on_time_delivery(conn, as_of, days), "shortages": lambda: shortages(conn),
          "inventory_value": lambda: inventory_value(conn), "days_of_inventory": lambda: days_of_inventory(conn, as_of),
          "supplier_on_time": lambda: supplier_on_time(conn, as_of, days),
          "open_nonconformances": lambda: open_nonconformances(conn, as_of, days)}[name]
    return {"name": name, "label": LABELS[name], "definition": DEFINITIONS[name], **fn()}


def weekly(conn, name: str, as_of: dt.date, weeks: int = 8) -> list[dict]:
    """The metric for each of the last ``weeks`` 7-day periods, oldest first."""
    out = []
    for w in range(weeks - 1, -1, -1):
        end = as_of - dt.timedelta(days=7 * w)
        r = compute(conn, name, end, 7)
        out.append({"week_ending": str(end), "value": r["value"]})
    return out


TRENDS = ("on_time_delivery", "supplier_on_time", "open_nonconformances")
