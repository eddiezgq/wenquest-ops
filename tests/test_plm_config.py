"""PLM step 26c (ADR-0026): option groups of a base machine, what each option does to the base BOM, rules between
options, models generated as ordinary items coded base code + option codes with a draft BOM, one model per choice,
and models listed when the configuration no longer matches their BOM. Fictional data only."""

import psycopg
import pytest

from tests.test_plm import CASEY, PW, erp, fake, files_dir, part, released, u, world  # noqa: F401  # noqa: F401
from wqops.hub.plm import boms as B
from wqops.hub.plm import config as CFG
from wqops.hub.plm import parts as PT

SHAFT_AT = {"p": [0.0, 0.0, 240.0], "q": [0.0, 0.0, 0.0, 1.0]}
FEED_AT = {"p": [0.0, 0.0, -2.0], "q": [0.0, 0.0, 0.0, 1.0]}


def base_machine(c, erp):  # noqa: F811
    head = released(c, erp, "Lockstitch head (demo)", "assembly")
    shaft = released(c, erp, "Main shaft", "shaft", d=14, length=420)
    feed = released(c, erp, "Bottom feed dog", "feeddog", rows=3, pitch=1.2)
    motor = released(c, erp, "Plain motor", "motor", "buy", power_w=400, rated_nm=1.2, peak_nm=3, rated_rpm=3000,
                     max_rpm=4500, inertia=0.3)
    others = {
        "servo": released(c, erp, "Direct drive servo", "motor", "buy", power_w=550, rated_nm=1.75, peak_nm=5.25,
                          rated_rpm=3000, max_rpm=5000, inertia=0.42),
        "cfeed": released(c, erp, "Compound feed dog", "feeddog", rows=4, pitch=1.5),
        "trim": released(c, erp, "Thread trimmer", "other"),
        "plate7": released(c, erp, "Needle plate 7 mm", "other"),
    }
    b = B.start(c, u(c, CASEY), head["id"])
    B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": shaft["item_code"], "qty": 1, "placements": [SHAFT_AT]},
                                                 {"code": feed["item_code"], "qty": 1, "placements": [FEED_AT]},
                                                 {"code": motor["item_code"], "qty": 1}])
    return head, shaft, feed, motor, others, b["bom"]["id"]


@pytest.fixture
def setup(world, erp, monkeypatch):  # noqa: F811
    c = world
    monkeypatch.setattr(B, "_supplier", lambda _c, _code: True)       # suppliers approved (17c) for the demo parts
    head, shaft, feed, motor, o, bid = base_machine(c, erp)
    B.release(c, u(c, CASEY), bid, PW, erp)
    cfg = {"groups": [
        {"code": "P", "name": "Stitch length", "options": [
            {"code": "5", "name": "5 mm", "edits": []},
            {"code": "7", "name": "7 mm", "edits": [{"action": "add", "code": o["plate7"]["item_code"], "qty": 1}]}]},
        {"code": "F", "name": "Feed", "options": [
            {"code": "D", "name": "Bottom feed", "edits": []},
            {"code": "C", "name": "Compound feed", "edits": [
                {"action": "replace", "code": feed["item_code"], "with": o["cfeed"]["item_code"]}]}]},
        {"code": "E", "name": "Drive", "options": [
            {"code": "M", "name": "Plain motor", "edits": []},
            {"code": "S", "name": "Servo", "edits": [
                {"action": "replace", "code": motor["item_code"], "with": o["servo"]["item_code"]}]}]},
        {"code": "T", "name": "Trimmer", "options": [
            {"code": "N", "name": "No", "edits": []},
            {"code": "T", "name": "Yes", "edits": [{"action": "add", "code": o["trim"]["item_code"], "qty": 1}]}]}],
        "rules": [{"kind": "requires", "a": "T/T", "b": "E/S"}, {"kind": "excludes", "a": "P/7", "b": "F/D"}]}
    v = CFG.save(c, u(c, CASEY), head["id"], cfg)
    return c, head, shaft, feed, motor, o, v


def test_configuration_round_trip_and_checks(setup):
    c, head, _shaft, feed, _motor, o, v = setup
    assert [g["code"] for g in v["config"]["groups"]] == ["P", "F", "E", "T"]
    assert v["config"]["rules"] == [{"kind": "requires", "a": "T/T", "b": "E/S"},
                                    {"kind": "excludes", "a": "P/7", "b": "F/D"}]
    with pytest.raises(PT.PlmError, match="one group exclude"):
        CFG.save(c, u(c, CASEY), head["id"], {**v["config"], "rules": [{"kind": "excludes", "a": "P/5", "b": "P/7"}]})
    with pytest.raises(PT.PlmError, match="no such part"):
        CFG.save(c, u(c, CASEY), head["id"], {"groups": [{"code": "X", "name": "x", "options": [
            {"code": "1", "name": "one", "edits": [{"action": "add", "code": "NOPE", "qty": 1}]}]}]})
    with pytest.raises(PT.PlmError, match="made assembly"):
        CFG.view(c, feed["id"])
    del o


