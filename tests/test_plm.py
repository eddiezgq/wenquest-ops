"""PLM, steps 26a and 26b (ADR-0026): revision letters, category parameters, similar parts, parts made in ERPNext,
signed release that locks a revision, new revisions only under an approved product change, files, design BOMs with
their release checks (unreleased parts, cycles, approved suppliers unknown), a Draft BOM in ERPNext, differences
between two revisions, the module switch and the permissions. Fictional data only."""

import copy
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.fake_erp import FakeErp
from tests.test_documents import DEMO, PW
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub.app import create_app
from wqops.hub.plm import boms as B
from wqops.hub.plm import parts as PT
from wqops.hub.plm import rules as R
from wqops.hub.quality import records as Q

DANA, CASEY, JORDAN, LEE = "dana@demo.example", "casey@demo.example", "jordan@demo.example", "lee@demo.example"
MOTOR = {"power_w": 550, "rated_nm": 1.75, "peak_nm": 5.25, "rated_rpm": 3000, "max_rpm": 5000, "inertia": 0.42}


def manifest(plm: bool = True) -> dict:
    m = copy.deepcopy(DEMO)
    if plm:
        m["modules"] = [*m["modules"], "plm"]
    if CASEY not in {p["email"] for p in m["people"]}:
        m["people"] = [*m["people"], {"name": "Casey Engineer", "email": CASEY, "roles": ["engineering"],
                                      "department": m["people"][0]["department"]}]
    return m


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def fake():
    return FakeErp()


@pytest.fixture
def erp(fake):
    return ErpClient("http://erp", transport=fake.transport())


@pytest.fixture
def world(conn):
    Acc.sync(conn, manifest())
    for e in (DANA, CASEY, JORDAN, LEE):
        Acc.set_password(conn, e, PW)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def approved_change(conn, kind="product", parts=()):
    """A change (fictional) listing ``parts`` ((part id, part | bom | both), 26d), raised, submitted and approved
    through change control."""
    from wqops.hub.plm import ecn as E
    from wqops.hub.quality import change_control as CC

    ch = CC.create(conn, CASEY, {"title": "Hook from a new supplier", "kind": kind, "description": "new hook",
                                 "reason": "supplier change", "owner": CASEY, "assessment": "small",
                                 "q_product": "no", "q_regulatory": "no", "q_risk": "no", "q_validation": "no"})
    for pid, scope in parts:
        E.add_item(conn, u(conn, CASEY), ch["id"], {"part_id": pid, "scope": scope})
    if parts:
        E.set_effect(conn, u(conn, CASEY), ch["id"], {"mode": "now"})
        E.analyse(conn, u(conn, CASEY), ch["id"], None)
    CC.submit(conn, CASEY, ch["id"])
    CC.approve(conn, u(conn, JORDAN), ch["id"], PW)
    return ch["id"]


def part(conn, erp, name, category="other", source="make", **kw):
    return PT.create(conn, u(conn, CASEY), {"name": name, "category": category, "source": source, **kw}, erp)


# ---- rules

def test_revision_letters_skip_i_o_q():
    assert R.next_revision(None) == "A"
    assert R.next_revision("H") == "J" and R.next_revision("N") == "P" and R.next_revision("P") == "R"
    assert R.next_revision("Z") == "AA" and R.next_revision("AZ") == "BA"


def test_params_are_checked_against_the_category():
    assert R.clean_params("needle", {"nm": "90", "blade_d": 0.9}) == {"nm": 90.0, "blade_d": 0.9}
    with pytest.raises(ValueError, match="between"):
        R.clean_params("needle", {"nm": 500})
    with pytest.raises(ValueError, match="not a parameter"):
        R.clean_params("needle", {"torque": 1})
    assert R.clean_params("bearing", {"designation": " 6202-2RS "})["designation"] == "6202-2RS"
    assert R.missing_params("needle", {"nm": 90}) == ["Blade diameter"]


