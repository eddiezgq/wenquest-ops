"""Workflow changes proposed from the company's procedures, step 15c (ADR-0015): the shape of a change, the quote and
red-line checks, a scripted model's proposal kept with what code found, accepting into a draft that someone else
enables, rejecting, decisions kept, the API and permissions. The procedures are the generated demo files
(wqops/demo/documents.py); the model is scripted."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_ai import Scripted
from tests.test_documents import AS_OF, DEMO, imported
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import ai_classify as AIC
from wqops.hub.docs import library as LIB
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_admin as WA
from wqops.hub.quality import workflow_ai as WAI
from wqops.hub.quality import workflow_proposals as WP

PW = "Demo pass 2026"
JORDAN, SAM, DANA = "jordan@demo.example", "sam@demo.example", "dana@demo.example"
LOT = "The lot number of the affected product is recorded on the NCR before the disposition."
GM = "The General Manager signs off every major NCR before it is closed."
UAI = "Use-as-is needs approval by a second person."


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM, DANA):
        Acc.set_password(conn, e, PW)
    return conn


def library(conn):
    """QP-08 Rev C, QP-09 and management review minutes, classified by the rules and confirmed."""
    imp, docs = imported(conn, ["QP-08 Control of Nonconforming Product Rev C", "QP-09", "Management review minutes"])
    AIC.run(conn, {"email": JORDAN, "roles": ["quality"]}, imp["id"], None, today=AS_OF)
    for d in docs:
        LIB.confirm(conn, JORDAN, d["id"])
    return [LIB.get(conn, d["id"]) for d in docs]


def change(op, quote, doc, why="the procedure says so", **kw):
    return {"change": {"op": op, **kw}, "document_id": doc, "quote": quote, "why": why}


def reply(changes, cannot=(), summary="Mostly followed already."):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 3000, "output_tokens": 400}, "content": [{
        "type": "tool_use", "id": "t1", "name": "propose_workflow_changes",
        "input": {"changes": list(changes), "cannot": list(cannot), "summary": summary}}]}


# ---------------------------------------------------------------- one change (no database)

def test_changes_are_cleaned_applied_and_checked():
    cfg = W.default("ncr")
    body = f"3.4 {UAI}\n3.5 {LOT}\n3.6 {GM}\nNCR numbers start with NC-2026."
    lot = WP.clean("ncr", {"op": "field", "name": "lot_no", "label": "Lot number", "type": "text",
                           "required_at": ["disposition"], "extra": "ignored"})
    assert lot == {"op": "field", "name": "lot_no", "label": "Lot number", "type": "text",
                   "required_at": ["disposition"]}
    found = WP.check(cfg, lot, LOT, body)
    assert found == {"verified": True, "problems": [], "already": False,
                     "lines": ["new field lot_no (Lot number, text)"]}
    assert WP.apply(cfg, lot)["fields"]["lot_no"]["required_at"] == ["disposition"] and "fields" not in cfg
    # the quote must be in the procedure it names, long enough, and the procedure must be one that was read
    assert WP.check(cfg, lot, "The lot number is written on the tag.", body)["problems"] == [
        "its quote is not in the procedure it names"]
    assert WP.check(cfg, lot, "lot number", body)["problems"] == ["its quote is too short to rest on"]
    assert WP.check(cfg, lot, LOT, None)["problems"] == ["it does not name one of the procedures that were read"]
    # quotes are compared as the library compares them: case, spaces and dashes do not matter
    assert WP.check(cfg, lot, LOT.upper().replace(" ", "  "), body)["verified"] is True
    # what the workflow already does is shown as such and cannot be accepted
    sep = WP.clean("ncr", {"op": "not_by", "step": "approve", "person": "disposition_by"})
    assert WP.check(cfg, sep, UAI, body) == {"verified": True, "problems": [], "already": True, "lines": []}
    # a change that breaks a red line is refused by the same check as a hand-made one
    bad = WP.clean("ncr", {"op": "approval", "name": "gm_ok", "label": "GM sign-off", "before": "close",
                           "roles": ["sales"], "when": {"severity": ["major"]}})
    assert "only roles that can see quality records can approve" in WP.check(cfg, bad, GM, body)["problems"][0]
    gm = WP.clean("ncr", dict(bad, roles=["owner"]))
    assert gm["sign"] == "GM sign-off" and WP.check(cfg, gm, GM, body)["problems"] == []
    assert WP.describe(gm, cfg) == "GM sign-off: signed by owner before close when severity is major"
    num = WP.clean("ncr", {"op": "numbering", "prefix": "NCR", "digits": "4"})
    assert WP.check(cfg, num, "NCR numbers start with NC-2026.", body)["problems"] == []
    assert WP.check(cfg, dict(num, prefix="QN"), "NCR numbers start with NC-2026.", body)["problems"] == [
        "the quote does not show the prefix QN"]
    for raw, msg in [({"op": "delete_step", "step": "close"}, "a change is one of"),
                     ({"op": "require", "step": "skip", "field": "owner"}, "there is no step"),
                     ({"op": "rule", "rule": "capa_closed_before_close", "severity": "major"}, None),
                     ({"op": "numbering", "prefix": "N", "digits": "four"}, "whole number")]:
        if msg is None:
            with pytest.raises(WP.ChangeError, match="rules that can be proposed"):
                WP.clean("capa", raw)
            continue
        with pytest.raises(WP.ChangeError, match=msg):
            WP.clean("ncr", raw)
    # the existing rule cannot be loosened through a proposal either: rules only add severities
    rule = WP.clean("ncr", {"op": "rule", "rule": "eight_d_before_close", "severity": "major"})
    assert WP.apply(cfg, rule)["rules"]["eight_d_before_close"] == ["major"]
    assert "rule eight_d_before_close" in WP.check(cfg, rule, GM, body)["lines"][0]
    # a field or approval of the same name that is different is not replaced by a proposal
    own = WP.apply(cfg, lot)
    assert "already has a field 'lot_no'" in WP.check(own, dict(lot, type="number"), LOT, body)["problems"][0]


# ---------------------------------------------------------------- the model's proposal, stored and decided

def test_proposal_is_checked_kept_and_decided(world):
    qp08, qp09, log = library(world)
    procs = WP.procedures(world, "ncr")
    assert [p["id"] for p in procs][:1] == [qp08["id"]] and log["id"] not in {p["id"] for p in procs}
    with pytest.raises(WA.AdminError, match="not a procedure"):
        WP.read(world, "ncr", [log["id"]])
    docs = WP.read(world, "ncr", [qp08["id"], qp09["id"]])
    assert docs[0]["name"] == "QP-08 Control of Nonconforming Product" and LOT in " ".join(docs[0]["text"].split())

    s = Scripted(reply([
        change("field", LOT, qp08["id"], name="lot_no", label="Lot number", type="text", required_at=["disposition"]),
        change("approval", GM, qp08["id"], name="gm_signoff", label="General Manager sign-off", before="close",
               roles=["owner"], when={"severity": ["major"]}, sign="Major NCR signed off by the General Manager"),
        change("not_by", UAI, qp08["id"], step="approve", person="disposition_by"),
        change("require", "Every NCR records the customer order number.", qp08["id"], step="contain",
               field="item_code"),
        change("roles", UAI, 999, step="approve", roles=["quality"]),
        change("delete_step", UAI, qp08["id"], step="close"),
    ], cannot=[{"document_id": qp08["id"], "quote": "Nonconforming product is tagged and moved to QC Hold.",
                "why": "tagging is done in the warehouse, not in the record"}]))
    p = WAI.propose(world, {"email": JORDAN, "roles": ["quality"]}, "ncr", docs, s.model(), today=AS_OF,
                    company="Harbor Lane Supply (Demo)")
    req = s.requests[0]["body"]
    assert req["tool_choice"]["name"] == "propose_workflow_changes" and "Harbor Lane Supply (Demo)" in req["system"]
    content = req["messages"][0]["content"]
    assert "- approve \"Approve disposition\"" in content and "Document " + str(qp08["id"]) in content
    assert "use_as_is: Use as is (concession), yes" in content
    v = WP.view(world, p)
    got = {i["seq"]: i for i in v["items"]}
    assert [got[n]["acceptable"] for n in range(1, 7)] == [True, True, False, False, False, False]
    assert got[1]["text"] == "New field Lot number (text), needed before submit disposition"
    assert got[3]["already"] is True and got[4]["problems"] == ["its quote is not in the procedure it names"]
    assert got[5]["document_id"] is None and "does not name one of the procedures" in got[5]["problems"][0]
    assert "a change is one of" in got[6]["problems"][0] and got[6]["text"] == "a change WenQuest Ops cannot make"
    assert v["cannot"][0]["verified"] is True and v["documents"][0]["name"].startswith("QP-08")
    run = world.execute("select * from ai_runs where id = %s", (p["ai_run"],)).fetchone()
    assert run["kind"] == "workflow" and run["verified"] is False and len(run["unverified"]) == 3
    assert run["usage"]["input_tokens"] == 3000

    # accepting puts the change into a new draft; the person who accepted changed the draft
    with pytest.raises(WA.AdminError, match="only a change whose quote was found"):
        WP.accept(world, got[4]["id"], JORDAN)
    a1 = WP.accept(world, got[1]["id"], JORDAN, "matches QP-08 3.5")
    draft = WA.get(world, a1["draft_version"])
    assert draft["status"] == "draft" and draft["config"]["fields"]["lot_no"]["required_at"] == ["disposition"]
    assert JORDAN in draft["edited_by"]
    a2 = WP.accept(world, got[2]["id"], JORDAN)
    assert a2["draft_version"] == draft["id"]
    with pytest.raises(WA.AdminError, match="already accepted by jordan"):
        WP.accept(world, got[2]["id"], DANA)
    WP.reject(world, got[3]["id"], JORDAN, "already so")
    hist = WA.view(world, WA.get(world, draft["id"]))["history"]
    assert [h["action"] for h in hist] == ["draft made", "changed", "proposal accepted", "changed",
                                           "proposal accepted"]
    assert GM in hist[-1]["note"] and "QP-08" in hist[-1]["note"]
    # someone who did not change the draft enables it with a signature; records then need what QP-08 asks for
    with pytest.raises(PermissionError):
        WA.enable(world, draft["id"], Acc.get(world, JORDAN), PW)
    WA.enable(world, draft["id"], Acc.get(world, DANA), PW)
    cfg = W.ensure(world, "ncr")["config"]
    assert cfg["approvals"][0]["name"] == "gm_signoff" and "lot_no" in cfg["fields"]
    assert WP.view(world, p)["enabled"] == 2 and WP.view(world, p)["base"] == 1

    # decisions and what was proposed are kept as they are
    with pytest.raises(psycopg.errors.RaiseException, match="decided once"):
        world.execute("update workflow_proposal_items set decision = 'open' where id = %s", (got[1]["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="decided once"):
        world.execute("update workflow_proposal_items set quote = 'changed' where id = %s", (got[5]["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        world.execute("delete from workflow_proposal_items where id = %s", (got[5]["id"],))
    with pytest.raises(psycopg.errors.RaiseException):
        world.execute("update workflow_proposals set summary = 'x' where id = %s", (p["id"],))
    assert WP.listing(world, "ncr")[0]["accepted"] == 2


def test_accepting_checks_again_against_the_draft_as_it_is(world):
    qp08, _, _ = library(world)
    docs = WP.read(world, "ncr", [qp08["id"]])
    s = Scripted(reply([
        change("field", LOT, qp08["id"], name="lot_no", label="Lot number", type="text", required_at=["disposition"]),
        change("field", LOT, qp08["id"], name="lot", label="Lot", type="text"),
        change("approval", GM, qp08["id"], name="gm_signoff", label="GM sign-off", before="close", roles=["owner"])]))
    p = WAI.propose(world, Acc.get(world, JORDAN), "ncr", docs, s.model(), today=AS_OF)
    it = {i["seq"]: i for i in WP.items(world, p["id"])}
    # meanwhile someone drafted a different field of the same name by hand
    d = WA.new_draft(world, "ncr", SAM)
    cfg = dict(d["config"], fields={"lot_no": {"label": "Lot", "type": "number"}})
    WA.save(world, d["id"], SAM, cfg)
    with pytest.raises(WA.AdminError, match="in the draft as it is now: the workflow already has a field 'lot_no'"):
        WP.accept(world, it[1]["id"], JORDAN)
    assert WP.items(world, p["id"])[0]["decision"] == "open"           # nothing was decided
    # a change the draft already has is accepted without changing the draft
    WA.save(world, d["id"], SAM, WP.apply(cfg, WP.clean("ncr", it[3]["change"])))
    before = WA.get(world, d["id"])["config"]
    WP.accept(world, it[3]["id"], JORDAN)
    assert WA.get(world, d["id"])["config"] == before
    assert "already in the draft" in WA.view(world, WA.get(world, d["id"]))["history"][-1]["note"]
    # a discarded draft does not take changes: accepting makes a new one from the enabled version
    WA.discard(world, d["id"], SAM, "start again")
    out = WP.accept(world, it[2]["id"], JORDAN)
    assert out["draft_version"] != d["id"] and WA.get(world, out["draft_version"])["edited_by"] == [JORDAN]


def test_without_a_model_or_when_it_fails(world):
    qp08, _, _ = library(world)
    docs = WP.read(world, "ncr", [qp08["id"]])
    with pytest.raises(WAI.NoModel):
        WAI.propose(world, Acc.get(world, JORDAN), "ncr", docs, L.Anthropic("", env={}), today=AS_OF)
    s = Scripted({"stop_reason": "end_turn", "content": [{"type": "text", "text": "Looks fine."}]})
    with pytest.raises(L.LlmError, match="did not propose"):
        WAI.propose(world, Acc.get(world, JORDAN), "ncr", docs, s.model(), today=AS_OF)
    run = world.execute("select * from ai_runs where kind = 'workflow'").fetchone()
    assert run["engine"] == "model (failed)" and "did not propose" in run["error"]
    assert world.execute("select count(*) as n from workflow_proposals").fetchone()["n"] == 0
    with pytest.raises(WA.AdminError, match="choose the procedures"):
        WP.read(world, "ncr", [])


def test_long_procedures_are_cut_and_said_to_be(world, monkeypatch):
    qp08, qp09, _ = library(world)
    monkeypatch.setattr(WP, "MAX_TOTAL", 300)
    docs = WP.read(world, "capa", [qp09["id"], qp08["id"]])
    assert [d["cut"] for d in docs] == [True, True] and len(docs[0]["text"]) == 300 and docs[1]["text"] == ""
    assert docs[0]["id"] == qp09["id"]
    assert "only the first 300 of" in WAI._docs_text(docs)


def test_proposals_api(db_url, monkeypatch):
    s = Scripted()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=s.model()))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, SAM, DANA):
            Acc.set_password(conn, e, PW)
        qp08, _, _ = library(conn)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(SAM)                                                 # may look, not ask or decide
    out = c.get("/api/quality/workflows/ncr/proposals").json()
    assert out["ai"] is True and out["can_propose"] is False and out["procedures"] == []
    assert c.post("/api/quality/workflows/ncr/proposals", json={"document_ids": [qp08["id"]]}).status_code == 403
    login(JORDAN)
    out = c.get("/api/quality/workflows/ncr/proposals").json()
    assert out["can_propose"] is True and out["procedures"][0]["id"] == qp08["id"]
    assert out["procedures"][0]["suggested"] is True
    assert c.get("/api/quality/workflows/nope/proposals").status_code == 404
    assert c.post("/api/quality/workflows/ncr/proposals", json={"document_ids": "all"}).status_code == 400
    assert c.post("/api/quality/workflows/ncr/proposals", json={"document_ids": [10**6]}).status_code == 409
    s.replies.append(reply([change("field", LOT, qp08["id"], name="lot_no", label="Lot number", type="text")]))
    r = c.post("/api/quality/workflows/ncr/proposals", json={"document_ids": [qp08["id"]]})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["items"][0]["acceptable"] is True and p["draft"] is None
    s.replies.append({"stop_reason": "end_turn", "content": [{"type": "text", "text": "no"}]})
    assert c.post("/api/quality/workflows/ncr/proposals", json={"document_ids": [qp08["id"]]}).status_code == 502
    iid = p["items"][0]["id"]
    login(SAM)
    assert c.get(f"/api/quality/workflows/proposals/{p['id']}").json()["can_decide"] is False
    assert c.post(f"/api/quality/workflows/proposal-items/{iid}/accept").status_code == 403
    login(JORDAN)
    done = c.post(f"/api/quality/workflows/proposal-items/{iid}/accept", json={"note": "per QP-08"}).json()
    assert done["items"][0]["decision"] == "accepted" and done["draft"]["version"] == 2
    assert c.post(f"/api/quality/workflows/proposal-items/{iid}/reject").status_code == 409
    assert c.get("/api/quality/workflows/proposals/999999").status_code == 404
    # without a model key the proposals are still shown, asking is not offered
    c2 = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c2.__enter__()
    assert c2.post("/api/login", json={"email": JORDAN, "password": PW}).status_code == 200
    out = c2.get("/api/quality/workflows/ncr/proposals").json()
    assert out["ai"] is False and out["can_propose"] is False and len(out["proposals"]) == 1
    assert c2.post("/api/quality/workflows/ncr/proposals", json={"document_ids": [qp08["id"]]}).status_code == 409
    c2.__exit__(None, None, None)
    c.__exit__(None, None, None)


def test_a_record_under_the_new_version_needs_what_the_procedure_asks(world):
    """End to end: the accepted lot number and GM sign-off are asked for on a new nonconformance report."""
    qp08, _, _ = library(world)
    docs = WP.read(world, "ncr", [qp08["id"]])
    s = Scripted(reply([
        change("field", LOT, qp08["id"], name="lot_no", label="Lot number", type="text", required_at=["disposition"]),
        change("approval", GM, qp08["id"], name="gm_signoff", label="GM sign-off", before="close", roles=["owner"],
               when={"severity": ["major"]})]))
    p = WAI.propose(world, Acc.get(world, JORDAN), "ncr", docs, s.model(), today=AS_OF)
    for it in WP.items(world, p["id"]):
        draft = WP.accept(world, it["id"], JORDAN)["draft_version"]
    WA.enable(world, draft, Acc.get(world, DANA), PW)
    rec = Q.create_ncr(world, JORDAN, title="Bent brackets", description="Bent in transit", severity="minor")
    Q.contain(world, rec["id"], JORDAN, "Moved to QC Hold")
    with pytest.raises(Q.QualityError, match="still needed: Lot number"):
        Q.submit_disposition(world, rec["id"], JORDAN, "scrap", 5, "Bent beyond repair")
