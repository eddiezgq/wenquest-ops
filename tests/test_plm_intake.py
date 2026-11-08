"""PLM step 26e (ADR-0026): design data from FreeCAD (machine token, scope plm:send), a STEP file (assembly
structure and names, no geometry) or an Excel BOM (flat or with levels) waits in one inbox; an engineer matches
each part or makes it new and writes the batch with a signature: parts and draft BOMs, never released; a released
BOM needs an approved design change. Fictional data only."""

import io
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

from tests.test_plm import (  # noqa: F401  # noqa: F401
    CASEY,
    PW,
    approved_change,
    erp,
    fake,
    files_dir,
    manifest,
    part,
    released,
    u,
    world,
)
from wqops.erp import ErpClient
from wqops.hub import integration as IG
from wqops.hub.app import create_app
from wqops.hub.plm import boms as B
from wqops.hub.plm import intake as IN
from wqops.hub.plm import parts as PT
from wqops.hub.plm import readers as RD

STEP = b"""ISO-10303-21;
HEADER;
FILE_NAME('head.stp','2026-11-08',(''),(''),'','','');
ENDSEC;
DATA;
#1=PRODUCT('HEAD-1','\\X2\\673A5934\\X0\\','',(#9));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('design','',#2,#10);
#4=PRODUCT('SFT-9','Main shaft; long','',(#9));
#5=PRODUCT_DEFINITION_FORMATION('','',#4);
#6=PRODUCT_DEFINITION('design','',#5,#10);
#7=PRODUCT('SCR-M5','Screw M5',
  '',(#9));
#8=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',#7,.NOT_KNOWN.);
#11=PRODUCT_DEFINITION('design','',#8,#10);
#20=NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','','',#3,#6,$);
#21=NEXT_ASSEMBLY_USAGE_OCCURRENCE('2','','',#3,#11,$);
#22=NEXT_ASSEMBLY_USAGE_OCCURRENCE('3','','',#3,#11,$);
#23=NEXT_ASSEMBLY_USAGE_OCCURRENCE('4','','',#3,#11,$);
ENDSEC;
END-ISO-10303-21;
"""


