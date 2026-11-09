"""The parts manual of the sewing demo (round 124, 27d): 蓝湾 (fictional) has a ready manual of its lockstitch model.

1. The mechanism in 3D: 15 parts made by WenQuest's sewing design software (one STEP each in manual/mechanism/, in
   machine coordinates, so every placement is "where it is") go onto their parts while they are drafts, as an engineer
   would add them; the BOM lines that use them get their placements.
2. Exploded views: the pages whose parts have 3D were laid out in the exploded view page and saved; their layout and
   picture are in manual/pages/ (by part code) and are written as they are. Every other assembly gets a schematic
   drawn here: one box per part that is drawn (fasteners are not, rule 4), its code and a numbered balloon, marked
   as a schematic of the demo. Nothing is made up as 3D.
3. English names from a table people wrote (machines/lockstitch_en.py), confirmed by the engineer; a name the table
   does not have stays without one.
4. Edition 1 of the manual of one lockstitch model.

No dealer link: its address is shown once, so whoever looks at the demo makes one."""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path

from wqops.demo.machines import lockstitch as LS
from wqops.demo.machines import lockstitch_en as EN

HERE = Path(__file__).parent / "manual"
IDENTITY = {"p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0]}
CJK_FONTS = (os.environ.get("WQO_CJK_FONT", ""), "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")


def mechanism(conn, user: dict) -> int:
    """The STEP files onto the draft parts, the placements onto the draft BOM lines. How many files."""
    from wqops.hub.plm import boms as B  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    ids = {}
    for code in sorted(set(LS.MECHANISM.values())):
        p = PT.by_code(conn, code)
        PT.add_file(conn, user, p["id"], "model", f"{code}.step", (HERE / "mechanism" / f"{code}.step").read_bytes())
        ids[p["id"]] = code
    # the lines that use a mechanism part, or an assembly with one somewhere below it (shown as one block on its
    # parent's page), sit where they are
    placed = set(ids)
    while True:
        more = {r["part_id"] for r in conn.execute(
            "select distinct b.part_id from plm_boms b join plm_bom_lines l on l.bom_id = b.id where b.status = "
            "'draft' and l.part_id = any(%s)", (list(placed),))} - placed
        if not more:
            break
        placed |= more
    boms = [r["id"] for r in conn.execute(
        "select distinct b.id from plm_boms b join plm_bom_lines l on l.bom_id = b.id where b.status = 'draft' and "
        "l.part_id = any(%s) order by b.id", (list(placed),))]
    for bid in boms:
        rows = []
        for ln in conn.execute("select part_id, qty, uom, note from plm_bom_lines where bom_id = %s order by pos",
                               (bid,)).fetchall():
            r = {"part_id": ln["part_id"], "qty": B.R.qty_text(ln["qty"]), "uom": ln["uom"], "note": ln["note"]}
            if ln["part_id"] in placed:
                r["placements"] = [IDENTITY] * int(ln["qty"])
            rows.append(r)
        B.set_lines(conn, user, bid, rows)
    return len(ids)


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
    """Each page of the manual: the saved layout and picture when there is one, else a schematic."""
    from wqops.hub.plm import explode as EX  # noqa: PLC0415
    from wqops.hub.plm import parts as PT  # noqa: PLC0415

    out = {"model": [], "schematic": []}
    for bid in boms:
        code = PT.get(conn, conn.execute("select part_id from plm_boms where id = %s", (bid,)).fetchone()["part_id"])[
            "item_code"]
        ls = EX.lines(conn, bid)
        by_code = {x["code"]: x["part_id"] for x in ls}
        saved = HERE / "pages" / f"{code}.json"
        if saved.is_file():
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
            continue
        image, snapshot, balloons = schematic(code, ls)
        EX.save(conn, user, bid, {"kind": "image", "layout": {}, "balloons": balloons}, snapshot=snapshot,
                image=image, image_name=f"{code}-示意图.png")
        out["schematic"].append(code)
    return out


def _fonts(size: int):
    from PIL import ImageFont  # noqa: PLC0415

    latin = ImageFont.load_default(size)
    cjk = next((ImageFont.truetype(f, size) for f in CJK_FONTS if f and os.path.isfile(f)), None)
    return latin, cjk


def schematic(code: str, lines: list[dict]) -> tuple[bytes, bytes, list[dict]]:
    """A drawing of the assembly's parts as boxes (no geometry: it says so), and the same with numbered balloons.
    Returns the drawing, the picture with balloons and the balloons (as the exploded view page keeps them)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    drawn = [x for x in lines if x["drawn"]]
    w, h = 1600, 1000
    cols = max(1, math.ceil(math.sqrt(max(len(drawn), 1) * 1.6)))
    rows = max(1, math.ceil(len(drawn) / cols))
    bw, bh = min(260, (w - 160) // cols - 40), min(120, (h - 220) // rows - 50)
    gx, gy = (w - cols * (bw + 40)) // 2 + 20, 150 + ((h - 190) - rows * (bh + 50)) // 2
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    latin, cjk = _fonts(26)
    small, cjk_small = _fonts(20)
    d.text((40, 30), f"{code}  Schematic (demo) - not to scale", fill="#333333", font=latin)
    if cjk:
        d.text((40, 70), "示意图（演示）：不是实物形状，只示意有哪些零件", fill="#666666", font=cjk)
    centers = []
    for i, x in enumerate(drawn):
        cx0, cy0 = gx + (i % cols) * (bw + 40), gy + (i // cols) * (bh + 50)
        d.rounded_rectangle((cx0, cy0, cx0 + bw, cy0 + bh), radius=10, outline="#555555", width=3, fill="#f4f5f7")
        d.text((cx0 + 12, cy0 + 12), x["code"], fill="#222222", font=small)
        if cjk_small:
            # the Chinese words only: the font has no Latin letters, and the size is in the table
            d.text((cx0 + 12, cy0 + 44), x["name"].split(" ")[0][:7], fill="#444444", font=cjk_small)
        centers.append((x, cx0 + bw - 18, cy0 + bh - 18, cx0 + bw + 4, cy0 - 18))
    image = _png(img)
    balloons = []
    for x, ax, ay, bx, by in centers:
        d.line((ax, ay, bx, by), fill="#333333", width=2)
        d.ellipse((bx - 18, by - 18, bx + 18, by + 18), fill="white", outline="#333333", width=3)
        t = str(x["no"])
        tw = d.textlength(t, font=small)
        d.text((bx - tw / 2, by - 12), t, fill="#111111", font=small)
        balloons.append({"part_id": x["part_id"], "x": bx / w, "y": by / h, "ax": ax / w, "ay": ay / h})
    return image, _png(img), balloons


def _png(img) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


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
            "model_pages": done["model"], "schematics": len(done["schematic"]), "names_open": m["names_open"]}
