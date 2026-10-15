"""Complaint checks, step 17e (ADR-0017; dee-qms PLAN-COMPLAINT): what is still needed at each step, and how a
reporting decision stands against the three questions. The decision itself is a person's; nothing here makes it.

Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

QUESTIONS = {
    "q_harm": "Did the device cause or contribute to a death or serious injury, or may it have?",
    "q_malfunction": "Did the device malfunction, and could the malfunction cause or contribute to a death or serious "
                     "injury if it happened again?",
    "q_recall": "Does it concern a recall, correction or removal?",
}


def to_investigate(c: dict) -> list[str]:
    """What a complaint needs before its investigation starts."""
    out = []
    if not c.get("owner"):
        out.append("an owner")
    if not c.get("item_code"):
        out.append("the product")
    if not str(c.get("description") or "").strip():
        out.append("what happened")
    if c.get("injury") not in ("yes", "no"):
        out.append("whether anyone was hurt (yes or no)")
    return out


def assessment(answers: dict, reportable, reason: str) -> dict:
    """The person's decision against the questions: every question answered, a decision and its reason. A yes with
    a decision not to report is allowed, and counted as an exception."""
    missing = [k for k in QUESTIONS if answers.get(k) not in ("yes", "no")]
    errs = [f"answer: {QUESTIONS[k]}" for k in missing]
    if type(reportable) is not bool:
        errs.append("decide whether it must be reported")
    if not str(reason or "").strip():
        errs.append("give the reason for the decision")
    any_yes = any(answers.get(k) == "yes" for k in QUESTIONS)
    return {"errors": errs, "any_yes": any_yes, "suggest": "report" if any_yes else None,
            "exception": any_yes and reportable is False}


def to_close(c: dict) -> list[str]:
    """Everything still needed to close, listed at once."""
    out = []
    if c.get("status") != "assessed":
        out.append("the reporting decision, signed")
    if c.get("investigate", True) and not str(c.get("investigation") or "").strip():
        out.append("the investigation's conclusion (or the reason, approved, for not investigating)")
    if not c.get("investigate", True) and not str(c.get("no_investigation_reason") or "").strip():
        out.append("the reason for not investigating")
    if c.get("reportable") and (not str(c.get("report_ref") or "").strip() or not c.get("reported_on")):
        out.append("the report's reference and the day it was made")
    if not str(c.get("response") or "").strip():
        out.append("the reply to the customer")
    return out
