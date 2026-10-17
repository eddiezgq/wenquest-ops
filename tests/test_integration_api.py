"""The machine interface, step 20d (ADR-0020): access tokens kept only as a hash, limited and revocable, every call
logged; measurements and production step results checked when they arrive, then accepted by a person with their
password (a machine never signs) or rejected with a reason; events written by the database and read in order; the
example client in docs/examples. Fictional data only; no network (the example client talks to the test client)."""

import datetime as dt
import importlib.util
import json
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_calibration import calibrate, caliper
from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, approved, receipts, table
from tests.test_production import active_template
from tests.test_quality_data import business
from tests.test_recall import world  # noqa: F401 - the fixture
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import integration as IG
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import iqc as I
from wqops.hub.quality import production as PRD
from wqops.hub.quality import records as Q

T = AS_OF
CHARS = [{"name": "Length", "kind": "measured", "lsl": 9.8, "usl": 10.2}, {"name": "Finish", "kind": "attribute"}]


def inspection(conn, receipt="PR-7"):
    table(conn)
    approved(conn)
    p = I.new_plan(conn, JORDAN, "BOLT-B", 1.0, CHARS)
    I.enable_plan(conn, Acc.get(conn, DANA), p["id"], PW)
    return I.start(conn, JORDAN, "BOLT-B", receipt=receipt, today=T)


def ok(conn, user, iid, pw=PW):
    """Accept as a person who opened the item just now."""
    return IG.accept(conn, user, iid, pw, seen=IG.item(conn, iid)["print"], today=T)


def test_tokens(world):  # noqa: F811
    row, token = IG.new_token(world, DANA, "Line 1 MES", ["measurements:send", "events:read"])
    assert token.startswith("wqo_") and row["prefix"] == token[:10] and "token_hash" not in row
    assert world.execute("select count(*) as n from integration_tokens where token_hash = %s",
                         (token,)).fetchone()["n"] == 0                       # only a hash is kept
    with pytest.raises(IG.IntegrationError, match="already has a token"):
        IG.new_token(world, DANA, "line 1 mes", ["events:read"])
    with pytest.raises(IG.IntegrationError, match="choose what it may do"):
        IG.new_token(world, DANA, "Bench", ["quality:edit"])
    assert IG.authenticate(world, token)["name"] == "Line 1 MES"
    assert IG.authenticate(world, token + "x") is None and IG.authenticate(world, "nope") is None
    IG.revoke(world, DANA, row["id"], "replaced")
    assert IG.authenticate(world, token) is None
    with pytest.raises(IG.IntegrationError, match="already revoked"):
        IG.revoke(world, DANA, row["id"])
    with pytest.raises(psycopg.errors.RaiseException, match="cannot change"):
        world.execute("update integration_tokens set scopes = '{events:read}'")
    with pytest.raises(psycopg.errors.RaiseException, match="revoke it"):
        world.execute("delete from integration_tokens")
    IG.new_token(world, DANA, "Line 1 MES", ["events:read"])               # the name is free again


