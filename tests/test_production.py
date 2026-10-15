"""Production records, step 17i (ADR-0017; dee-qms PLAN-DHR): templates activated by someone else and then fixed,
a lot started from the active template, steps recorded in order and signed, measurements judged against the limits
(limits included), equipment in calibration, reading confirmed, a failed step needing a nonconformance report,
material lots from released incoming inspections never over-used, release by someone who recorded nothing, held by
an open out-of-tolerance assessment, the record fixed with a fingerprint, the API. Fictional data only."""

import datetime as dt
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_calibration import calibrate, caliper
from tests.test_doc_control import in_review
from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, inspect, plan, receipts, table
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.docs import control as CTL
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP
from wqops.hub.quality import iqc as I
from wqops.hub.quality import prod_rules as PR
from wqops.hub.quality import production as PRD
from wqops.hub.quality import records as Q

SAM, LEE = "sam@demo.example", "lee@demo.example"
T = AS_OF


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA, LEE):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=receipts(business()).transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


STEPS = [{"name": "Visual check", "kind": "check"},
         {"name": "Shaft diameter", "kind": "measure", "low": 9.95, "high": 10.05, "unit": "mm"},
         {"name": "Torque note", "kind": "record"}]


def active_template(conn, materials=("BOLT-B",)):
    t = PRD.create_template(conn, JORDAN, {"code": "wa-asm", "item_code": "WIDGET-A", "title": "Widget assembly"})
    for s in STEPS:
        PRD.add_step(conn, JORDAN, t["id"], s)
    PRD.update_template(conn, JORDAN, t["id"], {"materials": list(materials)})
    return PRD.activate(conn, u(conn, SAM), t["id"], PW)


def bolt_lot(conn):
    """A released incoming lot of BOLT-B (100 pieces)."""
    table(conn)
    plan(conn)
    return inspect(conn, "PR-7", [10.0, 10.0, 10.0])


def test_rules():
    m = {"kind": "measure", "low": 9.95, "high": 10.05}
    assert PR.judge(m, value=9.95) == ("pass", "") and PR.judge(m, value="10.05")[0] == "pass"
    assert PR.judge(m, value=10.0500004)[0] == "pass"          # judged as stored, six places
    assert PR.judge(m, value=10.051)[0] == "fail"
    for bad in (None, "", True, "x", float("nan"), float("inf")):
        assert PR.judge(m, value=bad)[0] is None
    assert PR.judge({"kind": "check"}, result="fail") == ("fail", "")
    assert PR.judge({"kind": "record"}, text=" ")[0] is None
    assert PR.stored(1.23456789) == Decimal("1.234568")
    assert PR.template_needs({}, [{"seq": 1, "kind": "measure"}]) == ["step 1: a lower or upper limit"]
    rec = {"good_qty": 0, "scrap_qty": 0, "planned_qty": 5}
    assert PR.to_submit(rec, [{"seq": 1, "done_by": None}, {"seq": 2, "done_by": "x", "verdict": "fail",
                                                              "ncr_id": None}], [], ["BOLT-B"], {}) == [
        "steps 1 recorded", "the good quantity", "a nonconformance report for step 2",
        "the material lot of BOLT-B used"]
    assert PR.to_release([{"seq": 2, "verdict": "fail", "ncr_id": 7}], {7: "open"}, ["CAL-01"]) == [
        "the nonconformance report for step 2 closed", "the out-of-tolerance assessment of CAL-01 signed"]


