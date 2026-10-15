"""Setting the quality system up, step 16d (ADR-0016): the questionnaire and the declarations it proposes, changes
proposed from the company's procedures (scripted model) checked and decided one by one, and procedures written from
the workflow in use that need approval by someone else. Fictional data only."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted
from tests.test_documents import AS_OF, DEMO, PW, imported
from tests.test_metrics import build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import ai_classify as AIC
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP
from wqops.hub.quality import workflow_proposals as WP
from wqops.hub.system import qms as QMS
from wqops.hub.system import setup as SU
from wqops.hub.system import setup_ai as SAI

JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
T = AS_OF
GAUGES = "Gauges are calibrated every 12 months by an accredited laboratory."


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


def procedures(conn):
    """QP-11 Calibration and QP-08, approved."""
    imp, docs = imported(conn, ["QP-11", "QP-08 Control of Nonconforming Product Rev C"])
    AIC.run(conn, {"email": JORDAN, "roles": ["quality"]}, imp["id"], None, today=T)
    for d in docs:
        LIB.confirm(conn, JORDAN, d["id"])
        LIB.submit(conn, JORDAN, d["id"])
        LIB.approve(conn, Acc.get(conn, SAM), d["id"], PW, T)
    return [LIB.get(conn, d["id"]) for d in docs]


def reply(changes):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 2000, "output_tokens": 300}, "content": [{
        "type": "tool_use", "id": "t1", "name": "propose_setup",
        "input": {"changes": changes, "summary": "QP-11 sets the calibration interval."}}]}


def test_questionnaire(world):
    with pytest.raises(SU.SetupError, match="no question"):
        SU.save_answers(world, JORDAN, "iso9001", {"colour": "red"})
    with pytest.raises(SU.SetupError, match="yes or no"):
        SU.save_answers(world, JORDAN, "iso9001", {"designs": "no"})
    SU.save_answers(world, JORDAN, "iso9001", {"products": "Fasteners and cable, distributed", "people": 24,
                                                "designs": False, "customer_property": False, "measures": True})
    props = {p["control"]: p for p in SU.proposed_applicability(world, "iso9001")}
    assert props["design"]["applies"] is False and props["measuring"]["applies"] is True
    assert "after_delivery" not in {p["question"] for p in props.values()} and "post_delivery" not in props
    assert SU.apply_answers(world, Acc.get(world, DANA), "iso9001", PW, T) == 3
    decl = QMS.applicability(world, "iso9001")
    assert decl["design"]["applies"] is False and decl["design"]["email"] == DANA
    assert QMS.latest(world, "iso9001")["results"]["design"]["status"] == "not_applicable"
    with pytest.raises(SU.SetupError, match="already match"):
        SU.apply_answers(world, Acc.get(world, DANA), "iso9001", PW, T)
    assert SU.answers(world, "iso9001")["answers"]["people"] == 24


def test_changes_proposed_from_procedures(world):
    qp11, qp08 = procedures(world)
    docs = WP.read(world, "ncr", [qp11["id"], qp08["id"]])
    s = Scripted(reply([
        {"change": {"kind": "setting", "key": "calibration_interval_days", "value": 365}, "document_id": qp11["id"],
         "quote": GAUGES, "why": "12 months"},                                                    # already so
        {"change": {"kind": "setting", "key": "ncr_contain_days", "value": 2}, "document_id": qp08["id"],
         "quote": "Nonconforming product is tagged and moved to QC Hold.", "why": "at once"},
        {"change": {"kind": "evidence", "control": "production"}, "document_id": qp08["id"],
         "quote": "Quality decides the disposition: use as is, rework, return to supplier or scrap."},
        {"change": {"kind": "applies", "control": "measuring", "applies": True, "reason": "we calibrate gauges"},
         "document_id": qp11["id"], "quote": GAUGES},
        {"change": {"kind": "applies", "control": "ncr_records", "applies": False, "reason": "x"},
         "document_id": qp08["id"], "quote": GAUGES},
        {"change": {"kind": "setting", "key": "audit_interval_days", "value": 5}, "document_id": qp08["id"],
         "quote": "Audits happen weekly in our plant."},
    ]))
    p = SAI.propose(world, Acc.get(world, JORDAN), "iso9001", docs, s.model(), today=T, company="Harbor Lane")
    assert "calibration_interval_days: 365" in s.requests[0]["body"]["messages"][0]["content"]
    v = SU.view(world, p["id"])
    it = {i["seq"]: i for i in v["items"]}
    assert it[1]["already"] is True and it[2]["acceptable"] is True and it[3]["acceptable"] is True
    assert it[4]["acceptable"] is True and it[2]["text"] == "Days to contain a nonconformance: 2"
    assert it[5]["problems"] == ["this requirement always applies"]
    assert "from 30 to 1095" in it[6]["problems"][0]
    # accepting makes the change as a person would by hand: settings, links, signed declarations
    SU.decide(world, Acc.get(world, JORDAN), it[2]["id"], True, today=T)
    assert QMS.settings(world, "iso9001", QMS.load("iso9001"))["ncr_contain_days"] == 2
    SU.decide(world, Acc.get(world, JORDAN), it[3]["id"], True, today=T)
    assert QMS.latest(world, "iso9001")["results"]["production"]["status"] == "met"
    with pytest.raises(PermissionError):
        SU.decide(world, Acc.get(world, JORDAN), it[4]["id"], True, password="wrong", today=T)
    SU.decide(world, Acc.get(world, JORDAN), it[4]["id"], True, password=PW, today=T)
    assert QMS.applicability(world, "iso9001")["measuring"]["applies"] is True
    with pytest.raises(SU.SetupError, match="passes the checks"):
        SU.decide(world, Acc.get(world, JORDAN), it[5]["id"], True, today=T)
    SU.decide(world, Acc.get(world, JORDAN), it[5]["id"], False, note="not for us", today=T)
    with pytest.raises(SU.SetupError, match="already rejected"):
        SU.decide(world, Acc.get(world, JORDAN), it[5]["id"], True, today=T)
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update qms_setup_items set quote = 'x' where id = %s", (it[6]["id"],))
    assert SU.listing(world, "iso9001")[0]["accepted"] == 3
    # without a model, or when it fails, nothing is stored and the run says why
    with pytest.raises(SAI.NoModel):
        SAI.propose(world, Acc.get(world, JORDAN), "iso9001", docs, L.Anthropic("", env={}), today=T)
    with pytest.raises(L.LlmError, match="did not propose"):
        SAI.propose(world, Acc.get(world, JORDAN), "iso9001", docs,
                    Scripted({"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}).model(),
                    today=T)


def test_procedures_written_from_the_workflow(world):
    title, sections = SU.procedure_text(world, "ncr")
    text = "\n".join(p for _, paras in sections for p in paras)
    assert title == "Control of Nonconforming Product"
    assert "Approve disposition (from Waiting for approval to Dispositioned)" in text
    assert "Not done by the person who submitted the disposition." in text
    assert "A major nonconformance is closed only after its corrective action is closed." in text
    assert "Nonconformance report workflow version 1" in text
    doc = SU.generate(world, JORDAN, "ncr", "Harbor Lane Supply (Demo)")
    assert doc["status"] == "to_review" and doc["revision"] == "W1" and doc["process"] == "nonconformance"
    assert "written by WenQuest Ops from the workflow in use" in LIB.text(world, doc["id"])
    assert SU.generated(world)[0]["current"] is True
    # it is a draft to approve by someone else, even if confirmed as another type
    LIB.confirm(world, JORDAN, doc["id"], {"doc_type": "record"})
    assert LIB.get(world, doc["id"])["status"] == "draft"
    cap = SU.generate(world, JORDAN, "capa")
    assert "Effective, close" in LIB.text(world, cap["id"]) and cap["process"] == "capa"
    with pytest.raises(KeyError):
        SU.generate(world, JORDAN, "audit")


def test_setup_api(db_url):
    s = Scripted()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=s.model()))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(JORDAN)
    v = c.get("/api/qms/iso9001/setup").json()
    assert v["adopted"] is False and v["proposed"] == [] and "designs" in v["questions"]
    c.post("/api/qms/iso9001/enable", json={"edition": "2015", "password": PW})
    v = c.post("/api/qms/iso9001/setup/answers", json={"answers": {"designs": False}}).json()
    assert v["proposed"][0]["control"] == "design"
    assert c.post("/api/qms/iso9001/setup/answers", json={"answers": {"people": "many"}}).status_code == 409
    assert c.post("/api/qms/iso9001/setup/apply", json={"password": PW}).status_code == 200
    r = c.post("/api/qms-procedures/ncr")
    assert r.status_code == 201 and r.json()["title"] == "Control of Nonconforming Product"
    assert c.get("/api/qms/iso9001/setup").json()["generated"][0]["current"] is True
    assert c.post("/api/qms/iso9001/setup/proposals", json={"document_ids": "all"}).status_code == 400
    assert c.post("/api/qms-setup-items/1/maybe").status_code == 404
    login("lee@demo.example")
    assert c.get("/api/qms/iso9001/setup").json()["can_configure"] is False
    assert c.post("/api/qms/iso9001/setup/answers", json={"answers": {}}).status_code == 403
    assert c.post("/api/qms-procedures/capa").status_code == 403
    c.__exit__(None, None, None)
