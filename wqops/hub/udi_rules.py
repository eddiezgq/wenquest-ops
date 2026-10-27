"""Unique device identification and barcodes (ADR-0020, 20b). Pure functions: no database, no AI, no network.

Reads what a scanner returns from a GS1 code (GS1 DataMatrix, GS1 QR, GS1-128, its printed form with brackets or a
GS1 Digital Link web address), a HIBC code (primary, secondary or both in one) or an ICCBBA ISBT 128 code, and says
which fields it holds: the device identifier, lot, serial number and dates. Builds the same codes for a label from the
identifier the company got from its issuing agency; WenQuest Ops never makes up an identifier, it only checks the
check digit and the form. ZPL is the label language of Zebra printers.
"""

from __future__ import annotations

import datetime as dt
import re

from wqops.i18n import say

GS = "\x1d"
SYMBOLOGY = re.compile(r"^\][A-Za-z][0-9A-Za-z]")       # ]d2, ]Q3, ]C1: what the scanner may put first
# GS1 application identifiers read here: fixed length of their data, or None when it runs to a GS or the end
AIS = {"00": 18, "01": 14, "02": 14, "10": None, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2,
       "21": None, "22": None, "30": None, "240": None, "241": None, "250": None, "7003": 10}
FIELDS = {"01": "di", "10": "lot", "21": "serial", "11": "production_date", "17": "expiry_date", "13": "pack_date",
          "15": "best_before", "16": "sell_by", "30": "quantity", "00": "sscc", "02": "contained_di", "22": "cpv",
          "240": "additional_id", "241": "customer_part", "250": "secondary_serial", "7003": "expiry_time",
          "20": "variant", "12": "due_date"}
DATES = {"11", "12", "13", "15", "16", "17"}
HIBC_SET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%"
CSET82 = re.compile(r"[!\"%&'*+,\-./0-9:;<=>?A-Z_a-z]{1,20}")   # GS1 character set 82, without ( ) of the printed form


class UdiError(ValueError):
    pass


# ---------------------------------------------------------------- check digits

def gs1_check(digits: str) -> int:
    """The GS1 mod-10 check digit for the digits before it (GTIN-8, 12, 13, 14, SSCC)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10


def gtin14(v: str) -> str:
    """A GTIN-8, 12, 13 or 14 as 14 digits, if its check digit is right."""
    v = re.sub(r"\s", "", str(v or ""))
    if not re.fullmatch(r"\d{8}|\d{12,14}", v):
        raise UdiError(say("a GTIN has 8, 12, 13 or 14 digits"))
    if gs1_check(v[:-1]) != int(v[-1]):
        raise UdiError(say("the check digit of {v} is wrong: it should be {v2}", v=v, v2=gs1_check(v[:-1])))
    return v.zfill(14)


def hibc_check(data: str) -> str:
    """The HIBC mod-43 check character of everything before it, the leading + included."""
    try:
        return HIBC_SET[sum(HIBC_SET.index(c) for c in data) % 43]
    except ValueError as exc:
        raise UdiError(say("a HIBC code has only digits, capital letters and - . space $ / + %")) from exc


def yymmdd(s: str, today: dt.date | None = None) -> dt.date:
    """A GS1 date: YYMMDD, day 00 meaning the last day of the month, the century by GS1's 50-year window."""
    if not re.fullmatch(r"\d{6}", s):
        raise UdiError(say("{s} is not a date YYMMDD", s=repr(s)))
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:])
    if not 1 <= mm <= 12:
        raise UdiError(say("{s} is not a real date", s=repr(s)))
    now = (today or dt.date.today()).year  # noqa: DTZ011 - only the century window
    year = now // 100 * 100 + yy
    if year - now > 50:
        year -= 100
    elif now - year > 49:
        year += 100
    if dd == 0:
        nxt = dt.date(year + (mm == 12), mm % 12 + 1, 1)
        return nxt - dt.timedelta(days=1)
    try:
        return dt.date(year, mm, dd)
    except ValueError as exc:
        raise UdiError(say("{s} is not a real date", s=repr(s))) from exc


