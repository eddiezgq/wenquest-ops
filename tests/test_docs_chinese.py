"""Chinese files in the document library and the ledger import, without a model (ADR-0023, 23e-3): the rule
classification of Chinese file names and texts, Chinese CSV encodings, Chinese OCR, and Chinese column names and
words in old spreadsheets. Plain code: no database, no network, no model.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from wqops.hub.docs import classify as K
from wqops.hub.docs import extract as X
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import ledger_ai as LAI
from wqops.hub.docs import ledgers as LS  # noqa: F401 - adds the quality registers as ledger kinds

DISP = {"use_as_is": "Use as is", "rework": "Rework", "return_to_supplier": "Return to supplier", "scrap": "Scrap"}

QP05 = """宁波海港五金有限公司（演示） 质量管理体系文件
来料检验控制程序
文件编号：QP-05    版本号：D
生效日期：2025年9月8日
编制：张三  审核：李四  批准：王五
1 目的
规范来料检验，防止不合格品流入生产。
2 范围
适用于供应商提供的原材料、外购件的进货检验。引用 F-QA-012 不合格品处置单。
"""


def classify(name, folder, text=""):
    p = K.verify(K.rules(name, folder, text), name, folder, text)
    assert all(e["verified"] for e in p["evidence"].values()), (name, p["evidence"])
    return p


# ---------------------------------------------------------------- rule classification

def test_chinese_procedure_by_name_and_text():
    p = classify("QP-05 来料检验 版本D.pdf", "二级文件 程序文件", QP05)
    assert (p["doc_type"], p["process"], p["number"], p["revision"], p["effective_date"]) == \
        ("procedure", "receiving", "QP-05", "D", "2025-09-08")
    assert p["title"] == "来料检验控制程序" and p["owner"] == "张三" and p["language"] == "zh"
    assert p["refs"] == ["F-QA-012"]
    q = classify("QP-05来料检验.pdf", "", "")                   # the number right next to Chinese
    assert q["number"] == "QP-05" and q["doc_type"] == "procedure" and q["process"] == "receiving"


@pytest.mark.parametrize(("name", "folder", "text", "want"), [
    ("WI-03 包装作业指导书 第C版.docx", "三级文件", "包装作业指导书\n版本：C\n实施日期：2025-09-08",
     ("work_instruction", "production", "WI-03", "C")),
    ("F-QA-012 不合格品处置单.xlsx", "四级文件 程序文件", "", ("form", "nonconformance", "F-QA-012", None)),
    ("F-PU-02 供应商评价表 版本 B.xlsx", "表单", "", ("form", "purchasing", "F-PU-02", "B")),
    ("2025年9月 来料检验记录.xlsx", "质量记录", "", ("record", "receiving", None, None)),
    ("游标卡尺 校准证书 2025.pdf", "外来文件", "", ("certificate", "calibration", None, None)),
    ("QP-08 不合格品控制程序 Rev C.pdf", "程序文件", "", ("procedure", "nonconformance", "QP-08", "C")),
    ("QP-09 纠正和预防措施控制程序.docx", "", "", ("procedure", "capa", "QP-09", None)),
    ("培训签到表.docx", "表单", "", ("form", "training", None, None)),
    ("内部审核报告 2026.docx", "", "", ("record", "internal_audit", None, None)),
    ("管理评审会议纪要.docx", "", "", ("record", "management_review", None, None)),
    ("顾客投诉处理记录.xlsx", "", "", ("record", "complaints", None, None)),
    ("QP-02 文件和记录控制程序 版本号：A.docx", "", "", ("procedure", "document_control", "QP-02", "A")),
    ("产品检验规范.pdf", "", "", ("spec", "other", None, None)),
    ("GB／T 19001-2016 质量管理体系 要求.pdf", "外来文件", "", ("external", "other", None, None)),
])
def test_chinese_types_processes_numbers_revisions(name, folder, text, want):
    p = classify(name, folder, text)
    assert (p["doc_type"], p["process"], p.get("number"), p.get("revision")) == want


def test_chinese_folders_do_not_decide_over_the_file_name():
    # "程序文件" names the folder level; a form inside it is still a form
    assert classify("F-01 来料检验记录表.xlsx", "二级文件 程序文件")["doc_type"] == "form"
    assert classify("来料检验记录.xlsx", "程序文件")["doc_type"] == "record"
    assert classify("说明.docx", "程序文件")["doc_type"] == "procedure"       # nothing in the name: the folder


def test_chinese_dates_revisions_and_labels():
    d = K.dt.date(2025, 9, 8)
    assert K.dates_in("生效日期：2025年9月8日；2025-09-08；2025/9/8；2025.09.08") == [d] * 4
    assert K.dates_in("日期2025-09-08起") == [d]
    assert K.dates_in("on March 3, 2025 and 3 Mar 2025, 03/03/2025, 2025-03-03") == [K.dt.date(2025, 3, 3)] * 4
    text = "文件名称：供应商管理程序\n文件编号：QP-07\n第 C 版\n生效日期：2026年1月5日\n负责人：赵六"
    p = classify("供应商.docx", "", text)
    assert (p["title"], p["number"], p["revision"], p["effective_date"], p["owner"], p["process"]) == \
        ("供应商管理程序", "QP-07", "C", "2026-01-05", "赵六", "purchasing")
    assert "revision" not in classify("版本控制说明.docx", "", "")


def test_english_still_reads_as_before():
    p = classify("QP-08 Control of Nonconforming Product Rev C.pdf", "Procedures",
                 "Doc No. QP-08\nRev C\nEffective date: 2025-06-02\nControl of Nonconforming Product")
    assert (p["doc_type"], p["process"], p["number"], p["revision"], p["effective_date"], p["title"]) == \
        ("procedure", "nonconformance", "QP-08", "C", "2025-06-02", "Control of Nonconforming Product")


# ---------------------------------------------------------------- text from Chinese files

def test_chinese_csv_and_text_encodings():
    s = "物料编码,描述,数量\nM-001,螺栓弯曲,3\n"
    assert X.text_of("x.csv", s.encode("gb18030")).body == "物料编码 | 描述 | 数量\nM-001 | 螺栓弯曲 | 3"
    assert X.text_of("x.csv", s.encode("gbk")).body.startswith("物料编码 | 描述")
    assert X.text_of("x.csv", s.encode("utf-8-sig")).body.startswith("物料编码 | 描述")
    assert X.text_of("x.txt", s.encode("utf-16")).body.startswith("物料编码,描述")
    # Western Windows-1252 text that also decodes as GB18030 stays Western
    for w in ("Müller GmbH, Größe", "Café procedure", "Señor Pérez, Zürich", "naïve façade"):
        assert X.text_of("x.txt", w.encode("cp1252")).body == w
        assert LG.table("x.csv", f"Supplier\n{w}\n".encode("cp1252")).data()[0][1]["Supplier"] == w.split(",")[0]
    assert LG.table("x.csv", s.encode("utf-8-sig")).headers == ["物料编码", "描述", "数量"]
    assert LG.table("x.csv", s.encode("gbk")).headers == ["物料编码", "描述", "数量"]


def test_ocr_language_follows_the_installed_data(monkeypatch):
    import pytesseract

    X.ocr_lang.cache_clear()
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    assert X.ocr_lang() == "eng"
    X.ocr_lang.cache_clear()
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["chi_sim", "eng", "osd"])
    assert X.ocr_lang() == "chi_sim+eng"
    X.ocr_lang.cache_clear()

    def broken(config=""):
        raise OSError("no tesseract")
    monkeypatch.setattr(pytesseract, "get_languages", broken)
    assert X.ocr_lang() == "eng"
    X.ocr_lang.cache_clear()


def _cjk_font(size):
    from PIL import ImageFont

    for path in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return None


def test_chinese_scan_is_read_when_chinese_ocr_is_installed():
    from PIL import Image, ImageDraw

    X.ocr_lang.cache_clear()
    if not X._ocr_ready() or X.ocr_lang() != "chi_sim+eng":
        pytest.skip("Tesseract with Chinese (chi_sim) is not installed here")
    font = _cjk_font(48)
    if font is None:
        pytest.skip("no Chinese font to draw the test scan")
    img = Image.new("L", (1400, 300), 255)
    d = ImageDraw.Draw(img)
    d.text((40, 40), "来料检验控制程序", fill=0, font=font)
    d.text((40, 160), "文件编号：QP-05 版本：D", fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    t = X.text_of("扫描件.png", buf.getvalue())
    assert t.status == "ocr" and "来料检验" in t.body and "QP-05" in t.body, t.body


# ---------------------------------------------------------------- ledgers with Chinese column names

def _xlsx(rows, title="Sheet1"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def targets():
    return {t: LG.fields(t, DISP) for t in LG.TARGETS}


NCR_ROWS = [
    ["不合格品台账（2025年）"],
    ["不合格编号", "发现日期", "物料编码", "供应商", "问题描述", "不合格数量", "严重程度", "处置方式", "状态",
     "关闭日期", "责任人"],
    ["NCR-2025-001", "2025-03-04", "M-1001", "宁波某五金（演示）", "螺纹不良", "200件", "一般", "让步接收", "已关闭",
     "2025/3/20", "张三"],
    ["NCR-2025-002", "2025年4月1日", "M-1002", "", "尺寸超差", "15", "严重", "退货", "进行中", "", "李四"],
    ["NCR-2025-003", "2025.05.06", "M-1003", "", "表面划伤", "3", "轻微", "返工", "关闭", "2025-05-08", "王五"],
    ["NCR-2025-004", "2025-06-01", "M-1004", "", "生锈", "8", "一般", "报废", "作废", "", ""],
    ["NCR-2025-005", "2025-06-02", "M-1005", "", "包装破损", "2", "一般", "挑选后使用", "未关闭", "", ""],
]


def test_chinese_ncr_log_is_mapped_by_the_rules():
    tg = targets()
    t = LG.table("不合格品台账.xlsx", _xlsx(NCR_ROWS))
    assert t.header_row == 2
    assert LAI.rules_target(t, tg) == "ncr"
    m = LG.rules_mapping("ncr", t, tg["ncr"])
    assert {f: c["column"] for f, c in m["mapping"].items()} == {
        "external_no": "不合格编号", "reported_on": "发现日期", "item_code": "物料编码", "supplier": "供应商",
        "description": "问题描述", "quantity": "不合格数量", "severity": "严重程度", "disposition": "处置方式",
        "status": "状态", "closed_on": "关闭日期", "owner": "责任人"}
    assert m["values"]["disposition"] == {"让步接收": "use_as_is", "退货": "return_to_supplier", "返工": "rework",
                                          "报废": "scrap"}                  # "挑选后使用" is not guessed
    assert m["values"]["status"] == {"已关闭": "closed", "进行中": "open", "关闭": "closed", "作废": "cancelled",
                                     "未关闭": "open"}
    assert m["values"]["severity"] == {"一般": "minor", "严重": "major", "轻微": "minor"}
    rows = {r["row"]: r for r in LG.rows(t, tg["ncr"], m["mapping"], m["values"])}
    r3 = rows[3]["values"]
    assert r3["reported_on"] == "2025-03-04" and r3["closed_on"] == "2025-03-20" and r3["quantity"] == 200
    assert (r3["disposition"], r3["status"], r3["severity"]) == ("use_as_is", "closed", "minor")
    assert rows[4]["values"]["reported_on"] == "2025-04-01" and rows[5]["values"]["reported_on"] == "2025-05-06"
    assert "disposition" not in rows[7]["values"] and rows[7]["problems"]          # unknown, not guessed
    assert all(r["ok"] for r in rows.values())


def test_chinese_partial_column_names():
    tg = targets()
    t = LG.table("x.xlsx", _xlsx([["编号", "开立日期", "零件编号", "缺陷描述（详细）", "来料数量（件）"],
                                  ["1", "2025-01-02", "P-1", "毛刺", "5"]]))
    m = {f: c["column"] for f, c in LG.rules_mapping("ncr", t, tg["ncr"])["mapping"].items()}
    assert m == {"external_no": "编号", "reported_on": "开立日期", "item_code": "零件编号",
                 "description": "缺陷描述（详细）", "quantity": "来料数量（件）"}
    t = LG.table("x.csv", "序号,客户编号,描述\n1,C-9,毛刺\n".encode())
    m = LG.rules_mapping("ncr", t, tg["ncr"])["mapping"]
    assert m == {"description": {"column": "描述"}}                          # 编号 alone does not catch 客户编号
    assert LG.parse_number("12件") == 12 and LG.parse_number("￥1,200.5") == 1200.5


def test_chinese_capa_log():
    tg = targets()
    t = LG.table("纠正措施.xlsx", _xlsx([
        ["纠正措施编号", "开立日期", "措施类型", "标题", "根本原因", "纠正措施", "责任人", "状态", "不合格编号"],
        ["CAR-01", "2025-02-01", "纠正", "螺纹不良", "刀具磨损", "更换刀具", "张三", "实施中", "NCR-2025-001"],
        ["CAR-02", "2025-02-03", "预防", "包装破损", "", "", "李四", "已关闭", ""]]))
    assert LAI.rules_target(t, tg) == "capa"
    m = LG.rules_mapping("capa", t, tg["capa"])
    cols = {f: c["column"] for f, c in m["mapping"].items()}
    assert cols["ncr"] == "不合格编号" and cols["kind"] == "措施类型" and cols["action"] == "纠正措施"
    assert m["values"]["kind"] == {"纠正": "corrective", "预防": "preventive"}
    assert m["values"]["status"] == {"实施中": "implementation", "已关闭": "closed"}


def test_chinese_training_register():
    tg = targets()
    assert "reg_training" in tg
    t = LG.table("培训记录.xlsx", _xlsx([
        ["姓名", "培训内容", "日期", "结果", "培训人", "有效期至"],
        ["张三", "来料检验程序 QP-05", "2025-03-01", "合格", "李四", "2026-03-01"],
        ["王五", "叉车安全操作", "2025年3月2日", "需跟进", "李四", ""],
        ["赵六", "5S", "2025-03-03", "良好", "", ""]], title="培训"))
    # a register is chosen by the person (the rules guess one only when no other ledger fits at all)
    m = LG.rules_mapping("reg_training", t, tg["reg_training"])
    assert {f: c["column"] for f, c in m["mapping"].items()} == {
        "person": "姓名", "topic": "培训内容", "trained_on": "日期", "result": "结果", "trainer": "培训人",
        "valid_until": "有效期至"}
    assert m["values"]["result"] == {"合格": "competent", "需跟进": "needs follow-up"}   # "良好" stays unknown
    rows = LG.rows(t, tg["reg_training"], m["mapping"], m["values"])
    assert rows[1]["values"]["trained_on"] == "2025-03-02" and all(r["ok"] for r in rows)
    assert "result" not in rows[2]["values"] and rows[2]["problems"]


def test_chinese_calibration_and_supplier_registers():
    tg = targets()
    t = LG.table("计量器具台账.xlsx", _xlsx([
        ["器具编号", "器具名称", "校准日期", "下次校准日期", "校准结果", "校准机构", "证书编号"],
        ["G-01", "游标卡尺", "2025-01-10", "2026-01-10", "合格", "宁波计量所（演示）", "C2025-001"]]))
    m = LG.rules_mapping("reg_calibration", t, tg["reg_calibration"])
    assert {f: c["column"] for f, c in m["mapping"].items()} == {
        "equipment": "器具编号", "description": "器具名称", "calibrated_on": "校准日期", "next_due": "下次校准日期",
        "result": "校准结果", "by": "校准机构", "certificate": "证书编号"}
    assert m["values"]["result"] == {"合格": "pass"}
    t = LG.table("合格供应商名录.csv", "供应商名称,供应产品,状态,评定日期\n甲公司（演示）,螺栓,合格\n乙公司（演示）,"
                 "垫片,有条件,2025-01-01\n".encode("gbk"))
    m = LG.rules_mapping("reg_suppliers", t, tg["reg_suppliers"])
    assert m["mapping"]["supplier"] == {"column": "供应商名称"} and m["values"]["status"] == {
        "合格": "approved", "有条件": "conditional"}


def test_every_chinese_synonym_names_a_real_field():
    for tg, flds in LG.ZH_SYNONYMS.items():
        assert set(flds) <= set(LG.TARGETS[tg]["fields"]), tg
    for reg, flds in LG.ZH_REGISTER_SYNONYMS.items():
        assert set(flds) <= set(LG.TARGETS[f"reg_{reg}"]["fields"]), reg
    for f, spec in LG.TARGETS["ncr"]["fields"].items():          # English synonyms kept, first
        assert spec.synonyms[0].isascii(), f