def test_similar_parts_match_on_required_values_within_one_percent():
    others = [{"id": 1, "params": {"nm": 90, "blade_d": 0.9}}, {"id": 2, "params": {"nm": 100, "blade_d": 1.0}},
              {"id": 3, "params": {"nm": 90}}]
    assert [o["id"] for o in R.similar("needle", {"nm": 90.5, "blade_d": 0.9}, others)] == [1]
    assert R.similar("needle", {"nm": 90}, others) == []           # not all required values given: nothing to compare
    b6202 = {"designation": "6202", "d": 15, "D": 35, "B": 11}
    assert [o["id"] for o in R.similar("bearing", b6202, [{"id": 7, "params": b6202}])] == [7]


def test_cycle_and_diff_and_unknown_supplier():
    assert R.cycle(1, [2], {2: [3], 3: [1]}) == [1, 2, 3, 1]
    assert R.cycle(1, [2], {2: [3]}) is None
    old = [{"code": "A", "name": "a", "qty": "1", "uom": "Nos"}, {"code": "B", "name": "b", "qty": "2", "uom": "Nos"}]
    new = [{"code": "A", "name": "a", "qty": "1.0", "uom": "Nos"}, {"code": "C", "name": "c", "qty": "1", "uom": "Nos"}]
    assert [(d["code"], d["change"]) for d in R.diff(old, new)] == [("B", "removed"), ("C", "added")]
    line = {"code": "HOK-1", "qty": "1", "uom": "Nos", "part_status": "released", "source": "buy"}
    checks = R.bom_checks([{**line, "approved_supplier": None}], None)
    assert checks[-1]["result"] == "unknown" and not R.passed(checks)     # missing data never passes
    assert R.passed(R.bom_checks([{**line, "approved_supplier": True}], None))


# ---- parts

def test_part_creation_numbers_makes_the_item_and_finds_similar(world, fake, erp):
    c = world
    p = part(c, erp, "Main motor 550 W", "motor", "buy", params=MOTOR)
    assert p["item_code"] == "MOT-00001" and p["erp_state"] == "created"
    item = fake.docs["Item"]["MOT-00001"]
    assert item["item_group"] == "PLM" and item["stock_uom"] == "Nos" and "PLM" in fake.docs["Item Group"]
    with pytest.raises(PT.Similar) as similar:
        part(c, erp, "Motor again", "motor", "buy", params=MOTOR)
    assert [x["code"] for x in similar.value.parts] == ["MOT-00001"]
    p2 = part(c, erp, "Motor again", "motor", "buy", params=MOTOR, confirm_new=True)
    assert p2["item_code"] == "MOT-00002"
    # a code typed in: an item ERPNext already has is linked, not made again
    fake.put("Item", "OLD-77", item_name="Old part", stock_uom="Nos")
    with pytest.raises(PT.PlmError, match="link the existing item"):     # not silently someone else's item
        part(c, erp, "Old part", code="OLD-77")
    with pytest.raises(PT.PlmError, match="counts in Nos"):
        part(c, erp, "Old part", code="OLD-77", uom="kg", link_existing=True)
    p3 = part(c, erp, "Old part", code="OLD-77", link_existing=True)
    assert p3["erp_state"] == "existing"
    with pytest.raises(PT.PlmError, match="already exists"):
        part(c, erp, "Twice", code="OLD-77", link_existing=True)
    # the company sets its own prefix
    PT.set_numbering(c, DANA, "needle", "ZJ", 4)
    needle = part(c, erp, "Needle DBx1 90", "needle", "buy", params={"nm": 90, "blade_d": 0.9})
    assert needle["item_code"] == "ZJ-0001"
    with pytest.raises(PT.PlmError, match="already used"):
        PT.set_numbering(c, DANA, "hook", "ZJ", 4)


def test_failed_item_is_tried_again(world, fake, erp):
    c = world
    fake.fail_after = len(fake.requests)          # ERPNext stops answering after the part is numbered
    p = part(c, erp, "Shaft", "shaft", params={"d": 12, "length": 300}, code="SFT-OLD-1")
    assert p["erp_state"] == "failed" and p["erp_error"]
    fake.fail_after = None
    assert PT.retry_erp(c, u(c, CASEY), p["id"], erp)["erp_state"] == "created"


