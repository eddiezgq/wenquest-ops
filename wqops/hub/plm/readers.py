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

from wqops.hub.plm import place as PL
from wqops.i18n import say

MAX_NODES = 5000
MAX_ROWS = 50000


class ReadError(ValueError):
    pass


# ---- STEP (ISO 10303-21)

_ENTITY = re.compile(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*$", re.S)


def _statements(text: str):
    """The DATA section split at ; outside quoted strings."""
    i = text.find("DATA;")
    if i < 0:
        raise ReadError(say("this is not a STEP file (no DATA section)"))
    buf, quote, body, k = [], False, text[i + 5:], 0
    while k < len(body):
        ch = body[k]
        if not quote and body.startswith("/*", k):          # comments, which may hold apostrophes
            end = body.find("*/", k + 2)
            k = len(body) if end < 0 else end + 2
            continue
        if ch == "'":
            quote = not quote
        if ch == ";" and not quote:
            yield "".join(buf).strip()
            buf = []
        else:
            buf.append(ch)
        k += 1


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


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _decode(s: str) -> str:
    """STEP's escapes: \\X2\\...\\X0\\ (UTF-16, as CAD programs write Chinese names), \\X4\\ (UTF-32), \\X\\hh,
    \\\\; control characters dropped."""
    def wide(m, enc):
        h = m.group(1)
        try:
            return bytes.fromhex(h).decode(enc, "replace")
        except ValueError:
            return ""
    s = re.sub(r"\\X2\\([0-9A-Fa-f]*)\\X0\\", lambda m: wide(m, "utf-16-be"), s)
    s = re.sub(r"\\X4\\([0-9A-Fa-f]*)\\X0\\", lambda m: wide(m, "utf-32-be"), s)
    s = re.sub(r"\\X\\([0-9A-Fa-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), s)
    return _CTRL.sub("", s.replace("\\\\", "\\"))


def read_step(data: bytes) -> dict:  # noqa: PLR0912 - one pass over the file
    try:                                   # CAD programs often write names as plain UTF-8 bytes
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "ISO-10303-21" not in text[:200]:
        raise ReadError(say("this is not a STEP file"))
    ent: dict[str, tuple[str, list[str]]] = {}
    geo: dict[str, tuple[str, list[str]]] = {}       # what places a use of a part in its assembly
    rrwt: dict[str, str] = {}                        # representation relationship -> its transformation
    for st in _statements(text):
        m = _ENTITY.match(st)
        if m and m.group(2) in ("PRODUCT", "PRODUCT_DEFINITION_FORMATION",
                                "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE", "PRODUCT_DEFINITION",
                                "NEXT_ASSEMBLY_USAGE_OCCURRENCE"):
            a = _args(m.group(3))
            need = {"PRODUCT": 2, "PRODUCT_DEFINITION": 3, "NEXT_ASSEMBLY_USAGE_OCCURRENCE": 5}.get(m.group(2), 3)
            if len(a) < need:
                raise ReadError(say("the STEP file is damaged near #{n}", n=m.group(1)))
            ent["#" + m.group(1)] = (m.group(2), a)
        elif m and m.group(2) in GEO:
            geo["#" + m.group(1)] = (m.group(2), _args(m.group(3)))
        elif (c := _COMPLEX.match(st)) and (t := _RRWT.search(c.group(2))):
            rrwt["#" + c.group(1)] = "#" + t.group(1)
    products = {k: v[1] for k, v in ent.items() if v[0] == "PRODUCT"}
    if not products:
        raise ReadError(say("the STEP file names no parts"))
    formation = {k: v[1][2] for k, v in ent.items() if v[0].startswith("PRODUCT_DEFINITION_FORMATION")}
    pd = {k: formation.get(v[1][2]) for k, v in ent.items() if v[0] == "PRODUCT_DEFINITION"}   # -> product
    uses = Counter()
    where = _placements(geo, rrwt)                   # NAUO -> placement, where the file says
    placed: dict[tuple, list | None] = {}
    for k, v in ent.items():
        if v[0] == "NEXT_ASSEMBLY_USAGE_OCCURRENCE":
            parent, child = pd.get(v[1][3]), pd.get(v[1][4])
            if parent and child:
                uses[(parent, child)] += 1
                pl = where.get(k)
                got = placed.get((parent, child), [])
                placed[(parent, child)] = None if pl is None or got is None else [*got, pl]
    if len(products) > MAX_NODES:
        raise ReadError(say("more than {n} parts in one file", n=MAX_NODES))
    nodes = []
    for k, a in products.items():
        ident, name = _decode(a[0]).strip(), _decode(a[1]).strip() or _decode(a[0]).strip()
        code = ident if ident != name and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,59}", ident) else ""
        nodes.append({"key": k, "code": code, "name": name})   # a part number only when the file gives one
    if len(nodes) > MAX_NODES:
        raise ReadError(say("more than {n} parts in one file", n=MAX_NODES))
    links = [{"parent": p, "child": c, "qty": str(n), **({"placements": placed[(p, c)]} if placed.get((p, c)) else {})}
             for (p, c), n in sorted(uses.items())]
    return {"nodes": nodes, "links": links}


GEO = ("AXIS2_PLACEMENT_3D", "CARTESIAN_POINT", "DIRECTION", "ITEM_DEFINED_TRANSFORMATION",
       "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION", "PRODUCT_DEFINITION_SHAPE")
_COMPLEX = re.compile(r"#(\d+)\s*=\s*\((.*)\)\s*$", re.S)
_RRWT = re.compile(r"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION\s*\(\s*#(\d+)\s*\)")


def _numbers(s: str) -> list[float] | None:
    try:
        return [float(x) for x in s.strip().strip("()").split(",")]
    except ValueError:
        return None


def _placements(geo: dict, rrwt: dict) -> dict[str, dict]:
    """Each assembly use (NEXT_ASSEMBLY_USAGE_OCCURRENCE) with the place the file gives it: the transformation
    from the part's frame to the assembly's (ITEM_DEFINED_TRANSFORMATION: item 2 after item 1 undone). A use the
    file gives no place, or a malformed one, is left out: never guessed."""
    def axes(ref: str):
        e = geo.get(ref)
        if not e or e[0] != "AXIS2_PLACEMENT_3D" or len(e[1]) < 2:
            return None
        def vec(r, kind):
            g = geo.get(r)
            return _numbers(g[1][1]) if g and g[0] == kind and len(g[1]) > 1 else None
        o = vec(e[1][1], "CARTESIAN_POINT")
        z = vec(e[1][2], "DIRECTION") if len(e[1]) > 2 and e[1][2].startswith("#") else None
        x = vec(e[1][3], "DIRECTION") if len(e[1]) > 3 and e[1][3].startswith("#") else None
        if o is None or len(o) != 3 or (z and len(z) != 3) or (x and len(x) != 3):
            return None
        return PL.from_axes(o, z, x)

    pds = {k: v[1][2] for k, v in geo.items() if v[0] == "PRODUCT_DEFINITION_SHAPE" and len(v[1]) > 2}
    out = {}
    for v in geo.values():
        if v[0] != "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION" or len(v[1]) < 2:
            continue
        nauo, t = pds.get(v[1][1]), geo.get(rrwt.get(v[1][0], ""))
        if not nauo or not t or t[0] != "ITEM_DEFINED_TRANSFORMATION" or len(t[1]) < 4:
            continue
        a1, a2 = axes(t[1][2]), axes(t[1][3])
        if a1 is None or a2 is None:
            continue
        try:
            out[nauo] = PL.placement(PL.mul(a2, PL.inverse(a1)))
        except PL.PlaceError:
            continue
    return out


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
    if re.fullmatch(r"\.+\d+", s):                    # .1, ..2: the digit is the level
        return int(s.lstrip("."))
    if re.fullmatch(r"\.+", s):                        # dots only: one more than the dots
        return s.count(".") + 1
    if re.fullmatch(r"\d+(\.\d+)+", s):
        return s.count(".") + 1
    raise ReadError(say("row {row}: the level {level} is not a number", row=row, level=v))


def _source(v) -> str | None:
    t = str(v or "").strip().lower()
    return "buy" if t in ("外购", "采购", "buy", "purchased", "b") else "make" if t in ("自制", "make", "m") else None


def read_excel(data: bytes) -> dict:  # noqa: PLR0912, PLR0915 - one column after another
    import openpyxl  # noqa: PLC0415

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ReadError(say("this is not an Excel file (.xlsx)")) from exc
    rows = wb.worksheets[0].iter_rows(values_only=True)
    cols, start = {}, None
    for i, r in enumerate(rows, start=1):
        found = {_head(c): j for j, c in enumerate(r or ()) if _head(c)}
        if "code" in found and ("parent" in found or "level" in found):
            cols, start = found, i
            break
        if i >= 10:
            break
    if start is None:
        raise ReadError(say("no header row: write 父件编码, 子件编码, 数量 (flat) or 层级, 编码, 数量 (levels)"))

    def get(r, k):
        j = cols.get(k)
        return r[j] if j is not None and j < len(r) else None

    nodes: dict[str, dict] = {}
    links: Counter = Counter()
    occs: dict[str, list[Counter]] = {}           # level BOMs: the parts under each appearance of an assembly
    stack: list[tuple[int, str, Counter]] = []

    def node(code, name, r):
        code = str(code).strip()
        n = nodes.setdefault(code, {"key": code, "code": code, "name": str(name or code).strip()})
        for k in ("uom", "category"):
            if get(r, k) not in (None, ""):
                n[k] = str(get(r, k)).strip()
        if _source(get(r, "source")):
            n["source"] = _source(get(r, "source"))
        return code
    for i, raw in enumerate(rows, start=start + 1):
        if i - start > MAX_ROWS:
            raise ReadError(say("more than {n} rows", n=MAX_ROWS))
        r = raw or ()
        if get(r, "code") in (None, ""):
            continue
        code = node(get(r, "code"), get(r, "name"), r)
        qty = Decimal(_qty(get(r, "qty") if get(r, "qty") not in (None, "") else 1, i))
        if "level" in cols:
            lv = _level(get(r, "level"), i)
            while stack and stack[-1][0] >= lv:
                stack.pop()
            if stack:
                stack[-1][2][code] += qty
            elif lv > 1 and occs:
                raise ReadError(say("row {row}: level {level} has no parent above it", row=i, level=lv))
            occ = Counter()
            occs.setdefault(code, []).append(occ)
            stack.append((lv, code, occ))
        else:
            parent = get(r, "parent")
            if parent not in (None, ""):
                p = str(parent).strip()
                nodes.setdefault(p, {"key": p, "code": p, "name": p})
                links[(p, code)] += qty
        if len(nodes) > MAX_NODES:
            raise ReadError(say("more than {n} parts in one file", n=MAX_NODES))
    if not nodes:
        raise ReadError(say("the file has no rows under the header"))
    for code, lst in occs.items():               # a sub-assembly repeated where it is used: its parts once
        filled = [o for o in lst if o]
        if not filled:
            continue
        if any(o != filled[0] for o in filled[1:]):
            raise ReadError(say("{code} is listed with different parts in different places", code=code))
        for c, q in filled[0].items():
            links[(code, c)] = q
    return {"nodes": list(nodes.values()),
            "links": [{"parent": p, "child": c, "qty": format(q.normalize(), "f")} for (p, c), q in links.items()]}
