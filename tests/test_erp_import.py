"""20a (ADR-0020): another system's exports into ERPNext through the ledger import. The usual column names
(QuickBooks, SAP Business One, Odoo) are matched by rules; records already in ERPNext are skipped; opening stock and
orders need their items, warehouses and customers in ERPNext first; order lines become one order; orders and stock
are drafts in ERPNext unless the signer submits them; every row is recorded once. Fictional data only."""

import pytest
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, JORDAN, PW, SAM
from tests.test_metrics import build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import erp_import as EI
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import ledger_ai as LAI
from wqops.hub.docs import ledgers as LS
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP

DANA, ALEX = "dana@demo.example", "alex@demo.example"
CO = "Harbor Lane Supply (Demo)"
# a QuickBooks products export, an SAP Business One stock list and an Odoo-like order list (all invented)
ITEMS = ("Product/Service Name,Sales Description,Type,Sales Price / Rate,Purchase Cost\n"
         "GADGET-1,Small gadget,Inventory,12.50,6\nGADGET-2,Large gadget,Service,30,\n"
         "WIDGET-A,Widget,Inventory,4,2\nGADGET-1,Small gadget again,Inventory,12.50,6\n")
STOCK = "ItemCode,WhsCode,OnHand,AvgPrice\nGADGET-1,Main Stock,40,6\nWIDGET-A,Main Stock,10,2\nNOPE-9,Main Stock,5,1\n"
ORDERS = ("Order Number,Customer,Order Date,Delivery Date,Item,Quantity,Unit Price\n"
          "1001,Bayside Hardware,2026-10-01,2026-10-20,GADGET-1,5,12.5\n"
          "1001,Bayside Hardware,2026-10-01,2026-10-20,WIDGET-A,2,4\n"
          "1002,Nobody Inc,2026-10-02,2026-10-21,GADGET-1,1,12.5\n")


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (DANA, SAM, JORDAN, ALEX):
        Acc.set_password(conn, e, PW)
    f = build()
    f.put("Customer", "Bayside Hardware", customer_name="Bayside Hardware")
    f.put("Account", "Temporary Opening - HLS", account_type="Temporary", company=CO, is_group=0)
    erp = ErpClient("http://erp", transport=f.transport())
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    return conn, f, erp


def start(conn, name, text, target):
    imp = LIB.new_import(conn, DANA, "old system")
    doc = LIB.add_file(conn, imp["id"], name, text.encode())
    LIB.extract_import(conn, imp["id"])
    t = LS.table_of(conn, doc)
    p = LAI.propose(conn, {"email": DANA, "roles": ["owner"]}, t, {target: LS.flds(conn, target)}, None,
                    target=target, today=AS_OF)
    return doc, LS.create(conn, DANA, doc, p["target"], t, p["proposal"], p["engine"], p["ai_run"])


def sync(conn, erp):
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)


def run(conn, erp, lid, submit=False):
    return EI.run(conn, erp, Acc.get(conn, DANA), lid, PW, company=CO, today=AS_OF, submit=submit,
                  seen=LS.mapping_print(LS.get(conn, lid)))


def test_values_that_cannot_be_read_stop_the_row(world):
    conn, _, _ = world
    _, imp = start(conn, "items.csv", "SKU,Name,Sales Price,Cost\nA-1,Alpha,\"$1,250.00\",0\nB-2,Beta,twelve,1\n",
                   "erp_item")
    pv = LS.preview(conn, imp)
    a, b = pv["rows"]
    assert a["ok"] and a["values"]["standard_rate"] == 1250.0 and a["values"]["valuation_rate"] == 0
    assert not b["ok"] and "cannot be read, so not imported: selling price" in b["problems"]
    assert LG.parse_number("€ 3.5") == 3.5 and LG.parse_number("12,5") is None


