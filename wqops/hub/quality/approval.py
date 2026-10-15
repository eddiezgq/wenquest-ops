"""Approved supplier list judgement, step 17c (ADR-0017; dee-qms PLAN-ASL): may this supplier deliver this item?

Plain code: no AI, no network, no database (tests/test_isolation.py).

An entry for the item counts before an entry for all the supplier's items, except that a supplier suspended or
disqualified for all its items is blocked for every item. Approved and not due for re-evaluation: ok. Conditional,
or approved but past its re-evaluation date: allowed, with a flag that goes with the record. No entry, a draft,
suspended or disqualified: blocked.
"""

from __future__ import annotations

import datetime as dt

STATUSES = ("draft", "approved", "conditional", "suspended", "disqualified")
RISKS = ("low", "medium", "high")
SOON_DAYS = 30


def entry_for(entries: list[dict], supplier: str, item_code: str | None) -> dict | None:
    """The entry that speaks for this supplier and item: the item's own, else the supplier's for all items."""
    own = [e for e in entries if e["supplier"] == supplier and item_code and e.get("item_code") == item_code]
    if own:
        return own[0]
    every = [e for e in entries if e["supplier"] == supplier and not e.get("item_code")]
    return every[0] if every else None


def _day(v) -> dt.date | None:
    if v is None or isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def standing(entries: list[dict], supplier: str | None, item_code: str | None, today: dt.date) -> dict:
    """{outcome: ok | flag | block, why, entry}. ``supplier`` None: nothing to check against (block)."""
    if not supplier:
        return {"outcome": "block", "why": "no supplier is known for this lot", "entry": None}
    every = entry_for(entries, supplier, None)
    e = entry_for(entries, supplier, item_code)
    what = f"{supplier}" + (f" for {item_code}" if item_code else "")
    if every and every["status"] in ("suspended", "disqualified"):
        e, what = every, f"{supplier} (all items)"
    if e is None:
        return {"outcome": "block", "why": f"{what} is not on the approved supplier list", "entry": None}
    st, due = e["status"], _day(e.get("review_due"))
    if st in ("draft", "suspended", "disqualified"):
        return {"outcome": "block", "why": f"{what} is {st} on the approved supplier list", "entry": e}
    if st == "conditional":
        return {"outcome": "flag", "why": f"conditional supplier: {e.get('condition') or 'see the list'}",
                "entry": e}
    if due and due < today:
        return {"outcome": "flag", "why": f"supplier re-evaluation was due on {due}", "entry": e}
    return {"outcome": "ok", "why": f"approved{f' until {due}' if due else ''}", "entry": e}


def review_state(e: dict, today: dt.date) -> str | None:
    """overdue, soon (within SOON_DAYS) or None, for an approved or conditional entry."""
    due = _day(e.get("review_due"))
    if e["status"] not in ("approved", "conditional") or due is None:
        return None
    if due < today:
        return "overdue"
    return "soon" if (due - today).days <= SOON_DAYS else None
