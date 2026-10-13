"""Quality records (ADR-0009, ADR-0010): NCR life cycle with signed approval and closing, separation of duties,
disposition types as configuration, 8D, staged CAPA, append-only logs and signatures, automatic NCRs, objects,
metric, anomaly and root cause. All data is fictional (tests/test_metrics.py)."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import AS_OF, DEMO, build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import chain as CH
from wqops.hub.ont import metrics as M
from wqops.hub.ont import project as OP
from wqops.hub.quality import auto as AUTO
from wqops.hub.quality import records as Q

PW = "Demo pass 2026"
JORDAN, SAM = "jordan@demo.example", "sam@demo.example"


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, "dana@demo.example"):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=build().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def who(conn, email):
    return Acc.get(conn, email)


def log(conn, kind, ref):
    return [h["action"] for h in Q.history(conn, kind, ref)]


def ncr(conn, **kw):
    args = {"title": "Bent bolts", "description": "12 bolts bent in lot", "quantity": 12} | kw
    return Q.create_ncr(conn, JORDAN, **args)


def test_ncr_without_approval(world):
    n = ncr(world, inspection="QI-1", item_code="BOLT-B", receipt="PR-2", supplier="Gulf Fasteners")
    assert n["name"] == "NCR-00001" and n["status"] == "open" and n["owner"] == JORDAN
    with pytest.raises(Q.QualityError, match="already has a nonconformance report"):
        ncr(world, inspection="QI-1")
    with pytest.raises(Q.QualityError, match="needs it to be contained"):
        Q.submit_disposition(world, n["id"], JORDAN, "scrap", 12, "bent")
    Q.contain(world, n["id"], JORDAN, "Lot moved to QC Hold")
    with pytest.raises(Q.QualityError, match="disposition is one of"):
        Q.submit_disposition(world, n["id"], JORDAN, "keep", 12, "x")
    with pytest.raises(Q.QualityError, match="cannot exceed the report's 12"):
        Q.submit_disposition(world, n["id"], JORDAN, "return_to_supplier", 13, "RMA")
    with pytest.raises(Q.QualityError, match="reason"):
        Q.submit_disposition(world, n["id"], JORDAN, "return_to_supplier", 12, " ")
    assert Q.submit_disposition(world, n["id"], JORDAN, "return_to_supplier", 12, "RMA 77")["status"] == \
        "dispositioned"                                               # no approval needed for this type
    with pytest.raises(Q.SignatureError, match="password is wrong"):
        Q.close_ncr(world, n["id"], who(world, JORDAN), "wrong pass 1")
    assert Q.ncr(world, n["id"])["status"] == "dispositioned"        # a wrong password changes nothing
    done = Q.close_ncr(world, n["id"], who(world, JORDAN), PW, "credit received")
    assert done["status"] == "closed" and done["closed_by"] == JORDAN
    assert [(s["email"], s["meaning"]) for s in Q.signatures(world, "ncr", n["id"])] == [
        (JORDAN, "Nonconformance closed")]
    assert log(world, "ncr", n["id"]) == ["opened", "contained", "disposition submitted", "closed"]
    with pytest.raises(Q.QualityError, match="is closed"):
        Q.cancel_ncr(world, n["id"], JORDAN, "oops")
    with pytest.raises(Q.QualityError, match="cannot change"):
        Q.save_8d(world, n["id"], JORDAN, {"d1": "late"})


def test_concession_needs_another_persons_signed_approval(world):
    n = ncr(world)
    Q.contain(world, n["id"], JORDAN, "Held")
    assert Q.submit_disposition(world, n["id"], JORDAN, "use_as_is", 12, "cosmetic only")["status"] == \
        "pending_approval"
    with pytest.raises(Q.QualityError, match="someone other than the person who submitted"):
        Q.approve_disposition(world, n["id"], who(world, JORDAN), PW)
    assert Q.reject_disposition(world, n["id"], SAM, "customer will notice")["status"] == "contained"
    Q.submit_disposition(world, n["id"], JORDAN, "use_as_is", 12, "inside drawing tolerance after review")
    ok = Q.approve_disposition(world, n["id"], who(world, SAM), PW)
    assert ok["status"] == "dispositioned" and ok["approved_by"] == SAM
    assert Q.signatures(world, "ncr", n["id"])[0]["meaning"] == "Disposition approved"


def test_disposition_types_are_configuration(world):
    Q.save_disposition_type(world, "dana@demo.example", "sort", "Sort and use good parts", False)
    Q.save_disposition_type(world, "dana@demo.example", "scrap", "Scrap", False, active=False)
    types = Q.disposition_types(world)
    assert "sort" in types and "scrap" not in types and types["use_as_is"]["requires_approval"]
    with pytest.raises(Q.QualityError, match="needs a code"):
        Q.save_disposition_type(world, "dana@demo.example", "bad code!", "x", False)


def test_logs_and_signatures_cannot_be_changed(world):
    n = ncr(world)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("update quality_log set note = 'edited' where ref_id = %s", (n["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("delete from quality_log")
    Q.contain(world, n["id"], JORDAN, "Held")
    Q.submit_disposition(world, n["id"], JORDAN, "scrap", 12, "bent")
    Q.close_ncr(world, n["id"], who(world, JORDAN), PW)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("update signatures set name = 'Someone Else'")


def test_sso_only_people_need_a_password_to_sign(world):
    n = ncr(world)
    Q.contain(world, n["id"], JORDAN, "Held")
    Q.submit_disposition(world, n["id"], JORDAN, "scrap", 12, "bent")
    sso = who(world, "pat@demo.example")            # no password set: signs in with Microsoft or Google
    with pytest.raises(Q.SignatureError, match="set a password"):
        Q.close_ncr(world, n["id"], sso, "")


def test_8d_is_signed(world):
    n = ncr(world)
    Q.save_8d(world, n["id"], JORDAN, {"d1": "Jordan, Pat", "d2": "12 of 50 bent"})
    with pytest.raises(Q.QualityError, match="still to write: D3 Containment, D4 Root cause"):
        Q.complete_8d(world, n["id"], who(world, JORDAN), PW)
    Q.save_8d(world, n["id"], JORDAN, {k: f"text {k}" for k in ("d3", "d4", "d5", "d6", "d7", "d8")})
    with pytest.raises(Q.SignatureError):
        Q.complete_8d(world, n["id"], who(world, JORDAN), "nope")
    e = Q.complete_8d(world, n["id"], who(world, JORDAN), PW)
    assert e["complete"] and Q.signatures(world, "ncr", n["id"])[0]["meaning"] == "8D completed"
    with pytest.raises(Q.QualityError, match="complete"):
        Q.save_8d(world, n["id"], JORDAN, {"d1": "changed"})


def test_capa_stages(world):
    n = ncr(world, severity="major")
    Q.contain(world, n["id"], JORDAN, "Relabelled stock")
    Q.submit_disposition(world, n["id"], JORDAN, "rework", 12, "relabel")
    with pytest.raises(Q.QualityError, match="major"):
        Q.close_ncr(world, n["id"], who(world, JORDAN), PW)
    c = Q.create_capa(world, JORDAN, kind="corrective", title="Label check at packing", ncr_ids=[n["id"]])
    assert c["status"] == "draft" and c["owner"] == JORDAN
    with pytest.raises(Q.QualityError, match="already has an open corrective action, CAPA-00001"):
        Q.create_capa(world, JORDAN, kind="corrective", title="Another", ncr_ids=[n["id"]])
    with pytest.raises(Q.QualityError, match="still needed: problem description, risk level"):
        Q.submit_capa(world, c["id"], JORDAN)
    Q.update_capa(world, c["id"], JORDAN, description="Swapped labels shipped", risk="high")
    Q.submit_capa(world, c["id"], JORDAN)
    with pytest.raises(Q.QualityError, match="still needed: containment, root cause, at least one action"):
        Q.plan_actions(world, c["id"], JORDAN)
    with pytest.raises(Q.QualityError, match="title cannot change now"):
        Q.update_capa(world, c["id"], JORDAN, title="new")
    Q.update_capa(world, c["id"], JORDAN, containment="All stock relabelled", root_cause="Two label printers")
    with pytest.raises(Q.QualityError, match="past"):
        Q.add_action(world, c["id"], JORDAN, "Scan check", due="2026-10-01", today=AS_OF)
    a1 = Q.add_action(world, c["id"], JORDAN, "Add a scan check", "lee@demo.example", "2026-10-20", today=AS_OF)
    Q.plan_actions(world, c["id"], JORDAN)
    a2 = Q.add_action(world, c["id"], JORDAN, "Train packers", JORDAN, kind="preventive", today=AS_OF)
    with pytest.raises(Q.QualityError, match="not done yet: Add a scan check; Train packers"):
        Q.to_effectiveness(world, c["id"], JORDAN)
    with pytest.raises(PermissionError):
        Q.action_done(world, a1["id"], "alex@demo.example", may_edit=False, evidence="done")
    with pytest.raises(Q.QualityError, match="evidence"):
        Q.action_done(world, a1["id"], "lee@demo.example", may_edit=False, evidence="")
    Q.action_done(world, a1["id"], "lee@demo.example", may_edit=False, evidence="Scanner live on line 2")
    Q.action_done(world, a2["id"], JORDAN, may_edit=True, evidence="Training record T-12")
    Q.to_effectiveness(world, c["id"], JORDAN)
    back = Q.effectiveness(world, c["id"], who(world, SAM), "", "ineffective", "2 swaps last week")
    assert back["status"] == "implementation"
    Q.to_effectiveness(world, c["id"], JORDAN)
    with pytest.raises(Q.QualityError, match="someone other than the owner"):
        Q.effectiveness(world, c["id"], who(world, JORDAN), PW, "effective", "0 swaps in 3 weeks")
    done = Q.effectiveness(world, c["id"], who(world, SAM), PW, "effective", "0 swaps in 3 weeks")
    assert done["status"] == "closed" and done["closed_by"] == SAM
    assert Q.close_ncr(world, n["id"], who(world, JORDAN), PW)["status"] == "closed"
    assert log(world, "capa", c["id"]) == [
        "opened", "nonconformance linked", "updated", "investigation", "updated", "action added", "implementation",
        "action added", "action done", "action done", "effectiveness", "implementation", "effectiveness", "closed"]
    # a closed CAPA no longer blocks a new one for the same report
    assert Q.create_capa(world, JORDAN, kind="preventive", title="Printer audit", ncr_ids=[n["id"]])


def test_capa_cancel_and_multiple_ncrs(world):
    a, b = ncr(world), ncr(world, title="Second lot")
    c = Q.create_capa(world, JORDAN, kind="corrective", title="Supplier 8D", ncr_ids=[a["id"], b["id"]])
    assert [x["name"] for x in Q.capa_ncrs(world, c["id"])] == ["NCR-00001", "NCR-00002"]
    with pytest.raises(Q.QualityError, match="why"):
        Q.cancel_capa(world, c["id"], JORDAN, "")
    assert Q.cancel_capa(world, c["id"], JORDAN, "duplicate of supplier's own 8D")["status"] == "cancelled"
    assert Q.create_capa(world, JORDAN, kind="corrective", title="Again", ncr_ids=[a["id"]])


def test_rejected_inspections_open_ncrs_automatically(world):
    # QI-1 (10-02) and QI-3 (08-01) are rejected; counting starts on the day the feature first runs
    assert AUTO.open_for_rejected(world, AS_OF.replace(day=1)) == ["NCR-00001"]   # starts 10-01: only QI-1
    n = Q.ncr(world, 1)
    assert (n["inspection"], n["supplier"], n["receipt"], float(n["quantity"]), n["owner"]) == \
        ("QI-1", "Gulf Fasteners", "PR-2", 50.0, None)
    assert n["created_by"] == Q.SYSTEM and "Opened automatically" in n["description"]
    assert AUTO.open_for_rejected(world, AS_OF) == []                              # once per inspection


def test_objects_metric_anomalies_and_chain(world):
    assert M.open_nonconformances(world, AS_OF, 30)["value"] == 1                 # QI-1 rejected, no NCR yet
    AN.detect(world, AS_OF)
    n = ncr(world, inspection="QI-1", item_code="BOLT-B", receipt="PR-2", supplier="Gulf Fasteners", quantity=50)
    c = Q.create_capa(world, JORDAN, kind="corrective", title="Supplier 8D", ncr_ids=[n["id"]],
                      description="Thread damage", risk="medium")
    Q.submit_capa(world, c["id"], JORDAN)
    world.execute("insert into capa_actions (capa_id, text, owner, due) values (%s, 'Supplier root cause', %s, "
                  "'2026-10-01')", (c["id"], JORDAN))                             # due before today (set directly)
    OP.project(world, manifest=DEMO)
    links = {r["type"]: r["dst_key"] for r in world.execute(
        "select * from ont_links where src_type = 'Nonconformance' and src_key = 'NCR-00001'").fetchall()}
    assert links == {"item": "BOLT-B", "supplier": "Gulf Fasteners", "receipt": "PR-2", "inspection": "QI-1"}
    assert world.execute("select dst_key from ont_links where src_type = 'Capa' and type = 'ncr'").fetchone()[
        "dst_key"] == "NCR-00001"
    m = M.open_nonconformances(world, AS_OF, 30)
    assert m["value"] == 1 and [x["key"] for x in m["ncrs"]] == ["NCR-00001"] and m["inspections"] == []
    for _ in range(2):
        AN.detect(world, AS_OF)
    active = {(a["rule"], a["subject_key"]) for a in world.execute(
        "select * from anomalies where status in ('open', 'ack', 'doing')").fetchall()}
    assert ("capa_overdue", "CAPA-00001") in active and ("inspection_rejected", "QI-1") not in active
    out = CH.explain(world, "QualityInspection", "QI-1", AS_OF)
    assert [(s["to"][1], s["why"]) for s in out["impact"][:2]] == [
        ("NCR-00001", "NCR-00001 is open."), ("CAPA-00001", "CAPA-00001 (corrective) is investigation.")]


def test_quality_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, "alex@demo.example", "lee@demo.example", "dana@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        c.post("/api/login", json={"email": e, "password": PW})

    login("alex@demo.example")                       # sales: no quality view
    assert c.get("/api/quality/ncrs").status_code == 403
    login(JORDAN)
    n = c.post("/api/quality/ncrs", json={"title": "Scratched case", "description": "3 cases", "quantity": 3}).json()
    assert n["name"] == "NCR-00001" and n["dispositions"]["use_as_is"]["requires_approval"]
    nid = n["id"]
    assert c.post(f"/api/quality/ncrs/{nid}/contain", json={"containment": "Held"}).json()["status"] == "contained"
    r = c.post(f"/api/quality/ncrs/{nid}/disposition", json={"disposition": "use_as_is", "quantity": 3,
                                                             "reason": "cosmetic"})
    assert r.json()["status"] == "pending_approval"
    r = c.post(f"/api/quality/ncrs/{nid}/approve", json={"password": PW})
    assert r.status_code == 409 and "someone other" in r.json()["detail"]
    assert c.post("/api/quality/dispositions", json={"code": "sort", "name": "Sort"}).status_code == 403
    login(SAM)                                       # operations manager: may edit quality
    r = c.post(f"/api/quality/ncrs/{nid}/approve", json={"password": "wrong pass 9"})
    assert r.status_code == 403 and "password is wrong" in r.json()["detail"]
    r = c.post(f"/api/quality/ncrs/{nid}/approve", json={"password": PW}).json()
    assert r["status"] == "dispositioned" and r["signatures"][0]["email"] == SAM
    cp = c.post("/api/quality/capas", json={"kind": "preventive", "title": "Better packing", "ncr_id": nid,
                                            "description": "Scratches in transit", "risk": "low"}).json()
    assert cp["ncrs"][0]["name"] == "NCR-00001" and cp["status"] == "draft"
    cid = cp["id"]
    assert c.post(f"/api/quality/capas/{cid}/submit").json()["status"] == "investigation"
    c.post(f"/api/quality/capas/{cid}/update", json={"containment": "Re-packed", "root_cause": "Thin foam"})
    acts = c.post(f"/api/quality/capas/{cid}/action", json={"text": "New foam", "owner": "lee@demo.example",
                                                            "due": "2099-01-31"}).json()["actions"]
    assert c.post(f"/api/quality/capas/{cid}/plan").json()["status"] == "implementation"
    login("lee@demo.example")                        # warehouse: owns the action, cannot edit quality
    assert [a["text"] for a in c.get("/api/quality/my-actions").json()] == ["New foam"]
    assert c.post(f"/api/quality/capas/{cid}/effectiveness-check").status_code == 403
    r = c.post(f"/api/quality/capas/{cid}/action-done", json={"action_id": acts[0]["id"], "evidence": "PO 5 foam"})
    assert r.json()["actions"][0]["done"]
    login("dana@demo.example")
    assert c.post("/api/quality/dispositions", json={"code": "sort", "name": "Sort"}).json()["code"] == "sort"
    assert [s["meaning"] for s in c.get("/api/quality/signatures").json()] == ["Disposition approved"]
    c.__exit__(None, None, None)
