"""The ISO 13485 process pack, step 17a (ADR-0017): the pack is valid and only lets clauses 6-8 be excluded, both
standards read the one set of registers, the check that complaints are investigated and decided on reporting
(unknown when there are none), the questionnaire comes from each pack, and both standards can be adopted side by side.
Fictional data only."""

import datetime as dt

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, PW
from tests.test_metrics import build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.system import qms as QMS
from wqops.hub.system import registers as RG
from wqops.hub.system import rules as R
from wqops.hub.system import setup as SU

JORDAN, DANA = "jordan@demo.example", "dana@demo.example"
T = AS_OF
SET = R.defaults(QMS.load("iso13485"))


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, DANA):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=build().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def facts(rows):
    return {"today": T, "since": T - dt.timedelta(days=365), "registers": {"complaints": rows}}


def complaint(i, days_ago, **values):
    return {"id": i, "signed": False, "imported": False,
            "values": {"received_on": (T - dt.timedelta(days=days_ago)).isoformat(), "customer": f"Clinic {i}",
                       "kind": "complaint", "description": "Cracked housing"} | values}


def test_the_packs():
    p9, p13 = QMS.load("iso9001"), QMS.load("iso13485")
    assert R.check_pack(p9) == [] and R.check_pack(p13) == []
    assert p13["name"] == "ISO 13485" and list(p13["editions"]) == ["2016"]
    # one set of registers for the company, read by both standards
    assert p9["registers"] == p13["registers"] == RG.specs()
    assert {"reportable", "reported_on", "investigation"} <= set(RG.spec("complaints")["fields"])
    ctl = QMS.controls(p13)
    for c in ctl.values():
        assert list(c["clauses"]) == ["2016"] and c["clauses"]["2016"]
        if c.get("may_exclude"):          # the standard lets only requirements of clauses 6, 7 and 8 be left out
            assert all(x.split(".")[0] in ("6", "7", "8") for x in c["clauses"]["2016"]), c["id"]
    assert not ctl["design"].get("switch") and ctl["complaints_assessed"]["rule"] == "complaints_assessed"
    assert {"scope", "device_file", "qms_software", "management_rep", "sterilization_validation"} <= set(ctl)
    # every yes/no question names control points that may be excluded
    for q in p13["questions"].values():
        assert all(ctl[c].get("may_exclude") for c in q.get("if_no", {}))


def test_pack_mistakes_are_caught():
    p = QMS.load("iso13485")
    bad = {**p, "settings": {k: v for k, v in p["settings"].items() if k != "reportability_days"},
           "questions": {"designs": {"label": "Designs?", "type": "yesno", "if_no": {"policy": "x"}},
                         "odd": yaml.safe_load("{label: Odd, type: yesno, no: {design: x}}")}}
    errs = R.check_pack(bad)
    assert "complaints_assessed: its rule needs the setting reportability_days" in errs
    assert "question designs: policy is not a control point that may be excluded, or has no reason" in errs
    # 'no:' is read by YAML as false: caught rather than silently ignored
    assert "question odd: a label, a type (text, number, yesno) and what a no means (if_no)" in errs


def test_complaints_investigated_and_decided_on_reporting():
    def check(*rows):
        return R.complaints_assessed(facts(list(rows)), SET)
    assert check()["status"] == "unknown"
    # received recently, not decided yet: still within the days
    r = check(complaint(1, 3))
    assert r["status"] == "met" and "1 still within the 30 days" in r["detail"]
    r = check(complaint(1, 40))
    assert r["status"] == "not_met" and r["problems"][0]["why"] == "whether to report it is not decided after 40 days"
    r = check(complaint(1, 10, reportable=False))
    assert r["problems"][0]["why"] == "the reporting decision has no reason"
    r = check(complaint(1, 40, reportable=True, reportable_reason="Serious injury possible"))
    assert r["problems"][0]["why"] == "to be reported, but no report date recorded"
    r = check(complaint(1, 10, reportable=False, reportable_reason="No injury possible",
                        answered_on=T.isoformat(), response="Replaced"))
    assert r["problems"][0]["why"] == "closed without an investigation or the reason none was needed"
    done = complaint(1, 40, reportable=True, reportable_reason="Serious injury possible",
                     reported_on=(T - dt.timedelta(days=20)).isoformat(), investigation="Molding defect, lot 7")
    feedback = complaint(2, 40, kind="feedback")
    old = complaint(3, 400)
    r = check(done, feedback, old)
    assert r["status"] == "met" and [x["id"] for x in r["evidence"]] == [1]
    # the company sets its own days
    assert R.complaints_assessed(facts([complaint(1, 40)]), {**SET, "reportability_days": 60})["status"] == "met"