def test_templates_are_controlled(world):
    t = PRD.create_template(world, JORDAN, {"code": "wa-asm", "item_code": "WIDGET-A"})
    assert t["code"] == "WA-ASM"
    with pytest.raises(PRD.ProdError, match="not an item in ERPNext"):
        PRD.create_template(world, JORDAN, {"code": "x", "item_code": "NOPE"})
    with pytest.raises(PRD.ProdError, match="lower limit is above"):
        PRD.add_step(world, JORDAN, t["id"], {"name": "x", "kind": "measure", "low": 2, "high": 1})
    s = PRD.add_step(world, JORDAN, t["id"], {"name": "Diameter", "kind": "measure"})
    with pytest.raises(PermissionError, match="did not draft or edit"):
        PRD.activate(world, u(world, JORDAN), t["id"], PW)
    with pytest.raises(PRD.ProdError, match="step 1: a lower or upper limit"):
        PRD.activate(world, u(world, SAM), t["id"], PW)
    PRD.update_step(world, JORDAN, t["id"], s["id"], {"high": 5})
    a = PRD.activate(world, u(world, SAM), t["id"], PW)
    assert a["status"] == "active" and PRD.template_view(world, t["id"])["intact"] is True
    with pytest.raises(PRD.ProdError, match="start a new version"):
        PRD.add_step(world, JORDAN, t["id"], {"name": "y"})
    with pytest.raises(psycopg.errors.RaiseException, match="steps are fixed"):
        world.execute("update prod_template_steps set high = 9 where template_id = %s", (t["id"],))
    v2 = PRD.new_version(world, LEE, t["id"])
    with pytest.raises(PRD.ProdError, match="already being drafted"):
        PRD.new_version(world, LEE, t["id"])
    PRD.add_step(world, LEE, v2["id"], {"name": "Label", "kind": "check"})
    PRD.activate(world, u(world, SAM), v2["id"], PW)
    assert [x["status"] for x in PRD.template_view(world, v2["id"])["versions"]] == ["retired", "active"]
    with pytest.raises(psycopg.errors.RaiseException, match="signature"):
        PRD.create_template(world, JORDAN, {"code": "b", "item_code": "BOLT-B"})
        world.execute("update prod_templates set status = 'active', activated_by = %s, activated_at = now(), "
                      "fingerprint = 'x' where code = 'B'", (DANA,))


def test_lot_from_start_to_release(world):
    lot = bolt_lot(world)
    assert lot["status"] == "released"
    t = active_template(world)
    r = PRD.start(world, JORDAN, {"template_id": t["id"], "lot_no": " L-001 ", "planned_qty": 10})
    with pytest.raises(PRD.ProdError, match="already has a production record"):
        PRD.start(world, JORDAN, {"template_id": t["id"], "lot_no": "l-001", "planned_qty": 10})
    rid = r["id"]
    with pytest.raises(PRD.ProdError, match="record step 1 first"):
        PRD.record_step(world, u(world, JORDAN), rid, 2, PW, {"value": 10}, today=T)
    with pytest.raises(Q.SignatureError):
        PRD.record_step(world, u(world, JORDAN), rid, 1, "wrong", {"result": "pass"}, today=T)
    PRD.record_step(world, u(world, JORDAN), rid, 1, PW, {"result": "pass"}, today=T)
    PRD.record_step(world, u(world, LEE), rid, 2, PW, {"value": 10.06}, today=T)
    PRD.record_step(world, u(world, JORDAN), rid, 3, PW, {"text": "Torqued to 2 N·m"}, today=T)
    with pytest.raises(psycopg.errors.RaiseException, match="recorded"):
        world.execute("update prod_steps set value = 10 where record_id = %s and seq = 2", (rid,))
    v = PRD.view(world, rid)
    assert [s["verdict"] for s in v["steps"]] == ["pass", "fail", "pass"]
    with pytest.raises(PRD.ProdError, match="a lot that incoming inspection released"):
        PRD.add_material(world, JORDAN, rid, lot["id"] + 99, 5)
    with pytest.raises(PRD.ProdError, match="held 100"):
        PRD.add_material(world, JORDAN, rid, lot["id"], 101)
    PRD.add_material(world, JORDAN, rid, lot["id"], 60)
    with pytest.raises(PRD.ProdError, match="60 is already used"):
        PRD.add_material(world, JORDAN, rid, lot["id"], 41)
    with pytest.raises(PRD.ProdError, match="at most the quantity planned"):
        PRD.set_quantities(world, JORDAN, rid, {"good_qty": 9, "scrap_qty": 2})
    PRD.set_quantities(world, JORDAN, rid, {"good_qty": 9, "scrap_qty": 1, "work_order": "WO-0001"})
    with pytest.raises(PRD.ProdError, match="a nonconformance report for step 2"):
        PRD.submit(world, JORDAN, rid)
    with pytest.raises(PRD.ProdError, match="for a failed step"):
        PRD.step_ncr(world, JORDAN, rid, 1)
    n = PRD.step_ncr(world, JORDAN, rid, 2)
    assert "step 2 Shaft diameter failed" in n["title"]
    PRD.submit(world, JORDAN, rid)
    with pytest.raises(psycopg.errors.RaiseException, match="quantities are fixed"):
        world.execute("update prod_records set good_qty = 10 where id = %s", (rid,))
    for who in (JORDAN, LEE):              # they recorded in it
        with pytest.raises(PermissionError, match="recorded no step or material"):
            PRD.decide(world, u(world, who), rid, PW, True)
    with pytest.raises(PRD.ProdError, match="nonconformance report for step 2 closed"):
        PRD.decide(world, u(world, DANA), rid, PW, True)
    world.execute("update ncr_records set status = 'closed', closed_by = %s, closed_at = now() where id = %s",
                  (SAM, n["id"]))
    with pytest.raises(PRD.ProdError, match="reason for rejecting"):
        PRD.decide(world, u(world, DANA), rid, PW, False)
    done = PRD.decide(world, u(world, DANA), rid, PW, True, "Diameter deviation accepted by NCR")
    assert done["status"] == "released"
    v = PRD.view(world, rid)
    assert v["intact"] is True and [s["meaning"] for s in v["signatures"]] == ["Lot released"]
    with pytest.raises(psycopg.errors.RaiseException, match="released"):
        world.execute("update prod_records set decision_note = 'x' where id = %s", (rid,))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from prod_materials")
    s = PRD.summary(world, dt.date(2000, 1, 1), dt.date(2999, 1, 1))
    assert s == {"released": 1, "rejected": 0, "first_pass": 0.0, "in_production": 0}


