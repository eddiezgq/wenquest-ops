"""PLM step 27c (round 124): the parts manual. Made only from released BOMs; an edition is frozen when made (a
later BOM change needs a new edition, which lists the changes); a PDF; a read-only link for dealers shows the
pictures and tables of the newest edition, counts views, and once revoked shows nothing; never the 3D models."""

import datetime as dt
import io

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_plm import (  # noqa: F401
    CASEY,
    PW,
    approved_change,
    erp,
    fake,
    files_dir,
    manifest,
    part,
    released,
    u,
    world,
)
from tests.test_plm_explode import _asm
from wqops.erp import ErpClient
from wqops.hub.app import create_app
from wqops.hub.plm import boms as B
from wqops.hub.plm import catalog as CAT
from wqops.hub.plm import explode as EX
from wqops.hub.plm import manual as MAN
from wqops.hub.plm import parts as PT

TODAY = dt.date(2026, 11, 9)
_b = io.BytesIO()
Image.new("RGB", (40, 30), "white").save(_b, "PNG")
PNG = _b.getvalue()


def _release_all(c, erp, bid, ids, monkeypatch):  # noqa: F811
    monkeypatch.setattr(B, "_supplier", lambda _c, _code: True)
    for k in ("Bar", "Screw"):
        cat = CAT.get(PT.get(c, ids[k])["category"])
        PT.update(c, u(c, CASEY), ids[k], {"params": {f["key"]: "M4" if f.get("type") == "text" else 1
                                                      for f in cat["fields"] if f.get("required")}})
        PT.release(c, u(c, CASEY), ids[k], PW)
    PT.release(c, u(c, CASEY), ids["Asm"], PW)
    B.release(c, u(c, CASEY), bid, PW, erp)


def test_editions_pdf_and_links(world, fake, erp, monkeypatch, db_url):  # noqa: F811
    c = world
    bid, ids = _asm(c, erp)
    r = MAN.readiness(c, ids["Asm"])
    assert not r["ok"] and r["not_released"][0]["name"] == "针杆部件"
    with pytest.raises(PT.PlmError, match="not every BOM"):
        MAN.generate(c, u(c, CASEY), ids["Asm"], today=TODAY)
    _release_all(c, erp, bid, ids, monkeypatch)
    EX.save(c, u(c, CASEY), bid, {"kind": "model", "balloons": [{"part_id": ids["Bar"], "x": 0.7, "y": 0.3}]},
            snapshot=PNG)
    EX.set_name_en(c, u(c, CASEY), ids["Bar"], "Needle Bar", confirm=True)
    EX.set_name_en(c, u(c, CASEY), ids["Screw"], "Screw", confirm=False)          # a draft: not printed
    m = MAN.generate(c, u(c, CASEY), ids["Asm"], today=TODAY)
    assert m["edition"] == 1 and len(m["pages"]) == 1 and m["names_open"] == 2      # the screw and the assembly
    lines = {x["code"]: x for x in m["pages"][0]["lines"]}
    assert lines[PT.get(c, ids["Bar"])["item_code"]]["name_en"] == "Needle Bar"
    assert lines[PT.get(c, ids["Screw"])["item_code"]]["name_en"] == ""
    name, pdf = MAN.pdf(c, m["id"])
    assert pdf.startswith(b"%PDF") and name.endswith("-manual-1.pdf") and MAN.picture(c, m["id"], 1) == PNG
    name, pdf = MAN.pdf(c, m["id"], "print")
    assert pdf.startswith(b"%PDF") and name.endswith("-manual-1-print.pdf") and MAN.overview(c, ids["Asm"])[
        "editions"][0]["has_print"]
    with pytest.raises(psycopg.errors.RaiseException, match="kept as it was made"):
        c.execute("update plm_manuals set edition = 9")
    # a new BOM revision with 3 screws, released: edition 2 lists the change; edition 1 stays as it was
    cid = approved_change(c, parts=[(ids["Asm"], "bom")])
    b2 = B.start(c, u(c, CASEY), ids["Asm"], cid)["bom"]["id"]
    B.set_lines(c, u(c, CASEY), b2, [{"part_id": ids["Bar"], "qty": 1}, {"part_id": ids["Screw"], "qty": 3}])
    B.release(c, u(c, CASEY), b2, PW, erp)
    m2 = MAN.generate(c, u(c, CASEY), ids["Asm"], today=TODAY)
    assert m2["edition"] == 2 and [(x["change"], x["old"], x["new"]) for x in m2["changes"]] == [("quantity", "2", "3")]
    assert m2["pages"][0]["picture"] is None                       # the new revision has no saved picture yet
    assert MAN.get(c, m["id"])["pages"][0]["revision"] == "A"
    link = MAN.add_link(c, u(c, CASEY), ids["Asm"], "东莞经销商")
    with TestClient(create_app({}, lambda: (manifest(), "ok"), db_url=db_url,
                               erp=ErpClient("http://erp", transport=fake.transport()))) as cl:
        r = cl.get(f"/m/{link['token']}")
        assert r.status_code == 200 and "第 2 版" in r.text and "Needle Bar" in r.text and ".step" not in r.text
        assert cl.get(f"/m/{link['token']}/pdf").content.startswith(b"%PDF")
        assert cl.get("/m/not-a-token").status_code == 404
        MAN.revoke(c, u(c, CASEY), link["id"])
        r = cl.get(f"/m/{link['token']}")
        assert r.status_code == 410 and "作废" in r.text
        assert cl.get(f"/m/{link['token']}/pdf").status_code == 410
    v = MAN.overview(c, ids["Asm"])
    assert v["links"][0]["views"] == 1 and v["links"][0]["revoked_at"] and len(v["editions"]) == 2


