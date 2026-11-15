"""The parts manual as two PDFs (PLM 33c, WenQuest round 135; replaces round 124's single landscape PDF).

- **print**: A4 portrait trimmed (210 x 297 mm) with 3 mm bleed all round (216 x 303 mm media, TrimBox and BleedBox
  set, corner crop marks in the bleed), the exploded views as the FreeCAD add-on's line drawings, drawn as vectors.
- **screen**: A4 portrait, the colour pictures, clickable contents and "see section N", bookmarks.

Both: cover (machine, model, edition, date) -> contents -> changes from the edition before -> per assembly the
exploded view on a left page and the parts table on the right (more right-hand pages when the table is long; a
section always starts on a left page, a blank page in between when needed) -> back cover. Header: the machine;
footer: the page number outside, the edition inside. Chinese and English in one open font with both alphabets
(WenQuanYi Micro Hei, Apache-2.0), embedded (a subset)."""

from __future__ import annotations

import datetime as dt
import io
import os
import re
import xml.etree.ElementTree as ET  # noqa: S405 - only SVG the PLM checked (explode.clean_svg)
from collections.abc import Callable

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, Table, TableStyle

TRIM_W, TRIM_H, BLEED = 210 * mm, 297 * mm, 3 * mm
INNER, OUTER, TOP, BOTTOM = 20 * mm, 15 * mm, 20 * mm, 18 * mm
FONT_FILES = (os.environ.get("WQO_MANUAL_FONT", ""), "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")
INK, GREY, RULE, ZEBRA, BLUE = (colors.HexColor(x) for x in ("#111111", "#6b7078", "#c4c8cf", "#f2f3f5", "#0b4fae"))
CHANGE = {"added": "新增 Added", "removed": "去掉 Removed", "quantity": "数量改变 Quantity changed",
          "new page": "新的一页 New page", "page removed": "去掉的一页 Page removed"}


class ManualFontMissing(RuntimeError):
    pass


def font() -> str:
    """The one font for Chinese and Latin. Without it the manual is not made (boxes for Chinese are not a manual)."""
    for f in FONT_FILES:
        if f and os.path.isfile(f):
            if "WQ" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("WQ", f, subfontIndex=0))
            return "WQ"
    raise ManualFontMissing("the manual font is not installed (fonts-wqy-microhei)")


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- the line drawing: the FreeCAD add-on's SVG (polylines, lines, circles, text) drawn as PDF vectors

def _num(v, default=0.0) -> float:
    try:
        return float(re.sub(r"[a-z%]+$", "", str(v)))
    except (TypeError, ValueError):
        return default


def _colour(v):
    if not v or v == "none":
        return None
    try:
        if re.fullmatch(r"#[0-9a-fA-F]{3}", v):
            v = "#" + "".join(ch * 2 for ch in v[1:])
        return colors.HexColor(v) if v.startswith("#") else colors.toColor(v)
    except Exception:  # an unknown colour: drawn black, never a failed manual
        return INK


def _bounds(root) -> list[float] | None:
    """Where the part lines are (the balloons are placed again on the page), not the white page around them: x, y, w,
    h with a small margin."""
    xs, ys = [], []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "polyline":
            pts = [float(v) for v in re.split(r"[\s,]+", (el.get("points") or "").strip()) if v]
            xs += pts[0::2]
            ys += pts[1::2]
    if not xs:
        return None
    pad = 0.02 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    return [min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad]


