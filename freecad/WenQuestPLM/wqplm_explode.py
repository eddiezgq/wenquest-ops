"""WenQuest PLM add-on: "Exploded view" (WenQuest round 135, 33b; ADR-0030). For one assembly: pull the parts apart
(parts on the assembly's main axis along that axis, the others away from the middle; standard parts go with the part
they hold), place numbered balloons in BOM order, and draw it as a vector line drawing (isometric, visible lines
only, FreeCAD's hidden-line removal). Sent to the quality ERP the page waits there as "to confirm"; the colour
picture in the PLM is drawn from the same moves. Works without the FreeCAD window (batch).

items: [{"code": part code, "no": balloon number (the BOM line's), "shapes": [Part.Shape in the assembly frame, one
         per use], "follow": True for a standard part (a bearing: it moves with the nearest other part and is drawn),
         "std": True for a fastener (moves the same way; numbered in the table, not drawn)}]
"""
import math

VIEW = (-1.0, -1.0, 0.8)           # from the front left, a little above (x along the shaft, y to the back, z up)
W, H, MARGIN = 1600, 1100, 70       # the drawing, px; numbers and leaders fit in the margin


def _bb(shapes):
    import FreeCAD as App
    b = App.BoundBox()
    for s in shapes:
        b.add(s.BoundBox)
    return b


def _v(b):
    import FreeCAD as App
    return App.Vector(b.Center)


def _moved(b, m, grow=0.0):
    import FreeCAD as App
    return App.BoundBox(b.XMin + m.x - grow, b.YMin + m.y - grow, b.ZMin + m.z - grow,
                        b.XMax + m.x + grow, b.YMax + m.y + grow, b.ZMax + m.z + grow)


def _hits(a, b):
    return a.XMin < b.XMax and b.XMin < a.XMax and a.YMin < b.YMax and b.YMin < a.YMax and a.ZMin < b.ZMax and \
        b.ZMin < a.ZMax


def plan(items, factor=0.8):
    """moves {code: (dx, dy, dz)} in mm, the assembly frame. The biggest part (the housing, the shaft) stays; a part on
    its axis (when it is long) slides off along the axis, the others go straight out from its middle, each until it is
    clear of the biggest part and of the parts already placed, nearest first; standard parts go with the nearest
    part."""
    import FreeCAD as App
    drawn = [it for it in items if not (it.get("std") or it.get("follow")) and it["shapes"]]
    if not drawn:
        drawn = [it for it in items if not it.get("std") and it["shapes"]]
    if not drawn:
        return {}
    bbs = {it["code"]: _bb(it["shapes"]) for it in drawn}
    allb = _bb([s for it in drawn for s in it["shapes"]])
    size = max(allb.DiagonalLength, 1.0)
    gap = size * 0.035 * (0.5 + factor)
    base = max(drawn, key=lambda it: bbs[it["code"]].XLength * bbs[it["code"]].YLength * bbs[it["code"]].ZLength)
    bb0 = bbs[base["code"]]
    c0 = _v(bb0)
    ext = [bb0.XLength, bb0.YLength, bb0.ZLength]
    k = max(range(3), key=lambda i: ext[i])
    second = sorted(ext)[1]
    axis = App.Vector(*[1.0 if i == k else 0.0 for i in range(3)]) if ext[k] > 2.2 * max(second, 1e-6) else None
    moves, centres = {base["code"]: App.Vector()}, {base["code"]: c0}
    placed = [_moved(bb0, App.Vector(), gap)]
    rest = sorted((it for it in drawn if it is not base), key=lambda it: (_v(bbs[it["code"]]) - c0).Length)
    for it in rest:
        b = bbs[it["code"]]
        c = _v(b)
        centres[it["code"]] = c
        d = c - c0
        if axis is not None and (d - axis * d.dot(axis)).Length < 0.75 * second + 1.0:
            u = axis * (1.0 if d.dot(axis) >= 0 else -1.0)                     # on the shaft: slides off its end
        else:
            u = App.Vector(d) if d.Length > 1e-6 else App.Vector(0, 0, 1)
            u.normalize()
        t, step = 0.0, size * 0.01
        while t < 4 * size and any(_hits(_moved(b, u * t), q) for q in placed):
            t += step
        m = u * (t + gap if t > 0 else 0.0)
        moves[it["code"]] = m
        placed.append(_moved(b, m, gap / 2))
    for it in items:                                                    # standard parts: with the nearest part
        if it["code"] in moves or not it["shapes"]:
            continue
        c = _v(_bb(it["shapes"]))
        near = min(centres, key=lambda x: (centres[x] - c).Length)
        moves[it["code"]] = moves[near]
    return {k2: (round(v.x, 2), round(v.y, 2), round(v.z, 2)) for k2, v in moves.items()}


