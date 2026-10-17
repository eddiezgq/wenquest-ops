"""Sample records for the regulated quality modules of the demo company (ADR-0019 item 6): every part loads with the
modules' own rules, each leaves something done, under way and with a problem, a second run changes nothing, and the
demo signatures are accepted only while loading a demo company. Fictional data only."""

import pytest

from tests.test_demo import DEMO, TODAY, loaded  # noqa: F401 - the fixture
from wqops.demo import documents as DOCS
from wqops.demo import load as LD
from wqops.demo import quality as DQ
from wqops.hub import accounts as Acc
from wqops.hub import sync as Y
from wqops.hub.ont import project as OP
from wqops.hub.quality import records as Q


@pytest.fixture
def demo(loaded, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))
    conn, fake, erp, out = loaded
    Acc.sync(conn, DEMO)
    fake.docs["Quality Inspection"][out["rejected_inspection"]]["status"] = "Rejected"
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    LD.quality_records(conn, DEMO, out["rejected_inspection"], TODAY)
    DOCS.load(conn, DEMO, TODAY)
    return conn


def count(conn, sql):
    return {r["k"]: r["n"] for r in conn.execute(sql)}


def test_every_part_loads(demo):
    out = DQ.load(demo, DEMO, TODAY)
    assert not [(k, v) for k, v in out.items() if v.startswith(("not loaded", "skipped"))]
    c = demo
    assert count(c, "select status as k, count(*) as n from asl_entries group by 1") == {
        "approved": 2, "conditional": 1, "draft": 1}
    assert count(c, "select status as k, count(*) as n from iqc_inspections group by 1") == {
        "released": 1, "rejected": 1, "judged": 1, "in_progress": 2}
    assert count(c, "select status as k, count(*) as n from documents where status = 'effective' group by 1") == {
        "effective": 2}
    assert count(c, "select status as k, count(*) as n from complaints group by 1") == {
        "closed": 1, "investigation": 1, "new": 1}
    assert count(c, "select status as k, count(*) as n from changes group by 1") == {
        "closed": 1, "submitted": 1, "draft": 1}
    assert count(c, "select status as k, count(*) as n from risk_files group by 1") == {"approved": 1, "draft": 1}
    assert count(c, "select status as k, count(*) as n from prod_records group by 1") == {
        "released": 1, "in_production": 1}
    assert count(c, "select status as k, count(*) as n from recalls group by 1") == {"closed": 1}
    assert count(c, "select status as k, count(*) as n from mgmt_reviews group by 1") == {"closed": 1}
    assert c.execute("select count(*) as n from gauges where next_due < %s", (TODAY,)).fetchone()["n"] == 1
    # 20b-20d: a device identifier, a measurement file and readings from a machine waiting for a person
    assert c.execute("select di from udi_items where item_code = 'HX-BOLT-M8'").fetchone()["di"] == "09521234567899"
    assert c.execute("select readings from measurement_imports").fetchone()["readings"] == 4
    assert count(c, "select status as k, count(*) as n from integration_inbox group by 1") == {"pending": 1}
    assert c.execute("select count(*) as n from integration_tokens where token_hash like 'wqo_%'").fetchone()["n"] == 0
    # 22a: a check sheet form with tallies; its Pareto starts with crushed boxes
    from wqops.hub.quality import tools as TL

    form = c.execute("select id from check_sheet_forms").fetchone()
    p = TL.pareto_for(c, "check_sheet", "category", form_id=form["id"])
    assert p["records"] == 10 and p["bars"][0]["key"] == "Crushed box" and p["total"] == 96
    # 22b: a fishbone concluded into the report's 8D, and a 5 Why under way on the complaint
    assert count(c, "select method as k, count(*) as n from cause_analyses group by 1") == {
        "fishbone": 1, "five_why": 1}
    assert c.execute("select status from cause_analyses where method = 'five_why'").fetchone()["status"] == "open"
    d4 = c.execute("select e.sections from eightd e join ncr_records n on n.id = e.ncr_id where n.item_code = "
                   "'HX-BOLT-M8'").fetchone()["sections"]["d4"]
    assert d4.startswith("Supplier rolling dies were not re-set") and d4.endswith("(from Fishbone RCA-00001)")
    assert c.execute("select count(*) as n from cause_items where origin = 'ai'").fetchone()["n"] == 0
    # a second run finds the records and changes nothing
    again = DQ.load(demo, DEMO, TODAY)
    assert all(v.startswith("skipped") for v in again.values()), again
    # after loading, signatures need the person's password again
    with pytest.raises(Q.SignatureError):
        Q.check_signer(c, Acc.get(c, "dana@demo.example"), DQ.SIGN)


def test_only_for_the_demo_company(demo):
    with pytest.raises(DQ.DemoQualityError, match="demo: true"):
        DQ.load(demo, {**DEMO, "demo": False}, TODAY)
