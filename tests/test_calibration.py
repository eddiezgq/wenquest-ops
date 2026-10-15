"""Measuring equipment and calibration, step 17f (ADR-0017; dee-qms PLAN-CAL): equipment out of service until its
first good calibration is approved by someone else; out-of-tolerance results taking it out of use and listing what it
measured for a signed assessment; incoming inspection naming equipment in calibration when the inspector signs; the
ISO calibration check; the API. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import AS_OF, CHARS, DANA, DEMO, JORDAN, PW, approved, receipts, table
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import cal_rules as CR
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS

SAM = "sam@demo.example"
T = AS_OF


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, DANA, SAM):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=receipts(business()).transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def caliper(conn, months=12):
    return CAL.add(conn, JORDAN, "CAL-01", {"name": "Digital caliper 150 mm", "interval_months": months})


def calibrate(conn, gid, day, result="pass", by=JORDAN, approver=SAM):
    c = CAL.record(conn, by, gid, {"done_on": str(day), "done_by": "Metro Lab (Demo)", "result": result}, today=T)
    return CAL.approve(conn, u(conn, approver), c["id"], PW, today=T)


def started(conn, receipt="PR-7"):
    table(conn)
    approved(conn)
    p = I.new_plan(conn, JORDAN, "BOLT-B", 1.0, CHARS)
    I.enable_plan(conn, u(conn, DANA), p["id"], PW)
    ins = I.start(conn, JORDAN, "BOLT-B", receipt=receipt, today=T)
    I.enter(conn, JORDAN, ins["id"], [{"sample": s, "characteristic": "Length", "value": 10.0} for s in (1, 2, 3)]
            + [{"sample": s, "characteristic": "Finish", "passed": True} for s in (1, 2, 3)])
    return ins


def test_rules():
    g = {"code": "G1", "status": "in_service", "next_due": T}
    assert CR.usable(g, T) == (True, f"G1, calibrated, due {T}")
    assert CR.usable(g, T + dt.timedelta(days=1)) == (False, f"G1 was due for calibration on {T}")
    assert CR.usable({**g, "status": "out_of_service"}, T)[1] == "G1 is out of service"
    assert CR.add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)


def test_calibration_approved_by_someone_else(world):
    g = caliper(world)
    with pytest.raises(CAL.CalError, match="already exists"):
        CAL.add(world, JORDAN, "cal-01", {"name": "x", "interval_months": 6})
    assert g["status"] == "out_of_service"
    c = CAL.record(world, JORDAN, g["id"], {"done_on": str(T), "done_by": "Metro Lab (Demo)", "result": "pass"},
                   today=T)
    with pytest.raises(PermissionError, match="someone other than whoever recorded"):
        CAL.approve(world, u(world, JORDAN), c["id"], PW, today=T)
    CAL.change_calibration(world, u(world, DANA), c["id"], {"certificate": "MLD-4471"}, today=T)
    with pytest.raises(PermissionError, match="last changed"):
        CAL.approve(world, u(world, DANA), c["id"], PW, today=T)
    with pytest.raises(Q.SignatureError):
        CAL.approve(world, u(world, SAM), c["id"], "wrong", today=T)
    ok = CAL.approve(world, u(world, SAM), c["id"], PW, today=T)
    assert (ok["status"], ok["last_pass"], ok["next_due"]) == ("in_service", T, CR.add_months(T, 12))
    with pytest.raises(psycopg.errors.RaiseException, match="approved"):
        world.execute("update gauge_calibrations set result = 'fail' where id = %s", (c["id"],))
    old = CAL.record(world, JORDAN, g["id"], {"done_on": str(T - dt.timedelta(days=30)), "done_by": "x",
                                              "result": "pass"}, today=T)
    with pytest.raises(CAL.CalError, match="this one is older"):
        CAL.approve(world, u(world, SAM), old["id"], PW, today=T)
    # a shorter interval moves the due date
    assert CAL.change(world, DANA, g["id"], {"interval_months": 6})["next_due"] == CR.add_months(T, 6)
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("delete from gauges")


def test_inspection_names_equipment_in_calibration(world):
    ins = started(world)
    g = caliper(world)
    # equipment is registered now: the measured characteristic names it
    with pytest.raises(I.IqcError, match="name the equipment used for: Length"):
        I.sign(world, u(world, JORDAN), ins["id"], PW, today=T)
    with pytest.raises(I.IqcError, match="out of service"):
        I.set_gauge(world, JORDAN, ins["id"], "Length", g["id"], today=T)
    with pytest.raises(I.IqcError, match="measured characteristic"):
        I.set_gauge(world, JORDAN, ins["id"], "Finish", g["id"], today=T)
    calibrate(world, g["id"], T - dt.timedelta(days=400))
    # its last good calibration was over a year ago: overdue
    with pytest.raises(I.IqcError, match="was due for calibration"):
        I.set_gauge(world, JORDAN, ins["id"], "Length", g["id"], today=T)
    calibrate(world, g["id"], T - dt.timedelta(days=5))
    I.set_gauge(world, JORDAN, ins["id"], "Length", g["id"], today=T)
    # overdue by the day the inspector signs: refused
    with pytest.raises(I.IqcError, match="Length: CAL-01 was due"):
        I.sign(world, u(world, JORDAN), ins["id"], PW, today=T + dt.timedelta(days=400))
    I.sign(world, u(world, JORDAN), ins["id"], PW, today=T)
    used = I.view(world, ins["id"])["gauges"]["Length"]
    due = CR.add_months(T - dt.timedelta(days=5), 12).isoformat()
    assert used["gauge_code"] == "CAL-01" and used["next_due"] == due
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        world.execute("delete from iqc_gauges")
    # the company's choice: switched off, equipment is not asked for
    I.set_setting(world, DANA, "gauge_required", False)
    ins2 = I.start(world, JORDAN, "BOLT-B", receipt="PR-8", today=T)
    I.enter(world, JORDAN, ins2["id"], [{"sample": s, "characteristic": "Length", "value": 10.0} for s in (1, 2, 3)]
            + [{"sample": s, "characteristic": "Finish", "passed": True} for s in (1, 2, 3)])
    assert I.sign(world, u(world, JORDAN), ins2["id"], PW, today=T)["status"] == "judged"


def test_out_of_tolerance(world):
    ins = started(world)
    g = caliper(world)
    calibrate(world, g["id"], T - dt.timedelta(days=30))
    I.set_gauge(world, JORDAN, ins["id"], "Length", g["id"], today=T)
    I.sign(world, u(world, JORDAN), ins["id"], PW, today=T)
    out = calibrate(world, g["id"], T - dt.timedelta(days=10), result="fail")
    assert out["status"] == "out_of_service"
    imp = CAL.view(world, g["id"], T)["impacts"][0]
    assert imp["status"] == "open" and [x["name"] for x in imp["inspections"]] == [ins["name"]]
    assert imp["since"] == (T - dt.timedelta(days=30)).isoformat()
    # a good calibration from before the failure does not count; nor does the state change by hand
    with pytest.raises(CAL.CalError, match="must be after that"):
        calibrate(world, g["id"], T - dt.timedelta(days=12))
    with pytest.raises(psycopg.errors.RaiseException, match="stays out of service"):
        world.execute("update gauges set status = 'in_service' where id = %s", (g["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="approved calibration"):
        world.execute("update gauges set last_pass = %s where id = %s", (T, g["id"]))
    # a good calibration after it does not bring it back while the assessment is open
    assert calibrate(world, g["id"], T)["status"] == "out_of_service"
    with pytest.raises(CAL.CalError, match="conclusion"):
        CAL.assess(world, u(world, SAM), imp["id"], PW, "")
    back = CAL.assess(world, u(world, SAM), imp["id"], PW, "Readings were 0.01 mm off; within tolerance of the "
                                                          "characteristic: results stand", open_ncr=True)
    assert back["status"] == "in_service"
    done = CAL.view(world, g["id"], T)["impacts"][0]
    assert done["status"] == "assessed" and Q.ncr(world, done["ncr_id"])["title"] == "Out-of-tolerance equipment CAL-01"
    with pytest.raises(psycopg.errors.RaiseException, match="signed"):
        world.execute("update gauge_impacts set conclusion = 'x' where id = %s", (imp["id"],))


def test_named_equipment_is_checked_even_when_not_required(world):
    ins = started(world)
    g = caliper(world)
    calibrate(world, g["id"], T - dt.timedelta(days=30))
    I.set_gauge(world, JORDAN, ins["id"], "Length", g["id"], today=T)
    calibrate(world, g["id"], T - dt.timedelta(days=1), result="fail")
    I.set_setting(world, DANA, "gauge_required", False)
    with pytest.raises(I.IqcError, match="out of service"):
        I.sign(world, u(world, JORDAN), ins["id"], PW, today=T)


def test_iso_calibration_check_reads_equipment(world):
    QMS.enable(world, u(world, JORDAN), "iso9001", "2015", PW, T)
    g = caliper(world)
    calibrate(world, g["id"], T - dt.timedelta(days=30))
    QMS.evaluate(world, "iso9001", T, "manual", JORDAN)
    r = QMS.latest(world, "iso9001")["results"]["measuring"]
    assert r["status"] == "met" and r["evidence"][0]["id"] == f"g{g['id']}"
    calibrate(world, g["id"], T - dt.timedelta(days=2), result="fail")
    QMS.evaluate(world, "iso9001", T, "manual", JORDAN)
    r = QMS.latest(world, "iso9001")["results"]["measuring"]
    assert r["status"] == "not_met" and r["problems"][0]["why"] == "failed its last calibration"


def test_gauges_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (JORDAN, SAM, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.post("/api/gauges", json={"code": "G", "name": "x", "interval_months": 12}).status_code == 403
    login(JORDAN)
    gid = c.post("/api/gauges", json={"code": "G-1", "name": "Scale", "interval_months": 12}).json()["id"]
    assert c.post("/api/gauges", json={"code": "G-2", "name": "Scale", "interval_months": 0}).status_code == 409
    v = c.post(f"/api/gauges/{gid}/calibrations", json={"done_on": str(T), "done_by": "Lab", "result": "pass"}).json()
    cid = v["calibrations"][0]["id"]
    assert c.post(f"/api/gauge-calibrations/{cid}/approve", json={"password": PW}).status_code == 403
    login(SAM)
    assert c.post(f"/api/gauge-calibrations/{cid}/approve", json={"password": PW}).status_code == 403   # ops manager
    assert c.get(f"/api/gauges/{gid}").json()["status"] == "out_of_service"
    login(DANA)
    assert c.post(f"/api/gauge-calibrations/{cid}/approve", json={"password": PW}).json()["status"] == "in_service"
    assert c.get("/api/gauges/999999").status_code == 404
    c.__exit__(None, None, None)
