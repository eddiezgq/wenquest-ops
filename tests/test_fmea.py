"""Process FMEA, step 22c (ADR-0022): the company's own S / O / D scales and action rule; RPN computed by code; a
PFMEA approved with a signature by someone uninvolved and then fixed with its criteria and fingerprint; new versions
supersede old ones; reports on the item since approval are listed for a person to judge; CAPAs opened from rows; the
AI drafts rows citing records it was shown and never gives a rank. Scripted model; fictional data only."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted
from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, receipts, u
from tests.test_quality_data import business
from tests.test_quality_tools import lots
from tests.test_recall import world  # noqa: F401 - the fixture
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.quality import fmea as F
from wqops.hub.quality import fmea_ai as FAI
from wqops.hub.quality import fmea_rules as FR
from wqops.hub.quality import records as Q

RPN = {"method": "rpn", "rpn_action": 100, "severity_action": 9}


def scales(w):
    for kind in FR.KINDS:
        for rank in range(1, 11):
            F.add_scale(w, DANA, {"kind": kind, "rank": rank, "name": f"{kind[0].upper()}{rank} (demo wording)"})


def test_rules():
    assert FR.rpn(5, 4, 3) == 60 and FR.rpn(5, None, 3) is None
    cfg = FR.check_rule(RPN)
    assert FR.judge(cfg, 5, 4, 5) == {"rpn": 100, "priority": "action", "action": True}
    assert FR.judge(cfg, 9, 1, 1)["action"] is True and FR.judge(cfg, 8, 2, 2)["action"] is False
    assert FR.judge(None, 5, 5, 5)["action"] is None and FR.judge(cfg, 5, None, 5)["action"] is None
    for bad, msg in (({"method": "x"}, "RPN threshold"), ({"method": "rpn", "rpn_action": 0}, "1 to 1000"),
                     ({"method": "rpn", "rpn_action": 50, "severity_action": 11}, "severity threshold"),
                     ({"method": "lookup", "rules": []}, "at least one row"),
                     ({"method": "lookup", "rules": [{"s": [3, 1], "o": [1, 10], "d": [1, 10], "priority": "high"}]},
                      "low to high"),
                     ({"method": "lookup", "rules": [{"s": [1, 10], "o": [1, 10], "d": [1, 10], "priority": "x"}]},
                      "high, medium or low")):
        with pytest.raises(FR.FmeaRuleError, match=msg):
            FR.check_rule(bad)
    lk = FR.check_rule({"method": "lookup", "needs_action": ["high", "medium"], "rules": [
        {"s": [9, 10], "o": [1, 10], "d": [1, 10], "priority": "high"},
        {"s": [1, 8], "o": [6, 10], "d": [1, 10], "priority": "medium"},
        {"s": [1, 8], "o": [1, 5], "d": [1, 5], "priority": "low"}]})
    assert FR.judge(lk, 9, 1, 1)["priority"] == "high" and FR.judge(lk, 4, 7, 2)["action"] is True
    assert FR.judge(lk, 4, 2, 2) == {"rpn": 16, "priority": "low", "action": False}
    assert FR.judge(lk, 4, 2, 8)["action"] is None and FR.lookup_gaps(lk) == 8 * 5 * 5   # unmatched: not decided
    rk = {k: set(range(1, 11)) for k in FR.KINDS}
    row = {"seq": 1, "step": "Roll thread", "failure_mode": "Pitch diameter high", "effect": "Bolt strips",
           "cause": "Die worn", "severity": 8, "occurrence": 5, "detection": 3, "confirmed": True}
    assert FR.row_needs(row, rk, cfg) == ["row 1: needs action under the company's rule: say what is recommended"]
    assert FR.row_needs(row | {"action": "Die life limit"}, rk, cfg) == []
    assert "drafted by the AI" in FR.row_needs(row | {"confirmed": False, "action": "x"}, rk, cfg)[0]
    assert "not on the company's scale" in FR.row_needs(row | {"action": "x"}, rk | {"severity": {1, 2}}, cfg)[0]
    assert "given together" in FR.row_needs(row | {"action": "x", "res_severity": 8}, rk, cfg)[0]
    assert "does not decide" in FR.row_needs(row | {"detection": 8}, rk, lk)[0]
    assert FR.to_approve({}, [], {}, None)[0].startswith("the company's rule")
    kept, dropped = FR.verify([{"failure_mode": "a", "refs": ["N-1", "X"]}, {"failure_mode": "b", "refs": []}], {"N-1"})
    assert kept[0]["refs"] == ["N-1"] and dropped[0]["reason"] == "cites no record"


def test_criteria_approval_and_versions(world):  # noqa: F811
    w = world
    lots(w)                                             # BOLT-B: two rejected lots and their reports
    f = F.create(w, JORDAN, {"process": "Thread rolling, M8 bolts", "item_code": "BOLT-B", "owner": JORDAN})
    assert f["name"] == "PFMEA-00001" and f["status"] == "draft"
    r1 = F.add_row(w, JORDAN, f["id"], {"step": "Roll thread", "failure_mode": "Pitch diameter over limit",
                                         "effect": "Bolt strips at assembly", "cause": "Rolling die worn"})
    with pytest.raises(F.FmeaError, match="rank on the company's severity scale"):
        F.update_row(w, JORDAN, f["id"], r1["id"], {"severity": 8})
    v = F.view(w, f["id"])
    assert "the company's rule for when a row needs action (Process FMEA, criteria)" in v["to_approve"]
    assert "the company's severity scale" in v["to_approve"]
    scales(w)
    with pytest.raises(F.FmeaError, match="already on the scale"):
        F.add_scale(w, DANA, {"kind": "severity", "rank": 1, "name": "x"})
    with pytest.raises(F.FmeaError, match="RPN threshold"):
        F.set_rule(w, DANA, {"method": "nope"})
    F.set_rule(w, DANA, RPN)
    F.update_row(w, JORDAN, f["id"], r1["id"], {"severity": 8, "occurrence": 5, "detection": 3,
                                                  "refs": ["NCR-00001"]})
    with pytest.raises(F.FmeaError, match="no record with the number: NCR-09999"):
        F.update_row(w, JORDAN, f["id"], r1["id"], {"refs": ["NCR-09999"]})
    with pytest.raises(F.FmeaError, match="all three ranks after action"):
        F.update_row(w, JORDAN, f["id"], r1["id"], {"res_severity": 8})
    v = F.view(w, f["id"])
    assert v["rows"][0]["rpn"] == 120 and v["rows"][0]["action_needed"] is True
    assert v["to_approve"] == ["row 1: needs action under the company's rule: say what is recommended"]
    F.update_row(w, JORDAN, f["id"], r1["id"], {"action": "Die life limit and first-piece check",
                                                  "res_severity": 8, "res_occurrence": 2, "res_detection": 3})
    F.add_row(w, JORDAN, f["id"], {"step": "Pack", "failure_mode": "Mixed lots", "effect": "Wrong traceability",
                                    "cause": "No lot label", "severity": 4, "occurrence": 2, "detection": 4})
    # someone uninvolved approves, signed
    with pytest.raises(PermissionError, match="does not own and did not edit"):
        F.approve(w, u(w, JORDAN), f["id"], PW)
    with pytest.raises(Q.SignatureError):
        F.approve(w, u(w, DANA), f["id"], "wrong")
    a = F.approve(w, u(w, DANA), f["id"], PW)
    assert a["status"] == "approved" and a["criteria"]["rule"]["rpn_action"] == 100
    rows = F.rows(w, f["id"])
    assert [(r["rpn"], r["res_rpn"], r["priority"]) for r in rows] == [(120, 48, "action"), (32, None, "no action")]
    assert F.intact(w, F.get(w, f["id"])) is True
    with pytest.raises(psycopg.errors.RaiseException, match="rows are fixed"):
        w.execute("update fmea_rows set occurrence = 1 where file_id = %s", (f["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="it is fixed"):
        w.execute("update fmea_files set process = 'x' where id = %s", (f["id"],))
    with pytest.raises(F.FmeaError, match="start a new version"):
        F.add_row(w, JORDAN, f["id"], {"step": "x"})
    with pytest.raises(F.FmeaError, match="an approved PFMEA uses this rank"):
        F.update_scale(w, DANA, w.execute("select id from fmea_scales where kind = 'severity' and rank = 8")
                       .fetchone()["id"], {"name": "Changed"})
    # a report on the item after approval is listed for a person to judge
    assert F.view(w, f["id"])["ncrs_since"] == []
    n = Q.create_ncr(w, JORDAN, title="Long bolts again", description="Lot 3", item_code="BOLT-B")
    assert [x["name"] for x in F.view(w, f["id"])["ncrs_since"]] == [n["name"]]
    assert F.listing(w, "current")[0]["ncrs_since"] == 1
    # a CAPA from a row, also after approval
    c = F.open_capa(w, JORDAN, f["id"], 1)
    assert c["kind"] == "preventive" and c["title"].startswith("PFMEA-00001 row 1: Pitch diameter")
    assert F.view(w, f["id"])["capas"][0]["name"] == c["name"]
    # a new version supersedes the old one once approved
    v2 = F.revise(w, JORDAN, f["id"])
    assert v2["version"] == 2 and [r["rpn"] for r in F.rows(w, v2["id"])] == [None, None]
    with pytest.raises(F.FmeaError, match="already being drafted"):
        F.revise(w, JORDAN, f["id"])
    r = F.rows(w, v2["id"])[0]
    F.update_row(w, JORDAN, v2["id"], r["id"], {"occurrence": 6})
    F.approve(w, u(w, DANA), v2["id"], PW)
    assert F.get(w, f["id"])["status"] == "superseded" and F.rows(w, v2["id"])[0]["rpn"] == 144
    assert Q.signatures(w, "fmea", v2["id"])[0]["meaning"] == "Process FMEA approved"
    v3 = F.revise(w, JORDAN, v2["id"])
    F.withdraw(w, JORDAN, v3["id"], "not needed after all")
    assert F.get(w, v3["id"])["status"] == "withdrawn"
    hist = [h["action"] for h in F.criteria_history(w)]
    assert "rule changed" in hist and hist.count("scale rank added") == 30


def reply(rows, note=""):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 1500, "output_tokens": 400},
            "content": [{"type": "tool_use", "id": "t1", "name": "draft_rows", "input": {"rows": rows, "note": note}}]}


def test_ai_drafts_rows_without_ranks(world):  # noqa: F811
    w = world
    got = lots(w)
    scales(w)
    F.set_rule(w, DANA, RPN)
    f = F.create(w, JORDAN, {"process": "Receiving and thread rolling", "item_code": "BOLT-B"})
    with pytest.raises(FAI.NoModel):
        FAI.suggest(w, u(w, JORDAN), f["id"], L.Anthropic("", env={}), today=AS_OF)
    s = Scripted(reply([
        {"step": "Receive lot", "failure_mode": "Long bolts accepted", "effect": "Bolts do not fit",
         "cause": "Length not checked on every lot", "refs": [got[1]["name"]], "severity": 9, "occurrence": 4},
        {"step": "Roll thread", "failure_mode": "Thread too large", "effect": "Strips", "cause": "Worn die",
         "refs": ["CAL-777"]},                                                    # not shown: dropped
        {"step": "Pack", "failure_mode": "Mixed lots", "effect": "", "cause": "x", "refs": [got[1]["name"]]}],
        note="No process records were shown."))
    out = FAI.suggest(w, u(w, JORDAN), f["id"], s.model(), today=AS_OF)
    body = s.requests[0]["body"]
    assert body["tool_choice"]["name"] == "draft_rows" and "Do not rate severity" in body["system"]
    assert "severity" not in str(body["tools"][0]["input_schema"])
    assert f"[{got[1]['name']}] incoming inspection" in body["messages"][0]["content"]
    assert len(out["rows"]) == 1 and out["unusable"] == 1 and out["dropped"][0]["refs"] == ["CAL-777"]
    row = out["rows"][0]
    assert row["severity"] is None and row["occurrence"] is None and row["confirmed"] is False
    assert row["origin"] == "ai" and row["refs"] == [got[1]["name"]]
    run = w.execute("select * from ai_runs where id = %s", (out["run"],)).fetchone()
    assert run["kind"] == "fmea" and run["verified"] is False
    with pytest.raises(F.FmeaError, match="confirm or remove the rows the AI drafted"):
        FAI.suggest(w, u(w, JORDAN), f["id"], s.model(), today=AS_OF)
    assert "row 1: drafted by the AI; confirm or remove it" in F.view(w, f["id"])["to_approve"]
    F.update_row(w, JORDAN, f["id"], row["id"], {"severity": 7, "occurrence": 4, "detection": 3}, confirm=True)
    r = F.rows(w, f["id"])[0]
    assert r["confirmed"] is True and r["origin"] == "ai" and r["severity"] == 7
    assert "row confirmed" in [h["action"] for h in F.view(w, f["id"])["history"]]
    # without an item there is nothing for the AI to read
    g = F.create(w, JORDAN, {"process": "Kitting"})
    with pytest.raises(F.FmeaError, match="no records about this PFMEA's item"):
        FAI.suggest(w, u(w, JORDAN), g["id"], Scripted().model(), today=AS_OF)


def test_fmea_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.get("/api/fmea").status_code == 200
    assert c.post("/api/fmea/files", json={"process": "x"}).status_code == 403
    login(JORDAN)
    for kind in FR.KINDS:
        for rank in (1, 5, 10):
            assert c.post("/api/fmea/scales", json={"kind": kind, "rank": rank, "name": f"r{rank}"}).status_code == 201
    assert c.put("/api/fmea/rule", json=RPN).json()["rule"]["rpn_action"] == 100
    fid = c.post("/api/fmea/files", json={"process": "Packing", "item_code": "BOLT-B"}).json()["id"]
    p = c.post(f"/api/fmea/files/{fid}/rows", json={"step": "Pack", "failure_mode": "Mixed lots", "effect": "Recall",
                                                     "cause": "No label", "severity": 5, "occurrence": 5,
                                                     "detection": 5})
    assert p.status_code == 201 and p.json()["rows"][0]["rpn"] == 125 and p.json()["can_ask"] is False
    rid = p.json()["rows"][0]["id"]
    assert c.put(f"/api/fmea/files/{fid}/rows/{rid}", json={"severity": 7}).status_code == 409   # not on the scale
    assert c.put(f"/api/fmea/files/{fid}/rows/{rid}", json={"action": "Label every lot"}).json()["to_approve"] == []
    assert c.post(f"/api/fmea/files/{fid}/suggest").status_code == 409                        # no model key
    assert c.post(f"/api/fmea/files/{fid}/approve", json={"password": PW}).status_code == 403   # an editor
    login(DANA)
    assert c.post(f"/api/fmea/files/{fid}/approve", json={"password": PW}).json()["status"] == "approved"
    assert c.get(f"/api/fmea/files/{fid}/context").json()["records"] == []
    assert c.post(f"/api/fmea/files/{fid}/rows/1/capa", json={}).status_code == 201
    assert c.post(f"/api/fmea/files/{fid}/nope").status_code == 404
    assert c.post(f"/api/fmea/files/{fid}/revise").json()["version"] == 2
