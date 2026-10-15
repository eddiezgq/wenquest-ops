"""Gap report, to-dos and the internal audit checklist, step 16c (ADR-0016): gaps from the latest check, to-dos that
the check closes once the control point is met, dropping with a reason, to-dos kept as they were, the checklist with
samples, and the model drafting a missing document into the library for review (scripted model). Fictional data."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted
from tests.test_documents import AS_OF, DEMO, PW
from tests.test_metrics import build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP
from wqops.hub.system import draft_ai as DAI
from wqops.hub.system import gaps as G
from wqops.hub.system import qms as QMS
from wqops.hub.system import registers as RG

JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
T = AS_OF


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=build().transport()))
    OP.project(conn, manifest=DEMO)
    QMS.enable(conn, Acc.get(conn, JORDAN), "iso9001", "2015", PW, T)
    return conn


def draft_reply(**kw):
    inp = {"title": "Quality Policy", "doc_type": "other", "sections": [
        {"heading": "Our policy", "paragraphs": ["[to fill: company name] supplies parts that meet the order."]},
        {"heading": "Commitments", "paragraphs": ["We meet requirements.", "We improve our system."]}],
        "to_fill": ["company name", "who signs the policy"]} | kw
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 900, "output_tokens": 500},
            "content": [{"type": "tool_use", "id": "t1", "name": "write_document", "input": inp}]}


def test_gaps_and_todos(world):
    rep = G.report(world, "iso9001")
    ids = {g["id"]: g for p in rep["processes"] for g in p["gaps"]}
    assert "review" in ids and ids["supplier_approval"]["status"] == "not_met"
    assert rep["counts"]["not_met"] + rep["counts"]["unknown"] == len(ids) and rep["counts"]["with_todo"] == 0
    t = G.add(world, JORDAN, "iso9001", "review", owner="Dana", due=dt.date(2026, 12, 15))
    assert t["title"].startswith("Show: Top management reviews") and t["owner"] == "Dana"
    with pytest.raises(G.TodoError, match="already an open to-do"):
        G.add(world, JORDAN, "iso9001", "review")
    with pytest.raises(KeyError):
        G.add(world, JORDAN, "iso9001", "nope")
    made = G.add_all(world, JORDAN, "iso9001")
    assert made == len(ids) - 1 and G.report(world, "iso9001")["counts"]["with_todo"] == len(ids)
    sup = next(x for x in G.todos(world, "iso9001") if x["control"] == "supplier_approval")
    assert sup["title"].startswith("Suppliers are evaluated") and "Now: " in sup["title"]
    # the check closes a to-do once its control point is met
    e = RG.create(world, JORDAN, "management_reviews", {"review_date": "2026-09-30", "attendees": "Dana",
                                                         "decisions": "x"})
    RG.sign(world, Acc.get(world, SAM), e["id"], PW)
    QMS.evaluate(world, "iso9001", T, "changed")
    done = next(x for x in G.todos(world, "iso9001") if x["id"] == t["id"])
    assert done["status"] == "done" and done["closed_by"] == "WenQuest Ops"
    assert "review" not in {g["id"] for p in G.report(world, "iso9001")["processes"] for g in p["gaps"]}
    # people change and close to-dos; closed ones are kept as they were
    G.change(world, JORDAN, sup["id"], owner="Pat", due=dt.date(2026, 11, 1))
    with pytest.raises(G.TodoError, match="say why"):
        G.change(world, JORDAN, sup["id"], status="dropped")
    out = G.change(world, JORDAN, sup["id"], status="dropped", note="covered by the new purchasing procedure")
    assert out["status"] == "dropped" and out["closed_by"] == JORDAN
    with pytest.raises(G.TodoError, match="dropped"):
        G.change(world, JORDAN, sup["id"], owner="x")
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update qms_todos set title = 'x' where id = %s", (sup["id"],))
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("delete from qms_todos where id = %s", (sup["id"],))
    acts = [r["action"] for r in world.execute("select action from qms_todo_log where todo_id = %s order by id",
                                               (sup["id"],))]
    assert acts == ["opened", "changed", "dropped"]
    # a dropped gap can get a new to-do
    assert G.add(world, JORDAN, "iso9001", "supplier_approval")["status"] == "open"


def test_audit_checklist(world):
    cl = G.checklist(world, "iso9001", "nonconforming")
    assert [p["id"] for p in cl["processes"]] == ["nonconforming"] and len(cl["processes_all"]) == 9
    item = cl["processes"][0]["items"][0]
    assert item["question"].startswith("Can the company show that: nonconforming outputs are identified")
    assert item["clauses"] == ["8.7.1"]
    full = G.checklist(world, "iso9001")
    assert len(full["processes"]) == 9
    sup = next(i for p in full["processes"] for i in p["items"] if i["id"] == "supplier_approval")
    assert sup["status"] == "not_met" and 0 < len(sup["gaps"]) <= G.SAMPLE and sup["register"] == "suppliers"
    with pytest.raises(KeyError):
        G.checklist(world, "iso9001", "nope")


def test_the_model_drafts_a_missing_document(world):
    assert "policy" in DAI.draftable(world, "iso9001") and "review" not in DAI.draftable(world, "iso9001")
    with pytest.raises(DAI.NoModel):
        DAI.draft(world, Acc.get(world, JORDAN), "iso9001", "policy", L.Anthropic("", env={}), today=T)
    with pytest.raises(QMS.QmsError, match="not shown by a document"):
        DAI.draft(world, Acc.get(world, JORDAN), "iso9001", "review", Scripted().model(), today=T)
    s = Scripted(draft_reply())
    doc = DAI.draft(world, Acc.get(world, JORDAN), "iso9001", "policy", s.model(), today=T,
                    company="Harbor Lane Supply (Demo)")
    req = s.requests[0]["body"]
    assert req["tool_choice"]["name"] == "write_document" and "[to fill: ...]" in req["system"]
    assert "ISO 9001 5.2" in req["messages"][0]["content"]
    assert doc["status"] == "to_review" and doc["engine"] == "ai" and doc["title"] == "Quality Policy"
    assert doc["process"] == "management_review" and doc["original_name"] == "DRAFT Quality Policy.docx"
    body = LIB.text(world, doc["id"])
    assert "DRAFT written by AI" in body and "To fill in before approval" in body and "who signs the policy" in body
    run = world.execute("select * from ai_runs where id = %s", (doc["ai_run"],)).fetchone()
    assert run["kind"] == "document" and run["engine"] == "model"
    # a person confirms it; it counts only once it is in the library as confirmed and linked
    LIB.confirm(world, JORDAN, doc["id"])
    QMS.link(world, JORDAN, "iso9001", "policy", doc["id"], True, T)
    assert QMS.latest(world, "iso9001")["results"]["policy"]["status"] == "met"
    # a draft with no text, or cut off, is not stored; the run says why
    for reply, msg in [(draft_reply(sections=[]), "no title or no text"),
                       (dict(draft_reply(), stop_reason="max_tokens"), "cut off")]:
        with pytest.raises(L.LlmError, match=msg):
            DAI.draft(world, Acc.get(world, JORDAN), "iso9001", "roles", Scripted(reply).model(), today=T)
    assert world.execute("select count(*) as n from ai_runs where kind = 'document' and engine = 'model (failed)'"
                         ).fetchone()["n"] == 2


def test_gaps_api(db_url):
    s = Scripted()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=s.model()))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(JORDAN)
    assert c.get("/api/qms/iso9001/gaps").status_code == 409                # adopt first
    c.post("/api/qms/iso9001/enable", json={"edition": "2015", "password": PW})
    g = c.get("/api/qms/iso9001/gaps").json()
    assert g["can_edit"] is True and g["ai"] is True and "policy" in g["draftable"]
    r = c.post("/api/qms/iso9001/todos", json={"control": "policy", "owner": "Dana", "due": "2026-12-01"})
    assert r.status_code == 201 and r.json()["counts"]["with_todo"] == 1
    assert c.post("/api/qms/iso9001/todos", json={"control": "scope", "due": "soon"}).status_code == 400
    tid = r.json()["todos"][0]["id"]
    assert c.put(f"/api/qms-todos/{tid}", json={"due": ""}).json()["todos"][0]["due"] is None
    assert c.post("/api/qms/iso9001/todos/all", json={}).status_code == 200
    assert c.get("/api/qms/iso9001/checklist?process=audit").status_code == 404
    assert len(c.get("/api/qms/iso9001/checklist?process=evaluation").json()["processes"][0]["items"]) == 3
    s.replies.append(draft_reply())
    d = c.post("/api/qms/iso9001/controls/policy/draft")
    assert d.status_code == 201 and d.json()["title"] == "Quality Policy"
    login("lee@demo.example")                                    # warehouse: may look only
    g = c.get("/api/qms/iso9001/gaps").json()
    assert g["can_edit"] is False and g["draftable"] == []
    assert c.post("/api/qms/iso9001/todos", json={"control": "scope"}).status_code == 403
    assert c.post("/api/qms/iso9001/controls/roles/draft").status_code == 403
    c.__exit__(None, None, None)