def xlsx(rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_readers_step_and_excel():
    d = RD.read_step(STEP)
    names = {n["key"]: (n["code"], n["name"]) for n in d["nodes"]}
    assert names["#1"] == ("HEAD-1", "机头") and names["#4"][1] == "Main shaft; long"
    assert {(x["parent"], x["child"], x["qty"]) for x in d["links"]} == {("#1", "#4", "1"), ("#1", "#7", "3")}
    with pytest.raises(RD.ReadError, match="not a STEP"):
        RD.read_step(b"hello")
    flat = RD.read_excel(xlsx([["父件编码", "子件编码", "名称", "数量", "单位", "自制/外购"],
                               ["H", "S", "上轴", 1, "Nos", "自制"], ["H", "B", "轴承", 2, "Nos", "外购"],
                               ["H", "B", "轴承", 1, "Nos", "外购"]]))
    assert {(x["parent"], x["child"], x["qty"]) for x in flat["links"]} == {("H", "S", "1"), ("H", "B", "3")}
    assert next(n for n in flat["nodes"] if n["code"] == "B")["source"] == "buy"
    lv = RD.read_excel(xlsx([["层级", "编码", "名称", "数量"], [1, "H", "机头", 1], [2, "A", "针杆部件", 1],
                             [3, "N", "针杆", 1], [2, "S", "上轴", 1], [".2", "P", "销", 4]]))
    assert {(x["parent"], x["child"], x["qty"]) for x in lv["links"]} == {
        ("H", "A", "1"), ("A", "N", "1"), ("H", "S", "1"), ("H", "P", "4")}
    with pytest.raises(RD.ReadError, match="header"):
        RD.read_excel(xlsx([["a", "b"], [1, 2]]))


def test_inbox_plan_write_drafts_and_released_bom_needs_a_change(world, fake, erp):  # noqa: F811
    c = world
    shaft = released(c, erp, "Main shaft", "shaft", d=14, length=420)
    v = IN.upload(c, u(c, CASEY), "excel", "old.xlsx", xlsx([
        ["父件编码", "子件编码", "名称", "数量", "自制/外购"], ["H-1", shaft["item_code"], "上轴", 1, "自制"],
        ["H-1", "B-6202", "轴承 6202", 2, "外购"]]))
    rows = {r["key"]: r for r in v["rows"]}
    assert rows[shaft["item_code"]]["plan"] == {"action": "match", "part_id": shaft["id"]}
    assert rows["H-1"]["plan"]["category"] == "assembly" and rows["B-6202"]["plan"]["source"] == "buy"
    assert v["problems"] == []
    with pytest.raises(PT.PlmError, match="category"):
        IN.set_plan(c, u(c, CASEY), v["id"], {"B-6202": {"action": "new", "category": "nope", "source": "buy"}})
    v = IN.set_plan(c, u(c, CASEY), v["id"], {"B-6202": {"action": "new", "category": "bearing", "source": "buy",
                                                         "uom": "Nos"}})
    with pytest.raises(Exception, match="password"):
        IN.write(c, u(c, CASEY), v["id"], "wrong", erp)
    v = IN.write(c, u(c, CASEY), v["id"], PW, erp)
    assert v["status"] == "written" and sorted(v["result"]["parts_made"]) == ["B-6202", "H-1"]
    head = PT.by_code(c, "H-1")
    bom = B.view(c, v["result"]["boms"][0], erp)
    assert bom["bom"]["status"] == "draft" and {(x["code"], x["qty"]) for x in bom["lines"]} == {
        (shaft["item_code"], "1"), ("B-6202", "2")}
    assert fake.docs["Item"]["B-6202"]["item_group"] == "PLM"
    with pytest.raises(PT.PlmError, match="decided"):
        IN.write(c, u(c, CASEY), v["id"], PW, erp)
    # a second batch for the head while its BOM is still a draft: the draft's lines are replaced
    v2 = IN.upload(c, u(c, CASEY), "excel", "again.xlsx", xlsx([
        ["父件编码", "子件编码", "数量"], ["H-1", shaft["item_code"], 3]]))
    assert v2["problems"] == []
    v2 = IN.write(c, u(c, CASEY), v2["id"], PW, erp)
    assert v2["result"]["boms"] == [bom["bom"]["id"]]
    assert [(x["code"], x["qty"]) for x in B.lines(c, bom["bom"]["id"])] == [(shaft["item_code"], "3")]
    del head


def test_released_bom_and_rejection(world, fake, erp, monkeypatch):  # noqa: F811
    c = world
    monkeypatch.setattr(B, "_supplier", lambda _c, _code: True)
    head = released(c, erp, "Head", "assembly")
    shaft = released(c, erp, "Shaft", "shaft", d=10, length=100)
    b = B.start(c, u(c, CASEY), head["id"])
    B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": shaft["item_code"], "qty": 1}])
    B.release(c, u(c, CASEY), b["bom"]["id"], PW, erp)
    v = IN.upload(c, u(c, CASEY), "excel", "x.xlsx", xlsx([["父件编码", "子件编码", "数量"],
                                                           [head["item_code"], shaft["item_code"], 2]]))
    assert any("released" in p for p in v["problems"])
    with pytest.raises(PT.PlmError, match="not ready"):
        IN.write(c, u(c, CASEY), v["id"], PW, erp)
    v = IN.reject(c, u(c, CASEY), v["id"], "wrong file")
    assert v["status"] == "rejected"
    import psycopg

    with pytest.raises(psycopg.errors.RaiseException, match="kept"):
        c.execute("delete from plm_intake")


def test_freecad_push_with_a_machine_token(world, db_url, fake):  # noqa: F811
    c = world
    tok, secret = IG.new_token(c, "dana@demo.example", "FreeCAD on the design PC", ["plm:send"])
    other, other_secret = IG.new_token(c, "dana@demo.example", "Gauge", ["measurements:send"])
    data = {"nodes": [{"key": "Body", "code": "", "name": "Crank", "material": "QT500", "volume_mm3": 1234.5},
                      {"key": "Asm", "name": "Needle bar mechanism"}],
            "links": [{"parent": "Asm", "child": "Body", "qty": 2}]}
    with TestClient(create_app({}, lambda: (manifest(), "ok"), db_url=db_url,
                               erp=ErpClient("http://erp", transport=fake.transport()))) as cl:
        r = cl.post("/api/integration/v1/plm/design-data", headers={"Authorization": f"Bearer {other_secret}"},
                    data={"data": json.dumps(data)})
        assert r.status_code == 403
        r = cl.post("/api/integration/v1/plm/design-data", headers={"Authorization": f"Bearer {secret}"},
                    data={"data": json.dumps(data)},
                    files={"file:Body": ("crank.step", b"ISO-10303-21;"), "model": ("mech.FCStd", b"PK..")})
        assert r.status_code == 202, r.text
        iid = r.json()["id"]
        assert cl.post("/api/login", json={"email": CASEY, "password": PW}).status_code == 200
        v = cl.get(f"/api/plm/intake/{iid}").json()
        assert v["source"] == "freecad" and v["sent_by"] == "FreeCAD on the design PC"
        assert next(x for x in v["rows"] if x["key"] == "Body")["file"]["name"] == "crank.step"
        v = cl.post(f"/api/plm/intake/{iid}/write", json={"password": PW}).json()
        assert v["status"] == "written", v
        crank = PT.get(c, v["result"]["ids"]["Body"])
        assert PT.view(c, crank["id"])["revisions"][0]["files"][0]["name"] == "crank.step"
        assert PT.current(c, crank["id"])["params"]["material"] == "QT500"
        assert cl.get(f"/api/plm/intake/{iid}/file").content == b"PK.."
    del tok, other


def test_freecad_add_on_tree():
    """The add-on's tree (plain Python, no FreeCAD): links count as uses of what they point at; several top objects
    get one assembly named after the document."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freecad" / "WenQuestPLM"))
    import wqplm_tree as T

    items = [{"name": "Asm", "label": "Needle bar mechanism", "kind": "assembly", "children": ["Crank", "L1", "L2"]},
             {"name": "Crank", "label": "Crank", "kind": "solid", "code": "LNK-7", "material": "QT500"},
             {"name": "Pin", "label": "Pin", "kind": "solid", "volume_mm3": 12.5},
             {"name": "L1", "kind": "link", "target": "Pin"}, {"name": "L2", "kind": "link", "target": "Pin"},
             {"name": "Spare", "label": "Spare shaft", "kind": "solid"}]
    d = T.build(items, "Head")
    assert {(x["parent"], x["child"], x["qty"]) for x in d["links"]} == {
        ("Asm", "Crank", 1), ("Asm", "Pin", 2), ("__document__", "Asm", 1), ("__document__", "Spare", 1)}
    assert next(n for n in d["nodes"] if n["key"] == "Crank") == {"key": "Crank", "code": "LNK-7", "name": "Crank",
                                                                  "material": "QT500"}
    assert IN.check_data(d)["nodes"][-1]["name"] == "Head"


def test_step_written_by_freecad():
    """A STEP FreeCAD wrote (fictional needle bar mechanism: a crank and two links to one pin): UTF-8 names, the
    assembly read, no part numbers made up from names."""
    from pathlib import Path

    d = RD.read_step((Path(__file__).parent / "fixtures" / "plm-needle-bar-freecad.step").read_bytes())
    names = {n["key"]: n for n in d["nodes"]}
    by = {(names[x["parent"]]["name"], names[x["child"]]["name"]): x["qty"] for x in d["links"]}
    assert by == {("针杆机构", "曲柄"): "1", ("针杆机构", "销"): "2"}
    assert all(n["code"] == "" for n in d["nodes"])


def test_readers_repeats_damage_and_cycles():
    """A sub-assembly listed twice in a level BOM counts its parts once per sub-assembly, not twice; listed with
    other parts the second time it is refused. A damaged STEP or a NUL is a reading error, never a crash; a batch
    whose assembly contains itself is refused."""
    lv = RD.read_excel(xlsx([["层级", "编码", "数量"], [1, "H", 1], [2, "A", 2], [3, "N", 1], [3, "P", 4],
                             [2, "S", 1], [2, "A", 1], [3, "N", 1], [3, "P", 4]]))
    assert {(x["parent"], x["child"], x["qty"]) for x in lv["links"]} == {
        ("H", "A", "3"), ("A", "N", "1"), ("A", "P", "4"), ("H", "S", "1")}
    with pytest.raises(RD.ReadError, match="different parts"):
        RD.read_excel(xlsx([["层级", "编码", "数量"], [1, "H", 1], [2, "A", 1], [3, "N", 1], [2, "A", 1],
                            [3, "P", 1]]))
    with pytest.raises(RD.ReadError, match="damaged"):
        RD.read_step(STEP.replace(b"FORMATION('','',#1);", b"FORMATION(#1);"))
    with pytest.raises(PT.PlmError):
        IN.read_file("step", b"ISO-10303-21;\x00\xff" * 10)
    d = RD.read_step(STEP.replace(b"Main shaft; long", b"Main\x00shaft"))
    assert all("\x00" not in n["name"] for n in d["nodes"])
    assert IN.check_data({"nodes": [{"key": "a\x00", "name": "x\x00y"}]})["nodes"][0] == {
        "key": "a", "code": "", "name": "x y"}
    loop = {"nodes": [{"key": k} for k in "ABC"],
            "links": [{"parent": a, "child": b} for a, b in ("AB", "BC", "CA")]}
    with pytest.raises(PT.PlmError, match="contains itself"):
        IN.check_data(loop)


def test_erpnext_items_cycles_with_existing_boms_and_changes(world, fake, erp, monkeypatch):  # noqa: F811
    c = world
    monkeypatch.setattr(B, "_supplier", lambda _c, _code: True)
    fake.put("Item", "OLD-7", item_code="OLD-7", item_name="Old bushing", stock_uom="Nos")
    v = IN.upload(c, u(c, CASEY), "excel", "a.xlsx", xlsx([["父件编码", "子件编码", "名称", "数量", "自制/外购"],
                                                           ["H-2", "OLD-7", "Bushing", 2, "外购"]]))
    v = IN.set_plan(c, u(c, CASEY), v["id"], {"OLD-7": {"action": "new", "category": "other", "source": "buy",
                                                        "uom": "Nos"}})
    assert any("OLD-7" in p and "ERPNext" in p for p in IN.view(c, v["id"], erp)["problems"])
    with pytest.raises(PT.PlmError, match="not ready"):
        IN.write(c, u(c, CASEY), v["id"], PW, erp)
    v = IN.set_plan(c, u(c, CASEY), v["id"], {"OLD-7": {"action": "new", "category": "other", "source": "buy",
                                                        "uom": "Nos", "link_existing": True}})
    v = IN.write(c, u(c, CASEY), v["id"], PW, erp)
    assert PT.by_code(c, "OLD-7")["erp_state"] == "existing"
    # a released head that the batch would put under its own child
    head = released(c, erp, "Head", "assembly")
    arm = released(c, erp, "Arm", "assembly")
    b = B.start(c, u(c, CASEY), head["id"])
    B.set_lines(c, u(c, CASEY), b["bom"]["id"], [{"code": arm["item_code"], "qty": 1}])
    v = IN.upload(c, u(c, CASEY), "excel", "b.xlsx", xlsx([["父件编码", "子件编码", "数量"],
                                                           [arm["item_code"], head["item_code"], 1]]))
    assert any("contain itself" in p for p in v["problems"])
    # a released BOM under an approved change that does not list the part
    B.release(c, u(c, CASEY), b["bom"]["id"], PW, erp)
    other = released(c, erp, "Other", "shaft", d=5, length=50)
    cid = approved_change(c, parts=[(other["id"], "part")])
    v = IN.upload(c, u(c, CASEY), "excel", "c.xlsx", xlsx([["父件编码", "子件编码", "数量"],
                                                           [head["item_code"], other["item_code"], 1]]))
    v = IN.set_plan(c, u(c, CASEY), v["id"], {r["key"]: r["plan"] for r in v["rows"]}, {head["item_code"]: cid})
    assert any("does not list" in p for p in v["problems"])


def test_write_is_all_or_nothing_and_items_follow(world, fake, erp, monkeypatch):  # noqa: F811
    c = world
    v = IN.upload(c, u(c, CASEY), "excel", "x.xlsx", xlsx([["父件编码", "子件编码", "名称", "数量", "自制/外购"],
                                                           ["H-3", "P-3", "Pin", 2, "自制"]]))

    def broken(*_a, **_k):
        raise PT.PlmError("no room")
    monkeypatch.setattr(B, "set_lines", broken)
    with pytest.raises(PT.PlmError, match="BOM not made: no room"):
        IN.write(c, u(c, CASEY), v["id"], PW, erp)
    assert IN.view(c, v["id"])["status"] == "pending" and PT.by_code(c, "H-3") is None and PT.by_code(c, "P-3") is None
    monkeypatch.undo()

    def down(*_a, **_k):
        raise RuntimeError("ERPNext went away")
    monkeypatch.setattr(PT, "_erp_item", down)
    v = IN.write(c, u(c, CASEY), v["id"], PW, erp)
    assert v["status"] == "written" and PT.by_code(c, "P-3")["erp_state"] == "failed"