def test_measurements_wait_for_a_person(world):  # noqa: F811
    w = world
    ins = inspection(w)
    tok = IG.authenticate(w, IG.new_token(w, DANA, "CMM station", ["measurements:send"])[1])
    def one(sample, char, value):
        return {"inspection": ins["name"], "readings": [{"sample": sample, "characteristic": char, "value": value}]}
    for bad, msg in (({"inspection": "IQC-99"}, "no incoming inspection"),
                     ({"inspection": ins["name"], "readings": []}, "a list"),
                     (one(9, "Length", 1), "sample is 1 to 3"),
                     (one(1, "Finish", 1), "not a measured characteristic"),
                     (one(1, "Length", "x"), "not a number"), (one(1, "Length", True), "a number"),
                     (one(1, "Length", 10) | {"equipment": "NOPE"}, "no measuring equipment")):
        with pytest.raises(IG.IntegrationError, match=msg):
            IG.receive_measurements(w, tok, bad)
    rd = [{"sample": s, "characteristic": "Length", "value": v} for s, v in ((1, 10.01), (2, 9.99), (3, 10.0))]
    got = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd})
    assert got["status"] == "pending"
    assert all(r["value"] is None for r in I.readings(w, ins["id"]))       # nothing written yet
    me = Acc.get(w, JORDAN)
    with pytest.raises(PermissionError):
        ok(w, me, got["id"], "wrong")
    out = ok(w, me, got["id"], PW)
    assert out["status"] == "accepted" and out["result"] == f"3 readings into {ins['name']}"
    length = {r["sample"]: r for r in I.readings(w, ins["id"]) if r["characteristic"] == "Length"}
    assert length[2]["value"] == 9.99 and length[2]["inbox_id"] == got["id"] and length[2]["entered_by"] == JORDAN
    with pytest.raises(IG.IntegrationError, match="it was accepted by"):
        ok(w, me, got["id"], PW)
    assert Q.signatures(w, "integration_inbox", got["id"])[0]["meaning"].startswith("Measurements from CMM station")
    I.enter(w, JORDAN, ins["id"], [{"sample": 2, "characteristic": "Length", "value": 10.02}])
    assert {r["sample"]: r["inbox_id"] for r in I.readings(w, ins["id"]) if r["characteristic"] == "Length"}[2] is None
    g = caliper(w)                                                          # not calibrated: out of service
    again = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd[:1], "equipment": "CAL-01"})
    assert IG.item(w, again["id"])["replaces"] == []
    with pytest.raises(IG.IntegrationError, match="CAL-01"):
        ok(w, me, again["id"], PW)
    calibrate(w, g["id"], T - dt.timedelta(days=1))
    assert ok(w, me, again["id"], PW)["status"] == "accepted"
    assert I.view(w, ins["id"], T)["gauges"]["Length"]["gauge_code"] == "CAL-01"
    third = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": [
        {"sample": 3, "characteristic": "Length", "value": 10.1}]})
    assert IG.item(w, third["id"])["replaces"] == [{"sample": 3, "characteristic": "Length", "value": 10.1,
                                                   "before": 10.0}]
    with pytest.raises(IG.IntegrationError, match="say why"):
        IG.reject(w, JORDAN, third["id"], " ")
    assert IG.reject(w, JORDAN, third["id"], "wrong part on the fixture")["status"] == "rejected"
    with pytest.raises(psycopg.errors.RaiseException, match="cannot change"):
        w.execute("update integration_inbox set payload = '{}'")
    opened = IG.item(w, IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd[1:2]})["id"])
    assert opened["blocks"] == ["Length is measured with CAL-01 in this inspection, the machine does not say with what"]
    looked = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd[1:2], "equipment": "CAL-01"})
    seen = IG.item(w, looked["id"])["print"]
    I.enter(w, JORDAN, ins["id"], [{"sample": 2, "characteristic": "Length", "value": 10.03}])   # typed after
    with pytest.raises(IG.IntegrationError, match="changed since you opened it"):
        IG.accept(w, me, looked["id"], PW, seen=seen, today=T)
    late = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd[:1]})
    I.enter(w, JORDAN, ins["id"], [{"sample": s, "characteristic": "Finish", "passed": True} for s in (1, 2, 3)])
    I.sign(w, me, ins["id"], PW, today=T)
    assert f"{ins['name']} is judged now" in IG.item(w, late["id"])["blocks"]
    with pytest.raises(IG.IntegrationError, match="is judged now"):
        ok(w, me, late["id"], PW)
    with pytest.raises(IG.IntegrationError, match="takes no more readings"):
        IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": rd[:1]})


