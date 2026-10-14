"""Document library checks, step 14b (ADR-0014 item 4): duplicates, revisions and the current one, number conflicts,
missing numbers / revisions / dates, the company's numbering convention and suggested numbers, standard file names,
gaps between procedures and their forms and records, and keeping older revisions as obsolete. Fictional data only."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.test_documents import AS_OF, DEMO, JORDAN, PW, SAM, imported
from wqops.demo import documents as DD
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.ai import llm as L
from wqops.hub.app import create_app
from wqops.hub.docs import checks as CK
from wqops.hub.docs import library as LIB


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    for e in (JORDAN, SAM):
        Acc.set_password(conn, e, PW)
    return conn


PROCS = {"receiving": {"name": "Receiving inspection", "short": "RI"},
         "nonconformance": {"name": "Nonconforming product", "short": "NC"},
         "purchasing": {"name": "Purchasing and suppliers", "short": "PU"},
         "complaints": {"name": "Complaints", "short": "CP"}, "other": {"name": "Other", "short": "GEN"}}


def doc(i, doc_type="procedure", number=None, process="receiving", revision=None, status="to_review", sha=None,
        title="Receiving Inspection", refs=(), date=None, name=None):
    return {"id": i, "sha256": sha or f"{i:064d}", "status": status, "doc_type": doc_type, "process": process,
            "number": number, "title": title, "revision": revision, "effective_date": date, "refs": list(refs),
            "original_name": name or f"file{i}.pdf", "path": "QMS"}


def kinds(found):
    return sorted(i["kind"] for i in found)


def run(docs, rules=None):
    codes = CK.process_codes(docs, PROCS)
    convs = CK.conventions(docs, rules or {})
    return CK.issues(docs, PROCS, convs, codes), convs, codes


def test_revision_order_and_the_current_one():
    assert CK.rev_key("C") > CK.rev_key("B") and CK.rev_key("AA") > CK.rev_key("Z")
    assert CK.rev_key("10") > CK.rev_key("9") and CK.rev_key("2.1") > CK.rev_key("2")
    b, c = doc(1, number="QP-08", revision="B"), doc(2, number="QP-08", revision="C")
    assert CK.newest([b, c]) is c
    assert CK.newest([dict(b, status="effective"), c])["id"] == 1         # the effective one is current
    mixed = [doc(3, revision="3", date=dt.date(2024, 1, 1)), doc(4, revision="B", date=dt.date(2025, 1, 1))]
    assert CK.newest(mixed)["id"] == 4                                    # mixed schemes: the latest date


def test_revisions_conflicts_and_duplicates():
    docs = [doc(1, number="QP-08", revision="B", process="nonconformance", title="Control of Nonconforming Product"),
            doc(2, number="QP-08", revision="C", process="nonconformance", title="Control of Nonconforming Product"),
            doc(3, number="QP-05", revision="D", title="Receiving Inspection"),
            doc(4, number="QP-05", revision="E", title="Calibration of Gauges"),           # same number, other doc
            doc(5, number="QP-06", revision="A", title="Storage"), doc(6, number="QP-06", revision="A",
                                                                         title="Storage"),
            doc(7, doc_type="form", number="F-QA-010", sha="a" * 64, title="Receiving Inspection Record",
                revision="1", date="2025-01-01"),
            doc(8, doc_type="form", number="F-QA-010", sha="a" * 64, title="Receiving Inspection Record",
                revision="1", date="2025-01-01", name="copy.pdf")]
    found, _, _ = run(docs)
    rev = next(i for i in found if i["kind"] == "revisions")
    assert rev["keep"] == 2 and rev["older"] == [1] and "rev C is current" in rev["title"]
    assert next(i for i in found if i["kind"] == "number_conflict")["docs"] == [3, 4]
    assert next(i for i in found if i["kind"] == "same_revision")["docs"] == [5, 6]
    dup = next(i for i in found if i["kind"] == "duplicate")
    assert dup["docs"] == [7, 8] and dup["keep"] == 7
    assert [i["severity"] for i in found][:2] == ["high", "high"]           # most serious first
    found, _, _ = run([doc(1, number="QP-08", revision="B", status="obsolete"),
                       doc(2, number="QP-08", revision="C", status="effective")])
    assert "revisions" not in kinds(found)                                # the older one is already obsolete


def test_numbering_is_learned_from_the_company_and_suggested():
    docs = [doc(1, doc_type="form", number="F-QA-010", process="receiving"),
            doc(2, doc_type="form", number="F-QA-012", process="nonconformance"),
            doc(3, doc_type="form", number="F-PU-001", process="purchasing"),
            doc(4, doc_type="form", number=None, process="receiving", title="Gauge list"),
            doc(5, doc_type="form", number="GAUGES", process="receiving", title="Gauge sheet"),
            doc(6, number="QP-01"), doc(7, number="QP-04"), doc(8, number=None, title="Complaints",
                                                                process="complaints")]
    found, convs, codes = run(docs)
    assert convs["form"] == {"template": "F-{process}-{seq}", "digits": 3, "source": "learned",
                             "examples": ["F-PU-001", "F-QA-010", "F-QA-012"]}
    assert convs["procedure"]["template"] == "QP-{seq}" and convs["work_instruction"]["source"] == "default"
    assert codes["receiving"] == "QA" and codes["complaints"] == "CP"       # the company's code, else the short one
    by = {(i["kind"], i["docs"][0]): i for i in found}
    assert by[("no_number", 4)]["suggest"] == "F-QA-013"                  # next free in this process's series
    assert by[("no_number", 8)]["suggest"] == "QP-05"
    assert by[("odd_number", 5)]["suggest"] == "F-QA-014"                 # F-QA-013 is already suggested to 4
    assert ("odd_number", 1) not in by and ("odd_number", 3) not in by
    found, convs, _ = run(docs, {"form": {"template": "FRM-{seq}", "digits": 4}})
    assert convs["form"]["source"] == "rule"
    forms = sorted(i["suggest"] for i in found if i["kind"] in ("no_number", "odd_number")
                   and docs[i["docs"][0] - 1]["doc_type"] == "form")
    assert forms == ["FRM-0001", "FRM-0002", "FRM-0003", "FRM-0004", "FRM-0005"]    # every form off the rule
    assert CK.standard_name(doc(1, number="QP-08", revision="C", title="Control: of NC?", name="x.PDF")) == \
        "QP-08 Control of NC Rev C.pdf"
    assert CK.standard_name(doc(1)) is None


def test_gaps_between_procedures_forms_and_records():
    docs = [doc(1, number="QP-05", revision="D", refs=["F-QA-010", "F-QA-011", "TW-02", "QP-05"], date="2025-01-01"),
            doc(2, doc_type="form", number="F-QA-010", revision="3", date="2025-01-01"),
            doc(3, doc_type="form", number="F-QA-020", revision="1", process="purchasing", date="2025-01-01"),
            doc(4, doc_type="record", process="purchasing", title="Supplier list 2026"),
            doc(5, doc_type="record", number="F-QA-010", title="Inspection lot 4471")]
    found, _, _ = run(docs)
    miss = next(i for i in found if i["kind"] == "missing_ref")
    assert miss["missing"] == ["F-QA-011"]                                # a gauge id is not a document
    unused = next(i for i in found if i["kind"] == "form_unused")
    assert unused["docs"] == [3]                                          # F-QA-010 has a record
    assert next(i for i in found if i["kind"] == "no_procedure")["process"] == "purchasing"
    assert {i["process"] for i in found if i["kind"] == "empty_process"} == {"nonconformance", "complaints"}
    assert "no_date" not in kinds(found) and "no_revision" not in kinds(found)


def test_demo_library_shows_the_built_in_problems(world):
    DD.load(world, DEMO | {"demo": True}, AS_OF, None)
    st = LIB.check(world)
    k = kinds(st["issues"])
    assert {"duplicate", "revisions", "missing_ref", "no_number", "empty_process"} <= set(k)
    rev = next(i for i in st["issues"] if i["kind"] == "revisions")
    names = {d["id"]: d["path"] for d in st["docs"]}
    assert names[rev["older"][0]].endswith("/old")                         # the copy in the "old" folder
    wi = next(i for i in st["issues"] if i["kind"] == "no_number")
    s = LIB.suggestions(world, LIB.get(world, wi["docs"][0]), st)
    assert s["number"] == wi["suggest"] and s["file_name"].startswith(wi["suggest"])


def test_keep_older_revision_as_obsolete(world):
    imp, (c, b) = imported(world, ["QP-08 Control of Nonconforming Product Rev C",
                                   "QP-08 Control of Nonconforming Product Rev B"])
    with pytest.raises(LIB.DocError, match="type, process and title"):
        LIB.archive(world, JORDAN, b["id"], "replaced by rev C")
    from wqops.hub.docs import ai_classify as AIC

    AIC.run(world, {"email": JORDAN, "roles": ["quality"]}, imp["id"], None, today=AS_OF)
    with pytest.raises(LIB.DocError, match="say why"):
        LIB.archive(world, JORDAN, b["id"], "")
    old = LIB.archive(world, JORDAN, b["id"], "replaced by rev C")
    assert old["status"] == "obsolete" and old["fingerprint"] == old["sha256"]
    assert "revisions" not in kinds(LIB.check(world)["issues"])
    LIB.confirm(world, JORDAN, c["id"])
    LIB.submit(world, JORDAN, c["id"])
    with pytest.raises(LIB.DocError, match="waiting for review or a draft"):
        LIB.archive(world, JORDAN, c["id"], "x")
    assert LIB.approve(world, Acc.get(world, SAM), c["id"], PW, AS_OF)["status"] == "effective"


def test_numbering_rules_need_a_sensible_shape(world):
    for bad in ("{seq}-QP", "QP", "Q P-{seq}", "QP-{seq}{seq}"):
        with pytest.raises(LIB.DocError):
            LIB.set_rule(world, JORDAN, "procedure", bad, 2)
    with pytest.raises(LIB.DocError):
        LIB.set_rule(world, JORDAN, "record", "R-{seq}", 2)
    r = LIB.set_rule(world, JORDAN, "form", "frm-{Process}-{seq}", 3)
    assert r["template"] == "FRM-{process}-{seq}"
    assert LIB.check(world)["conventions"]["form"]["source"] == "rule"
    LIB.clear_rule(world, "form")
    assert LIB.check(world)["conventions"]["form"]["source"] == "default"


def test_checks_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, ai=L.Anthropic("", env={})))
    c.__enter__()
    with DB.connect(db_url) as conn:
        for e in (JORDAN, "alex@demo.example"):
            Acc.set_password(conn, e, PW)
        DD.load(conn, DEMO | {"demo": True}, AS_OF, None)
    c.post("/api/login", json={"email": "alex@demo.example", "password": PW})
    out = c.get("/api/docs/issues").json()
    assert out["conventions"]["procedure"]["template"] == "QP-{seq}" and out["issues"]
    assert all(str(i) in out["docs"] for x in out["issues"] for i in x["docs"])
    assert c.put("/api/docs/numbering/form", json={"template": "F-{seq}", "digits": 3}).status_code == 403
    ov = c.get("/api/docs/overview").json()
    assert ov["issues"]["medium"] >= 3 and ov["issues_by_process"]["nonconformance"] >= 1
    only = c.get("/api/docs/issues?process=nonconformance").json()["issues"]
    assert only and all(i["process"] == "nonconformance" or i["process"] is None for i in only)
    c.post("/api/login", json={"email": JORDAN, "password": PW})
    assert c.put("/api/docs/numbering/form", json={"template": "F-{seq}", "digits": 3}).json()["template"] == "F-{seq}"
    assert c.delete("/api/docs/numbering/form").json() == {"ok": True}
    qp = next(d for d in c.get("/api/docs?status=all&q=QP-05").json() if d["number"] == "QP-05")
    one = c.get(f"/api/docs/{qp['id']}").json()
    assert one["suggest"]["file_name"] == "QP-05 Receiving Inspection Rev D.pdf"
    f = c.get(f"/api/docs/{qp['id']}/file?standard=1")
    assert f.headers["content-disposition"].endswith("''QP-05%20Receiving%20Inspection%20Rev%20D.pdf")
    old = next(d for d in c.get("/api/docs?status=all&q=QP-08").json() if d["revision"] == "B")
    r = c.post(f"/api/docs/{old['id']}/archive", json={"reason": "replaced by rev C"}).json()
    assert r["status"] == "obsolete" and r["history"][-1]["action"] == "kept as obsolete"


def test_odd_data_from_the_review():
    """Cases an independent review found: none of them may crash or mislead."""
    assert CK.rev_key("1.10") > CK.rev_key("1.9") and CK.norm_rev("Rev. c") == "C" and CK.norm_rev("01") == "1"
    found, convs, _ = run([doc(1, doc_type="form", number="1001"), doc(2, doc_type="form", number="1002")])
    assert convs["form"]["source"] == "default"                           # all digits: nothing to learn, no crash
    b, c = doc(1, number="QP-08", revision="Rev B"), doc(2, number="QP-08", revision="C")
    assert next(i for i in run([c, b])[0] if i["kind"] == "revisions")["keep"] == 2
    found, _, _ = run([doc(1, number="QP-06", revision="01"), doc(2, number="QP-06", revision="1")])
    assert "same_revision" in kinds(found)
    found, _, _ = run([doc(1, number="QP-06"), doc(2, number="QP-06")])
    assert "same_revision" not in kinds(found) and kinds(found).count("no_revision") == 2
    eff = doc(1, number="QP-01", revision="B", status="effective", date="2025-01-01")
    new = dict(doc(2, number="QP-01", revision="C", status="draft", date="2025-01-01"), supersedes=1)
    assert "revisions" not in kinds(run([eff, new])[0])                  # a revision in progress is no problem
    two = [doc(1, doc_type="form", number="F-QA-010"), doc(2, doc_type="form", number="F-QA-011"),
           doc(3, doc_type="form", title="Gauge list A"), doc(4, doc_type="form", title="Gauge list B"),
           doc(5, doc_type="form", process="purchasing", title="Supplier list")]
    found, convs, _ = run(two)
    sug = {i["docs"][0]: i["suggest"] for i in found if i["kind"] == "no_number"}
    assert sug[3] != sug[4] and {sug[3], sug[4]} == {"F-QA-012", "F-QA-013"}   # never the same suggestion twice
    assert convs["form"]["template"] == "F-{process}-{seq}" and sug[5] == "F-PU-001"   # another process, its code
    assert CK.norm_no("F RI 001") == "F-RI-001"


def test_archive_and_rules_refuse_bad_input(world):
    with pytest.raises(LIB.DocError, match="1 to 6 digits"):
        LIB.set_rule(world, JORDAN, "form", "F-{seq}", "abc")
    _, (qp,) = imported(world, ["QP-05"])
    world.execute("update documents set supersedes = %s, doc_type = 'procedure', process = 'receiving', "
                  "title = 'x', status = 'draft' where id = %s", (qp["id"], qp["id"]))
    with pytest.raises(LIB.DocError, match="new revision in progress"):
        LIB.archive(world, JORDAN, qp["id"], "older")
