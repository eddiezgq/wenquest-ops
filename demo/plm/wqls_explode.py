"""Demo data (fictional company, real design): the exploded views of the 蓝湾 lockstitch machine's assemblies, made
by the FreeCAD add-on's "Exploded view" without the FreeCAD window (WenQuest round 138, G7.1 33b; ADR-0030). One
page per assembly that has 3D: wqops/demo/manual/explode/<code>.json (moves and balloons by part code, the
direction of view), <code>.svg (the line drawing) and <code>.png (the same drawing as a picture, for the manual).

    freecadcmd -c "import sys; sys.argv=['x']; exec(open('demo/plm/wqls_explode.py', encoding='utf-8').read())"

Reads wqops/demo/manual/lockstitch/models/*.step and placements.json (demo/plm/wqls_models.py writes them) and the
BOM in wqops/demo/machines/lockstitch.py, the same lines and numbers the PLM shows. Needs FreeCAD 1.0+ (its Part,
TechDraw and Qt with SVG).
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(os.environ.get("WQO_ROOT") or Path.cwd()).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "freecad" / "WenQuestPLM"))
import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import wqplm_explode as X  # noqa: E402

from wqops.demo.machines import lockstitch as LS  # noqa: E402

MAN = ROOT / "wqops" / "demo" / "manual"
OUT = MAN / "explode"


def nodes():
    out = {}

    def walk(n):
        out.setdefault(n[0], n)
        for k in n[5]:
            walk(k)
    walk(LS.TREE)
    for t in LS.OPTION_PARTS:
        walk(t)
    return out


def main():
    places = json.loads((MAN / "lockstitch" / "placements.json").read_text(encoding="utf-8"))
    tree = nodes()
    cache = {}

    def model(code):
        if code not in cache:
            f = MAN / "lockstitch" / "models" / f"{code}.step"
            cache[code] = Part.read(str(f)) if f.is_file() else None
        return cache[code]

    def shapes(code, asm, pl0, depth=0):
        """Every use of a line of ``asm`` in the frame of the page's assembly; a sub-assembly through its own lines."""
        out = []
        for pl in places.get(asm, {}).get(code) or []:
            m = pl0.multiply(App.Placement(App.Vector(*pl["p"]), App.Rotation(*pl["q"])))
            s = model(code)
            if s is not None:
                t = s.copy()
                t.Placement = m.multiply(t.Placement)
                out.append(t)
            elif code in places and depth < 6:
                for k in tree[code][5]:
                    out += shapes(k[0], code, m, depth + 1)
        return out

    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        f.unlink()
    made = []
    for asm in sorted(places):
        items = []
        for no, k in enumerate(tree[asm][5], start=1):
            code = k[0]
            std = LS.STD.get(code)
            sh = shapes(code, asm, App.Placement())
            items.append({"code": code, "no": no, "shapes": sh, "follow": bool(std and "轴承" in std[0]),
                          "std": bool(std and "轴承" not in std[0])})
        if sum(1 for it in items if it["shapes"] and not it["std"]) < 2:
            continue
        pg = X.page(items)
        (OUT / f"{asm}.svg").write_text(pg.pop("svg"), encoding="utf-8")
        (OUT / f"{asm}.png").write_bytes(X.png((OUT / f"{asm}.svg").read_text(encoding="utf-8"), scale=1))
        pg["moves"] = {c: list(v) for c, v in pg["moves"].items()}
        (OUT / f"{asm}.json").write_text(json.dumps({"code": asm, **pg}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
        made.append(asm)
        print(asm, len(pg["balloons"]), "balloons", flush=True)
    print(len(made), "pages")


main()
