"""Quality workflows as configuration, step 15a (ADR-0015): the default workflows are the Phase 1 behaviour (the
existing quality tests run unchanged on them), the red lines of ADR-0010 cannot be configured away, versions are
frozen and records finish under the version they started with, and numbers do not clash. Fictional data only."""

import copy
import threading
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from tests.test_metrics import DEMO
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W

PW = "Demo pass 2026"
JORDAN, SAM = "jordan@demo.example", "sam@demo.example"


def errs(kind, change):
    cfg = copy.deepcopy(W.default(kind))
    change(cfg)
    return " | ".join(W.validate(cfg))


def test_default_workflows_are_valid_and_describe_phase_one():
    for kind in W.KINDS:
        assert W.validate(W.default(kind)) == [], kind
    ncr = W.default("ncr")
    assert ncr["steps"]["approve"]["not_by"] == ["disposition_by"] and ncr["steps"]["close"]["sign"]
    assert W.default("capa")["steps"]["effective"]["not_by"] == ["owner"]
    assert W.fingerprint(ncr) == W.fingerprint(copy.deepcopy(ncr))


@pytest.mark.parametrize(("kind", "change", "says"), [
    ("ncr", lambda c: c["steps"]["close"].pop("sign"), "signed with the person's password"),
    ("ncr", lambda c: c["steps"]["approve"].update(not_by=[]), "separation of duties cannot be removed"),
    ("capa", lambda c: c["steps"]["effective"].update(not_by=["created_by"]), "the owner may not do it"),
    ("ncr", lambda c: c["steps"]["close"].update(kind="other"), "stays a close step"),
    ("ncr", lambda c: c["steps"].pop("cancel"), "cannot be removed"),
    ("ncr", lambda c: c["steps"].update(delete={"from": ["open"], "to": "closed", "permission": "quality:edit"}),
     "not a step WenQuest Ops can carry out"),
    ("ncr", lambda c: c["states"].update(parked={"label": "Parked"}), "state parked cannot be reached"),
    ("ncr", lambda c: c["steps"]["contain"].update(to="limbo"), "state limbo does not exist"),
    ("ncr", lambda c: c["steps"]["cancel"].update(**{"from": ["closed"]}), "a final state is locked"),
    ("capa", lambda c: c["steps"]["to_effectiveness"].update(to="implementation"),
     "state effectiveness cannot be reached"),
    ("ncr", lambda c: c["steps"]["contain"].update(required=["colour"]), "unknown field 'colour'"),
    ("ncr", lambda c: c["steps"]["contain"].update(permission="quality:everything"), "permission"),
    ("ncr", lambda c: c["steps"]["contain"].update(roles=["janitor"]), "unknown role"),
    ("ncr", lambda c: c["rules"].update(capa_closed_before_close=[]), "major nonconformance closes only after"),
    ("ncr", lambda c: c["rules"].update(eight_d_before_close=["huge"]), "severities are minor, major"),
    ("capa", lambda c: c["rules"].update(one_open_capa_per_ncr=False), "cannot be removed"),
    ("ncr", lambda c: c["numbering"].update(digits=1), "numbering"),
    ("ncr", lambda c: c.update(initial="nowhere"), "first state"),
])
def test_red_lines_cannot_be_configured_away(kind, change, says):
    assert says in errs(kind, change)


def test_dead_ends_and_states_in_use():
    def dead_end(c):
        c["steps"]["cancel"]["from"] = ["open", "contained", "dispositioned"]
        c["steps"]["approve"]["from"] = ["contained"]
        c["steps"]["reject_disposition"]["from"] = ["contained"]
    assert "state pending_approval has no step out of it" in errs("ncr", dead_end)
    cfg = W.default("ncr")
    assert W.validate(cfg, in_use={"open", "on_hold"}) == ["records are in state on_hold now; a new version cannot "
                                                           "remove it"]
    tighter = copy.deepcopy(cfg)                       # tightening is always allowed
    tighter["steps"]["approve"]["not_by"] = ["disposition_by", "created_by"]
    tighter["steps"]["contain"]["roles"] = ["quality", "owner"]
    tighter["rules"]["capa_closed_before_close"] = ["minor", "major"]
    tighter["rules"]["eight_d_before_close"] = ["major"]
    assert W.validate(tighter) == []


