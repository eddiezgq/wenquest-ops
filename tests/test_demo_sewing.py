"""The sewing machine demo company (PLM step 26f, ADR-0026), against the in-memory ERPNext stand-in: the parts and
BOMs of both machines released, approved suppliers for every bought part, the models generated, and the story in the
hub (supplier change, complaints, corrective action with the root cause; a finished design change; a FreeCAD batch
waiting). The ERPNext business itself (work orders, stock entries) needs a real ERPNext and is checked by the
install in CI. Fictional data only."""

import datetime as dt
from decimal import Decimal

import pytest

from tests.fake_erp import FakeErp
from wqops import company as C
from wqops.demo import sewing as SW
from wqops.demo.machines import lockstitch as LS
from wqops.demo.machines import overlock as OL
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


def test_machines_as_data():
    d = SW.design_data()
    codes = {n["code"] for n in d["nodes"]}
    assert len(codes) >= 500 and {"WQ88-0000", "WQ73-0000", "WQ88-1890", "WQ73-6000"} <= codes
    kids = SW._children(d)
    # options edit lines of the machine's own BOM; the overlock has no rotary hook
    assert {"WQ88-1800", "WQ88-2000", "WQ88-1530"} <= set(kids["WQ88-0000"])
    five = SW.explode(SW.model_lines("WQ73-0000", OL.CONFIG, {"X": "5"}, kids), kids)
    assert SW.HOOK not in five and five["WQ73-1390"] == Decimal(13)          # 2 + 10 in the box + 1 chain
    eco = SW.model_lines("WQ88-0000", LS.CONFIG, {"P": "5", "T": "N", "L": "K"}, kids)
    assert "WQ88-2000" not in eco and "WQ88-1530" not in eco
    thick = SW.model_lines("WQ88-0000", LS.CONFIG, {"P": "7", "T": "T", "L": "A"}, kids)
    assert "WQ88-1890" in thick and "WQ88-1800" not in thick and thick["WQ88-1893"] == 1
    # the hook: opening, lots and use add up to 120 on hand at the end
    used = sum(q for _d, _k, q in SW.LS_RUNS)
    assert SW.HOOK_OPENING + sum(q for _d, q, _a in SW.HOOK_LOTS) - used == 120
    assert SW.supplier_of("旋梭 HSH-7.94A") == SW.HOOK_SUPPLIER
    assert SW.supplier_of("内六角螺钉 M4×8") == "温岭标准件（演示）"


def test_hub_side_of_the_demo(conn, monkeypatch):
    m = C.load(C.DEMO_DIR / "demo-sewing.yaml")
    Acc.sync(conn, m)
    fake = FakeErp()
    erp = ErpClient("http://erp", transport=fake.transport())
    for doctype in ("Supplier Group", "Customer Group", "Territory"):
        fake.put(doctype, f"Demo {doctype}", is_group=0)
    monkeypatch.setattr(SW.Sewing, "business", lambda self: None)
    out = SW.load(conn, erp, m, dt.date(2026, 11, 8), say=lambda _t: None)
    assert out["parts"] >= 500 and out["boms"] >= 45
    assert conn.execute("select count(*) as n from plm_parts where status <> 'released'").fetchone()["n"] == 0
    assert conn.execute("select count(*) as n from plm_boms where status <> 'released'").fetchone()["n"] == 0
    assert len(out["models"]) == 6 and "WQ88-0000-5NK" in out["models"]
    assert all(b.get("docstatus") == 1 for b in fake.docs["BOM"].values())
    capa = conn.execute("select status, root_cause from capas").fetchone()
    assert capa["status"] == "investigation" and "梭尖硬度" in capa["root_cause"]
    assert conn.execute("select status from changes where kind = 'product'").fetchone()["status"] == "closed"
    assert conn.execute("select count(*) as n from plm_intake where status = 'pending'").fetchone()["n"] == 1
    with pytest.raises(SW.SewingError, match="already loaded"):
        SW.load(conn, erp, m, dt.date(2026, 11, 8), say=lambda _t: None)
