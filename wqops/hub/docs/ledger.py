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
from dataclasses import dataclass, field

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


REGISTER_KINDS = {"text": "text", "longtext": "text", "number": "number", "date": "date", "choice": "choice",
                  "yesno": "text"}


def add_registers(regs: dict[str, dict]) -> None:
    """The quality registers of a process pack as ledger kinds "reg_<name>" (ADR-0016, 16b): an old spreadsheet of
    training, calibration, audits and so on comes in the same way as a nonconformance log."""
    for name, r in regs.items():
        TARGETS[f"reg_{name}"] = {"label": f"Register: {r['label']}", "perm": "quality:edit", "fields": {
            f: Field(x["label"], REGISTER_KINDS.get(x.get("type"), "text"), bool(x.get("required")),
                     tuple(x.get("choices") or ()),
                     tuple(x.get("synonyms") or ())) for f, x in r["fields"].items()}}


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
        if re.search(r"[\u4e00-\u9fff]", text):
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

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9/#]+", " ", s.lower()).strip()


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


def rules_mapping(target: str, t: Table, flds: dict[str, Field]) -> dict:
    """A low-confidence mapping from the header names (and, for choice fields, the words used in the column)."""
    mapping, used = {}, set()

    def phrase(syn: str, h: str) -> bool:
        return f" {syn} " in f" {_norm(h)} "

    for exact in (True, False):                 # exact names first, then names containing a telling phrase
        for f, spec in flds.items():
            if f in mapping:
                continue
            for syn in spec.synonyms:
                if not exact and len(syn) < 7 and " " not in syn:
                    continue                    # "number" alone must not catch "Part number"
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
            hit = next((c for c in spec.choices if _norm(v) in CHOICE_WORDS.get(c, (c,)) or _norm(v) == c), None)
            if hit:
                vm[v] = hit
        values[f] = vm
    return {"mapping": mapping, "values": values, "confidence": "low", "notes": "Matched by column names."}


def check_mapping(target: str, t: Table, flds: dict[str, Field], proposal: dict) -> dict:
    """Keep only what fits: columns that exist, constants and mapped values among the field's choices, values that
    occur in the column. Returns the cleaned proposal and what was dropped."""
    headers = set(t.headers)
    mapping, values, dropped = {}, {}, []
    for f, m in (proposal.get("mapping") or {}).items():
        if f not in flds or not isinstance(m, dict):
            dropped.append(f"{f}: not a field of this ledger")
            continue
        if m.get("column") in headers:
            mapping[f] = {"column": m["column"]}
        elif m.get("value") and flds[f].kind == "choice" and m["value"] in flds[f].choices:
            mapping[f] = {"value": m["value"]}
        else:
            dropped.append(f"{f}: {m.get('column') or m.get('value')!r} is not a column or allowed value")
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
    m = re.fullmatch(r"\s*[$€£¥]?\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*([a-zA-Z]{0,5})\s*", s or "")
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
                    problems.append(f"{spec.label}: {raw!r} is not a date that can be read one way only")
                else:
                    vals[f] = d.isoformat()
            elif spec.kind == "number":
                x = parse_number(raw)
                if x is None or x < 0 or (x == 0 and not spec.zero):
                    problems.append(f"{spec.label}: {raw!r} is not " + ("a number of 0 or more" if spec.zero
                                                                         else "a quantity above 0"))
                else:
                    vals[f] = x
            elif spec.kind == "choice":
                if "value" in m:
                    vals[f] = raw
                elif raw in values.get(f, {}):
                    vals[f] = values[f][raw]
                else:
                    problems.append(f"{spec.label}: {raw!r} is not matched to one of ours, left unknown")
            else:
                vals[f] = raw[:4000]
                if len(raw) > 4000:
                    problems.append(f"{spec.label}: cut to its first 4000 characters")
        missing = [spec.label for f, spec in flds.items() if spec.required and f not in vals]
        if missing:
            problems.append("missing " + ", ".join(missing))
        out.append({"row": n, "values": vals, "raw": raws, "problems": problems, "ok": not missing})
    return out
