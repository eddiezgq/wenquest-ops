"""Demo data (fictional company, real design): the 3D of the 蓝湾 lockstitch machine from WenQuest's WQ-LS design
(WenQuest round 138, G7.1). One STEP per part code in wqops/demo/manual/lockstitch/models/ and where each BOM line
sits in wqops/demo/manual/lockstitch/placements.json (assembly code -> part code -> placements, millimetres, machine
coordinates, so a whole-machine part sits at the identity).

    python demo/plm/wqls_models.py <WQ-LS parts with options T,E> <WQ-LS parts without options> <WQ-LS housing>

The three folders are what WenQuest's tools/wqls/cad/mech.py writes (WQ_OPT=T,E and WQ_OPT=) and its housing build;
each holds <part>.step. A part code made of several WQ-LS parts (the motor) is one STEP of all of them. A line used
more than once whose WQ-LS part is that many solids (two bearings) gets one STEP of the first solid and one placement
per solid. Needs build123d.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import build123d as bd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wqops.demo.machines import lockstitch as LS  # noqa: E402

OUT = ROOT / "wqops" / "demo" / "manual" / "lockstitch"
# a code used in several assemblies is drawn in this one only (the others are spares or not modelled)
PLACE_IN = {"ZC-6201ZZ": "WQ88-1700", "WQ88-1490": "WQ88-1400"}
IDENTITY = {"p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0]}


def solids(dirs, name):
    for d in dirs:
        f = Path(d) / f"{name}.step"
        if f.is_file():
            return bd.import_step(str(f)).solids()
    raise SystemExit(f"no {name}.step in {dirs}")


def main():
    dirs = sys.argv[1:4]
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    for f in (OUT / "models").glob("*.step"):
        f.unlink()
    uses = {}                                      # code -> how many per use (the BOM quantity where it is drawn)
    places = {}

    def walk(node):
        code, _name, _qty, _src, _unit, kids = node
        for k in kids:
            kc, kq = k[0], int(k[2])
            drawn = kc in LS.WQLS and PLACE_IN.get(kc, code) == code
            if drawn or (k[5] and kc not in places.get(code, {})):
                places.setdefault(code, {})[kc] = kq
            if drawn:
                uses[kc] = kq
            walk(k)
    walk(LS.TREE)
    for t in LS.OPTION_PARTS:
        walk(t)
    split = {}
    for code, names in LS.WQLS.items():
        q = uses.get(code, 1)
        if len(names) == 1 and q == 1:              # the file as WQ-LS wrote it (written again it is twice as big)
            src = next(Path(d) / f"{names[0]}.step" for d in dirs if (Path(d) / f"{names[0]}.step").is_file())
            shutil.copyfile(src, OUT / "models" / f"{code}.step")
            continue
        so = [s for n in names for s in solids(dirs, n)]
        if q > 1:
            # q copies side by side (a bearing is rings and balls): sort the solids along the direction they spread
            # most and cut into q equal groups
            assert len(so) % q == 0, f"{code}: {q} uses but {len(so)} solids"
            cs = [tuple(s.center()) for s in so]
            ax = max(range(3), key=lambda i: max(c[i] for c in cs) - min(c[i] for c in cs))
            so = [s for _, s in sorted(zip([c[ax] for c in cs], so, strict=True), key=lambda t: t[0])]
            n = len(so) // q
            groups = [bd.Compound(so[i * n:(i + 1) * n]) if n > 1 else so[i * n] for i in range(q)]
            c0 = groups[0].bounding_box().center()
            split[code] = [{"p": [round(v, 4) for v in tuple(g.bounding_box().center() - c0)],
                            "q": [0.0, 0.0, 0.0, 1.0]} for g in groups]
            shape = groups[0]
        else:
            shape = bd.Compound(so) if len(so) > 1 else so[0]
        bd.export_step(shape, str(OUT / "models" / f"{code}.step"))
    out = {}
    for asm, kids in places.items():
        for code, q in kids.items():
            out.setdefault(asm, {})[code] = split.get(code) or [IDENTITY] * q
    (OUT / "placements.json").write_text(json.dumps(out, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    n = len(list((OUT / "models").glob("*.step")))
    print(n, "STEP files,", sum(len(v) for v in out.values()), "placed lines")


if __name__ == "__main__":
    main()
