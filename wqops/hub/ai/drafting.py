"""Drafts the assistant prepares (ADR-0008 item 3): replenishment purchase order, customer delay message,
nonconformance report. Every value comes from the objects; what is missing stops the draft and says what is missing.
The drafts are pending until a person with the right permission confirms them.
"""

from __future__ import annotations

import datetime as dt
import math

from wqops import i18n as I18N
from wqops.hub import drafts as D
from wqops.hub.ai import tools as T
from wqops.hub.ont import chain as CH
from wqops.hub.ont import metrics as M
from wqops.i18n import say


def _obj(ctx: T.Ctx, type_: str, key: str) -> dict:
    ctx.need_type(type_)
    r = ctx.conn.execute("select key, title, props from ont_objects where type = %s and key = %s and not deleted",
                         (type_, key)).fetchone()
    if r is None:
        raise T.ToolError(say("no {type} {key}", type=type_, key=key))
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
    return {"draft_id": d["id"], "status": say("pending - a person must confirm it"), "kind": doctype,
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
        raise T.ToolError(say("{item_code} is not short for open orders; no replenishment needed", item_code=item_code))
    last = None
    for o in M._objs(ctx.conn, "PurchaseOrder"):
        p = o["props"]
        line = next((ln for ln in p.get("lines", []) if ln.get("item_code") == item_code), None)
        if M._submitted(p) and line and (last is None or (p.get("transaction_date") or "", o["key"]) >
                                         (last[0]["props"].get("transaction_date") or "", last[0]["key"])):
            last = (o, line)
    if last is None:
        raise T.ToolError(say("no earlier purchase order for {item_code}, so the supplier is unknown; please draft "
                              "this one by hand in ERPNext",
                              item_code=item_code))
    po, line = last
    supplier = _link(ctx, "PurchaseOrder", po["key"], "supplier")
    if not supplier:
        raise T.ToolError(say("{key} has no supplier; please draft this one by hand", key=po['key']))
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
    with I18N.use(I18N.company_language()):          # the draft is the company's record: in its language
        vals = {"title": item["title"], "short": format(short["short"], "g"), "orders": ", ".join(short["orders"]),
                "qty": qty, "supplier": po["props"].get("supplier_name", supplier), "po": po["key"],
                "need_by": need_by}
        summary = (say("Replenish {title}: short {short} for {orders}; {qty} from {supplier} as on {po} at {rate}, "
                       "needed by {need_by}.", rate=format(line["rate"], "g"), **vals)
                   if line.get("rate") is not None else
                   say("Replenish {title}: short {short} for {orders}; {qty} from {supplier} as on {po}, needed by "
                       "{need_by}.", **vals))
    return _propose(ctx, "Purchase Order", payload, summary)


def delay_message(ctx: T.Ctx, sales_order: str) -> dict:
    """An email to the customer about a late or at-risk order. Supplier names are internal and left out."""
    so = _obj(ctx, "SalesOrder", sales_order)
    p = so["props"]
    if not M._submitted(p) or p.get("status") not in M.OPEN_SO:
        raise T.ToolError(say("{sales_order} is not an open order ({p}); no delay message needed",
                              sales_order=sales_order, p=p.get('status', 'no status')))
    customer = _link(ctx, "SalesOrder", sales_order, "customer")
    if not customer:
        raise T.ToolError(say("{sales_order} has no customer", sales_order=sales_order))
    due = p.get("delivery_date")
    waiting = []
    for s in CH.explain(ctx.conn, "SalesOrder", sales_order, ctx.today)["causes"]:
        if s["relation"] == "waits for" and s["to"]:
            line = next((ln for ln in p.get("lines", []) if ln.get("item_code") == s["to"][1]), {})
            left = (line.get("qty") or 0) - (line.get("delivered_qty") or 0)
            waiting.append((s["to"][1], format(left, "g")))
    if not waiting and not (due and dt.date.fromisoformat(due) < ctx.today):
        raise T.ToolError(say("{sales_order} is neither late nor waiting for stock; no delay message needed",
                              sales_order=sales_order))
    name = p.get("customer_name") or customer
    late = due and dt.date.fromisoformat(due) < ctx.today
    with I18N.use(I18N.company_language()):          # the message goes out in the company's language
        company = (ctx.manifest or {}).get("company", {}).get("name") or say("our company")
        sep = "、" if I18N.current() == "zh" else ", "
        items = sep.join(say("{code} ({left} to ship)", code=c, left=n) for c, n in waiting)
        if waiting:
            first = (say("Your order {order} was due on {due}. We are sorry: some items are not yet in stock: {items}.",
                         order=sales_order, due=due, items=items) if late else
                     say("Your order {order} is due on {due}. We are sorry: some items are not yet in stock: {items}.",
                         order=sales_order, due=due, items=items))
        else:
            first = (say("Your order {order} was due on {due}. We are sorry: it is taking longer than planned to "
                         "prepare.", order=sales_order, due=due) if late else
                     say("Your order {order} is due on {due}. We are sorry: it is taking longer than planned to "
                         "prepare.", order=sales_order, due=due))
        body = (say("Dear {name},", name=name) + "\n\n" + first + "\n\n"
                + say("We will confirm a new delivery date as soon as we have it, and we will ship as soon as the "
                      "goods arrive. If a partial shipment would help you, please let us know.") + "\n\n"
                + say("Best regards,") + "\n" + company)
        payload = {"customer": customer, "sales_order": sales_order,
                   "subject": say("Update on your order {order}", order=sales_order), "body": body}
        summary = say("Delay message to {name} about {order}.", name=name, order=sales_order)
    return _propose(ctx, "Customer Message", payload, summary)


def nonconformance(ctx: T.Ctx, inspection: str) -> dict:
    """A nonconformance report from a rejected quality inspection."""
    qi = _obj(ctx, "QualityInspection", inspection)
    p = qi["props"]
    if p.get("status") != "Rejected":
        raise T.ToolError(say("{inspection} was not rejected ({p}); no NCR needed",
                              inspection=inspection, p=p.get('status', 'no result')))
    existing = ctx.conn.execute("select name from ncr_records where inspection = %s and status <> 'cancelled'",
                                (inspection,)).fetchone()
    if existing:
        raise T.ToolError(say("{inspection} already has {name} (opened automatically or by a person)",
                              inspection=inspection, name=existing['name']))
    item = p.get("item_code")
    receipt = p.get("reference_name") if p.get("reference_type") == "Purchase Receipt" else None
    supplier = _link(ctx, "PurchaseReceipt", receipt, "supplier") if receipt else None
    qty = None
    if receipt:
        pr = ctx.conn.execute("select props from ont_objects where type = 'PurchaseReceipt' and key = %s",
                              (receipt,)).fetchone()
        qty = sum(ln.get("qty") or 0 for ln in (pr["props"].get("lines", []) if pr else [])
                  if ln.get("item_code") == item) or None
    with I18N.use(I18N.company_language()):          # the report is the company's record: in its language
        facts = [say("Quality inspection {inspection} ({type}) on {date} rejected {item}.", inspection=inspection,
                     type=I18N.label(p["inspection_type"]) if "inspection_type" in p else say("inspection"),
                     date=p["report_date"] if "report_date" in p else say("an unknown date"), item=item)]
        if receipt:
            q = format(qty, "g") if qty else ""
            facts.append(
                (say("Received on purchase receipt {receipt} from {supplier}, quantity {qty}.", receipt=receipt,
                     supplier=supplier, qty=q) if qty else
                 say("Received on purchase receipt {receipt} from {supplier}.", receipt=receipt, supplier=supplier))
                if supplier else
                (say("Received on purchase receipt {receipt}, quantity {qty}.", receipt=receipt, qty=q) if qty else
                 say("Received on purchase receipt {receipt}.", receipt=receipt)))
        facts.append(say("Disposition, containment and root cause: to be decided by Quality."))
        payload = {"inspection": inspection, "item_code": item,
                   "title": say("Rejected {item} ({inspection})", item=item, inspection=inspection),
                   "description": ("" if I18N.current() == "zh" else " ").join(facts)}
        summary = say("NCR for {item} rejected on {inspection}.", item=item, inspection=inspection)
    for k, v in (("receipt", receipt), ("supplier", supplier), ("quantity", qty)):
        if v is not None:
            payload[k] = v
    return _propose(ctx, "Nonconformance Report", payload, summary)


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