def test_known_exports_are_matched_by_their_column_names():
    t = LG.table("items.csv", ITEMS.encode())
    m = LG.rules_mapping("erp_item", t, LG.fields("erp_item"))
    assert m["mapping"]["item_code"] == {"column": "Product/Service Name"}
    assert m["mapping"]["standard_rate"] == {"column": "Sales Price / Rate"}
    assert m["values"]["is_stock_item"] == {"Inventory": "yes", "Service": "no"}
    t = LG.table("stock.csv", STOCK.encode())
    m = LG.rules_mapping("erp_opening_stock", t, LG.fields("erp_opening_stock"))
    assert {f: x["column"] for f, x in m["mapping"].items()} == {"item_code": "ItemCode", "warehouse": "WhsCode",
                                                                  "qty": "OnHand", "valuation_rate": "AvgPrice"}


def test_items_then_stock_then_orders(world):
    conn, f, erp = world
    _, imp = start(conn, "QuickBooks products.csv", ITEMS, "erp_item")
    pv = LS.preview(conn, imp)
    assert (pv["total"], pv["ready"], pv["already"]) == (4, 2, 2)
    assert "already in ERPNext as WIDGET-A" in pv["rows"][2]["exists"] and "row 2" in pv["rows"][3]["exists"]
    with pytest.raises(EI.Q.SignatureError):
        EI.run(conn, erp, Acc.get(conn, DANA), imp["id"], "wrong", company=CO, today=AS_OF,
               seen=LS.mapping_print(imp))
    with pytest.raises(EI.ErpImportError, match="mapping changed"):
        EI.run(conn, erp, Acc.get(conn, DANA), imp["id"], PW, company=CO, today=AS_OF, seen="old")
    out = run(conn, erp, imp["id"])
    assert out["status"] == "imported" and out["result"] == {"imported": 2, "drafted": 0, "skipped": 2}
    g = f.docs["Item"]["GADGET-1"]
    assert (g["item_name"], g["description"], g["is_stock_item"], g["standard_rate"]) == ("GADGET-1", "Small gadget",
                                                                                          1, 12.5)
    assert f.docs["Item"]["GADGET-2"]["is_stock_item"] == 0
    with pytest.raises(EI.ErpImportError, match="has been run"):
        run(conn, erp, imp["id"])
    # the same file again: what came in before is skipped, nothing is doubled
    doc = LIB.get(conn, imp["document_id"])
    t = LS.table_of(conn, doc)
    again = LS.create(conn, DANA, doc, "erp_item", t, {"mapping": imp["mapping"], "values": imp["values_map"]},
                      "person")
    assert run(conn, erp, again["id"])["result"]["imported"] == 0 and len(f.docs["Item"]) == 4
    # opening stock: needs its items in ERPNext; one Stock Reconciliation, a draft there
    sync(conn, erp)
    _, st = start(conn, "SAP stock.csv", STOCK, "erp_opening_stock")
    pv = LS.preview(conn, st)
    assert pv["ready"] == 2 and "'NOPE-9' is not in ERPNext yet" in " ".join(pv["rows"][2]["problems"])
    out = run(conn, erp, st["id"])
    assert out["result"] == {"imported": 0, "drafted": 2, "skipped": 1}
    (sr,) = f.docs["Stock Reconciliation"].values()
    assert sr["purpose"] == "Opening Stock" and sr["docstatus"] == 0 and sr["company"] == CO
    assert sr["expense_account"] == "Temporary Opening - HLS"
    assert [(i["item_code"], i["warehouse"], i["qty"]) for i in sr["items"]] == [("GADGET-1", "Main Stock - HLS", 40),
                                                                                  ("WIDGET-A", "Main Stock - HLS", 10)]
    # orders: lines of one order become one order; an order with an unknown customer waits; submitted on request
    _, so = start(conn, "Odoo orders.csv", ORDERS, "erp_sales_order")
    out = run(conn, erp, so["id"], submit=True)
    assert out["result"] == {"imported": 2, "drafted": 0, "skipped": 1}
    (order,) = [d for d in f.docs["Sales Order"].values() if d.get("company") == CO]
    assert order["docstatus"] == 1 and order["customer"] == "Bayside Hardware" and len(order["items"]) == 2
    assert order["transaction_date"] == "2026-10-01" and order["items"][0]["delivery_date"] == "2026-10-20"
    skipped = [r["note"] for r in LS.outcomes(conn, so["id"]) if r["outcome"] == "skipped"]
    assert len(skipped) == 1 and "'Nobody Inc' is not in ERPNext yet" in skipped[0]
    # a later export overlapping the first (another file): order 1001 and the stock are not brought in twice
    _, so2 = start(conn, "Odoo orders again.csv", ORDERS + "1003,Bayside Hardware,2026-10-03,2026-10-22,BOLT-B,1,0\n",
                   "erp_sales_order")
    pv = LS.preview(conn, so2)
    assert pv["rows"][0]["exists"].startswith("imported before as Sales Order:") and pv["ready"] == 1
    out = run(conn, erp, so2["id"])
    assert out["result"] == {"imported": 0, "drafted": 1, "skipped": 3}           # a price of 0 is a price
    bolt = next(d for d in f.docs["Sales Order"].values()
                if d.get("company") == CO and d["items"][0]["item_code"] == "BOLT-B")
    assert bolt["items"][0]["rate"] == 0
    _, st2 = start(conn, "stock again.csv", STOCK.replace("NOPE-9", "BOLT-B"), "erp_opening_stock")
    assert run(conn, erp, st2["id"])["result"] == {"imported": 0, "drafted": 1, "skipped": 2}


