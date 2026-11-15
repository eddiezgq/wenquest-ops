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
from wqops.demo import sewing_manual as SM
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
    assert len(codes) >= 450 and {"WQ88-0000", "WQ73-0000", "WQ88-2400", "WQ88-1720", "WQ73-6000"} <= codes
    kids = SW._children(d)
    # options edit lines of the machine's own BOM (WenQuest round 138: T, E, D of WQ-LS); the overlock has no hook
    assert {"WQ88-1710", "WQ88-1850", "WQ88-2000"} <= set(kids["WQ88-0000"])
    five = SW.explode(SW.model_lines("WQ73-0000", OL.CONFIG, {"X": "5"}, kids), kids)
    assert SW.HOOK not in five and five["WQ73-1390"] == Decimal(13)          # 2 + 10 in the box + 1 chain
    eco = SW.model_lines("WQ88-0000", LS.CONFIG, {"T": "N", "E": "M", "D": "S"}, kids)
    assert "WQ88-2000" not in eco and "WQ88-1850" in eco
    ted = SW.model_lines("WQ88-0000", LS.CONFIG, {"T": "T", "E": "E", "D": "D"}, kids)
    assert {"WQ88-2000", "WQ88-2400", "WQ88-1720"} <= set(ted) and not {"WQ88-1850", "WQ88-1710"} & set(ted)
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
    assert len(out["models"]) == 10 and "WQ88-0000-NMS" in out["models"]
    assert all(b.get("docstatus") == 1 for b in fake.docs["BOM"].values())
    capa = conn.execute("select status, root_cause from capas").fetchone()
    assert capa["status"] == "investigation" and "梭尖硬度" in capa["root_cause"]
    assert conn.execute("select status from changes where kind = 'product'").fetchone()["status"] == "closed"
    assert conn.execute("select count(*) as n from plm_intake where status = 'pending'").fetchone()["n"] == 1
    # the ready parts manual (WenQuest rounds 124, 138): the WQ-LS head in 3D, every line with 3D placed
    man = out["manual"]
    assert man["model"] == "WQ88-0000-TED" and man["edition"] == 1 and man["names_open"] == 0
    assert man["pages"] == len(man["model_pages"]) + man["no_picture"] and man["pages"] >= 20
    assert out["models_3d"] == len(list((SM.HERE / "lockstitch" / "models").glob("*.step"))) > 80
    unplaced = conn.execute(
        "select a.item_code as asm, p.item_code as code from plm_bom_lines l join plm_boms b on b.id = l.bom_id "
        "join plm_parts a on a.id = b.part_id join plm_parts p on p.id = l.part_id where a.item_code like 'WQ88-%%' "
        "and jsonb_array_length(l.placements) = 0 and exists (select 1 from plm_files f join plm_part_revisions r "
        "on r.id = f.revision_id where r.part_id = p.id and f.kind = 'model')").fetchall()
    # a part with 3D sits where it is drawn; its other uses (spare needles, the rear bearing) are not drawn
    assert {(x["asm"], x["code"]) for x in unplaced} <= {("WQ88-5000", "WQ88-1490"), ("WQ88-1200", "ZC-6201ZZ")}
    row = conn.execute("select pages from plm_manuals").fetchone()
    assert all(x["name_en"] for p in row["pages"] for x in p["lines"])
    with pytest.raises(SW.SewingError, match="already loaded"):
        SW.load(conn, erp, m, dt.date(2026, 11, 8), say=lambda _t: None)
