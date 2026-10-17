"""Measurement files and control charts, step 20c (ADR-0020): CSV exports of a coordinate measuring machine in the
long and the wide shape and Q-DAS files read by code; features matched to the plan only by name or by the person;
an import previewed, then signed, refused if anything changed in between or the file came before; readings from a
file naming their import until someone types over them; equipment out of calibration refused; control charts and
capability of the hub's own readings, unknown without limits. Fictional data only."""

import datetime as dt

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.test_calibration import calibrate, caliper, started
from tests.test_iqc import AS_OF, DANA, DEMO, JORDAN, PW, approved, inspect, plan, receipts, table
from tests.test_production import active_template
from tests.test_quality_data import business
from tests.test_recall import released, world  # noqa: F401 - the fixture
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import project as OP
from wqops.hub.quality import iqc as I
from wqops.hub.quality import meas_rules as MR
from wqops.hub.quality import measurements as ME

T = AS_OF
CHARS = [{"name": "Length", "kind": "measured", "lsl": 9.8, "usl": 10.2},
         {"name": "Finish", "kind": "attribute"}]
CMM = (b"Part,Feature,Axis,Nominal,Measured,+Tol,-Tol\n"
       b"1,LEN1,X,10.0,10.01,0.2,-0.2\n2,LEN1,X,10.0,9.97,0.2,-0.2\n3,LEN1,X,10.0,10.03,0.2,-0.2\n"
       b"1,PLN1,FLAT,0,0.004,0.01,0\n")
DFQ = (b"K0100 2\nK1001 BOLT-B\nK2001/1 1\nK2002/1 Length\nK2110/1 9.8\nK2111/1 10.25\nK2001/2 2\nK2002/2 Head\n"
       b"10.01\x140\x0f5.0\x140\n10.02\x14255\x0f5.1\x140\n")


def test_reading_files():
    long = MR.parse("run.csv", CMM)
    assert [f["name"] for f in long["features"]] == ["LEN1 X", "PLN1 FLAT"] and long["parts"] == ["1", "2", "3"]
    assert long["features"][0] == {"name": "LEN1 X", "nominal": 10.0, "lsl": 9.8, "usl": 10.2}
    wide = MR.parse("w.csv", b"Serial;Length;Width\nS1;10,01;5,2\nS2;9,99;\nS3;x;5,1\n")
    assert wide["parts"] == ["S1", "S2", "S3"] and wide["values"][("S1", "Length")] == 10.01
    assert ("S2", "Width") not in wide["values"]
    assert wide["problems"] == ["row 4: Length of part S3: 'x' is not a number"]
    nopart = MR.parse("n.csv", b"Length,Width\n10.0,5\n10.1,5\n")
    assert nopart["parts"] == ["1", "2"] and [f["name"] for f in nopart["features"]] == ["Length", "Width"]
    q = MR.parse("run.dfq", DFQ)
    assert q["part_no"] == "BOLT-B" and q["features"][0] == {"name": "Length", "lsl": 9.8, "usl": 10.25}
    assert q["values"] == {("1", "Length"): 10.01, ("1", "Head"): 5.0, ("2", "Head"): 5.1}
    assert "attribute 255" in q["problems"][0]
    kf = MR.parse("k.dfq", b"K2001/1 1\nK2002/1 Length\nK0001/1 10.0\nK0001/1 10.1\nK0002/1 4\n")
    assert kf["values"] == {("1", "Length"): 10.0} and "attribute 4" in kf["problems"][0]
    for name, raw, msg in (("a.csv", b"Part,Feature\n1,X\n", "no measured value"), ("a.csv", b"Length\n", "no rows"),
                           ("a.pdf", b"%PDF", "read CSV"), ("a.dfq", b"K0100 1\n", "no characteristics"),
                           ("a.csv", b"x" * (MR.MAX_BYTES + 1), "larger than 5 MB")):
        with pytest.raises(MR.MeasError, match=msg):
            MR.parse(name, raw)
    assert MR.number("1.234,5", comma=True) == 1234.5 and MR.number("-0,02", comma=True) == -0.02
    assert MR.number("1e-3") == 0.001 and MR.number("10 mm") is None and MR.number("") is None


