"""演示（虚构）：零件的三维和它们在每张 BOM 里的位置（第 135 轮 33a）。

``part(asm, code, shape)``：一个只装一处的零件，三维直接画在整机坐标里，位置就是“原地”。
``lib_part(code, shape)`` + ``at(asm, code, pos, axis, angle)``：画在原点、装好几处的零件（标准件、成对的零件），
每装一处给一个位置。所有部件的坐标都是整机坐标，所以 BOM 里子部件那一行的位置也是“原地”。
"""
from __future__ import annotations

from collections import defaultdict

import FreeCAD as App
from lib import Z, vec

SHAPES: dict = {}                                        # code -> Part.Shape (local)
PLACES: dict = defaultdict(lambda: defaultdict(list))    # assembly code -> part code -> [placement]
IDENT = {"p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0]}


def part(asm: str, code: str, shape, n: int = 1) -> None:
    if code in SHAPES:
        raise ValueError(f"{code} drawn twice")
    SHAPES[code] = shape
    PLACES[asm][code] += [IDENT] * n


def lib_part(code: str, shape) -> None:
    if code not in SHAPES:
        SHAPES[code] = shape


def at(asm: str, code: str, pos, axis=Z, angle: float = 0.0) -> None:
    if code not in SHAPES:
        raise KeyError(f"{code} has no shape yet")
    rot = App.Rotation(App.Vector(0, 0, 1), vec(axis).normalize()).multiply(App.Rotation(App.Vector(0, 0, 1), angle))
    p = vec(pos)
    PLACES[asm][code].append({"p": [round(p.x, 3), round(p.y, 3), round(p.z, 3)],
                              "q": [round(c, 7) for c in rot.Q]})


def sub(asm: str, child: str, n: int = 1) -> None:
    """A sub-assembly line: it sits where it is (its parts are drawn in machine coordinates)."""
    PLACES[asm][child] += [IDENT] * n
