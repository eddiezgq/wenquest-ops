"""Calibration judgement, step 17f (ADR-0017; dee-qms PLAN-CAL): when equipment is next due, and whether it may be
used to measure on a given day.

Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last))


def usable(g: dict, today: dt.date) -> tuple[bool, str]:
    """In service and not past its calibration due date."""
    if g["status"] == "retired":
        return False, f"{g['code']} is retired"
    if g["status"] != "in_service":
        return False, f"{g['code']} is out of service"
    due = g.get("next_due")
    if due is None:
        return False, f"{g['code']} has no calibration due date"
    if due < today:
        return False, f"{g['code']} was due for calibration on {due}"
    return True, f"{g['code']}, calibrated, due {due}"
