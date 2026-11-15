"""PLM 33d (WenQuest round 135; ADR-0031): the instruction manual of a machine. Eight fixed chapters in Chinese and
English; the AI drafts (a draft, its run kept, no number made up is the model's job, the person checks); a person
edits and confirms; editing a confirmed chapter makes it a draft again; only confirmed chapters go into an edition,
which is frozen, with a print and a screen PDF; pictures are confirmed exploded views of the machine or uploads."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_plm import (  # noqa: F401
    CASEY,
    PW,
    erp,
    fake,
    files_dir,
    manifest,
    u,
    world,
)
from tests.test_plm_explode import SVG, _asm
from tests.test_plm_manual import PNG, TODAY
from wqops.erp import ErpClient
from wqops.hub.app import create_app
from wqops.hub.plm import explode as EX
from wqops.hub.plm import parts as PT
from wqops.hub.plm import user_manual as UM


class Model:
    model = "test-model"

    def __init__(self, fig="ASM"):
        self.fig, self.asked = fig, []

    def configured(self):
        return True

    def create(self, system, messages, tools, max_tokens, tool_choice=None):
        self.asked.append(messages[0]["content"])
        return {"content": [{"type": "tool_use", "input": {
            "body_zh": "关电源再穿线。\n\n- 机针 〔待填 to be filled〕", "body_en": "Switch off before threading.",
            "figures": [{"code": self.fig, "caption": "针杆部件"}, {"code": "NOT-HERE"}]}}], "usage": {}}


def test_chapters_drafted_confirmed_and_an_edition(world, fake, erp):  # noqa: F811
    c = world
    bid, ids = _asm(c, erp)
    pid = ids["Asm"]
    code = PT.get(c, pid)["item_code"]
    with pytest.raises(PT.PlmError, match="machine with a BOM"):
        UM.view(c, ids["Bar"])
    v = UM.view(c, pid)
    assert [x["key"] for x in v["chapters"]] == list(UM.KEYS) and v["explodes"] == [] and v["confirmed"] == 0
    with pytest.raises(PT.PlmError, match="no chapter is confirmed"):
        UM.generate(c, u(c, CASEY), pid, today=TODAY)
    # an exploded view confirmed for the assembly: it can be a picture
    bar = PT.get(c, ids["Bar"])["item_code"]
    EX.from_freecad(c, "FreeCAD", code, {"moves": {}, "view": [-1, -1, 0.8],
                                         "balloons": [{"code": bar, "no": 1, "x": 0.6, "y": 0.4}]}, SVG, png=PNG)
    EX.confirm(c, u(c, CASEY), bid)
    assert [e["code"] for e in UM.view(c, pid)["explodes"]] == [code]
    # the AI drafts: its text a draft, only pictures from the list kept, the run kept
    with pytest.raises(PT.PlmError, match="no AI here"):
        UM.draft(c, u(c, CASEY), pid, "threading", None, today=TODAY)
    m = Model(code)
    v = UM.draft(c, u(c, CASEY), pid, "threading", m, today=TODAY)
    ch = next(x for x in v["chapters"] if x["key"] == "threading")
    assert ch["state"] == "draft" and ch["drafted_by"] == "AI (test-model)" and "待填" in ch["body_zh"]
    assert ch["figures"] == [{"kind": "explode", "code": code, "caption": "针杆部件"}]
    assert code in m.asked[0] and "针杆" in m.asked[0]                 # it is given the BOM
    run = c.execute("select kind from ai_runs where id = %s", (ch["ai_run"],)).fetchone()
    assert run["kind"] == "plm-manual"
    # a person writes, confirms; an edit makes it a draft again
    with pytest.raises(PT.PlmError, match="Chinese and English first"):
        UM.confirm(c, u(c, CASEY), pid, "safety")
    with pytest.raises(PT.PlmError, match="exploded view of an assembly"):
        UM.save(c, u(c, CASEY), pid, "safety", {"body_zh": "x", "body_en": "y", "figures": [{"kind": "explode",
                                                                                              "code": "OTHER"}]})
    with pytest.raises(KeyError):
        UM.save(c, u(c, CASEY), pid, "nope", {})
    UM.save(c, u(c, CASEY), pid, "safety", {"body_zh": "注意安全。", "body_en": "Be careful."})
    UM.confirm(c, u(c, CASEY), pid, "safety")
    UM.confirm(c, u(c, CASEY), pid, "threading")
    v = UM.save(c, u(c, CASEY), pid, "threading", {"body_zh": ch["body_zh"], "body_en": "Switch the power off.",
                                                  "figures": ch["figures"]})
    assert v["confirmed"] == 1
    fig = UM.upload(c, u(c, CASEY), pid, "mine.png", PNG)
    with pytest.raises(PT.PlmError, match="PNG or JPG"):
        UM.upload(c, u(c, CASEY), pid, "x.gif", b"GIF89a")
    UM.save(c, u(c, CASEY), pid, "threading", {"body_zh": ch["body_zh"], "body_en": "Switch the power off.",
                                              "figures": [*ch["figures"], fig]})
    UM.confirm(c, u(c, CASEY), pid, "threading")
    assert UM.uploaded(c, pid, fig["sha"]) == PNG
    # the edition: the two confirmed chapters, both PDFs, frozen
    r = UM.generate(c, u(c, CASEY), pid, today=TODAY)
    assert (r["edition"], r["chapters"], r["missing"]) == (1, 2, 6)
    for kind in ("screen", "print"):
        name, pdf = UM.pdf(c, r["id"], kind)
        assert pdf.startswith(b"%PDF") and b"Helvetica" not in pdf and name.startswith(code)
    with pytest.raises(psycopg.errors.RaiseException, match="kept as it was made"):
        c.execute("update plm_um_editions set edition = 9")
    assert UM.view(c, pid)["editions"][0]["chapters"] == 2


def test_user_manual_api(world, fake, erp, db_url):  # noqa: F811
    c = world
    _bid, ids = _asm(c, erp)
    pid = ids["Asm"]
    with TestClient(create_app({}, lambda: (manifest(), "ok"), db_url=db_url,
                               erp=ErpClient("http://erp", transport=fake.transport()))) as cl:
        assert cl.post("/api/login", json={"email": CASEY, "password": PW}).status_code == 200
        v = cl.get(f"/api/plm/user-manual/{pid}").json()
        assert len(v["chapters"]) == 8 and v["can_edit"]
        r = cl.put(f"/api/plm/user-manual/{pid}/chapters/specs", json={"body_zh": "参数", "body_en": "Specs"})
        assert r.status_code == 200
        assert cl.post(f"/api/plm/user-manual/{pid}/chapters/specs/confirm").json()["confirmed"] == 1
        fig = cl.post(f"/api/plm/user-manual/{pid}/pictures", files={"file": ("a.png", PNG)}).json()
        assert cl.get(f"/api/plm/user-manual/{pid}/pictures/{fig['sha']}").status_code == 404     # not in a chapter
        v = cl.post(f"/api/plm/user-manual/{pid}/editions").json()
        eid = v["editions"][0]["id"]
        r = cl.get(f"/api/plm/user-manual/editions/{eid}/pdf?kind=print")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert cl.get(f"/api/plm/user-manual/{pid}/chapters/nope/confirm").status_code in (404, 405)
