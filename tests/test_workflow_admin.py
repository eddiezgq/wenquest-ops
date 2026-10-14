"""Changing quality workflows, step 15b (ADR-0015): drafts, red lines, changes shown, signed enabling by someone who
did not change the draft, records finishing under their version, the company's own fields and extra signed
approvals. Fictional data only."""

import copy

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import DEMO
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_admin as WA

PW = "Demo pass 2026"
JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA):
        Acc.set_password(conn, e, PW)
    return conn


def who(conn, email):
    return Acc.get(conn, email)


def company_changes(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["fields"] = {"lot_no": {"label": "Lot number", "type": "text", "required_at": ["contain"]},
                     "found_at": {"label": "Found at", "type": "choice", "choices": ["Receiving", "Shipping"]},
                     "cost": {"label": "Cost", "type": "number"}}
    cfg["approvals"] = [{"name": "owner_close", "label": "Owner approval", "before": "close", "roles": ["owner"],
                         "sign": "Closing approved by the owner", "not_by": ["created_by"],
                         "when": {"severity": ["minor"]}}]
    cfg["steps"]["contain"]["label"] = "Quarantine"
    return cfg


def test_who_may_change_workflows():
    assert {r for r, perms in P.ROLE_PERMISSIONS.items() if "workflows:configure" in perms} == {"owner", "quality"}


def test_new_fields_and_approvals_are_checked():
    cfg = company_changes(W.default("ncr"))
    assert W.validate(cfg) == []
    bad = copy.deepcopy(cfg)
    bad["fields"]["Lot No"] = {"label": "", "type": "colour"}
    bad["fields"]["containment"] = {"label": "Again", "type": "text"}
    bad["fields"]["side"] = {"label": "Side", "type": "choice", "choices": ["left"], "required_at": ["fly"]}
    bad["approvals"] += [{"name": "owner_close", "label": "x", "before": "close", "roles": [], "sign": ""},
                         {"name": "x2", "label": "y", "before": "nowhere", "roles": ["king"], "sign": "s",
                          "when": {"colour": ["red"], "severity": ["huge"]}, "not_by": ["submitted_by"]}]
    bad["extra"] = 1
    found = " | ".join(W.validate(bad))
    for says in ("field 'Lot No'", "field Lot No: give it a label", "type is one of", "field 'containment'",
                 "at least two choices", "step 'fly'", "unique name", "approval owner_close: an approval is signed",
                 "name the roles", "'nowhere' does not exist", "condition on 'colour'", "severity is one of minor",
                 "'submitted_by' is not a person", "'extra' is not part of a workflow"):
        assert says in found, says
    assert W.diff(W.default("ncr"), cfg) == [
        "step contain: label 'Contain' -> 'Quarantine'", "new field cost (Cost, number)",
        "new field found_at (Found at, choice)", "new field lot_no (Lot number, text)",
        "new approval owner_close: Owner approval before close, by owner"]
    people = {JORDAN}
    assert W.clean_custom(cfg, {"cost": "12.5", "found_at": "Shipping", "lot_no": " L-7 "}, people) == \
        {"cost": 12.5, "found_at": "Shipping", "lot_no": "L-7"}
    for vals, says in (({"cost": "a lot"}, "a number"), ({"found_at": "Roof"}, "one of Receiving, Shipping"),
                       ({"colour": "red"}, "no field 'colour'")):
        with pytest.raises(W.StepError, match=says):
            W.clean_custom(cfg, vals, people)


def test_draft_change_and_signed_enabling(world):
    old = Q.create_ncr(world, JORDAN, title="Bent", description="12 bent", quantity=12)
    d = WA.new_draft(world, "ncr", JORDAN)
    assert (d["version"], d["status"], d["edited_by"]) == (2, "draft", [JORDAN])
    with pytest.raises(WA.AdminError, match="already a draft"):
        WA.new_draft(world, "ncr", DANA)
    broken = copy.deepcopy(d["config"])
    broken["steps"]["close"].pop("sign")
    WA.save(world, d["id"], JORDAN, broken)
    v = WA.view(world, WA.get(world, d["id"]))
    assert v["errors"] and "signed" in v["errors"][0]
    with pytest.raises(WA.AdminError, match="fix these first"):
        WA.enable(world, d["id"], who(world, DANA), PW)
    WA.save(world, d["id"], JORDAN, company_changes(d["config"]))
    v = WA.view(world, WA.get(world, d["id"]))
    assert v["errors"] == [] and "new field lot_no (Lot number, text)" in v["changes"]
    assert [h["action"] for h in v["history"]] == ["draft made", "changed", "changed"]
    with pytest.raises(PermissionError, match="did not change this draft"):
        WA.enable(world, d["id"], who(world, JORDAN), PW)
    with pytest.raises(Q.SignatureError):
        WA.enable(world, d["id"], who(world, DANA), "wrong pass 1")
    on = WA.enable(world, d["id"], who(world, DANA), PW)
    assert on["status"] == "enabled" and on["fingerprint"] == W.fingerprint(on["config"])
    assert world.execute("select status from workflow_versions where version = 1 and kind = 'ncr'").fetchone()[
        "status"] == "retired"
    assert [s["meaning"] for s in Q.signatures(world, "workflow", d["id"])] == ["Workflow version enabled"]
    with pytest.raises(WA.AdminError, match="enabled; changes go into a new draft"):
        WA.save(world, d["id"], DANA, on["config"])
    with pytest.raises(psycopg.errors.RaiseException, match="frozen"):
        world.execute("update workflow_versions set edited_by = '{}' where id = %s", (d["id"],))

    # the old report finishes under version 1: no lot number needed
    assert Q.contain(world, old["id"], JORDAN, "held")["status"] == "contained"
    new = Q.create_ncr(world, SAM, title="Scratched", description="3 scratched", quantity=3)
    assert new["workflow_version"] == d["id"]
    with pytest.raises(Q.QualityError, match="still needed: Lot number"):
        Q.contain(world, new["id"], JORDAN, "held")
    with pytest.raises(Q.QualityError, match="a number"):
        Q.update_ncr(world, new["id"], JORDAN, custom={"cost": "lots"})
    Q.update_ncr(world, new["id"], JORDAN, custom={"lot_no": "L-7", "cost": "40"})
    assert Q.ncr(world, new["id"])["custom"] == {"lot_no": "L-7", "cost": 40.0}
    assert Q.contain(world, new["id"], JORDAN, "held")["status"] == "contained"
    Q.submit_disposition(world, new["id"], JORDAN, "scrap", 3, "scrap them")
    with pytest.raises(Q.QualityError, match="Owner approval is needed first"):
        Q.close_ncr(world, new["id"], who(world, JORDAN), PW)
    with pytest.raises(PermissionError, match="only owner may give it"):
        Q.approve_extra(world, "ncr", new["id"], "owner_close", who(world, JORDAN), PW)
    Q.approve_extra(world, "ncr", new["id"], "owner_close", who(world, DANA), PW)
    with pytest.raises(Q.QualityError, match="already given"):
        Q.approve_extra(world, "ncr", new["id"], "owner_close", who(world, DANA), PW)
    assert Q.close_ncr(world, new["id"], who(world, JORDAN), PW)["status"] == "closed"
    assert [s["meaning"] for s in Q.signatures(world, "ncr", new["id"])] == [
        "Closing approved by the owner", "Nonconformance closed"]
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("delete from quality_approvals")


def test_approval_not_by_and_conditions(world):
    d = WA.new_draft(world, "ncr", JORDAN)
    WA.save(world, d["id"], JORDAN, company_changes(d["config"]))
    WA.enable(world, d["id"], who(world, DANA), PW)
    mine = Q.create_ncr(world, DANA, title="By the owner", description="x", quantity=1, owner=JORDAN)
    Q.update_ncr(world, mine["id"], JORDAN, custom={"lot_no": "L-1"})
    Q.contain(world, mine["id"], JORDAN, "held")
    Q.submit_disposition(world, mine["id"], JORDAN, "scrap", 1, "scrap")
    with pytest.raises(Q.QualityError, match="someone other than the person who opened it"):
        Q.approve_extra(world, "ncr", mine["id"], "owner_close", who(world, DANA), PW)
    major = Q.create_ncr(world, JORDAN, title="Big", description="y", quantity=1, severity="major")
    with pytest.raises(Q.QualityError, match="not needed"):
        Q.approve_extra(world, "ncr", major["id"], "owner_close", who(world, DANA), PW)
    assert Q.approvals(world, "ncr", major) == []


def test_discarding_a_draft(world):
    d = WA.new_draft(world, "capa", JORDAN)
    with pytest.raises(WA.AdminError, match="changes nothing"):
        WA.enable(world, d["id"], who(world, DANA), PW)
    with pytest.raises(WA.AdminError, match="say why"):
        WA.discard(world, d["id"], JORDAN, "")
    assert WA.discard(world, d["id"], JORDAN, "not needed")["status"] == "discarded"
    assert WA.new_draft(world, "capa", JORDAN)["version"] == 3      # numbers are never reused


def test_workflow_admin_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, DANA):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(SAM)                                                 # operations manager: may look, not change
    assert c.get("/api/quality/workflows").json()["ncr"]["can_configure"] is False
    assert c.post("/api/quality/workflows/ncr/drafts").status_code == 403
    login(JORDAN)
    d = c.post("/api/quality/workflows/ncr/drafts").json()
    assert d["status"] == "draft" and d["changes"] == [] and d["enabled_version"] == 1
    cfg = company_changes(d["config"])
    v = c.put(f"/api/quality/workflows/versions/{d['id']}", json={"config": cfg, "note": "lot numbers"}).json()
    assert v["errors"] == [] and len(v["changes"]) == 5 and v["note"] == "lot numbers"
    assert c.post(f"/api/quality/workflows/versions/{d['id']}/enable", json={"password": PW}).status_code == 403
    login(DANA)
    on = c.post(f"/api/quality/workflows/versions/{d['id']}/enable", json={"password": PW}).json()
    assert on["status"] == "enabled" and on["signatures"][0]["email"] == DANA
    n = c.post("/api/quality/ncrs", json={"title": "Dented", "description": "3 dented", "quantity": 3}).json()
    assert n["fields"]["lot_no"]["label"] == "Lot number" and n["approvals"][0]["name"] == "owner_close"
    r = c.post(f"/api/quality/ncrs/{n['id']}/update", json={"custom": {"found_at": "Roof"}})
    assert r.status_code == 409 and "Receiving, Shipping" in r.json()["detail"]
    r = c.post(f"/api/quality/ncrs/{n['id']}/update", json={"custom": {"found_at": "Shipping"}}).json()
    assert r["custom"] == {"found_at": "Shipping"}
    r = c.post(f"/api/quality/ncrs/{n['id']}/approvals/owner_close", json={"password": PW})
    assert r.status_code == 409 and "before close" in r.json()["detail"]   # not yet at the closing stage
    out = c.get("/api/quality/workflows").json()["ncr"]
    assert out["enabled"]["version"] == 2 and [x["status"] for x in out["versions"]] == ["enabled", "retired"]
