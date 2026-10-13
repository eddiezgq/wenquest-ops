"""Incoming inspection, supplier quality scores and SPC data (ADR-0009 items 4-6), read from the ops hub objects."""

from __future__ import annotations

import datetime as dt

from wqops.hub.ont import metrics as M
from wqops.hub.quality import spc


def _supplier_of_receipt(conn) -> dict[str, str]:
    return {r["src_key"]: r["dst_key"] for r in conn.execute(
        "select src_key, dst_key from ont_links where src_type = 'PurchaseReceipt' and type = 'supplier'").fetchall()}


def awaiting(conn) -> list[dict]:
    """Receipt lines (draft or submitted receipts) of items marked 'inspect on receipt' that have no quality inspection
    yet (draft or submitted inspection). ERPNext asks for the inspection before such a receipt is submitted."""
    need = {o["key"] for o in M._objs(conn, "Item") if o["props"].get("inspection_required")}
    done = set()
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        if p.get("reference_type") == "Purchase Receipt" and p.get("docstatus") in (0, 1):
            done.add((p.get("reference_name"), p.get("item_code")))
    sup = _supplier_of_receipt(conn)
    out = []
    for r in M._objs(conn, "PurchaseReceipt"):
        p = r["props"]
        if p.get("docstatus") not in (0, 1) or p.get("is_return"):   # drafts too: ERPNext wants the inspection first
            continue
        for ln in p.get("lines", []):
            code = ln.get("item_code")
            if code in need and (r["key"], code) not in done:
                out.append({"receipt": r["key"], "draft": p.get("docstatus") == 0, "item_code": code,
                            "qty": ln.get("qty"),
                            "supplier": sup.get(r["key"]), "received": p.get("posting_date")})
                done.add((r["key"], code))
    return sorted(out, key=lambda x: (x["received"] or "", x["receipt"]))


def supplier_quality(conn, as_of: dt.date, days: int = 90, tz: str = "UTC") -> dict:
    """Facts per supplier over the period (ADR-0010; no score): inspected and rejected lots, lot rejection rate,
    on-time rate, NCRs, concessions (closed NCRs whose disposition needed approval) and open corrective actions."""
    start, end = M.window(as_of, days)
    sup = _supplier_of_receipt(conn)
    names = {o["key"]: o["props"].get("supplier_name") or o["key"] for o in M._objs(conn, "Supplier")}
    lots: dict[str, dict] = {}
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        d = M._d(p.get("report_date"))
        if not (M._submitted(p) and p.get("inspection_type") == "Incoming" and p.get("reference_type") ==
                "Purchase Receipt" and d and start <= d <= end):
            continue
        s = sup.get(p.get("reference_name"))
        if s is None:
            continue
        x = lots.setdefault(s, {"lots": 0, "rejected": 0})
        x["lots"] += 1
        x["rejected"] += p.get("status") == "Rejected"
    on_time = {s["supplier"]: s for s in M.supplier_on_time(conn, as_of, days)["suppliers"]}
    ncrs = {r["supplier"]: r for r in conn.execute(
        "select n.supplier, count(*) as ncrs, count(*) filter (where n.status = 'closed' and t.requires_approval) "
        "as concessions from ncr_records n left join ncr_disposition_types t on t.code = n.disposition "
        "where n.supplier is not null and n.status <> 'cancelled' and "
        "(n.created_at at time zone %s)::date between %s and %s group by n.supplier", (tz, start, end)).fetchall()}
    capas = {r["supplier"]: r["n"] for r in conn.execute(
        "select n.supplier, count(distinct c.id) as n from capas c join capa_ncrs l on l.capa_id = c.id join "
        "ncr_records n on n.id = l.ncr_id where n.supplier is not null and c.status not in ('closed', 'cancelled') "
        "group by n.supplier").fetchall()}
    key_of = {n: k for k, n in names.items()}
    rows = []
    for key in sorted(set(lots) | {key_of.get(n, n) for n in on_time} | set(ncrs) | set(capas)):
        lot = lots.get(key, {"lots": 0, "rejected": 0})
        ot = on_time.get(names.get(key, key))
        rows.append({"supplier": key, "name": names.get(key, key), "lots": lot["lots"], "rejected": lot["rejected"],
                     "rejection_rate": round(100.0 * lot["rejected"] / lot["lots"], 1) if lot["lots"] else None,
                     "on_time": ot["value"] if ot else None, "on_time_lines": ot["total"] if ot else 0,
                     "ncrs": ncrs[key]["ncrs"] if key in ncrs else 0,
                     "concessions": ncrs[key]["concessions"] if key in ncrs else 0, "open_capas": capas.get(key, 0)})
    rows.sort(key=lambda r: (-(r["rejection_rate"] or 0), -r["ncrs"], r["name"]))
    return {"period": [str(start), str(end)], "suppliers": rows}


def parameters(conn) -> list[dict]:
    """Item and parameter pairs that have numeric readings, with how many inspections."""
    count: dict[tuple[str, str], int] = {}
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        if M._submitted(p):
            for r in p.get("readings") or []:
                k = (p.get("item_code"), r["parameter"])
                count[k] = count.get(k, 0) + 1
    return [{"item_code": i, "parameter": par, "inspections": n} for (i, par), n in sorted(count.items())]


def spc_for(conn, item_code: str, parameter: str, limit: int = 100) -> dict:
    groups = []
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        if not M._submitted(p) or p.get("item_code") != item_code:
            continue
        for r in p.get("readings") or []:
            if r["parameter"] == parameter:
                groups.append({"inspection": q["key"], "date": p.get("report_date") or "", "values": r["values"],
                               "min": r.get("min"), "max": r.get("max")})
    groups.sort(key=lambda g: (g["date"], g["inspection"]))
    groups = groups[-limit:]
    out = {"item_code": item_code, "parameter": parameter, "inspections": [g["inspection"] for g in groups]}
    if not groups:
        return out | {"enough_data": False, "note": "No numeric readings for this item and parameter.",
                      "subgroups": 0}
    return out | spc.chart(groups)
