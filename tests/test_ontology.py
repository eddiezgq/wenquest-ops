"""Ops hub ontology and objects (ADR-0007, step 6a). All business data here is fictional."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fake_erp import FakeErp
from tests.test_sync_replay import REC, Replay
from wqops import company as C
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.ont import schema as S

DEMO = C.load(C.DEMO_FILE)


def test_ontology_loads_and_is_english():
    o = S.load()
    assert [d["domain"] for d in o.domains] == ["customer", "sales", "product", "supply", "warehouse", "quality",
                                                "people", "finance"]
    assert all(t["label"].isascii() and t["source"].isascii() for t in o.types.values())
    for doctype, (type_, _) in OP.MAPPERS.items():
        assert o.types[type_]["maturity"] == "have", doctype
    assert {t for t, s in o.types.items() if s["maturity"] == "erp"} == {"SalesInvoice", "PurchaseInvoice"}


@pytest.mark.parametrize(("text", "msg"), [
    ("domain: x\norder: 1\nlabel: X\nview: nope\ntypes: {}\n", "view must be a permission"),
    ("domain: x\norder: 1\nlabel: X\nview: sales:view\ntypes:\n  bad_name: {}\n", "UpperCamelCase"),
    ("domain: x\norder: 1\nlabel: X\nview: sales:view\ntypes:\n  A: {label: A, maturity: have, source: s, key: k,"
     " props: {p: {t: text, l: P}}}\n", "a property needs t"),
    ("domain: x\norder: 1\nlabel: X\nview: sales:view\ntypes:\n  A: {label: A, maturity: have, source: s, key: k,"
     " title: '{nope}'}\n", "unknown property nope"),
    ("domain: x\norder: 1\nlabel: X\nview: sales:view\ntypes:\n  A: {label: A, maturity: have, source: s, key: k,"
     " links: {b: {to: B, l: B, inv: A}}}\n", "not an object type"),
    ("domain: x\norder: 1\nlabel: X\nview: sales:view\ntypes:\n  A: {label: A, maturity: soon, source: s, key: k}\n",
     "maturity"),
])
def test_ontology_errors(tmp_path, text, msg):
    (tmp_path / "x.yaml").write_text(text)
    with pytest.raises(S.OntologyError, match=msg):
        S.load(tmp_path)


@pytest.fixture
def fake():
    """A small fictional business."""
    f = FakeErp()
    f.put("Warehouse", "Main Stock - HLS", warehouse_name="Main Stock")
    f.put("Warehouse", "QC Hold - HLS", warehouse_name="QC Hold")
    f.put("Item", "WIDGET-01", item_name="Widget", stock_uom="Nos", is_stock_item=1)
    f.put("Customer", "Bayside Hardware", customer_name="Bayside Hardware")
    f.put("Supplier", "Gulf Fasteners", supplier_name="Gulf Fasteners")
    f.put("Stock Ledger Entry", "SLE-1", item_code="WIDGET-01", warehouse="Main Stock - HLS", actual_qty=100,
          stock_value_difference=250.0, voucher_type="Purchase Receipt", voucher_no="PR-1", is_cancelled=0, docstatus=1)
    f.put("Stock Ledger Entry", "SLE-2", item_code="WIDGET-01", warehouse="Main Stock - HLS", actual_qty=-30,
          stock_value_difference=-75.0, voucher_type="Delivery Note", voucher_no="DN-1", is_cancelled=0, docstatus=1)
    f.put("Stock Ledger Entry", "SLE-3", item_code="WIDGET-01", warehouse="QC Hold - HLS", actual_qty=5,
          stock_value_difference=12.5, voucher_type="Stock Entry", voucher_no="STE-1", is_cancelled=0, docstatus=1)
    f.put("Sales Order", "SO-1", customer="Bayside Hardware", customer_name="Bayside Hardware", docstatus=1,
          delivery_date="2026-10-01", status="To Deliver", grand_total=900.0, per_delivered=50,
          items=[{"item_code": "WIDGET-01", "qty": 60, "delivered_qty": 30, "rate": 15}])
    f.put("Delivery Note", "DN-1", customer="Bayside Hardware", customer_name="Bayside Hardware", docstatus=1,
          posting_date="2026-10-02", items=[{"item_code": "WIDGET-01", "qty": 30, "against_sales_order": "SO-1"}])
    f.put("Purchase Order", "PO-1", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners", docstatus=1,
          schedule_date="2026-09-20", items=[{"item_code": "WIDGET-01", "qty": 100, "received_qty": 100}])
    f.put("Purchase Receipt", "PR-1", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners", docstatus=1,
          posting_date="2026-09-22", items=[{"item_code": "WIDGET-01", "qty": 100, "purchase_order": "PO-1"}])
    f.put("Quality Inspection", "QI-1", item_code="WIDGET-01", reference_type="Purchase Receipt",
          reference_name="PR-1", status="Rejected", inspection_type="Incoming", docstatus=1, report_date="2026-09-22")
    return f


@pytest.fixture
def erp(fake):
    return ErpClient("http://erp", transport=fake.transport())


def obj(conn, t, k):
    return conn.execute("select * from ont_objects where type = %s and key = %s", (t, k)).fetchone()


def links(conn, t, k):
    return sorted((r["type"], r["dst_type"], r["dst_key"]) for r in conn.execute(
        "select * from ont_links where src_type = %s and src_key = %s", (t, k)).fetchall())


def test_objects_links_and_stock(conn, erp, fake):
    Acc.sync(conn, DEMO)
    Y.run(conn, erp)
    out = OP.project(conn, manifest=DEMO)
    assert out["events"] == 13
    so = obj(conn, "SalesOrder", "SO-1")
    assert so["title"] == "SO-1 Bayside Hardware" and so["props"]["lines"][0] == \
        {"item_code": "WIDGET-01", "qty": 60.0, "delivered_qty": 30.0, "rate": 15.0}
    assert links(conn, "DeliveryNote", "DN-1") == [
        ("customer", "Customer", "Bayside Hardware"), ("items", "Item", "WIDGET-01"),
        ("sales_orders", "SalesOrder", "SO-1")]
    assert links(conn, "QualityInspection", "QI-1") == [("item", "Item", "WIDGET-01"),
                                                        ("purchase_receipt", "PurchaseReceipt", "PR-1")]
    main = obj(conn, "StockLevel", "WIDGET-01@Main Stock - HLS")["props"]
    assert main == {"item": "WIDGET-01", "warehouse": "Main Stock - HLS", "actual_qty": 70.0, "stock_value": 175.0}
    assert obj(conn, "Warehouse", "QC Hold - HLS")["props"]["kind"] == "quarantine"
    assert obj(conn, "Person", "dana@demo.example")["props"]["roles"] == ["owner"]
    assert links(conn, "Person", "lee@demo.example") == [("department", "Department", "operations")]
    assert "sales_order" not in obj(conn, "Item", "WIDGET-01")["props"]   # nothing invented

    # a cancelled movement stops counting; a deleted customer is marked, with history
    fake.put("Stock Ledger Entry", "SLE-2", is_cancelled=1)
    fake.put("Sales Order", "SO-1", delivery_date="2026-10-05")
    fake.delete("Customer", "Bayside Hardware")
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    assert obj(conn, "StockLevel", "WIDGET-01@Main Stock - HLS")["props"]["actual_qty"] == 100.0
    assert obj(conn, "Customer", "Bayside Hardware")["deleted"]
    hist = conn.execute("select kind, changes from ont_history where type = 'SalesOrder' order by id").fetchall()
    assert [h["kind"] for h in hist] == ["created", "updated"]
    assert hist[1]["changes"] == {"delivery_date": {"from": "2026-10-01", "to": "2026-10-05"}}


def _snapshot(conn):
    """Live objects and links (a stock level that came and went within one batch never existed)."""
    return (sorted((r["type"], r["key"], r["title"], json.dumps(r["props"], sort_keys=True))
                   for r in conn.execute("select * from ont_objects where not deleted").fetchall()),
            sorted(tuple(r.values()) for r in conn.execute("select * from ont_links").fetchall()))


def test_rebuild_matches_incremental(conn, erp, fake):
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO, batch=3)
    fake.put("Item", "WIDGET-01", item_name="Widget, blue")
    fake.delete("Stock Ledger Entry", "SLE-3")
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO, batch=3)
    before = _snapshot(conn)
    assert OP.project(conn, manifest=DEMO, rebuild=True)["events"] > 0
    assert _snapshot(conn) == before
    gone = obj(conn, "StockLevel", "WIDGET-01@QC Hold - HLS")
    assert gone is None or gone["deleted"]


def test_real_erpnext_documents_become_objects(conn):
    """The replies recorded from a real ERPNext map without errors and give the expected objects."""
    summary = json.loads((REC / "summary.json").read_text(encoding="utf-8"))
    for n in (1, 2, 3):
        Y.run(conn, ErpClient("http://erp-frontend:8080", transport=Replay(REC / str(n))), page=summary["page"])
    OP.project(conn, manifest=DEMO)
    level = obj(conn, "StockLevel", "CI-WIDGET-01@Main Stock - HLS")["props"]
    assert level["actual_qty"] == 10.0 and level["stock_value"] == 25.0
    po = conn.execute("select key, props from ont_objects where type = 'PurchaseOrder'").fetchone()
    assert po["props"]["docstatus"] == 1 and po["props"]["lines"][0]["item_code"] == "CI-WIDGET-01"
    assert ("supplier", "Supplier", "CI Gulf Fasteners (Demo)") in links(conn, "PurchaseOrder", po["key"])
    assert obj(conn, "Customer", "CI Short-lived Customer (Demo)")["deleted"]
    assert obj(conn, "Warehouse", "Main Stock - HLS")["props"]["kind"] == "stores"


def test_object_api_and_permissions(db_url, fake):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=fake.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for email in ("dana@demo.example", "alex@demo.example", "lee@demo.example"):
            Acc.set_password(conn, email, "Demo pass 2026")
        Y.run(conn, ErpClient("http://erp", transport=fake.transport()))
        OP.project(conn, manifest=DEMO)
    assert c.get("/api/ont/schema").status_code == 401

    def login(email):
        c.post("/api/login", json={"email": email, "password": "Demo pass 2026"})

    login("alex@demo.example")                                       # sales
    domains = [d["domain"] for d in c.get("/api/ont/schema").json()]
    assert domains == ["customer", "sales", "product", "warehouse", "people"]
    assert c.get("/api/ont/objects/PurchaseOrder/PO-1").status_code == 403
    assert c.get("/api/ont/objects/Nope/x").status_code == 404
    so = c.get("/api/ont/objects/SalesOrder/SO-1").json()
    assert {p["name"]: p["value"] for p in so["props"]}["grand_total"] == 900.0
    rel = {(g["direction"], g["label"]): [o["key"] for o in g["objects"]] for g in so["relations"]}
    assert rel == {("out", "Customer"): ["Bayside Hardware"], ("out", "Items"): ["WIDGET-01"],
                   ("in", "Deliveries"): ["DN-1"]}
    item = c.get("/api/ont/objects/Item/WIDGET-01").json()
    assert not any(g["type"] in ("PurchaseOrder", "QualityInspection") for g in item["relations"])  # not for sales
    assert [o["key"] for o in c.get("/api/ont/search", params={"q": "bayside"}).json()] == \
        ["Bayside Hardware", "DN-1", "SO-1"]
    assert c.get("/api/ont/search", params={"q": "gulf"}).json() == []  # suppliers are purchasing's
    assert [o["key"] for o in c.get("/api/ont/search", params={"q": "widget-01", "type": "SalesOrder"}).json()] == \
        ["SO-1"]
    login("dana@demo.example")
    assert {o["key"] for o in c.get("/api/ont/search", params={"q": "gulf"}).json()} == {"Gulf Fasteners", "PO-1",
                                                                                      "PR-1"}
    g = c.get("/api/ont/graph/QualityInspection/QI-1", params={"depth": 2}).json()
    keys = {n["key"] for n in g["nodes"]}
    assert {"QI-1", "PR-1", "WIDGET-01", "Gulf Fasteners", "PO-1", "SO-1"} <= keys
    assert {"from": ["QualityInspection", "QI-1"], "link": "purchase_receipt", "label": "Receipt",
            "to": ["PurchaseReceipt", "PR-1"]} in g["edges"]
    lst = c.get("/api/ont/objects/StockLevel").json()
    assert lst["total"] == 2 and lst["objects"][0]["key"] == "WIDGET-01@Main Stock - HLS"
    hist = c.get("/api/ont/objects/SalesOrder/SO-1").json()["history"]
    assert hist[0]["kind"] == "created" and hist[0]["event_id"]
    c.__exit__(None, None, None)


def test_people_without_manifest_is_harmless(conn):
    assert OP.project(conn) == {"events": 0, "objects": 0, "last_event": 0}
    assert Path(S.DIR / "README.md").is_file()
