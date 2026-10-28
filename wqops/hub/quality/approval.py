"""Approved supplier list judgement, step 17c (ADR-0017; dee-qms PLAN-ASL): may this supplier deliver this item?

Plain code: no AI, no network, no database (tests/test_isolation.py).

An entry for the item counts before an entry for all the supplier's items, except that a supplier suspended or
disqualified for all its items is blocked for every item. Approved and not due for re-evaluation: ok. Conditional,
or approved but past its re-evaluation date: allowed, with a flag that goes with the record. No entry, a draft,
suspended or disqualified: blocked.
"""

from __future__ import annotations

import datetime as dt

from wqops.i18n import say

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
        return {"outcome": "block", "why": say("no supplier is known for this lot"), "entry": None}
    every = entry_for(entries, supplier, None)
    e = entry_for(entries, supplier, item_code)
    what = say("{supplier} for {item}", supplier=supplier, item=item_code) if item_code else f"{supplier}"
    if every and every["status"] in ("suspended", "disqualified"):
        e, what = every, say("{supplier} (all items)", supplier=supplier)
    if e is None:
        return {"outcome": "block", "why": say("{what} is not on the approved supplier list", what=what), "entry": None}
    st, due = e["status"], _day(e.get("review_due"))
    if st in ("draft", "suspended", "disqualified"):
        return {"outcome": "block", "why": say("{what} is {status} on the approved supplier list", what=what,
                                               status=say("supplier status::" + st)), "entry": e}
    if st == "conditional":
        return {"outcome": "flag", "why": say("conditional supplier: {condition}",
                                              condition=e.get("condition") or say("see the list")),
                "entry": e}
    if due and due < today:
        return {"outcome": "flag", "why": say("supplier re-evaluation was due on {due}", due=due), "entry": e}
    return {"outcome": "ok", "why": say("approved until {due}", due=due) if due else say("supplier status::approved"),
            "entry": e}


def review_state(e: dict, today: dt.date) -> str | None:
    """overdue, soon (within SOON_DAYS) or None, for an approved or conditional entry."""
    due = _day(e.get("review_due"))
    if e["status"] not in ("approved", "conditional") or due is None:
        return None
    if due < today:
        return "overdue"
    return "soon" if (due - today).days <= SOON_DAYS else None
