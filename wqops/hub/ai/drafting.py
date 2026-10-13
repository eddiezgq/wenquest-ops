"""Drafts the assistant prepares (ADR-0008 item 3): replenishment purchase order, customer delay message,
nonconformance report. Every value comes from the objects; what is missing stops the draft and says what is missing.
The drafts are pending until a person with the right permission confirms them.
"""

from __future__ import annotations

import datetime as dt
import math

from wqops.hub import drafts as D
from wqops.hub.ai import tools as T
from wqops.hub.ont import chain as CH
from wqops.hub.ont import metrics as M


def _obj(ctx: T.Ctx, type_: str, key: str) -> dict:
    ctx.need_type(type_)
    r = ctx.conn.execute("select key, title, props from ont_objects where type = %s and key = %s and not deleted",
                         (type_, key)).fetchone()
    if r is None:
        raise T.ToolError(f"no {type_} {key}")
    return r


def _link(ctx: T.Ctx, src_type: str, src_key: str, link: str) -> str | None:
    r = ctx.conn.execute("select dst_key from ont_links where src_type = %s and src_key = %s and type = %s",
                         (src_type, src_key, link)).fetchone()
    return r["dst_key"] if r else None


def _propose(ctx: T.Ctx, doctype: str, payload: dict, summary: str) -> dict:
    try:
        d = D.propose(ctx.conn, ctx.user, doctype, payload, summary=summary, source="ai",
                      ai_run=str(ctx.run_id) if ctx.run_id else None)
    except D.DraftError as exc:
        raise T.ToolError(str(exc)) from exc
    ctx.drafts.append(d["id"])
    return {"draft_id": d["id"], "status": "pending - a person must confirm it", "kind": doctype,
            "summary": summary, "payload": payload}


def _stores(ctx: T.Ctx) -> str | None:
    m = ctx.manifest or {}
    for w in m.get("warehouses", []):
        if w["kind"] == "stores":
            return f"{w['name']} - {m['company']['abbr']}"
    return None


def purchase_order(ctx: T.Ctx, item_code: str) -> dict:
    """Replenish a short item from the supplier of its most recent purchase order."""
    item = _obj(ctx, "Item", item_code)
    short = {x["item"]: x for x in M.shortages(ctx.conn)["items"]}.get(item_code)
    if short is None:
        raise T.ToolError(f"{item_code} is not short for open orders; no replenishment needed")
    last = None
    for o in M._objs(ctx.conn, "PurchaseOrder"):
        p = o["props"]
        line = next((ln for ln in p.get("lines", []) if ln.get("item_code") == item_code), None)
        if M._submitted(p) and line and (last is None or (p.get("transaction_date") or "", o["key"]) >
                                         (last[0]["props"].get("transaction_date") or "", last[0]["key"])):
            last = (o, line)
    if last is None:
        raise T.ToolError(f"no earlier purchase order for {item_code}, so the supplier is unknown; "
                          "please draft this one by hand in ERPNext")
    po, line = last
    supplier = _link(ctx, "PurchaseOrder", po["key"], "supplier")
    if not supplier:
        raise T.ToolError(f"{po['key']} has no supplier; please draft this one by hand")
    dues = sorted(d["due"] for d in M.open_demand(ctx.conn)[item_code] if d.get("due"))
    need_by = max(ctx.today, dt.date.fromisoformat(dues[0])) if dues else ctx.today + dt.timedelta(days=7)
    qty = math.ceil(short["short"])
    row = {"item_code": item_code, "qty": qty, "schedule_date": str(need_by)}
    warehouse = _stores(ctx) or line.get("warehouse")
    if warehouse:
        row["warehouse"] = warehouse
    if line.get("rate") is not None:
        row["rate"] = line["rate"]
    payload = {"supplier": supplier, "transaction_date": str(ctx.today), "schedule_date": str(need_by), "items": [row]}
    if ctx.manifest:
        payload["company"] = ctx.manifest["company"]["name"]
    summary = (f"Replenish {item['title']}: short {short['short']:g} for {', '.join(short['orders'])}; "
               f"{qty} from {po['props'].get('supplier_name', supplier)} as on {po['key']}"
               + (f" at {line['rate']:g}" if line.get("rate") is not None else "") + f", needed by {need_by}.")
    return _propose(ctx, "Purchase Order", payload, summary)


