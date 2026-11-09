"""The parts manual as a PDF (PLM step 27c, WenQuest round 124): A4 landscape; a cover with the machine, edition and
date, contents by assembly, then one page per assembly: its exploded view on top, the table of parts below
(No., part number, name in Chinese and English, quantity, see page). ReportLab (BSD); Chinese with Droid Sans
Fallback (Apache-2.0), installed in the hub image; without it the PDF still comes out, Chinese as boxes."""

from __future__ import annotations

import datetime as dt
import io
import os
import re
from collections.abc import Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_FILES = (os.environ.get("WQO_CJK_FONT", ""), "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")
CHANGE = {"added": "新增 Added", "removed": "去掉 Removed", "quantity": "数量改变 Quantity changed",
          "new page": "新的一页 New page", "page removed": "去掉的一页 Page removed"}


def _font() -> str:
    for f in FONT_FILES:
        if f and os.path.isfile(f):
            if "CJK" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("CJK", f))
            return "CJK"
    return "Helvetica"


CJK_RUN = re.compile(r"([\u2e80-\U0002ffff]+)")      # Chinese, Japanese, fullwidth signs: the Droid font


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs(s) -> list[tuple[bool, str]]:
    """The text cut into runs: (True, Chinese) for the CJK font, (False, the rest) for Helvetica. Droid Sans Fallback
    has no Latin letters or digits, so one font for both would lose the part numbers."""
    return [(n % 2 == 1, x) for n, x in enumerate(CJK_RUN.split(str(s or ""))) if x]


def _rich(s, font: str) -> str:
    """Paragraph markup for text that mixes Chinese and Latin; everything escaped."""
    if font == "Helvetica":
        return _esc(s)
    return "".join(f'<font name="{font}">{_esc(x)}</font>' if cjk else _esc(x) for cjk, x in _runs(s))


def _draw(c, font: str, size: float, at: tuple[float, float], text: str, *, right: bool = False) -> None:
    x, y = at
    runs = [(font if cjk and font != "Helvetica" else "Helvetica", t) for cjk, t in _runs(text)]
    if right:
        x -= sum(pdfmetrics.stringWidth(t, f, size) for f, t in runs)
    for f, t in runs:
        c.setFont(f, size)
        c.drawString(x, y, t)
        x += pdfmetrics.stringWidth(t, f, size)


def build(head: dict, pages: list[dict], changes: list[dict], *, picture: Callable[[str], bytes],
          today: dt.date) -> bytes:
    font = _font()
    st = {k: ParagraphStyle(k, fontName="Helvetica", fontSize=s, leading=s * 1.35) for k, s in
          (("title", 24), ("h", 14), ("p", 9.5), ("small", 8))}
    out = io.BytesIO()
    pw, ph = landscape(A4)
    margin = 12 * mm
    doc = SimpleDocTemplate(out, pagesize=(pw, ph), leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=14 * mm, title=f"{head['code']} parts manual", author="WenQuest PLM")
    width = pw - 2 * margin
    when = today.isoformat()

    def footer(c, d):
        c.saveState()
        c.setFillColor(colors.grey)
        _draw(c, font, 8, (margin, 7 * mm), f"{head['code']} · 配件手册 Parts Manual · 第 {head['edition']} 版 "
                                           f"Edition {head['edition']}")
        _draw(c, font, 8, (pw - margin, 7 * mm), str(d.page), right=True)
        c.restoreState()

    def para(text, style):
        return Paragraph(_rich(text, font), st[style])

    story = [Spacer(1, 40 * mm), para(head["name"], "title"), para(head.get("name_en") or "", "h"),
             Spacer(1, 6 * mm), para(f"配件手册 Parts Manual · {head['code']}", "h"),
             para(f"第 {head['edition']} 版 Edition {head['edition']} · {when}", "p"), Spacer(1, 10 * mm)]
    toc = [["节 Section", "部件 Assembly", "名称 Name", "版本 Rev."]]
    toc += [[str(n + 1), p["code"], f"{p['name']}  {p.get('name_en') or ''}", p["revision"]]
            for n, p in enumerate(pages)]
    story += [para("目录 Contents", "h"), _table(toc, font, width, [20 * mm, 32 * mm, None, 18 * mm]),
              PageBreak()]
    if changes:
        rows = [["部件 Assembly", "零件 Part", "名称 Name", "变化 Change", "原 Was", "现 Now"]]
        rows += [[c.get("page", ""), c.get("code", ""), c.get("name", ""), CHANGE.get(c["change"], c["change"]),
                  c.get("old", ""), c.get("new", "")] for c in changes]
        story += [para("与上一版相比 Changes from the previous edition", "h"),
                  _table(rows, font, width, [32 * mm, 32 * mm, None, 46 * mm, 16 * mm, 16 * mm])]
    else:
        story += [para("与上一版相比 Changes from the previous edition", "h"), para("第一版 First edition", "p")]
    story.append(PageBreak())
    pic_h = (ph - 2 * margin) * 0.55
    for n, p in enumerate(pages):
        story.append(Paragraph(_rich(f"{n + 1}. {p['code']}  {p['name']}  {p.get('name_en') or ''}", font)
                               + f"  <font size=8>(BOM {_esc(p['revision'])})</font>", st["h"]))
        pic = _picture(picture, p.get("picture"))
        if pic:
            iw, ih = ImageReader(io.BytesIO(pic)).getSize()
            s = min(width / iw, pic_h / ih)
            story.append(Image(io.BytesIO(pic), iw * s, ih * s))
        elif p.get("picture"):
            story.append(para("爆炸图无法读取 The exploded view could not be read", "small"))
        else:
            story.append(para("本页无爆炸图 No exploded view on this page", "small"))
        rows = [["序号 No.", "编码 Part No.", "名称 Name", "英文名 English", "数量 Qty", "备注 Note"]]
        for ln in p["lines"]:
            note = f"见第 {ln['page']} 节 See section {ln['page']}" if ln.get("page") else (ln.get("note") or "")
            rows.append([str(ln["no"]), ln["code"], ln["name"], ln.get("name_en") or "（英文名待确认 to be confirmed）",
                         f"{ln['qty']} {ln['uom']}", note])
        story += [Spacer(1, 3 * mm), _table(rows, font, width, [16 * mm, 32 * mm, None, None, 22 * mm, 40 * mm]),
                  PageBreak()]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def _picture(picture: Callable[[str], bytes], sha: str | None) -> bytes | None:
    """The picture's bytes when ReportLab can read them; a damaged file is noted on the page, not a failed manual."""
    if not sha:
        return None
    try:
        data = picture(sha)
        ImageReader(io.BytesIO(data)).getSize()
    except Exception:  # any unreadable image
        return None
    return data


def _table(rows: list[list[str]], font: str, width: float, cols: list) -> Table:
    fixed = sum(c for c in cols if c)
    free = [c for c in cols if not c]
    widths = [c or (width - fixed) / len(free) for c in cols]
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5)
    body = [[Paragraph(_rich(v, font), cell) for v in r] for r in rows]
    t = Table(body, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8bcc4")),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f3")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t
