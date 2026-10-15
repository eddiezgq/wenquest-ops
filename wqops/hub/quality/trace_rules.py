"""Traceability and recall rules, step 17i (ADR-0017; dee-qms PLAN-TRACE, PLAN-SHIP, PLAN-RECALL). Pure functions:
no database, no AI, no network.

Lots match by item and lot number, ignoring case and spaces at the ends. Who received a lot is read from ERPNext
delivery notes (submitted, not returns): a line of the item with the same batch number is a match; a line of the
item with no batch number may hold the lot too, so it is listed as "item only" (a recall reaches it rather than
miss it).
"""

from __future__ import annotations

from decimal import Decimal

CLASSES = ("class I", "class II", "class III", "not yet classified")


def lot_key(v) -> str:
    return str(v or "").strip().lower()


def same_lot(a, b) -> bool:
    return bool(lot_key(a)) and lot_key(a) == lot_key(b)


def deliveries(notes: list[dict], item_code: str, lot_no: str, since: str | None = None) -> list[dict]:
    """``notes``: ERPNext delivery notes as objects ({key, props, customer}). The lines that may carry the lot; a
    line with no batch number counts only from ``since`` (the day the lot was started) on."""
    out = []
    for n in notes:
        p = n["props"]
        if int(p.get("docstatus") or 0) != 1 or p.get("is_return"):
            continue
        for i, ln in enumerate(p.get("lines") or []):
            if ln.get("item_code") != item_code or not ln.get("qty"):
                continue
            batch = ln.get("batch_no")
            if batch and not same_lot(batch, lot_no):
                continue
            if not batch and since and (p.get("posting_date") or "") < since:
                continue
            match = "batch" if batch else "bundle" if ln.get("serial_and_batch_bundle") else "item only"
            out.append({"delivery_note": n["key"], "posting_date": p.get("posting_date"),
                        "customer": n.get("customer"), "customer_name": p.get("customer_name") or "",
                        "item_code": item_code, "lot_no": lot_no, "qty": ln["qty"], "line": i,
                        "batch_match": match})
    return sorted(out, key=lambda x: (x["posting_date"] or "", x["delivery_note"]))


def merge(rows: list[dict]) -> list[dict]:
    """A delivery line with no batch number counts once, whichever lots it may hold (their numbers joined)."""
    out: list[dict] = []
    seen: dict[tuple, dict] = {}
    for r in rows:
        if r["batch_match"] == "batch":
            out.append(r)
            continue
        k = (r["delivery_note"], r["line"])
        if k in seen:
            seen[k]["lot_no"] += ", " + r["lot_no"]
            seen[k]["records"].append(r.get("record"))
        else:
            seen[k] = {**r, "records": [r.get("record")]}
            out.append(seen[k])
    return sorted(out, key=lambda x: (x["posting_date"] or "", x["delivery_note"], x["line"]))


def _share(n: Decimal | int, d: Decimal | int) -> float | None:
    return round(float(n) / float(d), 4) if d else None


def effectiveness(rows: list[dict]) -> dict:
    """Shares of consignees notified and confirmed, and of the quantity shipped that came back or was corrected."""
    shipped = sum(Decimal(str(r["qty"])) for r in rows)
    back = sum(Decimal(str(r.get("returned_qty") or 0)) + Decimal(str(r.get("corrected_qty") or 0)) for r in rows)
    return {"consignees": len(rows),
            "notified": _share(sum(1 for r in rows if r.get("notified_on")), len(rows)),
            "confirmed": _share(sum(1 for r in rows if r.get("confirmed_on")), len(rows)),
            "recovered": _share(back, shipped), "shipped_qty": float(shipped), "recovered_qty": float(back)}


def to_open(r: dict, shipped: int) -> list[str]:
    out = []
    if not (r.get("reason") or "").strip():
        out.append("the reason")
    if not r.get("scope"):
        out.append("at least one lot")
    if r.get("classification") not in CLASSES:
        out.append("the classification")
    if not shipped and not (r.get("strategy") or "").strip():
        out.append("nothing was delivered: say in the strategy what happens to the stock")
    return out


def to_close(r: dict, rows: list[dict]) -> list[str]:
    out = []
    late = [x["delivery_note"] for x in rows if not x.get("notified_on")]
    if late:
        out.append("every consignee notified (" + ", ".join(sorted(set(late))[:10]) + ")")
    if not (r.get("effectiveness") or "").strip():
        out.append("the effectiveness conclusion")
    if any(not x.get("confirmed_on") for x in rows) and not (r.get("unconfirmed_note") or "").strip():
        out.append("a note on the consignees who did not confirm")
    if not (r.get("regulatory_decision") or "").strip():
        out.append("the regulatory decision")
    return out


def csv_cell(v) -> str:
    """A cell for a spreadsheet: text that starts like a formula is quoted."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
