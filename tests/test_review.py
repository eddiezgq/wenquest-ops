"""Management review, step 17j (ADR-0017; dee-qms PLAN-MR): inputs counted from the records for the period and
frozen with a fingerprint, collected again with the old fingerprint logged, the chair signing (not whoever prepared
it) once the meeting, notes and conclusion are written, actions decided with an owner and a date and marked done
with evidence, the review fixed once signed and read by the ISO check, the API. Fictional data only."""

import datetime as dt

import psycopg
import psycopg.types.json
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, inspect, plan, receipts, table
from tests.test_production import LEE, SAM
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import records as Q
from wqops.hub.quality import review as MR
from wqops.hub.quality import review_rules as RR
from wqops.hub.system import qms as QMS

T = AS_OF
# records are signed at the real "now": the period runs to tomorrow so they fall inside it in any time zone
END = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)
START = END - dt.timedelta(days=89)
TODAY = END - dt.timedelta(days=1)


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


def figs(r: dict, section: str) -> dict:
    return {f["label"]: f["value"] for f in r["inputs"]["sections"][section]["figures"]}


def test_rules():
    assert RR.rate(1, 4) == 25.0 and RR.rate(0, 0) is None
    r = {"status": "frozen", "chair": DANA, "meeting_on": str(T), "attendees": "Dana", "notes": {"capa": "ok"},
         "conclusion": "Suitable", "involved": [JORDAN]}
    assert RR.to_sign(r, DANA, T) == []
    assert RR.to_sign(r, SAM, T) == [f"the chair's signature ({DANA})"]
    assert RR.to_sign({**r, "involved": [DANA]}, DANA, T) == ["a chair who did not prepare it"]
    left = RR.to_sign({**r, "notes": {"capa": " "}, "conclusion": ""}, DANA, T)
    assert left[0].startswith("the meeting's assessment")
    assert RR.check_action("", "", T - dt.timedelta(days=1), T) == ["what is to be done", "who does it",
                                                                     "a due date that is not in the past"]
    assert RR.fingerprint({"a": 1, "b": 2}) == RR.fingerprint({"b": 2, "a": 1})


