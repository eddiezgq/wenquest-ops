"""Document control and reading, step 17d (ADR-0017; dee-qms PLAN-DOC, PLAN-TRAINING): a revision taking effect on
a planned day, periodic review approved by someone other than the reviewer, people confirming with their password
that they have read the revision in effect, records superseded by a new revision, waivers, the ISO training check,
and the API. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, PW, file, imported
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.docs import ai_classify as AIC
from wqops.hub.docs import control as CTL
from wqops.hub.docs import library as LIB
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R

DANA, SAM, JORDAN, LEE = "dana@demo.example", "sam@demo.example", "jordan@demo.example", "lee@demo.example"
T = AS_OF
D = dt.timedelta


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


def in_review(conn):
    """QP-08 confirmed by Jordan, readers set (warehouse role and Dana), sent for approval."""
    imp, (doc,) = imported(conn, ["QP-08 Control of Nonconforming Product Rev C"])
    AIC.run(conn, {"email": JORDAN, "roles": ["quality"]}, imp["id"], None, today=T)
    LIB.confirm(conn, JORDAN, doc["id"])
    CTL.set_training(conn, JORDAN, doc["id"], {"roles": ["warehouse"], "people": [DANA]}, True)
    LIB.submit(conn, JORDAN, doc["id"])
    return LIB.get(conn, doc["id"])


def test_planned_effect_and_reading(world):
    doc = in_review(world)
    with pytest.raises(LIB.DocError, match="before the day it is approved"):
        LIB.approve(world, u(world, SAM), doc["id"], PW, T, T - D(days=1))
    a = LIB.approve(world, u(world, SAM), doc["id"], PW, T, T + D(days=7))
    assert (a["status"], a["effective_date"], a["fingerprint"]) == ("approved", T + D(days=7), a["sha256"])
    assert LIB.take_effect_due(world, T + D(days=6)) == [] and CTL.training(world, today=T) == []
    assert LIB.take_effect_due(world, T + D(days=7)) == [doc["id"]]
    assert LIB.get(world, doc["id"])["status"] == "effective"
    recs = CTL.training(world, document_id=doc["id"], today=T + D(days=7))
    assert sorted(r["email"] for r in recs) == [DANA, LEE] and recs[0]["due"] == (T + D(days=37)).isoformat()
    lee = next(r for r in recs if r["email"] == LEE)
    # only the person confirms, with their own password
    with pytest.raises(PermissionError, match="only the person"):
        CTL.acknowledge(world, u(world, DANA), lee["id"], PW)
    with pytest.raises(Q.SignatureError):
        CTL.acknowledge(world, u(world, LEE), lee["id"], "wrong")
    assert CTL.acknowledge(world, u(world, LEE), lee["id"], PW)["status"] == "acknowledged"
    assert Q.signatures(world, "doc_training", lee["id"])[0]["meaning"] == "Read and understood"
    with pytest.raises(psycopg.errors.RaiseException, match="cannot change"):
        world.execute("update doc_training set due = due + 1 where id = %s", (lee["id"],))
    dana = next(r for r in recs if r["email"] == DANA)
    with pytest.raises(PermissionError, match="someone else"):
        CTL.waive(world, DANA, dana["id"], "on leave")
    with pytest.raises(CTL.ControlError, match="reason"):
        CTL.waive(world, JORDAN, dana["id"], "")
    assert CTL.waive(world, JORDAN, dana["id"], "not in the warehouse any more")["status"] == "waived"
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from doc_training")


def test_new_revision_supersedes_reading(world):
    doc = in_review(world)
    LIB.approve(world, u(world, SAM), doc["id"], PW, T)
    first = {r["email"]: r for r in CTL.training(world, document_id=doc["id"], today=T)}
    assert set(first) == {DANA, LEE}
    _, data = file("QP-08 Control of Nonconforming Product Rev B")
    rev = LIB.new_revision(world, JORDAN, doc["id"], name="QP-08 Rev D.pdf", data=data, revision="D")
    assert rev["trainees"] == {"roles": ["warehouse"], "people": [DANA]} and rev["needs_training"] is False
    CTL.set_training(world, JORDAN, rev["id"], rev["trainees"], True)
    LIB.submit(world, JORDAN, rev["id"])
    LIB.approve(world, u(world, SAM), rev["id"], PW, T)
    old = {r["email"]: r for r in CTL.training(world, document_id=doc["id"], today=T)}
    assert {r["status"] for r in old.values()} == {"superseded"} and "revision D" in old[LEE]["note"]
    assert {r["email"] for r in CTL.training(world, document_id=rev["id"], today=T)} == {DANA, LEE}
    with pytest.raises(CTL.ControlError, match="set before it takes effect"):
        CTL.set_training(world, JORDAN, rev["id"], rev["trainees"], False)


def test_periodic_review(world):
    doc = in_review(world)
    LIB.approve(world, u(world, SAM), doc["id"], PW, T)
    doc = LIB.get(world, doc["id"])
    assert CTL.next_review(world, doc) == dt.date(2028, 6, 2)             # 36 months after 2025-06-02
    assert CTL.review_list(world, T)[0]["overdue"] is False
    with pytest.raises(CTL.ControlError, match="names the new revision"):
        CTL.record_review(world, JORDAN, doc["id"], "change", "steps changed", today=T)
    with pytest.raises(CTL.ControlError, match="say why"):
        CTL.record_review(world, JORDAN, doc["id"], "postponed", "", today=T, next_due="2026-12-31")
    r = CTL.record_review(world, JORDAN, doc["id"], "no_change", "still matches the work", today=T)
    with pytest.raises(CTL.ControlError, match="waiting for approval"):
        CTL.record_review(world, JORDAN, doc["id"], "no_change", "again", today=T)
    with pytest.raises(PermissionError, match="other than the reviewer"):
        CTL.decide_review(world, u(world, JORDAN), r["id"], True, password=PW)
    assert CTL.next_review(world, doc) == dt.date(2028, 6, 2)             # not approved yet: unchanged
    CTL.decide_review(world, u(world, SAM), r["id"], True, password=PW)
    assert CTL.next_review(world, doc) == CTL.add_months(T, 36)          # 36 months after the review
    with pytest.raises(psycopg.errors.RaiseException, match="decided"):
        world.execute("update doc_reviews set note = 'x' where id = %s", (r["id"],))
    p = CTL.record_review(world, JORDAN, doc["id"], "postponed", "process being redesigned", today=T,
                          next_due="2027-01-31")
    with pytest.raises(CTL.ControlError, match="say why"):
        CTL.decide_review(world, u(world, SAM), p["id"], False)
    CTL.decide_review(world, u(world, SAM), p["id"], True, password=PW)
    assert CTL.next_review(world, doc) == dt.date(2027, 1, 31)
    # a type that is not reviewed has no due date
    CTL.set_type(world, DANA, "procedure", None, 30)
    assert CTL.next_review(world, doc) is None and CTL.review_list(world, T) == []


def test_iso_training_check_reads_reading(world):
    doc = in_review(world)
    LIB.approve(world, u(world, SAM), doc["id"], PW, T)
    facts = {"today": T + D(days=31), "since": T - D(days=365), "registers": {},
             "doc_training": CTL.training_facts(world)}
    r = R.training_current(facts, R.defaults(QMS.load("iso13485")))
    assert r["status"] == "not_met" and {p["why"] for p in r["problems"]} == {f"reading was due on {T + D(days=30)}"}
    for rec in CTL.training(world, document_id=doc["id"], today=T):
        CTL.acknowledge(world, u(world, rec["email"]), rec["id"], PW)
    facts["doc_training"] = CTL.training_facts(world)
    assert R.training_current(facts, R.defaults(QMS.load("iso13485")))["detail"] == (
        "2 readings of controlled documents confirmed, none overdue.")


def test_doc_control_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, SAM, JORDAN, LEE):
            Acc.set_password(conn, e, PW)
        doc = in_review(conn)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(SAM)
    r = c.post(f"/api/docs/{doc['id']}/approve", json={"password": PW, "effective_on": "nope"})
    assert r.status_code == 400
    v = c.post(f"/api/docs/{doc['id']}/approve", json={"password": PW}).json()
    assert v["status"] == "effective" and {t["email"] for t in v["training"]} == {DANA, LEE}
    assert v["next_review"] == "2028-06-02"
    login(LEE)
    mine = c.get("/api/my-reading").json()
    assert [m["number"] for m in mine] == ["QP-08"]
    assert c.post(f"/api/my-reading/{mine[0]['id']}/acknowledge", json={"password": PW}).json()[0]["status"] == \
        "acknowledged"
    assert c.put(f"/api/docs/{doc['id']}/readers", json={"trainees": {"roles": [], "people": []}}).status_code == 403
    login(JORDAN)
    assert c.post(f"/api/docs/{doc['id']}/reviews", json={"outcome": "no_change"}).status_code == 201
    rid = c.get(f"/api/docs/{doc['id']}").json()["reviews"][0]["id"]
    assert c.post(f"/api/doc-reviews/{rid}/approve", json={"password": PW}).status_code == 403
    login(DANA)
    due = CTL.add_months(OA.today(DEMO), 36).isoformat()
    assert c.post(f"/api/doc-reviews/{rid}/approve", json={"password": PW}).json()["next_review"] == due
    assert c.post(f"/api/doc-reviews/{rid}/maybe").status_code == 404
    v = c.get("/api/doc-control").json()
    assert v["types"]["procedure"]["review_months"] == 36 and v["can_configure"] is True
    assert c.post("/api/doc-types/procedure", json={"review_months": 0}).status_code == 409
    c.__exit__(None, None, None)
