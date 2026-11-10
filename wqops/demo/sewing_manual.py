"""The parts manual of the sewing demo (WenQuest rounds 124 and 135): 蓝湾 (fictional) has a ready manual of its
lockstitch model.

1. 3D for every part (round 135, 33a): the lockstitch machine modelled in FreeCAD by demo/plm/lockstitch_cad/ (one STEP
   per part in manual/lockstitch/models/, engineering approximation) goes onto the parts while they are drafts, as an
   engineer would push them; every BOM line gets where each use sits (manual/lockstitch/placements.json, machine
   coordinates).
2. Exploded views: the layouts and pictures saved in manual/pages/ (by assembly code), when there are any, are written
   as they are. Nothing is drawn in their place: a page without one says so (no schematic, round 135 rule 1).
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


def pages(conn, user: dict, boms: list[int]) -> dict:
    """Each page of the manual with a saved layout and picture (manual/pages/<assembly code>.json and .png)."""
    from wqops.hub.plm import explode as EX  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    out = {"model": [], "none": []}
    for bid in boms:
        code = PT.get(conn, conn.execute("select part_id from plm_boms where id = %s", (bid,)).fetchone()["part_id"])[
            "item_code"]
        saved = HERE / "pages" / f"{code}.json"
        if not saved.is_file():
            out["none"].append(code)
            continue
        by_code = {x["code"]: x["part_id"] for x in EX.lines(conn, bid)}
        d = json.loads(saved.read_text(encoding="utf-8"))
        lay = d["layout"]
        data = {"kind": "model", "layout": {
            **{k: lay[k] for k in ("camera", "factor") if k in lay},
            "moves": {str(by_code[c]): v for c, v in (lay.get("moves") or {}).items() if c in by_code},
            "drawn": {str(by_code[c]): v for c, v in (lay.get("drawn") or {}).items() if c in by_code}},
            "balloons": [{**{k: b[k] for k in ("x", "y", "ax", "ay") if k in b}, "part_id": by_code[b["code"]]}
                         for b in d["balloons"] if b["code"] in by_code]}
        EX.save(conn, user, bid, data, snapshot=(HERE / "pages" / f"{code}.png").read_bytes())
        out["model"].append(code)
    return out


def manual(conn, user: dict, model_code: str, today) -> dict:
    """English names, the pages, edition 1."""
    from wqops.hub.plm import boms as B  # noqa: PLC0415
    from wqops.hub.plm import manual as MAN  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    pid = PT.by_code(conn, model_code)["id"]
    root = B._shown_bom(conn, pid)
    n = names(conn, user, root)
    r = MAN.readiness(conn, pid)
    done = pages(conn, user, r["boms"])
    m = MAN.generate(conn, user, pid, today=today)
    return {"model": model_code, "edition": m["edition"], "pages": len(m["pages"]), "names": n,
            "model_pages": done["model"], "no_picture": len(done["none"]), "names_open": m["names_open"]}
