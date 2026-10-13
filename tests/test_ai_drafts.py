"""AI drafts, step 7b (ADR-0008 item 3): computed from the objects, pending until a person confirms, nothing written
before that. Business data is fictional (tests/test_anomalies.py plus an item nobody has bought yet)."""

import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted, final, tool_use
from tests.test_anomalies import business
from tests.test_metrics import AS_OF, DEMO
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import sync as Y
from wqops.hub.ai import agent as AG
from wqops.hub.ai import drafting as DR
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.app import create_app
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import project as OP

PAT = {"email": "pat@demo.example", "roles": ["purchasing"]}
ALEX = {"email": "alex@demo.example", "roles": ["sales"]}
JORDAN = {"email": "jordan@demo.example", "roles": ["quality"]}


def shop():
    f = business()
    f.put("Item", "CABLE-C", item_name="Cable-C", is_stock_item=1)
    f.put("Sales Order", "SO-9", customer="Bayside Hardware", customer_name="Bayside Hardware", status="To Deliver",
          delivery_date="2026-10-25", per_delivered=0, docstatus=1,
          items=[{"item_code": "CABLE-C", "qty": 5, "delivered_qty": 0}])
    return f


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    f = shop()
    erp = ErpClient("http://erp", transport=f.transport())
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    AN.detect(conn, AS_OF)
    f.requests.clear()
    return conn, f, erp


def ctx(conn, user):
    return T.Ctx(conn=conn, user=user, today=AS_OF, manifest=DEMO)


def test_replenishment_purchase_order(world):
    conn, f, erp = world
    out = AG.draft(ctx(conn, PAT), "purchase_order", "WIDGET-A")
    d = out["draft"]
    # short 50 (on hand 50, SO-5 80 + SO-8 20); last purchase order PO-3 from Gulf Fasteners; the earliest order
    # needing it (SO-8) was due 10-08, already past, so it is needed today
    assert d["payload"] == {"supplier": "Gulf Fasteners", "transaction_date": "2026-10-12",
                            "schedule_date": "2026-10-12", "company": "Harbor Lane Supply (Demo)",
                            "items": [{"item_code": "WIDGET-A", "qty": 50, "schedule_date": "2026-10-12",
                                       "warehouse": "Main Stock - HLS"}]}
    assert d["summary"] == ("Replenish WIDGET-A Widget-A: short 50 for SO-5, SO-8; 50 from Gulf Fasteners as on PO-3, "
                            "needed by 2026-10-12.")
    assert f.requests == []                                      # nothing written to ERPNext yet
    row = D.get(conn, d["draft_id"])
    assert row["status"] == "pending" and row["source"] == "ai" and row["ai_run"] == str(out["run_id"])
    done = D.confirm(conn, PAT, d["draft_id"], erp)
    made = f.docs["Purchase Order"][done["erp_name"]]
    assert made["docstatus"] == 0 and made["items"][0]["qty"] == 50


def test_purchase_order_needs_a_known_supplier_and_permission(world):
    conn, _, _ = world
    with pytest.raises(T.ToolError, match="no earlier purchase order for CABLE-C"):
        AG.draft(ctx(conn, PAT), "purchase_order", "CABLE-C")
    with pytest.raises(T.ToolError, match="Draft purchase orders"):
        AG.draft(ctx(conn, ALEX), "purchase_order", "WIDGET-A")
    with pytest.raises(T.ToolError, match="no Item BOLT-X"):
        DR.purchase_order(ctx(conn, PAT), "BOLT-X")
    failed = conn.execute("select error from ai_runs where kind = 'draft' and error is not null").fetchall()
    assert len(failed) == 2                                       # failed attempts are recorded too