def draw_svg(c, svg: bytes, x: float, y: float, w: float, h: float) -> None:
    """The drawing fitted into the box (x, y bottom left), kept in proportion, centred, room left round it for the
    balloons; the balloons a fixed size on paper (6.4 mm, 8.5 pt numbers) whatever the drawing's scale."""
    root = ET.fromstring(svg)  # noqa: S314 - checked on the way in: no entities, no DOCTYPE
    room = 11 * mm
    x, y, w, h = x + room, y + room, w - 2 * room, h - 2 * room
    vb = _bounds(root) or [_num(v) for v in (root.get("viewBox") or "0 0 100 100").replace(",", " ").split()]
    vw, vh = max(vb[2], 1e-6), max(vb[3], 1e-6)
    s = min(w / vw, h / vh)
    ox, oy = x + (w - vw * s) / 2, y + (h - vh * s) / 2

    def at(px, py):
        return ox + (px - vb[0]) * s, oy + (vh - (py - vb[1])) * s

    def walk(el, st):
        tag = el.tag.split("}")[-1]
        st = {**st, **{k: el.get(k) for k in ("stroke", "fill", "stroke-width", "font-size", "text-anchor")
                       if el.get(k) is not None}}
        stroke, fill = _colour(st.get("stroke")), _colour(st.get("fill"))
        c.setLineWidth(max(_num(st.get("stroke-width"), 1.0) * s, 0.35))
        if stroke:
            c.setStrokeColor(stroke)
        if fill:
            c.setFillColor(fill)
        if tag == "polyline":
            pts = [float(v) for v in re.split(r"[\s,]+", (el.get("points") or "").strip()) if v]
            if len(pts) >= 4 and stroke:
                p = c.beginPath()
                p.moveTo(*at(pts[0], pts[1]))
                for i in range(2, len(pts) - 1, 2):
                    p.lineTo(*at(pts[i], pts[i + 1]))
                c.drawPath(p, stroke=1, fill=0)
        elif tag == "line" and stroke:
            c.line(*at(_num(el.get("x1")), _num(el.get("y1"))), *at(_num(el.get("x2")), _num(el.get("y2"))))
        elif tag == "circle":
            cx, cy = at(_num(el.get("cx")), _num(el.get("cy")))
            c.circle(cx, cy, _num(el.get("r")) * s, stroke=1 if stroke else 0, fill=1 if fill else 0)
        elif tag == "text":
            size = _num(st.get("font-size"), 12) * s
            tx, ty = at(_num(el.get("x")), _num(el.get("y")))
            c.setFont(font(), size)
            c.setFillColor(fill or INK)
            draw = {"middle": c.drawCentredString, "end": c.drawRightString}.get(st.get("text-anchor"), c.drawString)
            draw(tx, ty, "".join(el.itertext()))
        for k in el:
            if tag != "text":
                walk(k, st)
    c.saveState()
    c.setLineCap(1)
    c.setLineJoin(1)
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "g" and el.get("font-size"):       # the balloons: placed again on the page
            _balloons(c, el, at, (x - room, y - room, w + 2 * room, h + 2 * room))
        elif tag != "rect":                          # the white background: the page is white already
            walk(el, {})
    c.restoreState()


