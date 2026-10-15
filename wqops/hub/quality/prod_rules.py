"""Production record rules, step 17i (ADR-0017; dee-qms PLAN-DHR). Pure functions: no database, no AI, no network.

A measurement passes when low <= value <= high (the limits included), judged on the value as stored (rounded to six
decimal places); a check is what the operator chose; a record passes once something is written.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal

KINDS = ("check", "measure", "record")
PLACES = 6
LIMIT = Decimal(10) ** 15     # readings and quantities are below this


def stored(value) -> Decimal | None:
    """A reading as it is stored: a finite number rounded to six places; None for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        x = Decimal(str(value).strip())
        if not x.is_finite() or abs(x) >= LIMIT:
            return None
        return round(x, PLACES)
    except ArithmeticError:
        return None


def judge(step: dict, *, value=None, result: str | None = None, text: str | None = None) -> tuple[str | None, str]:
    """(verdict, why); verdict None means the input is not usable for this step."""
    kind = step["kind"]
    if kind == "measure":
        v = stored(value)
        if v is None:
            return None, "the reading is a number"
        low, high = step.get("low"), step.get("high")
        ok = (low is None or Decimal(str(low)) <= v) and (high is None or v <= Decimal(str(high)))
        return ("pass" if ok else "fail"), ("" if ok else f"{v} is outside {fmt_limits(step)}")
    if kind == "check":
        if result not in ("pass", "fail"):
            return None, "choose pass or fail"
        return result, ""
    if not isinstance(text, str) or not text.strip():
        return None, "write what was done"
    return "pass", ""


def _n(v) -> str | None:
    return None if v is None else f"{Decimal(str(v)).normalize():f}"


def fmt_limits(step: dict) -> str:
    low, high, unit = _n(step.get("low")), _n(step.get("high")), step.get("unit") or ""
    if low is not None and high is not None:
        s = f"{low}-{high}"
    elif low is not None:
        s = f">= {low}"
    elif high is not None:
        s = f"<= {high}"
    else:
        s = "no limits"
    return f"{s} {unit}".strip()


def template_needs(t: dict, steps: list[dict]) -> list[str]:
    out = []
    if not steps:
        out.append("at least one step")
    for s in steps:
        if s["kind"] == "measure" and s.get("low") is None and s.get("high") is None:
            out.append(f"step {s['seq']}: a lower or upper limit")
    return out


def next_step(steps: list[dict]) -> int | None:
    """The first step not yet recorded (steps are recorded in order)."""
    for s in sorted(steps, key=lambda x: x["seq"]):
        if s.get("done_by") is None:
            return s["seq"]
    return None


def to_submit(rec: dict, steps: list[dict], materials: list[dict], required: list[str],
              open_ncrs: dict[int, str]) -> list[str]:
    """``open_ncrs``: the status of each nonconformance report the steps link to."""
    out = []
    left = [s["seq"] for s in steps if s.get("done_by") is None]
    if left:
        out.append("steps " + ", ".join(map(str, left)) + " recorded")
    if rec["good_qty"] <= 0:
        out.append("the good quantity")
    if rec["good_qty"] + rec["scrap_qty"] > rec["planned_qty"]:
        out.append("good and scrapped together at most the quantity planned")
    for s in steps:
        if s.get("verdict") == "fail" and (s.get("ncr_id") is None or open_ncrs.get(s["ncr_id"]) == "cancelled"):
            out.append(f"a nonconformance report for step {s['seq']}")
    used = {m["item_code"] for m in materials}
    for code in required:
        if code not in used:
            out.append(f"the material lot of {code} used")
    return out


def to_release(steps: list[dict], ncr_status: dict[int, str], on_hold: list[str]) -> list[str]:
    """Every failed step has its nonconformance report closed (a cancelled one does not count)."""
    out = []
    for s in steps:
        if s.get("verdict") == "fail" and ncr_status.get(s.get("ncr_id")) != "closed":
            out.append(f"the nonconformance report for step {s['seq']} closed")
    out += [f"the out-of-tolerance assessment of {g} signed" for g in on_hold]
    return out


def _plain(v):
    if isinstance(v, Decimal):
        return str(v.normalize()) if v == v.to_integral() else str(v)
    if isinstance(v, float) and math.isfinite(v):
        return repr(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def fingerprint(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=_plain, ensure_ascii=False).encode()).hexdigest()


TEMPLATE_KEYS = ("code", "version", "item_code", "title", "documents", "materials")
STEP_KEYS = ("seq", "name", "instruction", "kind", "low", "high", "unit", "gauge_required")


def template_print(t: dict, steps: list[dict]) -> str:
    return fingerprint({"template": {k: t.get(k) for k in TEMPLATE_KEYS},
                        "steps": [{k: _plain(s.get(k)) for k in STEP_KEYS}
                                  for s in sorted(steps, key=lambda x: x["seq"])]})


RECORD_KEYS = ("name", "item_code", "lot_no", "work_order", "planned_qty", "good_qty", "scrap_qty", "template_print")
DONE_KEYS = (*STEP_KEYS, "result", "value", "text_value", "verdict", "gauge_code", "gauge_due", "done_by", "ncr_id")
MATERIAL_KEYS = ("item_code", "inspection_id", "lot_no", "supplier", "qty", "added_by")


def record_print(rec: dict, steps: list[dict], materials: list[dict]) -> str:
    return fingerprint({"record": {k: rec.get(k) for k in RECORD_KEYS},
                        "steps": [{k: _plain(s.get(k)) for k in DONE_KEYS}
                                  for s in sorted(steps, key=lambda x: x["seq"])],
                        "materials": [{k: _plain(m.get(k)) for k in MATERIAL_KEYS} for m in materials]})
