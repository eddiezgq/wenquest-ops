"""Cause analysis, step 22b (ADR-0022): fishbone and 5 Why on a nonconformance report, a CAPA or a complaint. The
model suggests causes from the records it is shown and must cite them; code keeps only suggestions citing shown
records; a person accepts, edits or removes each; each why is confirmed before the next; the signed conclusion is
added to the record's root cause and the analysis is then kept as it was. Scripted model; fictional data only."""

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
from wqops.hub.quality import causes as C
from wqops.hub.quality import causes_ai as CAI
from wqops.hub.quality import causes_rules as CR
from wqops.hub.quality import complaints as CMP
from wqops.hub.quality import records as Q


def reply(name, key, items, note=""):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 1200, "output_tokens": 300},
            "content": [{"type": "tool_use", "id": "t1", "name": name, "input": {key: items, "note": note}}]}


def test_rules():
    assert CR.categories(None) == list(CR.BONES) and CR.categories([" Tooling ", "tooling", "Operator"]) == \
        ["Tooling", "Operator"]
    for bad in (["one"], "x", [str(i) for i in range(11)]):
        with pytest.raises(CR.CauseError):
            CR.categories(bad)
    assert CR.refs(["A-1", "A-1", " B-2 ", ""]) == ["A-1", "B-2"] and CR.refs("C-3") == ["C-3"]
    kept, dropped = CR.verify([{"text": "a", "refs": ["X-1", "Y-9"]}, {"text": "b", "refs": ["Z-9"]},
                               {"text": "c", "refs": []}], {"X-1", "X-2"})
    assert kept == [{"text": "a", "refs": ["X-1"], "unshown": ["Y-9"]}]
    assert [d["reason"] for d in dropped] == ["cites no record it was shown", "cites no record"]
    a = {"name": "RCA-1", "status": "open", "method": "five_why", "categories": []}
    its = [{"id": 1, "level": 1, "status": "accepted"}, {"id": 2, "level": 2, "status": "proposed"}]
    assert CR.frontier(its) == 2 and CR.frontier([]) == 1
    CR.can_add(a, its, category=None, level=2)
    with pytest.raises(CR.CauseError, match="accept an answer to why 2 first"):
        CR.can_add(a, its, category=None, level=3)
    with pytest.raises(CR.CauseError, match="already has an accepted answer"):
        CR.can_accept(a, [*its, {"id": 3, "level": 1, "status": "proposed"}], {"id": 3, "level": 1})
    its[1]["status"] = "accepted"
    with pytest.raises(CR.CauseError, match="rests on this one"):
        CR.can_remove(a, its, its[0])
    assert CR.ready(a, its) == [] and "every suggestion" in CR.ready(a, [*its, {"level": 3, "status": "proposed"}])[0]
    assert CR.write_back("", "Worn die", "RCA-00001", "fishbone") == "Worn die (from Fishbone RCA-00001)"
    assert CR.write_back("Earlier.", "X", "RCA-2", "five_why") == "Earlier.\n\nX (from 5 Why RCA-2)"


