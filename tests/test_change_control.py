"""Change control, step 17g (ADR-0017; dee-qms PLAN-CHANGE): what each step needs, the content fixed once
submitted, approval by someone who did not raise, own, submit or edit the change, implementation only with the new
revisions in effect and validation done, closing by someone other than the owner, records kept, the API.
Fictional data only."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_doc_control import in_review
from tests.test_documents import AS_OF, DEMO, PW, file
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.docs import library as LIB
from wqops.hub.quality import change_control as CC
from wqops.hub.quality import change_rules as CR
from wqops.hub.quality import records as Q

DANA, SAM, JORDAN, LEE = "dana@demo.example", "sam@demo.example", "jordan@demo.example", "lee@demo.example"
T = AS_OF
YES_NO = {"q_product": "no", "q_regulatory": "yes", "q_risk": "no", "q_validation": "yes"}


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (DANA, SAM, JORDAN, LEE):
        Acc.set_password(conn, e, PW)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def effective_doc(conn):
    doc = in_review(conn)
    LIB.approve(conn, u(conn, SAM), doc["id"], PW, T)
    return LIB.get(conn, doc["id"])


def test_rules():
    miss = CR.to_submit({"title": "x", "kind": "process", "q_regulatory": "yes", "q_validation": "yes"})
    assert "an owner" in miss and "the regulatory decision (what will be submitted or notified, or why not)" in miss
    assert "the verification or validation plan" in miss
    c = {"implementation": "done", "q_validation": "yes", "validation_result": "", "documents": [1], "revisions": [2]}
    assert CR.to_implement(c, {1: {"number": "QP-08"}, 2: {"supersedes": 1, "status": "in_review"}}) == [
        "the verification or validation result", "a new revision of QP-08, in effect"]
    assert CR.to_implement({**c, "validation_result": "OK"}, {2: {"supersedes": 1, "status": "effective"}}) == []


def test_change_from_draft_to_closed(world):
    doc = effective_doc(world)
    c = CC.create(world, JORDAN, {"title": "Move final inspection before packing", "kind": "process"})
    assert c["name"] == "CHG-00001"
    with pytest.raises(CC.ChangeError, match="still needed: what changes"):
        CC.submit(world, JORDAN, c["id"])
    with pytest.raises(CC.ChangeError, match="are not effective"):
        CC.update(world, JORDAN, c["id"], {"documents": [doc["id"] + 99]})
    CC.update(world, JORDAN, c["id"], {"description": "Inspect before sealing cartons", "reason": "Two escapes",
                                       "owner": LEE, "documents": [doc["id"]], "assessment": "Process only",
                                       **YES_NO, "regulatory_decision": "No submission: internal process",
                                       "validation_plan": "Run 3 lots with the new order"})
    CC.submit(world, LEE, c["id"])
    with pytest.raises(CC.ChangeError, match="cannot be changed now"):
        CC.update(world, JORDAN, c["id"], {"description": "x"})
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        world.execute("update changes set q_regulatory = 'no' where id = %s", (c["id"],))
    # the target date can still move, and the move is logged
    CC.update(world, LEE, c["id"], {"target_date": "2026-12-15"})
    for who in (JORDAN, LEE):              # raised and edited it; owns and submitted it
        with pytest.raises(PermissionError, match="did not raise, own, submit or edit"):
            CC.approve(world, u(world, who), c["id"], PW)
    with pytest.raises(Q.SignatureError):
        CC.approve(world, u(world, SAM), c["id"], "wrong")
    CC.approve(world, u(world, SAM), c["id"], PW)
    with pytest.raises(CC.ChangeError, match=r"how it was implemented.*validation result.*new revision of QP-08"):
        CC.implement(world, u(world, LEE), c["id"])
    _, data = file("QP-08 Control of Nonconforming Product Rev B")
    rev = LIB.new_revision(world, JORDAN, doc["id"], name="QP-08 Rev D.pdf", data=data, revision="D")
    CC.update(world, LEE, c["id"], {"revisions": [rev["id"]], "implementation": "QP-08 rev D issued",
                                    "validation_result": "3 lots, no escapes"})
    with pytest.raises(CC.ChangeError, match="new revision of QP-08, in effect"):
        CC.implement(world, u(world, LEE), c["id"])
    LIB.submit(world, JORDAN, rev["id"])
    LIB.approve(world, u(world, SAM), rev["id"], PW, T)
    with pytest.raises(PermissionError, match="the owner or Quality"):
        CC.implement(world, u(world, SAM), c["id"])
    CC.implement(world, u(world, LEE), c["id"])
    with pytest.raises(CC.ChangeError, match="effectiveness check"):
        CC.close(world, u(world, DANA), c["id"], PW)
    CC.update(world, LEE, c["id"], {"effectiveness": "No escapes in 6 weeks"})
    with pytest.raises(PermissionError, match="other than the owner"):
        CC.close(world, u(world, LEE), c["id"], PW)
    assert CC.close(world, u(world, DANA), c["id"], PW)["status"] == "closed"
    assert [s["meaning"] for s in Q.signatures(world, "change", c["id"])] == ["Change approved", "Change closed"]
    v = CC.view(world, c["id"], T)
    assert "target date: - -> 2026-12-15" in [h["note"] for h in v["history"]]
    with pytest.raises(psycopg.errors.RaiseException, match="closed"):
        world.execute("update changes set effectiveness = 'x' where id = %s", (c["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from changes")


def test_send_back_and_cancel(world):
    c = CC.create(world, JORDAN, {"title": "New label printer", "kind": "equipment", "description": "x", "reason": "y",
                                  "owner": LEE, "assessment": "z", "q_product": "no", "q_regulatory": "no",
                                  "q_risk": "no", "q_validation": "no"})
    CC.submit(world, JORDAN, c["id"])
    with pytest.raises(CC.ChangeError, match="say what"):
        CC.send_back(world, SAM, c["id"], "")
    CC.send_back(world, SAM, c["id"], "Say which lines")
    CC.update(world, SAM, c["id"], {"description": "Lines 1 and 2"})
    CC.submit(world, JORDAN, c["id"])
    # Sam edited it while it was a draft again: Sam does not approve it
    with pytest.raises(PermissionError):
        CC.approve(world, u(world, SAM), c["id"], PW)
    CC.approve(world, u(world, DANA), c["id"], PW)
    assert CC.cancel(world, JORDAN, c["id"], "Printer vendor withdrew")["status"] == "cancelled"
    with pytest.raises(CC.ChangeError, match="cannot be cancelled"):
        CC.cancel(world, JORDAN, c["id"], "again")
    assert [x["name"] for x in CC.listing(world, "open", T)] == []


def test_changes_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, JORDAN, LEE):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(LEE)
    assert c.post("/api/changes", json={"title": "x"}).status_code == 403
    login(JORDAN)
    cid = c.post("/api/changes", json={"title": "Faster dryer", "kind": "equipment"}).json()["id"]
    assert c.put(f"/api/changes/{cid}", json={"kind": "spaceship"}).status_code == 409
    v = c.put(f"/api/changes/{cid}", json={"description": "x", "reason": "y", "owner": LEE, "assessment": "z",
                                            "q_product": "no", "q_regulatory": "no", "q_risk": "no",
                                            "q_validation": "no"}).json()
    assert v["to_submit"] == []
    assert c.post(f"/api/changes/{cid}/submit").json()["status"] == "submitted"
    assert c.post(f"/api/changes/{cid}/approve", json={"password": PW}).status_code == 403
    login(DANA)
    assert c.post(f"/api/changes/{cid}/approve", json={"password": PW}).json()["status"] == "approved"
    assert c.post(f"/api/changes/{cid}/explode").status_code == 404
    assert c.get("/api/changes").json()["changes"][0]["name"] == "CHG-00001"
    c.__exit__(None, None, None)
