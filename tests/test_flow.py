"""Process flow charts, step 22d (ADR-0022): steps in order with branches (rework, scrap); links to documents in effect,
PFMEA rows, inspection plans, production templates and measuring equipment, checked against what is in effect; a link
to nothing in effect stops approval; approved with a signature by someone uninvolved, then fixed with what its links
pointed to and a fingerprint; what moved since approval is shown; new versions supersede. Fictional data only."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_demo import DEMO, TODAY, loaded  # noqa: F401 - the fixture
from tests.test_demo_quality import demo  # noqa: F401 - the fixture
from tests.test_iqc import PW, receipts
from tests.test_quality_data import business
from wqops.demo import quality as DQ
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.quality import flow as FW
from wqops.hub.quality import flow_rules as FL
from wqops.hub.quality import fmea as F
from wqops.hub.quality import records as Q

JORDAN, DANA = "jordan@demo.example", "dana@demo.example"


def test_rules():
    assert FL.branches([{"to": 2, "label": " Rejected ", "kind": "rework"}], {1, 2, 3}, 3) == \
        [{"to": 2, "label": "Rejected", "kind": "rework"}]
    assert FL.branches([{"to": None, "kind": "scrap", "label": "Return"}], {1}, 1)[0]["to"] is None
    for bad, msg in (([{"to": 9}], "a step of this chart"), ([{"to": 3}], "another step"),
                     ([{"to": None, "kind": "rework"}], "a rework branch always does"),
                     ([{"to": 1, "kind": "x"}], "rework, scrap or other"), ("x", "a list")):
        with pytest.raises(FL.FlowRuleError, match=msg):
            FL.branches(bad, {1, 2, 3}, 3)
    lk = FL.links({"documents": ["WI-1", "WI-1", " QP-5 "], "fmea": [{"name": "PFMEA-1", "seq": 2}], "plan": "BOX",
                   "gauges": [], "template": ""})
    assert lk == {"documents": ["WI-1", "QP-5"], "fmea": [{"name": "PFMEA-1", "seq": 2}], "plan": "BOX"}
    with pytest.raises(FL.FlowRuleError, match="not something a step links to"):
        FL.links({"photos": []})
    with pytest.raises(FL.FlowRuleError, match="its row number"):
        FL.links({"fmea": [{"name": "PFMEA-1"}]})
    assert FL.link_keys(lk) == [("documents", "WI-1"), ("documents", "QP-5"), ("fmea", "PFMEA-1#2"), ("plan", "BOX")]
    st = [{"seq": 1, "code": "10", "name": "Kit", "kind": "operation", "branches": [], "links": lk},
          {"seq": 3, "code": "30", "name": "Check", "kind": "inspection", "branches": [{"to": 2}], "links": {}}]
    res = {"documents:WI-1": {"ok": True}, "documents:QP-5": {"ok": False, "why": "no revision of it is in effect"},
           "fmea:PFMEA-1#2": {"ok": True}}
    assert FL.to_approve({}, st, res) == [
        "step 10 Kit: document QP-5: no revision of it is in effect",
        "step 10 Kit: incoming inspection plan BOX: not checked",
        "step 30 Check: a branch goes to a step that was removed"]
    assert FL.not_analysed(st) == ["30 Check"] and FL.to_approve({}, [], {}) == ["at least one step"]


def test_flow_chart_on_demo_records(demo):  # noqa: F811
    c = demo
    DQ.load(c, DEMO, TODAY)
    for e in (JORDAN, DANA):
        Acc.set_password(c, e, PW)
    ch = FW.create(c, JORDAN, {"title": "Kitting M8 bolts (Demo)", "item_code": "HX-BOLT-M8", "owner": JORDAN})
    assert ch["name"] == "PF-00002"                       # the demo has PF-00001
    steps = [("10", "move", "Receive lot", {"gauges": ["CAL-01"]}),
             ("20", "inspection", "Incoming inspection",
              {"plan": "BOX-12", "fmea": [{"name": "PFMEA-00001", "seq": 1}]}),
             ("30", "operation", "Kit", {"template": "KIT-M8", "documents": ["QP-05", "WI-99"],
                                         "fmea": [{"name": "PFMEA-00001", "seq": 2}]}),
             ("40", "inspection", "Weigh kit", {}),
             ("50", "store", "Finished kits", {})]
    for code, kind, name, links in steps:
        FW.add_step(c, JORDAN, ch["id"], {"code": code, "kind": kind, "name": name, "links": links})
    st = FW.steps(c, ch["id"])
    FW.update_step(c, JORDAN, ch["id"], st[3]["id"], {"branches": [{"to": 3, "label": "Light kit", "kind": "rework"}]})
    with pytest.raises(FW.FlowError, match="a step of this chart"):
        FW.update_step(c, JORDAN, ch["id"], st[3]["id"], {"branches": [{"to": 9}]})
    v = FW.view(c, ch["id"], today=TODAY)
    assert v["to_approve"] == ["step 30 Kit: document WI-99: no revision of it is in effect"]
    assert v["not_analysed"] == ["40 Weigh kit"]
    assert v["links_now"]["fmea:PFMEA-00001#2"]["label"].startswith("PFMEA-00001 v1 row 2: Bolts missing from a kit")
    assert v["links_now"]["template:KIT-M8"]["ok"] and v["links_now"]["documents:QP-05"]["ok"]
    with pytest.raises(FW.FlowError, match="WI-99"):
        FW.approve(c, Acc.get(c, DANA), ch["id"], PW, today=TODAY)
    FW.update_step(c, JORDAN, ch["id"], st[2]["id"], {"links": {"template": "KIT-M8", "documents": ["QP-05"],
                                                              "fmea": [{"name": "PFMEA-00001", "seq": 2}]}})
    # moving a step keeps branches pointing at the same steps
    FW.move_step(c, JORDAN, ch["id"], st[2]["id"], "up")
    after = {s["name"]: s for s in FW.steps(c, ch["id"])}
    assert after["Kit"]["seq"] == 2 and after["Weigh kit"]["branches"][0]["to"] == 2
    FW.move_step(c, JORDAN, ch["id"], st[2]["id"], "down")
    # approval: someone uninvolved, signed; the chart and what its links pointed to are kept
    with pytest.raises(PermissionError):
        FW.approve(c, Acc.get(c, JORDAN), ch["id"], PW, today=TODAY)
    a = FW.approve(c, Acc.get(c, DANA), ch["id"], PW, today=TODAY)
    assert a["status"] == "approved" and a["resolved"]["plan:BOX-12"]["ok"] is True
    assert FW.intact(c, FW.get(c, ch["id"])) is True
    with pytest.raises(psycopg.errors.RaiseException, match="steps are fixed"):
        c.execute("update flow_steps set name = 'x' where chart_id = %s", (ch["id"],))
    with pytest.raises(FW.FlowError, match="start a new version"):
        FW.add_step(c, JORDAN, ch["id"], {"name": "x"})
    pf = c.execute("select id from fmea_files where name = 'PFMEA-00001'").fetchone()["id"]
    assert [s["step"] for s in F.view(c, pf)["flow_steps"] if s["name"] == ch["name"]] == ["Incoming inspection", "Kit"]
    # the PFMEA gets a new version: the chart shows what moved since it was approved
    v2 = F.revise(c, JORDAN, pf)
    F.approve(c, Acc.get(c, DANA), v2["id"], PW)
    moved = FW.view(c, ch["id"], today=TODAY)["changed_since"]
    assert {m["link"] for m in moved} == {"fmea:PFMEA-00001#1", "fmea:PFMEA-00001#2"}
    assert moved[0]["now"].startswith("PFMEA-00001 v2")
    # a new version of the chart; removing a step drops branches to it
    n2 = FW.revise(c, JORDAN, ch["id"])
    kit = next(s for s in FW.steps(c, n2["id"]) if s["name"] == "Kit")
    FW.remove_step(c, JORDAN, n2["id"], kit["id"])
    assert next(s for s in FW.steps(c, n2["id"]) if s["name"] == "Weigh kit")["branches"] == []
    FW.approve(c, Acc.get(c, DANA), n2["id"], PW, today=TODAY)
    assert FW.get(c, ch["id"])["status"] == "superseded"
    assert Q.signatures(c, "flow_chart", n2["id"])[0]["meaning"] == "Process flow chart approved"
    assert {o["code"] for o in FW.options(c)["templates"]} == {"KIT-M8"}


def test_flow_api(db_url):
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
    assert c.get("/api/flow").status_code == 200
    assert c.post("/api/flow/charts", json={"title": "x"}).status_code == 403
    login(JORDAN)
    cid = c.post("/api/flow/charts", json={"title": "Packing"}).json()["id"]
    p = c.post(f"/api/flow/charts/{cid}/steps", json={"name": "Pack", "code": "10"})
    assert p.status_code == 201 and p.json()["steps"][0]["kind"] == "operation"
    p = c.post(f"/api/flow/charts/{cid}/steps", json={"name": "Check", "kind": "inspection",
                                                      "branches": [{"to": 1, "kind": "rework"}]})
    sid = p.json()["steps"][1]["id"]
    assert p.json()["steps"][1]["branches"][0]["to"] == 1
    assert c.post(f"/api/flow/charts/{cid}/steps", json={"name": "x", "kind": "dance"}).status_code == 409
    assert c.post(f"/api/flow/charts/{cid}/steps/{sid}/move", json={"direction": "up"}).json()["steps"][0]["name"] \
        == "Check"
    assert c.get("/api/flow/options").json()["templates"] == []
    assert c.post(f"/api/flow/charts/{cid}/approve", json={"password": PW}).status_code == 403    # an editor
    login(DANA)
    assert c.post(f"/api/flow/charts/{cid}/approve", json={"password": PW}).json()["status"] == "approved"
    assert c.delete(f"/api/flow/charts/{cid}/steps/{sid}").status_code == 409
    assert c.post(f"/api/flow/charts/{cid}/revise").json()["version"] == 2