def test_fishbone_on_a_report(world):  # noqa: F811
    w = world
    got = lots(w)                                       # two rejected lots of BOLT-B, each with a report
    ncrs = w.execute("select * from ncr_records order by id").fetchall()
    assert len(ncrs) == 2
    n = ncrs[-1]
    with pytest.raises(CR.CauseError, match="fishbone or five_why"):
        C.start(w, JORDAN, "ncr", n["id"], "pareto")
    a = C.start(w, JORDAN, "ncr", n["id"], "fishbone")
    assert a["name"] == "RCA-00001" and a["categories"] == list(CR.BONES) and a["ref_name"] == n["name"]
    recs = {r["ref"]: r for r in C.context(w, C.subject(w, "ncr", n["id"]), today=AS_OF)}
    assert n["name"] in recs and ncrs[0]["name"] in recs and got[1]["name"] in recs and got[0]["name"] in recs
    assert recs[got[0]["name"]]["kind"] == "incoming inspection" and "accept" in recs[got[0]["name"]]["summary"]
    # without a key the model is not asked
    with pytest.raises(CAI.NoModel):
        CAI.suggest(w, u(w, JORDAN), a["id"], L.Anthropic("", env={}), today=AS_OF)
    s = Scripted(reply("suggest_causes", "causes", [
        {"category": "Materials", "text": "Lots from Gulf Fasteners run long", "refs": [got[1]["name"], "PO-123"]},
        {"category": "Measurement", "text": "Length gauge may read short", "refs": ["GAUGE-404"]},     # not shown
        {"category": "Weather", "text": "Humid week", "refs": [n["name"]]},                             # no such bone
        {"category": "Methods", "text": "No first-article check at the supplier", "refs": [n["name"]]}],
        note="No supplier process records were shown."))
    out = CAI.suggest(w, u(w, JORDAN), a["id"], s.model(), today=AS_OF)
    body = s.requests[0]["body"]
    assert body["tool_choice"]["name"] == "suggest_causes" and "never invent a record" in body["system"]
    assert f"[{got[1]['name']}] incoming inspection" in body["messages"][0]["content"]
    assert len(out["items"]) == 2 and out["unusable"] == 1 and out["dropped"][0]["refs"] == ["GAUGE-404"]
    assert out["items"][0]["refs"] == [got[1]["name"]] and out["items"][0]["status"] == "proposed"
    run = w.execute("select * from ai_runs where id = %s", (out["run"],)).fetchone()
    assert run["kind"] == "cause" and run["verified"] is False and run["unverified"][0]["refs"] == ["GAUGE-404"]
    assert run["answer"] == "No supplier process records were shown."
    with pytest.raises(CR.CauseError, match="decide the suggestions already made"):
        CAI.suggest(w, u(w, JORDAN), a["id"], s.model(), today=AS_OF)
    with pytest.raises(CR.CauseError, match="every suggestion"):
        C.conclude(w, u(w, JORDAN), a["id"], "Long lots", PW, today=AS_OF)
    first, second = out["items"]
    C.decide(w, DANA, a["id"], first["id"], "edit", new_text="Gulf Fasteners lots run long on length")
    C.decide(w, DANA, a["id"], second["id"], "remove")
    with pytest.raises(CR.CauseError, match="was removed"):
        C.decide(w, DANA, a["id"], second["id"], "accept")
    with pytest.raises(CR.CauseError, match="no record with the number: NCR-09999"):
        C.add(w, JORDAN, a["id"], {"category": "Machines", "text": "Worn heading die", "refs": ["NCR-09999"]})
    with pytest.raises(CR.CauseError, match="choose one of the categories"):
        C.add(w, JORDAN, a["id"], {"category": "Luck", "text": "x"})
    mine = C.add(w, JORDAN, a["id"], {"category": "Machines", "text": "Worn heading die", "refs": [ncrs[0]["name"]]})
    assert mine["origin"] == "person" and mine["status"] == "accepted"
    v = C.view(w, a["id"])
    assert v["to_conclude"] == [] and [i["edited"] for i in v["items"]] == [True, False, False]
    with pytest.raises(Q.SignatureError):
        C.conclude(w, u(w, JORDAN), a["id"], "Supplier heading die worn", "wrong", today=AS_OF)
    done = C.conclude(w, u(w, JORDAN), a["id"], "Supplier heading die worn", PW, today=AS_OF)
    assert done["status"] == "concluded" and done["written_to"] == f"8D D4 of {n['name']}"
    d4 = w.execute("select sections from eightd where ncr_id = %s", (n["id"],)).fetchone()["sections"]["d4"]
    assert d4 == "Supplier heading die worn (from Fishbone RCA-00001)"
    assert Q.signatures(w, "cause_analysis", a["id"])[0]["meaning"] == "Root cause concluded"
    assert "root cause concluded" in [h["action"] for h in Q.history(w, "ncr", n["id"])]
    # kept as it was: only addenda are added
    with pytest.raises(CR.CauseError, match="add an addendum"):
        C.add(w, JORDAN, a["id"], {"category": "Machines", "text": "x"})
    with pytest.raises(psycopg.errors.RaiseException, match="kept as it was"):
        w.execute("update cause_analyses set conclusion = 'x' where id = %s", (a["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="kept as they were"):
        w.execute("update cause_items set text = 'x' where analysis_id = %s", (a["id"],))
    with pytest.raises(psycopg.errors.RaiseException):
        w.execute("delete from cause_items where analysis_id = %s", (a["id"],))
    C.addendum(w, DANA, a["id"], "Supplier replaced the die on 2026-10-20 (their report).")
    assert len(C.view(w, a["id"])["addenda"]) == 1
    # a second analysis appends to D4; a cancelled report takes none
    b = C.start(w, JORDAN, "ncr", n["id"], "five_why", problem="Why were lots long?")
    C.add(w, JORDAN, b["id"], {"level": 1, "text": "The die wore"})
    C.conclude(w, u(w, JORDAN), b["id"], "No die life limit at the supplier", PW, today=AS_OF)
    d4 = w.execute("select sections from eightd where ncr_id = %s", (n["id"],)).fetchone()["sections"]["d4"]
    assert d4.endswith("\n\nNo die life limit at the supplier (from 5 Why RCA-00002)")
    Q.cancel_ncr(w, ncrs[0]["id"], JORDAN, "duplicate")
    with pytest.raises(CR.CauseError, match="cannot take a new root cause: it is cancelled"):
        C.start(w, JORDAN, "ncr", ncrs[0]["id"], "fishbone")
    c = C.start(w, JORDAN, "ncr", n["id"], "fishbone", categories=["Tooling", "Gauging"])
    C.cancel(w, JORDAN, c["id"], "started by mistake")
    assert C.get(w, c["id"])["status"] == "cancelled"
    assert [x["name"] for x in C.for_record(w, "ncr", n["id"])] == ["RCA-00001", "RCA-00002", "RCA-00003"]


def test_five_why_on_a_complaint_and_a_capa(world):  # noqa: F811
    w = world
    got = lots(w)
    cmp = CMP.create(w, JORDAN, {"received_on": AS_OF.isoformat(), "customer": "Bayline Electrical",
                                 "item_code": "BOLT-B", "description": "Bolts too long to fit"}, today=AS_OF)
    a = C.start(w, JORDAN, "complaint", cmp["id"], "five_why")
    with pytest.raises(CR.CauseError, match="accept an answer to why 1 first"):
        C.add(w, JORDAN, a["id"], {"level": 2, "text": "x"})
    s = Scripted(reply("suggest_answers", "answers", [
        {"text": "Bolts from rejected lots reached the customer", "refs": [got[1]["name"]]},
        {"text": "Incoming lots run long", "refs": [got[2]["name"]]}]),
        reply("suggest_answers", "answers", [{"text": "Rejected lot was used before return", "refs": [cmp["name"]]}]))
    one = CAI.suggest(w, u(w, JORDAN), a["id"], s.model(), today=AS_OF)
    assert [i["level"] for i in one["items"]] == [1, 1]
    assert "Why 1: why did the problem happen?" in s.requests[0]["body"]["messages"][0]["content"]
    C.decide(w, JORDAN, a["id"], one["items"][0]["id"], "accept")
    with pytest.raises(CR.CauseError, match="why 1 already has an accepted answer"):
        C.decide(w, JORDAN, a["id"], one["items"][1]["id"], "accept")
    C.decide(w, JORDAN, a["id"], one["items"][1]["id"], "remove")
    assert C.view(w, a["id"])["next_level"] == 2
    two = CAI.suggest(w, u(w, JORDAN), a["id"], s.model(), today=AS_OF)
    ask = s.requests[1]["body"]["messages"][0]["content"]
    assert "Why 2: why did this happen: 'Bolts from rejected lots reached the customer'?" in ask
    assert "do not suggest them again:\n- Incoming lots run long" in ask
    assert two["items"][0]["level"] == 2
    C.decide(w, JORDAN, a["id"], two["items"][0]["id"], "accept")
    with pytest.raises(CR.CauseError, match="rests on this one"):
        C.decide(w, JORDAN, a["id"], one["items"][0]["id"], "remove")
    C.conclude(w, u(w, JORDAN), a["id"], "Rejected stock not segregated", PW, today=AS_OF)
    assert CMP.get(w, cmp["id"])["root_cause"] == "Rejected stock not segregated (from 5 Why RCA-00001)"
    # a CAPA takes its root cause while under investigation
    ncr = w.execute("select id from ncr_records order by id limit 1").fetchone()["id"]
    capa = Q.create_capa(w, JORDAN, kind="corrective", title="Long bolts", description="Two lots long",
                         ncr_ids=[ncr], risk="medium")
    b = C.start(w, JORDAN, "capa", capa["id"], "fishbone")
    assert C.subject(w, "capa", capa["id"])["item_code"] == "BOLT-B"
    C.add(w, JORDAN, b["id"], {"category": "Materials", "text": "Supplier die worn"})
    with pytest.raises(CR.CauseError, match="cannot be written now"):
        C.conclude(w, u(w, JORDAN), b["id"], "Supplier die worn", PW, today=AS_OF)       # still a draft
    Q.submit_capa(w, capa["id"], JORDAN)
    C.conclude(w, u(w, JORDAN), b["id"], "Supplier die worn", PW, today=AS_OF)
    assert Q.capa(w, capa["id"])["root_cause"] == "Supplier die worn (from Fishbone RCA-00002)"


def test_cause_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)
        nid = Q.create_ncr(conn, JORDAN, title="Scratched housing", description="Seen at packing")["id"]

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.get("/api/quality/causes").status_code == 200
    assert c.get(f"/api/quality/causes/for/ncr/{nid}").json()["can_start"] is False
    assert c.post("/api/quality/causes", json={"kind": "ncr", "ref_id": nid, "method": "fishbone"}).status_code == 403
    login(JORDAN)
    assert c.get(f"/api/quality/causes/for/ncr/{nid}").json()["can_start"] is True
    assert c.get("/api/quality/causes/for/nope/1").status_code == 404
    assert c.post("/api/quality/causes", json={"kind": "ncr", "ref_id": "x", "method": "fishbone"}).status_code == 400
    assert c.post("/api/quality/causes", json={"kind": "ncr", "ref_id": 99999, "method": "fishbone"}).status_code \
        == 404
    r = c.post("/api/quality/causes", json={"kind": "ncr", "ref_id": nid, "method": "fishbone"})
    assert r.status_code == 201
    aid = r.json()["id"]
    p = c.get(f"/api/quality/causes/{aid}").json()
    assert p["can_edit"] and p["can_ask"] is False and p["to_conclude"] == ["accept at least one cause"]
    assert c.get(f"/api/quality/causes/{aid}/context").json()["records"][0]["ref"] == "NCR-00001"
    assert c.post(f"/api/quality/causes/{aid}/suggest").status_code == 409                 # no model key
    p = c.post(f"/api/quality/causes/{aid}/items", json={"category": "Methods", "text": "No packing instruction"})
    assert p.status_code == 201 and p.json()["items"][0]["text"] == "No packing instruction"
    assert c.post(f"/api/quality/causes/{aid}/items", json={"category": "Nope", "text": "x"}).status_code == 409
    iid = p.json()["items"][0]["id"]
    assert c.post(f"/api/quality/causes/{aid}/items/{iid}", json={"action": "edit", "text": "No packing WI"}) \
        .json()["items"][0]["edited"] is True
    assert c.post(f"/api/quality/causes/{aid}/conclude", json={"conclusion": "x", "password": "no"}).status_code == 403
    done = c.post(f"/api/quality/causes/{aid}/conclude", json={"conclusion": "No packing WI", "password": PW})
    assert done.json()["analysis"]["status"] == "concluded"
    assert c.post(f"/api/quality/causes/{aid}/addenda", json={"text": "WI-12 issued"}).status_code == 201
    assert c.post(f"/api/quality/causes/{aid}/cancel", json={"reason": "x"}).status_code == 409
    assert c.get("/api/quality/causes").json()["analyses"][0]["accepted"] == 1
