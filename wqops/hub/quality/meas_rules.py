"""Measurement files (ADR-0020, 20c). Pure functions: no database, no AI, no network.

Reads what a measuring machine exports, a coordinate measuring machine (CMM), a 3D scanner's inspection report or a
gauge's own software, and places the values on the samples of an incoming inspection:

- CSV, long: one row per measured feature, with a part (or sample, serial) column, a feature column (with an axis
  column, as PC-DMIS and Calypso export: "CIR1 D"), a measured value, and optionally nominal and tolerances.
- CSV, wide: one row per part, one column per characteristic, the part number first.
- Q-DAS ASCII transfer format (.dfq, .dfd/.dfx): K-fields K2001/K2002 name the characteristics, K2110/K2111 their
  limits, values as K0001/i fields or as value lines (characteristics separated by 0x0F, the fields of one by 0x14).

The plan's limits decide; limits in the file are only compared with them. A value that cannot be read, or that the
measuring program marked (a Q-DAS attribute other than 0), is not imported and is said so. Nothing is guessed: a
feature of the file goes to a characteristic of the plan only when their names match or the person says so.
"""

from __future__ import annotations

import csv
import io
import re

MAX_BYTES = 5_000_000
PART = ("part", "part no", "part number", "part id", "sample", "sample no", "serial", "serial number", "piece",
        "unit", "teil", "teilenummer", "#")
FEATURE = ("feature", "characteristic", "char", "name", "feature name", "dimension", "label", "merkmal", "element")
AXIS = ("axis", "ax", "achse", "type")
VALUE = ("measured", "actual", "meas", "value", "measured value", "measurement", "result", "istwert", "ist")
NOMINAL = ("nominal", "nom", "nominal value", "sollwert", "soll")
UPPER = ("+tol", "tol+", "upper tol", "upper tolerance", "plus tol", "+ tol", "utol", "ot")
LOWER = ("-tol", "tol-", "lower tol", "lower tolerance", "minus tol", "- tol", "ltol", "ut")
USL = ("usl", "upper limit", "max", "upper spec", "ogw")
LSL = ("lsl", "lower limit", "min", "lower spec", "ugw")


