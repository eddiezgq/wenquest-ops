"""The company overview's rules (ADR-0018). Pure functions: no database, no AI, no network.

Each of the seven panels has a light. The colour comes from one number and the company's thresholds; with no number
the light is "unknown", never green. The thresholds below are starting points marked as such: every company sets its
own targets.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable

PANELS = ("sales", "delivery", "inventory", "purchasing", "production", "quality", "finance")
LABELS = {"sales": "Sales", "delivery": "Delivery", "inventory": "Inventory", "purchasing": "Purchasing",
          "production": "Production", "quality": "Quality", "finance": "Finance"}
VIEW = {"sales": "sales:view", "delivery": "sales:view", "inventory": "inventory:view",
        "purchasing": "purchasing:view", "production": "quality:view", "quality": "quality:view",
        "finance": "finance:view"}

# panel: (what the light reads, unit, "higher" or "lower" is better, green at, amber at). Starting points only.
THRESHOLDS = {
    "sales": ("Orders this week against the 8-week average", "%", "higher", 90, 70),
    "delivery": ("On-time delivery, last 30 days", "%", "higher", 95, 85),
    "inventory": ("Items short for open orders", "items", "lower", 0, 3),
    "purchasing": ("Purchase order lines received on time, last 30 days", "%", "higher", 90, 75),
    "production": ("Lots released without a failed step, last 30 days", "%", "higher", 95, 85),
    "quality": ("Overdue quality actions (CAPA steps, complaint deadlines, calibration)", "items", "lower", 0, 2),
    "finance": ("Overdue share of receivables", "%", "lower", 10, 25),
}
NOTE = "Starting point: set it to your company's target"


def thresholds(saved: dict | None) -> dict[str, dict]:
    """The thresholds in use: the company's where set, else the starting points."""
    out = {}
    for k, (what, unit, better, green, amber) in THRESHOLDS.items():
        mine = (saved or {}).get(k) or {}
        out[k] = {"what": what, "unit": unit, "better": better, "green": mine.get("green", green),
                  "amber": mine.get("amber", amber), "default": not mine}
    return out


def check_thresholds(data) -> dict:
    """A company's thresholds as sent: numbers, in the right order for the direction."""
    if not isinstance(data, dict):
        raise ValueError("thresholds are given per panel")
    out = {}
    for k, v in data.items():
        if k not in THRESHOLDS:
            raise ValueError(f"no panel {k}")
        if not isinstance(v, dict) or any(type(v.get(x)) not in (int, float) or not math.isfinite(v[x])
                                          for x in ("green", "amber")):
            raise ValueError(f"{k}: green and amber are numbers")
        better = THRESHOLDS[k][2]
        if (better == "higher" and v["green"] < v["amber"]) or (better == "lower" and v["green"] > v["amber"]):
            raise ValueError(f"{k}: green must be the better of the two")
        out[k] = {"green": v["green"], "amber": v["amber"]}
    return out


def light(value, rule: dict) -> str:
    if value is None:
        return "unknown"
    if rule["better"] == "higher":
        return "green" if value >= rule["green"] else "amber" if value >= rule["amber"] else "red"
    return "green" if value <= rule["green"] else "amber" if value <= rule["amber"] else "red"


def week_ends(as_of: dt.date, weeks: int) -> list[dt.date]:
    """The last day of each of the last ``weeks`` 7-day periods, oldest first (the last one ends today)."""
    return [as_of - dt.timedelta(days=7 * w) for w in range(weeks - 1, -1, -1)]


def by_week(rows: Iterable[tuple[dt.date | None, float]], as_of: dt.date, weeks: int) -> list[dict]:
    """Sum and count of (day, amount) rows per 7-day period ending on each of ``week_ends``."""
    ends = week_ends(as_of, weeks)
    out = [{"week_ending": str(e), "value": 0.0, "count": 0} for e in ends]
    first = ends[0] - dt.timedelta(days=6)
    for day, amount in rows:
        if day is None or not first <= day <= as_of:
            continue
        i = next(i for i, e in enumerate(ends) if day <= e)
        out[i]["value"] = round(out[i]["value"] + (amount or 0), 2)
        out[i]["count"] += 1
    return out


def vs_average(series: list[dict]) -> float | None:
    """This week as a share (%) of the average of the weeks before it; None without history."""
    if len(series) < 2:
        return None
    before = [w["value"] for w in series[:-1]]
    avg = sum(before) / len(before)
    return round(100.0 * series[-1]["value"] / avg, 1) if avg else None


def change(series: list[dict]) -> float | None:
    """This week against last week, in %."""
    if len(series) < 2 or series[-2]["value"] in (None, 0) or series[-1]["value"] is None:
        return None
    return round(100.0 * (series[-1]["value"] - series[-2]["value"]) / abs(series[-2]["value"]), 1)


AGING = (("current", 0), ("1-30", 30), ("31-60", 60), ("61-90", 90), ("over 90", None))


def aging(rows: Iterable[tuple[dt.date | None, float]], as_of: dt.date) -> list[dict]:
    """Outstanding amounts by how many days past their due date (rows of due date, amount)."""
    out = [{"bucket": b, "value": 0.0} for b, _ in AGING]
    for due, amount in rows:
        if not amount:
            continue
        late = (as_of - due).days if due else 0
        i = 0 if late <= 0 else next(i for i, (_, top) in enumerate(AGING) if i and (top is None or late <= top))
        out[i]["value"] = round(out[i]["value"] + amount, 2)
    return out


def scale(series: list[dict]) -> list[dict]:
    """For the big screen in visitor mode: the curve kept, the amounts left out (each week as % of the largest)."""
    top = max((abs(w["value"]) for w in series if w.get("value") is not None), default=0)
    return [{**{k: v for k, v in w.items() if k not in ("value",)},
             "value": round(100.0 * w["value"] / top, 1) if top and w.get("value") is not None else None}
            for w in series]


MONEY = {"currency"}


def redact(panel: dict) -> dict:
    """Visitor mode: no amounts of money and no customer or supplier names; shares, counts and curves stay."""
    out = {**panel, "redacted": True}
    out["figures"] = [f if f.get("unit") not in MONEY else {**f, "value": None, "hidden": True}
                      for f in panel.get("figures", [])]
    out["series"] = {k: {**s, "points": scale(s["points"])} if s.get("unit") in MONEY else s
                     for k, s in panel.get("series", {}).items()}
    out["lists"] = {k: v for k, v in panel.get("lists", {}).items() if k == "iso"}   # counts of control points only
    if panel.get("light", {}).get("unit") in MONEY:
        out["light"] = {**panel["light"], "value": None}
    return out
