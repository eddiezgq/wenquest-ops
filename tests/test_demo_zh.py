"""The Chinese demo company (ADR-0023, step 23e): the same sample quality records and the same folder of quality
documents as Harbor Lane, in Chinese, made by its own people with its own suppliers, customers and items; Harbor
Lane's output stays as it was. Fictional data only; no network, no model."""

import datetime as dt
import hashlib
import io
import re

import pytest

from tests.fake_erp import FakeErp
from tests.test_demo import DEMO, TODAY
from wqops import company as C
from wqops import i18n as I18N
from wqops.demo import documents as DOCS
from wqops.demo import load as LD
from wqops.demo import quality as DQ
from wqops.demo import scenario as S
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import sync as Y
from wqops.hub.ont import project as OP

ZH = C.load(C.DEMO_DIR / "demo-haigang.yaml")
ZH_PEOPLE = {p["email"] for p in ZH["people"]}
HAN = re.compile(r"[一-鿿]")
# Harbor Lane's folder before the Chinese one was added: the names of all files and the bytes of those made by plain
# code (PDF, text, CSV); Word, Excel and the scan depend on library versions, so only their names are in it
EN_DIGEST = "fafe4bb5192b3ed4573c1e8d4c87d8914fe20a1f72a81c036ccc07e3825bba87"


@pytest.fixture
def chinese():
    """The Chinese company active: its business and its language; Harbor Lane's again afterwards."""
    S.activate(ZH)
    I18N.set_company_language("zh")
    try:
        yield
    finally:
        I18N.set_company_language("en")
        S.activate(DEMO)


def _digest(files) -> str:
    h = hashlib.sha256()
    for p, d in files:
        h.update(p.encode())
        if p.endswith((".pdf", ".txt", ".csv")):
            h.update(d)
    return h.hexdigest()


def test_harbor_lane_files_unchanged(chinese):
    en = DOCS.files("en")                       # whatever company is active, English is Harbor Lane's folder
    assert _digest(en) == EN_DIGEST
    with I18N.use("en"):
        assert DOCS.files() == en
    assert DOCS.names("en") == {"root": DOCS.ROOT, "label": DOCS.LABEL, "company": DOCS.COMPANY}


def test_chinese_folder(chinese):
    import pypdf

    en, zh = DOCS.files("en"), dict(DOCS.files("zh"))
    assert DOCS.files() == list(zh.items())     # the company's language by default
    assert len(zh) == len(en) and dict(DOCS.files("zh")) == zh                       # deterministic
    root = DOCS.names("zh")["root"]
    assert root == "海港五金 质量体系" and all(p.startswith(root + "/") for p in zh)
    names = [p.rsplit("/", 1)[1] for p in zh]
    assert all(HAN.search(p) for p in zh)
    # the document number stays at the start of the name; the deliberate problems are kept
    assert "QP-05 来料检验 版本D.pdf" in names and "QP-11 校准 版本A.docx" in names
    assert any("/旧版/QP-08 " in p for p in zh)
    forms = f"{root}/03 表单"
    assert zh[f"{forms}/F-QA-012 不合格品报告.docx"] == zh[f"{forms}/F-QA-012 不合格品报告 - 副本.docx"]
    assert any(p.startswith(f"{root}/02 作业指导书/") and not re.search(r"[A-Z]{2}-", p.rsplit("/", 1)[1])
               for p in zh)                                                          # a work instruction, no number
    # every PDF's text reads back as Chinese
    pdfs = {p: d for p, d in zh.items() if p.endswith(".pdf")}
    assert len(pdfs) == 5
    for p, d in pdfs.items():
        text = "".join(pg.extract_text() for pg in pypdf.PdfReader(io.BytesIO(d)).pages)
        assert HAN.search(text), p
    qp05 = pypdf.PdfReader(io.BytesIO(zh[f"{root}/01 程序文件/QP-05 来料检验 版本D.pdf"])).pages[0].extract_text()
    assert "海港五金供应（演示）" in qp05 and "质检隔离仓" in qp05 and "F-QA-012" in qp05
    # the company's people, suppliers and metric units in the content
    csv = next(d for p, d in zh.items() if p.endswith(".csv")).decode("utf-8-sig")
    assert csv.startswith("姓名,") and "李强" in csv and "周静" in csv
    txt = next(d for p, d in zh.items() if p.endswith(".txt")).decode("utf-8")
    assert "N·m" in txt and "ft-lb" not in txt
    blob = b"".join(zh.values())
    assert "海湾紧固件（演示）".encode() in blob or HAN.search(blob.decode("utf-8", "ignore"))


