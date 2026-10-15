"""Incoming inspection, step 17b (ADR-0017; dee-qms PLAN-IQC, PLAN-SEVERITY): the sampling table as company data
(checked against its source, frozen once used), plans frozen once enabled, an inspection from a receipt line judged
by code when the inspector signs, released or rejected by someone else, drafted for ERPNext, a rejected lot's
nonconformance report linked when the inspection reaches ERPNext, switching suggested by the rules and confirmed by a
person, and the API with its permissions. Fictional data; the sampling table numbers are made up for the tests."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import AS_OF, DEMO
from tests.test_quality_data import business
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import auto as AUTO
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q

PW = "Demo pass 2026"
JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
CHARS = [{"name": "Length", "kind": "measured", "lsl": 9.8, "usl": 10.2, "unit": "mm"},
         {"name": "Finish", "kind": "attribute"}]


def receipts(f):
    for i in range(7, 19):
        f.put("Purchase Receipt", f"PR-{i}", supplier="Gulf Fasteners", posting_date=f"2026-10-{i - 6:02d}",
              docstatus=1, items=[{"item_code": "BOLT-B", "qty": 100}])
    return f


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA):
        Acc.set_password(conn, e, PW)
    Y.run(conn, ErpClient("http://erp", transport=receipts(business()).transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, email):
    return Acc.get(conn, email)


def table(conn):
    I.add_row(conn, DANA, {"aql": 1.0, "lot_min": 2, "lot_max": 50, "n": 5, "ac": 0})
    I.add_row(conn, DANA, {"aql": 1.0, "lot_min": 51, "lot_max": 500, "n": 3, "ac": 0})
    I.add_row(conn, DANA, {"aql": 1.0, "level": "tightened", "lot_min": 51, "lot_max": 500, "n": 4, "ac": 0})
    return I.rows(conn)


def plan(conn):
    p = I.new_plan(conn, JORDAN, "BOLT-B", 1.0, CHARS)
    return I.enable_plan(conn, u(conn, DANA), p["id"], PW)


def inspect(conn, receipt, lengths, finish=True):
    """Start, enter and sign an inspection of a receipt line (Jordan), then release or reject it (Dana)."""
    ins = I.start(conn, JORDAN, "BOLT-B", receipt=receipt)
    vals = [{"sample": i, "characteristic": "Length", "value": v} for i, v in enumerate(lengths, start=1)]
    vals += [{"sample": i, "characteristic": "Finish", "passed": finish} for i in range(1, len(lengths) + 1)]
    I.enter(conn, JORDAN, ins["id"], vals)
    I.sign(conn, u(conn, JORDAN), ins["id"], PW)
    return I.decide(conn, u(conn, DANA), ins["id"], PW, "checked", today=AS_OF)


def test_sampling_table_is_company_data(world):
    rows = table(world)
    assert [(r["n"], r["ac"], r["re"], r["verified_by"]) for r in rows] == [(5, 0, 1, None), (3, 0, 1, None),
                                                                           (4, 0, 1, None)]
    with pytest.raises(I.IqcError, match="overlaps the row for lots 51-500"):
        I.add_row(world, DANA, {"aql": 1, "lot_min": 400, "lot_max": 900, "n": 8, "ac": 1})
    with pytest.raises(I.IqcError, match="Re is Ac"):
        I.add_row(world, DANA, {"aql": 1, "lot_min": 501, "lot_max": 900, "n": 0, "ac": 0})
    with pytest.raises(I.IqcError, match="name what the row was checked against"):
        I.verify_row(world, DANA, rows[1]["id"], " ")
    r = I.verify_row(world, DANA, rows[1]["id"], "Company copy of the sampling standard, rev 3")
    assert r["verified_by"] == DANA and r["verified_at"]
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("delete from iqc_sampling_rows where id = %s", (rows[0]["id"],))


def test_plans_frozen_once_enabled(world):
    table(world)
    p = I.new_plan(world, JORDAN, "BOLT-B", 1.0, CHARS)
    with pytest.raises(I.IqcError, match="already has a draft"):
        I.new_plan(world, JORDAN, "BOLT-B", 1.0, CHARS)
    with pytest.raises(I.IqcError, match="Finish: an attribute is pass or fail"):
        I.update_plan(world, JORDAN, p["id"], characteristics=[CHARS[0], {**CHARS[1], "usl": 1}])
    with pytest.raises(PermissionError, match="someone other than the person who drafted"):
        I.enable_plan(world, u(world, JORDAN), p["id"], PW)
    with pytest.raises(I.IqcError, match=r"no normal rows for AQL 2\.5"):
        I.update_plan(world, JORDAN, p["id"], aql=2.5)
        I.enable_plan(world, u(world, DANA), p["id"], PW)
    seen = I.update_plan(world, JORDAN, p["id"], aql=1.0)["updated_at"].isoformat()
    I.update_plan(world, JORDAN, p["id"], note="changed after Dana opened it")
    with pytest.raises(I.IqcError, match="changed since you opened it"):
        I.enable_plan(world, u(world, DANA), p["id"], PW, seen)
    on = I.enable_plan(world, u(world, DANA), p["id"], PW, I.plan(world, p["id"])["updated_at"].isoformat())
    assert on["status"] == "enabled" and on["fingerprint"] == I.fingerprint(on)
    with pytest.raises(I.IqcError, match="make a new version"):
        I.update_plan(world, JORDAN, p["id"], aql=2.5)
    with pytest.raises(psycopg.errors.RaiseException, match="cannot change"):
        world.execute("update iqc_plans set aql = 2.5 where id = %s", (p["id"],))
    v2 = I.new_version(world, JORDAN, p["id"])
    assert v2["version"] == 2 and v2["status"] == "draft"
    I.update_plan(world, JORDAN, v2["id"], characteristics=[{**CHARS[0], "usl": 10.3}, CHARS[1]])
    I.enable_plan(world, u(world, DANA), v2["id"], PW)
    assert [(x["version"], x["status"]) for x in I.plans(world, "BOLT-B")] == [(2, "enabled"), (1, "retired")]
    # the rule is the company's: switched off, the drafter may enable
    I.set_setting(world, DANA, "plan_by_other", False)
    v3 = I.new_version(world, JORDAN, v2["id"])
    assert I.enable_plan(world, u(world, JORDAN), v3["id"], PW)["status"] == "enabled"


def test_inspection_from_receipt_to_erpnext(world):
    table(world)
    with pytest.raises(I.IqcError, match="no inspection plan in use"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-7")
    plan(world)
    assert {x["receipt"] for x in I.awaiting(world) if x["plan"]} >= {"PR-7", "PR-8"}
    ins = I.start(world, JORDAN, "BOLT-B", receipt="PR-7", lot_no="L-1")
    assert (ins["supplier"], ins["lot_qty"], ins["level"], ins["n"], ins["ac"], ins["re"], ins["unverified"]) == \
        ("Gulf Fasteners", 100, "normal", 3, 0, 1, True)
    assert "PR-7" not in {x["receipt"] for x in I.awaiting(world)}
    # a lot on a receipt is the receipt's: no other supplier or lot size
    with pytest.raises(I.IqcError, match="is from Gulf Fasteners, not Acme Cable"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-8", supplier="Acme Cable")
    with pytest.raises(I.IqcError, match="has 100 of BOLT-B"):
        I.start(world, JORDAN, "BOLT-B", 10, receipt="PR-8")
    with pytest.raises(I.IqcError, match="already being inspected"):
        I.start(world, JORDAN, "BOLT-B", receipt="PR-7")
    assert len(I.readings(world, ins["id"])) == 6
    I.enter(world, JORDAN, ins["id"], [{"sample": 1, "characteristic": "Length", "value": "10.05"}])
    with pytest.raises(I.IqcError, match="5 readings not entered yet"):
        I.sign(world, u(world, JORDAN), ins["id"], PW)
    with pytest.raises(I.IqcError, match="pass or fail"):
        I.enter(world, JORDAN, ins["id"], [{"sample": 1, "characteristic": "Finish", "passed": "yes"}])
    I.enter(world, JORDAN, ins["id"], [{"sample": s, "characteristic": "Length", "value": 10.0} for s in (2, 3)]
            + [{"sample": s, "characteristic": "Finish", "passed": True} for s in (1, 2, 3)])
    with pytest.raises(Q.SignatureError):
        I.sign(world, u(world, JORDAN), ins["id"], "wrong")
    s = I.sign(world, u(world, JORDAN), ins["id"], PW)
    assert (s["status"], s["result"], s["defectives"]) == ("judged", "accept", 0)
    with pytest.raises(I.IqcError, match="readings cannot change"):
        I.enter(world, JORDAN, ins["id"], [{"sample": 1, "characteristic": "Length", "value": 11}])
    with pytest.raises(psycopg.errors.RaiseException, match="signed"):
        world.execute("update iqc_readings set value = 11 where inspection_id = %s", (ins["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="no readings can be added"):
        world.execute("insert into iqc_readings (inspection_id, sample, characteristic) values (%s, 9, 'Length')",
                      (ins["id"],))
    with pytest.raises(I.IqcError, match="cannot be voided: once signed"):
        I.void(world, JORDAN, ins["id"], "start again")
    with pytest.raises(psycopg.errors.CheckViolation):          # an accepted lot is not rejected by hand, nor back
        world.execute("update iqc_inspections set status = 'rejected', decided_by = 'x', decided_at = now() "
                      "where id = %s", (ins["id"],))
    with pytest.raises(PermissionError, match="other than the inspector"):
        I.decide(world, u(world, JORDAN), ins["id"], PW, today=AS_OF)
    # the sampling row was not checked: releasing needs a reason
    with pytest.raises(I.IqcError, match="give the reason to release"):
        I.decide(world, u(world, DANA), ins["id"], PW, today=AS_OF)
    done = I.decide(world, u(world, DANA), ins["id"], PW, "Table checked by Quality on paper", today=AS_OF)
    assert done["status"] == "released" and done["draft_id"]
    d = D.get(world, done["draft_id"])
    assert d["status"] == "pending" and d["payload"]["status"] == "Accepted" and d["payload"]["sample_size"] == 3
    assert d["payload"]["reference_name"] == "PR-7"
    assert [s["meaning"] for s in Q.signatures(world, "iqc", ins["id"])] == ["Incoming inspection signed",
                                                                             "Lot released"]
    with pytest.raises(I.IqcError, match="cannot be voided"):
        I.void(world, DANA, ins["id"], "mistake")
    v = I.view(world, ins["id"])
    assert v["entered"] == 6 and all(r["conforms"] for r in v["readings"]) and v["level_now"]["lots"] == ["accept"]


def test_rejected_lot_gets_one_report(world):
    table(world)
    plan(world)
    f = receipts(business())
    done = inspect(world, "PR-8", [10.0, 10.5, 10.0])
    assert done["status"] == "rejected" and done["result"] == "reject" and done["defectives"] == 1
    n = Q.ncr(world, done["ncr_id"])
    assert n["supplier"] == "Gulf Fasteners" and n["receipt"] == "PR-8" and "sample 2 Length" in n["description"]
    assert D.get(world, done["draft_id"])["payload"]["status"] == "Rejected"
    # Quality confirms the draft; it is submitted in ERPNext; the automatic report links instead of opening another
    erp = ErpClient("http://erp", transport=f.transport())
    qi = D.confirm(world, {"email": JORDAN, "roles": ["quality"]}, done["draft_id"], erp)["erp_name"]
    f.docs["Quality Inspection"][qi].update(docstatus=1)
    Y.run(world, erp)
    OP.project(world, manifest=DEMO)
    AUTO.open_for_rejected(world, dt.date(2026, 1, 1))           # older rejected inspections get theirs
    assert [r["id"] for r in world.execute("select id from ncr_records where inspection = %s", (qi,))] == \
        [done["ncr_id"]]


def test_switching_is_suggested_and_confirmed(world):
    table(world)
    plan(world)
    I.set_setting(world, DANA, "unverified_reason", False)
    for pr, ok in (("PR-9", True), ("PR-10", False), ("PR-11", True), ("PR-12", False)):
        inspect(world, pr, [10.0, 10.0, 10.0 if ok else 11.0])
    lv = {(x["supplier"], x["item_code"]): x for x in I.levels(world)}[("Gulf Fasteners", "BOLT-B")]
    assert lv["level"] == "normal" and lv["lots"] == ["accept", "reject", "accept", "reject"]
    assert lv["suggestion"]["to"] == "tightened"
    with pytest.raises(I.IqcError, match="give the reason"):
        I.switch(world, u(world, DANA), "Gulf Fasteners", "BOLT-B", "tightened", "")
    with pytest.raises(I.IqcError, match="no reduced rows"):
        I.switch(world, u(world, DANA), "Gulf Fasteners", "BOLT-B", "reduced", "try")
    sw = I.switch(world, u(world, DANA), "Gulf Fasteners", "BOLT-B", "tightened", "Two rejects in four lots")
    assert sw["suggestion"].startswith("tightened: Normal to tightened") and sw["history"] == "A R A R"
    # the next lot is sampled at the tightened level, from its own row
    ins = I.start(world, JORDAN, "BOLT-B", receipt="PR-13")
    assert (ins["level"], ins["n"]) == ("tightened", 4)
    assert I.levels(world)[0]["lots"] == [] and I.levels(world)[0]["suggestion"] is None
    with pytest.raises(I.IqcError, match="straight to tightened"):
        world.execute("insert into iqc_level_switches (supplier, item_code, from_level, to_level, reason, email) "
                      "values ('Gulf Fasteners', 'BOLT-B', 'tightened', 'reduced', 'x', %s)", (DANA,))
        I.switch(world, u(world, DANA), "Gulf Fasteners", "BOLT-B", "tightened", "x")
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("delete from iqc_level_switches")


def test_void_and_rules(world):
    table(world)
    plan(world)
    with pytest.raises(I.IqcError, match="choose the supplier"):
        I.start(world, JORDAN, "BOLT-B", 40, supplier="Gulf Fastners", lot_no="L-9")
    ins = I.start(world, JORDAN, "BOLT-B", 40, supplier="Gulf Fasteners", lot_no="L-9")
    assert (ins["receipt"], ins["n"], ins["lot_qty"]) == (None, 5, 40)
    with pytest.raises(I.IqcError, match="give the reason"):
        I.void(world, JORDAN, ins["id"], "")
    assert I.void(world, JORDAN, ins["id"], "wrong lot size")["status"] == "void"
    again = I.start(world, JORDAN, "BOLT-B", 3, supplier="Gulf Fasteners", lot_no="L-9")
    assert again["n"] == 3 and "lot L-9" not in I.history(world, "inspection", again["id"])[0]["note"]
    rules = I.save_rule(world, DANA, None, {"from_level": "tightened", "to_level": "normal",
                                             "condition": "consecutive_accepted", "n": 3})
    assert len(rules) == 5
    with pytest.raises(I.IqcError, match="K is a whole number"):
        I.save_rule(world, DANA, rules[0]["id"], {**rules[0], "k": 9})
    off = I.save_rule(world, DANA, rules[0]["id"], {**rules[0], "active": False})
    assert off[0]["active"] is False
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("delete from iqc_switch_rules")


def test_iqc_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.get("/api/iqc").json()["can_edit"] is False
    assert c.post("/api/iqc/inspections", json={}).status_code == 403
    login(JORDAN)
    assert c.post("/api/iqc/rows", json={"aql": 1, "lot_min": 2, "lot_max": 500, "n": 3, "ac": 0}).status_code == 201
    p = c.post("/api/iqc/plans", json={"item_code": "BOLT-B", "aql": 1, "characteristics": CHARS}).json()
    assert c.post(f"/api/iqc/plans/{p['id']}/enable", json={"password": PW}).status_code == 403
    login(DANA)
    assert c.post(f"/api/iqc/plans/{p['id']}/enable", json={"password": PW}).json()["status"] == "enabled"
    login(JORDAN)
    ins = c.post("/api/iqc/inspections", json={"item_code": "BOLT-B", "receipt": "PR-14"}).json()
    vals = [{"sample": s, "characteristic": "Length", "value": 10} for s in (1, 2, 3)]
    vals += [{"sample": s, "characteristic": "Finish", "passed": True} for s in (1, 2, 3)]
    assert c.put(f"/api/iqc/inspections/{ins['id']}/readings", json={"readings": vals}).json()["entered"] == 6
    assert c.post(f"/api/iqc/inspections/{ins['id']}/sign", json={"password": PW}).json()["result"] == "accept"
    assert c.post(f"/api/iqc/inspections/{ins['id']}/decide", json={"password": PW}).status_code == 403
    login(DANA)
    r = c.post(f"/api/iqc/inspections/{ins['id']}/decide", json={"password": PW, "note": "ok"}).json()
    assert r["status"] == "released" and r["draft"]["status"] == "pending"
    assert c.get("/api/iqc/inspections/99999").status_code == 404
    assert c.post("/api/iqc/rows/1/explode").status_code == 404
    home = c.get("/api/iqc?status=all").json()
    assert home["inspections"][0]["name"] == ins["name"] and home["levels"][0]["lots"] == ["accept"]
    c.__exit__(None, None, None)
