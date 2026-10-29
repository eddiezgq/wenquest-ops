"""Historical ledgers (ADR-0014 item 10, step 14c): reading a spreadsheet's table, the fields each kind of ledger can
fill, the rule-based column mapping, the check of a proposed mapping, and turning each row into a record or a list of
problems. Plain code: no AI, no network, no database (tests/test_isolation.py).

A mapping says, for each field, which column holds it ({"column": header}) or that every row has the same value
({"value": "corrective"}, only for choice fields). Choice fields also have a value map from the ledger's words to
ours ("Closed" -> closed). A value the map does not cover stays unknown: the field is left empty and the row notes it,
nothing is guessed.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import unicodedata
from dataclasses import dataclass, field, replace

from wqops import i18n as I18N
from wqops.hub.docs import classify as K
from wqops.hub.docs import extract as X
from wqops.i18n import say

MAX_ROWS = 5000
MAX_COLS = 100
EXCEL_ERRORS = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}


@dataclass(frozen=True)
class Field:
    label: str
    kind: str = "text"                         # text | date | number | choice | ref
    required: bool = False
    choices: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    help: str = ""
    zero: bool = False                         # a number field: 0 is a value (a price or cost), not a missing one


NCR_STATUS = ("open", "closed", "cancelled")
CAPA_STATUS = ("draft", "investigation", "implementation", "effectiveness", "closed", "cancelled")
TARGETS: dict[str, dict] = {
    "ncr": {"label": "Nonconformance log", "perm": "quality:edit", "fields": {
        "external_no": Field("NCR number in the ledger", synonyms=("ncr no", "ncr number", "ncr #", "no", "number",
                                                                    "report no", "ncr id", "id")),
        "reported_on": Field("Date reported", "date", synonyms=("date", "date reported", "reported", "date opened",
                                                                 "opened", "found on", "date found")),
        "title": Field("Title", synonyms=("title", "subject", "summary", "problem")),
        "description": Field("Description", required=True, synonyms=("description", "nonconformance", "details",
                                                                     "description of nonconformance", "issue",
                                                                     "defect")),
        "item_code": Field("Item", synonyms=("item", "item code", "part", "part no", "part number", "sku", "product")),
        "supplier": Field("Supplier", synonyms=("supplier", "vendor")),
        "quantity": Field("Quantity", "number", synonyms=("qty", "quantity", "qty affected", "quantity affected")),
        "severity": Field("Severity", "choice", choices=("minor", "major"), synonyms=("severity", "class",
                                                                                     "classification")),
        "disposition": Field("Disposition", "choice", synonyms=("disposition", "decision"),
                             help="the company's disposition types"),
        "status": Field("Status", "choice", choices=NCR_STATUS, synonyms=("status", "state", "open/closed")),
        "closed_on": Field("Date closed", "date", synonyms=("closed", "date closed", "closed on", "close date")),
        "owner": Field("Owner", synonyms=("owner", "responsible", "assigned to", "raised by")),
        "containment": Field("Containment", synonyms=("containment", "immediate action", "correction")),
    }},
    "capa": {"label": "Corrective action log", "perm": "quality:edit", "fields": {
        "external_no": Field("CAPA number in the ledger", synonyms=("capa no", "capa number", "car no", "car #", "no",
                                                                     "number", "id", "capa id")),
        "reported_on": Field("Date opened", "date", synonyms=("date", "date opened", "opened", "date raised",
                                                               "raised")),
        "kind": Field("Corrective or preventive", "choice", required=True, choices=("corrective", "preventive"),
                      synonyms=("type", "kind", "ca/pa", "category")),
        "title": Field("Title", required=True, synonyms=("title", "subject", "problem", "summary")),
        "description": Field("Problem description", synonyms=("description", "problem description", "details")),
        "ncr": Field("Related NCR", "ref", synonyms=("ncr", "ncr no", "related ncr", "ncr ref", "source",
                                                     "reference")),
        "root_cause": Field("Root cause", synonyms=("root cause", "cause")),
        "containment": Field("Containment", synonyms=("containment", "immediate action")),
        "action": Field("Action taken", synonyms=("action", "actions", "corrective action", "action taken",
                                                   "action plan")),
        "owner": Field("Owner", synonyms=("owner", "responsible", "assigned to")),
        "risk": Field("Risk", "choice", choices=("low", "medium", "high"), synonyms=("risk", "priority")),
        "status": Field("Status", "choice", choices=CAPA_STATUS, synonyms=("status", "state")),
        "closed_on": Field("Date closed", "date", synonyms=("closed", "date closed", "closed on", "close date")),
    }},
    "supplier": {"label": "Supplier list", "perm": "purchasing:draft", "fields": {
        "supplier_name": Field("Supplier name", required=True, synonyms=("supplier", "supplier name", "vendor",
                                                                        "vendor name", "name", "company")),
        "country": Field("Country", synonyms=("country",)),
        "website": Field("Website", synonyms=("website", "web", "url")),
        "supplies": Field("What they supply", synonyms=("supplies", "products", "commodity", "category", "scope")),
        "approved_on": Field("Approved on", "date", synonyms=("approved on", "approval date", "date approved",
                                                               "approved")),
        "certificate": Field("Certificate", synonyms=("certificate", "certification", "iso", "cert")),
        "approval": Field("Approval status", synonyms=("status", "approval status", "approval")),
    }},
}


# ---------------------------------------------------------------- another system's exports (ADR-0020, 20a)
# The synonyms include the column names of the usual exports: QuickBooks, NetSuite, SAP Business One and Odoo.
YESNO = ("yes", "no")
ITEM = ("item code", "itemcode", "sku", "internal reference", "item no", "item number", "part number", "part no",
        "product code", "product/service name", "product/service", "item id", "item")
QTY = ("qty", "quantity", "ordered qty", "quantity ordered")
RATE = ("rate", "price", "unit price", "price/unit", "sales price", "unit cost")
TARGETS.update({
    "erp_item": {"label": "Items (into ERPNext)", "perm": "data:import", "doctype": "Item", "fields": {
        "item_code": Field("Item code", required=True, synonyms=(*ITEM, "name")),
        "item_name": Field("Item name", synonyms=("item name", "itemname", "display name", "product name", "name")),
        "description": Field("Description", synonyms=("description", "sales description", "item description")),
        "item_group": Field("Item group", synonyms=("item group", "itmsgrpcod", "product category", "category")),
        "stock_uom": Field("Unit of measure", synonyms=("uom", "unit", "unit of measure", "stock uom", "invntryuom",
                                                        "units type", "units", "sales unit")),
        "is_stock_item": Field("Stock item", "choice", choices=YESNO, synonyms=("maintain stock", "inventory item",
                                                                               "invntitem", "stock item",
                                                                               "track inventory", "type",
                                                                               "product type", "item type")),
        "standard_rate": Field("Selling price", "number", zero=True, synonyms=("sales price", "sales price / rate",
                                                                    "base price", "standard rate", "price")),
        "valuation_rate": Field("Cost", "number", zero=True, synonyms=("cost", "purchase cost", "purchase price",
                                                                      "avgprice", "valuation rate", "unit cost")),
    }},
    "erp_customer": {"label": "Customers (into ERPNext)", "perm": "data:import", "doctype": "Customer", "fields": {
        "customer_name": Field("Customer name", required=True, synonyms=("customer name", "customer", "cardname",
                                                                        "display name", "company name", "company",
                                                                        "name")),
        "customer_group": Field("Customer group", synonyms=("customer group", "groupcode", "customer type",
                                                            "category")),
        "territory": Field("Territory", synonyms=("territory", "region", "sales territory")),
        "tax_id": Field("Tax id", synonyms=("tax id", "federal tax id", "ein", "vat", "lictradnum", "tax number")),
        "email_id": Field("Email", synonyms=("email", "e-mail", "e_mail", "email address", "main email")),
        "mobile_no": Field("Phone", synonyms=("phone", "mobile", "phone1", "cellular", "main phone", "telephone")),
    }},
    "erp_supplier": {"label": "Suppliers (into ERPNext)", "perm": "data:import", "doctype": "Supplier", "fields": {
        "supplier_name": Field("Supplier name", required=True, synonyms=("supplier name", "supplier", "vendor name",
                                                                        "vendor", "cardname", "company name",
                                                                        "company", "name")),
        "supplier_group": Field("Supplier group", synonyms=("supplier group", "vendor type", "groupcode",
                                                            "category")),
        "country": Field("Country", synonyms=("country",)),
        "tax_id": Field("Tax id", synonyms=("tax id", "federal tax id", "ein", "vat", "lictradnum", "tax number")),
        "website": Field("Website", synonyms=("website", "web", "url")),
        "email_id": Field("Email", synonyms=("email", "e-mail", "email address", "main email")),
        "mobile_no": Field("Phone", synonyms=("phone", "mobile", "phone1", "main phone", "telephone")),
    }},
    "erp_opening_stock": {"label": "Opening stock (into ERPNext)", "perm": "data:import",
                          "doctype": "Stock Reconciliation", "fields": {
        "item_code": Field("Item code", required=True, synonyms=ITEM),
        "warehouse": Field("Warehouse", required=True, synonyms=("warehouse", "location", "whscode", "site", "bin")),
        "qty": Field("Quantity on hand", "number", required=True, synonyms=("quantity on hand", "qty on hand",
                                                                           "on hand", "onhand", "in stock",
                                                                           "available", *QTY)),
        "valuation_rate": Field("Cost per unit", "number", zero=True, synonyms=("cost", "unit cost", "valuation rate",
                                                                    "avg cost", "average cost", "avgprice")),
        "batch_no": Field("Batch or lot", synonyms=("batch", "batch no", "lot", "lot no", "lot number")),
    }},
    "erp_sales_order": {"label": "Open sales orders (into ERPNext)", "perm": "data:import", "doctype": "Sales Order",
                        "fields": {
        "order_no": Field("Order number", synonyms=("order no", "order number", "so number", "so no", "docnum",
                                                    "num", "sales order", "order #", "reference")),
        "customer": Field("Customer", required=True, synonyms=("customer", "customer name", "cardname", "name")),
        "transaction_date": Field("Order date", "date", required=True, synonyms=("order date", "date", "docdate",
                                                                  "transaction date")),
        "delivery_date": Field("Delivery date", "date", required=True, synonyms=("delivery date", "ship date",
                                                                                 "due date", "docduedate",
                                                                                 "expected ship date")),
        "item_code": Field("Item code", required=True, synonyms=ITEM),
        "qty": Field("Quantity", "number", required=True, synonyms=QTY),
        "rate": Field("Price", "number", zero=True, synonyms=RATE),
    }},
    "erp_purchase_order": {"label": "Open purchase orders (into ERPNext)", "perm": "data:import",
                           "doctype": "Purchase Order", "fields": {
        "order_no": Field("Order number", synonyms=("po number", "po no", "order no", "order number", "docnum",
                                                    "num", "purchase order", "po #", "reference")),
        "supplier": Field("Supplier", required=True, synonyms=("supplier", "vendor", "vendor name", "cardname",
                                                               "name")),
        "transaction_date": Field("Order date", "date", required=True, synonyms=("order date", "date", "docdate",
                                                                  "transaction date")),
        "schedule_date": Field("Required by", "date", required=True, synonyms=("required by", "expected date",
                                                                               "receipt date", "due date",
                                                                               "docduedate", "delivery date")),
        "item_code": Field("Item code", required=True, synonyms=ITEM),
        "qty": Field("Quantity", "number", required=True, synonyms=QTY),
        "rate": Field("Price", "number", zero=True, synonyms=RATE),
    }},
})


# ---------------------------------------------------------------- Chinese column names (ADR-0023, 23e-3)
# Old Chinese spreadsheets name their columns in Chinese. The names are added to each field's synonyms here; the
# quality registers' Chinese names are kept here too, not in packs/registers.yaml, which is part of the adopted packs.
_ITEM_ZH = ("物料编码", "物料编号", "物料代码", "料号", "品号", "存货编码", "商品编码", "产品编码", "零件号",
            "零件编号", "物料")
_QTY_ZH = ("数量", "订购数量", "订单数量", "采购数量")
_RATE_ZH = ("单价", "价格", "含税单价", "不含税单价")
_TAX_ZH = ("税号", "纳税人识别号", "统一社会信用代码")
_MAIL_ZH = ("邮箱", "电子邮件", "电子邮箱", "邮件")
_PHONE_ZH = ("电话", "手机", "联系电话", "手机号")
ZH_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "ncr": {
        "external_no": ("不合格编号", "不合格品编号", "不合格报告编号", "ncr编号", "报告编号", "编号", "单号"),
        "reported_on": ("发现日期", "报告日期", "发生日期", "开单日期", "登记日期", "检验日期", "日期"),
        "title": ("标题", "主题", "问题", "摘要"),
        "description": ("问题描述", "不合格描述", "不合格内容", "不合格情况", "缺陷描述", "异常描述", "描述", "缺陷",
                        "详细描述"),
        "item_code": (*_ITEM_ZH, "品名", "产品"),
        "supplier": ("供应商", "供应商名称", "供方", "厂商", "厂家"),
        "quantity": ("不合格数量", "不良数量", "数量"),
        "severity": ("严重程度", "严重度", "缺陷等级", "等级", "分类", "类别"),
        "disposition": ("处置", "处置方式", "处理方式", "处置结果", "处置决定", "处理结果"),
        "status": ("状态", "处理状态", "结案状态", "是否关闭"),
        "closed_on": ("关闭日期", "结案日期", "完成日期", "关闭时间"),
        "owner": ("负责人", "责任人", "处理人", "提出人", "报告人", "发现人"),
        "containment": ("围堵措施", "遏制措施", "临时措施", "应急措施", "隔离措施", "纠正"),
    },
    "capa": {
        "external_no": ("纠正措施编号", "capa编号", "car编号", "编号", "单号"),
        "reported_on": ("开立日期", "提出日期", "发起日期", "发现日期", "日期"),
        "kind": ("类型", "措施类型", "类别", "纠正/预防"),
        "title": ("标题", "主题", "问题"),
        "description": ("问题描述", "描述", "详细描述"),
        "ncr": ("不合格编号", "不合格报告编号", "关联不合格", "相关不合格", "关联ncr", "来源"),
        "root_cause": ("根本原因", "原因分析", "根因", "原因"),
        "containment": ("临时措施", "围堵措施", "遏制措施", "应急措施"),
        "action": ("纠正措施", "整改措施", "改进措施", "采取的措施", "行动计划", "措施"),
        "owner": ("负责人", "责任人"),
        "risk": ("风险", "风险等级", "优先级"),
        "status": ("状态", "处理状态"),
        "closed_on": ("关闭日期", "结案日期", "完成日期"),
    },
    "supplier": {
        "supplier_name": ("供应商", "供应商名称", "供方", "供方名称", "厂商", "厂家", "公司名称", "名称"),
        "country": ("国家", "国家/地区"),
        "website": ("网站", "网址", "官网"),
        "supplies": ("供应产品", "供货范围", "主营产品", "供应物料", "物料类别", "产品", "类别"),
        "approved_on": ("批准日期", "审批日期", "认可日期", "评定日期", "准入日期"),
        "certificate": ("证书", "认证", "资质", "体系认证"),
        "approval": ("状态", "审批状态", "批准状态", "评定结果"),
    },
    "erp_item": {
        "item_code": (*_ITEM_ZH, "编码"),
        "item_name": ("物料名称", "品名", "存货名称", "商品名称", "产品名称", "名称"),
        "description": ("描述", "规格", "规格型号"),
        "item_group": ("物料组", "物料类别", "物料分类", "存货分类", "类别"),
        "stock_uom": ("单位", "计量单位", "库存单位"),
        "is_stock_item": ("是否库存", "库存物料", "是否库存物料"),
        "standard_rate": ("售价", "销售价", "销售价格", "销售单价"),
        "valuation_rate": ("成本", "成本价", "采购价", "进价", "单位成本"),
    },
    "erp_customer": {
        "customer_name": ("客户", "客户名称", "公司名称", "名称"),
        "customer_group": ("客户分类", "客户类别", "客户组"),
        "territory": ("地区", "区域", "销售区域"),
        "tax_id": _TAX_ZH, "email_id": _MAIL_ZH, "mobile_no": _PHONE_ZH,
    },
    "erp_supplier": {
        "supplier_name": ("供应商", "供应商名称", "厂商", "公司名称", "名称"),
        "supplier_group": ("供应商分类", "供应商类别", "供应商组"),
        "country": ("国家", "国家/地区"),
        "tax_id": _TAX_ZH,
        "website": ("网站", "网址", "官网"),
        "email_id": _MAIL_ZH, "mobile_no": _PHONE_ZH,
    },
    "erp_opening_stock": {
        "item_code": _ITEM_ZH,
        "warehouse": ("仓库", "库位", "仓位", "存放地点"),
        "qty": ("库存数量", "结存数量", "在库数量", "现存量", *_QTY_ZH),
        "valuation_rate": ("成本", "单位成本", "成本单价", "单价"),
        "batch_no": ("批号", "批次", "批次号", "生产批号"),
    },
    "erp_sales_order": {
        "order_no": ("销售订单号", "订单号", "订单编号", "单据编号", "单号"),
        "customer": ("客户", "客户名称"),
        "transaction_date": ("订单日期", "下单日期", "单据日期", "日期"),
        "delivery_date": ("交货日期", "交期", "发货日期", "预计交货日期", "到期日"),
        "item_code": _ITEM_ZH, "qty": _QTY_ZH, "rate": _RATE_ZH,
    },
    "erp_purchase_order": {
        "order_no": ("采购订单号", "订单号", "订单编号", "单据编号", "单号"),
        "supplier": ("供应商", "供应商名称"),
        "transaction_date": ("订单日期", "采购日期", "下单日期", "单据日期", "日期"),
        "schedule_date": ("要求到货日期", "到货日期", "交货日期", "需求日期", "交期", "到期日"),
        "item_code": _ITEM_ZH, "qty": _QTY_ZH, "rate": _RATE_ZH,
    },
}
ZH_REGISTER_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "training": {
        "person": ("姓名", "员工姓名", "人员", "员工", "受训人", "参训人员", "学员"),
        "topic": ("培训内容", "培训课程", "培训项目", "培训主题", "课程", "技能", "内容"),
        "trained_on": ("培训日期", "培训时间", "完成日期", "日期"),
        "result": ("结果", "培训结果", "考核结果", "评估结果", "考核"),
        "trainer": ("培训人", "培训师", "讲师", "评估人", "考核人"),
        "valid_until": ("有效期至", "有效期", "复训日期", "下次培训日期", "到期日"),
    },
    "calibration": {
        "equipment": ("设备编号", "器具编号", "量具编号", "仪器编号", "管理编号", "编号"),
        "description": ("设备名称", "器具名称", "仪器名称", "名称", "规格型号"),
        "calibrated_on": ("校准日期", "检定日期", "上次校准日期", "日期"),
        "next_due": ("下次校准日期", "下次检定日期", "有效期至", "到期日"),
        "result": ("结果", "校准结果", "检定结果", "结论"),
        "by": ("校准机构", "校准单位", "检定单位", "校准人"),
        "certificate": ("证书编号", "校准证书", "证书", "报告编号"),
    },
    "audits": {
        "audit_date": ("审核日期", "日期"),
        "area": ("受审部门", "受审核部门", "审核范围", "审核区域", "部门", "过程"),
        "auditor": ("审核员", "审核人", "内审员", "审核组长"),
        "findings": ("审核发现", "发现", "观察项", "审核结果"),
        "nonconformities": ("不符合项数", "不符合项", "不合格项数"),
        "followed_up": ("跟踪验证", "验证情况", "是否关闭", "跟踪"),
    },
    "management_reviews": {
        "review_date": ("评审日期", "会议日期", "日期"),
        "attendees": ("参加人员", "出席人员", "参会人员"),
        "inputs": ("评审输入", "输入", "议程", "议题"),
        "decisions": ("评审输出", "决定", "决议", "输出", "会议纪要", "措施"),
    },
    "objectives": {
        "objective": ("质量目标", "目标", "指标"),
        "target": ("目标值", "指标值"),
        "actual": ("实际值", "实际", "完成情况", "达成值"),
        "status": ("状态", "达成情况", "是否达成"),
        "reviewed_on": ("评审日期", "统计日期", "截止日期", "日期"),
    },
    "risks": {
        "title": ("风险", "机遇", "风险/机遇", "风险描述", "事项", "描述"),
        "kind": ("类型", "类别"),
        "action": ("应对措施", "控制措施", "措施"),
        "owner": ("负责人", "责任人"),
        "reviewed_on": ("评审日期", "日期"),
    },
    "complaints": {
        "received_on": ("接收日期", "投诉日期", "收到日期", "日期"),
        "customer": ("客户", "顾客", "客户名称"),
        "kind": ("类型", "类别"),
        "description": ("投诉内容", "问题描述", "反馈内容", "描述", "内容"),
        "response": ("回复", "答复", "处理结果", "处理措施"),
        "answered_on": ("回复日期", "答复日期", "关闭日期"),
        "investigation": ("调查结果", "原因分析", "调查"),
        "reportable": ("是否上报", "需上报", "是否需要上报"),
        "reportable_reason": ("上报判定理由", "判定理由"),
        "reportable_by": ("判定人",),
        "reported_on": ("上报日期",),
        "report_ref": ("上报编号", "报告编号"),
    },
    "suppliers": {
        "supplier": ("供应商", "供应商名称", "供方", "名称"),
        "supplies": ("供应产品", "供货范围", "产品"),
        "status": ("状态", "评定结果", "审批状态"),
        "approved_on": ("批准日期", "评定日期", "评价日期", "日期"),
        "next_review": ("下次评审日期", "下次评价日期", "复评日期"),
        "basis": ("评定依据", "评价方法", "依据", "证书"),
    },
}
for _tg, _zh in ZH_SYNONYMS.items():
    for _f, _syn in _zh.items():
        _spec = TARGETS[_tg]["fields"][_f]
        TARGETS[_tg]["fields"][_f] = replace(_spec, synonyms=(*_spec.synonyms, *_syn))


REGISTER_KINDS = {"text": "text", "longtext": "text", "number": "number", "date": "date", "choice": "choice",
                  "yesno": "text"}


def add_registers(regs: dict[str, dict]) -> None:
    """The quality registers of a process pack as ledger kinds "reg_<name>" (ADR-0016, 16b): an old spreadsheet of
    training, calibration, audits and so on comes in the same way as a nonconformance log."""
    for name, r in regs.items():
        TARGETS[f"reg_{name}"] = {"label": f"Register: {r['label']}", "register": r["label"], "perm": "quality:edit",
                                  "fields": {
            f: Field(x["label"], REGISTER_KINDS.get(x.get("type"), "text"), bool(x.get("required")),
                     tuple(x.get("choices") or ()),
                     (*(x.get("synonyms") or ()), *ZH_REGISTER_SYNONYMS.get(name, {}).get(f, ())))
            for f, x in r["fields"].items()}}


def target_label(target: str) -> str:
    """A ledger kind as the reader sees it ("Nonconformance log", "Register: Training records")."""
    t = TARGETS.get(target)
    if t is None:
        return target
    if "register" in t:
        return say("Register: {name}", name=I18N.label(t["register"]))
    return I18N.label(t["label"])


def field_name(spec: Field, lower: bool = False) -> str:
    """A field's name as the reader sees it; ``lower`` for the middle of an English sentence."""
    if I18N.current() == "en":
        return spec.label.lower() if lower else spec.label
    return I18N.label(spec.label)