def test_release_signs_and_locks_and_new_revision_needs_an_approved_product_change(world, erp):
    c = world
    p = part(c, erp, "Needle bar", "needlebar")
    with pytest.raises(PT.PlmError, match="required parameters"):
        PT.release(c, u(c, CASEY), p["id"], PW)
    PT.update(c, u(c, CASEY), p["id"], {"params": {"mass": 0.05, "d": 7}, "description": "chrome plated"})
    with pytest.raises(Q.SignatureError, match="password"):
        PT.release(c, u(c, CASEY), p["id"], "wrong")
    v = PT.release(c, u(c, CASEY), p["id"], PW)
    assert v["part"]["status"] == "released" and v["revisions"][0]["status"] == "released"
    assert v["signatures"][0]["email"] == CASEY
    rev_id = v["revisions"][0]["id"]
    with pytest.raises(psycopg.errors.RaiseException, match="released"):
        c.execute("update plm_part_revisions set params = '{}' where id = %s", (rev_id,))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        c.execute("delete from plm_part_revisions where id = %s", (rev_id,))
    with pytest.raises(PT.PlmError, match="no draft revision"):
        PT.update(c, u(c, CASEY), p["id"], {"params": {"mass": 0.06}})
    with pytest.raises(PT.PlmError, match="approved product change"):
        PT.new_revision(c, u(c, CASEY), p["id"], None)
    with pytest.raises(PT.PlmError, match="approved product change"):
        PT.new_revision(c, u(c, CASEY), p["id"], approved_change(c, kind="process"))
    with pytest.raises(PT.PlmError, match="does not list"):          # a product change that lists no parts
        PT.new_revision(c, u(c, CASEY), p["id"], approved_change(c))
    v = PT.new_revision(c, u(c, CASEY), p["id"], approved_change(c, parts=[(p["id"], "part")]))
    assert [r["revision"] for r in v["revisions"]] == ["A", "B"] and v["revisions"][1]["params"]["mass"] == 0.05
    with pytest.raises(PT.PlmError, match="released"):          # name and source fixed once released
        PT.update(c, u(c, CASEY), p["id"], {"name": "Other"})
    PT.update(c, u(c, CASEY), p["id"], {"params": {"mass": 0.06, "d": 7}})
    v = PT.release(c, u(c, CASEY), p["id"], PW)
    assert [r["status"] for r in v["revisions"]] == ["superseded", "released"]


def test_files_on_draft_revisions_only(world, erp):
    c = world
    p = part(c, erp, "Crank", "link", params={"L": 32})
    with pytest.raises(PT.PlmError, match="model file"):
        PT.add_file(c, u(c, CASEY), p["id"], "model", "crank.pdf", b"%PDF")
    v = PT.add_file(c, u(c, CASEY), p["id"], "model", "crank.step", b"ISO-10303-21;")
    f = v["revisions"][0]["files"][0]
    assert f["name"] == "crank.step" and len(f["sha256"]) == 64
    assert PT.file_of(c, p["id"], f["id"])[1] == b"ISO-10303-21;"
    PT.release(c, u(c, CASEY), p["id"], PW)
    with pytest.raises(PT.PlmError, match="draft revision"):
        PT.remove_file(c, u(c, CASEY), p["id"], f["id"])
    with pytest.raises(psycopg.errors.RaiseException, match="released"):
        c.execute("update plm_files set removed_at = now() where id = %s", (f["id"],))


# ---- BOMs

def released(c, erp, name, category, source="make", **params):
    p = part(c, erp, name, category, source, params=params)
    PT.release(c, u(c, CASEY), p["id"], PW)
    return p