def test_matching_and_placing():
    q = MR.parse("run.dfq", DFQ)
    m = MR.match(q["features"], CHARS)
    assert m == {"Length": "Length"}                                 # Head is not in the plan; Finish is not measured
    with pytest.raises(MR.MeasError, match="not a measured characteristic"):
        MR.match(q["features"], CHARS, {"Head": "Finish"})
    with pytest.raises(MR.MeasError, match="more than one feature goes to Length"):
        MR.match(q["features"], CHARS, {"Head": "Length"})
    p = MR.place(q, CHARS, 3, 2, m)
    assert p["readings"] == [{"sample": 2, "characteristic": "Length", "value": 10.01}] and p["samples"] == [2, 3]
    assert any("USL 10.25 differs from the plan's 10.2" in n for n in p["notes"])
    assert any("Head: not in the plan" in n for n in p["notes"])
    with pytest.raises(MR.MeasError, match="only 1 samples"):
        MR.place(q, CHARS, 3, 3, m)


def test_import_into_an_inspection(world):  # noqa: F811
    w = world
    ins = started(w)                                   # samples 1-3 typed: Length 10.0
    me = Acc.get(w, JORDAN)
    with pytest.raises(ME.MeasurementError, match="no reading in the file"):
        p = ME.preview(w, ins["id"], "run.csv", CMM)
        ME.import_file(w, me, ins["id"], "run.csv", CMM, PW, seen=p["print"], today=T)
    mapping = {"LEN1 X": "Length"}
    p = ME.preview(w, ins["id"], "run.csv", CMM, mapping=mapping, first_sample=1)
    assert [r["value"] for r in p["readings"]] == [10.01, 9.97, 10.03] and len(p["replaces"]) == 3
    assert p["notes"] == ["PLN1 FLAT: not in the plan, left out"]
    with pytest.raises(PermissionError):
        ME.import_file(w, me, ins["id"], "run.csv", CMM, "wrong", seen=p["print"], mapping=mapping, first_sample=1,
                       today=T)
    with pytest.raises(ME.MeasurementError, match="changed since the preview"):     # another export of the run
        ME.import_file(w, me, ins["id"], "run.csv", CMM.replace(b"9.97", b"9.96"), PW, seen=p["print"],
                       mapping=mapping, first_sample=1, today=T)
    g = caliper(w)                                     # not calibrated yet: out of service
    with pytest.raises(ME.MeasurementError, match="CAL-01"):
        ME.import_file(w, me, ins["id"], "run.csv", CMM, PW, seen=p["print"], mapping=mapping, first_sample=1,
                       gauge_id=g["id"], today=T)
    calibrate(w, g["id"], T - dt.timedelta(days=3))
    got = ME.import_file(w, me, ins["id"], "run.csv", CMM, PW, seen=p["print"], mapping=mapping, first_sample=1,
                         gauge_id=g["id"], today=T)
    assert got["readings"] == 3 and got["samples"] == {"1": 1, "2": 2, "3": 3} and got["gauge_code"] == "CAL-01"
    rd = {r["sample"]: r for r in I.readings(w, ins["id"]) if r["characteristic"] == "Length"}
    assert rd[2]["value"] == 9.97 and rd[2]["import_id"] == got["id"]
    assert I.view(w, ins["id"], T)["gauges"]["Length"]["gauge_code"] == "CAL-01"
    p2 = ME.preview(w, ins["id"], "run.csv", CMM, mapping=mapping, first_sample=1)
    assert p2["already"]["by"] == JORDAN and p2["replaces"] == []
    with pytest.raises(ME.MeasurementError, match=r"imported into .* before"):
        ME.import_file(w, me, ins["id"], "run.csv", CMM, PW, seen=p2["print"], mapping=mapping, first_sample=1,
                       today=T)
    I.enter(w, JORDAN, ins["id"], [{"sample": 2, "characteristic": "Length", "value": 9.99}])
    rd = {r["sample"]: r for r in I.readings(w, ins["id"]) if r["characteristic"] == "Length"}
    assert rd[2]["import_id"] is None and rd[1]["import_id"] == got["id"]
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        w.execute("update measurement_imports set readings = 9")
    assert ME.content(w, got["id"]) == ("run.csv", CMM)
    signs = w.execute("select meaning from signatures where kind = 'measurement_import'").fetchall()
    assert signs[0]["meaning"].startswith("Measurements imported from run.csv (3 readings)")
    I.sign(w, me, ins["id"], PW, today=T)
    with pytest.raises(ME.MeasurementError, match="no longer be imported"):
        ME.preview(w, ins["id"], "other.csv", CMM, mapping=mapping)


