"""Complaint checks, step 17e (ADR-0017; dee-qms PLAN-COMPLAINT): what is still needed at each step, and how a
reporting decision stands against the three questions. The decision itself is a person's; nothing here makes it.

Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

from wqops.i18n import say

QUESTIONS = {
    "q_harm": "Did the device cause or contribute to a death or serious injury, or may it have?",
    "q_malfunction": "Did the device malfunction, and could the malfunction cause or contribute to a death or serious "
                     "injury if it happened again?",
    "q_recall": "Does it concern a recall, correction or removal?",
}


def questions() -> dict[str, str]:
    """The questions in the reader's language (the keys are what the answers are stored under)."""
    return {k: say(q) for k, q in QUESTIONS.items()}


def to_investigate(c: dict) -> list[str]:
    """What a complaint needs before its investigation starts."""
    out = []
    if not c.get("owner"):
        out.append(say("an owner"))
    if not c.get("item_code"):
        out.append(say("the product"))
    if not str(c.get("description") or "").strip():
        out.append(say("what happened"))
    if c.get("injury") not in ("yes", "no"):
        out.append(say("whether anyone was hurt (yes or no)"))
    return out


def assessment(answers: dict, reportable, reason: str) -> dict:
    """The person's decision against the questions: every question answered, a decision and its reason. A yes with
    a decision not to report is allowed, and counted as an exception."""
    missing = [k for k in QUESTIONS if answers.get(k) not in ("yes", "no")]
    errs = [say("answer: {question}", question=say(QUESTIONS[k])) for k in missing]
    if type(reportable) is not bool:
        errs.append(say("decide whether it must be reported"))
    if not str(reason or "").strip():
        errs.append(say("give the reason for the decision"))
    any_yes = any(answers.get(k) == "yes" for k in QUESTIONS)
    return {"errors": errs, "any_yes": any_yes, "suggest": "report" if any_yes else None,
            "exception": any_yes and reportable is False}


def to_close(c: dict) -> list[str]:
    """Everything still needed to close, listed at once."""
    out = []
    if c.get("status") != "assessed":
        out.append(say("the reporting decision, signed"))
    if c.get("investigate", True) and not str(c.get("investigation") or "").strip():
        out.append(say("the investigation's conclusion (or the reason, approved, for not investigating)"))
    if not c.get("investigate", True) and not str(c.get("no_investigation_reason") or "").strip():
        out.append(say("the reason for not investigating"))
    if c.get("reportable") and (not str(c.get("report_ref") or "").strip() or not c.get("reported_on")):
        out.append(say("the report's reference and the day it was made"))
    if not str(c.get("response") or "").strip():
        out.append(say("the reply to the customer"))
    return out