def test_equipment_and_reading(world):
    g = caliper(world)
    calibrate(world, g["id"], T - dt.timedelta(days=30))
    doc = in_review(world)
    LIB.approve(world, u(world, SAM), doc["id"], PW, T)
    doc = LIB.get(world, doc["id"])
    CTL.set_training(world, SAM, doc["id"], {"roles": doc["trainees"]["roles"],
                                             "people": [*doc["trainees"]["people"], JORDAN]}, True, today=T)
    t = PRD.create_template(world, LEE, {"code": "wa", "item_code": "WIDGET-A"})
    PRD.add_step(world, LEE, t["id"], {"name": "Diameter", "kind": "measure", "low": 1, "high": 2,
                                       "gauge_required": True})
    PRD.update_template(world, LEE, t["id"], {"documents": [doc["number"]]})
    PRD.activate(world, u(world, SAM), t["id"], PW)
    rid = PRD.start(world, JORDAN, {"template_id": t["id"], "lot_no": "L-9", "planned_qty": 1})["id"]
    with pytest.raises(PRD.ProdError, match=f"confirm reading {doc['number']}"):
        PRD.record_step(world, u(world, JORDAN), rid, 1, PW, {"value": 1.5, "gauge_id": g["id"]}, today=T)
    task = next(x for x in CTL.training(world, email=JORDAN, today=T) if x["document_id"] == doc["id"])
    CTL.acknowledge(world, u(world, JORDAN), task["id"], PW)
    with pytest.raises(PRD.ProdError, match="name the equipment"):
        PRD.record_step(world, u(world, JORDAN), rid, 1, PW, {"value": 1.5}, today=T)
    PRD.record_step(world, u(world, JORDAN), rid, 1, PW, {"value": 1.5, "gauge_id": g["id"]}, today=T)
    PRD.set_quantities(world, JORDAN, rid, {"good_qty": 1})
    # the caliper is found out of tolerance: the lot it measured is held until the assessment is signed
    calibrate(world, g["id"], T - dt.timedelta(days=1), result="fail")
    assert PRD.on_hold(world, rid) == ["CAL-01"]
    with pytest.raises(PRD.ProdError, match="out-of-tolerance assessment of CAL-01"):
        PRD.submit(world, JORDAN, rid)
    imp = world.execute("select id from gauge_impacts").fetchone()
    from wqops.hub.quality import calibration as CAL

    CAL.assess(world, u(world, SAM), imp["id"], PW, "Within tolerance of the step")
    PRD.submit(world, JORDAN, rid)
    assert I.settings(world)["production_training"] is True


