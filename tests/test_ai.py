"""AI assistant, step 7a (ADR-0008): tools by role, the rule engine, a scripted model, number checks, run records.

No real model is called: ``Scripted`` answers like the Anthropic Messages API, from a script.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.test_anomalies import business
from tests.test_metrics import AS_OF, DEMO
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.app import create_app
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import project as OP

DANA = {"email": "dana@demo.example", "roles": ["owner"]}
ALEX = {"email": "alex@demo.example", "roles": ["sales"]}


class Scripted:
    """A stand-in for the Messages API: returns the scripted replies in order and keeps the requests."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        r = self.replies.pop(0)
        return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)

    def model(self) -> L.Anthropic:
        return L.Anthropic("test-key", "test-model", transport=httpx.MockTransport(self.handle))


def tool_use(*calls):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 20},
            "content": [{"type": "tool_use", "id": f"t{i}", "name": n, "input": a} for i, (n, a) in enumerate(calls)]}


def final(text):
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 300, "output_tokens": 50},
            "content": [{"type": "text", "text": text}]}


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    f = business()
    Y.run(conn, ErpClient("http://erp", transport=f.transport()))
    OP.project(conn, manifest=DEMO)
    AN.detect(conn, AS_OF)
    return conn


def ctx(conn, user):
    return T.Ctx(conn=conn, user=user, today=AS_OF, manifest=DEMO)


def test_verify_numbers():
    corpus = '{"value": 33.333, "date": "2026-10-10", "short": 50.0, "total": 1234.5}'
    assert AG.verify("WIDGET-A is short by 50. Supplier on time 33.3%. Due 2026-10-10.", corpus) == []
    assert AG.verify("Inventory is worth 1,234.50 dollars.", corpus) == []
    assert AG.verify("Order 120 more. There are 3 orders.", corpus) == ["Order 120 more."]
    assert AG.verify("It arrives 2026-10-11.", corpus) == ["It arrives 2026-10-11."]


def test_rule_engine_late_orders(world):
    out = AG.ask(ctx(world, DANA), "Which orders are late?")
    assert out["engine"] == "rules" and out["verified"]
    assert "[SalesOrder:SO-8] Bayside Hardware is 4 days late." in out["answer"]   # the link shows SO-8
    assert "On-time delivery over 30 days: 50%." in out["answer"]
    assert [c["tool"] for c in out["tool_calls"]] == ["get_metric", "list_anomalies"]
    run = world.execute("select * from ai_runs where id = %s", (out["run_id"],)).fetchone()
    assert run["engine"] == "rules" and run["email"] == "dana@demo.example" and run["verified"]
    assert "[SalesOrder:SO-8]" in run["refs"]


def test_rule_engine_named_object(world):
    out = AG.ask(ctx(world, DANA), "what is going on with so-8")
    assert "Cause: WIDGET-A is short by 50: 50 on hand, open orders need 100." in out["answer"]
    assert "Cause: Gulf Fasteners delivered 1 of 3 receipt lines on time in 90 days (33.3%)." in out["answer"]
    assert out["verified"]


def test_rule_engine_respects_roles(world):
    out = AG.ask(ctx(world, ALEX), "How is our supplier doing?")
    assert "cannot see Supplier on-time" in out["answer"] and out["tool_calls"][0]["ok"] is False
    out = AG.ask(ctx(world, ALEX), "what about PO-3?")      # sales cannot see purchase orders: not found as an object
    assert "PO-3" not in out["answer"]
    assert AG.ask(ctx(world, DANA), "hello")["answer"] == AG.HELP


