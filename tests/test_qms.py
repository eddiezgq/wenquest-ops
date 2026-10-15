"""The quality system against ISO 9001, step 16a (ADR-0016): the pack file, each check (met, not met, and unknown
when there is nothing to judge; imported history counted, not judged), adopting a standard with a signature,
declaring what does not apply, documents linked as evidence, evaluations kept and run once a day, the API and
permissions. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_documents import imported
from tests.test_metrics import AS_OF, DEMO, build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import ai_classify as AIC
from wqops.hub.docs import library as LIB
from wqops.hub.ont import project as OP
from wqops.hub.quality import auto as AUTO
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R

PW = "Demo pass 2026"
JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
SET = {"window_days": 365, "ncr_contain_days": 7, "capa_within_days": 14, "capa_overdue_days": 0}
T = AS_OF
OLD = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
D = dt.date


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


def facts(**kw):
    base = {"today": T, "since": T - dt.timedelta(days=365), "documents": [], "document_issues": [],
            "document_approvals": set(), "ncrs": [], "capas": [], "ncr_capas": set(), "capa_actions": [],
            "signatures": {}, "approval_dispositions": {"use_as_is"}, "incoming_inspections": [],
            "ncr_inspections": set(), "applicability": {}, "excludable": {"design": "design and development"},
            "evidence": {}}
    return base | kw


def ncr(i, **kw):
    """A report as system/qms.py prepares it: dates are company days."""
    return {"id": i, "name": f"NCR-{i:05d}", "status": "open", "severity": "minor", "description": "d",
            "disposition": None, "disposition_reason": None, "disposition_by": None, "approved_by": None,
            "closed_by": None, "inspection": None, "opened": D(2026, 9, 1), "closed_on": None, "contained_on": None,
            "when": D(2026, 9, 1), "imported": False} | kw


def capa(i, **kw):
    return {"id": i, "name": f"CAPA-{i:05d}", "status": "implementation", "owner": JORDAN, "opened": D(2026, 9, 1),
            "closed_on": None, "when": D(2026, 9, 1), "imported": False, "verification_result": None,
            "verification_method": None, "closed_by": None} | kw


# ---------------------------------------------------------------- the pack

def test_the_pack_file():
    pack = QMS.load("iso9001")
    assert R.check_pack(pack) == []
    cs = QMS.controls(pack)
    assert len(cs) >= 25 and all(c["clauses"]["2015"] for c in cs.values())
    assert {c for c, x in cs.items() if x.get("may_exclude")} == {"measuring", "design", "customer_property",
                                                                   "post_delivery"}
    assert pack["editions"]["2026"]["ready"] is False
    # every 2015 clause cited is a clause of chapters 4 to 10
    for c in cs.values():
        for cl in c["clauses"]["2015"]:
            assert 4 <= int(cl.split(".")[0]) <= 10, cl
    bad = dict(pack, settings={"window_days": "a year"})
    bad["processes"] = {"x": {"label": "x", "controls": [{"id": "a", "summary": "", "rule": "guess",
                                                          "clauses": {"1987": ["4"]}}] * 2}}
    errs = R.check_pack(bad)
    assert "setting window_days is a whole number" in errs and "control point a twice" in errs
    assert "a: unknown rule 'guess'" in errs and "a: clauses for edition '1987' are a list" in errs
    assert "a: a summary" in errs


# ---------------------------------------------------------------- the checks, on facts

def test_which_records_are_judged():
    f = facts()
    rows = [ncr(1), ncr(2, status="cancelled"), ncr(3, status="closed", closed_on=D(2026, 10, 1)),
            ncr(4, status="closed", opened=D(2024, 1, 1), closed_on=D(2026, 10, 11)),       # old, closed yesterday
            ncr(5, status="closed", opened=D(2024, 1, 1), closed_on=D(2024, 3, 1)),         # closed long ago
            ncr(6, status="contained", opened=D(2024, 1, 1)),                              # old but still open
            ncr(7, status="closed", imported=True, when=D(2026, 2, 1)),                    # imported history
            ncr(8, status="closed", imported=True, when=D(2020, 2, 1)),                    # imported, out of period
            ncr(9, status="open", imported=True, opened=D(2026, 10, 1))]                   # imported, still open
    own, history = R.judged(rows, f)
    assert [n["id"] for n in own] == [1, 3, 4, 6, 9] and [n["id"] for n in history] == [7]


def test_nonconformance_checks():
    f = facts()
    for rule in (R.ncr_contained, R.ncr_concession_approved, R.ncr_recorded, R.capa_for_major):
        assert rule(f, SET)["status"] == "unknown"                     # nothing to judge is not "met"
    out = R.ncr_recorded(facts(ncrs=[ncr(1, status="closed", imported=True)]), SET)
    assert out["status"] == "unknown" and "1 imported report counted as history" in out["detail"]
    # only cancelled reports: nothing to judge
    assert R.ncr_contained(facts(ncrs=[ncr(1, status="cancelled")]), SET)["status"] == "unknown"
    late = facts(ncrs=[ncr(1), ncr(2, opened=D(2026, 10, 10)), ncr(3, status="contained", contained_on=D(2026, 9, 3)),
                       ncr(4, status="contained", contained_on=D(2026, 10, 11)),
                       ncr(5, status="contained", opened=D(2025, 1, 1), contained_on=D(2025, 1, 2))])
    out = R.ncr_contained(late, SET)
    assert out["status"] == "not_met" and {p["id"]: p["why"] for p in out["problems"]} == {
        1: "open for 41 days without containment", 4: "contained after 40 days"}
    assert R.ncr_contained(facts(ncrs=[ncr(3, status="contained", contained_on=D(2026, 9, 3))]), SET)["status"] == "met"
    # an old report still open is judged even when a newer one is fine
    old_open = facts(ncrs=[ncr(1, opened=D(2025, 1, 1)), ncr(2, status="contained", contained_on=D(2026, 9, 2))])
    assert [p["id"] for p in R.ncr_contained(old_open, SET)["problems"]] == [1]
    # an imported report contained before it was imported has no containment time: not judged
    assert R.ncr_contained(facts(ncrs=[ncr(1, status="contained", imported=True)]), SET)["status"] == "unknown"
    conc = [ncr(1, status="closed", disposition="use_as_is", disposition_by=JORDAN, approved_by=SAM,
                closed_on=D(2026, 10, 1)),
            ncr(2, status="dispositioned", disposition="use_as_is", disposition_by=JORDAN, approved_by=JORDAN),
            ncr(3, status="dispositioned", disposition="use_as_is", disposition_by=JORDAN),
            ncr(4, status="closed", disposition="use_as_is", disposition_by=JORDAN, approved_by=DANA,
                closed_on=D(2026, 10, 1)),
            ncr(5, status="closed", disposition="scrap", closed_on=D(2026, 10, 1))]
    out = R.ncr_concession_approved(facts(ncrs=conc, signatures={("ncr", 1): {SAM}, ("ncr", 4): {JORDAN}}), SET)
    assert out["status"] == "not_met" and {p["id"]: p["why"] for p in out["problems"]} == {
        2: "approved by the person who proposed it", 3: "no approval recorded", 4: "the approval has no signature"}
    assert R.ncr_concession_approved(facts(ncrs=conc[:1], signatures={("ncr", 1): {SAM}}), SET)["status"] == "met"
    closed = [ncr(1, status="closed", disposition="scrap", disposition_reason="bent", disposition_by=JORDAN,
                  closed_by=JORDAN, closed_on=D(2026, 10, 1)),
              ncr(2, status="closed", disposition="scrap", disposition_reason="", disposition_by=JORDAN,
                  closed_by=JORDAN, closed_on=D(2026, 10, 1)),
              ncr(3, status="closed", opened=D(2024, 1, 1), closed_on=D(2026, 10, 11), disposition="scrap",
                  disposition_reason="x", closed_by=JORDAN)]
    out = R.ncr_recorded(facts(ncrs=closed, signatures={("ncr", 1): {JORDAN}, ("ncr", 3): {JORDAN}}), SET)
    assert {p["id"]: p["why"] for p in out["problems"]} == {
        2: "missing: reason for the disposition, the closing signature",
        3: "missing: who decided the disposition"}                     # opened long ago, closed yesterday: judged
    major = [ncr(1, severity="major"), ncr(2, severity="major", opened=D(2026, 10, 1)),
             ncr(3, severity="major", status="cancelled"), ncr(4, severity="major"),
             ncr(5, severity="major", opened=D(2025, 1, 1))]
    out = R.capa_for_major(facts(ncrs=major, ncr_capas={4}), SET)
    assert out["status"] == "not_met" and [p["id"] for p in out["problems"]] == [1, 5]   # 2 is new, 3 cancelled
    assert R.capa_for_major(facts(ncrs=major[1:4], ncr_capas={4}), SET)["status"] == "met"


def test_incoming_and_corrective_action_checks():
    assert R.rejected_lots_have_ncr(facts(), SET)["status"] == "unknown"
    lots = [{"key": "QI-1", "item_code": "BOLT", "rejected": True}, {"key": "QI-2", "item_code": "NUT",
                                                                     "rejected": False}]
    out = R.rejected_lots_have_ncr(facts(incoming_inspections=lots), SET)
    assert out["status"] == "not_met" and out["problems"][0]["why"] == "rejected BOLT without a nonconformance report"
    assert R.rejected_lots_have_ncr(facts(incoming_inspections=lots[1:]), SET)["detail"].startswith(
        "1 incoming inspection, 0 rejected")
    c = capa(1)
    acts = [{"capa_id": 1, "text": "Scan check", "due": D(2026, 10, 1), "done": False, "done_on": None},
            {"capa_id": 1, "text": "Train", "due": D(2026, 10, 1), "done": True, "done_on": D(2026, 10, 3)},
            {"capa_id": 1, "text": "Later", "due": D(2026, 12, 1), "done": False, "done_on": None},
            {"capa_id": 1, "text": "No date", "due": None, "done": False, "done_on": None}]
    assert R.capa_on_time(facts(capas=[c]), SET)["status"] == "unknown"
    # actions without due dates give nothing to judge: unknown, not met
    assert R.capa_on_time(facts(capas=[c], capa_actions=acts[3:]), SET)["status"] == "unknown"
    out = R.capa_on_time(facts(capas=[c], capa_actions=acts), SET)
    assert [p["why"] for p in out["problems"]] == ["Scan check: due 2026-10-01, not done",
                                                    "Train: due 2026-10-01, done 2026-10-03"]
    out = R.capa_on_time(facts(capas=[c], capa_actions=acts), dict(SET, capa_overdue_days=30))
    assert out["status"] == "met" and out["detail"] == "3 actions with due dates: none late."
    # actions of an imported corrective action still open are judged too
    assert R.capa_on_time(facts(capas=[capa(1, imported=True)], capa_actions=acts[:1]), SET)["status"] == "not_met"
    shut = [capa(1, status="closed", closed_on=D(2026, 10, 1), verification_result="effective",
                 verification_method="0 swaps", closed_by=SAM),
            capa(2, status="closed", closed_on=D(2026, 10, 1), verification_result="effective",
                 verification_method="", closed_by=JORDAN),
            capa(3, status="closed", imported=True),
            capa(4, status="closed", opened=D(2024, 1, 1), closed_on=D(2026, 10, 11), verification_result="effective",
                 verification_method="ok", closed_by=SAM)]
    out = R.capa_effective(facts(capas=shut, signatures={("capa", 1): {SAM}, ("capa", 2): {JORDAN}}), SET)
    assert out["problems"] == [
        {"kind": "capa", "id": 2, "label": "CAPA-00002", "why": "missing: the evidence of effectiveness, someone "
         "other than the owner to close it"},
        {"kind": "capa", "id": 4, "label": "CAPA-00004", "why": "missing: the closing signature"}]
    assert R.capa_effective(facts(capas=shut[2:3]), SET)["status"] == "unknown"


def test_document_checks_and_declarations():
    assert R.documents_approved(facts(), SET)["status"] == "unknown"
    docs = [{"id": 1, "doc_type": "procedure", "status": "effective", "name": "QP-01"},
            {"id": 2, "doc_type": "form", "status": "draft", "name": "F-1"},
            {"id": 3, "doc_type": "record", "status": "confirmed", "name": "log"}]
    out = R.documents_approved(facts(documents=docs, document_approvals={1}), SET)
    assert out["status"] == "met" and "1 other not approved yet" in out["detail"]
    assert R.documents_approved(facts(documents=docs), SET)["problems"][0]["why"] == \
        "in effect without a recorded approval"
    assert R.documents_approved(facts(documents=docs[1:]), SET)["status"] == "not_met"
    issue = {"kind": "revisions", "docs": [1, 2], "title": "QP-01: 2 revisions", "detail": "keep the old one obsolete"}
    assert R.documents_current(facts(documents=docs, document_issues=[issue]), SET)["status"] == "not_met"
    assert R.documents_current(facts(documents=docs, document_issues=[dict(issue, kind="no_date")]),
                               SET)["status"] == "met"
    # records alone are not controlled documents: nothing to judge
    assert R.documents_current(facts(documents=docs[2:]), SET)["status"] == "unknown"
    ref = dict(issue, kind="missing_ref")
    assert R.documents_referenced(facts(documents=docs, document_issues=[ref]), SET)["status"] == "not_met"
    # linked documents: in effect, or confirmed for the kinds the library does not approve
    policy = {"id": 7, "name": "Quality policy", "status": "confirmed", "doc_type": "other"}
    assert R.linked_document(facts(evidence={"policy": [policy]}), SET, "policy")["status"] == "met"
    assert R.linked_document(facts(evidence={"policy": [dict(policy, doc_type="procedure")]}), SET,
                             "policy")["status"] == "not_met"
    assert R.linked_document(facts(evidence={"policy": [dict(policy, status="obsolete")]}), SET,
                             "policy")["status"] == "not_met"
    assert R.linked_document(facts(), SET, "policy")["status"] == "unknown"
    # scope: the scope statement linked and every excludable point declared
    decl = {"design": {"applies": False, "reason": "we resell only", "email": DANA}}
    scope = {"scope": [dict(policy, id=8, name="Scope statement")]}
    assert R.scope_declared(facts(), SET)["detail"] == \
        "To do: link the scope statement; say whether these apply: design and development."
    assert R.scope_declared(facts(applicability=decl), SET)["status"] == "unknown"
    assert R.scope_declared(facts(evidence=scope), SET)["status"] == "unknown"
    out = R.scope_declared(facts(applicability=decl, evidence=scope), SET)
    assert out["status"] == "met" and out["detail"] == \
        "Evidence: Scope statement. Excluded, with reasons: design and development (we resell only)."
    pack = QMS.load("iso9001")
    res = R.evaluate(pack, "2015", facts(applicability=decl, documents=docs, document_approvals={1}))
    assert res["design"]["status"] == "not_applicable" and res["doc_approved"]["status"] == "met"
    assert res["audit"]["status"] == "unknown" and "register" in res["audit"]["detail"]
    assert res["ncr_concession"]["clauses"] == ["8.7.1", "8.7.2"] and res["ncr_concession"]["process"] == \
        "nonconforming"
    assert sum(R.counts(res).values()) == len(QMS.controls(pack))
    # our own rules are settings: switched off, the control point is shown by a linked document instead
    assert res["capa_on_time"]["rule"] == "capa_on_time"
    off = R.evaluate(pack, "2015", facts(evidence={"capa_on_time": [policy]}), {"actions_on_time": False})
    assert off["capa_on_time"]["rule"] == "linked_document" and off["capa_on_time"]["status"] == "met"
    assert R.defaults(pack)["capa_within_days"] == 14


# ---------------------------------------------------------------- in the database

def test_adopting_declaring_linking_and_evaluating(world):
    jordan, dana = Acc.get(world, JORDAN), Acc.get(world, DANA)
    assert QMS.view(world, "iso9001")["enabled"] is None and QMS.evaluate(world, "iso9001", T, "manual") is None
    with pytest.raises(QMS.QmsError, match="not ready yet"):
        QMS.enable(world, jordan, "iso9001", "2026", PW, T)
    with pytest.raises(Q.SignatureError):
        QMS.enable(world, jordan, "iso9001", "2015", "wrong", T)
    p = QMS.enable(world, jordan, "iso9001", "2015", PW, T)
    assert p["fingerprint"] == QMS.fingerprint(QMS.load("iso9001"))
    assert Q.signatures(world, "qms", p["id"])[0]["meaning"] == "ISO 9001:2015 (with Amendment 1:2024) adopted"
    with pytest.raises(QMS.QmsError, match="already in use"):
        QMS.enable(world, dana, "iso9001", "2015", PW, T)
    v = QMS.view(world, "iso9001")
    assert v["evaluation"]["trigger"] == "enabled" and v["newer_pack"] is False
    res = {c["id"]: c["result"] for proc in v["processes"] for c in proc["controls"]}
    assert res["scope"]["status"] == "unknown" and res["ncr_contained"]["status"] == "unknown"
    # QI-1 and QI-3 of the demo business were rejected and have no report yet
    assert res["rejected_lots"]["status"] == "not_met"
    assert {x["id"] for x in res["rejected_lots"]["problems"]} == {"QI-1", "QI-3"}

    # records: an uncontained major report with no corrective action
    n = Q.create_ncr(world, JORDAN, title="Bent bolts", description="12 bent", severity="major")
    world.execute("update ncr_records set created_at = %s where id = %s", (OLD, n["id"]))
    AUTO.open_for_rejected(world, dt.date(2026, 7, 1))
    out = QMS.evaluate(world, "iso9001", T, "manual", JORDAN)["results"]
    assert out["rejected_lots"]["status"] == "met"
    assert out["ncr_contained"]["status"] == "not_met" and out["capa_for_major"]["problems"][0]["id"] == n["id"]

    # what does not apply, signed with a reason
    with pytest.raises(QMS.QmsError, match="always applies"):
        QMS.declare(world, dana, "iso9001", "ncr_records", False, "no", PW, T)
    with pytest.raises(QMS.QmsError, match="give the reason"):
        QMS.declare(world, dana, "iso9001", "design", False, " ", PW, T)
    for c in ("design", "customer_property", "post_delivery"):
        QMS.declare(world, dana, "iso9001", c, False, "distribution only, no design or service", PW, T)
    QMS.declare(world, dana, "iso9001", "measuring", True, "we gauge incoming bolts", PW, T)
    ev = QMS.latest(world, "iso9001")
    assert ev["trigger"] == "changed" and ev["results"]["design"]["status"] == "not_applicable"
    assert ev["counts"]["not_applicable"] == 3
    assert ev["results"]["scope"]["detail"] == "To do: link the scope statement."
    signed = world.execute("select meaning, email from signatures where kind = 'qms_applicability' "
                           "order by id").fetchall()
    assert [s["meaning"] for s in signed] == ["Does not apply"] * 3 + ["Applies"] and signed[0]["email"] == DANA

    # a document linked as evidence counts while it is in effect
    imp, docs = imported(world, ["QP-01"])
    AIC.run(world, {"email": JORDAN, "roles": ["quality"]}, imp["id"], None, today=T)
    with pytest.raises(QMS.QmsError, match="confirmed in the library"):
        QMS.link(world, JORDAN, "iso9001", "policy", docs[0]["id"], True, T)
    LIB.confirm(world, JORDAN, docs[0]["id"])
    with pytest.raises(QMS.QmsError, match="judged from the records"):
        QMS.link(world, JORDAN, "iso9001", "ncr_records", docs[0]["id"], True, T)
    QMS.link(world, JORDAN, "iso9001", "policy", docs[0]["id"], True, T, "stands in for the policy in this test")
    assert QMS.latest(world, "iso9001")["results"]["policy"]["status"] == "not_met"   # a draft is not in effect
    LIB.submit(world, JORDAN, docs[0]["id"])
    LIB.approve(world, Acc.get(world, SAM), docs[0]["id"], PW, T)
    out = QMS.evaluate(world, "iso9001", T, "manual")["results"]
    assert out["policy"]["status"] == "met" and out["doc_approved"]["status"] == "met"
    QMS.link(world, JORDAN, "iso9001", "scope", docs[0]["id"], True, T)
    assert QMS.latest(world, "iso9001")["results"]["scope"]["status"] == "met"
    with pytest.raises(QMS.QmsError, match="already linked"):
        QMS.link(world, JORDAN, "iso9001", "policy", docs[0]["id"], True, T)
    QMS.link(world, JORDAN, "iso9001", "policy", docs[0]["id"], False, T)
    assert QMS.latest(world, "iso9001")["results"]["policy"]["status"] == "unknown"

    # settings: days and our own rules, changed and recorded; the next check uses them
    with pytest.raises(QMS.QmsError, match="a whole number from 0 to 365"):
        QMS.set_setting(world, JORDAN, "iso9001", "ncr_contain_days", 9999, T)
    with pytest.raises(QMS.QmsError, match="yes or no"):
        QMS.set_setting(world, JORDAN, "iso9001", "major_needs_capa", 0, T)
    with pytest.raises(KeyError):
        QMS.set_setting(world, JORDAN, "iso9001", "made_up", 1, T)
    QMS.set_setting(world, JORDAN, "iso9001", "ncr_contain_days", 60, T)
    assert QMS.latest(world, "iso9001")["results"]["ncr_contained"]["status"] == "met"
    QMS.set_setting(world, JORDAN, "iso9001", "major_needs_capa", False, T)
    out = QMS.latest(world, "iso9001")["results"]["capa_for_major"]
    assert out["rule"] == "linked_document" and out["status"] == "unknown"
    QMS.link(world, JORDAN, "iso9001", "capa_for_major", docs[0]["id"], True, T)
    assert QMS.latest(world, "iso9001")["results"]["capa_for_major"]["status"] == "met"
    assert QMS.settings(world, "iso9001", QMS.load("iso9001"))["major_needs_capa"] is False
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update qms_settings set value = 'true'")

    # once a day; kept as they were
    assert QMS.evaluate_if_due(world, T) == ["iso9001"] and QMS.evaluate_if_due(world, T) == []
    assert QMS.evaluate_if_due(world, T + dt.timedelta(days=1)) == ["iso9001"]
    first = world.execute("select id from qms_evaluations order by id limit 1").fetchone()["id"]
    assert QMS.view(world, "iso9001", first)["evaluation"]["trigger"] == "enabled"
    v = QMS.view(world, "iso9001", day=T)
    assert v["evaluation"]["day"] == T.isoformat() and v["evaluation"]["trigger"] == "daily"
    assert [h["day"] for h in v["history"]] == [(T + dt.timedelta(days=1)).isoformat(), T.isoformat()]
    with pytest.raises(KeyError):
        QMS.view(world, "iso9001", day=T - dt.timedelta(days=30))
    # a newer pack: the old check is still shown with the pack it was made under
    world.execute("update qms_packs set status = 'retired', retired_at = now() where id = %s", (p["id"],))
    world.execute("insert into qms_packs (standard, edition, version, content, fingerprint, enabled_by) values "
                  "('iso9001', '2015', 2, %s, 'f2', %s)", (psycopg.types.json.Json(dict(QMS.load("iso9001"),
                                                                                         version=2)), DANA))
    old = QMS.view(world, "iso9001", first)
    assert old["shown_pack"]["id"] == p["id"] and old["enabled"]["version"] == 2 and old["newer_pack"] is True
    with pytest.raises(psycopg.errors.RaiseException, match="frozen"):
        world.execute("update qms_packs set status = 'enabled' where id = %s", (p["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="frozen"):
        world.execute("update qms_packs set retired_at = now() where id = %s", (p["id"],))
    for sql in ("update qms_evaluations set counts = '{}' where id = %s", "delete from qms_evaluations where id = %s",
                "update qms_packs set fingerprint = 'x' where id = %s", "delete from qms_packs where id = %s"):
        with pytest.raises(psycopg.errors.RaiseException):
            world.execute(sql, (first if "evaluations" in sql else p["id"],))
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update qms_applicability set reason = 'x'")


def test_quality_system_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, DANA):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    assert {r for r, perms in P.ROLE_PERMISSIONS.items() if "qms:configure" in perms} == {"owner", "quality"}
    login(SAM)                                                     # operations manager: may look
    v = c.get("/api/qms/iso9001").json()
    assert v["enabled"] is None and v["can_configure"] is False and v["editions"]["2015"]["ready"] is True
    assert c.post("/api/qms/iso9001/enable", json={"edition": "2015", "password": PW}).status_code == 403
    assert c.post("/api/qms/iso9001/evaluate").status_code == 409
    assert c.get("/api/qms/iso14001").status_code == 404
    login(JORDAN)
    assert c.post("/api/qms/iso9001/enable", json={"edition": "2015", "password": "no"}).status_code == 403
    v = c.post("/api/qms/iso9001/enable", json={"edition": "2015", "password": PW}).json()
    assert v["enabled"]["edition"] == "2015" and v["evaluation"]["counts"]["unknown"] > 0
    assert c.post("/api/qms/iso9001/controls/design/applies", json={"applies": "no"}).status_code == 400
    r = c.post("/api/qms/iso9001/controls/design/applies", json={"applies": False, "reason": "resale only",
                                                                    "password": PW})
    assert r.status_code == 200 and r.json()["applicability"]["design"]["applies"] is False
    assert c.post("/api/qms/iso9001/controls/nope/applies", json={"applies": False, "reason": "x",
                                                                     "password": PW}).status_code == 404
    assert c.post("/api/qms/iso9001/controls/policy/evidence", json={"document_id": True}).status_code == 400
    r = c.post("/api/qms/iso9001/settings", json={"key": "actions_on_time", "value": False})
    assert r.status_code == 200 and r.json()["settings"]["actions_on_time"] is False
    assert c.post("/api/qms/iso9001/settings", json={"key": "window_days", "value": "a year"}).status_code == 409
    assert c.post("/api/qms/iso9001/controls/policy/evidence", json={"document_id": 10**6}).status_code == 404
    login(SAM)
    v = c.post("/api/qms/iso9001/evaluate").json()
    assert v["evaluation"]["trigger"] == "manual" and len(v["history"]) == 1    # one row a day
    assert c.post("/api/qms/iso9001/settings", json={"key": "window_days", "value": 30}).status_code == 403
    assert v["can_check"] is True
    assert c.get("/api/qms/iso9001?day=yesterday").status_code == 400
    with DB.connect(db_url) as conn:
        first = conn.execute("select min(id) as i from qms_evaluations").fetchone()["i"]
    assert c.get(f"/api/qms/iso9001?evaluation={first}").json()["evaluation"]["trigger"] == "enabled"
    assert c.get(f"/api/qms/iso9001?day={v['evaluation']['day']}").json()["evaluation"]["trigger"] == "manual"
    assert c.get("/api/qms/iso9001?evaluation=999999").status_code == 404
    c.__exit__(None, None, None)
