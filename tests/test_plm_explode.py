"""PLM step 27b (round 124): the exploded view of an assembly, a page of the parts manual. Lines numbered in BOM
order, fasteners listed but not drawn by default, the picture and balloons kept, a new revision starting from the
old layout; English names written, drafted by AI (kept as drafts until a person confirms) and every AI run kept."""

import pytest

from tests.test_plm import (  # noqa: F401
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
from wqops.hub.plm import boms as B
from wqops.hub.plm import explode as EX
from wqops.hub.plm import intake as IN
from wqops.hub.plm import parts as PT

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _asm(c, erp):  # noqa: F811
    data = {"nodes": [{"key": "Asm", "name": "针杆部件"}, {"key": "Bar", "name": "针杆"},
                      {"key": "Screw", "name": "螺钉 SM9/64(40)×4"}],
            "links": [{"parent": "Asm", "child": "Bar", "qty": 1, "placements": [{"p": [0, 0, 0]}]},
                      {"parent": "Asm", "child": "Screw", "qty": 2}]}
    v = IN.receive(c, source="freecad", sent_by="FreeCAD", data=data, file_name="a.FCStd")
    v = IN.write(c, u(c, CASEY), v["id"], PW, erp)
    PT.add_file(c, u(c, CASEY), v["result"]["ids"]["Bar"], "model", "bar.step", b"ISO-10303-21; bar")
    return v["result"]["boms"][0], v["result"]["ids"]


def test_page_numbers_saves_and_starts_a_new_revision_from_the_old_layout(world, fake, erp, monkeypatch):  # noqa: F811
    c = world
    bid, ids = _asm(c, erp)
    v = EX.view(c, bid)
    assert [(x["no"], x["name"], x["drawn"]) for x in v["lines"]] == [(1, "针杆", True),
                                                                       (2, "螺钉 SM9/64(40)×4", False)]
    assert [x["line"] for x in v["scene"]["items"]] == [ids["Bar"]] and v["page"]["kind"] == "model"
    with pytest.raises(PT.PlmError, match="PNG or JPG"):
        EX.save(c, u(c, CASEY), bid, {"kind": "model"}, snapshot=b"GIF89a")
    with pytest.raises(PT.PlmError, match="upload the drawing"):
        EX.save(c, u(c, CASEY), bid, {"kind": "image"})
    v = EX.save(c, u(c, CASEY), bid, {"kind": "model", "layout": {"factor": 9, "moves": {str(ids["Bar"]): [0, 0, 5],
                                                                                       "999": [1, 1, 1]},
                                                              "drawn": {str(ids["Screw"]): True}},
                                      "balloons": [{"part_id": ids["Bar"], "x": 0.8, "y": 0.2, "ax": 0.5, "ay": 0.5},
                                                   {"part_id": 999, "x": 0, "y": 0}]}, snapshot=PNG)
    p = v["page"]
    assert p["layout"]["factor"] == 5 and p["layout"]["moves"] == {str(ids["Bar"]): [0, 0, 5]}
    assert [b["part_id"] for b in p["balloons"]] == [ids["Bar"]] and EX.picture(c, bid, "snapshot") == PNG
    # released, then a new revision under an approved change: it starts from this layout
    monkeypatch.setattr(B, "_supplier", lambda _c, _code: True)
    from wqops.hub.plm import catalog as CAT

    for k in ("Bar", "Screw"):
        cat = CAT.get(PT.get(c, ids[k])["category"])
        PT.update(c, u(c, CASEY), ids[k], {"params": {f["key"]: "M4" if f.get("type") == "text" else 1
                                                      for f in cat["fields"] if f.get("required")}})
        PT.release(c, u(c, CASEY), ids[k], PW)
    PT.release(c, u(c, CASEY), ids["Asm"], PW)
    B.release(c, u(c, CASEY), bid, PW, erp)
    EX.save(c, u(c, CASEY), bid, {"kind": "model", "balloons": []}, snapshot=PNG)   # a layout after release: fine
    cid = approved_change(c, parts=[(ids["Asm"], "bom")])
    b2 = B.start(c, u(c, CASEY), ids["Asm"], cid)["bom"]["id"]
    v2 = EX.view(c, b2)
    assert v2["page"]["from_revision"] == "A" and v2["page"]["snapshot_sha"] is None


class Model:
    model = "test-model"

    def __init__(self, names):
        self.names = names

    def configured(self):
        return True

    def create(self, system, messages, tools, max_tokens, tool_choice=None):
        asked = [ln.split("\t")[0] for ln in messages[0]["content"].splitlines()]
        return {"content": [{"type": "tool_use", "input": {"names": [{"code": k, "name_en": self.names[k]}
                                                                     for k in asked if k in self.names]
                                                           + [{"code": "NOT-ASKED", "name_en": "x"}]}}],
                "usage": {}}


def test_english_names_drafted_then_confirmed(world, fake, erp):  # noqa: F811
    c = world
    bid, ids = _asm(c, erp)
    bar = PT.get(c, ids["Bar"])["item_code"]
    EX.set_name_en(c, u(c, CASEY), ids["Screw"], "Screw SM9/64(40)x4", confirm=True)
    import datetime as dt

    r = EX.draft_names(c, u(c, CASEY), bid, Model({bar: "Needle Bar"}), today=dt.date(2026, 11, 9))
    assert r["drafted"] == 1 and r["left"] == 1                                  # the assembly itself had none
    by = {x["part_id"]: x for x in EX.lines(c, bid)}
    assert (by[ids["Bar"]]["name_en"], by[ids["Bar"]]["name_en_state"]) == ("Needle Bar", "draft")
    assert (by[ids["Screw"]]["name_en"], by[ids["Screw"]]["name_en_state"]) == ("Screw SM9/64(40)x4", "confirmed")
    assert c.execute("select count(*) as n from ai_runs").fetchone()["n"] == 1
    with pytest.raises(PT.PlmError, match="no AI"):
        EX.draft_names(c, u(c, CASEY), bid, None, today=dt.date(2026, 11, 9))
