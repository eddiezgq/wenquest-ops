"""演示（虚构）：建模用的小工具，在 FreeCAD 里运行（第 135 轮 33a）。

坐标（整机，毫米）：X 沿主轴，正方向朝手轮；Y 朝后（操作者在 -Y 一侧）；Z 朝上；原点在针板上面、机针正下方。
台板上面也在 Z = 0。每个函数返回 Part.Shape，已经放在给定位置。工程近似：尺寸对、形状像，不做铸造筋和细小圆角。
"""
from __future__ import annotations

import itertools
import math

import FreeCAD as App
import Part

V = App.Vector
X, Y, Z = V(1, 0, 0), V(0, 1, 0), V(0, 0, 1)


def vec(p) -> App.Vector:
    return p if isinstance(p, App.Vector) else V(*p)


def place(shape: Part.Shape, pos=(0, 0, 0), axis=Z, angle: float = 0.0) -> Part.Shape:
    """A shape built along +Z at the origin, turned so +Z points along ``axis`` (then ``angle`` degrees about it) and
    moved to ``pos``."""
    s = shape.copy()
    if angle:
        s.rotate(V(0, 0, 0), Z, angle)
    a = vec(axis).normalize()
    if (a - Z).Length > 1e-9:
        if (a + Z).Length < 1e-9:
            s.rotate(V(0, 0, 0), X, 180)
        else:
            rot = App.Rotation(Z, a)
            s.Placement = App.Placement(V(0, 0, 0), rot).multiply(s.Placement)
    s.translate(vec(pos))
    return s


def cyl(r: float, h: float, base=(0, 0, 0), axis=Z) -> Part.Shape:
    return Part.makeCylinder(r, h, vec(base), vec(axis))


def tube(ro: float, ri: float, h: float, base=(0, 0, 0), axis=Z) -> Part.Shape:
    return cyl(ro, h, base, axis).cut(cyl(ri, h + 0.2, vec(base) - vec(axis).normalize() * 0.1, axis))


def box(p0, p1, r: float = 0.0) -> Part.Shape:
    """A box between two corners; ``r`` rounds its vertical edges."""
    a, b = vec(p0), vec(p1)
    lo = V(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z))
    s = Part.makeBox(abs(b.x - a.x), abs(b.y - a.y), abs(b.z - a.z), lo)
    if r > 0:
        try:
            s = s.makeFillet(r, [e for e in s.Edges if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1e-6])
        except Exception:
            pass
    return s


def rounded(shape: Part.Shape, r: float) -> Part.Shape:
    try:
        return shape.makeFillet(r, shape.Edges)
    except Exception:
        return shape


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def lever(circles, t: float, holes=(), origin=(0, 0, 0), u=X, v=Z, n=Y) -> Part.Shape:
    """A flat part (crank, link, lever, bracket) round the circles (a, b, radius) in the plane o + a·u + b·v, ``t``
    thick along n; ``holes`` (a, b, radius) go through it."""
    o, u, v, n = vec(origin), vec(u), vec(v), vec(n)
    pts = []
    for a, b, r in circles:
        for k in range(32):
            ang = 2 * math.pi * k / 32
            pts.append((round(a + r * math.cos(ang), 4), round(b + r * math.sin(ang), 4)))
    ring = [o + u * a + v * b for a, b in _hull(pts)]
    face = Part.Face(Part.makePolygon([*ring, ring[0]]))
    s = face.extrude(n * t)
    for a, b, r in holes:
        s = s.cut(cyl(r, t + 2, o + u * a + v * b - n * 1, n))
    return s


def shaft(segments, base=(0, 0, 0), axis=X, bore: float = 0.0) -> Part.Shape:
    """A stepped shaft: ``segments`` [(length, diameter), ...] from ``base`` along ``axis``."""
    a = vec(axis).normalize()
    at = vec(base)
    s = None
    for length, d in segments:
        c = cyl(d / 2, length, at, a)
        s = c if s is None else s.fuse(c)
        at = at + a * length
    s = s.removeSplitter()
    if bore:
        s = s.cut(cyl(bore / 2, sum(x[0] for x in segments) + 2, vec(base) - a, a))
    return s


def disc(r: float, t: float, base=(0, 0, 0), axis=X, bore: float = 0.0, offset=(0, 0)) -> Part.Shape:
    """A disc (eccentric, pulley, wheel) ``t`` thick; its centre may sit ``offset`` off the axis (an eccentric)."""
    a = vec(axis).normalize()
    side = a.cross(Z) if abs(a.z) < 0.9 else a.cross(X)
    side.normalize()
    up = a.cross(side)
    c = vec(base) + side * offset[0] + up * offset[1]
    s = cyl(r, t, c, a)
    if bore:
        s = s.cut(cyl(bore / 2, t + 2, vec(base) - a, a))
    return s


def spring(r: float, pitch: float, length: float, wire: float, base=(0, 0, 0), axis=Z) -> Part.Shape:
    """A helical spring of mean radius ``r``; drawn as stacked rings (quick, and reads as a spring in a drawing)."""
    turns = max(2, int(length / pitch))
    s = None
    for k in range(turns + 1):
        ring = Part.makeTorus(r, wire / 2, V(0, 0, k * length / turns))
        s = ring if s is None else s.fuse(ring)
    return place(s, base, axis)