# ---------------------------------------------------------------- reading

def _gs1_elements(data: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(data):
        if data[i] == GS:
            i += 1
            continue
        ai = next((a for a in sorted(AIS, key=len, reverse=True) if data.startswith(a, i)), None)
        if ai is None:
            raise UdiError(say("unknown GS1 application identifier at {data}", data=repr(data[i:i + 4])))
        i += len(ai)
        n = AIS[ai]
        if n is None:
            end = data.find(GS, i)
            end = len(data) if end < 0 else end
        else:
            end = i + n
            if end > len(data):
                raise UdiError(say("({ai}) needs {n} characters", ai=ai, n=n))
        out.append((ai, data[i:end]))
        i = end
    return out


def _from_brackets(s: str) -> str:
    """"(01)0001...(10)ABC" -> the element string with a GS after each variable-length field."""
    parts = re.findall(r"\((\d{2,4})\)([^(]*)", s)
    if not parts or "".join(f"({a}){v}" for a, v in parts) != s:
        raise UdiError(say("not a GS1 code in brackets"))
    return "".join(a + v + (GS if AIS.get(a, 0) is None and k < len(parts) - 1 else "")
                   for k, (a, v) in enumerate(parts))


def _unquote(v: str) -> str:
    """Percent-decoding of a web address part (%2F -> /), by hand: no network library in this module."""
    b, out, i = v.encode(), bytearray(), 0
    while i < len(b):
        if b[i] == 0x25 and re.fullmatch(rb"[0-9A-Fa-f]{2}", b[i + 1:i + 3]):
            out.append(int(b[i + 1:i + 3], 16))
            i += 3
        else:
            out.append(b[i])
            i += 1
    try:
        return out.decode()
    except UnicodeDecodeError as exc:
        raise UdiError(say("the web address has a broken %-code")) from exc


def _from_link(s: str) -> str:
    """A GS1 Digital Link web address -> the element string. The path may start with the company's own folders;
    from (01) on it is key/value pairs."""
    rest = s.split("://", 1)[1]                        # read by hand: this module never opens the address
    path, _, query = rest.split("#")[0].partition("?")
    seg = [x for x in path.split("/")[1:] if x]
    start = next((k for k in range(len(seg) - 1) if seg[k] == "01" and re.fullmatch(r"\d{8,14}", seg[k + 1])), None)
    if start is None:
        raise UdiError(say("not a GS1 Digital Link address"))
    out = []
    for k in range(start, len(seg) - 1, 2):
        if seg[k] in AIS:
            out.append((seg[k], _unquote(seg[k + 1])))
    for pair in query.split("&"):
        a, _, v = pair.partition("=")
        if a in AIS and v:
            out.append((a, _unquote(v)))
    return "".join(a + v + (GS if AIS[a] is None else "") for a, v in out).rstrip(GS)


def parse_gs1(data: str, today: dt.date | None = None) -> dict:
    out: dict = {"agency": "gs1", "elements": {}}
    for ai, v in _gs1_elements(data):
        out["elements"][ai] = v
        name = FIELDS.get(ai, f"ai_{ai}")
        if ai in DATES:
            out[name] = yymmdd(v, today).isoformat()
        elif ai == "01":
            out[name] = gtin14(v)
        else:
            out[name] = v
    if "di" not in out:
        raise UdiError(say("the GS1 code has no device identifier (01)"))
    return out


def _hibc_secondary(s: str, today: dt.date | None) -> dict:
    """The HIBC secondary data, starting with "$": "$" lot, "$+" serial, or "$$" / "$$+" with an expiry date in
    one of the date formats (flag 2 to 7; none means MMYY) before the lot or serial."""
    if not s.startswith("$"):
        raise UdiError(say("the HIBC secondary data starts with $"))
    if s.startswith("$$"):
        rest = s[2:]
        kind = "serial" if rest.startswith("+") else "lot"
        rest = rest[1:] if kind == "serial" else rest
        if rest[:1] in ("8", "9"):
            raise UdiError(say("HIBC codes with a quantity ($$8, $$9) are not read yet"))
        flag = rest[0] if rest and rest[0] in "234567" else ""
        rest = rest[len(flag):]
        n = {"": 4, "2": 6, "3": 6, "4": 8, "5": 5, "6": 7, "7": 0}[flag]
        raw, rest = rest[:n], rest[n:]
        out: dict = {}
        if flag in {"", "2"}:
            if not re.fullmatch(r"\d{4}" if flag == "" else r"\d{6}", raw):
                raise UdiError(say("the HIBC expiry date cannot be read"))
            out["expiry_date"] = yymmdd(raw[2:4] + raw[:2] + "00" if flag == "" else raw[4:] + raw[:4],
                                        today).isoformat()
        elif flag in "34":
            out["expiry_date"] = yymmdd(raw[:6], today).isoformat()
        elif flag in "56":
            if not re.fullmatch(r"\d+", raw) or len(raw) != n:
                raise UdiError(say("the HIBC expiry date cannot be read"))
            year = yymmdd(raw[:2] + "0101", today).year
            out["expiry_date"] = (dt.date(year, 1, 1) + dt.timedelta(days=int(raw[2:5]) - 1)).isoformat()
        out[kind] = rest
        return out
    if s.startswith("$+"):
        return {"serial": s[2:]}
    return {"lot": s[1:]}


def parse_hibc(data: str, today: dt.date | None = None) -> dict:
    if not data.startswith("+") or len(data) < 3:
        raise UdiError(say("not a HIBC code"))
    body, check = data[:-1], data[-1]
    if hibc_check(body) != check:
        raise UdiError(say("the HIBC check character is wrong: it should be {body}", body=hibc_check(body)))
    out: dict = {"agency": "hibcc"}
    if body.startswith("+$"):                            # secondary code on its own: its last character links it
        if len(body) < 4:                                # to the primary code (that code's check character)
            raise UdiError(say("the HIBC secondary code is too short"))
        out.update(_hibc_secondary(body[1:-1], today), link=body[-1])
        return out
    primary, _, secondary = body[1:].partition("/")
    m = re.fullmatch(r"([A-Z][A-Z0-9]{3})([A-Z0-9]{1,18})(\d)", primary)
    if not m:
        raise UdiError(say("the HIBC primary data is not LIC (4), product number (1-18) and unit of measure (1)"))
    out.update(lic=m.group(1), pcn=m.group(2), unit=m.group(3), di=f"+{primary}")
    if secondary:
        out.update(_hibc_secondary(secondary, today))
    return out


def parse(code: str, today: dt.date | None = None) -> dict:
    """Whatever a scanner returned: which agency, and the fields. Raises UdiError when it cannot be read."""
    # only line ends come off the end: a HIBC check character can be a space
    s = str(code or "").lstrip().rstrip("\r\n").replace("\\x1d", GS).replace("<GS>", GS)
    if not s:
        raise UdiError(say("nothing was scanned"))
    if len(s) > 500:
        raise UdiError(say("this is too long for a device label"))
    s = SYMBOLOGY.sub("", s)
    if s[:8].lower().startswith(("http://", "https://")):
        return {**parse_gs1(_from_link(s), today), "form": "GS1 Digital Link"}
    if s.startswith("("):
        return {**parse_gs1(_from_brackets(s), today), "form": "GS1 (printed)"}
    if s.startswith("+"):
        return {**parse_hibc(s, today), "form": "HIBC"}
    if s.startswith("="):
        return {"agency": "iccbba", "form": "ISBT 128", "raw": s}
    if s.startswith(GS):
        s = s[1:]
    if re.fullmatch(r"\d{8}|\d{12,14}", s):              # a bare GTIN from a box's EAN, UPC or ITF-14
        return {"agency": "gs1", "elements": {"01": s}, "di": gtin14(s), "form": "GTIN"}
    if re.match(r"\d{2}", s):
        return {**parse_gs1(s, today), "form": "GS1"}
    raise UdiError(say("not a GS1, HIBC or ISBT 128 code"))


# ---------------------------------------------------------------- building

def gs1_data(di: str, *, lot: str = "", serial: str = "", production: dt.date | None = None,
             expiry: dt.date | None = None) -> tuple[str, str]:
    """(the element string with GS separators, its printed form in brackets) for a label."""
    parts = [("01", gtin14(di))]
    if production:
        parts.append(("11", production.strftime("%y%m%d")))
    if expiry:
        parts.append(("17", expiry.strftime("%y%m%d")))
    for ai, raw in (("10", lot), ("21", serial)):
        v = str(raw or "").strip()
        if v:
            if not CSET82.fullmatch(v):
                raise UdiError(say("({ai}) holds up to 20 letters, digits and GS1's punctuation (not # $ @ ( ) [ ] { "
                                   "})",
                                   ai=ai))
            parts.append((ai, v))
    data = "".join(a + v + (GS if AIS[a] is None and k < len(parts) - 1 else "") for k, (a, v) in enumerate(parts))
    return data, "".join(f"({a}){v}" for a, v in parts)


def hibc_di(lic: str, pcn: str, unit: str) -> str:
    lic, pcn, unit = str(lic or "").upper(), str(pcn or "").upper(), str(unit or "")
    if not re.fullmatch(r"[A-Z][A-Z0-9]{3}", lic):
        raise UdiError(say("the labeler identification code (LIC) is a letter and 3 letters or digits"))
    if not re.fullmatch(r"[A-Z0-9]{1,18}", pcn):
        raise UdiError(say("the product number is 1 to 18 letters or digits"))
    if not re.fullmatch(r"\d", unit):
        raise UdiError(say("the unit of measure is one digit (0 for the unit of use)"))
    return f"+{lic}{pcn}{unit}"


def hibc_data(di: str, *, lot: str = "", serial: str = "", expiry: dt.date | None = None) -> str:
    """The HIBC primary and secondary data in one code, with its check character."""
    if serial and lot:
        raise UdiError(say("a HIBC code carries a lot or a serial number, not both"))
    v = str(serial or lot or "").upper().strip()
    if v and not re.fullmatch(r"[A-Z0-9\-. ]{1,18}", v):
        raise UdiError(say("the lot or serial number is up to 18 letters, digits, - . or spaces"))
    body = di
    if v or expiry:
        sec = ("$$+" if serial else "$$") + ("3" + expiry.strftime("%y%m%d") if expiry else "7") + v \
            if expiry or serial else "$" + v
        body = f"{di}/{sec}"
    return body + hibc_check(body)


def _zpl_text(s: str) -> str:
    """A printed line, cut first and then escaped: _ ^ and ~ (a printer command anywhere in ZPL) as hex."""
    return "".join({"_": "_5F", "^": "_5E", "~": "_7E"}.get(c, c) for c in str(s)[:60] if c >= " ")


def zpl(data: str, lines: list[str], *, gs1: bool, copies: int = 1) -> str:
    """A Zebra label: the code as a Data Matrix (GS1 with FNC1) and the printed lines beside it."""
    if not 1 <= copies <= 500:
        raise UdiError(say("print 1 to 500 copies"))
    if re.search(r"[_^~]", data):
        raise UdiError(say("_ ^ and ~ cannot be printed in a Zebra code; leave them out of the lot or serial"))
    fd = ("_1" + data.replace(GS, "_1")) if gs1 else data     # _ is the escape: _1 is FNC1 (GS1)
    text = "".join(f"^FO230,{30 + 34 * i}^A0N,26,26^FH^FD{_zpl_text(s)}^FS" for i, s in enumerate(lines[:6]))
    return f"^XA^CI28^PQ{copies}^FO20,20^BXN,6,200,,,,_^FD{fd}^FS{text}^XZ\n"
