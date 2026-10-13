"""Automatic nonconformance reports (ADR-0010): a submitted inspection with the result Rejected gets an NCR, one per
inspection. Only inspections dated on or after the day this started are covered, so old history is not flooded with
reports. Plain code on the ops hub objects: no AI, no network.
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.ont import metrics as M
from wqops.hub.quality import records as Q


def since(conn, today: dt.date) -> dt.date:
    r = conn.execute("select value from ont_state where name = 'auto_ncr_since'").fetchone()
    if r:
        return dt.date.fromisoformat(r["value"])
    conn.execute("insert into ont_state (name, value) values ('auto_ncr_since', %s)", (Jsonb(str(today)),))
    return today


def open_for_rejected(conn, today: dt.date) -> list[str]:
    start = since(conn, today)
    have = {r["inspection"] for r in conn.execute(
        "select inspection from ncr_records where inspection is not null and status <> 'cancelled'").fetchall()}
    made = []
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        d = M._d(p.get("report_date"))
        if not (M._submitted(p) and p.get("status") == "Rejected" and d and d >= start) or q["key"] in have:
            continue
        item, rt, rn = p.get("item_code"), p.get("reference_type"), p.get("reference_name")
        receipt = rn if rt == "Purchase Receipt" else None
        supplier = qty = None
        if receipt:
            link = conn.execute("select dst_key from ont_links where src_type = 'PurchaseReceipt' and src_key = %s "
                                "and type = 'supplier'", (receipt,)).fetchone()
            supplier = link["dst_key"] if link else None
            pr = conn.execute("select props from ont_objects where type = 'PurchaseReceipt' and key = %s",
                              (receipt,)).fetchone()
            qty = sum(ln.get("qty") or 0 for ln in (pr["props"].get("lines", []) if pr else [])
                      if ln.get("item_code") == item) or None
        facts = [f"Quality inspection {q['key']} ({p.get('inspection_type', 'inspection')}) on {d} rejected {item}."]
        if receipt:
            facts.append(f"Received on {receipt}" + (f" from {supplier}" if supplier else "")
                         + (f", quantity {qty:g}." if qty else "."))
        facts.append("Opened automatically; containment, disposition and root cause are for Quality to decide.")
        n = Q.create_ncr(conn, Q.SYSTEM, title=f"Rejected {item} ({q['key']})", description=" ".join(facts),
                         inspection=q["key"], item_code=item, receipt=receipt, supplier=supplier, quantity=qty)
        made.append(n["name"])
    return made
