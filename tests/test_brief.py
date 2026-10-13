"""Daily brief, step 7c (ADR-0008 item 6): numbers by code, model wording only when every number checks out."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted, final
from tests.test_ai_drafts import shop
from tests.test_metrics import AS_OF, DEMO
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import brief as BR
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import project as OP

OWNER = ["owner"]


def business():
    f = shop()
    f.put("Sales Order", "SO-10", customer="Bayside Hardware", customer_name="Bayside Hardware", status="To Deliver",
          delivery_date="2026-10-12", per_delivered=0, docstatus=1,
          items=[{"item_code": "BOLT-B", "qty": 1, "delivered_qty": 0}])
    return f


def load(conn):
    Acc.sync(conn, DEMO)
    Y.run(conn, ErpClient("http://erp", transport=business().transport()))
    OP.project(conn, manifest=DEMO)
    AN.detect(conn, AS_OF)


@pytest.fixture
def world(conn):
    load(conn)
    return conn


def test_facts_and_rule_text(world):
    f = BR.facts(world, AS_OF)
    assert f["metrics"]["on_time_delivery"]["value"] == 50.0 and f["metrics"]["inventory_value"]["value"] == 170.0
    assert f["due_today"] == [{"type": "SalesOrder", "key": "SO-10", "title": "SO-10 Bayside Hardware"}]
    n = len(f["anomalies"])
    t = BR.text(f, "Harbor Lane Supply (Demo)")
    assert t.startswith("Good morning. Brief for Harbor Lane Supply (Demo), 2026-10-12.\nLast 30 days: On-time "
                        "delivery 50%; Items short 3; Inventory value 170.00; Days of inventory 28.9 days; "
                        "Supplier on-time 33.3%; Open nonconformances 1.")
    assert f"Open problems: {n}, of which {n} new since yesterday and 0 critical." in t
    assert "Due today: SO-10 Bayside Hardware." in t


def test_model_wording_is_checked(world):
    good = Scripted(final("Morning! On-time delivery is 50% and inventory is worth 170.00. SO-10 is due today."))
    row = BR.generate(world, AS_OF, DEMO, good.model())
    assert row["engine"] == "model" and row["model_text"].startswith("Morning!")
    assert good.requests[0]["body"]["tools"] == []
    bad = Scripted(final("Morning! Inventory is worth 180.00."))
    row = BR.generate(world, AS_OF, DEMO, bad.model())               # same day: replaced
    assert row["engine"] == "rules (model wording failed the number check)" and row["model_text"] is None
    run = world.execute("select * from ai_runs where id = %s", (row["run_id"],)).fetchone()
    assert run["kind"] == "brief" and run["unverified"] == ["Inventory is worth 180.00."]
    assert world.execute("select count(*) as n from briefs").fetchone()["n"] == 1


def test_each_role_sees_its_part(world):
    row = BR.generate(world, AS_OF, DEMO, Scripted(final("Morning! On-time delivery is 50%.")).model())
    owner = BR.view(row, OWNER, "Harbor Lane Supply (Demo)")
    assert owner["text"] == "Morning! On-time delivery is 50%." and owner["run_id"]
    sales = BR.view(row, ["sales"], "Harbor Lane Supply (Demo)")
    assert "Supplier on-time" not in sales["text"] and sales["engine"] == "rules" and sales["run_id"] is None
    assert {a["rule"] for a in sales["facts"]["anomalies"]} <= {"order_late", "order_at_risk", "item_short"}
    assert [d["type"] for d in sales["facts"]["due_today"]] == ["SalesOrder"]


def test_made_once_after_seven_thirty(world):
    ny = dt.timezone(dt.timedelta(hours=-4))
    assert BR.due(world, DEMO, dt.datetime(2026, 10, 12, 7, 29, tzinfo=ny)) is None
    assert BR.due(world, DEMO, dt.datetime(2026, 10, 12, 7, 31, tzinfo=ny)) == dt.date(2026, 10, 12)
    BR.generate(world, dt.date(2026, 10, 12), DEMO)
    assert BR.due(world, DEMO, dt.datetime(2026, 10, 12, 9, 0, tzinfo=ny)) is None


def test_brief_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        load(conn)
        for e in ("dana@demo.example", "alex@demo.example"):
            Acc.set_password(conn, e, "Demo pass 2026")
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert c.get("/api/brief").status_code == 404
    assert c.post("/api/brief/generate").status_code == 403
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Demo pass 2026"})
    b = c.post("/api/brief/generate").json()
    assert b["text"].startswith("Good morning.") and b["engine"] == "rules"
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert "Supplier on-time" not in c.get("/api/brief").json()["text"]
    c.__exit__(None, None, None)