def test_both_standards_on_the_same_records(world):
    assert [(s["standard"], s["adopted"]) for s in QMS.standards(world)] == [("iso9001", False),
                                                                             ("iso13485", False)]
    jordan = Acc.get(world, JORDAN)
    QMS.enable(world, jordan, "iso9001", "2015", PW, T)
    with pytest.raises(QMS.QmsError, match="no edition"):
        QMS.enable(world, jordan, "iso13485", "2015", PW, T)
    p = QMS.enable(world, jordan, "iso13485", "2016", PW, T)
    assert p["version"] == 1 and p["fingerprint"] == QMS.fingerprint(QMS.load("iso13485"))
    res = QMS.latest(world, "iso13485")["results"]
    assert len(res) == len(QMS.controls(QMS.load("iso13485")))
    assert res["complaints_assessed"]["status"] == "unknown" and res["design"]["status"] == "unknown"
    # one complaint, entered once, is read by both
    RG.create(world, DANA, "complaints", {"received_on": T.isoformat(), "customer": "Bay Vet Clinic (Demo)",
                                          "kind": "complaint", "description": "Display flickers"})
    QMS.evaluate_changed(world, T, DANA)
    assert QMS.latest(world, "iso9001")["results"]["customer_feedback"]["status"] == "met"
    assert QMS.latest(world, "iso13485")["results"]["complaints_assessed"]["status"] == "met"
    # settings, declarations and the view are kept per standard
    QMS.set_setting(world, JORDAN, "iso13485", "reportability_days", 10, T)
    assert QMS.settings(world, "iso9001", QMS.load("iso9001")).get("reportability_days") is None
    v = QMS.view(world, "iso13485")
    assert v["name"] == "ISO 13485" and v["edition_label"] == "ISO 13485:2016"
    assert [x["standard"] for x in QMS.standards(world) if x["adopted"]] == ["iso9001", "iso13485"]


def test_questionnaire_per_standard(world):
    QMS.enable(world, Acc.get(world, JORDAN), "iso13485", "2016", PW, T)
    assert "sterile" in SU.questions(world, "iso13485") and "sterile" not in SU.questions(world, "iso9001")
    with pytest.raises(SU.SetupError, match="no question"):
        SU.save_answers(world, JORDAN, "iso9001", {"sterile": False})
    SU.save_answers(world, JORDAN, "iso13485", {"sterile": False, "designs": True, "role": "Manufacturer"})
    props = {p["control"]: p for p in SU.proposed_applicability(world, "iso13485")}
    assert set(props) == {"sterile_records", "sterilization_validation", "design"}
    assert props["design"]["applies"] is True and props["sterile_records"]["applies"] is False
    assert SU.apply_answers(world, Acc.get(world, DANA), "iso13485", PW, T) == 3
    res = QMS.latest(world, "iso13485")["results"]
    assert res["sterilization_validation"]["status"] == "not_applicable"
    assert QMS.applicability(world, "iso9001") == {}


def test_standards_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, JORDAN, PW)
    assert c.post("/api/login", json={"email": JORDAN, "password": PW}).status_code == 200
    assert [s["name"] for s in c.get("/api/qms").json()] == ["ISO 9001", "ISO 13485"]
    v = c.get("/api/qms/iso13485").json()
    assert v["enabled"] is None and v["name"] == "ISO 13485" and list(v["editions"]) == ["2016"]
    assert c.get("/api/qms/iso9999").status_code == 404
    assert c.post("/api/qms/iso13485/enable", json={"edition": "2016", "password": PW}).json()["enabled"]
    s = c.get("/api/qms/iso13485/setup").json()
    assert s["name"] == "ISO 13485" and "implantable" in s["questions"]
    assert c.get("/api/qms/iso13485/checklist").json()["name"] == "ISO 13485"
    assert c.get("/api/qms/iso13485/gaps").json()["name"] == "ISO 13485"
    c.__exit__(None, None, None)
