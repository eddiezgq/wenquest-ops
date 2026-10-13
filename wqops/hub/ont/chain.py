"""Root cause and impact (ADR-0007 item 6): from an anomaly or any object, walk the objects upstream to find causes
and downstream to find what is affected. Every step says why, with the numbers it is based on.

Chains in Phase 1:
    late or at-risk sales order -> items short -> open purchase orders for them (or none) -> supplier on-time rate
    rejected inspection -> purchase receipt -> supplier, item -> open sales orders needing the item -> customers
    item short / late purchase order -> open sales orders waiting for the items -> customers
At most 6 steps deep and 200 objects. Walking logic adapted from freecad-ai-parts factory/digital/hub/ont/chain.py.
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import metrics as M

MAX_DEPTH = 6
MAX_NODES = 200


class Walk:
    def __init__(self, conn, today: dt.date):
        self.conn, self.today = conn, today
        self.steps: list[dict] = []
        self.nodes: dict[tuple[str, str], str] = {}
        self._short = None
        self._sup = None

    def title(self, t: str, k: str) -> str:
        if (t, k) not in self.nodes:
            r = self.conn.execute("select title from ont_objects where type = %s and key = %s", (t, k)).fetchone()
            self.nodes[(t, k)] = r["title"] if r else k
        return self.nodes[(t, k)]

    def step(self, frm, to, relation: str, why: str, depth: int, **evidence) -> bool:
        if len(self.nodes) >= MAX_NODES or depth > MAX_DEPTH:
            return False
        self.title(*frm)
        if to:
            self.title(*to)
        self.steps.append(
            {
                "from": list(frm),
                "to": list(to) if to else None,
                "relation": relation,
                "why": why,
                "depth": depth,
                "evidence": evidence,
            }
        )
        return True

    @property
    def short(self) -> dict:
        if self._short is None:
            self._short = {x["item"]: x for x in M.shortages(self.conn)["items"]}
        return self._short

    @property
    def suppliers(self) -> dict:
        if self._sup is None:
            r = M.supplier_on_time(self.conn, self.today, 90)
            self._sup = {s["supplier"]: s for s in r["suppliers"]}
        return self._sup

    # ---- upstream (causes)
    def order_causes(self, key: str, depth: int) -> None:
        o = self.conn.execute("select props from ont_objects where type = 'SalesOrder' and key = %s", (key,)).fetchone()
        if not o:
            return
        due = M._d(o["props"].get("delivery_date"))
        for ln in o["props"].get("lines", []):
            code = ln.get("item_code")
            left = (ln.get("qty") or 0) - (ln.get("delivered_qty") or 0)
            if code in self.short and left > 0:
                s = self.short[code]
                if self.step(
                    ("SalesOrder", key),
                    ("Item", code),
                    "waits for",
                    f"{code} is short by {s['short']:g}: {s['on_hand']:g} on hand, open orders need {s['demand']:g}.",
                    depth,
                    on_hand=s["on_hand"],
                    demand=s["demand"],
                    short=s["short"],
                ):
                    self.item_causes(code, depth + 1, need_by=due)

    def item_causes(self, code: str, depth: int, need_by: dt.date | None = None) -> None:
        open_pos = []
        for o in M._objs(self.conn, "PurchaseOrder"):
            p = o["props"]
            if not M._submitted(p) or p.get("status") in AN.CLOSED_PO:
                continue
            for ln in p.get("lines", []):
                left = (ln.get("qty") or 0) - (ln.get("received_qty") or 0)
                if ln.get("item_code") == code and left > 0:
                    open_pos.append((o, ln, left, M._d(ln.get("schedule_date") or p.get("schedule_date"))))
        if not open_pos:
            self.step(("Item", code), None, "no supply", f"No open purchase order brings more {code}.", depth)
            return
        for o, _ln, left, due in open_pos:
            notes = []
            if due and due < self.today:
                notes.append(f"{(self.today - due).days} days past its required-by date {due}")
            elif due and need_by and due > need_by:
                notes.append(f"arrives {due}, after the order needs it ({need_by})")
            elif due:
                notes.append(f"required by {due}")
            if self.step(
                ("Item", code),
                ("PurchaseOrder", o["key"]),
                "expected from",
                f"{o['key']}: {left:g} still to receive, {'; '.join(notes)}.",
                depth,
                still_to_receive=left,
                required_by=str(due) if due else None,
            ):
                self.po_causes(o, depth + 1)

    def po_causes(self, o: dict, depth: int) -> None:
        sup = o["props"].get("supplier_name")
        link = self.conn.execute(
            "select dst_key from ont_links where src_type = 'PurchaseOrder' and src_key = %s and type = 'supplier'",
            (o["key"],),
        ).fetchone()
        if not link:
            return
        s = self.suppliers.get(sup)
        why = (
            f"{sup} delivered {s['on_time']} of {s['total']} receipt lines on time in 90 days ({s['value']:g}%)."
            if s
            else f"{sup}: no receipts in the last 90 days to rate on-time delivery (unknown)."
        )
        self.step(
            ("PurchaseOrder", o["key"]),
            ("Supplier", link["dst_key"]),
            "ordered from",
            why,
            depth,
            on_time_pct=s["value"] if s else None,
            lines=s["total"] if s else 0,
        )

    def inspection_causes(self, key: str, depth: int) -> None:
        qi = self.conn.execute(
            "select props from ont_objects where type = 'QualityInspection' and key = %s", (key,)
        ).fetchone()
        if not qi:
            return
        p = qi["props"]
        if p.get("reference_type") == "Purchase Receipt" and p.get("reference_name"):
            pr = p["reference_name"]
            if self.step(
                ("QualityInspection", key),
                ("PurchaseReceipt", pr),
                "inspected",
                f"{p.get('item_code')} from receipt {pr} was {p.get('status', 'inspected').lower()}.",
                depth,
            ):
                sup = self.conn.execute(
                    "select dst_key from ont_links where src_type = 'PurchaseReceipt' and "
                    "src_key = %s and type = 'supplier'",
                    (pr,),
                ).fetchone()
                if sup:
                    self.step(
                        ("PurchaseReceipt", pr),
                        ("Supplier", sup["dst_key"]),
                        "received from",
                        f"Supplied by {self.title('Supplier', sup['dst_key'])}.",
                        depth + 1,
                    )

    # ---- downstream (impact)
    def item_impact(self, code: str, depth: int) -> None:
        for d in M.open_demand(self.conn).get(code, []):
            if self.step(
                ("Item", code),
                ("SalesOrder", d["order"]),
                "needed by",
                f"{d['order']} still needs {d['qty']:g} of {code}, due {d['due']}.",
                depth,
                qty=d["qty"],
                due=d["due"],
            ):
                cust = self.conn.execute(
                    "select dst_key from ont_links where src_type = 'SalesOrder' and src_key = %s "
                    "and type = 'customer'",
                    (d["order"],),
                ).fetchone()
                if cust:
                    self.step(
                        ("SalesOrder", d["order"]),
                        ("Customer", cust["dst_key"]),
                        "for customer",
                        f"Ordered by {self.title('Customer', cust['dst_key'])}.",
                        depth + 1,
                    )


def explain(conn, type_: str, key: str, today: dt.date) -> dict:  # noqa: PLR0912 - one branch per chain
    """Causes and impact of one object (an anomaly's subject, or anything a person opens)."""
    w = Walk(conn, today)
    causes, impact = [], []
    w.title(type_, key)
    if type_ == "SalesOrder":
        w.order_causes(key, 1)
        causes, w.steps = w.steps, []
        o = conn.execute(
            "select dst_key from ont_links where src_type = 'SalesOrder' and src_key = %s and type = 'customer'", (key,)
        ).fetchone()
        if o:
            w.step(
                ("SalesOrder", key),
                ("Customer", o["dst_key"]),
                "for customer",
                f"Ordered by {w.title('Customer', o['dst_key'])}.",
                1,
            )
    elif type_ == "Item":
        w.item_causes(key, 1)
        causes, w.steps = w.steps, []
        w.item_impact(key, 1)
    elif type_ == "PurchaseOrder":
        o = conn.execute(
            "select key, props from ont_objects where type = 'PurchaseOrder' and key = %s", (key,)
        ).fetchone()
        if o:
            w.po_causes(o, 1)
            causes, w.steps = w.steps, []
            for ln in AN.late_po_lines(o, today) or o["props"].get("lines", []):
                code = ln.get("item") or ln.get("item_code")
                if (
                    code
                    and code in w.short
                    and w.step(
                        ("PurchaseOrder", key),
                        ("Item", code),
                        "brings",
                        f"{code} is short by {w.short[code]['short']:g}.",
                        1,
                    )
                ):
                    w.item_impact(code, 2)
    elif type_ == "QualityInspection":
        w.inspection_causes(key, 1)
        causes, w.steps = w.steps, []
        qi = conn.execute(
            "select props from ont_objects where type = 'QualityInspection' and key = %s", (key,)
        ).fetchone()
        code = qi["props"].get("item_code") if qi else None
        for n in conn.execute(
            "select o.key, o.props from ont_links l join ont_objects o on o.type = l.src_type and "
            "o.key = l.src_key where l.src_type = 'Nonconformance' and l.type = 'inspection' and "
            "l.dst_key = %s and not o.deleted",
            (key,),
        ).fetchall():
            if w.step(
                ("QualityInspection", key),
                ("Nonconformance", n["key"]),
                "reported in",
                f"{n['key']} is {n['props'].get('status')}"
                + (
                    f", disposition {n['props']['disposition'].replace('_', ' ')}."
                    if n["props"].get("disposition")
                    else "."
                ),
                1,
            ):
                for cp in conn.execute(
                    "select o.key, o.props from ont_links l join ont_objects o on o.type = l.src_type "
                    "and o.key = l.src_key where l.src_type = 'Capa' and l.type = 'ncr' and "
                    "l.dst_key = %s and not o.deleted",
                    (n["key"],),
                ).fetchall():
                    w.step(
                        ("Nonconformance", n["key"]),
                        ("Capa", cp["key"]),
                        "corrected by",
                        f"{cp['key']} ({cp['props'].get('kind')}) is "
                        f"{cp['props'].get('status', '').replace('_', ' ')}.",
                        2,
                    )
        if code and w.step(("QualityInspection", key), ("Item", code), "affects", f"Rejected lot of {code}.", 1):
            w.item_impact(code, 2)
    elif type_ == "Supplier":
        for o in M._objs(conn, "PurchaseOrder"):
            link = conn.execute(
                "select 1 from ont_links where src_type = 'PurchaseOrder' and src_key = %s and "
                "type = 'supplier' and dst_key = %s",
                (o["key"], key),
            ).fetchone()
            late = AN.late_po_lines(o, today) if link else []
            if late and w.step(
                ("Supplier", key),
                ("PurchaseOrder", o["key"]),
                "late order",
                f"{o['key']} is {max(x['days_late'] for x in late)} days late.",
                1,
            ):
                for x in late:
                    if x["item"] in w.short and w.step(
                        ("PurchaseOrder", o["key"]),
                        ("Item", x["item"]),
                        "brings",
                        f"{x['item']} is short by {w.short[x['item']]['short']:g}.",
                        2,
                    ):
                        w.item_impact(x["item"], 3)
    impact = w.steps
    return {
        "root": [type_, key],
        "causes": causes,
        "impact": impact,
        "nodes": [{"type": t, "key": k, "title": v} for (t, k), v in w.nodes.items()],
        "truncated": len(w.nodes) >= MAX_NODES,
    }