def test_print_and_screen_pdfs():
    """33c: A4 portrait, print with 3 mm bleed (TrimBox, BleedBox), every font embedded, the line drawing as vectors
    with balloons; a section opens on a left page; the screen PDF has links and bookmarks."""
    import re

    from wqops.hub.plm import manual_print as MPR

    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1100"><rect width="100%" height="100%" '
           b'fill="#fff"/><g fill="none" stroke="#111" stroke-width="1.1"><polyline points="100,100 900,700 1500,'
           b'200"/></g><g stroke="#0b4fae" fill="#fff" font-size="17" text-anchor="middle"><line x1="900" y1="700" '
           b'x2="960" y2="760"/><circle cx="900" cy="700" r="2" fill="#0b4fae"/><circle cx="960" cy="760" r="16"/>'
           b'<text x="960" y="766" fill="#0b4fae" stroke="none">1</text></g></svg>')
    lines = [{"no": i, "code": f"WQ-{i:03d}", "name": "针杆", "name_en": "Needle bar", "qty": "1", "uom": "个",
              "page": 2 if i == 1 else None, "note": ""} for i in range(1, 60)]          # two right-hand pages
    pages = [{"code": "WQ-100", "name": "针杆部件", "name_en": "Needle bar assembly", "revision": "A",
              "picture": None, "svg": "s", "line": None, "lines": lines},
             {"code": "WQ-200", "name": "小部件", "name_en": "", "revision": "B", "picture": None, "svg": None,
              "line": None, "lines": lines[:3]}]
    head = {"code": "WQ-1", "name": "演示机（虚构）", "name_en": "Demo machine (fictional)", "edition": 1}
    out = MPR.make(head, pages, [], blob=lambda _sha: svg, today=TODAY)

    pr, sc = out["print"], out["screen"]
    assert pr.startswith(b"%PDF") and sc.startswith(b"%PDF")
    assert re.search(rb"/MediaBox \[ 0 0 612\.28\d* 858\.89\d* \]", pr)              # 216 x 303 mm
    assert b"/TrimBox [ 8.50" in pr and b"/BleedBox [ 0 0" in pr
    assert re.search(rb"/MediaBox \[ 0 0 595\.27\d* 841\.88\d* \]", sc)              # A4
    for pdf in (pr, sc):
        assert b"Helvetica" not in pdf and b"/FontFile2" in pdf                    # one font, embedded
    n = len(re.findall(rb"/Type /Page\b", pr))
    # cover, contents, changes, [blank], 1: view + 2 tables, [blank], 2: view + table, back cover on a left page
    assert n % 2 == 0 and n >= 10
    assert b"/Subtype /Image" not in pr                                          # lines drawn, not a picture
    assert b"/Outlines" in sc and b"/Link" in sc and b"/Outlines" not in pr
    with pytest.raises(MPR.ManualFontMissing):
        MPR.FONT_FILES, old = ("/no/such/font.ttf",), MPR.FONT_FILES
        try:
            from reportlab.pdfbase import pdfmetrics
            del pdfmetrics._fonts["WQ"]
            MPR.font()
        finally:
            MPR.FONT_FILES = old
