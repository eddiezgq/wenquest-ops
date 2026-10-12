"""Ops hub metrics (ADR-0007, step 6b) on a small fictional business, checked against hand calculations.

Period: 30 days ending 2026-10-12, so 2026-09-13 .. 2026-10-12. Days of inventory looks back 90 days
(2026-07-15 .. 2026-10-12).
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.fake_erp import FakeErp
from wqops import company as C
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import metrics as M
from wqops.hub.ont import project as OP

DEMO = C.load(C.DEMO_FILE)
AS_OF = dt.date(2026, 10, 12)
MAIN, QC = "Main Stock - HLS", "QC Hold - HLS"


def build() -> FakeErp:
    f = FakeErp()
    f.put("Warehouse", MAIN, warehouse_name="Main Stock")
    f.put("Warehouse", QC, warehouse_name="QC Hold")
    for code in ("WIDGET-A", "BOLT-B"):
        f.put("Item", code, item_name=code.title(), is_stock_item=1)

    def sle(name, item, wh, qty, value, vt, vn, date, cancelled=0):
        f.put("Stock Ledger Entry", name, item_code=item, warehouse=wh, actual_qty=qty, stock_value_difference=value,
              voucher_type=vt, voucher_no=vn, posting_date=date, is_cancelled=cancelled, docstatus=1)

    sle("S1", "WIDGET-A", MAIN, 100, 200.0, "Purchase Receipt", "PR-1", "2026-09-01")
    sle("S2", "WIDGET-A", MAIN, -40, -80.0, "Delivery Note", "DN-1", "2026-09-20")
    sle("S3", "WIDGET-A", QC, 10, 20.0, "Stock Entry", "STE-1", "2026-09-25")
    sle("S4", "BOLT-B", MAIN, 50, 500.0, "Purchase Receipt", "PR-2", "2026-09-10")
    sle("S5", "BOLT-B", MAIN, -45, -450.0, "Delivery Note", "DN-2", "2026-10-01")
    sle("S6", "BOLT-B", MAIN, -5, -50.0, "Delivery Note", "DN-3", "2026-10-05", cancelled=1)
    sle("S7", "WIDGET-A", MAIN, -10, -20.0, "Delivery Note", "DN-4", "2026-06-01")

    def so(name, status, due, per, items, docstatus=1):
        f.put("Sales Order", name, customer="Bayside Hardware", customer_name="Bayside Hardware", status=status,
              delivery_date=due, per_delivered=per, docstatus=docstatus, items=items)

    so("SO-1", "Completed", "2026-09-21", 100, [{"item_code": "WIDGET-A", "qty": 40, "delivered_qty": 40}])
    so("SO-2", "Completed", "2026-09-28", 100, [{"item_code": "BOLT-B", "qty": 45, "delivered_qty": 45}])
    so("SO-3", "Completed", "2026-08-01", 100, [{"item_code": "WIDGET-A", "qty": 10, "delivered_qty": 10}])
    so("SO-4", "Completed", "2026-09-30", 100, [{"item_code": "WIDGET-A", "qty": 1, "delivered_qty": 1}])
    so("SO-5", "To Deliver and Bill", "2026-10-20", 0, [{"item_code": "WIDGET-A", "qty": 80, "delivered_qty": 0},
                                                        {"item_code": "BOLT-B", "qty": 3, "delivered_qty": 0}])
    so("SO-6", "To Deliver", "2026-10-15", 40, [{"item_code": "BOLT-B", "qty": 10, "delivered_qty": 4}])
    so("SO-7", "Draft", "2026-10-30", 0, [{"item_code": "WIDGET-A", "qty": 1000}], docstatus=0)

    def dn(name, order, date, docstatus=1):
        f.put("Delivery Note", name, customer="Bayside Hardware", posting_date=date, docstatus=docstatus,
              items=[{"item_code": "X", "qty": 1, "against_sales_order": order}])

    dn("DN-1", "SO-1", "2026-09-20")
    dn("DN-2", "SO-2", "2026-10-01")
    dn("DN-3", "SO-2", "2026-10-05", docstatus=2)  # cancelled: does not move SO-2's delivery date
    dn("DN-4", "SO-3", "2026-06-01")

    f.put("Purchase Order", "PO-1", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners", docstatus=1,
          items=[{"name": "po1-a", "item_code": "WIDGET-A", "qty": 100, "schedule_date": "2026-09-15"}])
    f.put("Purchase Order", "PO-2", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners", docstatus=1,
          items=[{"name": "po2-b", "item_code": "BOLT-B", "qty": 50, "schedule_date": "2026-09-30"},
                 {"name": "po2-a", "item_code": "WIDGET-A", "qty": 5, "schedule_date": "2026-09-20"}])

    def pr(name, supplier, date, lines):
        f.put("Purchase Receipt", name, supplier=supplier, supplier_name=supplier, posting_date=date, docstatus=1,
              items=lines)

    pr("PR-1", "Gulf Fasteners", "2026-09-14", [{"item_code": "WIDGET-A", "qty": 100, "purchase_order": "PO-1",
                                                 "purchase_order_item": "po1-a"}])
    pr("PR-2", "Gulf Fasteners", "2026-10-02", [
        {"item_code": "BOLT-B", "qty": 50, "purchase_order": "PO-2", "purchase_order_item": "po2-b"},
        {"item_code": "WIDGET-A", "qty": 5, "purchase_order": "PO-2", "purchase_order_item": "po2-a"}])
    pr("PR-3", "Acme Cable", "2026-09-20", [{"item_code": "BOLT-B", "qty": 1}])
    pr("PR-4", "Acme Cable", "2026-08-01", [{"item_code": "BOLT-B", "qty": 1, "purchase_order_item": "po2-b"}])

    def qi(name, status, date, docstatus=1):
        f.put("Quality Inspection", name, item_code="BOLT-B", status=status, report_date=date, docstatus=docstatus,
              reference_type="Purchase Receipt", reference_name="PR-2", inspection_type="Incoming")

    qi("QI-1", "Rejected", "2026-10-02")
    qi("QI-2", "Accepted", "2026-10-02")
    qi("QI-3", "Rejected", "2026-08-01")
    qi("QI-4", "Rejected", "2026-10-03", docstatus=0)
    return f


@pytest.fixture
def conn_demo(conn):
    Y.run(conn, ErpClient("http://erp", transport=build().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def test_on_time_delivery(conn_demo):
    r = M.on_time_delivery(conn_demo, AS_OF, 30)
    # SO-1 delivered 09-20 for 09-21: on time; SO-2 delivered 10-01 for 09-28: 3 days late;
    # SO-3 finished before the period; SO-4 has no delivery note (unknown); SO-5..7 not finished
    assert (r["value"], r["on_time"], r["total"]) == (50.0, 1, 2)
    assert [(x["key"], x["days_late"]) for x in r["late"]] == [("SO-2", 3)]
    assert r["unknown"] == [{"key": "SO-4", "missing": "delivery note date"}]
    assert r["period"] == ["2026-09-13", "2026-10-12"]


def test_shortages(conn_demo):
    r = M.shortages(conn_demo)
    # WIDGET-A: on hand 100-40-10 = 50 in Main (10 in QC Hold not counted); open demand SO-5 80 -> short 30
    # BOLT-B: on hand 50-45 = 5 (the cancelled -5 does not count); demand SO-5 3 + SO-6 (10-4) 6 = 9 -> short 4
    # the draft SO-7 is not demand
    assert r["value"] == 2
    assert [(x["item"], x["on_hand"], x["demand"], x["short"], x["orders"]) for x in r["items"]] == [
        ("BOLT-B", 5.0, 9.0, 4.0, ["SO-5", "SO-6"]), ("WIDGET-A", 50.0, 80.0, 30.0, ["SO-5"])]


def test_inventory_value_and_days(conn_demo):
    r = M.inventory_value(conn_demo)
    # Main: WIDGET-A 200-80-20 = 100, BOLT-B 500-450 = 50; QC Hold: 20
    assert r["value"] == 170.0 and r["by_warehouse"] == {MAIN: 150.0, QC: 20.0}
    d = M.days_of_inventory(conn_demo, AS_OF)
    # shipped in 90 days: DN-1 80 + DN-2 450 = 530 (DN-3 cancelled, DN-4 before the 90 days); 170 / (530 / 90)
    assert d["shipped_value"] == 530.0 and d["value"] == round(170 / (530 / 90), 1) == 28.9


def test_supplier_on_time(conn_demo):
    r = M.supplier_on_time(conn_demo, AS_OF, 30)
    # PR-1 09-14 for 09-15 on time; PR-2 10-02: po2-b due 09-30 (2 late), po2-a due 09-20 (12 late)
    # PR-3 names no order line (unknown); PR-4 is before the period
    assert (r["value"], r["on_time"], r["total"]) == (33.3, 1, 3)
    gulf = r["suppliers"][0]
    assert gulf["supplier"] == "Gulf Fasteners" and gulf["value"] == 33.3
    assert sorted(x["days_late"] for x in gulf["late"]) == [2, 12]
    assert r["unknown"] == [{"receipt": "PR-3", "line": 1}]


def test_open_nonconformances(conn_demo):
    r = M.open_nonconformances(conn_demo, AS_OF, 30)
    assert r["value"] == 1 and r["inspections"][0]["key"] == "QI-1"   # QI-3 too old, QI-4 a draft


def test_no_data_is_unknown_not_zero(conn):
    assert M.on_time_delivery(conn, AS_OF, 30)["value"] is None
    assert M.supplier_on_time(conn, AS_OF, 30)["value"] is None
    assert M.days_of_inventory(conn, AS_OF)["value"] is None
    assert M.inventory_value(conn)["value"] == 0  # no stock at all is a real zero


def test_weekly_trend(conn_demo):
    t = M.weekly(conn_demo, "on_time_delivery", AS_OF)
    assert [x["week_ending"] for x in t][-4:] == ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12"]
    assert [x["value"] for x in t][-4:] == [100.0, None, 0.0, None]


def test_dashboard_by_role(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=build().transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "alex@demo.example", "Demo pass 2026")
        Acc.set_password(conn, "dana@demo.example", "Demo pass 2026")
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Demo pass 2026"})
    c.post("/api/sync/run")
    d = c.get("/api/dashboard", params={"as_of": "2026-10-12"}).json()
    assert {m["name"]: m["value"] for m in d["metrics"]} == {
        "on_time_delivery": 50.0, "shortages": 2, "inventory_value": 170.0, "days_of_inventory": 28.9,
        "supplier_on_time": 33.3, "open_nonconformances": 1}
    assert all(m["definition"] for m in d["metrics"]) and set(d["trends"]) == set(M.TRENDS)
    assert c.get("/api/dashboard", params={"days": 14}).status_code == 400
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})   # sales
    d = c.get("/api/dashboard", params={"as_of": "2026-10-12"}).json()
    assert [m["name"] for m in d["metrics"]] == ["on_time_delivery", "shortages", "inventory_value",
                                                 "days_of_inventory"]
    assert c.get("/api/dashboard/supplier_on_time").status_code == 403
    assert c.get("/api/dashboard/shortages").json()["value"] == 2
    c.__exit__(None, None, None)
