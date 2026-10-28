"""Change control checks, step 17g (ADR-0017; dee-qms PLAN-CHANGE): what a change needs before it is submitted,
implemented and closed. The answers to the questions are a person's; nothing here answers them.

Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

from wqops.i18n import say

KINDS = ("product", "process", "supplier", "document", "software", "equipment", "other")
QUESTIONS = {
    "q_product": "Does it affect the form, fit, function, safety or performance of product already released?",
    "q_regulatory": "Could it need a regulatory submission or notification?",
    "q_risk": "Does the risk management file need updating?",
    "q_validation": "Does it need verification or validation before it is implemented?",
}


def questions() -> dict[str, str]:
    """The questions in the reader's language (the keys are what the answers are stored under)."""
    return {k: say(q) for k, q in QUESTIONS.items()}


def _blank(v) -> bool:
    return not str(v or "").strip()


def to_submit(c: dict, docs: dict[int, dict] | None = None) -> list[str]:
    """``docs``: the documents it changes, by id; each must still be in effect."""
    out = []
    for k, what in (("title", say("a title")), ("description", say("what changes")), ("reason", say("why")),
                    ("owner", say("an owner")), ("assessment", say("the assessment"))):
        if _blank(c.get(k)):
            out.append(what)
    if c.get("kind") not in KINDS:
        out.append(say("the kind of change"))
    out += [say("answer: {question}", question=say(q)) for k, q in QUESTIONS.items() if c.get(k) not in ("yes", "no")]
    if c.get("q_regulatory") == "yes" and _blank(c.get("regulatory_decision")):
        out.append(say("the regulatory decision (what will be submitted or notified, or why not)"))
    if c.get("q_validation") == "yes" and _blank(c.get("validation_plan")):
        out.append(say("the verification or validation plan"))
    for d in c.get("documents") or []:
        doc = (docs or {}).get(int(d))
        if docs is not None and (doc is None or doc.get("status") != "effective"):
            name = (doc or {}).get("number") or say("document {id}", id=d)
            out.append(say("{name} is no longer in effect: choose its current revision", name=name))
    return out


def to_implement(c: dict, docs: dict[int, dict]) -> list[str]:
    """``docs``: the documents it affects and its new revisions, by id ({status, supersedes, number, approved_at}).
    A new revision counts only if it was approved after the change was."""
    out = []
    if _blank(c.get("implementation")):
        out.append(say("how it was implemented"))
    if c.get("q_validation") == "yes" and _blank(c.get("validation_result")):
        out.append(say("the verification or validation result"))
    revs = [docs.get(int(r)) for r in c.get("revisions") or []]
    for d in c.get("documents") or []:
        new = [r for r in revs if r and r.get("supersedes") == int(d) and r.get("status") == "effective"
               and (c.get("approved_at") is None or (r.get("approved_at") and r["approved_at"] >= c["approved_at"]))]
        if not new:
            name = (docs.get(int(d)) or {}).get("number") or say("document {id}", id=d)
            out.append(say("a new revision of {name}, approved after the change and in effect", name=name))
    return out


def to_close(c: dict) -> list[str]:
    return [say("the effectiveness check")] if _blank(c.get("effectiveness")) else []