def test_limits_on_what_machines_send(world, monkeypatch):  # noqa: F811
    w = world
    ins = inspection(w)
    row, token = IG.new_token(w, DANA, "Bench", ["measurements:send"])
    tok = IG.authenticate(w, token)
    sent = IG.receive_measurements(w, tok, {"inspection": ins["name"], "readings": [
        {"sample": 1, "characteristic": "Length", "value": 10}]})
    IG.revoke(w, DANA, row["id"], "bench replaced")
    assert IG.item(w, sent["id"])["blocks"] == ["the token of Bench was revoked: reject what it sent"]
    with pytest.raises(IG.IntegrationError, match="was revoked"):
        ok(w, Acc.get(w, JORDAN), sent["id"])
    monkeypatch.setattr(IG, "MAX_PENDING", 1)
    tok2 = IG.authenticate(w, IG.new_token(w, DANA, "Bench 2", ["measurements:send"])[1])
    IG.receive_measurements(w, tok2, {"inspection": ins["name"], "readings": [
        {"sample": 1, "characteristic": "Length", "value": 10}]})
    with pytest.raises(IG.IntegrationError, match="waiting for a person"):
        IG.receive_measurements(w, tok2, {"inspection": ins["name"], "readings": [
            {"sample": 2, "characteristic": "Length", "value": 10}]})


def test_production_steps_and_events(world):  # noqa: F811
    w = world
    active_template(w)
    rec = PRD.start(w, JORDAN, {"template_id": w.execute("select id from prod_templates where status = 'active'")
                                .fetchone()["id"], "lot_no": "L-9", "planned_qty": 5})
    tok = IG.authenticate(w, IG.new_token(w, DANA, "Assembly MES", ["production:send", "events:read"])[1])
    with pytest.raises(IG.IntegrationError, match="pass or fail"):
        IG.receive_step(w, tok, {"record": rec["name"], "step": 1, "result": "ok"})
    with pytest.raises(IG.IntegrationError, match="the number of a step"):
        IG.receive_step(w, tok, {"record": rec["name"], "step": 7, "value": 1})
    two = IG.receive_step(w, tok, {"record": rec["name"], "step": 2, "value": 10.01})
    one = IG.receive_step(w, tok, {"record": rec["name"], "step": 1, "result": "pass"})
    me = Acc.get(w, JORDAN)
    with pytest.raises(IG.IntegrationError, match="record step 1 first"):
        ok(w, me, two["id"], PW)
    assert ok(w, me, one["id"], PW)["result"] == f"step 1 of {rec['name']} recorded"
    assert ok(w, me, two["id"], PW)["status"] == "accepted"
    steps = {s["seq"]: s for s in PRD.steps(w, rec["id"])}
    assert steps[2]["verdict"] == "pass" and steps[2]["done_by"] == JORDAN and float(steps[2]["value"]) == 10.01
    with pytest.raises(IG.IntegrationError, match="recorded already"):
        IG.receive_step(w, tok, {"record": rec["name"], "step": 1, "result": "pass"})
    IG.receive_step(w, tok, {"record": rec["name"], "step": 3, "text": "torque 12 Nm"})
    with pytest.raises(IG.IntegrationError, match="already waiting"):
        IG.receive_step(w, tok, {"record": rec["name"], "step": 3, "text": "again"})
    first = IG.events(w)
    n = Q.create_ncr(w, JORDAN, title="Burr on shaft", description="Seen at step 2", item_code="WIDGET-A")
    ev = IG.events(w, after=first["next"])
    assert [(e["kind"], e["ref_name"]) for e in ev["events"]] == [("ncr.opened", n["name"])]
    assert ev["events"][0]["data"]["item_code"] == "WIDGET-A" and IG.events(w, after=ev["next"])["events"] == []
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        w.execute("delete from hub_events")


