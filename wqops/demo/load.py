"""Write the fictional demo business into ERPNext and the hub (ADR-0012).

    python -m wqops.demo.load [--today YYYY-MM-DD]

Runs only for a company manifest marked ``demo: true``, once (it stops if the demo customers already exist). This is an
installation tool run by IT, not an AI write-back. Documents are created and submitted in date order with their
historical posting dates; then the hub syncs, and a quality record set (NCR, corrective action with an overdue step)
is added for the rejected lot. Then a folder of fictional quality documents is imported into the document library
and classified, waiting for people to review it (wqops/demo/documents.py), and last the regulated quality modules get
sample records (wqops/demo/quality.py).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Callable

from wqops import company as C
from wqops.demo import scenario as S
from wqops.erp import ErpClient
from wqops.erp_setup import fiscal_year, warehouse_name
from wqops.i18n import say as _say

UOM = "Nos"


class DemoError(RuntimeError):
    pass


def _leaf(erp: ErpClient, doctype: str) -> str:
    rows = erp.list(doctype, filters=[["is_group", "=", 0]], order_by="name asc", limit=1)
    if not rows:
        raise DemoError(_say("ERPNext has no {doctype} to use", doctype=doctype))
    return rows[0]["name"]


class Loader:
    def __init__(self, erp: ErpClient, manifest: dict, today: dt.date, say: Callable[[str], None] = print):
        if not manifest.get("demo"):
            raise DemoError(_say("demo data is only loaded into a company manifest marked demo: true"))
        self.erp, self.m, self.today, self.say = erp, manifest, today, say
        self.company = manifest["company"]["name"]
        whs = {w["kind"]: warehouse_name(manifest, w) for w in manifest["warehouses"]}
        if "stores" not in whs or "quarantine" not in whs:
            raise DemoError(_say("the demo manifest needs a stores and a quarantine warehouse"))
        self.main, self.hold = whs["stores"], whs["quarantine"]
        self.names: dict[str, dict] = {}          # local ref -> {"name": ERPNext name, "rows": [row names]}

    def submit(self, doctype: str, name: str) -> None:
        self.erp.update(doctype, name, {"docstatus": 1})

    def make(self, doc: dict, ref: str | None = None, submit: bool = True) -> dict:
        out = self.erp.insert(doc)
        if submit:
            self.submit(doc["doctype"], out["name"])
        if ref:
            self.names[ref] = {"name": out["name"], "rows": [r["name"] for r in out.get("items", [])]}
        return out

    # ---------------------------------------------------------------- master data
    def masters(self, start: dt.date) -> None:
        if self.erp.find("Customer", {"customer_name": S.CUSTOMERS[0]}):
            raise DemoError(_say("demo data is already loaded (the demo customers exist)"))
        fy_start, fy_end = fiscal_year(self.m["company"]["fiscal_year_start"], start)
        if not self.erp.list("Fiscal Year", filters=[["year_start_date", "<=", str(start)],
                                                     ["year_end_date", ">=", str(start)]], limit=1):
            self.erp.insert({"doctype": "Fiscal Year", "year": f"{fy_start.year}-{fy_end.year}"
                             if fy_start.year != fy_end.year else str(fy_start.year),
                             "year_start_date": str(fy_start), "year_end_date": str(fy_end),
                             "companies": [{"company": self.company}]})
        # a rejected incoming lot is still received and then moved to QC Hold; ERPNext's default would refuse the
        # receipt, so the demo site warns instead (demo sites only)
        self.erp.update("Stock Settings", "Stock Settings", {"action_if_quality_inspection_is_rejected": "Warn"})
        for group in sorted({i[2] for i in S.ITEMS}):
            if self.erp.get("Item Group", group) is None:
                self.erp.insert({"doctype": "Item Group", "item_group_name": group,
                                 "parent_item_group": "All Item Groups", "is_group": 0})
        for param, *_ in S.INSPECTED.values():
            if self.erp.get("Quality Inspection Parameter", param) is None:
                self.erp.insert({"doctype": "Quality Inspection Parameter", "parameter": param})
        for code, name, group, _sup, cost, price, _d in S.ITEMS:
            self.erp.insert({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
                             "stock_uom": UOM, "is_stock_item": 1, "valuation_rate": cost, "standard_rate": price,
                             "inspection_required_before_purchase": int(code in S.REQUIRED_BEFORE_RECEIPT)})
        sgroup, cgroup, territory = _leaf(self.erp, "Supplier Group"), _leaf(self.erp, "Customer Group"), \
            _leaf(self.erp, "Territory")
        for s in S.SUPPLIERS:
            self.erp.insert({"doctype": "Supplier", "supplier_name": s, "supplier_group": sgroup})
        for c in S.CUSTOMERS:
            self.erp.insert({"doctype": "Customer", "customer_name": c, "customer_group": cgroup,
                             "territory": territory})

    # ---------------------------------------------------------------- documents
    def apply(self, d: S.Doc) -> None:  # noqa: PLR0912 - one branch per kind of document
        day, x = str(d.day), d.data
        posting = {"posting_date": day, "set_posting_time": 1}
        if d.kind == "opening":
            self.make({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": self.company,
                       **posting, "items": [{"item_code": ln["item"], "qty": ln["qty"], "t_warehouse": self.main,
                                             "basic_rate": ln["rate"]} for ln in x["lines"]]}, d.ref)
        elif d.kind == "po":
            self.make({"doctype": "Purchase Order", "supplier": x["supplier"], "company": self.company,
                       "transaction_date": day, "schedule_date": str(x["due"]),
                       "items": [{"item_code": x["item"], "qty": x["qty"], "rate": x["rate"],
                                  "warehouse": self.main, "schedule_date": str(x["due"])}]}, d.ref)
        elif d.kind in ("receipt", "receipt_draft"):
            po = self.names[x["po"]]
            doc = {"doctype": "Purchase Receipt", "supplier": x["supplier"], "company": self.company, **posting,
                   "items": [{"item_code": x["item"], "qty": x["qty"], "rate": x["rate"], "warehouse": self.main,
                              "purchase_order": po["name"], "purchase_order_item": po["rows"][0]}]}
            # ERPNext wants the inspection before such a receipt is submitted; it is added by the inspection
            self.make(doc, d.ref, submit=d.kind == "receipt" and not x.get("inspect_first"))
            if x.get("inspect_first") and d.kind == "receipt":
                self.pending_receipt = d.ref
        elif d.kind == "inspection":
            pr = self.names[x["receipt"]]
            self.make({"doctype": "Quality Inspection", "inspection_type": "Incoming",
                       "reference_type": "Purchase Receipt", "reference_name": pr["name"], "item_code": x["item"],
                       "sample_size": x["sample"], "report_date": day, "inspected_by": "Administrator",
                       "readings": [{"specification": x["parameter"], "numeric": 1, "min_value": x["min"],
                                     "max_value": x["max"], **{f"reading_{i}": str(v)
                                                               for i, v in enumerate(x["values"], start=1)}}]},
                      d.ref)
            if getattr(self, "pending_receipt", None) == x["receipt"]:
                self.submit("Purchase Receipt", pr["name"])
                self.pending_receipt = None
        elif d.kind == "hold":
            self.make({"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "company": self.company,
                       **posting, "items": [{"item_code": x["item"], "qty": x["qty"], "s_warehouse": self.main,
                                             "t_warehouse": self.hold, "basic_rate": x["rate"]}]}, d.ref)
        elif d.kind == "so":
            self.make({"doctype": "Sales Order", "customer": x["customer"], "company": self.company,
                       "transaction_date": day, "delivery_date": str(x["due"]),
                       "items": [{"item_code": ln["item"], "qty": ln["qty"], "rate": ln["rate"],
                                  "warehouse": self.main, "delivery_date": str(x["due"])} for ln in x["lines"]]},
                      d.ref)
        elif d.kind == "delivery":
            so = self.names[x["so"]]
            self.make({"doctype": "Delivery Note", "customer": x["customer"], "company": self.company, **posting,
                       "items": [{"item_code": ln["item"], "qty": ln["qty"], "rate": ln["rate"],
                                  "warehouse": self.main, "against_sales_order": so["name"],
                                  "so_detail": so["rows"][ln["line"]]} for ln in x["lines"]]}, d.ref)
        elif d.kind == "sales_invoice":
            dn = self.names[x["delivery"]]
            self.make({"doctype": "Sales Invoice", "customer": x["customer"], "company": self.company, **posting,
                       "due_date": str(x["due"]),
                       "items": [{"item_code": ln["item"], "qty": ln["qty"], "rate": ln["rate"],
                                  "delivery_note": dn["name"], "dn_detail": dn["rows"][i]}
                                 for i, ln in enumerate(x["lines"])]}, d.ref)
        elif d.kind == "purchase_invoice":
            pr = self.names[x["receipt"]]
            self.make({"doctype": "Purchase Invoice", "supplier": x["supplier"], "company": self.company,
                       **posting, "due_date": str(x["due"]), "bill_no": d.ref, "bill_date": day,
                       "items": [{"item_code": x["item"], "qty": x["qty"], "rate": x["rate"],
                                  "purchase_receipt": pr["name"], "pr_detail": pr["rows"][0]}]}, d.ref)
        elif d.kind in ("payment_in", "payment_out"):
            inv = self.names[x["invoice"]]["name"]
            pe = self.erp.call("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
                               dt="Sales Invoice" if d.kind == "payment_in" else "Purchase Invoice", dn=inv)
            pe = {k: v for k, v in pe.items() if k not in ("name", "__islocal", "__unsaved", "docstatus")}
            pe["references"] = [{k: v for k, v in r.items() if k not in ("name", "parent", "__islocal", "__unsaved")}
                                for r in pe.get("references") or []]
            pe.update({"posting_date": day, "reference_no": f"DEMO-{d.ref}", "reference_date": day})
            self.make(pe, d.ref)
        else:
            raise DemoError(_say("unknown document kind {kind}", kind=d.kind))

    def run(self) -> dict:
        docs = S.build(self.today)
        self.masters(docs[0].day)
        for i, d in enumerate(docs, start=1):
            try:
                self.apply(d)
            except Exception as exc:
                raise DemoError(_say("{kind} {ref} on {day}: {exc}",
                                    kind=d.kind, ref=d.ref, day=d.day, exc=exc)) from exc
            if i % 50 == 0:
                self.say(f"{i} of {len(docs)} documents")
        return {"documents": S.summary(docs), "rejected_inspection": next(
            (self.names[d.ref]["name"] for d in docs if d.kind == "inspection" and d.data["rejected"]), None)}


def quality_records(conn, manifest: dict, rejected_qi: str | None, today: dt.date) -> list[str]:
    """Hub-side quality history for the rejected lot: an NCR and a corrective action with an overdue step."""
    from wqops.hub.ont import metrics as M  # noqa: PLC0415
    from wqops.hub.quality import records as Q  # noqa: PLC0415

    if not rejected_qi:
        return []
    qi = conn.execute("select props from ont_objects where type = 'QualityInspection' and key = %s",
                      (rejected_qi,)).fetchone()
    if qi is None:
        raise DemoError(_say("{rejected_qi} has not been synced yet", rejected_qi=rejected_qi))
    p = qi["props"]
    day = M._d(p.get("report_date")) or today
    people = {x["roles"][0]: x["email"] for x in manifest["people"]}
    quality, buyer = people.get("quality"), people.get("purchasing")
    sup = conn.execute("select dst_key from ont_links where src_type = 'PurchaseReceipt' and src_key = %s and "
                       "type = 'supplier'", (p.get("reference_name"),)).fetchone()
    pr = conn.execute("select props from ont_objects where type = 'PurchaseReceipt' and key = %s",
                      (p.get("reference_name"),)).fetchone()
    qty = sum(ln.get("qty") or 0 for ln in (pr["props"].get("lines", []) if pr else [])
              if ln.get("item_code") == p["item_code"]) or None
    n = Q.create_ncr(conn, quality, title=f"Rejected {p['item_code']} ({rejected_qi})", severity="major",
                     description=f"Pitch diameter over the upper limit on all 5 samples of the lot received on "
                                 f"{p.get('reference_name')}.", inspection=rejected_qi, item_code=p["item_code"],
                     receipt=p.get("reference_name"), supplier=sup["dst_key"] if sup else None, quantity=qty)
    Q.contain(conn, n["id"], quality, "Lot moved to QC Hold; open orders for this item checked.")
    if qty:
        Q.submit_disposition(conn, n["id"], quality, "return_to_supplier", qty, "Return the lot for credit.")
    c = Q.create_capa(conn, quality, kind="corrective", title="Supplier thread rolling out of tolerance",
                      ncr_ids=[n["id"]], description="Thread pitch diameter over the limit on a full lot.",
                      risk="medium", owner=buyer)
    Q.submit_capa(conn, c["id"], quality)
    Q.update_capa(conn, c["id"], quality, containment="Lot quarantined and returned.",
                  root_cause="Supplier did not adjust rolling dies after maintenance (supplier 8D).")
    Q.add_action(conn, c["id"], quality, "Supplier to send 8D and first-article data", buyer,
                 str(day + dt.timedelta(days=10)), today=day)
    Q.plan_actions(conn, c["id"], quality)
    return [n["name"], c["name"]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wqops.demo.load", description="Load the fictional demo business")
    ap.add_argument("--today", type=dt.date.fromisoformat, help="pretend today is this date (tests)")
    a = ap.parse_args(argv)
    from wqops.erp_setup import client_from_env  # noqa: PLC0415
    from wqops.hub import db as DB  # noqa: PLC0415
    from wqops.hub import sync as Y  # noqa: PLC0415
    from wqops.hub.ont import anomaly as AN  # noqa: PLC0415
    from wqops.hub.ont import api as OA  # noqa: PLC0415
    from wqops.hub.ont import project as OP  # noqa: PLC0415

    manifest = C.load(os.environ["WQO_COMPANY_FILE"])
    today = a.today or OA.today(manifest)
    with DB.connect(os.environ["WQO_DB"]) as conn:
        DB.migrate(conn)
        try:
            with Y.paused(conn):     # the hub syncs once the whole business is in ERPNext, not half of it
                out = Loader(client_from_env(), manifest, today).run()
        except DemoError as exc:
            print(f"demo data not loaded: {exc}", file=sys.stderr)
            return 1
        Y.run(conn, client_from_env(), trigger="demo")
        OP.project(conn, manifest=manifest)
        out["quality"] = quality_records(conn, manifest, out["rejected_inspection"], today)
        OP.project(conn, manifest=manifest)
        AN.detect(conn, today)
        # the hub may have made today's brief before the business was loaded; make it again from the loaded data
        from wqops.hub.ai import brief as BR  # noqa: PLC0415
        from wqops.hub.ai import llm as L  # noqa: PLC0415

        out["brief"] = str(BR.generate(conn, today, manifest, L.Anthropic())["day"])
        from wqops.demo import documents as DOCS  # noqa: PLC0415

        out["documents"] = DOCS.load(conn, manifest, today, L.Anthropic())
        from wqops.demo import quality as DQ  # noqa: PLC0415
        from wqops.hub import accounts as Acc  # noqa: PLC0415

        Acc.sync(conn, manifest)
        out["quality_samples"] = DQ.load(conn, manifest, today)
        OP.project(conn, manifest=manifest)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
