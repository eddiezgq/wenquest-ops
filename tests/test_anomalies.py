"""Anomalies and root causes (ADR-0007, step 6c) on the fictional business of test_metrics, plus a late order."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import AS_OF, DEMO, MAIN, build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import chain as CH
from wqops.hub.ont import project as OP


def business():
    f = build()
    # earlier purchase orders are complete
    f.put("Purchase Order", "PO-1", status="Completed", items=[{"name": "po1-a", "item_code": "WIDGET-A", "qty": 100,
                                                               "received_qty": 100, "schedule_date": "2026-09-15"}])
    f.put("Purchase Order", "PO-2", status="Completed", items=[
        {"name": "po2-b", "item_code": "BOLT-B", "qty": 50, "received_qty": 50, "schedule_date": "2026-09-30"},
        {"name": "po2-a", "item_code": "WIDGET-A", "qty": 5, "received_qty": 5, "schedule_date": "2026-09-20"}])
    # a late order waiting for WIDGET-A, which waits for a late purchase order
    f.put("Sales Order", "SO-8", customer="Bayside Hardware", customer_name="Bayside Hardware", status="To Deliver",
          delivery_date="2026-10-08", per_delivered=0, docstatus=1,
          items=[{"item_code": "WIDGET-A", "qty": 20, "delivered_qty": 0}])
    f.put("Purchase Order", "PO-3", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners", docstatus=1,
          status="To Receive and Bill", schedule_date="2026-10-10",
          items=[{"name": "po3-a", "item_code": "WIDGET-A", "qty": 60, "received_qty": 0,
                  "schedule_date": "2026-10-10"}])
    return f


@pytest.fixture
def world(conn):
    f = business()
    erp = ErpClient("http://erp", transport=f.transport())
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    return conn, f, erp


def active(conn):
    return sorted((r["rule"], r["subject_key"], r["severity"]) for r in conn.execute(
        "select * from anomalies where status in ('open', 'ack', 'doing')").fetchall())


def test_rules_find_the_problems(world):
    conn, _, _ = world
    assert AN.detect(conn, AS_OF)["opened"] == 7
    assert active(conn) == [
        ("inspection_rejected", "QI-1", "warn"),
        ("item_short", "BOLT-B", "warn"),          # on hand 5, SO-5 3 + SO-6 6 = 9
        ("item_short", "WIDGET-A", "warn"),        # on hand 50, SO-5 80 + SO-8 20 = 100
        ("order_at_risk", "SO-6", "warn"),         # due 10-15 (within 7 days), BOLT-B short; SO-5 due 10-20 is not
        ("order_late", "SO-8", "warn"),            # due 10-08, 4 days late
        ("po_late", "PO-3", "warn"),               # required by 10-10, nothing received
        ("supplier_on_time_low", "Gulf Fasteners", "info"),   # 1 of 3 lines on time in 90 days
    ]
    assert AN.detect(conn, AS_OF) == {"opened": 0, "updated": 7, "escalated": 0, "resolved": 0}


def test_life_cycle(world):
    conn, f, erp = world
    AN.detect(conn, AS_OF)
    # PO-3 arrives: WIDGET-A is no longer short and PO-3 no longer late; SO-8 is still late
    f.put("Purchase Order", "PO-3", status="To Bill", items=[{"name": "po3-a", "item_code": "WIDGET-A", "qty": 60,
                                                             "received_qty": 60, "schedule_date": "2026-10-10"}])
    f.put("Stock Ledger Entry", "S8", item_code="WIDGET-A", warehouse=MAIN, actual_qty=60, stock_value_difference=120.0,
          voucher_type="Purchase Receipt", voucher_no="PR-5", posting_date="2026-10-12", is_cancelled=0, docstatus=1)
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    assert AN.detect(conn, AS_OF)["resolved"] == 0           # gone once: not yet resolved
    assert AN.detect(conn, AS_OF)["resolved"] == 2           # gone twice
    assert ("item_short", "WIDGET-A", "warn") not in active(conn)
    out = AN.detect(conn, AS_OF + dt.timedelta(days=8))      # SO-8 now 12 days late
    assert out["escalated"] >= 1 and ("order_late", "SO-8", "critical") in active(conn)
    aid = conn.execute("select id from anomalies where rule = 'order_late' and subject_key = 'SO-8'").fetchone()["id"]
    AN.set_status(conn, aid, "ack", "sam@demo.example")
    AN.set_status(conn, aid, "closed", "sam@demo.example", "customer agreed a new date")
    with pytest.raises(ValueError, match="from closed to ack"):
        AN.set_status(conn, aid, "ack", "sam@demo.example")
    log = [r["action"] for r in conn.execute("select action from anomaly_log where anomaly_id = %s order by id",
                                             (aid,)).fetchall()]
    assert log == ["opened", "escalated", "ack", "closed"]
    assert AN.detect(conn, AS_OF + dt.timedelta(days=8))["opened"] == 1   # still late: a new anomaly


def test_late_order_root_cause(world):
    conn, _, _ = world
    out = CH.explain(conn, "SalesOrder", "SO-8", AS_OF)
    assert [(s["from"][1], s["to"][1] if s["to"] else None, s["relation"]) for s in out["causes"]] == [
        ("SO-8", "WIDGET-A", "waits for"), ("WIDGET-A", "PO-3", "expected from"),
        ("PO-3", "Gulf Fasteners", "ordered from")]
    why = [s["why"] for s in out["causes"]]
    assert why[0] == "WIDGET-A is short by 50: 50 on hand, open orders need 100."
    assert why[1] == "PO-3: 60 still to receive, 2 days past its required-by date 2026-10-10."
    assert why[2] == "Gulf Fasteners delivered 1 of 3 receipt lines on time in 90 days (33.3%)."
    assert [(s["to"][0], s["to"][1]) for s in out["impact"]] == [("Customer", "Bayside Hardware")]


def test_rejected_inspection_cause_and_impact(world):
    conn, _, _ = world
    out = CH.explain(conn, "QualityInspection", "QI-1", AS_OF)
    assert [s["to"][1] for s in out["causes"]] == ["PR-2", "Gulf Fasteners"]
    assert [(s["to"][0], s["to"][1]) for s in out["impact"]] == [
        ("Item", "BOLT-B"), ("SalesOrder", "SO-5"), ("Customer", "Bayside Hardware"),
        ("SalesOrder", "SO-6"), ("Customer", "Bayside Hardware")]
    nosupply = CH.explain(conn, "Item", "BOLT-B", AS_OF)["causes"]
    assert nosupply == [{"from": ["Item", "BOLT-B"], "to": None, "relation": "no supply",
                         "why": "No open purchase order brings more BOLT-B.", "depth": 1, "evidence": {}}]


def test_supplier_impact(world):
    conn, _, _ = world
    out = CH.explain(conn, "Supplier", "Gulf Fasteners", AS_OF)
    assert [(s["to"][0], s["to"][1]) for s in out["impact"]][:3] == [
        ("PurchaseOrder", "PO-3"), ("Item", "WIDGET-A"), ("SalesOrder", "SO-5")]


def test_anomaly_api_by_role(db_url):
    f = business()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for email in ("dana@demo.example", "alex@demo.example", "jordan@demo.example"):
            Acc.set_password(conn, email, "Demo pass 2026")
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
        AN.detect(conn, AS_OF)

    def login(email):
        c.post("/api/login", json={"email": email, "password": "Demo pass 2026"})

    login("alex@demo.example")    # sales: orders and items, not purchasing or quality
    rules = {a["rule"] for a in c.get("/api/anomalies").json()}
    assert rules == {"order_late", "order_at_risk", "item_short"}
    late = next(a for a in c.get("/api/anomalies").json() if a["rule"] == "order_late")
    detail = c.get(f"/api/anomalies/{late['id']}").json()
    assert [s["to"][1] for s in detail["explain"]["causes"]] == ["WIDGET-A"]   # purchase order and supplier hidden
    assert detail["hint"] and detail["log"][0]["action"] == "opened"
    po = next(r["id"] for r in DB.connect(db_url).execute("select id from anomalies where rule = 'po_late'"))
    assert c.get(f"/api/anomalies/{po}").status_code == 403
    assert c.get("/api/explain/PurchaseOrder/PO-3").status_code == 403
    r = c.post(f"/api/anomalies/{late['id']}/status", json={"status": "ack", "note": "looking"})
    assert r.status_code == 200 and r.json()["status"] == "ack"
    assert c.post(f"/api/anomalies/{late['id']}/status", json={"status": "open"}).status_code == 409

    login("jordan@demo.example")  # quality also sees purchasing (supplier quality), not sales
    assert {a["rule"] for a in c.get("/api/anomalies").json()} == {"inspection_rejected", "item_short", "po_late",
                                                                   "supplier_on_time_low"}
    login("dana@demo.example")
    assert len(c.get("/api/anomalies").json()) == 7
    assert len(c.get("/api/anomalies/rules").json()) == 6
    item = c.get("/api/ont/objects/Item/WIDGET-A").json()
    assert {a["rule"] for a in item["anomalies"]} == {"item_short", "po_late"}   # subject, and related to PO-3
    full = c.get("/api/explain/SalesOrder/SO-8").json()
    assert [s["to"][1] for s in full["causes"]] == ["WIDGET-A", "PO-3", "Gulf Fasteners"]
    c.__exit__(None, None, None)


def test_rule_catalog_is_complete():
    rules = AN.load_rules()
    assert set(rules) == set(AN.DETECTORS)