def test_review_from_inputs_to_signature(world):
    table(world)
    plan(world)
    inspect(world, "PR-7", [10.0, 10.0, 10.0])
    r = MR.create(world, JORDAN, {"title": "Q3 management review", "period_start": str(START),
                                  "period_end": str(END), "chair": DANA})
    assert r["name"] == "MR-00001"
    with pytest.raises(MR.ReviewError, match="still needed: the inputs collected"):
        MR.sign(world, u(world, DANA), r["id"], PW, today=TODAY)
    r = MR.collect(world, JORDAN, r["id"], today=T)
    assert figs(r, "incoming")["Lots inspected"] == 1 and figs(r, "incoming")["Lot rejection rate"] == 0.0
    assert figs(r, "previous")["Still open"] == 0 and len(r["inputs"]["sections"]) == len(MR.SECTIONS)
    first = r["fingerprint"]
    # later records do not change the frozen inputs until they are collected again
    inspect(world, "PR-8", [10.0, 10.0, 11.0])
    assert figs(MR.get(world, r["id"]), "incoming")["Lots inspected"] == 1
    r = MR.collect(world, JORDAN, r["id"], today=T)
    assert figs(r, "incoming")["Lots rejected"] == 1 and r["fingerprint"] != first
    assert any(first in h["note"] for h in MR.view(world, r["id"], u(world, DANA), TODAY)["history"])
    with pytest.raises(MR.ReviewError, match="cancel and start a new review"):
        MR.update(world, JORDAN, r["id"], {"period_start": str(START + dt.timedelta(days=1))})
    MR.update(world, JORDAN, r["id"], {"meeting_on": str(TODAY), "attendees": "Dana, Jordan, Sam",
                                       "notes": {"incoming": "One lot rejected: supplier warned"},
                                       "conclusion": "The system is suitable, adequate and effective."})
    with pytest.raises(MR.ReviewError, match="not in the past"):
        MR.add_action(world, JORDAN, r["id"], {"text": "Audit Gulf", "owner": SAM,
                                                "due": str(T - dt.timedelta(days=1))}, today=T)
    a = MR.add_action(world, JORDAN, r["id"], {"text": "Audit Gulf Fasteners", "owner": SAM,
                                                "due": str(T + dt.timedelta(days=30))}, today=T)
    for who, msg in ((SAM, "chair's signature"), (JORDAN, "chair's signature")):
        with pytest.raises(MR.ReviewError, match=msg):
            MR.sign(world, u(world, who), r["id"], PW, today=TODAY)
    with pytest.raises(Q.SignatureError):
        MR.sign(world, u(world, DANA), r["id"], "wrong", today=TODAY)
    # notes are merged per input: a second person writing another input keeps the first one's note
    MR.update(world, SAM, r["id"], {"notes": {"capa": "No overdue actions"}})
    assert MR.get(world, r["id"])["notes"] == {"incoming": "One lot rejected: supplier warned",
                                                "capa": "No overdue actions"}
    with pytest.raises(MR.ReviewError, match="give the period"):
        MR.update(world, JORDAN, r["id"], {"period_start": None})
    with pytest.raises(MR.ReviewError, match="a meeting date within"):
        MR.sign(world, u(world, DANA), r["id"], PW, today=TODAY - dt.timedelta(days=1))
    # the database keeps the frozen inputs, the period and the signature fields as they are
    for sql, msg in (("update mgmt_reviews set inputs = '{}' where id = %s", "collected again"),
                     ("update mgmt_reviews set period_end = period_end - 1 where id = %s", "collected for this period"),
                     ("update mgmt_reviews set signed_by = 'x' where id = %s", "not signed")):
        with pytest.raises(psycopg.errors.RaiseException, match=msg):
            with world.transaction():
                world.execute(sql, (r["id"],))
    # inputs changed behind its back (even with a new collection time) are not signed
    good = MR.get(world, r["id"])
    world.execute("update mgmt_reviews set inputs = inputs - 'counted_on', collected_at = clock_timestamp() "
                  "where id = %s", (r["id"],))
    assert MR.view(world, r["id"], u(world, DANA), TODAY)["intact"] is False
    with pytest.raises(MR.ReviewError, match="no longer match"):
        MR.sign(world, u(world, DANA), r["id"], PW, today=TODAY)
    world.execute("update mgmt_reviews set inputs = %s, collected_at = clock_timestamp() where id = %s",
                  (psycopg.types.json.Jsonb(good["inputs"]), r["id"]))
    MR.sign(world, u(world, DANA), r["id"], PW, today=TODAY)
    v = MR.view(world, r["id"], u(world, DANA), TODAY)
    assert v["status"] == "closed" and v["intact"] is True
    assert [s["meaning"] for s in v["signatures"]] == ["Management review approved"]
    with pytest.raises(psycopg.errors.RaiseException, match="closed"):
        world.execute("update mgmt_reviews set conclusion = 'x' where id = %s", (r["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        world.execute("update mgmt_review_actions set due = due + 1 where id = %s", (a["id"],))
    with pytest.raises(PermissionError, match="owner or Quality"):
        MR.action_done(world, u(world, LEE), a["id"], "done")
    with pytest.raises(MR.ReviewError, match="what shows"):
        MR.action_done(world, u(world, SAM), a["id"], " ")
    # the next review carries the action still open
    r2 = MR.create(world, JORDAN, {"title": "Q4", "period_start": str(T), "period_end": str(T), "chair": DANA})
    r2 = MR.collect(world, JORDAN, r2["id"], today=T)
    assert figs(r2, "previous")["Still open"] == 1
    MR.action_done(world, u(world, SAM), a["id"], "Audit report AR-12")
    b = MR.add_action(world, JORDAN, r2["id"], {"text": "Train", "owner": SAM, "due": str(T)}, today=T)
    assert MR.cancel(world, JORDAN, r2["id"], "Merged into the next one")["status"] == "cancelled"
    with pytest.raises(MR.ReviewError, match="cancelled"):
        MR.action_done(world, u(world, SAM), b["id"], "done")
    with pytest.raises(psycopg.errors.RaiseException, match="cancelled"):
        world.execute("update mgmt_review_actions set text = 'x' where id = %s", (b["id"],))
    # the ISO check reads the signed review from the register
    QMS.enable(world, u(world, JORDAN), "iso9001", "2015", PW, TODAY)
    QMS.evaluate(world, "iso9001", TODAY, "manual", JORDAN)
    res = QMS.latest(world, "iso9001")["results"]["review"]
    assert res["status"] == "met" and res["evidence"][0]["id"] == f"m{r['id']}"
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from mgmt_reviews")


def test_whoever_prepared_it_does_not_sign(world):
    r = MR.create(world, JORDAN, {"title": "R", "period_start": str(START), "period_end": str(END),
                                  "chair": DANA, "meeting_on": str(TODAY), "attendees": "All"})
    MR.collect(world, DANA, r["id"], today=T)                     # Dana collected the inputs
    MR.update(world, JORDAN, r["id"], {"notes": {"capa": "Fine"}, "conclusion": "Effective"})
    with pytest.raises(MR.ReviewError, match="did not prepare it"):
        MR.sign(world, u(world, DANA), r["id"], PW, today=TODAY)
    with pytest.raises(psycopg.errors.RaiseException, match="starts as a draft"):
        world.execute("insert into mgmt_reviews (name, title, period_start, period_end, status, created_by) values "
                      "('X', 'x', now(), now(), 'closed', 'x')")


def test_review_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=receipts(business()).transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, JORDAN, SAM):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(SAM)
    assert c.post("/api/reviews", json={"title": "x"}).status_code == 403
    login(JORDAN)
    rid = c.post("/api/reviews", json={"title": "Annual review", "period_start": "2026-01-01",
                                       "period_end": "2026-09-30", "chair": DANA}).json()["id"]
    v = c.post(f"/api/reviews/{rid}/collect").json()
    assert v["status"] == "frozen" and "incoming" in v["inputs"]["sections"]
    v = c.put(f"/api/reviews/{rid}", json={"meeting_on": "2026-10-10", "attendees": "Dana, Jordan",
                                           "notes": {"capa": "No open actions"}, "conclusion": "Effective"}).json()
    assert v["to_sign"] == [f"the chair's signature ({DANA})", "a chair who did not prepare it"]   # for Jordan
    assert c.put(f"/api/reviews/{rid}", json={"notes": {"weather": "x"}}).status_code == 409
    login(DANA)
    assert c.post(f"/api/reviews/{rid}/sign", json={"password": PW}).json()["status"] == "closed"
    assert c.post(f"/api/reviews/{rid}/explode").status_code == 404
    assert c.get("/api/reviews").json()["reviews"][0]["name"] == "MR-00001"
    c.__exit__(None, None, None)
