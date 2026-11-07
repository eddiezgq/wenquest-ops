"""PLM checks (ADR-0026 items 5-8): revision letters, category parameters, similar parts, what a part or a BOM needs
before release, a BOM's cycles and the difference between two BOM revisions.

A check that lacks data is "unknown", never "pass" (ADR-0010). Plain code: no AI, no network.
"""

from __future__ import annotations

import string
from decimal import Decimal, InvalidOperation

from wqops import i18n as I18N
from wqops.hub.plm import catalog as CAT
from wqops.i18n import say

LETTERS = [c for c in string.ascii_uppercase if c not in "IOQ"]   # I, O, Q look like 1 and 0


def next_revision(rev: str | None) -> str:
    """A, B, ... Z (without I, O, Q), then AA, AB, ..."""
    if not rev:
        return LETTERS[0]
    out = list(rev)
    i = len(out) - 1
    while i >= 0:
        k = LETTERS.index(out[i])
        if k + 1 < len(LETTERS):
            out[i] = LETTERS[k + 1]
            return "".join(out)
        out[i] = LETTERS[0]
        i -= 1
    return LETTERS[0] + "".join(out)


def clean_params(category: str, raw) -> dict:
    """The parameters of a part, checked against its category: known keys, numbers in range, texts trimmed.
    Missing required values are allowed in a draft (release checks them)."""
    cat = CAT.get(category)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(say("parameters are a list of name and value"))
    fields = {x["key"]: x for x in cat["fields"]}
    out = {}
    for k, v in raw.items():
        if k not in fields:
            raise ValueError(say("{k} is not a parameter of this category", k=k))
        x = fields[k]
        if v in (None, ""):
            continue
        if x["min"] is None:
            out[k] = str(v).strip()[:200]
            continue
        try:
            n = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(say("{label} is a number", label=I18N.label(x["label"]))) from exc
        if not x["min"] <= n <= x["max"]:
            raise ValueError(say("{label} is between {lo} and {hi} {unit}", label=I18N.label(x["label"]), lo=x["min"],
                                 hi=x["max"], unit=x["unit"]))
        out[k] = n
    return out


def missing_params(category: str, params: dict) -> list[str]:
    return [I18N.label(x["label"]) for x in CAT.get(category)["fields"]
            if x["required"] and params.get(x["key"]) in (None, "")]


def similar(category: str, params: dict, others: list[dict]) -> list[dict]:
    """Parts of the same category whose required parameters all match (numbers within 1 %, texts ignoring case).
    Nothing to compare (no required values given) finds nothing."""
    req = [x for x in CAT.get(category)["fields"] if x["required"]]
    if not req or any(params.get(x["key"]) in (None, "") for x in req):
        return []
    out = []
    for o in others:
        p = o.get("params") or {}
        same = True
        for x in req:
            a, b = params.get(x["key"]), p.get(x["key"])
            if b in (None, ""):
                same = False
            elif x["min"] is None:
                same = str(a).strip().lower() == str(b).strip().lower()
            else:
                same = abs(float(a) - float(b)) <= 0.01 * max(abs(float(a)), abs(float(b)), 1e-9)
            if not same:
                break
        if same:
            out.append(o)
    return out


def part_checks(part: dict, rev: dict) -> list[dict]:
    """What a part revision needs before release: [{check, result: pass | fail | unknown, detail}]."""
    out = []
    miss = missing_params(part["category"], rev.get("params") or {})
    out.append({"check": say("required parameters"), "result": "fail" if miss else "pass",
                "detail": ", ".join(miss)})
    st = part.get("erp_state")
    out.append({"check": say("item in ERPNext"),
                "result": "pass" if st in ("created", "existing") else "fail" if st == "failed" else "unknown",
                "detail": part.get("erp_error") or ""})
    return out


def qty(v) -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(say("the quantity is a number above 0")) from exc
    if not d.is_finite() or d <= 0:
        raise ValueError(say("the quantity is a number above 0"))
    return d


def cycle(parent: int, children: list[int], uses: dict[int, list[int]]) -> list[int] | None:
    """A path parent -> ... -> parent through BOMs, if any. ``uses`` maps a part to the parts its BOM uses (the BOM
    being checked included as ``children``)."""
    graph = {**uses, parent: list(children)}
    stack = [(parent, [parent])]
    seen = set()
    while stack:
        node, path = stack.pop()
        for c in graph.get(node, []):
            if c == parent:
                return [*path, c]
            if c not in seen:
                seen.add(c)
                stack.append((c, [*path, c]))
    return None


def bom_checks(lines: list[dict], loop: list[str] | None) -> list[dict]:
    """What a BOM revision needs before release. Each line: code, name, qty, uom, part_status (released or not),
    source (make | buy) and approved_supplier (True, False or None when it is not known)."""
    out = [{"check": say("at least one line"), "result": "pass" if lines else "fail", "detail": ""}]
    unreleased = [x["code"] for x in lines if x.get("part_status") != "released"]
    out.append({"check": say("every part on it released"), "result": "fail" if unreleased else "pass",
                "detail": ", ".join(unreleased)})
    out.append({"check": say("no part contains itself"), "result": "fail" if loop else "pass",
                "detail": " → ".join(loop or [])})
    bad = [x["code"] for x in lines if not x.get("uom") or not x.get("qty") or Decimal(str(x["qty"])) <= 0]
    out.append({"check": say("quantity and unit on every line"), "result": "fail" if bad else "pass",
                "detail": ", ".join(bad)})
    buy = [x for x in lines if x.get("source") == "buy"]
    no = [x["code"] for x in buy if x.get("approved_supplier") is False]
    unknown = [x["code"] for x in buy if x.get("approved_supplier") is None]
    out.append({"check": say("bought parts have an approved supplier"),
                "result": "fail" if no else "unknown" if unknown else "pass", "detail": ", ".join(no or unknown)})
    return out


def passed(checks: list[dict]) -> bool:
    return all(c["result"] == "pass" for c in checks)


def diff(old: list[dict], new: list[dict]) -> list[dict]:
    """Lines added, removed or changed from one BOM revision to the next, matched by part code."""
    a = {x["code"]: x for x in old}
    b = {x["code"]: x for x in new}
    out = []
    for code in sorted(set(a) | set(b)):
        x, y = a.get(code), b.get(code)
        if x is None:
            out.append({"code": code, "name": y["name"], "change": "added", "old": None,
                        "new": f"{y['qty']} {y['uom']}"})
        elif y is None:
            out.append({"code": code, "name": x["name"], "change": "removed", "old": f"{x['qty']} {x['uom']}",
                        "new": None})
        elif (Decimal(str(x["qty"])), x["uom"]) != (Decimal(str(y["qty"])), y["uom"]):
            out.append({"code": code, "name": y["name"], "change": "changed", "old": f"{x['qty']} {x['uom']}",
                        "new": f"{y['qty']} {y['uom']}"})
    return out
