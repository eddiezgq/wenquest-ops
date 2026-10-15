"""The approved supplier list, step 17c (ADR-0017; dee-qms PLAN-ASL): which supplier may deliver which item, the
judgement incoming inspection uses (blocked, flagged or ok), approvals signed by someone else and kept, the ISO 9001
supplier register brought in once, the ISO supplier check reading the list, and purchase order drafts that say when
a supplier is not approved. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import CHARS, DANA, JORDAN, PW, receipts, table
from tests.test_metrics import AS_OF, DEMO
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import approval as AP
from wqops.hub.quality import asl as A
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS
from wqops.hub.system import registers as RG

T = AS_OF


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, DANA):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=receipts(business()).transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, email):
    return Acc.get(conn, email)


def e(sid, status, item=None, **kw):
    return {"id": sid, "supplier": "Gulf Fasteners", "item_code": item, "status": status} | kw


def test_standing():
    assert AP.standing([], "Gulf Fasteners", "BOLT-B", T)["why"] == ("Gulf Fasteners for BOLT-B is not on the approved "
                                                                    "supplier list")
    assert AP.standing([e(1, "approved")], None, "BOLT-B", T)["outcome"] == "block"
    for st in ("draft", "suspended", "disqualified"):
        assert AP.standing([e(1, st)], "Gulf Fasteners", "BOLT-B", T)["outcome"] == "block"
    assert AP.standing([e(1, "approved")], "Gulf Fasteners", "BOLT-B", T)["outcome"] == "ok"
    # the item's own entry counts before the one for all items
    both = [e(1, "approved"), e(2, "suspended", "BOLT-B")]
    assert AP.standing(both, "Gulf Fasteners", "BOLT-B", T)["outcome"] == "block"
    assert AP.standing(both, "Gulf Fasteners", "WIDGET-A", T)["outcome"] == "ok"
    # but a supplier suspended for all its items is blocked for every item
    held = [e(1, "suspended"), e(2, "approved", "BOLT-B")]
    assert AP.standing(held, "Gulf Fasteners", "BOLT-B", T)["why"] == ("Gulf Fasteners (all items) is suspended on the "
                                                                      "approved supplier list")
    s = AP.standing([e(1, "conditional", condition="100% inspection of the first 3 lots")], "Gulf Fasteners", "X", T)
    assert s == {"outcome": "flag", "why": "conditional supplier: 100% inspection of the first 3 lots",
                 "entry": s["entry"]}
    late = e(1, "approved", review_due=T - dt.timedelta(days=1))
    why = AP.standing([late], "Gulf Fasteners", "X", T)["why"]
    assert why == f"supplier re-evaluation was due on {late['review_due']}"
    assert AP.review_state(late, T) == "overdue"
    assert AP.review_state(e(1, "approved", review_due=T + dt.timedelta(days=20)), T) == "soon"
    assert AP.review_state(e(1, "suspended", review_due=T - dt.timedelta(days=9)), T) is None


def test_approvals_signed_and_kept(world):
    with pytest.raises(A.AslError, match="choose a supplier ERPNext knows"):
        A.add(world, JORDAN, "Nobody Inc", None, {})
    x = A.add(world, JORDAN, "Gulf Fasteners", "BOLT-B", {"risk": "high"})
    with pytest.raises(A.AslError, match="already has an entry for BOLT-B"):
        A.add(world, JORDAN, "Gulf Fasteners", "BOLT-B", {})
    with pytest.raises(PermissionError, match="someone other than the person who entered"):
        A.approve(world, u(world, JORDAN), x["id"], PW, reason="ok", today=T)
    with pytest.raises(A.AslError, match="say what the approval rests on"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="ok", today=T)
    with pytest.raises(A.AslError, match="give the reason"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="", today=T, basis="Audit 2026-09")
    with pytest.raises(A.AslError, match="when the supplier is re-evaluated next"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="ok", today=T, basis="Audit 2026-09")
    with pytest.raises(Q.SignatureError):
        A.approve(world, u(world, DANA), x["id"], "wrong", reason="ok", today=T, basis="Audit 2026-09",
                  review_due="2027-09-30")
    ok = A.approve(world, u(world, DANA), x["id"], PW, reason="Audit passed", today=T, basis="Audit 2026-09",
                   review_due="2027-09-30")
    assert (ok["status"], ok["approved_by"]) == ("approved", DANA)
    # approved content changes only by re-evaluation, signed
    with pytest.raises(A.AslError, match="re-evaluate it, or suspend it"):
        A.change(world, JORDAN, x["id"], {"basis": "x"})
    with pytest.raises(psycopg.errors.RaiseException, match="re-evaluate it"):
        world.execute("update asl_entries set basis = 'x' where id = %s", (x["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="only with the approver's signature"):
        world.execute("update asl_entries set approved_by = %s, approved_at = now() + interval '1 second' "
                      "where id = %s", (JORDAN, x["id"]))
    with pytest.raises(psycopg.errors.RaiseException, match="is a draft"):
        world.execute("insert into asl_entries (supplier, status, basis, created_by, approved_by, approved_at) "
                      "values ('Acme Cable', 'approved', 'x', 'x', 'x', now())")
    with pytest.raises(A.AslError, match="re-evaluated next, after today"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="yearly", today=T, review_due=str(T))
    again = A.approve(world, u(world, DANA), x["id"], PW, reason="yearly", today=T, review_due="2028-09-30",
                      condition="Certificate of conformity with every lot")
    assert again["status"] == "conditional" and str(again["review_due"]) == "2028-09-30"
    A.move(world, DANA, x["id"], "suspended", "late certificates")
    A.change(world, DANA, x["id"], {"condition": ""})
    # Dana changed it, so Dana does not approve it again
    with pytest.raises(PermissionError, match="entered or changed"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="x", today=T, review_due="2028-01-31")
    A.move(world, DANA, x["id"], "disqualified", "lost its certification")
    with pytest.raises(A.AslError, match="qualified again first"):
        A.approve(world, u(world, DANA), x["id"], PW, reason="x", today=T)
    assert A.move(world, DANA, x["id"], "draft", "certified again")["status"] == "draft"
    assert [h["action"] for h in A.history(world, x["id"])] == [
        "entered", "approved", "re-evaluated with conditions", "suspended", "changed", "disqualified",
        "qualified again"]
    assert [s["meaning"] for s in Q.signatures(world, "asl", x["id"])] == ["Supplier approved",
                                                                           "Supplier re-evaluated with conditions"]
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from asl_entries")
    with pytest.raises(psycopg.errors.RaiseException, match="cannot go from draft to suspended"):
        world.execute("update asl_entries set status = 'suspended' where id = %s", (x["id"],))


def test_incoming_inspection_reads_the_list(world):
    table(world)
    p = I.new_plan(world, JORDAN, "BOLT-B", 1.0, CHARS)
    I.enable_plan(world, u(world, DANA), p["id"], PW)
    # an empty list is not in use yet; once it has an entry, a supplier not on it is blocked
    first = I.start(world, JORDAN, "BOLT-B", receipt="PR-9", today=T)
    assert first["supplier_standing"] is None
    A.add(world, JORDAN, "Acme Cable", None, {})
    with pytest.raises(I.IqcError, match="Gulf Fasteners for BOLT-B is not on the approved supplier list"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-7", today=T)
    x = A.add(world, JORDAN, "Gulf Fasteners", None, {"basis": "Certificate"})
    with pytest.raises(I.IqcError, match="is draft on the approved supplier list"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-7", today=T)
    A.approve(world, u(world, DANA), x["id"], PW, reason="ok", today=T, condition="First lots 100% inspected",
              review_due="2027-01-31")
    ins = I.start(world, JORDAN, "BOLT-B", receipt="PR-7", today=T)
    assert ins["supplier_standing"] == "conditional supplier: First lots 100% inspected"
    assert "conditional supplier" in I.history(world, "inspection", ins["id"])[0]["note"]
    A.move(world, DANA, x["id"], "suspended", "audit finding")
    with pytest.raises(I.IqcError, match="suspended"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-8", today=T)
    # the company's choice: switched off, the list is not consulted
    I.set_setting(world, DANA, "asl_enforced", False)
    assert I.start(world, JORDAN, "BOLT-B", receipt="PR-8", today=T)["supplier_standing"] is None


def test_register_brought_in_and_read_by_the_iso_check(world):
    QMS.enable(world, u(world, JORDAN), "iso9001", "2015", PW, T)
    RG.create(world, DANA, "suppliers", {"supplier": "Gulf Fasteners", "status": "approved",
                                         "approved_on": "2026-03-01", "next_review": "2027-03-01",
                                         "basis": "ISO 9001 certificate"})
    RG.create(world, DANA, "suppliers", {"supplier": "acme cable", "status": "removed", "approved_on": "2026-05-01"})
    RG.create(world, DANA, "suppliers", {"supplier": "Nobody Inc", "status": "approved", "approved_on": "2026-05-01"})
    RG.create(world, DANA, "suppliers", {"supplier": "Gulf Fasteners", "status": "conditional",
                                         "approved_on": "2025-01-01"})                 # older: the latest counts
    assert A.from_register(world, DANA) == {"brought_in": 2, "skipped": 1}
    rows = {r["supplier"]: r for r in A.listing(world, T)}
    assert set(rows) == {"Gulf Fasteners", "Acme Cable"}
    g = rows["Gulf Fasteners"]
    # brought in as a draft for someone else to approve
    assert (g["status"], g["review_due"], g["approved_by"]) == ("draft", "2027-03-01", None)
    assert g["basis"] == "ISO 9001 certificate Approved or evaluated on 2026-03-01." and g["source"].startswith(
        "supplier register entry #")
    assert rows["Acme Cable"]["status"] == "disqualified"
    with pytest.raises(A.AslError, match="nothing to bring in"):
        A.from_register(world, DANA)
    with pytest.raises(PermissionError):
        A.approve(world, u(world, DANA), g["id"], PW, reason="as in the register", today=T)
    A.approve(world, u(world, JORDAN), g["id"], PW, reason="as in the register", today=T)
    # the ISO supplier check now reads the list: Acme Cable was bought from but is disqualified
    QMS.evaluate(world, "iso9001", T, "manual", JORDAN)
    r = QMS.latest(world, "iso9001")["results"]["supplier_approval"]
    assert r["status"] == "not_met" and "(approved supplier list)" in r["detail"]
    assert [(p["label"], p["why"]) for p in r["problems"]] == [
        ("Acme Cable", "bought from but Acme Cable (all items) is disqualified on the approved supplier list")]
    # an approval for one item does not cover the supplier's other items
    world.execute("update asl_entries set status = 'draft' where supplier = 'Acme Cable'")
    a2 = A.add(world, JORDAN, "Acme Cable", "WIDGET-A", {"basis": "sample lots"})
    A.approve(world, u(world, DANA), a2["id"], PW, reason="ok", today=T, review_due="2027-06-30")
    QMS.evaluate(world, "iso9001", T, "manual", JORDAN)
    r = QMS.latest(world, "iso9001")["results"]["supplier_approval"]
    assert r["status"] == "not_met" and r["problems"][0]["why"].startswith("bought from but Acme Cable for ")


def test_asl_api_and_purchase_drafts(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for em in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, em, PW)
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)

    def login(em):
        assert c.post("/api/login", json={"email": em, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.get("/api/asl").json()["can_configure"] is False
    assert c.post("/api/asl", json={"supplier": "Gulf Fasteners"}).status_code == 403
    login(JORDAN)
    v = c.post("/api/asl", json={"supplier": "Gulf Fasteners", "basis": "Certificate"}).json()
    eid = v["entries"][0]["id"]
    assert c.post(f"/api/asl/{eid}/approve", json={"password": PW, "reason": "ok",
                                                   "review_due": "2027-09-30"}).status_code == 403
    login(DANA)
    v = c.post(f"/api/asl/{eid}/approve", json={"password": PW, "reason": "ok", "review_due": "2027-09-30"}).json()
    assert v["entries"][0]["status"] == "approved"
    assert c.post(f"/api/asl/{eid}/explode", json={}).status_code == 404
    assert c.get(f"/api/asl/{eid}/history").json()["signatures"][0]["meaning"] == "Supplier approved"
    # a purchase order draft for a supplier not on the list says so
    with DB.connect(db_url) as conn:
        D.propose(conn, {"email": DANA, "roles": ["owner"]}, "Purchase Order",
                  {"supplier": "Acme Cable", "items": [{"item_code": "BOLT-B", "qty": 5}]})
        D.propose(conn, {"email": DANA, "roles": ["owner"]}, "Purchase Order",
                  {"supplier": "Gulf Fasteners", "items": [{"item_code": "BOLT-B", "qty": 5}]})
    drafts = {d["payload"]["supplier"]: d for d in c.get("/api/erp/drafts").json() if d["doctype"] == "Purchase Order"}
    assert drafts["Acme Cable"]["asl"] == [{"item_code": "BOLT-B", "outcome": "block",
                                            "why": "Acme Cable for BOLT-B is not on the approved supplier list"}]
    assert drafts["Gulf Fasteners"]["asl"] == []
    c.__exit__(None, None, None)
