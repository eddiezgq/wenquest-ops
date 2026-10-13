"""Quality module, step 8a (ADR-0009 items 1-3, 7, 8): NCR life cycle, 8D, CAPA, objects, metric, anomaly, chain.
All data is fictional (tests/test_metrics.py)."""

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
from wqops.hub.quality import records as Q

JORDAN = "jordan@demo.example"


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    Y.run(conn, ErpClient("http://erp", transport=build().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def log(conn, kind, ref):
    return [h["action"] for h in Q.history(conn, kind, ref)]


def test_ncr_life_cycle(world):
    n = Q.create_ncr(world, JORDAN, title="Bent bolts", description="12 bolts bent in lot", inspection="QI-1",
                     item_code="BOLT-B", receipt="PR-2", supplier="Gulf Fasteners", quantity=12)
    assert n["name"] == "NCR-00001" and n["status"] == "open" and n["owner"] == JORDAN
    with pytest.raises(Q.QualityError, match="needs it to be contained"):
        Q.disposition(world, n["id"], JORDAN, "scrap")
    with pytest.raises(Q.QualityError, match="describe the containment"):
        Q.contain(world, n["id"], JORDAN, " ")
    Q.contain(world, n["id"], JORDAN, "Lot moved to QC Hold; open orders checked")
    with pytest.raises(Q.QualityError, match="disposition is one of"):
        Q.disposition(world, n["id"], JORDAN, "keep")
    Q.disposition(world, n["id"], JORDAN, "return_to_supplier", 12, "RMA requested")
    done = Q.close_ncr(world, n["id"], JORDAN, "credit received")
    assert done["status"] == "closed" and done["disposition"] == "return_to_supplier" and done["closed_at"]
    assert log(world, "ncr", n["id"]) == ["opened", "contained", "dispositioned", "closed"]
    with pytest.raises(Q.QualityError, match="is closed"):
        Q.cancel_ncr(world, n["id"], JORDAN, "oops")


def test_major_ncr_needs_a_closed_capa(world):
    n = Q.create_ncr(world, JORDAN, title="Wrong label", description="Labels swapped", severity="major")
    Q.contain(world, n["id"], JORDAN, "Relabelled stock")
    Q.disposition(world, n["id"], JORDAN, "rework", 40)
    with pytest.raises(Q.QualityError, match="major"):
        Q.close_ncr(world, n["id"], JORDAN)
    c = Q.create_capa(world, JORDAN, kind="corrective", title="Label check at packing", ncr_id=n["id"],
                      actions=[{"text": "Add a scan check", "owner": "lee@demo.example", "due": "2026-10-20"},
                               {"text": "Train packers", "owner": JORDAN}])
    with pytest.raises(Q.QualityError, match="needs it to be in_progress"):
        Q.to_verification(world, c["id"], JORDAN)
    Q.start_capa(world, c["id"], JORDAN)
    with pytest.raises(Q.QualityError, match="not done yet: Add a scan check; Train packers"):
        Q.to_verification(world, c["id"], JORDAN)
    acts = Q.actions(world, c["id"])
    with pytest.raises(PermissionError):
        Q.action_done(world, acts[0]["id"], "alex@demo.example", may_edit=False)
    Q.action_done(world, acts[0]["id"], "lee@demo.example", may_edit=False)   # the owner may
    Q.action_done(world, acts[1]["id"], JORDAN, may_edit=True)
    Q.to_verification(world, c["id"], JORDAN)
    with pytest.raises(Q.QualityError, match="say how"):
        Q.verify(world, c["id"], JORDAN, "effective", "")
    assert Q.verify(world, c["id"], JORDAN, "ineffective", "2 swapped labels last week")["status"] == "in_progress"
    Q.to_verification(world, c["id"], JORDAN)
    assert Q.verify(world, c["id"], JORDAN, "effective", "0 swaps in 3 weeks")["status"] == "closed"
    assert Q.close_ncr(world, n["id"], JORDAN)["status"] == "closed"
    assert log(world, "capa", c["id"]) == ["opened", "action added", "action added", "in_progress", "action done",
                                           "action done", "verification", "in_progress", "verification", "closed"]


def test_8d(world):
    n = Q.create_ncr(world, JORDAN, title="Bent bolts", description="d")
    Q.save_8d(world, n["id"], JORDAN, {"d1": "Jordan, Pat", "d2": "12 of 50 bent"})
    with pytest.raises(Q.QualityError, match="still to write: D3 Containment, D4 Root cause"):
        Q.complete_8d(world, n["id"], JORDAN)
    Q.save_8d(world, n["id"], JORDAN, {k: f"text {k}" for k in ("d3", "d4", "d5", "d6", "d7", "d8")})
    e = Q.complete_8d(world, n["id"], JORDAN)
    assert e["complete"] and e["sections"]["d1"] == "Jordan, Pat"
    with pytest.raises(Q.QualityError, match="complete"):
        Q.save_8d(world, n["id"], JORDAN, {"d1": "changed"})
    with pytest.raises(Q.QualityError, match="unknown 8D sections: d9"):
        Q.save_8d(world, Q.create_ncr(world, JORDAN, title="x", description="y")["id"], JORDAN, {"d9": "x"})


def test_objects_metric_anomalies_and_chain(world):
    assert M.open_nonconformances(world, AS_OF, 30)["value"] == 1          # QI-1 rejected, no NCR yet
    AN.detect(world, AS_OF)
    n = Q.create_ncr(world, JORDAN, title="Rejected BOLT-B", description="d", inspection="QI-1", item_code="BOLT-B",
                     receipt="PR-2", supplier="Gulf Fasteners", quantity=50)
    c = Q.create_capa(world, JORDAN, kind="corrective", title="Supplier 8D", ncr_id=n["id"],
                      actions=[{"text": "Supplier root cause", "owner": JORDAN, "due": "2026-10-01"}])
    OP.project(world, manifest=DEMO)
    o = world.execute("select props from ont_objects where type = 'Nonconformance' and key = 'NCR-00001'").fetchone()
    assert o["props"]["status"] == "open" and o["props"]["quantity"] == 50.0
    links = {r["type"]: r["dst_key"] for r in world.execute(
        "select * from ont_links where src_type = 'Nonconformance' and src_key = 'NCR-00001'").fetchall()}
    assert links == {"item": "BOLT-B", "supplier": "Gulf Fasteners", "receipt": "PR-2", "inspection": "QI-1"}
    m = M.open_nonconformances(world, AS_OF, 30)
    assert m["value"] == 1 and [x["key"] for x in m["ncrs"]] == ["NCR-00001"] and m["inspections"] == []
    for _ in range(2):
        AN.detect(world, AS_OF)
    active = {(a["rule"], a["subject_key"]) for a in world.execute(
        "select * from anomalies where status in ('open', 'ack', 'doing')").fetchall()}
    assert ("capa_overdue", "CAPA-00001") in active                   # due 10-01, not done
    assert ("inspection_rejected", "QI-1") not in active              # the NCR is open: resolved
    out = CH.explain(world, "QualityInspection", "QI-1", AS_OF)
    assert [(s["to"][1], s["why"]) for s in out["impact"][:2]] == [
        ("NCR-00001", "NCR-00001 is open."), ("CAPA-00001", "CAPA-00001 (corrective) is open.")]
    Q.action_done(world, Q.actions(world, c["id"])[0]["id"], JORDAN, may_edit=True)
    OP.project(world, manifest=DEMO)
    for _ in range(2):
        AN.detect(world, AS_OF)
    assert world.execute("select status from anomalies where rule = 'capa_overdue'").fetchone()["status"] == "resolved"


def test_quality_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, "alex@demo.example", "lee@demo.example"):
            Acc.set_password(conn, e, "Demo pass 2026")

    def login(e):
        c.post("/api/login", json={"email": e, "password": "Demo pass 2026"})

    login("alex@demo.example")                       # sales: no quality view
    assert c.get("/api/quality/ncrs").status_code == 403
    login(JORDAN)
    n = c.post("/api/quality/ncrs", json={"title": "Scratched case", "description": "3 cases scratched",
                                          "quantity": 3}).json()
    assert n["name"] == "NCR-00001" and n["history"][0]["action"] == "opened" and n["quantity"] == 3.0
    r = c.post(f"/api/quality/ncrs/{n['id']}/close")
    assert r.status_code == 409 and "needs it to be dispositioned" in r.json()["detail"]
    assert c.post(f"/api/quality/ncrs/{n['id']}/contain", json={"containment": "Held"}).json()["status"] == \
        "contained"
    assert c.post(f"/api/quality/ncrs/{n['id']}/8d", json={"sections": {"d1": "Jordan"}}).json()["eightd"][
        "sections"] == {"d1": "Jordan"}
    assert c.post(f"/api/quality/ncrs/{n['id']}/nope").status_code == 404
    cp = c.post("/api/quality/capas", json={"kind": "preventive", "title": "Better packing", "ncr_id": n["id"],
                                            "actions": [{"text": "New foam", "owner": "lee@demo.example"}]}).json()
    assert cp["ncr"]["name"] == "NCR-00001" and cp["actions"][0]["owner"] == "lee@demo.example"
    assert [x["name"] for x in c.get("/api/quality/ncrs/1").json()["capas"]] == ["CAPA-00001"]
    with DB.connect(db_url) as conn:
        assert conn.execute("select 1 from ont_objects where type = 'Capa'").fetchone()   # projected right away
    login("lee@demo.example")                        # warehouse: owns the action, cannot edit quality
    assert [a["text"] for a in c.get("/api/quality/my-actions").json()] == ["New foam"]
    assert c.post(f"/api/quality/capas/{cp['id']}/start").status_code == 403
    aid = cp["actions"][0]["id"]
    assert c.post(f"/api/quality/capas/{cp['id']}/action-done", json={"action_id": aid}).json()["actions"][0]["done"]
    assert c.get("/api/quality/my-actions").json() == []
    c.__exit__(None, None, None)
