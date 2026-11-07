"""PLM step 26d (ADR-0026): a product change lists the parts it changes, how it takes effect and its impact analysis
(assemblies above, stock, open purchase, work and sales orders; unknown when there is no data), all fixed once
submitted; it is submitted only with them and implemented only when each part has its new revision released under
it; a change that lists parts starts revisions only of those parts; the AI drafts the impact note from the analysis
only. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.test_plm import (  # noqa: F401  # noqa: F401
    CASEY,
    DANA,
    JORDAN,
    PW,
    approved_change,
    erp,
    fake,
    files_dir,
    part,
    released,
    u,
    world,
)
from wqops.hub.plm import boms as B
from wqops.hub.plm import ecn as E
from wqops.hub.plm import ecn_ai as EAI
from wqops.hub.plm import parts as PT
from wqops.hub.quality import change_control as CC

YES_NO = {"q_product": "yes", "q_regulatory": "no", "q_risk": "no", "q_validation": "no"}


def machine(c, erp):  # noqa: F811
    """Head (machine) <- Arm (assembly) <- Crank; a bought hook on the head."""
    head = released(c, erp, "Lockstitch head", "assembly")
    arm = released(c, erp, "Needle bar arm", "assembly")
    crank = released(c, erp, "Crank", "link", L=32)
    ba = B.start(c, u(c, CASEY), arm["id"])
    B.set_lines(c, u(c, CASEY), ba["bom"]["id"], [{"code": crank["item_code"], "qty": 1}])
    B.release(c, u(c, CASEY), ba["bom"]["id"], PW, erp)
    bh = B.start(c, u(c, CASEY), head["id"])
    B.set_lines(c, u(c, CASEY), bh["bom"]["id"], [{"code": arm["item_code"], "qty": 1}])
    B.release(c, u(c, CASEY), bh["bom"]["id"], PW, erp)
    return head, arm, crank


def draft_change(c, title="Thicker crank"):
    ch = CC.create(c, CASEY, {"title": title, "kind": "product", "description": "crank 8 -> 10 mm",
                              "reason": "cracks in the field", "owner": CASEY, "assessment": "see impact",
                              **YES_NO})
    return ch["id"]


def synced(c, doctype, name, **data):
    c.execute("insert into erp_docs (doctype, name, modified, docstatus, hash, data) values (%s, %s, 'x', %s, 'h', %s)",
              (doctype, name, data.pop("docstatus", 1), Jsonb(data)))


def test_impact_analysis_and_unknowns(world, fake, erp):  # noqa: F811
    c = world
    head, arm, crank = machine(c, erp)
    cid = draft_change(c)
    v = E.add_item(c, u(c, CASEY), cid, {"code": crank["item_code"], "scope": "part"})
    assert v["items"][0]["from_part"] == "A" and v["items"][0]["from_bom"] is None
    with pytest.raises(PT.PlmError, match="no released BOM"):
        E.add_item(c, u(c, CASEY), cid, {"code": crank["item_code"], "scope": "bom"})
    # nothing synced yet: stock and orders are unknown, not zero
    v = E.analyse(c, u(c, CASEY), cid, erp)
    p = v["impact"]["data"]["parts"][0]
    assert [a["code"] for a in p["used_in"]] == [arm["item_code"], head["item_code"]] and p["used_in"][1]["top"]
    assert p["stock"] is None and p["purchase_orders"] is None and p["sales_orders"] is None
    assert p["work_orders"] == []
    synced(c, "Stock Ledger Entry", "SLE-1", item_code=crank["item_code"], actual_qty=120)
    synced(c, "Stock Ledger Entry", "SLE-2", item_code=crank["item_code"], actual_qty=-20)
    synced(c, "Purchase Order", "PO-1", status="To Receive and Bill", supplier="Cast Co (fictional)",
           items=[{"item_code": crank["item_code"], "qty": 50, "received_qty": 10}])
    synced(c, "Purchase Order", "PO-2", status="Completed", items=[{"item_code": crank["item_code"], "qty": 5}])
    synced(c, "Sales Order", "SO-1", status="To Deliver and Bill", customer="Garment Co (fictional)",
           items=[{"item_code": head["item_code"], "qty": 3, "delivered_qty": 1}])
    fake.put("Work Order", "WO-1", production_item=arm["item_code"], qty=10, produced_qty=4, status="In Process",
             docstatus=1)
    v = E.analyse(c, u(c, CASEY), cid, erp)
    p = v["impact"]["data"]["parts"][0]
    assert p["stock"] == "100" and p["purchase_orders"] == [{"name": "PO-1", "party": "Cast Co (fictional)",
                                                           "open": "40"}]
    assert p["sales_orders"][0]["name"] == "SO-1" and p["sales_orders"][0]["open"] == "2"
    assert p["work_orders"] == [{"name": "WO-1", "item": arm["item_code"], "open": "6"}]
    assert v["impact"]["current"]
    text = E.as_text(v["impact"]["data"])
    assert "100" in text and "PO-1 40" in text and "WO-1 6" in text
    fake.fail_after = len(fake.requests)                 # ERPNext not answering: work orders unknown
    v = E.analyse(c, u(c, CASEY), cid, erp)
    assert v["impact"]["data"]["parts"][0]["work_orders"] is None
    fake.fail_after = None


def test_submit_needs_effect_and_current_analysis_implement_needs_released_revisions(world, erp):  # noqa: F811
    c = world
    head, arm, crank = machine(c, erp)
    cid = draft_change(c)
    E.add_item(c, u(c, CASEY), cid, {"code": crank["item_code"], "scope": "part"})
    with pytest.raises(CC.ChangeError, match="takes effect"):
        CC.submit(c, CASEY, cid)
    with pytest.raises(PT.PlmError, match="date"):
        E.set_effect(c, u(c, CASEY), cid, {"mode": "date"})
    E.set_effect(c, u(c, CASEY), cid, {"mode": "use_up"})
    E.analyse(c, u(c, CASEY), cid, erp)
    E.add_item(c, u(c, CASEY), cid, {"code": arm["item_code"], "scope": "bom"})
    with pytest.raises(CC.ChangeError, match="impact analysis"):        # the list changed after the analysis
        CC.submit(c, CASEY, cid)
    E.analyse(c, u(c, CASEY), cid, erp)
    CC.submit(c, CASEY, cid)
    with pytest.raises(PT.PlmError, match="submitted"):
        E.add_item(c, u(c, CASEY), cid, {"code": head["item_code"], "scope": "bom"})
    with pytest.raises(psycopg.errors.RaiseException, match="fixed"):
        c.execute("delete from plm_change_items where change_id = %s", (cid,))
    with pytest.raises(PermissionError):                 # the engineer who listed the parts is an editor
        CC.approve(c, u(c, CASEY), cid, PW)
    CC.approve(c, u(c, JORDAN), cid, PW)
    # only what the change lists, for what it says changes
    with pytest.raises(PT.PlmError, match="does not list"):
        PT.new_revision(c, u(c, CASEY), head["id"], cid)
    with pytest.raises(PT.PlmError, match="does not list"):
        PT.new_revision(c, u(c, CASEY), arm["id"], cid)          # the change says only Arm's BOM changes
    c.execute("update changes set implementation = 'new revisions released' where id = %s", (cid,))
    with pytest.raises(CC.ChangeError, match="new revision of LNK-00001"):
        CC.implement(c, u(c, CASEY), cid)
    PT.new_revision(c, u(c, CASEY), crank["id"], cid)
    PT.update(c, u(c, CASEY), crank["id"], {"params": {"L": 32, "t": 10}})
    PT.release(c, u(c, CASEY), crank["id"], PW)
    with pytest.raises(CC.ChangeError, match="new BOM revision of ASM"):
        CC.implement(c, u(c, CASEY), cid)
    b = B.start(c, u(c, CASEY), arm["id"], cid)
    B.release(c, u(c, CASEY), b["bom"]["id"], PW, erp)
    assert CC.implement(c, u(c, CASEY), cid)["status"] == "implemented"
    v = CC.view(c, cid, dt.date(2026, 11, 7))
    assert any("design change" == h["action"] for h in v["history"])


def test_ai_drafts_only_from_the_analysis(world, erp):  # noqa: F811
    c = world
    _head, _arm, crank = machine(c, erp)
    cid = draft_change(c)
    E.add_item(c, u(c, CASEY), cid, {"code": crank["item_code"], "scope": "part"})
    with pytest.raises(PT.PlmError, match="analyse"):
        EAI.draft(c, u(c, CASEY), cid, None, today=dt.date(2026, 11, 7))
    E.analyse(c, u(c, CASEY), cid, erp)
    out = EAI.draft(c, u(c, CASEY), cid, None, today=dt.date(2026, 11, 7))      # no model: the analysis itself
    assert out["engine"] == "rules" and crank["item_code"] in out["note"]

    class Model:
        model = "test-model"

        def configured(self):
            return True

        def create(self, *_a, **_k):
            return {"content": [{"type": "tool_use", "input": {
                "note": "Touches the lockstitch head. Use up the 100 cranks in stock first."}}], "usage": {}}
    out = EAI.draft(c, u(c, CASEY), cid, Model(), today=dt.date(2026, 11, 7))
    assert out["engine"] == "model" and out["unverified"] == ["Use up the 100 cranks in stock first."]   # 100 is not
    run = c.execute("select kind, verified from ai_runs order by id desc limit 1").fetchone()
    assert run["kind"] == "plm-impact" and run["verified"] is False
