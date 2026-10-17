"""20b (ADR-0020): device identifiers, scanned codes and labels. GS1 check digits on known GTINs, GS1 codes in all
the forms a scanner returns, HIBC with its check character, labels for released lots from the production record,
every change and print kept, and what a scan is matched to. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_iqc import DEMO, JORDAN, PW, receipts
from tests.test_production import SAM, active_template, bolt_lot
from tests.test_quality_data import business
from tests.test_recall import released, world  # noqa: F401 - the fixture
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import udi as UD
from wqops.hub import udi_rules as U
from wqops.hub.app import create_app

D = dt.date


def test_check_digits_and_known_gtins():
    # published codes, for their check digits; the records below use GS1 prefix 952, kept for examples
    assert U.gtin14("4006381333931") == "04006381333931"           # a published EAN-13
    assert U.gtin14("036000291452") == "00036000291452"            # a published UPC-A
    with pytest.raises(U.UdiError, match="should be 1"):
        U.gtin14("4006381333932")
    with pytest.raises(U.UdiError, match="8, 12, 13 or 14"):
        U.gtin14("12345")
    assert U.yymmdd("280200", D(2026, 1, 1)) == D(2028, 2, 29)     # day 00: the last day of the month
    assert U.yymmdd("990101", D(2026, 1, 1)) == D(1999, 1, 1)


def test_gs1_in_every_form_a_scanner_gives():
    data, text = U.gs1_data("4006381333931", lot="L-1", serial="S9", production=D(2026, 10, 1),
                            expiry=D(2028, 9, 30))
    assert text == "(01)04006381333931(11)261001(17)280930(10)L-1(21)S9" and data.count(U.GS) == 1
    want = {"di": "04006381333931", "lot": "L-1", "serial": "S9", "production_date": "2026-10-01",
            "expiry_date": "2028-09-30"}
    for code in (data, "]d2" + data, "]Q3" + data, text, data.replace(U.GS, "<GS>")):
        got = U.parse(code, D(2026, 10, 16))
        assert {k: got[k] for k in want} == want, code
    link = U.parse("https://id.gs1.org/01/04006381333931/10/L-1?17=280930", D(2026, 10, 16))
    assert (link["di"], link["lot"], link["expiry_date"], link["form"]) == ("04006381333931", "L-1", "2028-09-30",
                                                                            "GS1 Digital Link")
    for bad, msg in (("0104006381333932", "check digit"), ("99X", "unknown GS1"), ("0104006", "needs 14"),
                     ("(10)ABC", "no device identifier"), ("hello", "not a GS1, HIBC")):
        with pytest.raises(U.UdiError, match=msg):
            U.parse(bad)


def test_what_review_found_in_reading_and_printing():
    today = D(2026, 10, 16)
    code = U.hibc_data("+A123YX0")                     # its check character is a space
    assert code.endswith(" ") and U.parse(code + "\r\n", today)["pcn"] == "YX"
    body = "+$LOT1I"                                    # a secondary code on its own ends with its link character
    assert U.parse(body + U.hibc_check(body), today).items() >= {"lot": "LOT1", "link": "I"}.items()
    hibc_qty = "+A123PROD10/$$8050LOT1"
    with pytest.raises(U.UdiError, match="quantity"):
        U.parse(hibc_qty + U.hibc_check(hibc_qty), today)
    for bad in ("(01)09521234567899(17)261300", "(01)09521234567899(17)260000"):
        with pytest.raises(U.UdiError, match="not a real date"):
            U.parse(bad, today)
    link = U.parse("HTTPS://ID.GS1.ORG/shop/01/09521234567899/10/10/21/5", today)
    assert (link["lot"], link["serial"]) == ("10", "5")
    assert U.parse("https://id.gs1.org/01/09521234567899/10/AB%2F12", today)["lot"] == "AB/12"
    assert U.parse("09521234567899", today).items() >= {"di": "09521234567899", "form": "GTIN"}.items()
    assert U.parse("9521234567899", today)["di"] == "09521234567899"
    for lot in ("A#1", "A(1)", "x" * 21):
        with pytest.raises(U.UdiError, match="holds up to 20"):
            U.gs1_data("9521234567899", lot=lot)
    z = U.zpl("01x", ["A~JA", "x" * 58 + "_y"], gs1=False)
    assert "~" not in z and "^FDA_7EJA^FS" in z and "x" * 58 + "_5Fy" in z and "_5^" not in z


def test_hibc_codes_round_trip():
    di = U.hibc_di("a123", "widget1", "0")
    assert di == "+A123WIDGET10"
    for kw, want in (({}, {}), ({"lot": "L1"}, {"lot": "L1"}),
                     ({"lot": "L1", "expiry": D(2028, 9, 30)}, {"lot": "L1", "expiry_date": "2028-09-30"}),
                     ({"serial": "SN5"}, {"serial": "SN5"})):
        got = U.parse(U.hibc_data(di, **kw), D(2026, 10, 16))
        assert got["lic"] == "A123" and got["pcn"] == "WIDGET1" and all(got[k] == v for k, v in want.items())
    code = U.hibc_data(di, lot="L1")
    with pytest.raises(U.UdiError, match="check character"):
        U.parse(code[:-1] + ("A" if code[-1] != "A" else "B"))
    with pytest.raises(U.UdiError, match="labeler identification"):
        U.hibc_di("1AB", "X", "0")
    zpl = U.zpl(U.gs1_data("4006381333931", lot="L1")[0], ["WIDGET-A"], gs1=True, copies=2)
    assert "^BXN,6,200,,,,_" in zpl and "^FD_1010400638133393110L1^FS" in zpl and "^PQ2" in zpl
    with pytest.raises(U.UdiError, match="cannot be printed"):
        U.zpl("01^X", [], gs1=True)


def test_labels_and_scans(world):  # noqa: F811
    with pytest.raises(UD.UdiError, match="not an item"):
        UD.set_di(world, JORDAN, "NOPE", {"agency": "gs1", "gtin": "9521234567899"})
    with pytest.raises(UD.UdiError, match="check digit"):
        UD.set_di(world, JORDAN, "WIDGET-A", {"agency": "gs1", "gtin": "9521234567898"})
    UD.set_di(world, JORDAN, "WIDGET-A", {"agency": "hibcc", "lic": "A123", "pcn": "WA", "unit": "0"})
    UD.set_di(world, JORDAN, "WIDGET-A", {"agency": "gs1", "gtin": "9521234567899"})
    assert [h["action"] for h in UD.history(world, "WIDGET-A")] == ["set", "changed"]
    with pytest.raises(UD.UdiError, match="already the identifier of WIDGET-A"):
        UD.set_di(world, JORDAN, "BOLT-B", {"agency": "gs1", "gtin": "09521234567899"})
    active_template(world)
    lot = bolt_lot(world)
    r = released(world, "L-001", lot["id"])
    lab = UD.label(world, r["id"], expiry=D(2029, 1, 31))
    assert lab["text"].startswith("(01)09521234567899(11)") and lab["text"].endswith("(17)290131(10)L-001")
    assert lab["lines"][:2] == ["WIDGET-A", "LOT L-001"]
    with pytest.raises(UD.UdiError, match="after the production date"):
        UD.label(world, r["id"], expiry=D(2000, 1, 1))
    UD.printed(world, JORDAN, r["id"], lab, fmt="zpl", copies=3)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        world.execute("delete from label_prints")
    found = UD.look_up(world, lab["data"], D(2026, 10, 16))
    assert found["found"]["item_code"] == "WIDGET-A" and [p["lot_no"] for p in found["found"]["production"]] == [
        "L-001"]
    assert UD.look_up(world, "(01)00036000291452(10)L-001", D(2026, 10, 16))["found"]["item_code"] is None


def test_udi_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=receipts(business()).transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (JORDAN, SAM, "alex@demo.example"):
            Acc.set_password(conn, e, PW)
    c.post("/api/login", json={"email": "alex@demo.example", "password": PW})
    out = c.post("/api/udi/scan", json={"code": "(01)09521234567899(10)L-9"}).json()
    assert out["read"]["lot"] == "L-9" and out["found"]["production"] == []       # sales sees the read only
    assert c.get("/api/udi/items").status_code == 403
    assert c.post("/api/udi/scan", json={"code": "nonsense"}).status_code == 409
    c.post("/api/login", json={"email": JORDAN, "password": PW})
    assert c.put("/api/udi/items/NOPE", json={"agency": "gs1", "gtin": "9521234567899"}).status_code == 409
    assert c.get("/api/production/99999/label").status_code == 404
    assert c.post("/api/production/1/label", json={"format": "pdf"}).status_code == 400
    c.__exit__(None, None, None)