def test_bom_checks_release_draft_in_erpnext_and_new_revision(world, fake, erp, monkeypatch):
    c = world
    head = part(c, erp, "Lockstitch head", "assembly")
    shaft = released(c, erp, "Main shaft", "shaft", d=14, length=420)
    hook = released(c, erp, "Rotary hook", "hook", "buy", model="HSM-M1", bobbin_d=21)
    link = part(c, erp, "Needle bar crank", "link", params={"L": 32})     # not released
    with pytest.raises(PT.PlmError, match="bought part has no BOM"):
        B.start(c, u(c, CASEY), hook["id"])
    b = B.start(c, u(c, CASEY), head["id"])
    assert b["bom"]["revision"] == "A" and b["checks"][0]["result"] == "fail"       # no lines yet
    with pytest.raises(PT.PlmError, match="own BOM"):
        B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": head["item_code"], "qty": 1}])
    with pytest.raises(PT.PlmError, match="quantity"):
        B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": shaft["item_code"], "qty": 0}])
    v = B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": shaft["item_code"], "qty": 1},
                                                     {"code": hook["item_code"], "qty": 1},
                                                     {"code": link["item_code"], "qty": 2}])
    res = {x["check"]: x["result"] for x in v["checks"]}
    assert res["every part on it released"] == "fail"
    assert res["bought parts have an approved supplier"] == "unknown"               # nothing in the supplier list
    assert res["the assembly is an item in ERPNext"] == "pass"
    PT.update(c, u(c, CASEY), link["id"], {"params": {"L": 32}})
    PT.release(c, u(c, CASEY), link["id"], PW)
    # an entry in the approved supplier list that is still a draft: no approved supplier yet
    c.execute("insert into asl_entries (supplier, item_code, created_by) values ('Hook Works (fictional)', %s, %s)",
              (hook["item_code"], JORDAN))
    v = B.view(c, b["bom"]["id"], erp)
    assert {x["check"]: x["result"] for x in v["checks"]}["bought parts have an approved supplier"] == "fail"
    monkeypatch.setattr(B, "_supplier", lambda _c, code: code == hook["item_code"])    # approved (signed in 17c)
    v = B.view(c, b["bom"]["id"], erp)
    assert v["ready"], v["checks"]
    v = B.release(c, u(c, CASEY), b["bom"]["id"], PW, erp)
    erp_bom = fake.docs["BOM"][v["bom"]["erp_bom"]]
    assert erp_bom["docstatus"] == 0 and erp_bom["item"] == head["item_code"]            # a draft: people submit it
    assert [(x["item_code"], x["qty"]) for x in erp_bom["items"]] == [("SFT-00001", 1.0), ("HOK-00001", 1.0),
                                                                        ("LNK-00001", 2.0)]
    assert v["erp_status"] == "draft"
    fake.put("BOM", v["bom"]["erp_bom"], docstatus=1)
    assert B.view(c, b["bom"]["id"], erp)["erp_status"] == "submitted"
    with pytest.raises(psycopg.errors.RaiseException, match="released"):
        c.execute("update plm_bom_lines set qty = 3 where bom_id = %s", (b["bom"]["id"],))
    with pytest.raises(PT.PlmError, match="approved product change"):
        B.start(c, u(c, CASEY), head["id"])
    b2 = B.start(c, u(c, CASEY), head["id"], approved_change(c, parts=[(head["id"], "bom")]))
    assert b2["bom"]["revision"] == "B" and len(b2["lines"]) == 3
    v = B.set_lines(c, u(c, CASEY), b2["bom"]["id"], [{"code": shaft["item_code"], "qty": 1},
                                                      {"code": hook["item_code"], "qty": 1},
                                                      {"code": link["item_code"], "qty": 1}])
    assert v["previous"]["revision"] == "A"
    assert v["previous"]["diff"] == [{"code": "LNK-00001", "name": "Needle bar crank", "change": "changed",
                                      "old": "2 Nos", "new": "1 Nos"}]
    assert B.compare(c, b["bom"]["id"], b2["bom"]["id"])["diff"] == v["previous"]["diff"]
    assert PT.where_used(c, shaft["id"])[0]["item_code"] == head["item_code"]


def test_a_part_cannot_contain_itself(world, erp):
    c = world
    a = released(c, erp, "Head", "assembly")
    s = released(c, erp, "Arm", "assembly")
    ba = B.start(c, u(c, CASEY), a["id"])
    B.set_lines(c, u(c, CASEY), ba["bom"]["id"], [{"code": s["item_code"], "qty": 1}])
    bs = B.start(c, u(c, CASEY), s["id"])
    v = B.set_lines(c, u(c, CASEY), bs["bom"]["id"], [{"code": a["item_code"], "qty": 1}])
    loop = next(x for x in v["checks"] if x["check"] == "no part contains itself")
    assert loop["result"] == "fail" and loop["detail"] == f"{s['item_code']} → {a['item_code']} → {s['item_code']}"


# ---- API

