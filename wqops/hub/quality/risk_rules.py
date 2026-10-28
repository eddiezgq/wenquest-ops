"""Risk management rules, step 17h (ADR-0017; dee-qms PLAN-RISK). Pure functions: no database, no AI, no network.

Acceptability is only ever looked up in the company's matrix (severity rank x probability rank); a missing cell is
"not determined" and stops approval. The matrix and the levels are the company's own criteria, not standard values.
"""

from __future__ import annotations

import hashlib
import json

from wqops.i18n import say

VERDICTS = {"acceptable": "Acceptable", "reduce": "Reduce as far as possible", "unacceptable": "Unacceptable"}
KINDS = ("severity", "probability")

# An example only, so a new company sees how it works; every company replaces it with its own criteria.
EXAMPLE_NOTE = "Example - replace with your company's criteria"
EXAMPLE_LEVELS = {
    "severity": ["Negligible", "Minor", "Serious", "Critical", "Catastrophic"],
    "probability": ["Improbable", "Remote", "Occasional", "Probable", "Frequent"],
}


def verdicts() -> dict[str, str]:
    """The verdict names in the reader's language (the keys are what is stored)."""
    return {k: say(v) for k, v in VERDICTS.items()}


def shown_levels(levels: list[dict]) -> list[dict]:
    """The levels as sent to the page: an example level nobody changed yet (its name and the example note as loaded)
    is shown in the reader's language; every level a company named or described itself is sent as it is."""
    out = []
    for lv in levels:
        names = EXAMPLE_LEVELS.get(lv.get("kind"), [])
        x = dict(lv)
        if 1 <= (lv.get("rank") or 0) <= len(names) and lv.get("name") == names[lv["rank"] - 1]:
            x["name"] = say("risk level::" + lv["name"])
        if lv.get("description") == EXAMPLE_NOTE:
            x["description"] = say(EXAMPLE_NOTE)
        out.append(x)
    return out


def example_matrix() -> dict[tuple[int, int], str]:
    """The example 5 x 5: product of the ranks up to 4 acceptable, up to 9 reduce, above that unacceptable."""
    return {(s, p): "acceptable" if s * p <= 4 else "reduce" if s * p <= 9 else "unacceptable"
            for s in range(1, 6) for p in range(1, 6)}


def verdict(matrix: dict[tuple[int, int], str], severity: int | None, probability: int | None) -> str | None:
    """The cell of the matrix; None when either rank is missing or the matrix has no such cell."""
    if severity is None or probability is None:
        return None
    return matrix.get((severity, probability))


def item_needs(item: dict, matrix: dict[tuple[int, int], str]) -> list[str]:
    """What one item still needs before its file can be approved."""
    n = item.get("seq")
    out = []
    if not (item.get("hazard") or "").strip() or not (item.get("harm") or "").strip():
        out.append(say("item {n}: the hazard and the harm", n=n))
    first = verdict(matrix, item.get("severity"), item.get("probability"))
    if first is None:
        out.append(say("item {n}: the initial risk is not determined (severity and probability, and a matrix cell "
                       "for them)", n=n))
    if first != "acceptable":
        if not (item.get("controls") or "").strip() or not (item.get("verification") or "").strip():
            out.append(say("item {n}: risk controls and how they were verified", n=n))
        rest = verdict(matrix, item.get("res_severity"), item.get("res_probability"))
        if rest is None:
            out.append(say("item {n}: the residual risk is not determined", n=n))
        elif rest == "unacceptable" and not (item.get("benefit_risk") or "").strip():
            out.append(say("item {n}: the residual risk is unacceptable: say why the benefit outweighs it", n=n))
    elif item.get("res_severity") is not None and verdict(matrix, item.get("res_severity"),
                                                          item.get("res_probability")) is None:
        out.append(say("item {n}: the residual risk is not determined", n=n))
    return out


def to_approve(f: dict, items: list[dict], matrix: dict[tuple[int, int], str]) -> list[str]:
    out = []
    if not items:
        out.append(say("at least one hazard"))
    if not (f.get("conclusion") or "").strip():
        out.append(say("the overall residual risk conclusion"))
    for it in items:
        out += item_needs(it, matrix)
    return out


def residual(item: dict, matrix: dict[tuple[int, int], str]) -> str | None:
    """The risk left: the residual cell when residual ranks are given, else the initial one."""
    if item.get("res_severity") is not None:
        return verdict(matrix, item["res_severity"], item["res_probability"])
    return verdict(matrix, item.get("severity"), item.get("probability"))


def criteria(levels: list[dict], matrix: dict[tuple[int, int], str]) -> dict:
    """The criteria as they are now, in a form kept with an approved file."""
    return {"levels": sorted(({"kind": lv["kind"], "rank": lv["rank"], "name": lv["name"]} for lv in levels
                              if lv.get("active", True)), key=lambda x: (x["kind"], x["rank"])),
            "matrix": sorted([s, p, v] for (s, p), v in matrix.items())}


ITEM_KEYS = ("seq", "hazard", "situation", "harm", "severity", "probability", "controls", "verification",
             "res_severity", "res_probability", "benefit_risk", "capa_id", "initial_verdict", "residual_verdict")
FILE_KEYS = ("name", "version", "product", "scope", "owner", "conclusion", "benefit_risk")


def fingerprint(f: dict, items: list[dict], crit: dict) -> str:
    """SHA-256 of what was approved: the file, its items and the criteria used."""
    body = {"file": {k: f.get(k) for k in FILE_KEYS},
            "items": [{k: it.get(k) for k in ITEM_KEYS} for it in sorted(items, key=lambda x: x["seq"])],
            "criteria": crit}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def matrix_gaps(levels: list[dict], matrix: dict[tuple[int, int], str]) -> list[str]:
    """Cells of the active levels the matrix does not decide."""
    sev = sorted(lv["rank"] for lv in levels if lv["kind"] == "severity" and lv.get("active", True))
    prob = sorted(lv["rank"] for lv in levels if lv["kind"] == "probability" and lv.get("active", True))
    return [f"S{s} x P{p}" for s in sev for p in prob if (s, p) not in matrix]
