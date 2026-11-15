"""The parts manual of the sewing demo (WenQuest rounds 124 and 138): 蓝湾 (fictional) has a ready manual of its
lockstitch model.

1. 3D (WenQuest round 138): the head mechanism is WenQuest's WQ-LS design; demo/plm/wqls_models.py writes one STEP per
   part code in manual/lockstitch/models/ and where each BOM line sits (manual/lockstitch/placements.json, machine
   coordinates). They go onto the parts while they are drafts, as an engineer would push them. Lines that WQ-LS does
   not model (covers, needle plate, controls, table, accessories, most standard parts) have no 3D and no placement.
2. Exploded views (33b, ADR-0030): made by the FreeCAD add-on without its window from the same 3D (manual/explode/),
   sent as the add-on sends them and confirmed by the engineer, one left waiting. A page without one says so (no
   schematic, WenQuest round 135 rule 1).
3. English names from a table people wrote (machines/lockstitch_en.py), confirmed by the engineer.
4. Edition 1 of the manual of one lockstitch model.

No dealer link: its address is shown once, so whoever looks at the demo makes one."""

from __future__ import annotations

import json
from pathlib import Path

from wqops.demo.machines import lockstitch_en as EN

HERE = Path(__file__).parent / "manual"


def models(conn, user: dict) -> int:
    """The STEP files onto the draft parts, where each use sits onto the draft BOM lines. How many files."""
    from wqops.hub.plm import boms as B  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    root = HERE / "lockstitch"
    n = 0
    for f in sorted((root / "models").glob("*.step")):
        p = PT.by_code(conn, f.stem)
        if p is None:
            continue
        PT.add_file(conn, user, p["id"], "model", f.name, f.read_bytes())
        n += 1
    places = json.loads((root / "placements.json").read_text(encoding="utf-8"))
    for asm, kids in places.items():
        a = PT.by_code(conn, asm)
        if a is None:
            continue
        bid = conn.execute("select id from plm_boms where part_id = %s and status = 'draft' order by id desc limit 1",
                           (a["id"],)).fetchone()
        if bid is None:
            continue
        rows = []
        for ln in conn.execute("select l.part_id, l.qty, l.uom, l.note, p.item_code from plm_bom_lines l join "
                               "plm_parts p on p.id = l.part_id where l.bom_id = %s order by l.pos",
                               (bid["id"],)).fetchall():
            r = {"part_id": ln["part_id"], "qty": B.R.qty_text(ln["qty"]), "uom": ln["uom"], "note": ln["note"]}
            if ln["item_code"] in kids:
                r["placements"] = kids[ln["item_code"]]
            rows.append(r)
        try:
            B.set_lines(conn, user, bid["id"], rows)
        except PT.PlmError as exc:
            raise PT.PlmError(f"{asm}: {exc}") from exc
    return n


def names(conn, user: dict, bid: int) -> int:
    """English names from the table, confirmed; how many."""
    from wqops.hub.plm import explode as EX  # noqa: PLC0415

    n = 0
    for p in EX.tree_parts(conn, bid):              # the assembly itself included
        e = EN.en(p["name"])
        if e and p["name_en_state"] != "confirmed":
            EX.set_name_en(conn, user, p["id"], e, confirm=True)
            n += 1
    return n


PENDING = ("WQ88-1710",)        # left for whoever looks at the demo to confirm (not in the TED manual)


def pages(conn, user: dict) -> dict:
    """The exploded views the FreeCAD add-on made without its window (manual/explode/<assembly code>.json, .svg, .png;
    demo/plm/wqls_explode.py), sent as the add-on sends them; the engineer confirms all but one."""
    from wqops.hub.plm import boms as B  # noqa: PLC0415
    from wqops.hub.plm import explode as EX  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    out = {"confirmed": [], "pending": []}
    for f in sorted((HERE / "explode").glob("*.json")):
        code = f.stem
        p = PT.by_code(conn, code)
        if p is None or B._shown_bom(conn, p["id"]) is None:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        r = EX.from_freecad(conn, "FreeCAD (demo batch)", code, d, f.with_suffix(".svg").read_bytes(),
                            png=f.with_suffix(".png").read_bytes())
        if code in PENDING:
            out["pending"].append(code)
            continue
        EX.confirm(conn, user, r["bom"])
        out["confirmed"].append(code)
    return out


def manual(conn, user: dict, model_code: str, today) -> dict:
    """English names, the pages, edition 1."""
    from wqops.hub.plm import boms as B  # noqa: PLC0415
    from wqops.hub.plm import manual as MAN  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    pid = PT.by_code(conn, model_code)["id"]
    root = B._shown_bom(conn, pid)
    n = names(conn, user, root)
    done = pages(conn, user)
    m = MAN.generate(conn, user, pid, today=today)
    return {"model": model_code, "edition": m["edition"], "pages": len(m["pages"]), "names": n,
            "model_pages": done["confirmed"], "pending": done["pending"],
            "no_picture": sum(1 for x in m["pages"] if not x.get("picture")), "names_open": m["names_open"]}
