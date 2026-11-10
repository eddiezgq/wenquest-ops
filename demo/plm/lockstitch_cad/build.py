"""演示（虚构）：在 FreeCAD 里生成 WQ-8800D 平缝机全部零件的三维和装配位置（第 135 轮 33a）。

    WQ_OUT=<目录> freecadcmd -c "exec(open('demo/plm/lockstitch_cad/build.py').read())"

写出 <目录>/models/<编码>.step（每个零件一份，零件自己的坐标）和 <目录>/placements.json
（{部件编码: {零件编码: [{p, q}, ...]}}，每装一个一项）。默认目录 wqops/demo/manual/lockstitch/。
WQ_MESH=1 时另写 <目录>/../preview.json（看效果用的网格，不进仓库）。
"""
import json
import os
import sys

HERE = os.path.join(os.getcwd(), "demo", "plm", "lockstitch_cad")
sys.path[:0] = [HERE, os.getcwd()]

import FreeCAD as App  # noqa: E402
import reg  # noqa: E402
import stdparts  # noqa: E402

from wqops.demo.machines import lockstitch as LS  # noqa: E402

OUT = os.environ.get("WQ_OUT") or os.path.join(os.getcwd(), "wqops", "demo", "manual", "lockstitch")

stdparts.ensure_all(LS.STD)
import head_a  # noqa: E402

head_a.all_()
for mod in ("head_b", "head_c", "rest"):
    try:
        __import__(mod).all_()
    except ModuleNotFoundError as exc:
        if exc.name != mod:
            raise
        print("not yet:", mod)


def tree_lines(node, out):
    code, _name, _qty, _src, _unit, kids = node
    if kids:
        out[code] = {k[0]: k[2] for k in kids}
        for k in kids:
            tree_lines(k, out)
    return out


lines = {}
for t in (LS.TREE, *LS.OPTION_PARTS):
    tree_lines(t, lines)

# every BOM line drawn the number of times it is used; nothing drawn that is not in the BOM
problems = []
for asm, kids in lines.items():
    for code, qty in kids.items():
        if code in lines:
            continue
        got = len(reg.PLACES.get(asm, {}).get(code, []))
        if got != qty:
            problems.append(f"{asm} {code}: {got} placed, {qty} in the BOM")
for asm, kids in reg.PLACES.items():
    for code in kids:
        if code not in lines.get(asm, {}):
            problems.append(f"{asm} {code}: placed but not in the BOM")
print(f"{len(reg.SHAPES)} parts drawn; {len(problems)} problems")
for p in problems[:80]:
    print("  ", p)

used = {c for kids in lines.values() for c in kids if c not in lines} | {t[0] for t in LS.OPTION_PARTS if not t[5]}
os.makedirs(os.path.join(OUT, "models"), exist_ok=True)
for old in os.listdir(os.path.join(OUT, "models")):
    os.remove(os.path.join(OUT, "models", old))
for code, shape in sorted(reg.SHAPES.items()):
    if code in used:                                  # standard parts the lockstitch machine does not use: left out
        shape.exportStep(os.path.join(OUT, "models", f"{code}.step"))
places = {asm: {code: v for code, v in sorted(kids.items())} for asm, kids in sorted(reg.PLACES.items())}
for asm, kids in lines.items():                       # sub-assembly lines sit where they are
    for code, qty in kids.items():
        if code in lines:
            places.setdefault(asm, {})[code] = [reg.IDENT] * qty
with open(os.path.join(OUT, "placements.json"), "w", encoding="utf-8") as f:
    json.dump(places, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    f.write("\n")

if os.environ.get("WQ_MESH"):
    mesh = []
    want = os.environ.get("WQ_MESH_ASM", "")

    def under(asm):
        return [asm, *(c for c in lines.get(asm, {}) if c in lines for c in under(c))]

    asms = under(want) if want else list(places)
    for asm in asms:
        for code, pls in places.get(asm, {}).items():
            if code not in reg.SHAPES:
                continue
            for pl in pls:
                s = reg.SHAPES[code].copy()
                s.Placement = App.Placement(App.Vector(*pl["p"]), App.Rotation(*pl["q"])).multiply(s.Placement)
                v, f = s.tessellate(0.6)
                mesh.append({"code": code, "asm": asm, "v": [[round(c, 2) for c in (p.x, p.y, p.z)] for p in v],
                             "f": [list(t) for t in f]})
    with open(os.path.join(OUT, "..", "preview.json"), "w") as fp:
        json.dump(mesh, fp)
    print("mesh", len(mesh))