class _Reply:
    def __init__(self, r):
        self.status, self._body = r.status_code, r.content

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_machine_interface(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
        Acc.sync(conn, DEMO)
        ins = inspection(conn, "PR-9")

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(JORDAN)
    assert c.post("/api/integrations/tokens", json={"name": "CMM", "scopes": ["events:read"]}).status_code == 403
    login(DANA)
    made = c.post("/api/integrations/tokens", json={"name": "CMM", "scopes": ["measurements:send"]}).json()
    token = made["token"]
    ev_token = c.post("/api/integrations/tokens",
                      json={"name": "ERP bridge", "scopes": ["events:read"]}).json()["token"]
    assert "token" not in c.get("/api/integrations/tokens").json()["tokens"][0]
    c.cookies.clear()                                                        # machines have no session

    def opener(req, timeout):
        return _Reply(c.request(req.get_method(), req.full_url.replace("http://localhost", ""), content=req.data,
                                headers=dict(req.header_items())))

    spec = importlib.util.spec_from_file_location("mes_client",
                                                  Path(__file__).parents[1] / "docs/examples/mes_client.py")
    mes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mes)
    assert c.get("/api/integration/v1/whoami").status_code == 401
    assert c.get("/api/integration/v1/whoami", headers={"authorization": "Bearer wqo_nope"}).status_code == 401
    st, out = mes.events("http://localhost", token, opener=opener)
    assert st == 403 and "may not" in out["detail"]
    st, out = mes.send_measurements("http://localhost", token, ins["name"], [{"sample": 5, "characteristic": "Length",
                                                                        "value": 10}], opener=opener)
    assert st == 422 and "sample is 1 to 3" in out["detail"]
    st, out = mes.send_measurements("http://localhost", token, ins["name"], [{"sample": 1, "characteristic": "Length",
                                                                        "value": 10.03}], opener=opener)
    assert st == 202 and out["status"] == "pending"
    big = c.post("/api/integration/v1/measurements", content=b"x" * 1_000_001,
                 headers={"authorization": f"Bearer {token}"})
    assert big.status_code == 413
    nul = c.post("/api/integration/v1/measurements", headers={"authorization": f"Bearer {token}"},
                 json={"inspection": ins["name"] + "\x00", "readings": []})
    assert nul.status_code == 400 and "NUL" in nul.json()["detail"]
    login("lee@demo.example")
    inbox = c.get("/api/integrations/inbox").json()
    assert inbox["can_decide"] is False and inbox["items"][0]["sender"] == "CMM"
    assert c.post(f"/api/integrations/inbox/{out['id']}/accept", json={"password": PW}).status_code == 403
    login(JORDAN)
    seen = c.get(f"/api/integrations/inbox/{out['id']}").json()["print"]
    acc = f"/api/integrations/inbox/{out['id']}/accept"
    assert c.post(acc, json={"password": "x", "seen": seen}).status_code == 403
    assert c.post(acc, json={"password": PW, "seen": "x"}).status_code == 409
    done = c.post(acc, json={"password": PW, "seen": seen}).json()
    assert done["status"] == "accepted" and done["link"] == f"/quality/iqc/{ins['id']}"
    assert c.get("/api/integrations/inbox/99999").status_code == 404
    login(DANA)
    calls = c.get(f"/api/integrations/tokens/{made['id']}/calls").json()
    assert [x["status"] for x in calls][:5] == [400, 413, 202, 422, 403]
    with DB.connect(db_url) as conn:                                       # calls without a valid token too
        assert conn.execute("select count(*) as n from integration_calls where token_id is null").fetchone()["n"] == 2
    c.cookies.clear()
    st, out = mes.events("http://localhost", ev_token, opener=opener)
    assert st == 200 and out["events"] == [] and out["next"] == 0
    bearer = {"authorization": f"Bearer {ev_token}"}
    assert c.get("/api/integration/v1/events?limit=0", headers=bearer).status_code == 400
    assert json.loads(c.get("/api/integration/v1/whoami", headers={"authorization": f"Bearer {ev_token}"}).content) == {
        "name": "ERP bridge", "scopes": ["events:read"]}
