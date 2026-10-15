"""Risk management, step 17h (ADR-0017; dee-qms PLAN-RISK): acceptability looked up in the company's matrix ("not
determined" stops approval), controls required where the risk is not acceptable, a benefit-risk note where the
residual risk is unacceptable, approval by someone who did not own or edit the file (signed), fixed with the
criteria and a fingerprint, revised as a new version that supersedes the old, the criteria logged, the API.
Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_documents import DEMO, PW
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.quality import records as Q
from wqops.hub.quality import risk as R
from wqops.hub.quality import risk_rules as RR

DANA, SAM, JORDAN, LEE = "dana@demo.example", "sam@demo.example", "jordan@demo.example", "lee@demo.example"
M = RR.example_matrix()


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (DANA, SAM, JORDAN, LEE):
        Acc.set_password(conn, e, PW)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def test_rules():
    assert RR.verdict(M, 1, 1) == "acceptable" and RR.verdict(M, 3, 3) == "reduce"
    assert RR.verdict(M, 5, 4) == "unacceptable"
    assert RR.verdict(M, 6, 1) is None and RR.verdict(M, None, 2) is None
    it = {"seq": 1, "hazard": "Sharp edge", "harm": "Cut", "severity": 4, "probability": 4}
    assert RR.item_needs(it, M) == ["item 1: risk controls and how they were verified",
                                    "item 1: the residual risk is not determined"]
    it |= {"controls": "Deburr", "verification": "Inspection", "res_severity": 4, "res_probability": 3}
    assert RR.item_needs(it, M) == ["item 1: the residual risk is unacceptable: say why the benefit outweighs it"]
    assert RR.item_needs(it | {"res_probability": 2}, M) == []
    assert RR.item_needs({"seq": 2, "hazard": "x", "harm": "y", "severity": 9, "probability": 1}, M)[0].startswith(
        "item 2: the initial risk is not determined")
    assert RR.item_needs({"seq": 3, "hazard": "x", "harm": "y", "severity": 1, "probability": 1}, M) == []
    assert RR.to_approve({}, [], M) == ["at least one hazard", "the overall residual risk conclusion"]
    lv = [{"kind": "severity", "rank": 1, "name": "a"}, {"kind": "probability", "rank": 1, "name": "b"},
          {"kind": "probability", "rank": 2, "name": "c"}]
    assert RR.matrix_gaps(lv, {(1, 1): "acceptable"}) == ["S1 x P2"]
    crit = RR.criteria(lv, {(1, 1): "acceptable"})
    f = {"name": "RMF-00001", "version": 1, "product": "P"}
    assert RR.fingerprint(f, [it], crit) == RR.fingerprint(dict(f), [dict(it)], crit)
    assert RR.fingerprint(f, [it | {"harm": "Deep cut"}], crit) != RR.fingerprint(f, [it], crit)


def test_criteria_are_the_companys(world):
    R.load_example(world, SAM)
    with pytest.raises(R.RiskError, match="already has risk levels"):
        R.load_example(world, SAM)
    assert all(lv["description"] == RR.EXAMPLE_NOTE for lv in R.levels(world))
    assert R.matrix(world) == M
    with pytest.raises(R.RiskError, match="already a severity level 5"):
        R.add_level(world, SAM, {"kind": "severity", "rank": 5, "name": "x"})
    R.add_level(world, SAM, {"kind": "severity", "rank": 6, "name": "Fatal"})
    with pytest.raises(R.RiskError, match="both levels"):
        R.set_cell(world, SAM, 6, 9, "unacceptable")
    R.set_cell(world, SAM, 6, 1, "unacceptable")
    R.set_cell(world, SAM, 2, 2, "reduce")
    R.set_cell(world, SAM, 2, 2, None)
    assert (2, 2) not in R.matrix(world)
    notes = [h["note"] for h in R.criteria_history(world)]
    assert "S2 x P2: acceptable -> reduce" in notes and "S2 x P2: reduce -> -" in notes
    with pytest.raises(psycopg.errors.RaiseException, match="keeps its kind and rank"):
        world.execute("update risk_levels set rank = 7 where rank = 6 and kind = 'severity'")
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from risk_levels")


def test_file_from_draft_to_superseded(world):
    R.load_example(world, SAM)
    f = R.create(world, JORDAN, {"product": "Canine infusion pump", "owner": LEE})
    assert f["name"] == "RMF-00001"
    with pytest.raises(R.RiskError, match="rank of a severity level"):
        R.add_item(world, JORDAN, f["id"], {"hazard": "x", "severity": 9})
    with pytest.raises(R.RiskError, match="both the residual"):
        R.add_item(world, JORDAN, f["id"], {"hazard": "x", "res_severity": 2})
    a = R.add_item(world, JORDAN, f["id"], {"hazard": "Free flow", "situation": "Door opened mid-infusion",
                                            "harm": "Overdose", "severity": 5, "probability": 3})
    R.add_item(world, LEE, f["id"], {"hazard": "Label smudged", "harm": "Wrong drug", "severity": 2,
                                     "probability": 1})
    gone = R.add_item(world, LEE, f["id"], {"hazard": "Typo"})
    R.remove_item(world, LEE, f["id"], gone["id"])
    v = R.view(world, f["id"])
    assert [i["initial_verdict"] for i in v["items"]] == ["unacceptable", "acceptable"]
    assert v["to_approve"] == ["the overall residual risk conclusion",
                               "item 1: risk controls and how they were verified",
                               "item 1: the residual risk is not determined"]
    R.update_item(world, LEE, f["id"], a["id"], {"controls": "Anti-free-flow clamp", "verification": "Test report TR-9",
                                                 "res_severity": 4, "res_probability": 2})
    R.update(world, LEE, f["id"], {"conclusion": "Overall residual risk acceptable"})
    for who in (JORDAN, LEE):          # raised and edited it; owns it
        with pytest.raises(PermissionError, match="does not own and did not edit"):
            R.approve(world, u(world, who), f["id"], PW)
    with pytest.raises(Q.SignatureError):
        R.approve(world, u(world, SAM), f["id"], "wrong")
    # the matrix changed meanwhile: 4 x 2 is now unacceptable, so the benefit must be stated first
    R.set_cell(world, SAM, 4, 2, "unacceptable")
    with pytest.raises(R.RiskError, match="say why the benefit outweighs it"):
        R.approve(world, u(world, DANA), f["id"], PW)
    R.update_item(world, LEE, f["id"], a["id"], {"benefit_risk": "Therapy outweighs the remaining risk"})
    R.approve(world, u(world, DANA), f["id"], PW)
    v = R.view(world, f["id"])
    assert v["status"] == "approved" and v["intact"] is True
    assert [(i["initial_verdict"], i["residual_verdict"]) for i in v["items"]] == [
        ("unacceptable", "unacceptable"), ("acceptable", "acceptable")]
    assert [4, 2, "unacceptable"] in v["criteria"]["matrix"]
    assert [s["meaning"] for s in v["signatures"]] == ["Risk management file approved"]
    with pytest.raises(R.RiskError, match="start a new version"):
        R.update(world, LEE, f["id"], {"scope": "x"})
    with pytest.raises(psycopg.errors.RaiseException, match="items are fixed"):
        world.execute("update risk_items set harm = 'x' where file_id = %s", (f["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        world.execute("update risk_files set conclusion = 'x' where id = %s", (f["id"],))
    with pytest.raises(R.RiskError, match="its name stays"):
        R.update_level(world, SAM, R.levels(world)[4]["id"], {"name": "Deadly"})   # severity 5, used
    # changing the criteria later does not change what was approved
    R.set_cell(world, SAM, 2, 1, "reduce")
    assert R.view(world, f["id"])["intact"] is True

    v2 = R.revise(world, LEE, f["id"])
    assert (v2["name"], v2["version"]) == ("RMF-00001", 2)
    with pytest.raises(R.RiskError, match="already being drafted"):
        R.revise(world, LEE, f["id"])
    with pytest.raises(psycopg.errors.UniqueViolation):
        world.execute("insert into risk_files (name, version, previous_id, product, created_by) values "
                      "('RMF-00001', 3, %s, 'x', 'x')", (f["id"],))
    world.rollback()
    v = R.view(world, v2["id"])
    assert [i["hazard"] for i in v["items"]] == ["Free flow", "Label smudged"]
    assert v["to_approve"] == ["item 2: risk controls and how they were verified",   # 2 x 1 is "reduce" now
                               "item 2: the residual risk is not determined"]
    R.update_item(world, LEE, v2["id"], v["items"][1]["id"], {"controls": "Laminated label", "verification": "Rub test",
                                                              "res_severity": 1, "res_probability": 1})
    R.approve(world, u(world, SAM), v2["id"], PW)
    assert R.get(world, f["id"])["status"] == "superseded"
    assert [x["status"] for x in R.view(world, v2["id"])["versions"]] == ["superseded", "approved"]
    assert R.summary(world, dt.date(2000, 1, 1), dt.date(2999, 1, 1)) == {
        "approved": 2, "residual_not_acceptable": 1, "drafts": 0}
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from risk_files")


def test_withdraw_a_draft(world):
    R.load_example(world, SAM)
    f = R.create(world, JORDAN, {"product": "Feline thermometer"})
    with pytest.raises(R.RiskError, match="give the reason"):
        R.withdraw(world, JORDAN, f["id"], " ")
    assert R.withdraw(world, JORDAN, f["id"], "Product dropped")["status"] == "withdrawn"
    with pytest.raises(R.RiskError, match="withdrawn"):
        R.add_item(world, JORDAN, f["id"], {"hazard": "x"})
    assert R.create(world, JORDAN, {"product": "Other"})["name"] == "RMF-00002"
    assert [x["product"] for x in R.listing(world, "current")] == ["Other"]


def test_risk_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, JORDAN, LEE):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(LEE)
    assert c.post("/api/risk/example").status_code == 403
    login(DANA)
    v = c.post("/api/risk/example").json()
    assert len(v["levels"]) == 10 and v["gaps"] == []
    assert c.put("/api/risk/matrix", json={"severity": 1, "probability": 1, "verdict": "maybe"}).status_code == 409
    login(JORDAN)
    fid = c.post("/api/risk/files", json={"product": "Canine collar sensor"}).json()["id"]
    v = c.post(f"/api/risk/files/{fid}/items", json={"hazard": "Battery heat", "harm": "Burn", "severity": 2,
                                                     "probability": 2}).json()
    assert v["items"][0]["initial_verdict"] == "acceptable"
    v = c.put(f"/api/risk/files/{fid}", json={"conclusion": "Acceptable"}).json()
    assert v["to_approve"] == []
    assert c.post(f"/api/risk/files/{fid}/approve", json={"password": PW}).status_code == 403
    login(DANA)
    v = c.post(f"/api/risk/files/{fid}/approve", json={"password": PW}).json()
    assert v["status"] == "approved" and v["intact"] is True
    assert c.post(f"/api/risk/files/{fid}/explode").status_code == 404
    assert c.get("/api/risk").json()["files"][0]["name"] == "RMF-00001"
    c.__exit__(None, None, None)


def test_review_fixes(world):
    """Withdrawn drafts keep their version number; a level no longer in use decides nothing; the database keeps
    approval signed and superseding earned."""
    R.load_example(world, SAM)
    f = R.create(world, JORDAN, {"product": "Equine scale"})
    it = R.add_item(world, JORDAN, f["id"], {"hazard": "Tip over", "harm": "Bruise", "severity": 4,
                                             "probability": 1})
    R.update(world, JORDAN, f["id"], {"conclusion": "Acceptable"})
    with pytest.raises(psycopg.errors.RaiseException, match="signature"):
        world.execute("update risk_files set status = 'approved', approved_by = %s, approved_at = now(), "
                      "criteria = '{}', fingerprint = 'x' where id = %s", (DANA, f["id"]))
    s4 = next(lv for lv in R.levels(world) if lv["kind"] == "severity" and lv["rank"] == 4)
    R.update_level(world, SAM, s4["id"], {"active": False})
    assert R.view(world, f["id"])["to_approve"][0].startswith("item 1: the initial risk is not determined")
    R.update_item(world, JORDAN, f["id"], it["id"], {"hazard": "Tips over", "severity": 4})   # unchanged rank: kept
    R.update_level(world, SAM, s4["id"], {"active": True})
    R.approve(world, u(world, DANA), f["id"], PW)
    with pytest.raises(psycopg.errors.RaiseException, match="superseded only by an approved newer version"):
        world.execute("update risk_files set status = 'superseded' where id = %s", (f["id"],))
    v2 = R.revise(world, JORDAN, f["id"])
    R.withdraw(world, JORDAN, v2["id"], "Not now")
    v3 = R.revise(world, JORDAN, f["id"])
    assert v3["version"] == 3
    R.approve(world, u(world, DANA), v3["id"], PW)
    assert [x["status"] for x in R.view(world, v3["id"])["versions"]] == ["superseded", "withdrawn", "approved"]
