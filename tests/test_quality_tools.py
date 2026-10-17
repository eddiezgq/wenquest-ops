"""Quality tools, step 22a (ADR-0022): Pareto charts of failed readings, nonconformance reports, complaints and check
sheets; histograms beside capability; scatter plots of two characteristics on the same piece; check sheet forms kept
as made and tallies signed and append-only. Every bar names its records; a missing value is its own bar, never
dropped; what cannot be computed is unknown. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, approved, receipts, table, u
from tests.test_quality_data import business
from tests.test_recall import world  # noqa: F401 - the fixture
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app
from wqops.hub.quality import complaints as CMP
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q
from wqops.hub.quality import tools as TL
from wqops.hub.quality import tools_rules as TR

CHARS = [{"name": "Length", "kind": "measured", "lsl": 9.8, "usl": 10.2, "unit": "mm"},
         {"name": "Width", "kind": "measured", "lsl": 4.9, "usl": 5.1, "unit": "mm"},
         {"name": "Finish", "kind": "attribute"}]


def test_rules():
    bars = TR.pareto({"Scratch": 12, "Dent": 30, "Burr": 5, TR.NOT_RECORDED: 3, "Crack": 0})
    assert [b["key"] for b in bars] == ["Dent", "Scratch", "Burr", TR.NOT_RECORDED]   # zero left out
    assert bars[0]["share"] == 0.6 and bars[1]["cumulative"] == pytest.approx(0.84) and bars[-1]["cumulative"] == 1
    assert TR.vital_few(bars) == 2 and TR.pareto({}) == []
    assert [b["key"] for b in TR.pareto({"b": 2, "a": 2})] == ["a", "b"]                # ties by name
    h = TR.histogram([9.9, 10.0, 10.0, 10.1, 10.3, 9.7, 10.05, 9.95], 9.8, 10.2)
    assert sum(h["counts"]) == 8 and len(h["edges"]) == len(h["counts"]) + 1 and h["below"] == 1 and h["above"] == 1
    assert h["edges"][0] == 9.7 and h["edges"][-1] == 10.3 and TR.bins_for(8) == 5 and TR.bins_for(10_000) == 15
    one = TR.histogram([5.0, 5.0, 5.0])
    assert one["counts"] == [3] and one["below"] is None
    with pytest.raises(TR.ToolError, match="at least 2"):
        TR.histogram([1.0])
    fit = TR.correlation([(1, 2), (2, 4), (3, 6.1), (4, 7.9)])
    assert fit["r"] > 0.99 and fit["slope"] == pytest.approx(1.98) and "does not show which causes" in fit["note"]
    assert TR.correlation([(1, 2), (2, 3)])["r"] is None
    flat = TR.correlation([(1, 5), (2, 5), (3, 5)])
    assert flat["r"] is None and flat["note"].startswith("unknown")
    assert TR.correlation([(1, 3), (2, 2), (3, 1)])["note"].startswith("strong negative")


def lots(w):
    """Three incoming lots of BOLT-B from Gulf Fasteners: one good, two rejected."""
    table(w)
    approved(w)
    p = I.new_plan(w, JORDAN, "BOLT-B", 1.0, CHARS)
    I.enable_plan(w, u(w, DANA), p["id"], PW)
    out = []
    for i, (lengths, widths, finish) in enumerate((([10.0, 10.02, 9.98], [5.0, 5.01, 4.99], True),
                                                   ([10.3, 10.25, 10.0], [5.05, 5.04, 5.0], True),
                                                   ([10.0, 10.1, 10.0], [5.0, 5.02, 5.0], False))):
        ins = I.start(w, JORDAN, "BOLT-B", receipt=f"PR-{7 + i}")
        vals = [{"sample": k, "characteristic": "Length", "value": v} for k, v in enumerate(lengths, 1)]
        vals += [{"sample": k, "characteristic": "Width", "value": v} for k, v in enumerate(widths, 1)]
        vals += [{"sample": k, "characteristic": "Finish", "passed": finish} for k in (1, 2, 3)]
        I.enter(w, JORDAN, ins["id"], vals)
        I.sign(w, u(w, JORDAN), ins["id"], PW)
        out.append(I.decide(w, u(w, DANA), ins["id"], PW, "checked", today=AS_OF))
    return out


def test_pareto_from_records(world):  # noqa: F811
    w = world
    got = lots(w)
    assert [x["status"] for x in got] == ["released", "rejected", "rejected"]
    inc = TL.pareto_for(w, "incoming", "characteristic")
    assert [(b["key"], b["count"]) for b in inc["bars"]] == [("Finish", 3), ("Length", 2)]
    assert inc["records"] == 3 and inc["total"] == 5 and inc["vital_few"] == 2
    assert {r["name"] for r in inc["bars"][1]["records"]} == {got[1]["name"]}
    assert TL.pareto_for(w, "incoming", "supplier")["bars"][0]["key"] == "Gulf Fasteners"
    Q.create_ncr(w, JORDAN, title="Scratched housing", description="Seen at packing")       # no supplier
    ncr = TL.pareto_for(w, "ncr", "supplier")
    assert [(b["key"], b["count"]) for b in ncr["bars"]] == [("Gulf Fasteners", 2), (TR.NOT_RECORDED, 1)]
    assert "1 of 3 reports have no supplier recorded" in ncr["note"]
    assert TL.pareto_for(w, "ncr", "supplier", until="2000-01-01")["note"] == "Nothing to count in this period."
    for c in ("Bayline Electrical", "Bayline Electrical", "Coastal Retail"):
        CMP.create(w, JORDAN, {"received_on": AS_OF.isoformat(), "customer": c, "description": "Box arrived crushed"},
                   today=AS_OF)
    cm = TL.pareto_for(w, "complaints", "customer")
    assert [(b["key"], b["count"]) for b in cm["bars"]] == [("Bayline Electrical", 2), ("Coastal Retail", 1)]
    for src, by, msg in (("x", "item_code", "count one of"), ("ncr", "colour", "group nonconformance reports by"),
                         ("check_sheet", "category", "choose the check sheet form")):
        with pytest.raises(TL.ToolsError, match=msg):
            TL.pareto_for(w, src, by)
    with pytest.raises(TL.ToolsError, match="ends before it starts"):
        TL.pareto_for(w, "ncr", "supplier", since="2026-10-10", until="2026-10-01")
    assert "custom:" not in str(TL.options(w)["sources"]["ncr"]["by"])     # no company choice field yet


def test_histogram_and_scatter(world):  # noqa: F811
    w = world
    lots(w)
    h = TL.histogram_for(w, "incoming", "BOLT-B", "Length")
    assert h["enough_data"] and h["values"] == 9 and sum(h["histogram"]["counts"]) == 9
    assert h["histogram"]["above"] == 2 and h["histogram"]["below"] == 0 and h["histogram"]["LSL"] == 9.8
    assert h["capability"] is not None or h["capability_note"]
    assert TL.histogram_for(w, "incoming", "BOLT-B", "Finish")["enough_data"] is False
    s = TL.scatter_for(w, "incoming", "BOLT-B", "Length", "Width")
    assert len(s["points"]) == 9 and s["points"][0]["label"].endswith("sample 1")
    assert s["fit"]["r"] > 0.7 and s["fit"]["n"] == 9
    with pytest.raises(TL.ToolsError, match="two different"):
        TL.scatter_for(w, "incoming", "BOLT-B", "Length", "Length")
    with pytest.raises(TL.ToolsError, match="incoming or production"):
        TL.scatter_for(w, "erp", "BOLT-B", "Length", "Width")
    assert TL.scatter_for(w, "production", "WIDGET-A", "A", "B")["fit"]["r"] is None


def test_check_sheets(world):  # noqa: F811
    w = world
    f = TL.new_form(w, JORDAN, " Packing  defects ",
                    ["Crushed box", "Wrong label", " crushed BOX ", "", "Missing part"])
    assert f["name"] == "Packing defects" and f["categories"] == ["Crushed box", "Wrong label", "Missing part"]
    for bad, msg in (([], "at least one"), ("x", "list the categories"), (["not recorded"], "kept for missing")):
        with pytest.raises(TL.ToolsError, match=msg):
            TL.new_form(w, JORDAN, "Other", bad)
    with pytest.raises(TL.ToolsError, match="already a form"):
        TL.new_form(w, JORDAN, "packing defects", ["A"])
    me = u(w, JORDAN)
    s1 = TL.record(w, me, f["id"], {"counts": {"Crushed box": 7, "Wrong label": "2"}, "place": "Line 1"}, PW,
                   today=AS_OF)
    assert s1["name"] == "CS-00001" and s1["counts"] == {"Crushed box": 7, "Wrong label": 2, "Missing part": 0}
    assert s1["total"] == 9 and s1["on_date"] == AS_OF and s1["form"] == "Packing defects"
    TL.record(w, me, f["id"], {"counts": {"Wrong label": 1, "Missing part": 4}, "place": "Line 2",
                               "on_date": (AS_OF - dt.timedelta(days=1)).isoformat()}, PW, today=AS_OF)
    for data, msg in (({"counts": {"Dent": 1}}, "does not count Dent"), ({"counts": {"Wrong label": -1}}, "whole"),
                      ({"counts": {"Wrong label": True}}, "whole"), ({"counts": []}, "a count for each"),
                      ({"counts": {}, "on_date": "2099-01-01"}, "future")):
        with pytest.raises(TL.ToolsError, match=msg):
            TL.record(w, me, f["id"], data, PW, today=AS_OF)
    with pytest.raises(Q.SignatureError):
        TL.record(w, me, f["id"], {"counts": {}}, "wrong", today=AS_OF)
    p = TL.pareto_for(w, "check_sheet", "category", form_id=f["id"])
    assert [(b["key"], b["count"]) for b in p["bars"]] == [("Crushed box", 7), ("Missing part", 4), ("Wrong label", 3)]
    assert [(b["key"], b["count"]) for b in TL.pareto_for(w, "check_sheet", "place", form_id=f["id"])["bars"]] == \
        [("Line 1", 9), ("Line 2", 5)]
    assert len(TL.sheets(w, f["id"])) == 2 and len(TL.sheets(w)) == 2
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        w.execute("update check_sheets set total = 0")
    with pytest.raises(psycopg.errors.RaiseException, match="kept as made"):
        w.execute("update check_sheet_forms set categories = '{A}'")
    TL.retire_form(w, DANA, f["id"])
    with pytest.raises(TL.ToolsError, match="retired"):
        TL.record(w, me, f["id"], {"counts": {}}, PW, today=AS_OF)
    assert w.execute("select meaning from signatures where kind = 'check_sheet' order by id").fetchone()["meaning"] \
        == "Check sheet recorded (9 counted)"


def test_tools_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login("lee@demo.example")
    assert c.get("/api/quality/tools/options").status_code == 200                     # charts: quality:view
    assert c.post("/api/quality/check-sheets/forms", json={"name": "S", "categories": ["A"]}).status_code == 403
    login(JORDAN)
    opts = c.get("/api/quality/tools/options").json()
    assert set(opts["sources"]) == {"ncr", "incoming", "complaints", "check_sheet"} and opts["forms"] == []
    form = c.post("/api/quality/check-sheets/forms", json={"name": "Visual", "categories": ["Scratch", "Dent"]})
    assert form.status_code == 201
    fid = form.json()["id"]
    r = c.post("/api/quality/check-sheets", json={"form_id": fid, "counts": {"Scratch": 3}, "password": PW})
    assert r.status_code == 201 and r.json()["total"] == 3
    assert c.post("/api/quality/check-sheets", json={"form_id": "x", "counts": {}}).status_code == 400
    assert c.post("/api/quality/check-sheets", json={"form_id": fid, "counts": {}, "password": "no"}).status_code == 403
    assert c.post("/api/quality/check-sheets", json={"form_id": fid, "counts": {"Nope": 1}, "password": PW}) \
        .status_code == 409
    assert c.post("/api/quality/check-sheets", json={"form_id": 99999, "counts": {}, "password": PW}).status_code == 404
    p = c.get(f"/api/quality/tools/pareto?source=check_sheet&by=category&form_id={fid}").json()
    assert p["bars"][0]["key"] == "Scratch" and p["bars"][0]["records"][0]["name"] == "CS-00001"
    assert c.get("/api/quality/tools/pareto?source=ncr&by=nope").status_code == 409
    assert c.get("/api/quality/tools/histogram?source=incoming&item_code=BOLT-B&parameter=Length").json()[
        "enough_data"] is False
    assert c.get("/api/quality/tools/scatter?source=x&item_code=A&x=a&y=b").status_code == 409
    assert c.post(f"/api/quality/check-sheets/forms/{fid}/active", json={"active": False}).json()["active"] is False
    assert len(c.get("/api/quality/check-sheets").json()["sheets"]) == 1
