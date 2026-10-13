"""Quality, step 8b (ADR-0009 items 4-6): SPC against hand calculations, supplier scores, incoming inspection.
All data is fictional."""

import math

import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import AS_OF, DEMO, build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import sync as Y
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import incoming as IN
from wqops.hub.quality import spc

GROUPS = [[10, 11, 12], [11, 12, 13], [9, 10, 11], [10, 10, 10]]


def test_xbar_r_by_hand():
    c = spc.xbar_r(GROUPS)
    # means 11, 12, 10, 10 -> 10.75; ranges 2, 2, 2, 0 -> 1.5; n = 3: A2 1.023, D4 2.574, d2 1.693
    assert c["center"] == 10.75 and c["Rbar"] == 1.5
    assert math.isclose(c["UCL"], 10.75 + 1.023 * 1.5) and math.isclose(c["LCL"], 10.75 - 1.023 * 1.5)
    assert math.isclose(c["UCL_R"], 2.574 * 1.5) and c["LCL_R"] == 0
    assert math.isclose(c["sigma_within"], 1.5 / 1.693)
    cap = spc.capability([v for g in GROUPS for v in g], 7, 15, c["sigma_within"])
    # Cp = 8 / (6 * 0.8860) = 1.505; Cpk = min(15 - 10.75, 10.75 - 7) / (3 * 0.8860) = 3.75 / 2.658 = 1.411
    assert round(cap["Cp"], 3) == 1.505 and round(cap["Cpk"], 3) == 1.411


def test_individuals_and_rules():
    c = spc.i_mr([10, 12, 11, 13])
    # moving ranges 2, 1, 2 -> 5/3; sigma = (5/3) / 1.128; limits 11.5 +/- 3 sigma
    assert math.isclose(c["MRbar"], 5 / 3) and math.isclose(c["UCL"], 11.5 + 3 * (5 / 3) / 1.128)
    sig = spc.special_causes([0.1] * 8 + [5.0], 0, 1)
    assert [(s["rule"], s["index"]) for s in sig] == [(4, 7), (1, 8)]
    with pytest.raises(spc.SpcError):
        spc.xbar_r([[1, 2]])
    assert spc.chart([{"inspection": "Q", "date": "d", "values": [1, 2]}])["enough_data"] is False
    mixed = spc.chart([{"inspection": f"Q{i}", "date": str(i), "values": v} for i, v in
                       enumerate([[10, 11], [12], [11, 13, 12]])])
    assert mixed["chart"]["kind"] == "i_mr" and mixed["chart"]["points"] == [10.5, 12, 12]


def business():
    f = build()
    f.put("Item", "BOLT-B", item_name="Bolt-B", is_stock_item=1, inspection_required_before_purchase=1)
    for i, vals in enumerate(GROUPS, start=1):
        f.put("Quality Inspection", f"QM-{i}", item_code="WIDGET-A", status="Accepted", docstatus=1,
              report_date=f"2026-10-0{i}", inspection_type="In Process",
              readings=[{"specification": "Length", "numeric": 1, "min_value": 7, "max_value": 15,
                         **{f"reading_{j}": v for j, v in enumerate(vals, start=1)}},
                        {"specification": "Finish", "numeric": 0, "reading_value": "OK"}])
    return f