def test_chinese_folder_is_read_by_the_hub(chinese):
    """The text of every Chinese Word, Excel, CSV and text file comes out in Chinese (the hub's own reader)."""
    from wqops.hub.docs import extract as X

    read = 0
    for p, d in DOCS.files("zh"):
        if p.endswith((".docx", ".xlsx", ".csv", ".txt", ".pdf")):
            t = X.text_of(p.rsplit("/", 1)[1], d)
            assert HAN.search(t.body), p
            read += 1
    assert read == len(DOCS.files("zh")) - 1          # all but the scanned certificate (English, read by OCR)


@pytest.fixture
def zh_demo(conn, tmp_path, monkeypatch, chinese):
    monkeypatch.setenv("WQO_FILES_DIR", str(tmp_path / "files"))
    fake = FakeErp()
    fake.put("Stock Settings", "Stock Settings")
    erp = ErpClient("http://erp", transport=fake.transport())
    for kind, name in (("Supplier Group", "经销商"), ("Customer Group", "商业客户"), ("Territory", "中国")):
        fake.put(kind, name, is_group=0)
    out = LD.Loader(erp, ZH, TODAY, say=lambda _m: None).run()
    Acc.sync(conn, ZH)
    fake.docs["Quality Inspection"][out["rejected_inspection"]]["status"] = "Rejected"
    Y.run(conn, erp)
    OP.project(conn, manifest=ZH)
    LD.quality_records(conn, ZH, out["rejected_inspection"], TODAY)
    loaded = DOCS.load(conn, ZH, TODAY)
    assert loaded["loaded"] and loaded["files"] == len(DOCS.files("zh"))
    return conn


def _rows(conn, table: str) -> str:
    return " ".join(r["t"] for r in conn.execute(f"select row_to_json(x)::text as t from {table} x"))


