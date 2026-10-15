"""Change control checks, step 17g (ADR-0017; dee-qms PLAN-CHANGE): what a change needs before it is submitted,
implemented and closed. The answers to the questions are a person's; nothing here answers them.

Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

KINDS = ("product", "process", "supplier", "document", "software", "equipment", "other")
QUESTIONS = {
    "q_product": "Does it affect the form, fit, function, safety or performance of product already released?",
    "q_regulatory": "Could it need a regulatory submission or notification?",
    "q_risk": "Does the risk management file need updating?",
    "q_validation": "Does it need verification or validation before it is implemented?",
}


def _blank(v) -> bool:
    return not str(v or "").strip()


def to_submit(c: dict) -> list[str]:
    out = []
    for k, what in (("title", "a title"), ("description", "what changes"), ("reason", "why"),
                    ("owner", "an owner"), ("assessment", "the assessment")):
        if _blank(c.get(k)):
            out.append(what)
    if c.get("kind") not in KINDS:
        out.append("the kind of change")
    out += [f"answer: {q}" for k, q in QUESTIONS.items() if c.get(k) not in ("yes", "no")]
    if c.get("q_regulatory") == "yes" and _blank(c.get("regulatory_decision")):
        out.append("the regulatory decision (what will be submitted or notified, or why not)")
    if c.get("q_validation") == "yes" and _blank(c.get("validation_plan")):
        out.append("the verification or validation plan")
    return out


def to_implement(c: dict, docs: dict[int, dict]) -> list[str]:
    """``docs``: the documents it affects and its new revisions, by id ({status, supersedes, number})."""
    out = []
    if _blank(c.get("implementation")):
        out.append("how it was implemented")
    if c.get("q_validation") == "yes" and _blank(c.get("validation_result")):
        out.append("the verification or validation result")
    revs = [docs.get(int(r)) for r in c.get("revisions") or []]
    for d in c.get("documents") or []:
        new = [r for r in revs if r and r.get("supersedes") == int(d) and r.get("status") == "effective"]
        if not new:
            name = (docs.get(int(d)) or {}).get("number") or f"document {d}"
            out.append(f"a new revision of {name}, in effect")
    return out


def to_close(c: dict) -> list[str]:
    return ["the effectiveness check"] if _blank(c.get("effectiveness")) else []