class MeasError(ValueError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def decode(raw: bytes) -> str:
    if len(raw) > MAX_BYTES:
        raise MeasError("the file is larger than 5 MB")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise MeasError("the file is not text")  # pragma: no cover - cp1252 decodes almost anything


def number(v, comma: bool = False) -> float | None:
    s = str(v if v is not None else "").strip().replace("−", "-")
    if comma:
        s = s.replace(".", "").replace(",", ".") if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", s) else s.replace(",", ".")
    if not re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", s):
        return None
    return float(s)


def _empty() -> dict:
    return {"parts": [], "features": [], "values": {}, "problems": []}


def _feature(out: dict, name: str, **limits) -> dict:
    for f in out["features"]:
        if f["name"] == name:
            for k, v in limits.items():
                if v is not None and f.get(k) is None:
                    f[k] = v
            return f
    f = {"name": name, **{k: v for k, v in limits.items() if v is not None}}
    out["features"].append(f)
    return f


def _part(out: dict, p: str) -> None:
    if p not in out["parts"]:
        out["parts"].append(p)


def _col(head: list[str], names: tuple[str, ...]) -> int | None:
    for i, h in enumerate(head):
        if _norm(h) in names:
            return i
    return None


def parse_csv(text: str) -> dict:  # noqa: PLR0912, PLR0915 - the long and the wide shape
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise MeasError("the file has no rows under its header")
    try:
        delim = csv.Sniffer().sniff(lines[0], delimiters=",;\t").delimiter
    except csv.Error:
        delim = ","
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
    head, body = rows[0], rows[1:]
    comma = delim == ";"
    out = _empty() | {"format": "csv"}
    fcol, pcol, vcol = _col(head, FEATURE), _col(head, PART), _col(head, VALUE)
    if fcol is not None:                                            # long: a row per measured feature
        if vcol is None:
            raise MeasError("there is a feature column but no measured value column (Measured, Actual or Value)")
        out["shape"] = "long"
        acol, ncol = _col(head, AXIS), _col(head, NOMINAL)
        ucol, lcol, uscol, lscol = _col(head, UPPER), _col(head, LOWER), _col(head, USL), _col(head, LSL)
        for k, r in enumerate(body, start=2):
            cell = lambda i, r=r: r[i] if i is not None and i < len(r) else ""  # noqa: E731
            name = cell(fcol).strip()
            if not name:
                continue
            ax = cell(acol).strip()
            name = f"{name} {ax}" if ax else name
            part = cell(pcol).strip() or "1" if pcol is not None else "1"
            nom = number(cell(ncol), comma)
            up, lo = number(cell(ucol), comma), number(cell(lcol), comma)
            usl, lsl = number(cell(uscol), comma), number(cell(lscol), comma)
            if nom is not None and up is not None and usl is None:
                usl = nom + abs(up)
            if nom is not None and lo is not None and lsl is None:
                lsl = nom - abs(lo)
            _feature(out, name, nominal=nom, lsl=lsl, usl=usl)
            _part(out, part)
            v = number(cell(vcol), comma)
            if v is None:
                out["problems"].append(f"row {k}: {name} of part {part}: {cell(vcol)!r} is not a number")
            elif (part, name) in out["values"]:
                out["problems"].append(f"row {k}: {name} of part {part} is in the file twice; the first is used")
            else:
                out["values"][(part, name)] = v
        return out
    out["shape"] = "wide"                                           # wide: a row per part
    pc = pcol                                                      # no part column: parts in row order
    names = [(i, h.strip()) for i, h in enumerate(head) if i != pc and h.strip()]
    for _, h in names:
        _feature(out, h)
    for k, r in enumerate(body, start=2):
        part = (r[pc].strip() if pc is not None and pc < len(r) else "") or str(k - 1)
        _part(out, part)
        for i, h in names:
            raw = r[i] if i < len(r) else ""
            if not str(raw).strip():
                continue
            v = number(raw, comma)
            if v is None:
                out["problems"].append(f"row {k}: {h} of part {part}: {raw!r} is not a number")
            else:
                out["values"][(part, h)] = v
    return out


KFIELD = re.compile(r"^K(\d{4})(?:/(\d+))?\s?(.*)$")


def parse_dfq(text: str) -> dict:  # noqa: PLR0912 - one branch per kind of field
    out = _empty() | {"format": "dfq", "shape": "q-das"}
    names: dict[int, str] = {}
    limits: dict[int, dict] = {}
    columns: dict[int, list[tuple[float | None, int]]] = {}     # characteristic -> [(value, attribute)]
    value_lines: list[str] = []
    part_no = ""
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = KFIELD.match(line)
        if not m:
            if line.strip():
                value_lines.append(line)
            continue
        key, idx, val = int(m.group(1)), int(m.group(2) or 0), m.group(3).strip()
        if key == 1001:
            part_no = val
        elif key == 2002:
            names[idx] = val
        elif key == 2001 and idx not in names:
            names[idx] = val
        elif key in (2101, 2110, 2111) and idx:
            lim = {2101: "nominal", 2110: "lsl", 2111: "usl"}[key]
            limits.setdefault(idx, {})[lim] = number(val)
        elif key == 1:
            columns.setdefault(idx, []).append((number(val), 0))
        elif key == 2 and idx in columns and columns[idx]:   # K0002: the attribute of the last value
            v, _ = columns[idx][-1]
            columns[idx][-1] = (v, int(val) if val.isdigit() else 0)
    if not names:
        raise MeasError("no characteristics (K2001 or K2002) in the Q-DAS file")
    for line in value_lines:                                    # one line per part
        for i, chunk in enumerate(line.split("\x0f"), start=1):
            fields = chunk.split("\x14")
            att = int(fields[1]) if len(fields) > 1 and fields[1].strip().isdigit() else 0
            columns.setdefault(i, []).append((number(fields[0]), att))
    count = max((len(v) for v in columns.values()), default=0)
    for idx in sorted(names):
        _feature(out, names[idx] or f"characteristic {idx}", **limits.get(idx, {}))
    for p in range(1, count + 1):
        _part(out, str(p))
    for idx, vals in columns.items():
        if idx not in names:
            out["problems"].append(f"values for characteristic {idx}, which the file does not describe")
            continue
        name = names[idx] or f"characteristic {idx}"
        for p, (v, att) in enumerate(vals, start=1):
            if att:
                out["problems"].append(f"{name} of part {p}: marked by the measuring program (attribute {att}), "
                                       "not imported")
            elif v is None:
                out["problems"].append(f"{name} of part {p}: not a number")
            else:
                out["values"][(str(p), name)] = v
    if part_no:
        out["part_no"] = part_no
    return out


def parse(file_name: str, raw: bytes) -> dict:
    text = decode(raw)
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if ext in ("dfq", "dfd", "dfx") or re.match(r"^K0100|^K1001|^K2001", text.lstrip()):
        return parse_dfq(text)
    if ext in ("csv", "txt", "tsv", ""):
        return parse_csv(text)
    raise MeasError("read CSV exports and Q-DAS files (.dfq, .dfd, .dfx); save other reports as CSV")


def match(features: list[dict], chars: list[dict], mapping: dict | None = None) -> dict[str, str]:
    """file feature -> plan characteristic: what the person chose, else the same name (case and spaces aside).
    Only measured characteristics take values; an empty choice leaves a feature out."""
    measured = {_norm(c["name"]): c["name"] for c in chars if c["kind"] == "measured"}
    out = {}
    for f in features:
        if mapping is not None and f["name"] in mapping:
            want = mapping[f["name"]]
            if want:
                if _norm(want) not in measured:
                    raise MeasError(f"{want!r} is not a measured characteristic of the plan")
                out[f["name"]] = measured[_norm(want)]
        elif _norm(f["name"]) in measured:
            out[f["name"]] = measured[_norm(f["name"])]
    if len(set(out.values())) < len(out):
        twice = sorted({c for c in out.values() if list(out.values()).count(c) > 1})
        raise MeasError("more than one feature goes to " + ", ".join(twice))
    return out


def place(parsed: dict, chars: list[dict], n: int, first_sample: int, mapping: dict[str, str]) -> dict:
    """The readings to write: parts in file order on samples first_sample, first_sample + 1, ... and what was left
    out or differs."""
    problems = list(parsed["problems"])
    notes = []
    if not 1 <= first_sample <= n:
        raise MeasError(f"the first sample is 1 to {n}")
    parts = parsed["parts"]
    if first_sample - 1 + len(parts) > n:
        raise MeasError(f"the file has {len(parts)} parts; from sample {first_sample} there are only "
                        f"{n - first_sample + 1} samples")
    sample = {p: first_sample + i for i, p in enumerate(parts)}
    plan = {c["name"]: c for c in chars}
    for f in parsed["features"]:
        c = plan.get(mapping.get(f["name"], ""))
        if c is None:
            notes.append(f"{f['name']}: not in the plan, left out")
            continue
        for lim in ("lsl", "usl"):
            fv, pv = f.get(lim), c.get(lim)
            if fv is not None and pv is not None and abs(float(fv) - float(pv)) > 1e-9:
                notes.append(f"{f['name']}: the file's {lim.upper()} {fv:g} differs from the plan's {float(pv):g}; "
                             "the plan's limit decides")
    readings = [{"sample": sample[p], "characteristic": mapping[name], "value": v}
                for (p, name), v in parsed["values"].items() if name in mapping]
    readings.sort(key=lambda r: (r["sample"], r["characteristic"]))
    missing = sorted({c["name"] for c in chars if c["kind"] == "measured"} - set(mapping.values()))
    return {"readings": readings, "samples": [sample[p] for p in parts], "parts": parts, "problems": problems,
            "notes": notes, "unmapped_characteristics": missing}
