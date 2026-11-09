"""PLM step 27a (round 124): where each use of a part sits in its assembly. FreeCAD (the add-on) and a STEP file
give the same placements; they go onto the BOM lines, survive a save without them and a new revision, and the 3D
view of a BOM places every part with a model; what has no placement or model is listed, never guessed."""

import math
from pathlib import Path

import pytest

from tests.test_plm import (  # noqa: F401
    CASEY,
    PW,
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
from wqops.hub.plm import intake as IN
from wqops.hub.plm import parts as PT
from wqops.hub.plm import place as PL
from wqops.hub.plm import readers as RD

FIX = Path(__file__).parent / "fixtures"
# what FreeCAD 1.0 said about the same assembly (a box turned 30° about x, a pin turned 90° about z and a link)
FREECAD = {("Crank", 1): [{"p": [-5.0, 0.0, 3.0], "q": [0.258819045, 0.0, 0.0, 0.965925826]}],
           ("Pin", 2): [{"p": [10.0, 20.0, 0.0], "q": [0.0, 0.0, 0.707106781, 0.707106781]},
                        {"p": [0.0, -15.0, 7.0], "q": [0.0, 0.0, 0.0, 1.0]}]}


def test_placement_arithmetic():
    pl = PL.clean({"p": [1, 2, 3], "q": [0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4)]})
    m = PL.matrix(pl)
    assert [round(v, 6) for v in m[:3]] == [0, -1, 0]                       # x turns onto y
    assert PL.placement(PL.mul(m, PL.inverse(m))) == {"p": [0, 0, 0], "q": [0, 0, 0, 1]}
    back = PL.placement(m)
    assert back["p"] == pl["p"] and all(abs(a - b) < 1e-8 for a, b in zip(back["q"], pl["q"], strict=True))
    with pytest.raises(PL.PlaceError):
        PL.clean({"p": [1, 2], "q": [0, 0, 0, 1]})
    with pytest.raises(PL.PlaceError):
        PL.clean({"p": [1, 2, 3], "q": [0, 0, 0, 2]})
    with pytest.raises(PL.PlaceError):
        PL.clean_list([{"p": [0, 0, 0]}], 2)


def test_step_from_freecad_gives_the_placements_freecad_has():
    d = RD.read_step((FIX / "plm-placed-freecad.step").read_bytes())
    names = {n["key"]: n["name"] for n in d["nodes"]}
    got = {(names[x["child"]], int(x["qty"])): x["placements"] for x in d["links"]}
    assert got == FREECAD


def test_placements_onto_lines_kept_and_shown_in_3d(world, fake, erp):  # noqa: F811
    c = world
    data = {"nodes": [{"key": "Asm", "name": "Needle bar mechanism"}, {"key": "Crank", "name": "Crank"},
                      {"key": "Pin", "name": "Pin"}, {"key": "Plate", "name": "Plate"}],
            "links": [{"parent": "Asm", "child": "Crank", "qty": 1, "placements": FREECAD[("Crank", 1)]},
                      {"parent": "Asm", "child": "Pin", "qty": 2, "placements": FREECAD[("Pin", 2)]},
                      {"parent": "Asm", "child": "Plate", "qty": 1}]}
    with pytest.raises(PT.PlmError, match="placements for a quantity"):
        IN.check_data({**data, "links": [{**data["links"][1], "qty": 3}]})
    v = IN.receive(c, source="freecad", sent_by="FreeCAD", data=data, file_name="m.FCStd")
    v = IN.write(c, u(c, CASEY), v["id"], PW, erp)
    ids = v["result"]["ids"]
    bid = v["result"]["boms"][0]
    by = {x["code"]: x for x in B.lines(c, bid)}
    assert {PT.get(c, ids[k])["item_code"]: n for k, n in (("Crank", 1), ("Pin", 2), ("Plate", 0))} == \
        {k: by[k]["placed"] for k in by}
    # the BOM editor saves without placements: they stay while the quantity fits
    B.set_lines(c, u(c, CASEY), bid, [{"part_id": ids["Crank"], "qty": 1}, {"part_id": ids["Pin"], "qty": 2},
                                      {"part_id": ids["Plate"], "qty": 1}])
    assert [x["placed"] for x in B.lines(c, bid)] == [1, 2, 0]
    B.set_lines(c, u(c, CASEY), bid, [{"part_id": ids["Crank"], "qty": 1}, {"part_id": ids["Pin"], "qty": 3},
                                      {"part_id": ids["Plate"], "qty": 1}])
    assert [x["placed"] for x in B.lines(c, bid)] == [1, 0, 0]          # 3 pins, 2 places: not guessed
    B.set_lines(c, u(c, CASEY), bid, [{"part_id": ids["Crank"], "qty": 1, "placements": FREECAD[("Crank", 1)]},
                                      {"part_id": ids["Pin"], "qty": 2, "placements": FREECAD[("Pin", 2)]},
                                      {"part_id": ids["Plate"], "qty": 1}])
    # models on the crank and the pin; none on the plate
    for k in ("Crank", "Pin"):
        PT.add_file(c, u(c, CASEY), ids[k], "model", f"{k.lower()}.step", b"ISO-10303-21; " + k.encode())
    s = B.scene(c, bid)
    assert sorted(x["code"] for x in s["items"]) == sorted([PT.get(c, ids["Crank"])["item_code"]] +
                                                           [PT.get(c, ids["Pin"])["item_code"]] * 2)
    pin = [x for x in s["items"] if x["part_id"] == ids["Pin"]]
    assert [round(v, 6) for v in pin[0]["m"][:4]] == [0, -1, 0, 10]
    assert s["missing"] == [{"code": PT.get(c, ids["Plate"])["item_code"], "name": "Plate", "why": "model"}]
