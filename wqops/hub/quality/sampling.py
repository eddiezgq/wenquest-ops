"""Incoming inspection judgement (ADR-0017, step 17b; dee-qms PLAN-IQC and PLAN-SEVERITY): looking up the sampling
table, judging each reading, each sample unit and the lot, and suggesting a switch between normal, tightened and
reduced inspection from the lots' results.

Plain code: no AI, no network, no database (tests/test_isolation.py). The sampling table and the switching rules are
the company's configuration data; nothing here holds a number taken from a standard.
"""

from __future__ import annotations

import math

from wqops import i18n as I18N
from wqops.i18n import say

LEVELS = {"normal": "Normal", "tightened": "Tightened", "reduced": "Reduced"}
KINDS = ("measured", "attribute")
CONDITIONS = {"window_rejected": "at least K of the last N lots rejected",
              "consecutive_accepted": "N lots in a row accepted",
              "any_rejected": "any lot rejected"}
# the same conditions as whole sentences to translate (the web pages use these too)
_CONDITION_TEXT = {"window_rejected": "at least {K} of the last {N} lots rejected",
                   "consecutive_accepted": "{N} lots in a row accepted", "any_rejected": "any lot rejected"}


def _level(level: str) -> str:
    """'tightened' as a word in a sentence, in the reader's language."""
    return say(LEVELS[level]).lower() if level in LEVELS else level


def _join(items, sep: str = ", ") -> str:
    if I18N.current() == "zh":
        sep = {", ": "、"}.get(sep, sep)
    return sep.join(items)


class SamplingError(ValueError):
    pass


def check_row(r: dict) -> list[str]:
    """What is wrong with a sampling table row: a lot size range, n >= 1, Ac >= 0, Re = Ac + 1."""
    errs = []
    if r.get("level") not in LEVELS:
        errs.append(say("the inspection level is normal, tightened or reduced"))
    aql = r.get("aql")
    if not isinstance(aql, (int, float)) or isinstance(aql, bool) or not 0 < aql <= 1000 or math.isnan(aql):
        errs.append(say("the AQL is a number above 0"))
    ints = {k: r.get(k) for k in ("lot_min", "lot_max", "n", "ac", "re")}
    if any(type(v) is not int for v in ints.values()):
        errs.append(say("lot sizes, n, Ac and Re are whole numbers"))
        return errs
    if ints["lot_min"] < 1 or ints["lot_max"] < ints["lot_min"]:
        errs.append(say("the lot size range {lot_min}-{lot_max} is not a range", lot_min=ints["lot_min"],
                        lot_max=ints["lot_max"]))
    if ints["n"] < 1 or ints["ac"] < 0 or ints["re"] != ints["ac"] + 1:
        errs.append(say("n is at least 1, Ac at least 0 and Re is Ac + 1"))
    return errs


def lookup(rows: list[dict], aql: float, level: str, lot_qty: int) -> dict:
    """The one active row for this AQL, level and lot size. None or more than one is an error: never a guess."""
    hits = [r for r in rows if r.get("active", True) and float(r["aql"]) == float(aql) and r["level"] == level
            and r["lot_min"] <= lot_qty <= r["lot_max"]]
    where = say("AQL {aql}, {level} inspection, lot size {lot_qty}", aql=format(aql, "g"), level=_level(level),
                lot_qty=lot_qty)
    if not hits:
        raise SamplingError(say("the sampling table has no row for {where}", where=where))
    if len(hits) > 1:
        raise SamplingError(say("the sampling table has overlapping rows for {where}: fix the table first",
                                where=where))
    return hits[0]


def plan_for(row: dict, lot_qty: int) -> dict:
    """Sample size, Ac and Re for a lot; a sample larger than the lot means every piece is inspected."""
    n = min(int(row["n"]), int(lot_qty))
    return {"n": n, "ac": int(row["ac"]), "re": int(row["re"]), "all": n == int(lot_qty) and n < int(row["n"])}