def test_api_module_switch_permissions_and_similar(db_url, fake):
    def app(plm):
        return TestClient(create_app({}, lambda: (manifest(plm), "ok"), db_url=db_url,
                                     erp=ErpClient("http://erp", transport=fake.transport())))
    off = app(False)
    with off:
        from wqops.hub import db as DB

        with DB.connect(db_url) as c:
            for e in (DANA, CASEY, LEE):
                Acc.set_password(c, e, PW)
        assert off.post("/api/login", json={"email": CASEY, "password": PW}).status_code == 200
        assert off.get("/api/plm/parts").status_code == 404
        assert "plm" not in off.get("/api/workspace").json()["modules"]
    c = app(True)
    with c:
        assert c.post("/api/login", json={"email": LEE, "password": PW}).status_code == 200
        assert c.get("/api/plm/parts").status_code == 403                  # warehouse does not see PLM
        assert c.post("/api/login", json={"email": CASEY, "password": PW}).status_code == 200
        cat = c.get("/api/plm/catalog").json()
        assert cat["can_release"] and any(x["key"] == "hook" for x in cat["categories"])
        r = c.post("/api/plm/parts", json={"name": "Hook", "category": "hook", "source": "buy",
                                           "params": {"model": "HSM", "bobbin_d": 21}})
        assert r.status_code == 201 and r.json()["code"] == "HOK-00001"
        r = c.post("/api/plm/parts", json={"name": "Hook 2", "category": "hook", "source": "buy",
                                           "params": {"model": "hsm", "bobbin_d": 21}})
        assert r.status_code == 409 and r.json()["similar"][0]["code"] == "HOK-00001"
        pid = c.get("/api/plm/parts?q=hook").json()["parts"][0]["id"]
        assert c.post(f"/api/plm/parts/{pid}/release", json={"password": PW}).json()["part"]["status"] == "released"
        up = c.post(f"/api/plm/parts/{pid}/files", data={"kind": "model"}, files={"file": ("h.step", b"x")})
        assert up.status_code == 409                                          # released: no new files
        assert c.get(f"/api/plm/parts/{pid}").json()["can_edit"]


# ---- what the independent review found (round 109)

def test_review_cycle_through_a_released_revision_quantities_and_units(world, fake, erp):
    c = world
    head = released(c, erp, "Head", "assembly")
    arm = released(c, erp, "Arm", "assembly")
    shaft = released(c, erp, "Shaft", "shaft", d=10, length=100)
    ba = B.start(c, u(c, CASEY), arm["id"])
    B.set_lines(c, u(c, CASEY), ba["bom"]["id"], [{"code": head["item_code"], "qty": "10"}])
    v = B.view(c, ba["bom"]["id"], erp)
    assert v["lines"][0]["qty"] == "10"                                  # not 1E+1
    B.release(c, u(c, CASEY), ba["bom"]["id"], PW, erp)
    # the draft drops Head; rev A still has it
    ba2 = B.start(c, u(c, CASEY), arm["id"], approved_change(c, parts=[(arm["id"], "bom")]))
    B.set_lines(c, u(c, CASEY), ba2["bom"]["id"], [{"code": shaft["item_code"], "qty": 2.5}])
    bh = B.start(c, u(c, CASEY), head["id"])
    v = B.set_lines(c, u(c, CASEY), bh["bom"]["id"], [{"code": arm["item_code"], "qty": 1}])
    assert next(x for x in v["checks"] if x["check"] == "no part contains itself")["result"] == "fail"
    with pytest.raises(PT.PlmError, match="counts in Nos"):
        B.set_lines(c, u(c, CASEY), bh["bom"]["id"], [{"code": arm["item_code"], "qty": 1, "uom": "kg"}])
    with pytest.raises(PT.PlmError, match="6 decimals"):
        B.set_lines(c, u(c, CASEY), bh["bom"]["id"], [{"code": arm["item_code"], "qty": "1e400"}])
    assert R.qty_text(Decimal("2.500")) == "2.5" and R.qty_text(Decimal("100")) == "100"


