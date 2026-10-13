"""Incoming inspection, supplier quality scores and SPC data (ADR-0009 items 4-6), read from the ops hub objects."""

from __future__ import annotations

import datetime as dt

from wqops.hub.ont import metrics as M
from wqops.hub.quality import spc

ACCEPT_WEIGHT, ON_TIME_WEIGHT = 0.6, 0.4
GRADES = ((95, "A"), (85, "B"), (70, "C"))


def _supplier_of_receipt(conn) -> dict[str, str]:
    return {r["src_key"]: r["dst_key"] for r in conn.execute(
        "select src_key, dst_key from ont_links where src_type = 'PurchaseReceipt' and type = 'supplier'").fetchall()}


def awaiting(conn) -> list[dict]:
    """Receipt lines of items marked 'inspect on receipt' with no quality inspection yet (draft or submitted)."""
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
        if not M._submitted(p) or p.get("is_return"):
            continue
        for ln in p.get("lines", []):
            code = ln.get("item_code")
            if code in need and (r["key"], code) not in done:
                out.append({"receipt": r["key"], "item_code": code, "qty": ln.get("qty"),
                            "supplier": sup.get(r["key"]), "received": p.get("posting_date")})
                done.add((r["key"], code))
    return sorted(out, key=lambda x: (x["received"] or "", x["receipt"]))


def grade(score: float | None) -> str | None:
    if score is None:
        return None
    return next((g for limit, g in GRADES if score >= limit), "D")


def supplier_scores(conn, as_of: dt.date, days: int = 90) -> dict:
    """Score = 60% lot acceptance + 40% on-time; unknown when either part is unknown."""
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
        x = lots.setdefault(s, {"accepted": 0, "lots": 0})
        x["lots"] += 1
        x["accepted"] += p.get("status") == "Accepted"
    on_time = {s["supplier"]: s for s in M.supplier_on_time(conn, as_of, days)["suppliers"]}
    ncrs: dict[str, int] = {}
    for r in conn.execute("select supplier, count(*) as n from ncr_records where supplier is not null and "
                          "created_at::date between %s and %s and status <> 'cancelled' group by supplier",
                          (start, end)).fetchall():
        ncrs[r["supplier"]] = r["n"]
    key_of = {n: k for k, n in names.items()}
    rows = []
    for key in sorted(set(lots) | {key_of.get(n, n) for n in on_time} | set(ncrs)):
        lot = lots.get(key)
        acc = round(100.0 * lot["accepted"] / lot["lots"], 1) if lot else None
        ot = on_time.get(names.get(key, key))
        otv = ot["value"] if ot else None
        score = round(ACCEPT_WEIGHT * acc + ON_TIME_WEIGHT * otv, 1) if acc is not None and otv is not None else None
        rows.append({"supplier": key, "name": names.get(key, key), "lot_acceptance": acc,
                     "lots": lot["lots"] if lot else 0, "accepted": lot["accepted"] if lot else 0,
                     "on_time": otv, "on_time_lines": ot["total"] if ot else 0, "ncrs": ncrs.get(key, 0),
                     "score": score, "grade": grade(score)})
    rows.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 0, r["name"]))
    return {"period": [str(start), str(end)], "weights": {"lot_acceptance": ACCEPT_WEIGHT, "on_time": ON_TIME_WEIGHT},
            "grades": {g: limit for limit, g in GRADES}, "suppliers": rows}


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