def check_characteristics(chars) -> list[str]:
    """What is wrong with a plan's characteristics: names unique, a kind, limits only on measured ones and in order."""
    errs, seen = [], set()
    if not isinstance(chars, list) or not chars:
        return [say("a plan has at least one characteristic")]
    for i, c in enumerate(chars, start=1):
        if not isinstance(c, dict):
            errs.append(say("characteristic {i} is not described", i=i))
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            errs.append(say("characteristic {i} needs a name", i=i))
        elif name.lower() in seen:
            errs.append(say("characteristic {name} twice", name=repr(name)))
        seen.add(name.lower())
        if c.get("kind") not in KINDS:
            errs.append(say("{name}: measured or attribute", name=name or i))
            continue
        lo, hi = c.get("lsl"), c.get("usl")
        for v in (lo, hi):
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v)):
                errs.append(say("{name}: limits are numbers", name=name or i))
                break
        else:
            if c["kind"] == "attribute" and (lo is not None or hi is not None or c.get("unit")):
                errs.append(say("{name}: an attribute is pass or fail, with no limits or unit", name=name or i))
            if c["kind"] == "measured" and lo is None and hi is None:
                errs.append(say("{name}: a measured characteristic needs a lower or an upper limit", name=name or i))
            if lo is not None and hi is not None and lo > hi:
                errs.append(say("{name}: the lower limit is above the upper limit", name=name or i))
    return errs


def conforms(char: dict, value=None, passed=None) -> bool | None:
    """One reading: within the limits that are set (measured) or passed (attribute); None when not entered."""
    if char["kind"] == "attribute":
        return passed if isinstance(passed, bool) else None
    if value is None:
        return None
    lo, hi = char.get("lsl"), char.get("usl")
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def judge(chars: list[dict], readings: list[dict], n: int, ac: int, re: int) -> dict:
    """The lot. A sample unit fails if any of its readings fails; the lot is accepted with Ac or fewer failing
    units and rejected with Re or more. Every reading must be entered first."""
    by = {c["name"]: c for c in chars}
    missing, bad_units = [], set()
    for r in readings:
        ok = conforms(by[r["characteristic"]], r.get("value"), r.get("passed"))
        if ok is None:
            missing.append(say("sample {sample}, {characteristic}", sample=r["sample"],
                               characteristic=r["characteristic"]))
        elif not ok:
            bad_units.add(r["sample"])
    if len(readings) != n * len(chars):
        raise SamplingError(say("expected {v} readings, found {readings}", v=n * len(chars), readings=len(readings)))
    if missing:
        raise SamplingError(say("{missing} readings not entered yet, first: {missing2}",
                                missing=len(missing), missing2=missing[0]))
    d = len(bad_units)
    return {"defectives": d, "failed_samples": sorted(bad_units),
            "result": "accept" if d <= ac else "reject" if d >= re else None}


def check_rule(r: dict) -> list[str]:
    errs = []
    if r.get("from_level") not in LEVELS or r.get("to_level") not in LEVELS or r.get("from_level") == r.get(
            "to_level"):
        errs.append(say("a rule goes from one inspection level to another"))
    if (r.get("from_level"), r.get("to_level")) == ("reduced", "tightened"):
        errs.append(say("reduced cannot go straight to tightened; it goes back to normal first"))
    if r.get("condition") not in CONDITIONS:
        errs.append(say("the condition is one of: {list}", list=_join(CONDITIONS)))
    elif r["condition"] != "any_rejected":
        n, k = r.get("n"), r.get("k")
        if type(n) is not int or n < 1:
            errs.append(say("N is a whole number of lots, at least 1"))
        elif r["condition"] == "window_rejected" and (type(k) is not int or not 1 <= k <= n):
            errs.append(say("K is a whole number from 1 to N"))
    return errs


def _met(rule: dict, results: list[str]) -> tuple[bool, list[str]]:
    if rule["condition"] == "any_rejected":
        return "reject" in results, results
    tail = results[-rule["n"]:]
    if rule["condition"] == "consecutive_accepted":
        return len(tail) == rule["n"] and all(r == "accept" for r in tail), tail
    return tail.count("reject") >= rule["k"], tail


def suggest(rules: list[dict], level: str, results: list[str]) -> dict | None:
    """The switch the rules suggest from the current level, given the lots judged at it (oldest first), with the
    reason in numbers. A suggestion only: a person confirms a switch."""
    for rule in rules:
        if not rule.get("active", True) or rule["from_level"] != level:
            continue
        hit, tail = _met(rule, results)
        if hit:
            what = say(_CONDITION_TEXT[rule["condition"]], K=rule.get("k"), N=rule.get("n"))
            return {"to": rule["to_level"], "rule_id": rule.get("id"),
                    "reason": say("{from_level} to {to_level}: {what}; actually {rejected} of the last {n} lots "
                                  "rejected", from_level=say(LEVELS[level]), to_level=_level(rule["to_level"]),
                                  what=what, rejected=tail.count("reject"), n=len(tail))}
    return None