def test_chinese_quality_samples(zh_demo):
    c = zh_demo
    imp = c.execute("select * from doc_imports").fetchone()
    assert imp["label"] == "演示：海港五金 质量体系文件夹" and imp["created_by"] == "wangdan@demo.example"
    out = DQ.load(c, ZH, TODAY)
    assert not [(k, v) for k, v in out.items() if v.startswith(("未导入", "已跳过"))], out
    assert all(HAN.search(v) for v in out.values()), out
    count = lambda sql: {r["k"]: r["n"] for r in c.execute(sql)}  # noqa: E731
    # the same states as Harbor Lane's
    assert count("select status as k, count(*) as n from asl_entries group by 1") == {
        "approved": 2, "conditional": 1, "draft": 1}
    assert count("select status as k, count(*) as n from iqc_inspections group by 1") == {
        "released": 1, "rejected": 1, "judged": 1, "in_progress": 2}
    assert count("select status as k, count(*) as n from documents where status = 'effective' group by 1") == {
        "effective": 2}
    assert count("select status as k, count(*) as n from complaints group by 1") == {
        "closed": 1, "investigation": 1, "new": 1}
    assert count("select status as k, count(*) as n from changes group by 1") == {
        "closed": 1, "submitted": 1, "draft": 1}
    assert count("select status as k, count(*) as n from risk_files group by 1") == {"approved": 1, "draft": 1}
    assert count("select status as k, count(*) as n from prod_records group by 1") == {
        "released": 1, "in_production": 1}
    assert count("select status as k, count(*) as n from recalls group by 1") == {"closed": 1}
    assert count("select status as k, count(*) as n from mgmt_reviews group by 1") == {"closed": 1}
    assert c.execute("select readings from measurement_imports").fetchone()["readings"] == 4
    assert count("select status as k, count(*) as n from integration_inbox group by 1") == {"pending": 1}
    # written in Chinese, by the Chinese company's people, about its suppliers and customers
    for table in ("asl_entries", "gauges", "iqc_plans", "complaints", "changes", "risk_files", "prod_templates",
                  "recalls", "mgmt_reviews", "qms_register_entries", "check_sheet_forms", "cause_items",
                  "fmea_scales", "fmea_rows", "flow_charts"):
        assert HAN.search(_rows(c, table)), table
    text = " ".join(_rows(c, t) for t in ("asl_entries", "complaints", "changes", "mgmt_reviews", "fmea_files",
                                          "qms_register_entries"))
    emails = set(re.findall(r"[\w.]+@demo\.example", text))
    assert emails and emails <= ZH_PEOPLE, emails
    assert "dana@" not in text and "Jordan" not in text and "Gulf" not in text
    assert S.GULF in _rows(c, "asl_entries") and S.CUSTOMERS[0] in _rows(c, "complaints")
    assert "周静" in _rows(c, "qms_register_entries") and "海湾紧固件" in _rows(c, "mgmt_reviews")
    titles = {r["title"] for r in c.execute("select title from documents where status = 'effective'")}
    assert titles == {"来料检验", "测量设备校准"}
    f = c.execute("select * from fmea_files").fetchone()
    assert f["status"] == "approved" and f["approved_by"] == "wangdan@demo.example"
    assert [r["rpn"] for r in c.execute("select rpn from fmea_rows order by seq")] == [160, 60, 90]
    ch = c.execute("select * from flow_charts").fetchone()
    assert ch["status"] == "approved" and all(r["ok"] for r in ch["resolved"].values())
    from wqops.hub.quality import tools as TL

    form = c.execute("select id from check_sheet_forms").fetchone()
    p = TL.pareto_for(c, "check_sheet", "category", form_id=form["id"])
    assert p["bars"][0]["key"] == "纸箱压坏" and p["total"] == 96
    # a second run finds the records and changes nothing
    assert all(v.startswith("已跳过") for v in DQ.load(c, ZH, TODAY).values())



def test_the_chinese_business_has_the_same_problems_on_any_day():
    """Late sales orders, a rejected lot and a receipt waiting for inspection, whatever day the demo is loaded."""
    S.activate(C.load(C.DEMO_DIR / "demo-haigang.yaml"))
    try:
        for k in range(0, 28, 3):
            today = dt.date(2026, 10, 1) + dt.timedelta(days=k)
            docs = S.build(today)
            shipped: dict[str, set] = {}
            for d in docs:
                if d.kind == "delivery":
                    shipped.setdefault(d.data["so"], set()).update(ln["line"] for ln in d.data["lines"])
            late = [d for d in docs if d.kind == "so" and d.data["due"] < today
                    and len(shipped.get(d.ref, ())) < len(d.data["lines"])]
            assert len(late) >= 2, (today, len(late))
            assert sum(1 for d in docs if d.kind == "inspection" and d.data["rejected"]) == 1
            assert {d.data["item"] for d in docs if d.kind == "receipt_draft"} == {"CBL-12-50"}
    finally:
        S.activate(None)


def test_a_deadlock_in_erpnext_is_tried_again(monkeypatch):
    """ERPNext's own background jobs may deadlock with the demo's writes (seen on the small server): the rolled-back
    write is tried again; other errors are not."""
    from wqops.erp import ErpError

    monkeypatch.setattr(LD.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ErpError("ERPNext PUT /api/resource/Purchase Receipt/X -> 500: frappe.exceptions.QueryDeadlockError: "
                           "(1020, \"Record has changed since last read in table 'tabItem'\")")
        return {"name": "X"}

    assert LD.Loader._again(flaky) == {"name": "X"} and calls["n"] == 3

    def broken():
        raise ErpError("ERPNext POST -> 417: LinkValidationError")

    with pytest.raises(ErpError, match="LinkValidationError"):
        LD.Loader._again(broken)