@pytest.fixture
def world(conn):
    Y.run(conn, ErpClient("http://erp", transport=business().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def test_spc_from_inspections(world):
    assert IN.parameters(world) == [{"item_code": "WIDGET-A", "parameter": "Length", "inspections": 4}]
    out = IN.spc_for(world, "WIDGET-A", "Length")
    assert out["enough_data"] and out["chart"]["kind"] == "xbar_r" and out["chart"]["center"] == 10.75
    assert round(out["capability"]["Cpk"], 3) == 1.411 and out["out_of_spec"] == 0
    assert out["inspections"] == ["QM-1", "QM-2", "QM-3", "QM-4"]
    assert IN.spc_for(world, "WIDGET-A", "Width")["enough_data"] is False


def test_supplier_facts(world):
    """ADR-0010: facts only, no score."""
    from wqops.hub.quality import records as Q

    n = Q.create_ncr(world, "jordan@demo.example", title="Bent", description="d", supplier="Gulf Fasteners",
                     quantity=5)
    world.execute("update ncr_records set created_at = '2026-10-05 12:00+00' where id = %s", (n["id"],))  # in period
    Q.create_capa(world, "jordan@demo.example", kind="corrective", title="Supplier 8D", ncr_ids=[n["id"]])
    r = IN.supplier_quality(world, AS_OF, 90)
    gulf, acme = r["suppliers"]
    # Gulf: incoming lots in 90 days QI-1 rejected, QI-2 accepted, QI-3 rejected -> 2 of 3 = 66.7%; on time 1 of 3
    assert (gulf["supplier"], gulf["lots"], gulf["rejected"], gulf["rejection_rate"], gulf["on_time"]) == \
        ("Gulf Fasteners", 3, 2, 66.7, 33.3)
    assert (gulf["ncrs"], gulf["concessions"], gulf["open_capas"]) == (1, 0, 1)
    assert "score" not in gulf and "grade" not in gulf
    # Acme: on time 1 of 1, no inspected lots -> rejection rate unknown, not 0
    assert (acme["supplier"], acme["on_time"], acme["lots"], acme["rejection_rate"]) == ("Acme Cable", 100.0, 0, None)


def test_awaiting_inspection(conn):
    # BOLT-B must be inspected: PR-2 has inspections; PR-3, PR-4 and the draft PR-5 do not; a cancelled one is ignored
    f = business()
    f.put("Purchase Receipt", "PR-5", supplier="Acme Cable", posting_date="2026-10-12", docstatus=0,
          items=[{"item_code": "BOLT-B", "qty": 3}])
    f.put("Purchase Receipt", "PR-6", supplier="Acme Cable", posting_date="2026-10-12", docstatus=2,
          items=[{"item_code": "BOLT-B", "qty": 3}])
    Y.run(conn, ErpClient("http://erp", transport=f.transport()))
    OP.project(conn, manifest=DEMO)
    assert [(x["receipt"], x["item_code"], x["draft"]) for x in IN.awaiting(conn)] == [
        ("PR-4", "BOLT-B", False), ("PR-3", "BOLT-B", False), ("PR-5", "BOLT-B", True)]


def test_quality_data_api(db_url):
    f = business()
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport()), ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in ("jordan@demo.example", "alex@demo.example"):
            Acc.set_password(conn, e, "Demo pass 2026")
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert c.get("/api/quality/suppliers").status_code == 403
    c.post("/api/login", json={"email": "jordan@demo.example", "password": "Demo pass 2026"})
    assert [x["supplier"] for x in c.get("/api/quality/suppliers").json()["suppliers"]] == ["Gulf Fasteners",
                                                                                        "Acme Cable"]
    assert c.get("/api/quality/spc", params={"item_code": "WIDGET-A", "parameter": "Length"}).json()["enough_data"]
    r = c.post("/api/quality/incoming/draft", json={"receipt": "PR-3", "item_code": "BOLT-B"})
    assert r.status_code == 400 and "sample size" in r.json()["detail"]
    r = c.post("/api/quality/incoming/draft", json={"receipt": "PR-9", "item_code": "BOLT-B", "sample_size": 5})
    assert r.status_code == 409
    d = c.post("/api/quality/incoming/draft", json={"receipt": "PR-3", "item_code": "BOLT-B", "sample_size": 5}).json()
    assert d["status"] == "pending" and d["payload"]["sample_size"] == 5.0 and f.requests[-1].method == "GET"
    with DB.connect(db_url) as conn:
        done = D.confirm(conn, {"email": "jordan@demo.example", "roles": ["quality"]}, d["id"],
                         ErpClient("http://erp", transport=f.transport()))
    qi = f.docs["Quality Inspection"][done["erp_name"]]
    assert qi["docstatus"] == 0 and qi["reference_name"] == "PR-3" and qi["inspection_type"] == "Incoming"
    assert qi["inspected_by"] == "Administrator"      # Jordan has no ERPNext account: the account the hub uses
    f.users.add("jordan@demo.example")                # after Jordan's first sign-in to ERPNext
    with DB.connect(db_url) as conn:
        again = D.propose(conn, {"email": "jordan@demo.example", "roles": ["quality"]}, "Quality Inspection",
                          {k: d["payload"][k] for k in d["payload"]})
        done = D.confirm(conn, {"email": "jordan@demo.example", "roles": ["quality"]}, again["id"],
                         ErpClient("http://erp", transport=f.transport()))
    assert f.docs["Quality Inspection"][done["erp_name"]]["inspected_by"] == "jordan@demo.example"
    c.__exit__(None, None, None)