def pulley(r: float, t: float, base=(0, 0, 0), axis=X, bore: float = 0.0, teeth: int = 0) -> Part.Shape:
    s = disc(r, t, base, axis, bore)
    a = vec(axis).normalize()
    flange = disc(r + 1.5, 1.2, base, axis).fuse(disc(r + 1.5, 1.2, vec(base) + a * (t - 1.2), axis))
    s = s.fuse(flange)
    if teeth:
        for k in range(teeth):
            ang = 360.0 * k / teeth
            g = place(Part.makeBox(1.6, 1.2, t - 2.4, V(-0.8, r - 1.0, 1.2)), (0, 0, 0), Z, ang)
            s = s.cut(place(g, base, axis))
    return s


# ---- standard parts, built at the origin along +Z (the head on z <= 0, the body down +Z ... see each)

INCH_SM = {"9/64": 3.57, "11/64": 4.37, "15/64": 5.95, "1/4": 6.35, "3/16": 4.76}


def screw(d: float, length: float, head: str = "cheese") -> Part.Shape:
    """A screw with its head on top at z = 0..h and the body down to z = -length: ``cheese`` (slotted, sewing machine
    SM screws), ``socket`` (hex socket cap, GB/T 70.1), ``set`` (headless, slotted)."""
    body = cyl(d / 2, length, (0, 0, -length))
    if head == "set":
        return body.cut(Part.makeBox(d * 0.2, d * 1.2, d * 0.4, V(-d * 0.1, -d * 0.6, -d * 0.4)))
    if head == "socket":
        hd, hh = 1.5 * d, d
        h = cyl(hd / 2, hh)
        hexa = Part.Face(Part.makePolygon([V(0.43 * d * math.cos(math.pi / 3 * k), 0.43 * d * math.sin(math.pi / 3 * k),
                                              hh - 0.5 * d) for k in range(7)])).extrude(V(0, 0, 0.6 * d))
        return body.fuse(h.cut(hexa))
    hd, hh = 1.7 * d, 0.65 * d
    h = rounded(cyl(hd / 2, hh), min(0.4, hh / 4))
    slot = Part.makeBox(hd + 1, d * 0.25, hh * 0.5, V(-(hd + 1) / 2, -d * 0.125, hh * 0.5))
    return body.fuse(h.cut(slot))


def nut(d: float) -> Part.Shape:
    s = 1.6 * d + 0.4 if d < 8 else 13.0
    m = 0.8 * d
    r = s / math.sqrt(3)
    hexa = Part.Face(Part.makePolygon([V(r * math.cos(math.pi / 3 * k), r * math.sin(math.pi / 3 * k), 0)
                                       for k in range(7)])).extrude(V(0, 0, m))
    return hexa.cut(cyl(d / 2, m + 1, (0, 0, -0.5)))


def washer(d: float, spring_: bool = False) -> Part.Shape:
    if spring_:
        w = tube(d / 2 + 0.5 + 0.8 * d * 0.25, d / 2 + 0.2, 0.25 * d + 0.3)
        return w.cut(Part.makeBox(0.6, d, d, V(-0.3, 0, -1)))
    return tube(1.0 * d + 0.2, d / 2 + 0.25, 0.15 * d + 0.3)


def eclip(d: float) -> Part.Shape:
    """An E-ring for a shaft of diameter ``d``."""
    ring = tube(d * 0.95, d * 0.38, 0.6 + d * 0.04)
    return ring.cut(Part.makeBox(d * 0.8, d * 2, 2, V(-d * 0.4, 0, -0.5)))


def bearing(d: float, D: float, B: float, needle: bool = False) -> Part.Shape:
    if needle:
        return tube(D / 2, d / 2, B)
    s = tube(D / 2, (D / 2 + d / 2) / 2 + 1, B).fuse(tube((D / 2 + d / 2) / 2 - 1, d / 2, B))
    return s.fuse(tube((D / 2 + d / 2) / 2 + 1, (D / 2 + d / 2) / 2 - 1, 0.6, (0, 0, 0.3)))


def pin(d: float, length: float) -> Part.Shape:
    return rounded(cyl(d / 2, length), min(0.3, d / 6))


def split_pin(d: float, length: float) -> Part.Shape:
    legs = cyl(d / 4, length, (-d / 4, 0, 0)).fuse(cyl(d / 4, length * 0.85, (d / 4, 0, 0)))
    eye = Part.makeTorus(d * 0.55, d / 4, V(0, 0, length), Y)
    return legs.fuse(eye)


def plug(d: float) -> Part.Shape:
    return cyl(d / 2 + 1.2, 1.5).fuse(cyl(d / 2, 4, (0, 0, -4)))


def oil_seal(d: float) -> Part.Shape:
    return tube(d / 2 + 5, d / 2, 7)


def oring(d: float, w: float = 1.5) -> Part.Shape:
    return Part.makeTorus(d / 2 + w / 2, w / 2)


def route(points, r: float) -> Part.Shape:
    """A hose, cable or wire through the points: straight runs with round joints."""
    pts = [vec(p) for p in points]
    s = Part.makeSphere(r, pts[0])
    for a, b in itertools.pairwise(pts):
        d = b - a
        if d.Length > 1e-6:
            s = s.fuse(cyl(r, d.Length, a, d)).fuse(Part.makeSphere(r, b))
    return s


def shell_box(p0, p1, wall: float, open_top: bool = True, r: float = 0.0) -> Part.Shape:
    """A tray or a box: the outside between two corners, ``wall`` thick, open at the top or closed."""
    a, b = vec(p0), vec(p1)
    lo = V(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z))
    hi = V(max(a.x, b.x), max(a.y, b.y), max(a.z, b.z))
    outer = box(lo, hi, r)
    top = hi.z + 1 if open_top else hi.z - wall
    return outer.cut(box(lo + V(wall, wall, wall), V(hi.x - wall, hi.y - wall, top), max(0.0, r - wall)))
