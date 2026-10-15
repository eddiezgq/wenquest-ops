"""Quality registers, step 16b (ADR-0016): register definitions from the pack, entries checked by their fields,
signed registers locked after approval, voiding with a reason, history kept, the checks on each register (unknown
when empty), suppliers bought from against the approval register, old spreadsheets brought in with the ledger import,
the API and permissions. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, PW
from tests.test_metrics import build
from wqops.demo import documents as DD
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import ledgers as LS
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS
from wqops.hub.system import registers as RG
from wqops.hub.system import rules as R

JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
T = AS_OF
D = dt.date
SET = R.defaults(QMS.load("iso9001"))


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
    return conn


def facts(regs=None, **kw):
    return {"today": T, "since": T - dt.timedelta(days=365), "registers": regs or {}} | kw


def e(i, signed=False, imported=False, **values):
    return {"id": i, "values": values, "signed": signed, "imported": imported}


# ---------------------------------------------------------------- definitions and values

def test_register_definitions_and_values():
    regs = RG.specs()
    assert RG.check_specs(regs) == [] and set(regs) == {"training", "calibration", "audits", "management_reviews",
                                                        "objectives", "risks", "complaints", "suppliers"}
    assert RG.check_specs({"Bad": {"label": "", "fields": {"x": {"type": "colour"}}, "key": ["y"]}}) == [
        "register Bad: a name of lower-case letters and a label", "register Bad, field x: a label and a type (text, "
        "longtext, number, date, choice, yesno)", "register Bad: key y is not a field"]
    s = RG.spec("audits")
    v = RG.clean(s, {"audit_date": "2026-09-30 00:00", "area": " Receiving ", "auditor": "Jordan",
                     "nonconformities": "2", "followed_up": "Yes", "findings": ""})
    assert v == {"audit_date": "2026-09-30", "area": "Receiving", "auditor": "Jordan", "nonconformities": 2,
                 "followed_up": True}
    for bad, msg in [({"audit_date": "30/09"}, "Audit date: a date"), ({"nonconformities": "nan"}, "a number"),
                     ({"followed_up": "maybe"}, "yes or no"), ({"colour": "red"}, "no field 'colour'")]:
        with pytest.raises(RG.RegisterError, match=msg):
            RG.clean(s, {**v, **bad})
    with pytest.raises(RG.RegisterError, match="still needed: Process or area audited, Auditor"):
        RG.clean(s, {"audit_date": "2026-09-30"})
    assert RG.clean(RG.spec("suppliers"), {"supplier": "Gulf", "status": "APPROVED", "approved_on": "2026-01-02"})[
        "status"] == "approved"
    with pytest.raises(RG.RegisterError, match="one of approved, conditional, removed"):
        RG.clean(RG.spec("suppliers"), {"supplier": "Gulf", "status": "ok", "approved_on": "2026-01-02"})


# ---------------------------------------------------------------- the checks, on facts

def test_register_checks():
    for rule in (R.training_current, R.calibration_current, R.audits_done, R.reviews_done, R.objectives_reviewed,
                 R.risks_reviewed, R.suppliers_approved):
        assert rule(facts(), SET)["status"] == "unknown"                    # an empty register is not "met"
    tr = [e(1, person="Lee", topic="QP-05", trained_on="2025-01-01", valid_until="2026-01-01"),
          e(2, person="Lee", topic="QP-05", trained_on="2026-02-01"),                    # the latest counts
          e(3, person="Pat", topic="QP-04", trained_on="2026-01-01", result="needs follow-up"),
          e(4, person="Ana", topic="QP-04", trained_on="2025-01-01", valid_until="2026-03-01")]
    out = R.training_current(facts({"training": tr}), SET)
    assert {p["id"]: p["why"] for p in out["problems"]} == {3: "needs follow-up since 2026-01-01",
                                                             4: "expired on 2026-03-01"}
    assert R.training_current(facts({"training": tr[:2]}), SET)["status"] == "met"
    cal = [e(1, equipment="G-1", calibrated_on="2025-11-01"), e(2, equipment="G-2", calibrated_on="2025-09-01"),
           e(3, equipment="G-3", calibrated_on="2026-09-01", result="fail"),
           e(4, equipment="G-4", calibrated_on="2026-01-01", next_due="2026-06-30")]
    out = R.calibration_current(facts({"calibration": cal}), SET)
    assert {p["id"]: p["why"] for p in out["problems"]} == {2: "calibration was due on 2026-09-01",
                                                             3: "failed its last calibration",
                                                             4: "calibration was due on 2026-06-30"}
    assert R.calibration_current(facts({"calibration": cal[:2]}), dict(SET, calibration_interval_days=500))[
        "status"] == "met"
    au = [e(1, audit_date="2026-03-01", area="Receiving", nonconformities=2, followed_up=False)]
    assert R.audits_done(facts({"audits": au}), SET)["detail"] == "The internal audit recorded are not approved yet."
    au[0]["signed"] = True
    assert R.audits_done(facts({"audits": au}), SET)["problems"][0]["why"] == "findings not followed up"
    au.append(e(2, signed=True, audit_date="2026-09-01", area="Purchasing", nonconformities=0))
    au[0]["values"]["followed_up"] = True
    assert R.audits_done(facts({"audits": au}), SET)["status"] == "met"
    assert R.audits_done(facts({"audits": au}), dict(SET, audit_interval_days=30))["detail"] == \
        "The last internal audit was on 2026-09-01; one is due every 30 days."
    # an old review brought in from a spreadsheet counts as having happened
    rv = [e(1, imported=True, review_date="2026-02-01", attendees="Dana", decisions="x")]
    assert R.reviews_done(facts({"management_reviews": rv}), SET)["status"] == "met"
    assert R.reviews_done(facts({"management_reviews": rv}), dict(SET, review_interval_days=90))["status"] == "not_met"
    ob = [e(1, objective="On-time delivery", target="95%", reviewed_on="2026-01-01"),
          e(2, objective="On-time delivery", target="95%", reviewed_on="2026-09-01")]
    assert R.objectives_reviewed(facts({"objectives": ob}), SET)["status"] == "met"
    assert R.objectives_reviewed(facts({"objectives": ob[:1]}), SET)["problems"][0]["why"] == \
        "last reviewed 2026-01-01; due every 180 days"
    rk = [e(1, title="Single supplier for bolts", kind="risk", reviewed_on="2026-06-01"),
          e(2, title="New market", kind="opportunity", reviewed_on="2026-06-01")]
    assert R.risks_reviewed(facts({"risks": rk}), SET)["problems"] == [
        {"kind": "entry", "id": 1, "label": "Single supplier for bolts", "why": "no action planned"}]
    cp = [e(1, kind="complaint", customer="Acme", received_on="2026-09-01", response="credit",
            answered_on="2026-09-05"),
          e(2, kind="complaint", customer="Bolt Co", received_on="2026-08-01"),
          e(3, kind="complaint", customer="Cal", received_on="2026-07-01", response="replaced",
            answered_on="2026-09-01"),
          e(4, kind="complaint", customer="Dee", received_on="2026-10-01"),
          e(5, kind="survey", customer="Acme", received_on="2026-05-01")]
    out = R.complaints_answered(facts({"complaints": cp}), SET)
    assert {p["id"]: p["why"] for p in out["problems"]} == {2: "not answered after 72 days",
                                                             3: "answered after 62 days"}
    assert R.feedback_collected(facts({"complaints": cp}), SET)["status"] == "met"
    assert R.feedback_collected(facts({"complaints": cp[:4]}), SET)["status"] == "unknown"
    assert R.complaints_answered(facts({"complaints": cp[4:]}), SET)["status"] == "unknown"
    sp = [e(1, supplier="Gulf Fasteners", status="approved", approved_on="2026-01-01", next_review="2027-01-01"),
          e(2, supplier="Old Metal", status="approved", approved_on="2024-01-01", next_review="2025-01-01")]
    used = {"Gulf Fasteners": "Gulf Fasteners", "SUP-2": "Bayline Electrical (Demo)"}
    out = R.suppliers_approved(facts({"suppliers": sp}, suppliers_used=used), SET)
    assert {p["label"]: p["why"] for p in out["problems"]} == {
        "Bayline Electrical (Demo)": "bought from without an approval",
        "Old Metal": "re-evaluation was due on 2025-01-01"}
    assert R.suppliers_approved(facts({"suppliers": sp[:1]}, suppliers_used={"Gulf Fasteners": "Gulf Fasteners"}),
                                SET)["status"] == "met"


# ---------------------------------------------------------------- in the database

def test_entries_are_signed_locked_voided_and_judged(world):
    p = QMS.enable(world, Acc.get(world, JORDAN), "iso9001", "2015", PW, T)
    assert p["version"] == 2
    res = QMS.latest(world, "iso9001")["results"]
    assert res["audit"]["detail"] == "Nothing in the audits register yet."
    # every supplier the demo business bought from in the last year is listed as not approved
    sup = res["supplier_approval"]
    assert sup["status"] == "not_met" and all(x["why"] == "bought from without an approval" for x in sup["problems"])
    with pytest.raises(RG.RegisterError, match="still needed"):
        RG.create(world, JORDAN, "audits", {"audit_date": "2026-09-01"})
    a = RG.create(world, JORDAN, "audits", {"audit_date": "2026-09-01", "area": "Receiving", "auditor": "Jordan",
                                            "nonconformities": 1})
    RG.update(world, JORDAN, a["id"], {"followed_up": "yes"})
    with pytest.raises(Q.SignatureError):
        RG.sign(world, Acc.get(world, SAM), a["id"], "wrong")
    RG.sign(world, Acc.get(world, SAM), a["id"], PW)
    assert Q.signatures(world, "register", a["id"])[0]["meaning"] == "Internal audit report approved"
    with pytest.raises(RG.RegisterError, match="approved; void it"):
        RG.update(world, JORDAN, a["id"], {"area": "Shipping"})
    with pytest.raises(psycopg.errors.RaiseException, match="cannot change"):
        world.execute("update qms_register_entries set \"values\" = '{}' where id = %s", (a["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from qms_register_entries where id = %s", (a["id"],))
    t = RG.create(world, JORDAN, "training", {"person": "Lee", "topic": "QP-05", "trained_on": "2026-09-15"})
    with pytest.raises(RG.RegisterError, match="not approved with a signature"):
        RG.sign(world, Acc.get(world, SAM), t["id"], PW)
    for s in sup["problems"]:
        RG.create(world, JORDAN, "suppliers", {"supplier": s["label"], "status": "approved",
                                               "approved_on": "2026-01-02"})
    out = QMS.evaluate(world, "iso9001", T, "manual")["results"]
    assert out["audit"]["status"] == "met" and out["competence"]["status"] == "met"
    assert out["supplier_approval"]["status"] == "met"
    with pytest.raises(RG.RegisterError, match="say why"):
        RG.void(world, JORDAN, a["id"], " ")
    RG.void(world, JORDAN, a["id"], "entered for the wrong year")
    assert QMS.evaluate(world, "iso9001", T, "manual")["results"]["audit"]["status"] == "unknown"
    assert [h["action"] for h in RG.history(world, a["id"])] == ["recorded", "changed", "approved", "void"]
    assert RG.counts(world)["audits"] == {"void": 1}
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update qms_register_log set note = 'x'")


def test_old_spreadsheets_come_into_registers(world):
    data = DD.xlsx({"Training": [["Training matrix (Demo)"], ["Name", "Course", "Completed", "Assessment"],
                                 ["Lee Warehouse", "QP-05 Receiving Inspection", "2025-09-15", "Competent"],
                                 ["Pat Buyer", "QP-04 Purchasing", "2025-04-28", "Competent"],
                                 ["Sam Ops", "", "2025-05-01", "Competent"]]})
    imp = LIB.new_import(world, JORDAN, "test")
    doc = LIB.add_file(world, imp["id"], "Training matrix.xlsx", data)
    LIB.extract_import(world, imp["id"])
    t = LS.table_of(world, LIB.get(world, doc["id"]))
    flds = LS.flds(world, "reg_training")
    prop = LG.rules_mapping("reg_training", t, flds)
    assert prop["mapping"]["person"] == {"column": "Name"} and prop["mapping"]["topic"] == {"column": "Course"}
    li = LS.create(world, JORDAN, LIB.get(world, doc["id"]), "reg_training", t, prop, "rules")
    out = LS.run_import(world, Acc.get(world, JORDAN), li["id"], PW)
    assert out["result"] == {"imported": 2, "drafted": 0, "skipped": 1}
    rows = RG.entries(world, "training")
    assert {r["values"]["person"] for r in rows} == {"Lee Warehouse", "Pat Buyer"}
    assert all(r["source_doc"] == doc["id"] for r in rows) and rows[0]["values"]["result"] == "competent"


def test_registers_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for em in (JORDAN, SAM, DANA, "lee@demo.example"):
            Acc.set_password(conn, em, PW)

    def login(em):
        assert c.post("/api/login", json={"email": em, "password": PW}).status_code == 200

    login("lee@demo.example")                                  # warehouse: may look, not record
    regs = c.get("/api/registers").json()
    assert [r["name"] for r in regs][:2] == ["training", "calibration"] and regs[2]["signed"] is True
    assert c.get("/api/registers/training").json()["can_edit"] is False
    assert c.post("/api/registers/training", json={"values": {"person": "x"}}).status_code == 403
    login(JORDAN)
    assert c.get("/api/registers/nope").status_code == 404
    assert c.post("/api/registers/training", json={"values": {"person": "Lee"}}).status_code == 409
    r = c.post("/api/registers/management_reviews", json={"values": {
        "review_date": "2026-09-30", "attendees": "Dana, Jordan, Sam", "decisions": "Add a second bolt supplier"}})
    assert r.status_code == 201
    eid = r.json()["entries"][0]["id"]
    assert c.put(f"/api/register-entries/{eid}", json={"values": {"inputs": "audit results"}}).status_code == 200
    assert c.post(f"/api/register-entries/{eid}/sign", json={"password": PW}).json()["entries"][0]["status"] == \
        "signed"
    one = c.get(f"/api/register-entries/{eid}").json()
    assert one["signatures"][0]["email"] == JORDAN and [h["action"] for h in one["history"]] == [
        "recorded", "changed", "approved"]
    assert c.post(f"/api/register-entries/{eid}/void", json={"reason": ""}).status_code == 409
    assert c.get(f"/api/register-entries/{2**70}").status_code == 404
    c.__exit__(None, None, None)
