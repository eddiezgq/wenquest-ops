"""17k: the ISO checks read the regulated modules' own records (ADR-0017): risk files, production records,
traceability to incoming lots, releases by a second person and overdue periodic document reviews. With no records
yet, a control point shows the documents linked to it, as before. Fictional data only."""

import datetime as dt

from tests.test_demo import DEMO, TODAY, loaded  # noqa: F401 - the fixture
from tests.test_demo_quality import demo  # noqa: F401 - the fixture
from tests.test_qms import SET, D, facts
from wqops.demo import quality as DQ
from wqops.hub import accounts as Acc
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R

LOT = {"id": 1, "name": "DHR-00001", "lot_no": "KIT-1", "status": "released", "decided_by": "dana@demo.example",
       "decided_on": D(2026, 10, 1), "involved": ["sam@demo.example"], "materials_needed": ["BOX-12"],
       "materials_used": ["BOX-12"]}
DOC = {"id": 7, "name": "QP-11 Calibration", "status": "effective"}


def test_risk_files():
    assert R.risk_managed(facts(), SET)["status"] == "unknown"           # nothing yet: no document linked either
    assert R.risk_managed(facts(evidence={"risk_management": [DOC]}), SET)["status"] == "met"   # documents, as before
    f = {"id": 1, "name": "RMF-00001", "product": "Kit", "status": "approved", "intact": True}
    r = R.risk_managed(facts(risk_files=[f, dict(f, id=2, status="draft", intact=None)]), SET)
    assert r["status"] == "met" and "1 draft" in r["detail"] and r["evidence"][0]["kind"] == "risk_file"
    r = R.risk_managed(facts(risk_files=[dict(f, intact=False)]), SET)
    assert r["status"] == "not_met" and r["problems"][0]["why"] == "changed since it was approved"


def test_production_traceability_and_release():
    old = dict(LOT, decided_on=D(2024, 1, 1))
    for rule in (R.production_recorded, R.lots_traceable, R.release_signed):
        assert rule(facts(production=[old]), SET)["status"] == "unknown"   # outside the period
        assert rule(facts(production=[LOT]), SET)["status"] == "met"
    r = R.lots_traceable(facts(production=[dict(LOT, materials_used=[])]), SET)
    assert r["status"] == "not_met" and "BOX-12" in r["problems"][0]["why"]
    self_released = dict(LOT, decided_by="sam@demo.example")
    assert R.production_recorded(facts(production=[self_released]), SET)["status"] == "not_met"
    assert R.release_signed(facts(production=[self_released]), SET)["status"] == "not_met"
    lot = {"id": 3, "name": "IQC-00003", "status": "released", "signed_by": "jordan@demo.example",
           "decided_by": "jordan@demo.example", "decided_on": D(2026, 10, 2)}
    assert R.release_signed(facts(iqc_decided=[lot]), SET)["status"] == "not_met"
    r = R.release_signed(facts(iqc_decided=[dict(lot, decided_by="dana@demo.example")]), SET)
    assert r["status"] == "met" and r["evidence"][0]["kind"] == "iqc"


def test_overdue_periodic_review():
    doc = {"id": 1, "name": "QP-05", "status": "effective", "doc_type": "procedure"}
    late = {"id": 1, "number": "QP-05", "title": "Receiving", "due": "2026-01-01"}
    assert R.documents_current(facts(documents=[doc]), SET)["status"] == "met"
    r = R.documents_current(facts(documents=[doc], doc_reviews_overdue=[late]), SET)
    assert r["status"] == "not_met" and "periodic review" in r["detail"] and r["problems"][0]["id"] == 1


def test_iso13485_reads_the_demo_records(demo):  # noqa: F811
    assert not [v for v in DQ.load(demo, DEMO, TODAY).values() if v.startswith(("not loaded", "skipped"))]
    dana = Acc.get(demo, "dana@demo.example")
    with DQ.demo_signing(DEMO):
        QMS.enable(demo, dana, "iso13485", "2016", DQ.SIGN, TODAY)
    QMS.evaluate(demo, "iso13485", TODAY + dt.timedelta(days=1), "manual")
    res = QMS.latest(demo, "iso13485")["results"]
    for c in ("risk_management", "production", "traceability", "product_release"):
        assert res[c]["status"] == "met", (c, res[c]["detail"])
    assert res["traceability"]["evidence"][0]["kind"] == "production"
    assert {e["kind"] for e in res["product_release"]["evidence"]} == {"production", "iqc"}