def test_control_charts_of_the_hubs_readings(world):  # noqa: F811
    w = world
    table(w)
    plan(w)
    lots = [inspect(w, f"PR-{7 + i}", v) for i, v in enumerate(
        ([10.0, 10.02, 9.98], [10.01, 9.99, 10.0], [10.03, 10.0, 9.97], [9.99, 10.01, 10.0]))]
    pars = {(p["source"], p["item_code"], p["parameter"]): p["inspections"] for p in ME.parameters(w)}
    assert pars[("incoming", "BOLT-B", "Length")] == 4
    ch = ME.spc_for(w, "incoming", "BOLT-B", "Length")
    assert ch["enough_data"] and ch["chart"]["kind"] == "xbar_r" and ch["chart"]["n"] == 3
    assert ch["capability"]["LSL"] == 9.8 and ch["values"] == 12 and "rough guide" in ch["capability_note"]
    assert ME.spc_for(w, "incoming", "BOLT-B", "Finish")["enough_data"] is False
    active_template(w)
    for k in range(3):
        released(w, f"L-{k}", lots[0]["id"])
    pr = ME.spc_for(w, "production", "WIDGET-A", "Shaft diameter")
    assert pr["chart"]["kind"] == "i_mr" and pr["values"] == 3 and pr["capability"] is None
    assert pr["capability_note"].startswith("unknown")                # three equal values: no spread
    with pytest.raises(ME.MeasurementError, match="incoming or production"):
        ME.spc_for(w, "erp", "BOLT-B", "Length")


def test_measurements_api(db_url):
    f = receipts(business())
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=f.transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, DANA, "lee@demo.example"):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=f.transport()))
        OP.project(conn, manifest=DEMO)
        Acc.sync(conn, DEMO)
        approved(conn)
        table(conn)
        p = I.new_plan(conn, JORDAN, "BOLT-B", 1.0, CHARS)
        I.enable_plan(conn, Acc.get(conn, DANA), p["id"], PW)
        ins = I.start(conn, JORDAN, "BOLT-B", receipt="PR-9", today=T)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    url = f"/api/iqc/inspections/{ins['id']}/measurements"
    up = {"file": ("w.csv", b"Sample,Length\n1,10.0\n2,10.1\n", "text/csv")}
    login("lee@demo.example")
    assert c.post(url + "/preview", files=up).status_code == 403
    assert c.get("/api/quality/measurements/parameters").status_code == 200     # charts: quality:view
    login(JORDAN)
    assert c.post(url + "/preview", data={"mapping": "[1]"}, files=up).status_code == 400
    assert c.post(url + "/preview").status_code == 400
    pv = c.post(url + "/preview", files=up).json()
    assert pv["first_sample"] == 1 and len(pv["readings"]) == 2
    assert c.post(url, data={"password": PW, "seen": "x"}, files=up).status_code == 409
    assert c.post(url, data={"password": "no", "seen": pv["print"]}, files=up).status_code == 403
    done = c.post(url, data={"password": PW, "seen": pv["print"]}, files=up)
    assert done.status_code == 201 and done.json()["readings"] == 2
    assert c.get(url).json()[0]["file_name"] == "w.csv"
    assert c.get(f"/api/measurements/{done.json()['id']}/file").content == up["file"][1]
    assert c.get("/api/measurements/99999/file").status_code == 404
    assert c.get("/api/quality/measurements/spc?source=x&item_code=B&parameter=L").status_code == 409
    assert c.get("/api/quality/measurements/parameters").json() == []    # nothing signed yet
