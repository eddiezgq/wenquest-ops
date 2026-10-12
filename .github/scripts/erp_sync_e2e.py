"""ERPNext sync and drafts against the real ERPNext of a fresh install (ADR-0006). Runs inside the hub container:

    docker compose exec -T hub python - < .github/scripts/erp_sync_e2e.py

Creates a few documents for the fictional demo company, then checks that created, changed and deleted documents
become events. Uses its own PostgreSQL schema so the hub's own sync state is untouched, and saves ERPNext's replies
under /tmp/erp-recordings/<run> for the replay test (tests/recordings/erpnext/).
"""

import datetime as dt
import json
import os
import time
from pathlib import Path

import psycopg

from wqops.erp_setup import client_from_env
from wqops.hub import db as DB
from wqops.hub import sync as Y

OUT = Path("/tmp/erp-recordings")  # noqa: S108 - inside a throwaway CI container
erp = client_from_env()
today = dt.date.today()  # noqa: DTZ011 - ERPNext dates are in the site's time zone; close enough for test data
company = erp.list("Company", fields=["name", "abbr"], order_by="name asc", limit=1)[0]
wh = f"Main Stock - {company['abbr']}"


def leaf(doctype):
    return erp.list(doctype, filters=[["is_group", "=", 0]], order_by="name asc", limit=1)[0]["name"]


item = erp.insert({"doctype": "Item", "item_code": "CI-WIDGET-01", "item_name": "CI Widget (demo)",
                   "item_group": leaf("Item Group"), "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 2.5})
customer = erp.insert({"doctype": "Customer", "customer_name": "CI Bayside Hardware (Demo)",
                       "customer_group": leaf("Customer Group"), "territory": leaf("Territory")})
temp = erp.insert({"doctype": "Customer", "customer_name": "CI Short-lived Customer (Demo)",
                   "customer_group": leaf("Customer Group"), "territory": leaf("Territory")})
supplier = erp.insert({"doctype": "Supplier", "supplier_name": "CI Gulf Fasteners (Demo)",
                       "supplier_group": leaf("Supplier Group")})
receipt = erp.insert({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": company["name"],
                      "items": [{"item_code": item["name"], "qty": 10, "t_warehouse": wh, "basic_rate": 2.5}]})
erp.update("Stock Entry", receipt["name"], {"docstatus": 1})
po = erp.insert({"doctype": "Purchase Order", "supplier": supplier["name"], "company": company["name"],
                 "transaction_date": str(today), "schedule_date": str(today + dt.timedelta(days=7)),
                 "items": [{"item_code": item["name"], "qty": 5, "rate": 2.5, "warehouse": wh,
                            "schedule_date": str(today + dt.timedelta(days=7))}]})
so = erp.insert({"doctype": "Sales Order", "customer": customer["name"], "company": company["name"],
                 "transaction_date": str(today), "delivery_date": str(today + dt.timedelta(days=3)),
                 "items": [{"item_code": item["name"], "qty": 2, "rate": 9, "warehouse": wh,
                            "delivery_date": str(today + dt.timedelta(days=3))}]})

url = os.environ["WQO_DB"]
with psycopg.connect(url, autocommit=True) as c:
    c.execute("drop schema if exists sync_e2e cascade")
    c.execute("create schema sync_e2e")
conn = DB.connect(url)
conn.execute("set search_path to sync_e2e")
DB.migrate(conn)


def sync(n):
    client = client_from_env(Y.RecordingTransport(OUT / str(n)))
    for _ in range(60):  # the hub's own background sync may hold the lock for a moment
        try:
            return Y.run(conn, client, trigger="ci", page=20)["events"]
        except Y.SyncBusy:
            time.sleep(2)
    raise SystemExit("the sync lock was never free")


def kinds(doctype, name):
    return [r["kind"] for r in conn.execute("select kind from erp_events where doctype = %s and name = %s "
                                            "order by id", (doctype, name)).fetchall()]


first = sync(1)
print("run 1", first)
assert first["Item"] >= 1 and first["Customer"] >= 2 and first["Supplier"] >= 1, first
assert first["Warehouse"] >= 4 and first["Stock Ledger Entry"] >= 1, first
assert kinds("Purchase Order", po["name"]) == ["created"] and kinds("Sales Order", so["name"]) == ["created"]
lines = conn.execute("select data from erp_docs where doctype = 'Purchase Order' and name = %s",
                     (po["name"],)).fetchone()["data"]["items"]
assert lines[0]["item_code"] == item["name"] and lines[0]["qty"] == 5, lines
sle = conn.execute("select data from erp_docs where doctype = 'Stock Ledger Entry' and data->>'item_code' = %s",
                   (item["name"],)).fetchone()["data"]
assert sle["actual_qty"] == 10 and sle["warehouse"] == wh, sle

erp.update("Item", item["name"], {"description": "Changed by CI"})
erp.update("Purchase Order", po["name"], {"docstatus": 1})
erp.http.delete(f"/api/resource/Customer/{temp['name']}").raise_for_status()
second = sync(2)
print("run 2", second)
assert kinds("Item", item["name"]) == ["created", "updated"]
assert kinds("Purchase Order", po["name"]) == ["created", "submitted"]
assert kinds("Customer", temp["name"]) == ["created", "deleted"]

third = sync(3)
print("run 3", third)
assert sum(third.values()) == 0, third

summary = {"runs": [first, second, third], "page": 20}
(OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
print("ERPNext sync end to end: ok")

# Drafts (ADR-0006 item 5): proposed, confirmed by a person, created in ERPNext as a Draft - never submitted
from wqops.hub import drafts as D  # noqa: E402

buyer = {"email": "pat@demo.example", "roles": ["purchasing"]}
d = D.propose(conn, buyer, "Purchase Order", {
    "supplier": supplier["name"], "company": company["name"], "transaction_date": str(today),
    "schedule_date": str(today + dt.timedelta(days=10)),
    "items": [{"item_code": item["name"], "qty": 7, "rate": 2.5, "warehouse": wh,
               "schedule_date": str(today + dt.timedelta(days=10))}]}, summary="CI restock", source="ai", ai_run="ci")
done = D.confirm(conn, buyer, d["id"], erp)
made = erp.get("Purchase Order", done["erp_name"])
assert made["docstatus"] == 0 and made["items"][0]["qty"] == 7, made
print("draft written to ERPNext:", done["erp_name"])