def test_refused_rows_and_a_part_of_an_order(world):
    conn, f, erp = world
    sync(conn, erp)
    lines = ORDERS.replace("1002,Nobody Inc", "1001,Bayside Hardware").replace("2026-10-02", "2026-10-01") \
        .replace("2026-10-21", "2026-10-20").replace("GADGET-1,1,", "NOPE-9,1,").replace("GADGET-1,5,", "BOLT-B,5,")
    _, so = start(conn, "orders.csv", lines, "erp_sales_order")
    out = run(conn, erp, so["id"])
    assert out["result"]["drafted"] == 0
    assert not [d for d in f.docs.get("Sales Order", {}).values() if d.get("company") == CO]
    assert "another line of order 1001" in LS.outcomes(conn, so["id"])[0]["note"]
    f.fail_after = 0                                  # ERPNext stops answering: rows are skipped with the reason
    _, it = start(conn, "items.csv", ITEMS, "erp_item")
    out = run(conn, erp, it["id"])
    assert out["result"]["skipped"] == 4 and "ERPNext refused it" in LS.outcomes(conn, it["id"])[0]["note"]


def test_erp_import_api(db_url, world):
    conn, _, erp = world
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, erp=erp))
    c.__enter__()
    doc, imp = start(conn, "QuickBooks products.csv", ITEMS, "erp_item")
    c.post("/api/login", json={"email": ALEX, "password": PW})
    assert "erp_item" not in c.get("/api/ledgers", params={"document_id": doc["id"]}).json()["kinds"]
    assert c.post(f"/api/ledgers/{imp['id']}/import", json={"password": PW}).status_code == 403
    assert c.get(f"/api/ledgers/{imp['id']}").status_code == 403           # nor see its rows
    c.post("/api/login", json={"email": SAM, "password": PW})            # the operations manager may import
    seen = c.get(f"/api/ledgers/{imp['id']}").json()["preview"]["print"]
    assert c.post(f"/api/ledgers/{imp['id']}/import", json={"password": PW}).status_code == 409   # look first
    v = c.post(f"/api/ledgers/{imp['id']}/import", json={"password": PW, "seen": seen}).json()
    assert v["status"] == "imported" and v["result"]["imported"] == 2
    assert conn.execute("select 1 from ont_objects where type = 'Item' and key = 'GADGET-1'").fetchone()  # synced
    c.__exit__(None, None, None)