def _on(shape):
    """A point on the part for its balloon's leader: the middle of its biggest solid (a bounding box's middle may be
    empty space)."""
    so = shape.Solids or [shape]
    big = max(so, key=lambda x: x.Volume if x.Solids else 0.0)
    try:
        c = big.CenterOfMass
    except Exception:
        c = _v(big.BoundBox)
    return c


def _project(shape, d):
    """Visible edges of a shape seen along d (hard and outline lines)."""
    import TechDraw
    r = TechDraw.projectEx(shape, d)
    return [e for g in (r[0], r[3]) for e in (g.Edges if g else [])]


def _point(p, d):
    """Where a 3D point lands in the projection's 2D frame (the same one as the edges)."""
    import FreeCAD as App
    import Part
    import TechDraw
    e = TechDraw.project(Part.makeLine(p, p + App.Vector(0.01, 0.01, 0.01)), d)[0].Edges
    v = e[0].Vertexes[0].Point if e else App.Vector()
    return (v.x, v.y)


def _lines(edges, turn):
    """The visible edges as polylines in the picture plane, turned so the assembly's z points up."""
    cs, sn = math.cos(turn), math.sin(turn)
    polys = []
    for e in edges:
        try:
            pts = e.discretize(Deflection=0.05)
        except Exception as exc:        # an edge OCCT cannot cut into points: left out of the drawing
            print("wqplm_explode: edge left out:", exc)
            continue
        if len(pts) > 1:
            polys.append([(p.x * cs - p.y * sn, p.x * sn + p.y * cs) for p in pts])
    return polys


def _spread(bl, r=22):
    """Balloons [code, no, ax, ay, bx, by] pushed apart where they overlap, kept on the page."""
    for _ in range(60):
        moved = False
        for i in range(len(bl)):
            for j in range(i + 1, len(bl)):
                dx, dy = bl[j][4] - bl[i][4], bl[j][5] - bl[i][5]
                dist = math.hypot(dx, dy)
                if dist < 2 * r:
                    ux, uy = (dx / dist, dy / dist) if dist > 1e-6 else (1.0, 0.0)
                    push = (2 * r - dist) / 2
                    bl[i][4], bl[i][5] = bl[i][4] - ux * push, bl[i][5] - uy * push
                    bl[j][4], bl[j][5] = bl[j][4] + ux * push, bl[j][5] + uy * push
                    moved = True
        for b in bl:
            b[4], b[5] = min(max(b[4], r + 2), W - r - 2), min(max(b[5], r + 2), H - r - 2)
        if not moved:
            break
    return bl


def draw(items, moves, view=VIEW):
    """The line drawing (SVG text) and the balloons as fractions of the picture:
    [{"code", "no", "x", "y", "ax", "ay"}]."""
    import FreeCAD as App
    import Part
    d = App.Vector(*view)
    moved, anchors = [], {}
    for it in items:
        if it.get("std") or not it["shapes"]:
            continue
        m = App.Vector(*moves.get(it["code"], (0, 0, 0)))
        for sh in it["shapes"]:
            t = sh.copy()
            t.translate(m)
            moved.append(t)
        anchors[it["code"]] = (it["no"], _on(it["shapes"][0]) + m)
    if not moved:
        return "", []
    o2, z2 = _point(App.Vector(), d), _point(App.Vector(0, 0, 100), d)
    turn = math.pi / 2 - math.atan2(z2[1] - o2[1], z2[0] - o2[0])          # the assembly's z points up the page
    polys = _lines(_project(Part.makeCompound(moved), d), turn)
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = min((W - 2 * MARGIN) / max(x1 - x0, 1e-6), (H - 2 * MARGIN) / max(y1 - y0, 1e-6))
    ox, oy = (W - (x1 - x0) * s) / 2, (H - (y1 - y0) * s) / 2

    def px(x, y):                       # y up in the projection, down in SVG
        x, y = x * math.cos(turn) - y * math.sin(turn), x * math.sin(turn) + y * math.cos(turn)
        return (ox + (x - x0) * s, H - (oy + (y - y0) * s))

    def flat(x, y):
        return (ox + (x - x0) * s, H - (oy + (y - y0) * s))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           '<rect width="100%" height="100%" fill="#fff"/>',
           '<g fill="none" stroke="#111" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round">']
    for p in polys:
        q = " ".join(f"{a:.1f},{b:.1f}" for a, b in (flat(*xy) for xy in p))
        out.append(f'<polyline points="{q}"/>')
    out.append("</g>")
    bl = []                              # balloons: out from the middle of the picture, then pushed apart
    for code, (no, p) in sorted(anchors.items(), key=lambda t: t[1][0]):
        ax, ay = px(*_point(p, d))
        dx, dy = ax - W / 2, ay - H / 2
        n = math.hypot(dx, dy) or 1.0
        bl.append([code, no, ax, ay, ax + dx / n * 60, ay + dy / n * 60])
    _spread(bl)
    out.append('<g stroke="#0b4fae" stroke-width="1" fill="#fff" font-family="Arial, sans-serif" font-size="17" '
               'text-anchor="middle">')
    for _code, no, ax, ay, bx, by in bl:
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}"/><circle cx="{ax:.1f}" '
                   f'cy="{ay:.1f}" r="2" fill="#0b4fae"/><circle cx="{bx:.1f}" cy="{by:.1f}" r="16"/>'
                   f'<text x="{bx:.1f}" y="{by + 6:.1f}" fill="#0b4fae" stroke="none">{int(no)}</text>')
    out.append("</g></svg>")
    balloons = [{"code": c, "no": int(no), "x": round(bx / W, 4), "y": round(by / H, 4), "ax": round(ax / W, 4),
                 "ay": round(ay / H, 4)} for c, no, ax, ay, bx, by in bl]
    return "\n".join(out), balloons