def test_production_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=receipts(business()).transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, JORDAN, LEE):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=receipts(business()).transport()))
        OP.project(conn, manifest=DEMO)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(LEE)
    assert c.post("/api/production/templates", json={"code": "x", "item_code": "WIDGET-A"}).status_code == 403
    login(JORDAN)
    tid = c.post("/api/production/templates", json={"code": "wa", "item_code": "WIDGET-A"}).json()["id"]
    v = c.post(f"/api/production/templates/{tid}/steps", json={"name": "Look", "kind": "check"}).json()
    assert v["to_activate"] == []
    assert c.post(f"/api/production/templates/{tid}/activate", json={"password": PW}).status_code == 403
    login(DANA)
    assert c.post(f"/api/production/templates/{tid}/activate", json={"password": PW}).json()["status"] == "active"
    login(JORDAN)
    rid = c.post("/api/production/records", json={"template_id": tid, "lot_no": "A1", "planned_qty": 2}).json()["id"]
    v = c.post(f"/api/production/records/{rid}/steps/1", json={"password": PW, "result": "pass"}).json()
    assert v["steps"][0]["verdict"] == "pass" and v["next_step"] is None
    c.put(f"/api/production/records/{rid}", json={"good_qty": 2})
    assert c.post(f"/api/production/records/{rid}/submit").json()["status"] == "qa_review"
    login(DANA)
    assert c.post(f"/api/production/records/{rid}/release", json={"password": PW}).json()["status"] == "released"
    assert c.post(f"/api/production/records/{rid}/explode").status_code == 404
    assert c.get("/api/production?status=released").json()["records"][0]["lot_no"] == "A1"
    c.__exit__(None, None, None)


def test_review_fixes(world):
    # a cancelled report does not let a failed step through; odd input is refused, not a crash
    assert PR.to_release([{"seq": 1, "verdict": "fail", "ncr_id": 7}], {7: "cancelled"}, []) == [
        "the nonconformance report for step 1 closed"]
    assert PR.stored("1e30") is None and PR.stored(10**20) is None
    assert PR.judge({"kind": "record"}, text=5)[0] is None
    t = active_template(world, materials=())
    rid = PRD.start(world, JORDAN, {"template_id": t["id"], "lot_no": "Z1", "planned_qty": 1})["id"]
    with pytest.raises(psycopg.errors.RaiseException, match="starts in production"):
        world.execute("insert into prod_records (name, template_id, template_print, item_code, lot_no, planned_qty, "
                      "status, created_by) values ('X', %s, %s, 'WIDGET-A', 'Z2', 1, 'released', 'x')",
                      (t["id"], t["fingerprint"]))
    with pytest.raises(psycopg.errors.RaiseException, match="starts as a draft"):
        world.execute("insert into prod_templates (code, item_code, status, created_by) values ('Q', 'X', 'active', "
                      "'x')")
    with pytest.raises(psycopg.errors.RaiseException, match="added when a lot starts"):
        world.execute("insert into prod_steps (record_id, seq, name, kind, verdict, done_by, done_at) values "
                      "(%s, 9, 'x', 'check', 'pass', 'x', now())", (rid,))
    # a code whose only version was retired can be drafted again
    PRD.end_template(world, SAM, t["id"], "Line moved")
    assert PRD.new_version(world, LEE, t["id"])["version"] == 2