def _balloons(c, g, at, box, r=3.2 * mm) -> None:
    """Each balloon: a leader from the part, the number in a circle; out from the part the way the add-on put it,
    at least 12 mm, then pushed apart where they would touch and kept inside the box."""
    kids = list(g)
    bl = []
    for i, el in enumerate(kids):
        if el.tag.split("}")[-1] != "line":
            continue
        txt = next((k for k in kids[i + 1:i + 5] if k.tag.split("}")[-1] == "text"), None)
        ax, ay = at(_num(el.get("x1")), _num(el.get("y1")))
        bx, by = at(_num(el.get("x2")), _num(el.get("y2")))
        dx, dy = bx - ax, by - ay
        d = (dx * dx + dy * dy) ** 0.5 or 1.0
        k = max(d, 12 * mm) / d
        bl.append([ax, ay, ax + dx * k, ay + dy * k, "".join(txt.itertext()) if txt is not None else "?"])
    x0, y0, w, h = box
    for _ in range(80):
        moved = False
        for i in range(len(bl)):
            for j in range(i + 1, len(bl)):
                dx, dy = bl[j][2] - bl[i][2], bl[j][3] - bl[i][3]
                d = (dx * dx + dy * dy) ** 0.5
                if d < 2.3 * r:
                    ux, uy = (dx / d, dy / d) if d > 1e-6 else (1.0, 0.0)
                    push = (2.3 * r - d) / 2
                    bl[i][2], bl[i][3] = bl[i][2] - ux * push, bl[i][3] - uy * push
                    bl[j][2], bl[j][3] = bl[j][2] + ux * push, bl[j][3] + uy * push
                    moved = True
        for b in bl:
            b[2] = min(max(b[2], x0 + r), x0 + w - r)
            b[3] = min(max(b[3], y0 + r), y0 + h - r)
        if not moved:
            break
    c.setLineWidth(0.4)
    c.setStrokeColor(INK)
    for ax, ay, bx, by, _n in bl:
        d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1.0
        c.line(ax, ay, bx - (bx - ax) / d * r, by - (by - ay) / d * r)
        c.setFillColor(INK)
        c.circle(ax, ay, 0.45 * mm, stroke=0, fill=1)
    for _ax, _ay, bx, by, n in bl:
        c.setFillColor(colors.white)
        c.circle(bx, by, r, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont(font(), 8.5)
        c.drawCentredString(bx, by - 3, n)


# ---- the book

class Book:
    """Pages drawn one by one; page n is a right-hand page when n is odd (the cover is page 1)."""

    def __init__(self, head: dict, *, kind: str, today: dt.date):
        self.head, self.kind, self.today = head, kind, today
        self.f = font()
        self.out = io.BytesIO()
        self.bleed = BLEED if kind == "print" else 0.0
        self.c = rl_canvas.Canvas(self.out, pagesize=(TRIM_W + 2 * self.bleed, TRIM_H + 2 * self.bleed),
                                  pageCompression=1, initialFontName=self.f, initialFontSize=9)
        self.c.setTitle(f"{head['code']} {head['name']} — 配件手册 Parts Manual, "
                        f"{'印刷版 print' if kind == 'print' else '电子版 screen'}")
        self.c.setAuthor("WenQuest PLM")
        self.n = 0
        self.st = {k: ParagraphStyle(k, fontName=self.f, bulletFontName=self.f, fontSize=s,
                                     leading=s * 1.32, textColor=INK) for k, s in
                   (("cell", 8.6), ("small", 8), ("p", 10), ("h", 15), ("title", 26))}

    # page frame (in trim coordinates: 0..TRIM_W, 0..TRIM_H)
    def start(self, *, plain: bool = False) -> None:
        if self.n:
            self.c.showPage()
        self.n += 1
        self.c.translate(self.bleed, self.bleed)
        if self.kind == "print":
            self._boxes()
            self._marks()
        if not plain:
            self._header_footer()

    @property
    def right(self) -> bool:
        return self.n % 2 == 1

    def box(self) -> tuple[float, float, float, float]:
        """The text area: x, y, w, h (inner margin on the spine side)."""
        left = INNER if self.right else OUTER
        return left, BOTTOM, TRIM_W - INNER - OUTER, TRIM_H - TOP - BOTTOM

    def _boxes(self) -> None:
        b = self.bleed
        self.c.setTrimBox((b, b, b + TRIM_W, b + TRIM_H))
        self.c.setBleedBox((0, 0, TRIM_W + 2 * b, TRIM_H + 2 * b))

    def _marks(self) -> None:
        """Crop marks at the four corners, in the bleed (cut away with it)."""
        c, b = self.c, self.bleed
        c.saveState()
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.25)
        for x, y in ((0, 0), (TRIM_W, 0), (0, TRIM_H), (TRIM_W, TRIM_H)):
            sx = -1 if x == 0 else 1
            sy = -1 if y == 0 else 1
            c.line(x + sx * 0.5 * mm, y, x + sx * b, y)
            c.line(x, y + sy * 0.5 * mm, x, y + sy * b)
        c.restoreState()

    def fit(self, s: str, size: float, width: float) -> str:
        """Cut to the width, with an ellipsis."""
        s = str(s or "")
        if pdfmetrics.stringWidth(s, self.f, size) <= width:
            return s
        while s and pdfmetrics.stringWidth(s + "…", self.f, size) > width:
            s = s[:-1]
        return s + "…"

    def text(self, at: tuple[float, float], s: str, size: float, *, colour=INK, anchor: str = "start") -> None:
        x, y = at
        self.c.setFont(self.f, size)
        self.c.setFillColor(colour)
        {"middle": self.c.drawCentredString, "end": self.c.drawRightString}.get(anchor, self.c.drawString)(x, y, s)

    def _header_footer(self) -> None:
        h, c = self.head, self.c
        x, _y, w, _h = self.box()
        out_x, in_x = (x + w, x) if self.right else (x, x + w)
        out_a, in_a = ("end", "start") if self.right else ("start", "end")
        ty = TRIM_H - TOP + 8 * mm
        self.text((out_x, ty), self.fit(h.get("short") or h["name"], 8, w * 0.6), 8, colour=GREY, anchor=out_a)
        self.text((in_x, ty), f"配件手册 Parts Manual · {h['code']}", 8, colour=GREY, anchor=in_a)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(x, ty - 2.5 * mm, x + w, ty - 2.5 * mm)
        fy = BOTTOM - 10 * mm
        self.text((out_x, fy), str(self.n), 9, anchor=out_a)
        self.text((in_x, fy), f"第 {h['edition']} 版 Edition {h['edition']} · {self.today.isoformat()}", 7.5,
                  colour=GREY, anchor=in_a)

    def para(self, s: str, style: str, *, rich: bool = False) -> Paragraph:
        return Paragraph(s if rich else _esc(s), self.st[style])

    def table(self, rows: list[list], widths: list[float], *, align_right: tuple[int, ...] = ()) -> Table:
        body = [[v if isinstance(v, Paragraph) else self.para(str(v), "cell") for v in r] for r in rows]
        t = Table(body, colWidths=widths, repeatRows=1)
        style = [("FONTNAME", (0, 0), (-1, -1), self.f), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(rows), 2)]
        style += [("ALIGN", (k, 0), (k, -1), "RIGHT") for k in align_right]
        t.setStyle(TableStyle(style))
        return t

    def flow(self, t: Table, title: Callable[[bool], None], top_gap: float = 14 * mm) -> None:
        """A table over as many pages as it takes, from the current page (each page gets the title, 'cont.')."""
        first = True
        while t is not None:
            x, y, w, h = self.box()
            title(not first)
            avail = h - top_gap
            parts = t.split(w, avail)
            if not parts:
                raise ValueError("a table row taller than a page")
            head = parts[0]
            _w, hh = head.wrapOn(self.c, w, avail)
            head.drawOn(self.c, x, y + h - top_gap - hh)
            t = parts[1] if len(parts) > 1 else None
            first = False
            if t is not None:
                self.start()

    def finish(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.out.getvalue()


def build(head: dict, pages: list[dict], changes: list[dict], *, kind: str, blob: Callable[[str], bytes],
          today: dt.date) -> bytes:
    """kind: print (line drawings, bleed) or screen (colour pictures, links). pages as manual._page makes them:
    code, name, name_en, revision, picture (sha), svg (sha), lines."""
    b = Book(head, kind=kind, today=today)
    _cover(b)
    _contents(b, pages)
    _changes(b, changes)
    for n, p in enumerate(pages, start=1):
        _section(b, n, p, blob)
    if b.n % 2 == 1:                                    # the back cover is a left-hand page
        b.start(plain=True)
    b.start(plain=True)
    _back(b)
    return b.finish()


def _cover(b: Book) -> None:
    b.start(plain=True)
    h, c = b.head, b.c
    c.setFillColor(colors.HexColor("#0f2a4a"))
    c.rect(-b.bleed, TRIM_H * 0.62, TRIM_W + 2 * b.bleed, TRIM_H * 0.38 + b.bleed, stroke=0, fill=1)
    b.text((OUTER + 5 * mm, TRIM_H - 40 * mm), "配件手册", 30, colour=colors.white)
    b.text((OUTER + 5 * mm, TRIM_H - 52 * mm), "Parts Manual", 22, colour=colors.HexColor("#c9d6e8"))
    y = TRIM_H * 0.62 - 22 * mm
    cw = TRIM_W - 2 * OUTER - 10 * mm
    for txt, size, col in ((h["name"], 20, INK), (h.get("name_en") or "", 12, GREY)):
        para = Paragraph(_esc(txt), ParagraphStyle("c", fontName=b.f, bulletFontName=b.f, fontSize=size, leading=size * 1.3,
                                                     textColor=col))
        _w, ph = para.wrapOn(c, cw, 60 * mm)
        para.drawOn(c, OUTER + 5 * mm, y - ph)
        y -= ph + 4 * mm
    y -= 4 * mm
    rows = [("型号 Model", h["code"]), ("版次 Edition", f"第 {h['edition']} 版 Edition {h['edition']}"),
            ("日期 Date", b.today.isoformat())]
    for i, (k, v) in enumerate(rows):
        yy = y - 6 * mm - i * 9 * mm
        b.text((OUTER + 5 * mm, yy), k, 10, colour=GREY)
        b.text((OUTER + 45 * mm, yy), v, 11)
    b.text((OUTER + 5 * mm, BOTTOM), h.get("maker") or "", 9, colour=GREY)
    if b.kind == "screen":
        b.c.bookmarkPage("cover")
        b.c.addOutlineEntry("封面 Cover", "cover", 0)


def _contents(b: Book, pages: list[dict]) -> None:
    b.start()
    if b.kind == "screen":
        b.c.bookmarkPage("contents")
        b.c.addOutlineEntry("目录 Contents", "contents", 0)
    w = b.box()[2]
    rows = [["节 Section", "部件 Assembly", "名称 Name", "BOM"]]
    for n, p in enumerate(pages, start=1):
        name = f"{_esc(p['name'])}<br/><font color='#6b7078'>{_esc(p.get('name_en') or '')}</font>"
        if b.kind == "screen":
            name = f'<link destination="sec{n}" color="#0b4fae">{name}</link>'
        rows.append([str(n), p["code"], b.para(name, "cell", rich=True), p["revision"]])
    t = b.table(rows, [16 * mm, 30 * mm, w - 62 * mm, 16 * mm])

    def title(cont):
        x0, y0, _w0, h0 = b.box()
        b.text((x0, y0 + h0 - 7 * mm), "目录 Contents" + ("（续 cont.）" if cont else ""), 15)
    b.flow(t, title)


def _changes(b: Book, changes: list[dict]) -> None:
    b.start()
    x, y, w, h = b.box()
    b.text((x, y + h - 7 * mm), "与上一版相比 Changes from the previous edition", 15)
    if not changes:
        b.text((x, y + h - 18 * mm), "第一版 First edition", 10, colour=GREY)
        return
    rows = [["部件 Assembly", "零件 Part", "名称 Name", "变化 Change", "原 Was", "现 Now"]]
    rows += [[c.get("page", ""), c.get("code", ""), c.get("name", ""), CHANGE.get(c["change"], c["change"]),
              c.get("old", ""), c.get("new", "")] for c in changes]
    t = b.table(rows, [28 * mm, 28 * mm, w - 120 * mm, 40 * mm, 12 * mm, 12 * mm])

    def title(cont):
        x0, y0, _w0, h0 = b.box()
        b.text((x0, y0 + h0 - 7 * mm), "与上一版相比 Changes from the previous edition" + ("（续 cont.）" if cont else ""),
               15)
    b.flow(t, title)


def _section(b: Book, n: int, p: dict, blob: Callable[[str], bytes]) -> None:
    """The exploded view on a left page, the table from the right page on."""
    b.start()
    if b.right:                                         # a section opens on a left page
        b.text((TRIM_W / 2, TRIM_H / 2), "本页空白 This page is intentionally blank", 9, colour=GREY,
               anchor="middle")
        b.start()
    if b.kind == "screen":
        b.c.bookmarkPage(f"sec{n}")
        b.c.addOutlineEntry(f"{n}  {p['code']}  {p['name']}", f"sec{n}", 0)
    x, y, w, h = b.box()
    b.text((x, y + h - 7 * mm), f"{n}", 22, colour=BLUE)
    b.text((x + 14 * mm, y + h - 4 * mm), f"{p['code']}  {p['name']}", 13)
    b.text((x + 14 * mm, y + h - 10 * mm), f"{p.get('name_en') or ''}   BOM {p['revision']}", 9, colour=GREY)
    pic_box = (x, y, w, h - 18 * mm)
    drawn = False
    try:
        colour = p.get("picture") if p.get("picture") and p.get("picture") != p.get("line") else None
        if p.get("svg") and (b.kind == "print" or not colour):     # screen: the colour picture when there is one
            draw_svg(b.c, blob(p["svg"]), *pic_box)
            drawn = True
        elif p.get("picture"):
            data = blob(colour or p["picture"])
            img = ImageReader(io.BytesIO(data))
            iw, ih = img.getSize()
            s = min(pic_box[2] / iw, pic_box[3] / ih)
            b.c.drawImage(img, x + (w - iw * s) / 2, y + (pic_box[3] - ih * s) / 2, iw * s, ih * s)
            drawn = True
    except Exception:  # a damaged picture is noted on the page, never a failed manual
        drawn = False
    if not drawn:
        b.c.setStrokeColor(RULE)
        b.c.setDash(3, 3)
        b.c.rect(x, y + pic_box[3] * 0.3, w, pic_box[3] * 0.4)
        b.c.setDash()
        b.text((x + w / 2, y + pic_box[3] / 2), "本部件暂无爆炸图 No exploded view for this assembly yet", 10,
               colour=GREY, anchor="middle")
    b.start()
    rows = [["序号<br/>No.", "编码<br/>Part No.", "名称 Name", "数量<br/>Qty", "备注 Note"]]
    rows = [[b.para(v, "cell", rich=True) for v in rows[0]]]
    for ln in p["lines"]:
        en = ln.get("name_en") or "（英文名待确认 to be confirmed）"
        name = b.para(f"{_esc(ln['name'])}<br/><font color='#6b7078'>{_esc(en)}</font>", "cell", rich=True)
        if ln.get("page"):
            see = f"见第 {ln['page']} 节<br/>See section {ln['page']}"
            note = b.para(f'<link destination="sec{ln["page"]}" color="#0b4fae">{see}</link>' if b.kind == "screen"
                          else see, "cell", rich=True)
        else:
            note = ln.get("note") or ""
        rows.append([str(ln["no"]), ln["code"], name, f"{ln['qty']} {ln['uom']}", note])
    w = b.box()[2]
    t = b.table(rows, [13 * mm, 30 * mm, w - 13 * mm - 30 * mm - 20 * mm - 32 * mm, 20 * mm, 32 * mm],
                align_right=(3,))

    def title(cont):
        x0, y0, _w0, h0 = b.box()
        b.text((x0, y0 + h0 - 7 * mm), f"{n}  {p['code']}  {p['name']}" + ("（续 cont.）" if cont else ""), 11)
    b.flow(t, title, top_gap=11 * mm)


def _back(b: Book) -> None:
    h = b.head
    b.c.setFillColor(colors.HexColor("#0f2a4a"))
    b.c.rect(-b.bleed, -b.bleed, TRIM_W + 2 * b.bleed, 40 * mm + b.bleed, stroke=0, fill=1)
    b.text((OUTER, 22 * mm), f"{h['name']}  ·  {h['code']}", 10, colour=colors.white)
    b.text((OUTER, 15 * mm), f"配件手册 第 {h['edition']} 版 · Parts Manual, Edition {h['edition']} · "
                             f"{b.today.isoformat()}", 8, colour=colors.HexColor("#c9d6e8"))


def make(head: dict, pages: list[dict], changes: list[dict], *, blob: Callable[[str], bytes],
         today: dt.date) -> dict[str, bytes]:
    """Both PDFs."""
    return {k: build(head, pages, changes, kind=k, blob=blob, today=today) for k in ("print", "screen")}