def test_model_uses_tools_and_numbers_are_checked(world):
    s = Scripted(tool_use(("get_metric", {"name": "shortages"})),
                 final("WIDGET-A is short by 50 [Item:WIDGET-A]. I suggest ordering 120 units."))
    out = AG.ask(ctx(world, DANA), "What is short?", s.model())
    assert out["engine"] == "model" and out["model"] == "test-model"
    assert out["unverified"] == ["I suggest ordering 120 units."] and not out["verified"]
    first, second = s.requests
    assert first["headers"]["x-api-key"] == "test-key" and first["body"]["model"] == "test-model"
    assert {t["name"] for t in first["body"]["tools"]} == {t.name for t in T.READ_TOOLS}
    assert "Never guess or invent numbers" in first["body"]["system"]
    result = second["body"]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t0" and not result["is_error"]
    assert '"short": 50.0' in result["content"]
    run = world.execute("select * from ai_runs where id = %s", (out["run_id"],)).fetchone()
    assert run["usage"] == {"input_tokens": 400, "output_tokens": 70}
    assert run["tool_calls"][0]["tool"] == "get_metric" and run["unverified"] == ["I suggest ordering 120 units."]


def test_model_cannot_read_past_the_role(world):
    s = Scripted(tool_use(("get_object", {"type": "PurchaseOrder", "key": "PO-3"}),
                          ("get_metric", {"name": "supplier_on_time"})),
                 final("I cannot see purchasing data with your role."))
    out = AG.ask(ctx(world, ALEX), "Why is SO-8 late?", s.model())
    results = s.requests[1]["body"]["messages"][-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "cannot see Purchase order objects" in results[0]["content"]
    assert "PO-3" not in json.dumps([c for c in out["tool_calls"] if c["ok"]])


def test_model_failure_falls_back_to_rules(world):
    s = Scripted(httpx.Response(529, json={"error": {"message": "overloaded"}}))
    out = AG.ask(ctx(world, DANA), "Which orders are late?", s.model())
    assert out["engine"] == "rules (model unavailable)" and "overloaded" in out["error"]
    assert "[SalesOrder:SO-8]" in out["answer"]


def test_model_step_limit(world):
    s = Scripted(*[tool_use(("list_anomalies", {}))] * AG.MAX_ROUNDS)
    out = AG.ask(ctx(world, DANA), "Loop forever", s.model())
    assert "could not finish" in out["answer"] and len(out["tool_calls"]) == AG.MAX_ROUNDS


def test_unknown_tool_and_bad_arguments(world):
    s = Scripted(tool_use(("drop_tables", {}), ("get_object", {"typ": "Item"})), final("Done."))
    AG.ask(ctx(world, DANA), "x", s.model())
    results = s.requests[1]["body"]["messages"][-1]["content"]
    assert "no tool drop_tables" in results[0]["content"] and "wrong arguments" in results[1]["content"]


def test_ai_api(db_url):
    f = business()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport()), ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "dana@demo.example", "Demo pass 2026")
        Acc.set_password(conn, "alex@demo.example", "Demo pass 2026")
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
    assert c.post("/api/ai/ask", json={"question": "hi"}).status_code == 401
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Demo pass 2026"})
    assert c.get("/api/ai/status").json() == {"model_configured": False, "model": None, "engine": "rules",
                                              "provider": None}
    assert c.post("/api/ai/ask", json={"question": " "}).status_code == 400
    out = c.post("/api/ai/ask", json={"question": "What is the inventory value?"}).json()
    assert out["answer"].startswith("Inventory value: 170.00.")   # as computed by hand in test_metrics
    rid = out["run_id"]
    assert c.post(f"/api/ai/runs/{rid}/feedback", json={"useful": True}).json() == {"ok": True}
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert c.get(f"/api/ai/runs/{rid}").status_code == 404           # someone else's run
    assert c.get("/api/ai/runs", params={"everyone": True}).status_code == 403
    assert c.get("/api/ai/runs").json() == []
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Demo pass 2026"})
    runs = c.get("/api/ai/runs", params={"everyone": True}).json()
    assert runs[0]["feedback"] == 1 and runs[0]["question"] == "What is the inventory value?"
    c.__exit__(None, None, None)