def test_generate_models_rules_one_per_choice_and_drift(setup, erp, fake):  # noqa: F811
    c, head, shaft, feed, motor, o, _v = setup
    with pytest.raises(PT.PlmError, match="requires E/S"):
        CFG.generate(c, u(c, CASEY), head["id"], {"P": "5", "F": "D", "E": "M", "T": "T"}, erp)
    with pytest.raises(PT.PlmError, match="cannot be chosen together"):
        CFG.generate(c, u(c, CASEY), head["id"], {"P": "7", "F": "D", "E": "S", "T": "N"}, erp)
    with pytest.raises(PT.PlmError, match="choose an option for Trimmer"):
        CFG.generate(c, u(c, CASEY), head["id"], {"P": "5", "F": "D", "E": "S"}, erp)
    r = CFG.generate(c, u(c, CASEY), head["id"], {"P": "7", "F": "c", "E": "S", "T": "T"}, erp)
    m = PT.get(c, r["model"])
    assert m["item_code"] == f"{head['item_code']}-7CST" and m["erp_state"] == "created"
    assert fake.docs["Item"][m["item_code"]]["item_group"] == "PLM"           # an ordinary item, not a variant
    bom = B.view(c, r["bom"], erp)
    assert bom["bom"]["status"] == "draft"                                    # a person releases it
    assert sorted((x["code"], x["qty"]) for x in bom["lines"]) == sorted([
        (shaft["item_code"], "1"), (o["cfeed"]["item_code"], "1"), (o["servo"]["item_code"], "1"),
        (o["plate7"]["item_code"], "1"), (o["trim"]["item_code"], "1")])
    # round 135: where each use sits comes with it; a replacing module sits where the old one did
    at = {r["part_id"]: r["placements"] for r in c.execute("select part_id, placements from plm_bom_lines where "
                                                           "bom_id = %s", (r["bom"],))}
    assert at[shaft["id"]] == [SHAFT_AT] and at[o["cfeed"]["id"]] == [FEED_AT]
    assert at[o["servo"]["id"]] == [] and at[o["trim"]["id"]] == []           # the motor had none; added: none
    again = CFG.generate(c, u(c, CASEY), head["id"], {"P": "7", "F": "C", "E": "S", "T": "T"}, erp)
    assert again["model"] == m["id"] and again["existing"] is True
    v = CFG.view(c, head["id"])
    assert v["models"][0]["differs"] == []
    # the configuration changes: the trimmer comes in 2; the model is listed, not changed
    cfg = v["config"]
    cfg["groups"][3]["options"][1]["edits"][0]["qty"] = 2
    v = CFG.save(c, u(c, CASEY), head["id"], cfg)
    assert v["models"][0]["differs"] == [{"code": o["trim"]["item_code"], "name": "Thread trimmer",
                                          "change": "changed", "old": "1 Nos", "new": "2 Nos"}]
    assert len(B.lines(c, r["bom"])) == 5
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        c.execute("delete from plm_models")
    del feed, motor


def test_api_permissions(setup, db_url, fake):  # noqa: F811
    from fastapi.testclient import TestClient

    from tests.test_plm import manifest
    from wqops.erp import ErpClient
    from wqops.hub.app import create_app

    c, head, *_ = setup
    with TestClient(create_app({}, lambda: (manifest(), "ok"), db_url=db_url,
                               erp=ErpClient("http://erp", transport=fake.transport()))) as cl:
        assert cl.post("/api/login", json={"email": CASEY, "password": PW}).status_code == 200
        v = cl.get(f"/api/plm/parts/{head['id']}/config").json()
        assert len(v["config"]["groups"]) == 4 and v["can_edit"]
        r = cl.post(f"/api/plm/parts/{head['id']}/models", json={"choice": {"P": "5", "F": "D", "E": "S", "T": "N"}})
        assert r.status_code == 201 and r.json()["existing"] is False
        cl.post("/api/logout")
    del c


def test_review_save_checks_versions_and_models(setup, erp):  # noqa: F811
    c, head, _shaft, feed, motor, o, v = setup
    cfg = v["config"]
    draft = part(c, erp, "Draft bracket", "other")
    bad = {**cfg, "groups": [*cfg["groups"], {"code": "X", "name": "x", "options": [
        {"code": "1", "name": "one", "edits": [{"action": "add", "code": draft["item_code"], "qty": 1}]}]}]}
    with pytest.raises(PT.PlmError, match="not released"):
        CFG.save(c, u(c, CASEY), head["id"], bad)
    bad["groups"][-1]["options"][0]["edits"] = [{"action": "remove", "code": o["trim"]["item_code"]}]
    with pytest.raises(PT.PlmError, match="not on the released base BOM"):
        CFG.save(c, u(c, CASEY), head["id"], bad)
    bad["groups"][-1]["options"] = [{"code": "5", "name": "a", "edits": []}, {"code": "57", "name": "b", "edits": []}]
    with pytest.raises(PT.PlmError, match="same length"):
        CFG.save(c, u(c, CASEY), head["id"], bad)
    with pytest.raises(PT.PlmError, match="changed meanwhile"):           # a page from before the last save
        CFG.save(c, u(c, CASEY), head["id"], {**cfg, "version": "0"})
    r = CFG.generate(c, u(c, CASEY), head["id"], {"P": "5", "F": "D", "E": "S", "T": "N"}, erp, v["version"])
    with pytest.raises(PT.PlmError, match="this is a model"):
        CFG.view(c, r["model"])
    assert PT.view(c, r["model"])["model_of"]["id"] == head["id"]
    gone = {**cfg, "groups": [g for g in cfg["groups"] if g["code"] != "T"], "rules": []}
    with pytest.raises(PT.PlmError, match="keep that group"):              # a model uses T/N
        CFG.save(c, u(c, CASEY), head["id"], gone)
    # an earlier generation stopped before its lines: generating again fills the BOM
    c.execute("delete from plm_bom_lines where bom_id = %s", (r["bom"],))
    again = CFG.generate(c, u(c, CASEY), head["id"], {"P": "5", "F": "D", "E": "S", "T": "N"}, erp)
    assert again["bom"] == r["bom"] and len(B.lines(c, r["bom"])) == 3
    del feed, motor
