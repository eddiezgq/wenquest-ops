"""The AI chat panel (ADR-0021): conversations kept per person, a follow-up sent with the earlier questions and
answers, the page and its record told to the assistant, which reads the record with the person's role. No real model
is called (``Scripted``). Fictional data only."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_ai import ALEX, DANA, Scripted, ctx, final, tool_use, world  # noqa: F401 - the fixture
from tests.test_anomalies import business
from tests.test_metrics import DEMO
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import record_tool as RT
from wqops.hub.app import create_app
from wqops.hub.quality import records as Q

PAGE = {"path": "/quality/ncr/1", "title": "NCR-00001", "record": {"kind": "ncr", "id": 1}}


def ncr(conn):
    return Q.create_ncr(conn, "jordan@demo.example", title="Scratched housing", severity="minor",
                        description="Two housings scratched", item_code="WIDGET-A")


def test_follow_up_and_page(world):  # noqa: F811
    n = ncr(world)
    chat = world.execute("insert into ai_chats (email) values ('dana@demo.example') returning id").fetchone()["id"]
    s = Scripted(tool_use(("get_record", {"kind": "ncr", "id": n["id"]})), final("NCR-00001 is open."),
                 final("It is minor."))
    m = s.model()
    out = AG.ask(ctx(world, DANA), "Summarize this", m, [RT.TOOL], chat_id=chat, page=PAGE)
    assert out["answer"] == "NCR-00001 is open." and f"[Record:ncr/{n['id']}/NCR-00001]" in out["refs"]
    system = s.requests[0]["body"]["system"]
    assert "looking at the page 'NCR-00001' (/quality/ncr/1)" in system and "get_record" in system
    AG.ask(ctx(world, DANA), "How serious?", m, [RT.TOOL], chat_id=chat, page=PAGE)
    msgs = s.requests[-1]["body"]["messages"]               # the follow-up carries the conversation so far
    assert [x["role"] for x in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "Summarize this" and msgs[1]["content"] == "NCR-00001 is open."
    runs = world.execute("select chat_id, page from ai_runs where chat_id = %s order by id", (chat,)).fetchall()
    assert len(runs) == 2 and runs[0]["page"]["record"] == {"kind": "ncr", "id": 1}
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from ai_chats")


def test_record_tool_and_rules(world):  # noqa: F811
    n = ncr(world)
    page = {**PAGE, "record": {"kind": "ncr", "id": n["id"]}}
    out = AG.ask(ctx(world, DANA), "summarize this", None, [RT.TOOL], page=page)    # no model: the rules answer
    assert out["engine"] == "rules" and "Scratched housing" in out["answer"] and "Status: open." in out["answer"]
    out = AG.ask(ctx(world, ALEX), "summarize this", None, [RT.TOOL], page=page)    # sales cannot see quality
    assert "cannot see ncr records" in out["answer"]
    with pytest.raises(RT.T.ToolError, match="no ncr 999"):
        RT.get_record(ctx(world, DANA), "ncr", 999)
    with pytest.raises(RT.T.ToolError, match="no record kind"):
        RT.get_record(ctx(world, DANA), "payroll", 1)
    assert "text" not in RT._clean({"text": "long", "a": [{"text": "x", "b": 1}]})["a"][0]


def test_chat_api(db_url):
    f = business()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport()), ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in ("dana@demo.example", "alex@demo.example"):
            Acc.set_password(conn, e, "Demo pass 2026")
    assert c.post("/api/ai/chats").status_code == 401
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Demo pass 2026"})
    cid = c.post("/api/ai/chats").json()["id"]
    out = c.post(f"/api/ai/chats/{cid}/ask", json={"question": "What is the inventory value?",
                                                   "page": {"path": "/", "title": "Dashboard",
                                                            "record": {"kind": "ncr", "id": "1; drop"}}}).json()
    assert out["answer"].startswith("Inventory value:")
    v = c.get(f"/api/ai/chats/{cid}").json()
    assert v["title"] == "What is the inventory value?" and len(v["turns"]) == 1
    assert v["turns"][0]["page"] == {"path": "/", "title": "Dashboard"}       # a bad record is left out
    assert c.get("/api/ai/chats").json()[0]["turns"] == 1
    for bad in ({"question": " "}, []):
        assert c.post(f"/api/ai/chats/{cid}/ask", json=bad).status_code == 400
    r = c.post(f"/api/ai/chats/{cid}/ask", content=b"{", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert c.post("/api/ai/chats/99999/ask", json={"question": "x"}).status_code == 404
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert c.get(f"/api/ai/chats/{cid}").status_code == 404                  # someone else's conversation
    assert c.get("/api/ai/chats").json() == []
    c.__exit__(None, None, None)