def test_review_one_erpnext_bom_and_locked_records(world, fake, erp):
    c = world
    head = released(c, erp, "Head", "assembly")
    shaft = released(c, erp, "Shaft", "shaft", d=10, length=100)
    b = B.start(c, u(c, CASEY), head["id"])
    B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": shaft["item_code"], "qty": 1}])
    bid = b["bom"]["id"]
    fake.fail_after = None
    # ERPNext made the BOM but the answer got lost: the retry links it instead of making a second one
    orig = B._erp_bom

    def lost(erp_, b_, part_, ls_):
        orig(erp_, b_, part_, ls_)
        raise TimeoutError("answer lost")
    B._erp_bom = lost
    try:
        v = B.release(c, u(c, CASEY), bid, PW, erp)
    finally:
        B._erp_bom = orig
    assert v["bom"]["erp_error"] and not v["bom"]["erp_bom"]
    v = B.to_erp(c, u(c, CASEY), bid, erp)
    assert len(fake.docs["BOM"]) == 1 and v["bom"]["erp_bom"] in fake.docs["BOM"]
    with pytest.raises(PT.PlmError, match="already in ERPNext"):
        B.to_erp(c, u(c, CASEY), bid, erp)
    with pytest.raises(psycopg.errors.RaiseException, match="keeps its ERPNext BOM"):
        c.execute("update plm_boms set erp_bom = 'BOM-X' where id = %s", (bid,))
    with pytest.raises(psycopg.errors.RaiseException, match="starts as a draft"):
        c.execute("insert into plm_boms (part_id, revision, status, created_by, released_by, released_at) values "
                  "(%s, 'Z', 'released', 'x', 'x', now())", (head["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        c.execute("update plm_parts set uom = 'kg' where id = %s", (shaft["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        c.execute("update plm_parts set status = 'draft' where id = %s", (shaft["id"],))


def test_review_part_rules_after_the_item_exists(world, fake, erp):
    c = world
    p = part(c, erp, "Bracket", "other")
    with pytest.raises(PT.PlmError, match="unit is fixed"):
        PT.update(c, u(c, CASEY), p["id"], {"uom": "kg"})
    PT.update(c, u(c, CASEY), p["id"], {"name": "Bracket, left"}, erp)
    assert fake.docs["Item"][p["item_code"]]["item_name"] == "Bracket, left"
    B.start(c, u(c, CASEY), p["id"])
    with pytest.raises(PT.PlmError, match="stays a made part"):
        PT.update(c, u(c, CASEY), p["id"], {"source": "buy"})
    # a revision started under a change is not released once that change is cancelled
    q = released(c, erp, "Pin", "other")
    ch = approved_change(c, parts=[(q["id"], "part")])
    PT.new_revision(c, u(c, CASEY), q["id"], ch)
    c.execute("update changes set status = 'cancelled', cancel_reason = 'not needed' where id = %s", (ch,))
    with pytest.raises(PT.PlmError, match="no longer approved"):
        PT.release(c, u(c, CASEY), q["id"], PW)


def test_review_an_edit_during_a_release_waits_and_is_refused(world, db_url, erp):
    """The lines trigger reads the BOM "for share": an edit running while the BOM is released waits for the release
    and then sees it released."""
    import threading

    from wqops.hub import db as DB

    c = world
    head = released(c, erp, "Head", "assembly")
    shaft = released(c, erp, "Shaft", "shaft", d=10, length=100)
    bid = B.start(c, u(c, CASEY), head["id"])["bom"]["id"]
    B.set_lines(c, u(c, CASEY), bid, [{"code": shaft["item_code"], "qty": 1}])
    rel = DB.connect(db_url)
    rel.autocommit = False
    rel.execute("update plm_boms set status = 'released', released_by = %s, released_at = now() where id = %s",
                (CASEY, bid))
    out = {}

    def edit():
        with DB.connect(db_url) as e:
            try:
                e.execute("insert into plm_bom_lines (bom_id, pos, part_id, qty, uom) values (%s, 9, %s, 1, 'Nos')",
                          (bid, head["id"]))
                out["r"] = "inserted"
            except psycopg.errors.RaiseException as exc:
                out["r"] = str(exc)
    t = threading.Thread(target=edit)
    t.start()
    t.join(1.0)
    assert t.is_alive()                     # waiting for the release
    rel.commit()
    rel.close()
    t.join(10)
    assert "released" in out["r"]
