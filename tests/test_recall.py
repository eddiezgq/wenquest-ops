"""Traceability and recalls, step 17i (ADR-0017; dee-qms PLAN-TRACE, PLAN-SHIP, PLAN-RECALL): forward from an
incoming lot and backward from a production lot or a complaint, deliveries read from ERPNext delivery notes (same
batch, or the item with no batch), a recall opened by its owner or Quality with the consignee list fixed, contact
recorded within its limits, effectiveness counted, closed with a signature by someone not involved, the CSV, the
API. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, receipts
from tests.test_production import LEE, SAM, active_template, bolt_lot
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import complaints as CMP
from wqops.hub.quality import production as PRD
from wqops.hub.quality import recall as RC
from wqops.hub.quality import records as Q
from wqops.hub.quality import trace as TRC
from wqops.hub.quality import trace_rules as TR

T = AS_OF


def erp():
    f = receipts(business())
    f.put("Customer", "Harbor Vet Clinic", customer_name="Harbor Vet Clinic (Demo)")

    def dn(name, date, lines, customer="Bayside Hardware", **kw):
        f.put("Delivery Note", name, customer=customer, customer_name=customer, posting_date=date, docstatus=1,
              items=lines, **kw)

    dn("DN-L1", "2026-10-10", [{"item_code": "WIDGET-A", "qty": 4, "batch_no": "L-001"}])
    dn("DN-L2", "2026-10-11", [{"item_code": "WIDGET-A", "qty": 3, "batch_no": "L-002"}])          # another lot
    # no batch number: may hold a lot made before it was delivered (the date is after the lots start in the tests)
    dn("DN-NB", "2099-01-05", [{"item_code": "WIDGET-A", "qty": 2}], customer="Harbor Vet Clinic")
    dn("DN-OLD", "2026-01-05", [{"item_code": "WIDGET-A", "qty": 7}])   # before the lots: cannot hold them
    dn("DN-RET", "2026-10-13", [{"item_code": "WIDGET-A", "qty": -1, "batch_no": "L-001"}], is_return=1)
    return f


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA, LEE):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=erp().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def released(conn, lot_no, ins_id, qty=10):
    t = conn.execute("select id from prod_templates where status = 'active'").fetchone()
    rid = PRD.start(conn, JORDAN, {"template_id": t["id"], "lot_no": lot_no, "planned_qty": qty})["id"]
    PRD.record_step(conn, u(conn, JORDAN), rid, 1, PW, {"result": "pass"}, today=T)
    PRD.record_step(conn, u(conn, JORDAN), rid, 2, PW, {"value": 10}, today=T)
    PRD.record_step(conn, u(conn, JORDAN), rid, 3, PW, {"text": "ok"}, today=T)
    PRD.add_material(conn, JORDAN, rid, ins_id, 20)
    PRD.set_quantities(conn, JORDAN, rid, {"good_qty": qty})
    PRD.submit(conn, JORDAN, rid)
    return PRD.decide(conn, u(conn, DANA), rid, PW, True)


def test_rules():
    notes = [{"key": "A", "customer": "C", "props": {"docstatus": 1, "posting_date": "2026-10-01", "lines": [
        {"item_code": "W", "qty": 2, "batch_no": " l-1"}, {"item_code": "W", "qty": 1, "batch_no": "L-2"},
        {"item_code": "W", "qty": 5}, {"item_code": "X", "qty": 1}]}},
             {"key": "B", "props": {"docstatus": 2, "lines": [{"item_code": "W", "qty": 9}]}}]
    got = TR.deliveries(notes, "W", "L-1 ")
    assert [(x["delivery_note"], x["qty"], x["batch_match"]) for x in got] == [("A", 2, "batch"), ("A", 5, "item only")]
    rows = [{"delivery_note": "A", "qty": 4, "notified_on": "x", "confirmed_on": "y", "returned_qty": 3},
            {"delivery_note": "B", "qty": 4, "notified_on": None, "confirmed_on": None}]
    assert TR.effectiveness(rows) == {"consignees": 2, "notified": 0.5, "confirmed": 0.5, "recovered": 0.375,
                                      "shipped_qty": 8.0, "recovered_qty": 3.0}
    assert TR.to_close({"effectiveness": "ok"}, rows)[0].startswith("every consignee notified")
    assert TR.to_open({"scope": [1], "reason": "x", "classification": "class II"}, 0) == [
        "nothing was delivered: say in the strategy what happens to the stock"]
    assert TR.csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and TR.csv_cell("Bayside") == "Bayside"


def test_trace_and_recall(world):
    lot = bolt_lot(world)
    active_template(world)
    r1 = released(world, "L-001", lot["id"])
    r2 = released(world, "L-002", lot["id"])
    # forward from the incoming lot: both lots, their deliveries, the customers
    fw = TRC.from_incoming(world, lot["id"])
    assert [x["lot_no"] for x in fw["lots"]] == ["L-001", "L-002"] and fw["start"]["used_qty"] == 40.0
    assert [(s["delivery_note"], s["batch_match"], s["lot_no"]) for s in fw["shipments"]] == [
        ("DN-L1", "batch", "L-001"), ("DN-L2", "batch", "L-002"), ("DN-NB", "item only", "L-001, L-002")]
    assert fw["customers"] == ["Bayside Hardware", "Harbor Vet Clinic"]
    # backward from a lot
    bw = TRC.from_record(world, r1["id"])
    assert bw["suppliers"] == ["Gulf Fasteners"] and [s["lot_no"] for s in bw["siblings"]] == ["L-002"]
    assert [s["delivery_note"] for s in bw["shipments"]] == ["DN-L1", "DN-NB"]
    # from a complaint naming the lot (case and spaces do not matter)
    cmp = CMP.create(world, JORDAN, {"received_on": str(T), "customer": "Bayside Hardware", "item_code": "WIDGET-A",
                                     "lot_no": " l-001", "description": "Shaft loose"}, today=T)
    assert TRC.from_complaint(world, cmp["id"])["lots"][0]["name"] == r1["name"]
    assert [c["name"] for c in TRC.from_record(world, r1["id"])["complaints"]] == [cmp["name"]]
    other = CMP.create(world, JORDAN, {"received_on": str(T), "customer": "x", "description": "y"}, today=T)
    assert "does not name both" in TRC.from_complaint(world, other["id"])["note"]

    # the recall
    rc = RC.create(world, JORDAN, {"title": "Loose shafts", "scope": [r1["id"]], "owner": LEE})
    with pytest.raises(RC.RecallError, match="the reason"):
        RC.open_recall(world, u(world, LEE), rc["id"], today=T)
    RC.update(world, u(world, JORDAN), rc["id"], {"reason": "Shaft can loosen", "classification": "class II"})
    with pytest.raises(PermissionError, match="the owner or Quality"):
        RC.open_recall(world, {"email": JORDAN, "roles": ["warehouse"]}, rc["id"], today=T)
    RC.open_recall(world, u(world, LEE), rc["id"], today=T)
    v = RC.view(world, rc["id"])
    assert [(x["delivery_note"], float(x["qty"])) for x in v["consignees"]] == [("DN-L1", 4.0), ("DN-NB", 2.0)]
    with pytest.raises(psycopg.errors.RaiseException, match="scope is fixed"):
        world.execute("update recalls set scope = '[]' where id = %s", (rc["id"],))
    assert PRD.view(world, r1["id"])["recalls"][0]["name"] == rc["name"]
    c1, c2 = v["consignees"]
    with pytest.raises(RC.RecallError, match="together"):
        RC.record_contact(world, JORDAN, c1["id"], {"notified_on": str(T)}, today=T)
    with pytest.raises(RC.RecallError, match="between the opening"):
        RC.record_contact(world, JORDAN, c1["id"], {"notified_on": "2020-01-01", "method": "phone"}, today=T)
    today = T
    RC.record_contact(world, JORDAN, c1["id"], {"notified_on": str(today), "method": "phone"}, today=today)
    with pytest.raises(RC.RecallError, match="at most the 4 delivered"):
        RC.record_contact(world, JORDAN, c1["id"], {"returned_qty": 3, "corrected_qty": 2}, today=today)
    RC.record_contact(world, JORDAN, c1["id"], {"confirmed_on": str(today), "returned_qty": 4}, today=today)
    with pytest.raises(RC.RecallError, match="the effectiveness conclusion"):
        RC.close(world, u(world, DANA), rc["id"], PW, today=T)
    RC.update(world, u(world, LEE), rc["id"], {"effectiveness": "All reached", "regulatory_decision": "Reported"})
    for who in (JORDAN, LEE):          # raised it; owns and opened it
        with pytest.raises(PermissionError, match="does not own it"):
            RC.close(world, u(world, who), rc["id"], PW, today=T)
    with pytest.raises(RC.RecallError, match=r"every consignee notified \(DN-NB\)"):
        RC.close(world, u(world, DANA), rc["id"], PW, today=T)
    RC.record_contact(world, JORDAN, c2["id"], {"notified_on": str(today), "method": "email"}, today=today)
    with pytest.raises(RC.RecallError, match="did not confirm"):
        RC.close(world, u(world, DANA), rc["id"], PW, today=T)
    RC.update(world, u(world, LEE), rc["id"], {"unconfirmed_note": "Clinic does not answer; letter sent"})
    with pytest.raises(Q.SignatureError):
        RC.close(world, u(world, DANA), rc["id"], "wrong", today=T)
    assert RC.close(world, u(world, DANA), rc["id"], PW, today=T)["status"] == "closed"
    v = RC.view(world, rc["id"])
    assert v["effectiveness_counts"]["recovered"] == round(4 / 6, 4)
    assert RC.csv_text(world, rc["id"]).splitlines()[1].startswith("DN-L1,2026-10-10,Bayside Hardware,WIDGET-A")
    with pytest.raises(psycopg.errors.RaiseException, match="closed"):
        world.execute("update recall_consignees set note = 'x' where recall_id = %s", (rc["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from recalls")
    assert RC.summary(world, dt.date(2000, 1, 1), dt.date(2999, 1, 1)) == {"open": 0, "closed": 1}
    # a draft is cancelled, not deleted
    d = RC.create(world, JORDAN, {"title": "Maybe", "scope": [r2["id"]]})
    assert RC.cancel(world, DANA, d["id"], "Not needed")["status"] == "cancelled"


def test_recall_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=erp().transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, JORDAN, LEE, SAM):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=erp().transport()))
        OP.project(conn, manifest=DEMO)
        lot = bolt_lot(conn)
        active_template(conn)
        r1 = released(conn, "L-001", lot["id"])

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(SAM)
    t = c.get(f"/api/trace?record={r1['id']}").json()
    assert t["customers"] == ["Bayside Hardware", "Harbor Vet Clinic"]
    assert c.get("/api/trace?record=999").status_code == 404
    rid = c.post("/api/recalls", json={"title": "Loose shafts", "scope": [r1["id"]], "reason": "x"}).json()["id"]
    assert c.post(f"/api/recalls/{rid}/open").status_code == 403          # not the owner, not Quality
    login(DANA)
    v = c.post(f"/api/recalls/{rid}/open").json()
    assert v["status"] == "open" and len(v["consignees"]) == 2
    r = c.get(f"/api/recalls/{rid}/consignees.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert c.post(f"/api/recalls/{rid}/explode").status_code == 404
    c.__exit__(None, None, None)


def test_review_fixes(world):
    notes = [{"key": "A", "props": {"docstatus": 1, "posting_date": "2026-10-01", "lines": [
        {"item_code": "W", "qty": 2, "serial_and_batch_bundle": "SABB-1"}]}}]
    assert TR.deliveries(notes, "W", "L-1")[0]["batch_match"] == "bundle"
    assert TR.deliveries(notes, "W", "L-1", since="2026-10-02") == []
    lot = bolt_lot(world)
    active_template(world)
    r1 = released(world, "L-001", lot["id"])
    rc = RC.create(world, JORDAN, {"title": "x", "scope": [r1["id"]], "owner": DANA, "reason": "y"})
    with pytest.raises(RC.RecallError, match="title"):
        RC.update(world, u(world, JORDAN), rc["id"], {"title": " "})
    with pytest.raises(psycopg.errors.RaiseException, match="taken when the recall opens"):
        world.execute("insert into recall_consignees (recall_id, delivery_note, item_code, lot_no, batch_match, qty) "
                      "values (%s, 'DN-X', 'WIDGET-A', 'L-001', 'batch', 1)", (rc["id"],))
    RC.open_recall(world, u(world, DANA), rc["id"], today=T)
    # Dana owned it; handing it to Lee does not let Dana close it
    RC.update(world, u(world, DANA), rc["id"], {"owner": LEE})
    for c in RC.consignees(world, rc["id"]):
        RC.record_contact(world, JORDAN, c["id"], {"notified_on": str(T), "method": "letter", "confirmed_on": str(T)},
                          today=T)
    RC.update(world, u(world, LEE), rc["id"], {"effectiveness": "Done", "regulatory_decision": "None needed"})
    with pytest.raises(PermissionError, match="does not own it"):
        RC.close(world, u(world, DANA), rc["id"], PW, today=T)
    with pytest.raises(psycopg.errors.RaiseException, match="keeps everyone who owned it"):
        world.execute("update recalls set owners = '{}' where id = %s", (rc["id"],))
    assert RC.close(world, u(world, SAM), rc["id"], PW, today=T)["closed_on"] == T
