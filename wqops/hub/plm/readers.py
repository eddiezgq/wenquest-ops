"""Reading design data, step 26e (ADR-0026): the assembly structure of a STEP file (products and how many of each
are used in each assembly; no geometry), and an Excel BOM written either flat (parent, child, quantity) or with a
level column (1, 2, 3, ...). Both give the same shape as a FreeCAD push:

    {"nodes": [{"key", "code", "name", "uom"?, "source"?, "category"?}], "links": [{"parent", "child", "qty"}]}

Plain code: no AI, no network.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from wqops.i18n import say

MAX_NODES = 5000


class ReadError(ValueError):
    pass


# ---- STEP (ISO 10303-21)

_ENTITY = re.compile(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*$", re.S)


def _statements(text: str):
    """The DATA section split at ; outside quoted strings."""
    i = text.find("DATA;")
    if i < 0:
        raise ReadError(say("this is not a STEP file (no DATA section)"))
    buf, quote = [], False
    for ch in text[i + 5:]:
        if ch == "'":
            quote = not quote
        if ch == ";" and not quote:
            yield "".join(buf).strip()
            buf = []
        else:
            buf.append(ch)


def _args(s: str) -> list[str]:
    """Top-level arguments of an entity (strings unquoted, references kept as #n)."""
    out, depth, quote, cur = [], 0, False, []
    for ch in s:
        if ch == "'":
            quote = not quote
        if not quote and ch in "(":
            depth += 1
        if not quote and ch in ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return [a[1:-1].replace("''", "'") if len(a) >= 2 and a[0] == "'" and a[-1] == "'" else a for a in out]


def _decode(s: str) -> str:
    """STEP's \\X2\\...\\X0\\ escapes (UTF-16 hex), as CAD programs write Chinese names."""
    def x2(m):
        h = m.group(1)
        return "".join(chr(int(h[k:k + 4], 16)) for k in range(0, len(h), 4))
    return re.sub(r"\\X2\\([0-9A-Fa-f]+)\\X0\\", x2, s)


def read_step(data: bytes) -> dict:
    try:                                   # CAD programs often write names as plain UTF-8 bytes
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "ISO-10303-21" not in text[:200]:
        raise ReadError(say("this is not a STEP file"))
    ent: dict[str, tuple[str, list[str]]] = {}
    for st in _statements(text):
        m = _ENTITY.match(st)
        if m and m.group(2) in ("PRODUCT", "PRODUCT_DEFINITION_FORMATION",
                                "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE", "PRODUCT_DEFINITION",
                                "NEXT_ASSEMBLY_USAGE_OCCURRENCE"):
            ent["#" + m.group(1)] = (m.group(2), _args(m.group(3)))
    products = {k: v[1] for k, v in ent.items() if v[0] == "PRODUCT"}
    if not products:
        raise ReadError(say("the STEP file names no parts"))
    formation = {k: v[1][2] for k, v in ent.items() if v[0].startswith("PRODUCT_DEFINITION_FORMATION")}
    pd = {k: formation.get(v[1][2]) for k, v in ent.items() if v[0] == "PRODUCT_DEFINITION"}   # -> product
    uses = Counter()
    for v in ent.values():
        if v[0] == "NEXT_ASSEMBLY_USAGE_OCCURRENCE":
            parent, child = pd.get(v[1][3]), pd.get(v[1][4])
            if parent and child:
                uses[(parent, child)] += 1
    nodes = []
    for k, a in products.items():
        ident, name = _decode(a[0]).strip(), _decode(a[1]).strip() or _decode(a[0]).strip()
        code = ident if ident != name and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,59}", ident) else ""
        nodes.append({"key": k, "code": code, "name": name})   # a part number only when the file gives one
    if len(nodes) > MAX_NODES:
        raise ReadError(say("more than {n} parts in one file", n=MAX_NODES))
    links = [{"parent": p, "child": c, "qty": str(n)} for (p, c), n in sorted(uses.items())]
    return {"nodes": nodes, "links": links}


# ---- Excel