def test_the_guard():
    cfg = W.default("ncr")
    rec = {"name": "NCR-00007", "status": "contained", "disposition_by": JORDAN}
    with pytest.raises(W.StepError, match="NCR-00007 is contained; this step needs it to be pending approval"):
        W.check(cfg, rec, "approve", {"email": SAM})
    rec["status"] = "pending_approval"
    with pytest.raises(W.StepError, match="someone other than the person who submitted the disposition"):
        W.check(cfg, rec, "approve", {"email": JORDAN})
    with pytest.raises(W.NotAllowed, match="your role does not allow"):
        W.check(cfg, rec, "approve", {"email": SAM, "roles": ["sales"]})
    assert W.check(cfg, rec, "approve", {"email": SAM, "roles": ["quality"]})["sign"] == "Disposition approved"
    with pytest.raises(W.StepError, match="still needed: quantity, reason"):
        W.check(cfg, dict(rec, status="contained"), "disposition", None, {"disposition": "scrap"})
    strict = copy.deepcopy(cfg)
    strict["steps"]["approve"]["roles"] = ["owner"]
    with pytest.raises(W.NotAllowed, match="only owner may do this"):
        W.check(strict, rec, "approve", {"email": SAM, "roles": ["quality"]})
    assert W.target(cfg, "disposition", True) == "pending_approval" and W.target(cfg, "disposition") == \
        "dispositioned"


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM):
        Acc.set_password(conn, e, PW)
    return conn


def enable(conn, kind, cfg, version):
    """A new enabled version (the editing and signed enabling come in 15b)."""
    assert W.validate(cfg) == []
    conn.execute("update workflow_versions set status = 'retired' where kind = %s and status = 'enabled'", (kind,))
    return conn.execute("insert into workflow_versions (kind, version, config, status, fingerprint, created_by, "
                        "enabled_by, enabled_at) values (%s, %s, %s, 'enabled', %s, %s, %s, now()) returning *",
                        (kind, version, Json(cfg), W.fingerprint(cfg), JORDAN, SAM)).fetchone()


def test_versions_are_frozen_and_records_keep_theirs(world):
    old = Q.create_ncr(world, JORDAN, title="Bent", description="12 bent", quantity=12)
    v1 = W.ensure(world, "ncr")
    assert old["workflow_version"] == v1["id"] and v1["version"] == 1 and old["name"] == "NCR-00001"
    assert W.ensure(world, "ncr")["id"] == v1["id"]                    # the default is stored once
    with pytest.raises(psycopg.errors.RaiseException, match="frozen"):
        world.execute("update workflow_versions set config = '{}' where id = %s", (v1["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("delete from workflow_versions")
    cfg = copy.deepcopy(v1["config"])
    cfg["numbering"] = {"prefix": "NC", "digits": 4}
    cfg["rules"]["capa_closed_before_close"] = ["minor", "major"]
    v2 = enable(world, "ncr", cfg, 2)
    new = Q.create_ncr(world, JORDAN, title="Scratched", description="3 scratched", quantity=3)
    assert new["name"] == "NC-0002" and new["workflow_version"] == v2["id"]
    for n in (old, new):
        Q.contain(world, n["id"], JORDAN, "held")
        Q.submit_disposition(world, n["id"], JORDAN, "scrap", 1, "scrap it")
    assert Q.close_ncr(world, old["id"], Acc.get(world, JORDAN), PW)["status"] == "closed"   # v1: minor needs no CAPA
    with pytest.raises(Q.QualityError, match="minor: it closes when a linked corrective action is closed"):
        Q.close_ncr(world, new["id"], Acc.get(world, JORDAN), PW)                        # v2: it does
    eight = copy.deepcopy(cfg)
    eight["rules"]["eight_d_before_close"] = ["minor"]
    eight["rules"]["capa_closed_before_close"] = ["major"]
    enable(world, "ncr", eight, 3)
    third = Q.create_ncr(world, JORDAN, title="Torn", description="2 torn", quantity=2)
    Q.contain(world, third["id"], JORDAN, "held")
    Q.submit_disposition(world, third["id"], JORDAN, "scrap", 1, "scrap it")
    with pytest.raises(Q.QualityError, match="its 8D is complete"):
        Q.close_ncr(world, third["id"], Acc.get(world, JORDAN), PW)


def test_numbers_do_not_clash_when_two_are_created_at_once(db_url, world):
    names, other = [], DB.connect(db_url)

    def second():
        names.append(Q.create_ncr(other, SAM, title="B", description="b", quantity=1)["name"])

    with world.transaction():
        names.append(Q.create_ncr(world, JORDAN, title="A", description="a", quantity=1)["name"])
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.5)                                  # the second waits for the first transaction's lock
        assert len(names) == 1
    t.join(10)
    other.close()
    assert sorted(names) == ["NCR-00001", "NCR-00002"]


def test_workflows_page_data(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, JORDAN, PW)
    c.post("/api/login", json={"email": JORDAN, "password": PW})
    n = c.post("/api/quality/ncrs", json={"title": "Dented", "description": "3 dented", "quantity": 3}).json()
    assert n["workflow"]["version"] == 1 and [s["step"] for s in n["workflow"]["next"]] == ["update", "contain",
                                                                                            "cancel", "complete_8d"]
    out = c.get("/api/quality/workflows").json()
    ncr = out["ncr"]
    assert ncr["enabled"]["version"] == 1 and ncr["counts"] == {"open": 1}
    assert ncr["workflow"]["steps"]["approve"]["not_by_text"] == ["the person who submitted the disposition"]
    assert out["capa"]["workflow"]["steps"]["plan"]["needs"] == ["containment", "root cause", "at least one action"]