def png(svg_text, scale=2):
    """The same drawing as a PNG (Qt's SVG renderer; offscreen works without a window)."""
    from PySide import QtCore, QtGui, QtSvg
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["wqplm"])     # batch: no window, a Qt still
    png.app = app
    r = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_text.encode("utf-8")))
    img = QtGui.QImage(W * scale, H * scale, QtGui.QImage.Format_ARGB32)
    img.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    r.render(p)
    p.end()
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def page(items, factor=0.8, view=VIEW):
    """Everything the quality ERP keeps for one assembly's page: moves by part code (mm, the assembly frame, the whole
    pull: the PLM adds none of its own), balloons by part code, the direction of view (assembly frame, towards the
    viewer; the PLM's colour picture looks the same way) and the line drawing."""
    mv = plan(items, factor)
    svg, balloons = draw(items, mv, view)
    return {"moves": mv, "balloons": balloons, "view": list(view), "svg": svg}


def from_document(asm, lines):
    """The items of an assembly (App::Part or Assembly) in the open document, matched to its BOM lines by part code
    (PartNumber / Code / WQCode, a link counts as what it links): {code: line} from the PLM. Returns (items, codes of
    children that are not on the BOM)."""
    import Part
    import wqplm_doc as D
    by = {x["code"]: x for x in lines}
    shapes, other = {}, []
    for c in D._kids(asm):
        t = c.LinkedObject if c.TypeId == "App::Link" and c.LinkedObject is not None else c
        code = D._code(c) or D._code(t)
        if not code:
            continue
        if code not in by:
            other.append(code)
            continue
        try:
            s = Part.getShape(c, "", needSubElement=False, refine=False, transform=True)
        except Exception as exc:        # nothing to draw for it: it is listed, not drawn
            print("wqplm_explode:", code, exc)
            continue
        if not s.isNull() and s.Volume > 0:
            shapes.setdefault(code, []).append(s)
    items = []
    for x in lines:
        cat = x.get("category") or ""
        items.append({"code": x["code"], "no": x["no"], "shapes": shapes.get(x["code"], []),
                      "std": not x.get("drawn", True), "follow": cat == "bearing"})
    return items, other


def make(asm, factor=0.8):
    """The button: ask the PLM for the assembly's lines, draw, send. Returns the server's answer and what was left
    out."""
    import wqplm_doc as D
    import wqplm_net as N
    code = D._code(asm)
    if not code:
        raise N.NetError("这个装配没有编码（属性 PartNumber / Code / WQCode）/ the assembly has no part code")
    info = N.explode_lines(code)
    items, other = from_document(asm, info["lines"])
    if sum(1 for it in items if it["shapes"] and not it["std"]) < 1:
        raise N.NetError("装配里的零件和 BOM 对不上编码 / no part of the assembly matches a BOM line by code")
    pg = page(items, factor)
    r = N.send_explode(code, pg, png(pg["svg"]))
    return {**r, "not_on_bom": other, "without_3d": [it["code"] for it in items if not it["shapes"]]}