def test_customer_delay_message(world):
    conn, f, erp = world
    out = AG.draft(ctx(conn, ALEX), "delay_message", "SO-8")
    p = out["draft"]["payload"]
    assert p["customer"] == "Bayside Hardware" and p["subject"] == "Update on your order SO-8"
    assert "Your order SO-8 was due on 2026-10-08." in p["body"]
    assert "some items are not yet in stock: WIDGET-A (20 to ship)" in p["body"]
    assert "Gulf" not in p["body"] and "Harbor Lane Supply (Demo)" in p["body"]   # suppliers stay internal
    done = D.confirm(conn, ALEX, out["draft"]["draft_id"], erp)
    assert done["status"] == "confirmed" and done["target"] == "hub" and f.requests == []
    with pytest.raises(T.ToolError, match="not an open order"):
        AG.draft(ctx(conn, ALEX), "delay_message", "SO-1")
    soon = AG.draft(ctx(conn, ALEX), "delay_message", "SO-9")["draft"]["payload"]["body"]   # not late yet, at risk
    assert "Your order SO-9 is due on 2026-10-25." in soon and "CABLE-C (5 to ship)" in soon


def test_nonconformance_report(world):
    conn, f, erp = world
    out = AG.draft(ctx(conn, JORDAN), "nonconformance", "QI-1")
    p = out["draft"]["payload"]
    assert p["receipt"] == "PR-2" and p["supplier"] == "Gulf Fasteners" and p["quantity"] == 50
    assert p["description"].startswith("Quality inspection QI-1 (Incoming) on 2026-10-02 rejected BOLT-B.")
    with pytest.raises(D.NotAllowed):
        D.confirm(conn, ALEX, out["draft"]["draft_id"], erp)
    done = D.confirm(conn, JORDAN, out["draft"]["draft_id"], erp)
    assert done["record"] == "NCR-00001" and f.requests == []
    ncr = conn.execute("select * from ncr_records").fetchone()
    assert ncr["title"] == "Rejected BOLT-B (QI-1)" and ncr["created_by"] == "jordan@demo.example"
    with pytest.raises(T.ToolError, match="not rejected"):
        AG.draft(ctx(conn, JORDAN), "nonconformance", "QI-2")


def test_model_drafts_stay_pending(world):
    conn, f, _ = world
    s = Scripted(tool_use(("draft_purchase_order", {"item_code": "WIDGET-A"})),
                 final("I prepared a purchase order for 50 of [Item:WIDGET-A]; please confirm it."))
    out = AG.ask(ctx(conn, PAT), "Order what we need for WIDGET-A", s.model(), DR.DRAFT_TOOLS)
    assert len(out["drafts"]) == 1 and out["verified"] and f.requests == []
    assert D.get(conn, out["drafts"][0])["ai_run"] == str(out["run_id"])
    run = conn.execute("select drafts from ai_runs where id = %s", (out["run_id"],)).fetchone()
    assert run["drafts"] == out["drafts"]
    assert "draft_customer_delay_message" in {t["name"] for t in s.requests[0]["body"]["tools"]}


def test_drafts_api(db_url):
    f = shop()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport()), ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in ("alex@demo.example", "pat@demo.example"):
            Acc.set_password(conn, e, "Demo pass 2026")
    c.post("/api/login", json={"email": "pat@demo.example", "password": "Demo pass 2026"})
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    with DB.connect(db_url) as conn:
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
    r = c.post("/api/ai/draft", json={"kind": "delay_message", "key": "SO-8"})
    assert r.status_code == 200 and r.json()["draft"]["kind"] == "Customer Message"
    assert c.post("/api/ai/draft", json={"kind": "purchase_order", "key": "WIDGET-A"}).status_code == 400
    assert c.post("/api/ai/draft", json={"kind": "invoice", "key": "x"}).status_code == 400
    assert [d["doctype"] for d in c.get("/api/erp/drafts").json()] == ["Customer Message"]
    c.post("/api/login", json={"email": "pat@demo.example", "password": "Demo pass 2026"})
    assert c.get("/api/erp/drafts").json() == []                 # purchasing does not see customer messages
    c.__exit__(None, None, None)