HEADS = {
    "parent": ("父件编码", "父件", "上级编码", "parent", "parent code"),
    "level": ("层级", "层次", "级别", "level"),
    "code": ("子件编码", "编码", "物料编码", "零件编码", "code", "item code", "part number", "child", "child code"),
    "name": ("名称", "子件名称", "物料名称", "零件名称", "name", "description"),
    "qty": ("数量", "用量", "qty", "quantity"),
    "uom": ("单位", "uom", "unit"),
    "source": ("自制/外购", "自制外购", "来源", "make/buy", "source"),
    "category": ("类别", "category"),
}


def _head(cell) -> str | None:
    t = str(cell or "").strip().lower()
    for k, names in HEADS.items():
        if t in names:
            return k
    return None


def _qty(v, row: int) -> str:
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ReadError(say("row {row}: the quantity {qty} is not a number", row=row, qty=v)) from exc
    if not d.is_finite() or d <= 0:
        raise ReadError(say("row {row}: the quantity {qty} is not a number", row=row, qty=v))
    return format(d.normalize(), "f")


def _level(v, row: int) -> int:
    """1, 2, 3 · .1, ..2 (dots before) · 1.2.1 (dotted path)."""
    s = str(v if v is not None else "").strip()
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\.+\d*", s):
        return s.count(".") + 1
    if re.fullmatch(r"\d+(\.\d+)+", s):
        return s.count(".") + 1
    raise ReadError(say("row {row}: the level {level} is not a number", row=row, level=v))


def _source(v) -> str | None:
    t = str(v or "").strip().lower()
    return "buy" if t in ("外购", "采购", "buy", "purchased", "b") else "make" if t in ("自制", "make", "m") else None


def read_excel(data: bytes) -> dict:  # noqa: PLR0912 - one column after another
    import openpyxl  # noqa: PLC0415

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ReadError(say("this is not an Excel file (.xlsx)")) from exc
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    cols, start = {}, None
    for i, r in enumerate(rows[:10]):
        found = {_head(c): j for j, c in enumerate(r) if _head(c)}
        if "code" in found and ("parent" in found or "level" in found):
            cols, start = found, i + 1
            break
    if start is None:
        raise ReadError(say("no header row: write 父件编码, 子件编码, 数量 (flat) or 层级, 编码, 数量 (levels)"))
    nodes: dict[str, dict] = {}
    links: Counter = Counter()
    stack: list[tuple[int, str]] = []

    def node(code, name, r):
        code = str(code).strip()
        n = nodes.setdefault(code, {"key": code, "code": code, "name": str(name or code).strip()})
        for k in ("uom", "category"):
            if k in cols and r[cols[k]] not in (None, ""):
                n[k] = str(r[cols[k]]).strip()
        if "source" in cols and _source(r[cols["source"]]):
            n["source"] = _source(r[cols["source"]])
        return code
    for i, r in enumerate(rows[start:], start=start + 1):
        if not r or r[cols["code"]] in (None, ""):
            continue
        code = node(r[cols["code"]], r[cols["name"]] if "name" in cols else None, r)
        qty = _qty(r[cols["qty"]] if "qty" in cols and r[cols["qty"]] not in (None, "") else 1, i)
        if "level" in cols:
            lv = _level(r[cols["level"]], i)
            while stack and stack[-1][0] >= lv:
                stack.pop()
            if stack:
                links[(stack[-1][1], code)] += Decimal(qty)
            elif lv > 1:
                raise ReadError(say("row {row}: level {level} has no parent above it", row=i, level=lv))
            stack.append((lv, code))
        else:
            parent = r[cols["parent"]]
            if parent not in (None, ""):
                p = str(parent).strip()
                nodes.setdefault(p, {"key": p, "code": p, "name": p})
                links[(p, code)] += Decimal(qty)
        if len(nodes) > MAX_NODES:
            raise ReadError(say("more than {n} parts in one file", n=MAX_NODES))
    if not nodes:
        raise ReadError(say("the file has no rows under the header"))
    return {"nodes": list(nodes.values()),
            "links": [{"parent": p, "child": c, "qty": format(q.normalize(), "f")} for (p, c), q in links.items()]}
