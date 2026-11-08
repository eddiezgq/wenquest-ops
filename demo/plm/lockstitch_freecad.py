"""演示（虚构）：按 wqops/demo/machines/lockstitch.py 的结构在 FreeCAD 里搭一个平缝机装配模型，用来试“推送到 PLM”。

零件只是占位的简单形体（轴、销是圆柱，其他是方块），装配结构、编码（PartNumber 属性）和数量与旧 BOM 一致：
部件是 App::Part，同一个零件第二次及以后用到时是链接（App::Link），数量几就几个链接。

    freecadcmd -c "exec(open('demo/plm/lockstitch_freecad.py', encoding='utf-8').read())"    # 写出 平缝机-演示.FCStd
环境变量 WQ_OUT 可改输出路径。
"""
import os
import sys
import zlib

import FreeCAD as App

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    os.path.join(os.getcwd(), "demo", "plm")
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from wqops.demo.machines import lockstitch as L  # noqa: E402

doc = App.newDocument("Lockstitch")
doc.Label = L.MACHINE[1]
made = {}
n = [0]


def _tag(o, code):
    o.addProperty("App::PropertyString", "PartNumber", "WenQuest")
    o.PartNumber = code


def solid(code, name):
    h = zlib.crc32(code.encode())
    if ("轴" in name and "轴套" not in name and "轴承" not in name) or "销" in name:
        o = doc.addObject("Part::Cylinder", "P")
        o.Radius, o.Height = 2 + h % 8, 10 + h % 200
    else:
        o = doc.addObject("Part::Box", "P")
        o.Length, o.Width, o.Height = 4 + h % 60, 4 + (h >> 8) % 40, 2 + (h >> 16) % 30
    n[0] += 1
    o.Placement.Base = App.Vector((n[0] % 20) * 80, (n[0] // 20) * 80, 0)
    o.Label = name
    _tag(o, code)
    return o


def build(node, parent=None):
    code, name, qty, _src, _unit, kids = node
    if kids:
        a = doc.addObject("App::Part", "A")
        a.Label = name
        _tag(a, code)
        for k in kids:
            build(k, a)
        uses = [a]
    else:
        first = code not in made
        if first:
            made[code] = solid(code, name)
        uses = ([made[code]] if first else []) + [None] * (int(qty) - (1 if first else 0))
    if parent is None:
        return
    for u in uses:
        o = u
        if o is None:
            o = doc.addObject("App::Link", "L")
            o.setLink(made[code])
            o.Label = name
        parent.addObject(o)


build(L.TREE)
doc.recompute()
out = os.environ.get("WQ_OUT") or os.path.join(HERE, "平缝机-演示.FCStd")
doc.saveAs(out)
open(out + ".txt", "w", encoding="utf-8").write(f"{len(made)} solids, {len(doc.Objects)} objects\n")
