"""Incoming inspection judgement (ADR-0017, step 17b; dee-qms PLAN-IQC and PLAN-SEVERITY): looking up the sampling
table, judging each reading, each sample unit and the lot, and suggesting a switch between normal, tightened and
reduced inspection from the lots' results.

Plain code: no AI, no network, no database (tests/test_isolation.py). The sampling table and the switching rules are
the company's configuration data; nothing here holds a number taken from a standard.
"""

from __future__ import annotations

import math

from wqops.i18n import say

LEVELS = {"normal": "Normal", "tightened": "Tightened", "reduced": "Reduced"}
KINDS = ("measured", "attribute")
CONDITIONS = {"window_rejected": "at least K of the last N lots rejected",
              "consecutive_accepted": "N lots in a row accepted",
              "any_rejected": "any lot rejected"}


class SamplingError(ValueError):
    pass


def check_row(r: dict) -> list[str]:
    """What is wrong with a sampling table row: a lot size range, n >= 1, Ac >= 0, Re = Ac + 1."""
    errs = []
    if r.get("level") not in LEVELS:
        errs.append("the inspection level is normal, tightened or reduced")
    aql = r.get("aql")
    if not isinstance(aql, (int, float)) or isinstance(aql, bool) or not 0 < aql <= 1000 or math.isnan(aql):
        errs.append("the AQL is a number above 0")
    ints = {k: r.get(k) for k in ("lot_min", "lot_max", "n", "ac", "re")}
    if any(type(v) is not int for v in ints.values()):
        errs.append("lot sizes, n, Ac and Re are whole numbers")
        return errs
    if ints["lot_min"] < 1 or ints["lot_max"] < ints["lot_min"]:
        errs.append(f"the lot size range {ints['lot_min']}-{ints['lot_max']} is not a range")
    if ints["n"] < 1 or ints["ac"] < 0 or ints["re"] != ints["ac"] + 1:
        errs.append("n is at least 1, Ac at least 0 and Re is Ac + 1")
    return errs


def lookup(rows: list[dict], aql: float, level: str, lot_qty: int) -> dict:
    """The one active row for this AQL, level and lot size. None or more than one is an error: never a guess."""
    hits = [r for r in rows if r.get("active", True) and float(r["aql"]) == float(aql) and r["level"] == level
            and r["lot_min"] <= lot_qty <= r["lot_max"]]
    where = f"AQL {aql:g}, {LEVELS.get(level, level).lower()} inspection, lot size {lot_qty}"
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
        return ["a plan has at least one characteristic"]
    for i, c in enumerate(chars, start=1):
        if not isinstance(c, dict):
            errs.append(f"characteristic {i} is not described")
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            errs.append(f"characteristic {i} needs a name")
        elif name.lower() in seen:
            errs.append(f"characteristic {name!r} twice")
        seen.add(name.lower())
        if c.get("kind") not in KINDS:
            errs.append(f"{name or i}: measured or attribute")
            continue
        lo, hi = c.get("lsl"), c.get("usl")
        for v in (lo, hi):
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v)):
                errs.append(f"{name or i}: limits are numbers")
                break
        else:
            if c["kind"] == "attribute" and (lo is not None or hi is not None or c.get("unit")):
                errs.append(f"{name or i}: an attribute is pass or fail, with no limits or unit")
            if c["kind"] == "measured" and lo is None and hi is None:
                errs.append(f"{name or i}: a measured characteristic needs a lower or an upper limit")
            if lo is not None and hi is not None and lo > hi:
                errs.append(f"{name or i}: the lower limit is above the upper limit")
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
            missing.append(f"sample {r['sample']}, {r['characteristic']}")
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
        errs.append("a rule goes from one inspection level to another")
    if (r.get("from_level"), r.get("to_level")) == ("reduced", "tightened"):
        errs.append("reduced cannot go straight to tightened; it goes back to normal first")
    if r.get("condition") not in CONDITIONS:
        errs.append("the condition is one of: " + ", ".join(CONDITIONS))
    elif r["condition"] != "any_rejected":
        n, k = r.get("n"), r.get("k")
        if type(n) is not int or n < 1:
            errs.append("N is a whole number of lots, at least 1")
        elif r["condition"] == "window_rejected" and (type(k) is not int or not 1 <= k <= n):
            errs.append("K is a whole number from 1 to N")
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
            what = CONDITIONS[rule["condition"]].replace("K", str(rule.get("k"))).replace("N", str(rule.get("n")))
            return {"to": rule["to_level"], "rule_id": rule.get("id"),
                    "reason": f"{LEVELS[level]} to {LEVELS[rule['to_level']].lower()}: {what}; actually "
                              f"{tail.count('reject')} of the last {len(tail)} lots rejected"}
    return None