def join_names(items) -> str:
    return ("、" if I18N.current() == "zh" else ", ").join(items)


def fields(target: str, dispositions: dict[str, str] | None = None) -> dict[str, Field]:
    out = dict(TARGETS[target]["fields"])
    if target == "ncr" and dispositions:
        out["disposition"] = Field("Disposition", "choice", choices=tuple(dispositions),
                                   synonyms=out["disposition"].synonyms)
    return out


# ---------------------------------------------------------------- reading the table

@dataclass
class Table:
    sheets: list[str]
    sheet: str
    rows: list[tuple[int, list[str]]]           # (row number in the sheet, cells as text)
    header_row: int
    headers: list[str] = field(default_factory=list)

    def data(self) -> list[tuple[int, dict[str, str]]]:
        """The rows under the header, as {header: value}; empty rows left out."""
        out = []
        for n, cells in self.rows:
            if n <= self.header_row or not any(c.strip() for c in cells):
                continue
            out.append((n, {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(self.headers)
                            if h}))
        return out


def _cell(v) -> str:
    if v is None or (isinstance(v, str) and v.strip() in EXCEL_ERRORS):   # a formula error is no value
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\x00", "").strip()


def _text(data: bytes) -> str:
    """CSV text: UTF-8, UTF-16 (with its mark), Chinese GB18030, else Windows-1252."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("gb18030")
        if X.looks_chinese(text):                # not Western bytes that happen to decode as rare characters
            return text
    except UnicodeDecodeError:
        pass
    return data.decode("cp1252", errors="replace")


def sheets_of(name: str, data: bytes) -> dict[str, list[list[str]]]:
    ext = X.suffix(name)
    if ext == ".csv":
        csv.field_size_limit(1_000_000)
        reader = csv.reader(io.StringIO(_text(data).replace("\x00", "")))
        return {"CSV": [[c.strip() for c in r[:MAX_COLS]] for _, r in zip(range(MAX_ROWS), reader, strict=False)]}
    if ext in (".xlsx", ".xlsm"):
        import openpyxl  # noqa: PLC0415

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = {}
        for ws in wb.worksheets:
            cells = ws.iter_rows(values_only=True, max_col=MAX_COLS)       # sheets formatted far to the right
            rows = [[_cell(v) for v in row] for _, row in zip(range(MAX_ROWS), cells, strict=False)]
            while rows and not any(rows[-1]):
                rows.pop()
            out[ws.title] = [r[:max((i + 1 for i, c in enumerate(r) if c), default=0)] for r in rows]
        wb.close()
        return out
    raise ValueError(say("a ledger is an Excel (.xlsx) or CSV file"))


def guess_header(rows: list[list[str]]) -> int:
    """The header row (1-based): among the first 15 rows, the one with the most text cells that has data under it."""
    best, score = 1, -1
    for i, cells in enumerate(rows[:15]):
        filled = [c for c in cells if c.strip()]
        texts = [c for c in filled if not re.fullmatch(r"[\d.,/: -]+", c)]
        below = any(any(c.strip() for c in r) for r in rows[i + 1:i + 4])
        if below and len(texts) > score and len(texts) >= 2:
            best, score = i + 1, len(texts)
    return best


def table(name: str, data: bytes, sheet: str = "", header_row: int = 0) -> Table:
    books = sheets_of(name, data)
    names = list(books)
    if not names:
        raise ValueError(say("the file has no sheets"))
    if not sheet:                               # the sheet with the most filled rows
        sheet = max(names, key=lambda s: sum(any(c for c in r) for r in books[s]))
    if sheet not in books:
        raise ValueError(say("no sheet {sheet}; sheets: {names}", sheet=repr(sheet), names=', '.join(names)))
    rows = books[sheet]
    hr = header_row or guess_header(rows)
    if not 1 <= hr <= len(rows):
        raise ValueError(say("the header row is outside the sheet"))
    seen: dict[str, int] = {}
    headers = []
    width = max((len(r) for r in rows), default=0)
    head = rows[hr - 1] + [""] * (width - len(rows[hr - 1]))
    for i, raw in enumerate(head):              # unique, non-empty header names
        h = raw.strip() or (f"Column {i + 1}" if any(i < len(r) and r[i].strip() for r in rows[hr:]) else "")
        if h:
            base, k = h, 1
            while h in seen:
                k += 1
                h = f"{base} ({k})"
            seen[h] = 1
        headers.append(h)
    return Table(names, sheet, [(i + 1, r) for i, r in enumerate(rows)], hr, headers)


# ---------------------------------------------------------------- mapping

_HAN = re.compile(r"[\u3400-\u9fff]")
# Chinese words too general to find inside a longer column name ("编号" is in "物料编号"); they still match exactly.
_ZH_EXACT_ONLY = {"编号", "单号", "名称", "来源", "产品", "物料", "问题", "内容", "过程", "发现", "输入", "输出",
                  "实际", "调查", "跟踪", "考核", "措施", "风险", "机遇", "目标", "人员", "员工", "客户", "顾客",
                  "纠正"}


def _norm(s: str) -> str:
    """A column name or value for comparing: lower case, letters, digits, "/" and "#", and Chinese characters
    (full-width forms such as "（" and "：" are folded first)."""
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^a-z0-9/#\u3400-\u9fff]+", " ", s).strip()


CHOICE_WORDS = {
    "minor": ("minor", "min", "low", "cosmetic"), "major": ("major", "maj", "critical", "high"),
    "open": ("open", "opened", "new", "in progress", "ongoing", "pending"),
    "closed": ("closed", "close", "done", "complete", "completed", "finished", "verified"),
    "cancelled": ("cancelled", "canceled", "void", "withdrawn", "rejected"),
    "draft": ("draft", "new", "open", "opened"), "investigation": ("investigation", "investigating", "analysis"),
    "implementation": ("implementation", "implementing", "in progress", "action"),
    "effectiveness": ("effectiveness", "verification", "verify", "effectiveness check"),
    "corrective": ("corrective", "ca", "car", "corrective action"), "preventive": ("preventive", "pa", "preventative"),
    "low": ("low", "l"), "medium": ("medium", "med", "m"), "high": ("high", "h"),
    "yes": ("yes", "y", "true", "1", "x", "inventory", "stock", "tinventory"), "no": ("no", "n", "false", "0",
                                                                                     "service", "non-inventory",
                                                                                     "non inventory"),
    "use_as_is": ("use as is", "use-as-is", "uai", "accept", "concession"), "rework": ("rework", "repair", "sort"),
    "return_to_supplier": ("return to supplier", "rts", "return", "returned"), "scrap": ("scrap", "scrapped"),
}
CHOICE_WORDS_ZH = {          # the usual words of Chinese ledgers; a word not here stays unknown
    "minor": ("一般", "轻微", "次要", "轻"), "major": ("严重", "主要", "重大", "致命", "重"),
    "open": ("未关闭", "进行中", "处理中", "待处理", "打开", "开启", "新建", "未完成"),
    "closed": ("已关闭", "关闭", "已完成", "完成", "已结案", "结案", "已验证"),
    "cancelled": ("已取消", "取消", "作废", "已作废", "撤销"),
    "draft": ("草稿", "新建"), "investigation": ("调查中", "分析中", "原因分析"),
    "implementation": ("实施中", "整改中", "执行中", "进行中"),
    "effectiveness": ("效果验证", "有效性验证", "验证中"),
    "corrective": ("纠正", "纠正措施"), "preventive": ("预防", "预防措施"),
    "low": ("低",), "medium": ("中",), "high": ("高",),
    "yes": ("是", "有", "库存"), "no": ("否", "无", "服务"),
    "use_as_is": ("让步接收", "让步", "特采", "特采放行", "照用", "原样使用"),
    "rework": ("返工", "返修", "挑选", "挑选使用"),
    "return_to_supplier": ("退货", "退回供应商", "退供应商", "退回"), "scrap": ("报废",),
    # the quality registers' choices (packs/registers.yaml)
    "competent": ("合格", "胜任", "通过", "考核合格"), "needs follow-up": ("不合格", "需跟进", "待提高", "未通过"),
    "pass": ("合格", "通过", "正常"), "adjusted": ("已调整", "调整后合格", "校准后合格"), "fail": ("不合格", "失效"),
    "on track": ("正常", "按计划"), "off track": ("滞后", "落后"), "met": ("达成", "已达成", "完成"),
    "missed": ("未达成", "未完成"), "risk": ("风险",), "opportunity": ("机遇", "机会"),
    "complaint": ("投诉", "客诉"), "feedback": ("反馈", "建议"), "survey": ("满意度调查", "调查", "问卷"),
    "approved": ("合格", "批准", "已批准", "认可"), "conditional": ("有条件", "有条件批准", "试用"),
    "removed": ("取消", "已取消", "淘汰", "不合格"),
}


def _choice_hit(v: str, c: str) -> bool:
    w = _norm(v)
    return w in CHOICE_WORDS.get(c, (c,)) or w == c or w in CHOICE_WORDS_ZH.get(c, ())


def rules_mapping(target: str, t: Table, flds: dict[str, Field]) -> dict:
    """A low-confidence mapping from the header names (and, for choice fields, the words used in the column)."""
    mapping, used = {}, set()

    def phrase(syn: str, h: str) -> bool:
        if _HAN.search(syn):                    # Chinese names end in their noun: 发现日期, 来料数量, 数量（件）
            return any(w.endswith(syn) for w in _norm(h).split())
        return f" {syn} " in f" {_norm(h)} "

    for exact in (True, False):                 # exact names first, then names containing a telling phrase
        for f, spec in flds.items():
            if f in mapping:
                continue
            for syn in spec.synonyms:
                if not exact and (syn in _ZH_EXACT_ONLY if _HAN.search(syn) else len(syn) < 7 and " " not in syn):
                    continue                    # "number" alone must not catch "Part number", nor 编号 物料编号
                col = next((h for h in t.headers if h and h not in used and
                            (_norm(h) == syn if exact else phrase(syn, h))), None)
                if col:
                    mapping[f] = {"column": col}
                    used.add(col)
                    break
    values = {}
    rows = t.data()
    for f, m in mapping.items():
        spec = flds[f]
        if spec.kind != "choice":
            continue
        seen = sorted({r[m["column"]] for _, r in rows if r.get(m["column"])})
        vm = {}
        for v in seen:
            hit = next((c for c in spec.choices if _choice_hit(v, c)), None)
            if hit:
                vm[v] = hit
        values[f] = vm
    return {"mapping": mapping, "values": values, "confidence": "low", "notes": say("Matched by column names.")}


def check_mapping(target: str, t: Table, flds: dict[str, Field], proposal: dict) -> dict:
    """Keep only what fits: columns that exist, constants and mapped values among the field's choices, values that
    occur in the column. Returns the cleaned proposal and what was dropped."""
    headers = set(t.headers)
    mapping, values, dropped = {}, {}, []
    for f, m in (proposal.get("mapping") or {}).items():
        if f not in flds or not isinstance(m, dict):
            dropped.append(say("{field}: not a field of this ledger", field=f))
            continue
        if m.get("column") in headers:
            mapping[f] = {"column": m["column"]}
        elif m.get("value") and flds[f].kind == "choice" and m["value"] in flds[f].choices:
            mapping[f] = {"value": m["value"]}
        else:
            dropped.append(say("{field}: {value} is not a column or allowed value", field=f,
                               value=repr(m.get("column") or m.get("value"))))
    rows = t.data()
    for f, vm in (proposal.get("values") or {}).items():
        if f not in mapping or "column" not in mapping[f] or not isinstance(vm, dict):
            continue
        present = {r[mapping[f]["column"]] for _, r in rows}
        values[f] = {k: v for k, v in vm.items() if k in present and v in flds[f].choices}
        dropped += [f"{f}: {k!r} -> {v!r}" for k, v in vm.items() if not (k in present and v in flds[f].choices)]
    conf = proposal.get("confidence") if proposal.get("confidence") in K.LEVELS else "low"
    if dropped and conf == "high":
        conf = "medium"
    return {"mapping": mapping, "values": values, "confidence": conf, "dropped": dropped,
            "notes": str(proposal.get("notes") or "")[:1000]}


# ---------------------------------------------------------------- rows

def parse_date(s: str) -> dt.date | None:
    """A date, or None when it cannot be read or could be read two ways (03/04/2024: March 4 or 3 April)."""
    s = s.strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
    if m:
        a, b, y = (int(x) for x in m.groups())
        if a <= 12 and b <= 12 and a != b:
            return None                         # day and month cannot be told apart
        month, day = (a, b) if b > 12 or a == b else (b, a)
        try:
            return dt.date(y, month, day)
        except ValueError:
            return None
    found = K.dates_in(s)
    return found[0] if len(found) == 1 else None


def parse_number(s: str) -> float | None:
    """A plain quantity: 12, 12.5, 1,200 or 1,200.5 (a comma only between groups of three digits), with an optional
    currency sign before it and an optional unit after it; "12,5" could be twelve and a half or a typo, so it is not
    read."""
    m = re.fullmatch(r"\s*[$€£¥￥]?\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*([a-zA-Z\u3400-\u9fff]{0,5})\s*",
                     s or "")                    # also "12件", "3 个"
    return float(m.group(1).replace(",", "")) if m else None


def rows(t: Table, flds: dict[str, Field], mapping: dict, values: dict) -> list[dict]:  # noqa: PLR0912
    """Every data row as {"row": n, "values": {field: value}, "problems": [...], "ok": bool}. Missing or
    unreadable values stay out (unknown) and are named in the problems; a row without a required field is not ok."""
    out = []
    for n, r in t.data():
        vals, problems, raws = {}, [], {}
        for f, spec in flds.items():
            m = mapping.get(f)
            if not m:
                continue
            raw = m["value"] if "value" in m else r.get(m["column"], "")
            if raw == "":
                continue
            raws[f] = raw
            if spec.kind == "date":
                d = parse_date(raw)
                if d is None:
                    problems.append(say("{field}: {value} is not a date that can be read one way only",
                                        field=field_name(spec), value=repr(raw)))
                else:
                    vals[f] = d.isoformat()
            elif spec.kind == "number":
                x = parse_number(raw)
                if x is None or x < 0 or (x == 0 and not spec.zero):
                    problems.append(say("{field}: {value} is not a number of 0 or more", field=field_name(spec),
                                        value=repr(raw)) if spec.zero else
                                    say("{field}: {value} is not a quantity above 0", field=field_name(spec),
                                        value=repr(raw)))
                else:
                    vals[f] = x
            elif spec.kind == "choice":
                if "value" in m:
                    vals[f] = raw
                elif raw in values.get(f, {}):
                    vals[f] = values[f][raw]
                else:
                    problems.append(say("{field}: {value} is not matched to one of ours, left unknown",
                                        field=field_name(spec), value=repr(raw)))
            else:
                vals[f] = raw[:4000]
                if len(raw) > 4000:
                    problems.append(say("{field}: cut to its first 4000 characters", field=field_name(spec)))
        missing = [field_name(spec) for f, spec in flds.items() if spec.required and f not in vals]
        if missing:
            problems.append(say("missing {fields}", fields=join_names(missing)))
        out.append({"row": n, "values": vals, "raw": raws, "problems": problems, "ok": not missing})
    return out
