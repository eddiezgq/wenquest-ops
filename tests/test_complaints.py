"""Complaints, step 17e (ADR-0017; dee-qms PLAN-COMPLAINT): what each step needs, the reporting decision made and
signed by someone other than the owner (WenQuest Ops asks and shows the deadline, never decides), exceptions,
closing by someone else with everything in place, records kept, the ISO checks reading complaints, and the API.
Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, PW
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.ont import api as OA
from wqops.hub.quality import complaint_rules as CR
from wqops.hub.quality import complaints as C
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS

DANA, SAM, JORDAN, LEE = "dana@demo.example", "sam@demo.example", "jordan@demo.example", "lee@demo.example"
T = AS_OF
NO = {"q_harm": "no", "q_malfunction": "no", "q_recall": "no"}


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (DANA, SAM, JORDAN, LEE):
        Acc.set_password(conn, e, PW)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def received(conn, **kw):
    return C.create(conn, LEE, {"received_on": str(T - dt.timedelta(days=3)), "customer": "Bay Vet Clinic (Demo)",
                                "description": "Infusion pump alarm did not sound", "item_code": "PUMP-1",
                                **kw}, today=T)


def test_rules():
    assert CR.to_investigate({"description": "x"}) == ["an owner", "the product", "whether anyone was hurt (yes or no)"]
    a = CR.assessment({"q_harm": "yes"}, None, "")
    assert len(a["errors"]) == 4 and a["suggest"] == "report"
    assert CR.assessment({**NO, "q_recall": "yes"}, False, "Recall already reported")["exception"] is True
    assert CR.assessment(NO, False, "Cosmetic")["errors"] == [] and CR.assessment(NO, False, "x")["exception"] is False
    assert CR.to_close({"status": "assessed", "investigate": True, "investigation": "", "reportable": True,
                        "report_ref": "", "response": ""}) == [
        "the investigation's conclusion (or the reason, approved, for not investigating)",
        "the report's reference and the day it was made", "the reply to the customer"]


def test_from_receipt_to_close(world):
    with pytest.raises(C.ComplaintError, match="cannot be after today"):
        received(world, aware_on=str(T + dt.timedelta(days=1)))
    c = received(world, injury="unknown")
    assert c["name"] == "CMP-00001" and c["aware_on"] == c["received_on"]
    with pytest.raises(C.ComplaintError, match=r"an owner.*whether anyone was hurt"):
        C.start(world, LEE, c["id"])
    C.update(world, u(world, LEE), c["id"], {"owner": JORDAN, "injury": "yes"}, today=T)
    C.start(world, LEE, c["id"])
    # once investigating, only Quality changes the owner
    with pytest.raises(PermissionError, match="Quality changes the owner"):
        C.update(world, u(world, LEE), c["id"], {"owner": LEE}, today=T)
    with pytest.raises(C.ComplaintError, match="investigation's conclusion first"):
        C.assess(world, u(world, SAM), c["id"], PW, answers=NO, reportable=False, reason="x")
    C.update(world, u(world, JORDAN), c["id"], {"investigation": "Alarm speaker failed; lot 7 affected",
                                                 "root_cause": "Supplier speaker change"}, today=T)
    with pytest.raises(PermissionError, match="other than the owner"):
        C.assess(world, u(world, JORDAN), c["id"], PW, answers=NO, reportable=False, reason="x")
    with pytest.raises(C.ComplaintError, match="answer: Did the device malfunction"):
        C.assess(world, u(world, SAM), c["id"], PW, answers={"q_harm": "yes", "q_recall": "no"}, reportable=True,
                 reason="Patient harm possible")
    with pytest.raises(Q.SignatureError):
        C.assess(world, u(world, SAM), c["id"], "wrong", answers={**NO, "q_harm": "yes"}, reportable=True,
                 reason="Patient harm possible")
    a = C.assess(world, u(world, SAM), c["id"], PW, answers={**NO, "q_harm": "yes"}, reportable=True,
                 reason="Patient harm possible")
    assert (a["status"], a["deadline_days"], a["deadline_on"]) == ("assessed", 30, c["aware_on"] + dt.timedelta(30))
    # what the decision rests on is fixed now, in code and in the database
    with pytest.raises(C.ComplaintError, match="is assessed"):
        C.update(world, u(world, JORDAN), c["id"], {"investigation": "changed"}, today=T)
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        world.execute("update complaints set reportable = false where id = %s", (c["id"],))
    with pytest.raises(C.ComplaintError, match=r"report.s reference.*reply to the customer"):
        C.close(world, u(world, SAM), c["id"], PW)
    C.update(world, u(world, JORDAN), c["id"], {"report_ref": "MDR-2026-0042", "reported_on": str(T),
                                                 "response": "Pump replaced; speaker supplier corrected"}, today=T)
    with pytest.raises(PermissionError, match="other than the owner closes"):
        C.close(world, u(world, JORDAN), c["id"], PW)
    done = C.close(world, u(world, DANA), c["id"], PW)
    assert done["status"] == "closed"
    assert [s["meaning"] for s in Q.signatures(world, "complaint", c["id"])] == ["Reportable", "Complaint closed"]
    with pytest.raises(psycopg.errors.RaiseException, match="closed"):
        world.execute("update complaints set response = 'x' where id = %s", (c["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from complaints")


def test_exceptions_no_investigation_and_cancel(world):
    c = received(world, injury="no", owner=JORDAN)
    C.start(world, LEE, c["id"])
    with pytest.raises(C.ComplaintError, match="give the reason"):
        C.no_investigation(world, SAM, c["id"], " ")
    C.no_investigation(world, SAM, c["id"], "Same event as CMP-00007, already investigated")
    a = C.assess(world, u(world, SAM), c["id"], PW, answers={**NO, "q_recall": "yes"}, reportable=False,
                 reason="The recall it belongs to was reported already")
    assert a["exception"] is True and a["deadline_on"] is not None
    n = C.open_ncr(world, JORDAN, c["id"])
    assert n["item_code"] == "PUMP-1" and C.get(world, c["id"])["ncr_id"] == n["id"]
    cp = C.open_capa(world, JORDAN, c["id"])
    assert [x["id"] for x in Q.capa_ncrs(world, cp["id"])] == [n["id"]]
    dup = received(world)
    with pytest.raises(C.ComplaintError, match="duplicate"):
        C.cancel(world, LEE, dup["id"], "")
    assert C.cancel(world, LEE, dup["id"], "duplicate of CMP-00001")["status"] == "cancelled"
    assert [x["name"] for x in C.listing(world, "open", T)] == ["CMP-00001"]


def test_iso_checks_read_complaints(world):
    QMS.enable(world, u(world, JORDAN), "iso13485", "2016", PW, T)
    c = received(world, injury="no", owner=JORDAN, aware_on=str(T - dt.timedelta(days=40)))
    C.start(world, LEE, c["id"])
    QMS.evaluate(world, "iso13485", T, "manual", JORDAN)
    r = QMS.latest(world, "iso13485")["results"]["complaints_assessed"]
    # received 3 days ago: still within the days to decide, nothing decided yet
    assert r["status"] == "unknown"
    C.update(world, u(world, JORDAN), c["id"], {"investigation": "User error"}, today=T)
    C.assess(world, u(world, SAM), c["id"], PW, answers=NO, reportable=False, reason="No harm possible")
    QMS.evaluate(world, "iso13485", T, "manual", JORDAN)
    r = QMS.latest(world, "iso13485")["results"]["complaints_assessed"]
    assert r["status"] == "met" and r["evidence"][0]["id"] == f"c{c['id']}"


def test_complaints_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, SAM, JORDAN, LEE):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    day = str(OA.today(DEMO))
    login(LEE)
    assert c.post("/api/complaints", json={"received_on": day, "customer": "Clinic", "description": "x"}).status_code \
        == 403                                    # the warehouse sees quality, does not record it
    login(JORDAN)
    r = c.post("/api/complaints", json={"received_on": day, "customer": "Clinic", "description": "Leak",
                                        "item_code": "PUMP-1", "injury": "no", "owner": LEE})
    cid = r.json()["id"]
    assert c.post(f"/api/complaints/{cid}/start").json()["status"] == "investigation"
    assert c.put(f"/api/complaints/{cid}", json={"colour": "red"}).status_code == 409
    c.put(f"/api/complaints/{cid}", json={"investigation": "Seal damaged in transit"})
    v = c.post(f"/api/complaints/{cid}/assess", json={"answers": NO, "reportable": False, "reason": "No harm",
                                                      "password": PW}).json()
    assert v["status"] == "assessed" and v["deadline_on"] is None
    assert c.post(f"/api/complaints/{cid}/explode").status_code == 404
    assert c.get("/api/complaints?status=all").json()["complaints"][0]["name"] == "CMP-00001"
    c.__exit__(None, None, None)
