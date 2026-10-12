"""Drafts for ERPNext (ADR-0006 item 5): proposed, confirmed by a person, created in ERPNext as a Draft only."""

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fake_erp import FakeErp
from wqops import company as C
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub.app import create_app

PO = {"supplier": "Gulf Fasteners", "schedule_date": "2026-10-20",
      "items": [{"item_code": "WIDGET-01", "qty": 50, "rate": 2.5, "warehouse": "Main Stock - HLS"}]}
PAT = {"email": "pat@demo.example", "roles": ["purchasing"]}
ALEX = {"email": "alex@demo.example", "roles": ["sales"]}
JORDAN = {"email": "jordan@demo.example", "roles": ["quality"]}


@pytest.fixture
def fake():
    return FakeErp()


@pytest.fixture
def erp(fake):
    return ErpClient("http://erp", transport=fake.transport())


def test_clean_rejects_what_a_draft_may_not_set():
    assert D.clean("Purchase Order", PO) == PO
    for bad, msg in [({**PO, "docstatus": 1}, "set by ERPNext"), ({**PO, "name": "PO-1"}, "set by ERPNext"),
                     ({**PO, "doctype": "Sales Invoice"}, "says doctype"),
                     ({"items": PO["items"]}, "missing: supplier"),
                     ({**PO, "items": [{"item_code": "X", "qty": 0}]}, "row 1"), ([1], "object"),
                     ({**PO, "items": "WIDGET"}, "list of rows")]:
        with pytest.raises(D.DraftError, match=msg):
            D.clean("Purchase Order", bad)
    with pytest.raises(D.DraftError, match="does not draft 'Sales Invoice'"):
        D.permission("Sales Invoice")


def test_propose_confirm_creates_an_erpnext_draft(conn, erp, fake):
    d = D.propose(conn, PAT, "Purchase Order", PO, summary="Restock widgets")
    assert d["status"] == "pending" and fake.requests == []      # nothing sent to ERPNext yet
    done = D.confirm(conn, PAT, d["id"], erp)
    assert done["status"] == "confirmed" and done["decided_by"] == "pat@demo.example"
    created = fake.docs["Purchase Order"][done["erp_name"]]
    assert created["docstatus"] == 0 and created["supplier"] == "Gulf Fasteners"
    with pytest.raises(D.Conflict, match="already confirmed"):
        D.confirm(conn, PAT, d["id"], erp)
    log = [r["action"] for r in conn.execute("select action from erp_draft_log order by id").fetchall()]
    assert log == ["proposed", "confirmed"]


def test_permissions_by_doctype(conn, erp):
    with pytest.raises(D.NotAllowed, match="Draft purchase orders"):
        D.propose(conn, ALEX, "Purchase Order", PO)
    with pytest.raises(D.NotAllowed):
        D.propose(conn, JORDAN, "Purchase Order", PO)
    qi = D.propose(conn, JORDAN, "Quality Inspection", {"inspection_type": "Incoming", "reference_type":
                   "Purchase Receipt", "reference_name": "MAT-PRE-0001", "item_code": "WIDGET-01"})
    with pytest.raises(D.NotAllowed):
        D.confirm(conn, PAT, qi["id"], erp)                     # purchasing cannot confirm a quality draft
    assert [x["doctype"] for x in D.visible(conn, JORDAN)] == ["Quality Inspection"]
    assert D.visible(conn, PAT) == []


def test_ai_drafts_wait_for_a_person(conn, erp, fake):
    d = D.propose(conn, PAT, "Purchase Order", PO, source="ai", ai_run="run-42")
    assert d["source"] == "ai" and d["ai_run"] == "run-42" and fake.requests == []
    assert D.confirm(conn, {"email": "sam@demo.example", "roles": ["ops_manager"]}, d["id"], erp)["status"] == \
        "confirmed"
    with pytest.raises(D.DraftError, match="source"):
        D.propose(conn, PAT, "Purchase Order", PO, source="robot")


def test_failed_confirmation_can_be_retried_or_rejected(conn, erp, fake):
    d = D.propose(conn, PAT, "Purchase Order", PO)
    fake.fail_after = 0
    with pytest.raises(httpx.ConnectError):
        D.confirm(conn, PAT, d["id"], erp)
    row = D.get(conn, d["id"])
    assert row["status"] == "failed" and "ConnectError" in row["error"]
    fake.fail_after = None
    assert D.confirm(conn, PAT, d["id"], erp)["status"] == "confirmed"
    other = D.propose(conn, PAT, "Purchase Order", PO)
    assert D.reject(conn, PAT, other["id"], "not needed")["status"] == "rejected"
    with pytest.raises(D.Conflict):
        D.reject(conn, PAT, other["id"])
    with pytest.raises(D.Conflict):
        D.confirm(conn, PAT, other["id"], erp)


def test_drafts_api(db_url, fake, monkeypatch):
    monkeypatch.setenv("WQO_ERP_PUBLIC_URL", "https://erp.ops.example.com")
    c = TestClient(create_app({}, lambda: (C.load(C.DEMO_FILE), "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=fake.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "pat@demo.example", "Buyer pass 2026")
        Acc.set_password(conn, "alex@demo.example", "Sales pass 2026")
    assert c.post("/api/erp/drafts", json={"doctype": "Purchase Order", "payload": PO}).status_code == 401
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Sales pass 2026"})
    assert c.post("/api/erp/drafts", json={"doctype": "Purchase Order", "payload": PO}).status_code == 403
    c.post("/api/login", json={"email": "pat@demo.example", "password": "Buyer pass 2026"})
    r = c.post("/api/erp/drafts", json={"doctype": "Purchase Order", "payload": {**PO, "docstatus": 1}})
    assert r.status_code == 400 and "set by ERPNext" in r.json()["detail"]
    r = c.post("/api/erp/drafts", json={"doctype": "Purchase Order", "payload": PO, "summary": "Restock"})
    assert r.status_code == 201
    did = r.json()["id"]
    assert [d["id"] for d in c.get("/api/erp/drafts?status=pending").json()] == [did]
    r = c.post(f"/api/erp/drafts/{did}/confirm")
    assert r.status_code == 200
    name = r.json()["erp_name"]
    assert r.json()["erp_url"] == f"https://erp.ops.example.com/app/purchase-order/{name}"
    assert c.post(f"/api/erp/drafts/{did}/confirm").status_code == 409
    assert c.post("/api/erp/drafts/999/confirm").status_code == 404
    did2 = c.post("/api/erp/drafts", json={"doctype": "Purchase Order", "payload": PO}).json()["id"]
    fake.fail_after = len(fake.requests)
    r = c.post(f"/api/erp/drafts/{did2}/confirm")
    assert r.status_code == 502 and "ERPNext did not accept" in r.json()["detail"]
    assert c.post(f"/api/erp/drafts/{did2}/reject", json={"reason": "duplicate"}).json()["status"] == "rejected"
    c.__exit__(None, None, None)