def delay_message(ctx: T.Ctx, sales_order: str) -> dict:
    """An email to the customer about a late or at-risk order. Supplier names are internal and left out."""
    so = _obj(ctx, "SalesOrder", sales_order)
    p = so["props"]
    if not M._submitted(p) or p.get("status") not in M.OPEN_SO:
        raise T.ToolError(f"{sales_order} is not an open order ({p.get('status', 'no status')}); "
                          "no delay message needed")
    customer = _link(ctx, "SalesOrder", sales_order, "customer")
    if not customer:
        raise T.ToolError(f"{sales_order} has no customer")
    due = p.get("delivery_date")
    waiting = []
    for s in CH.explain(ctx.conn, "SalesOrder", sales_order, ctx.today)["causes"]:
        if s["relation"] == "waits for" and s["to"]:
            line = next((ln for ln in p.get("lines", []) if ln.get("item_code") == s["to"][1]), {})
            left = (line.get("qty") or 0) - (line.get("delivered_qty") or 0)
            waiting.append(f"{s['to'][1]} ({left:g} to ship)")
    if not waiting and not (due and dt.date.fromisoformat(due) < ctx.today):
        raise T.ToolError(f"{sales_order} is neither late nor waiting for stock; no delay message needed")
    company = (ctx.manifest or {}).get("company", {}).get("name", "our company")
    name = p.get("customer_name") or customer
    status = f"was due on {due}" if due and dt.date.fromisoformat(due) < ctx.today else f"is due on {due}"
    reason = (f"some items are not yet in stock: {', '.join(waiting)}" if waiting
              else "it is taking longer than planned to prepare")
    body = (f"Dear {name},\n\nYour order {sales_order} {status}. We are sorry: {reason}.\n\n"
            "We will confirm a new delivery date as soon as we have it, and we will ship as soon as the goods "
            "arrive. If a partial shipment would help you, please let us know.\n\n"
            f"Best regards,\n{company}")
    payload = {"customer": customer, "sales_order": sales_order, "subject": f"Update on your order {sales_order}",
               "body": body}
    return _propose(ctx, "Customer Message", payload, f"Delay message to {name} about {sales_order}.")


def nonconformance(ctx: T.Ctx, inspection: str) -> dict:
    """A nonconformance report from a rejected quality inspection."""
    qi = _obj(ctx, "QualityInspection", inspection)
    p = qi["props"]
    if p.get("status") != "Rejected":
        raise T.ToolError(f"{inspection} was not rejected ({p.get('status', 'no result')}); no NCR needed")
    existing = ctx.conn.execute("select name from ncr_records where inspection = %s and status <> 'cancelled'",
                                (inspection,)).fetchone()
    if existing:
        raise T.ToolError(f"{inspection} already has {existing['name']} (opened automatically or by a person)")
    item = p.get("item_code")
    receipt = p.get("reference_name") if p.get("reference_type") == "Purchase Receipt" else None
    supplier = _link(ctx, "PurchaseReceipt", receipt, "supplier") if receipt else None
    qty = None
    if receipt:
        pr = ctx.conn.execute("select props from ont_objects where type = 'PurchaseReceipt' and key = %s",
                              (receipt,)).fetchone()
        qty = sum(ln.get("qty") or 0 for ln in (pr["props"].get("lines", []) if pr else [])
                  if ln.get("item_code") == item) or None
    facts = [f"Quality inspection {inspection} ({p.get('inspection_type', 'inspection')}) on "
             f"{p.get('report_date', 'an unknown date')} rejected {item}."]
    if receipt:
        facts.append(f"Received on purchase receipt {receipt}" + (f" from {supplier}" if supplier else "") +
                     (f", quantity {qty:g}." if qty else "."))
    facts.append("Disposition, containment and root cause: to be decided by Quality.")
    payload = {"inspection": inspection, "item_code": item, "title": f"Rejected {item} ({inspection})",
               "description": " ".join(facts)}
    for k, v in (("receipt", receipt), ("supplier", supplier), ("quantity", qty)):
        if v is not None:
            payload[k] = v
    return _propose(ctx, "Nonconformance Report", payload, f"NCR for {item} rejected on {inspection}.")


DRAFT_TOOLS = [
    T.Tool("draft_purchase_order", "Prepare a replenishment purchase order for a short item (supplier and price from "
           "its most recent purchase order). It stays pending until a buyer confirms it.",
           {"properties": {"item_code": {"type": "string"}}, "required": ["item_code"]}, purchase_order),
    T.Tool("draft_customer_delay_message", "Prepare an email to the customer of a late or at-risk sales order. It is "
           "not sent; a person confirms it and sends it.",
           {"properties": {"sales_order": {"type": "string"}}, "required": ["sales_order"]}, delay_message),
    T.Tool("draft_nonconformance", "Prepare a nonconformance report (NCR) from a rejected quality inspection. "
           "Quality confirms it.", {"properties": {"inspection": {"type": "string"}}, "required": ["inspection"]},
           nonconformance),
]
KINDS = {"purchase_order": purchase_order, "delay_message": delay_message, "nonconformance": nonconformance}
