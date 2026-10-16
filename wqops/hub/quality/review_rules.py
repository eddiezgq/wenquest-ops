"""Management review rules, step 17j (ADR-0017; dee-qms PLAN-MR). Pure functions: no database, no AI, no network."""

from __future__ import annotations

import datetime as dt
import hashlib
import json


def fingerprint(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def rate(n: int, total: int) -> float | None:
    """A share in %, or None when there is nothing to divide (unknown, not 0)."""
    return round(100.0 * n / total, 1) if total else None


def to_sign(r: dict, user_email: str, today: dt.date) -> list[str]:
    """What the review still needs before its chair signs."""
    out = []
    if r.get("status") != "frozen":
        out.append("the inputs collected")
    if not r.get("chair"):
        out.append("the chair")
    elif user_email != r["chair"]:
        out.append(f"the chair's signature ({r['chair']})")
    m = r.get("meeting_on")
    if isinstance(m, str):
        m = dt.date.fromisoformat(m)
    start = r.get("period_start")
    if isinstance(start, str):
        start = dt.date.fromisoformat(start)
    if not m:
        out.append("the meeting date")
    elif m > today or (start and m < start):
        out.append("a meeting date within the period's start and today")
    if not (r.get("attendees") or "").strip():
        out.append("who attended")
    if not any((v or "").strip() for v in (r.get("notes") or {}).values()):
        out.append("the meeting's assessment of at least one input")
    if not (r.get("conclusion") or "").strip():
        out.append("the conclusion on the system's suitability, adequacy and effectiveness")
    if user_email in (r.get("involved") or []):
        out.append("a chair who did not prepare it")
    return out


def check_action(text: str, owner: str, due: dt.date, today: dt.date) -> list[str]:
    out = []
    if not text.strip():
        out.append("what is to be done")
    if not owner:
        out.append("who does it")
    if due < today:
        out.append("a due date that is not in the past")
    return out
