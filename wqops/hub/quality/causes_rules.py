"""Cause analysis rules, step 22b (ADR-0022): plain code, no AI, no network (tests/test_isolation.py).

What may be added where on a fishbone or a 5 Why, which suggestions of the model stand (only those citing records it
was shown), and when an analysis is ready to conclude. The database keeps closed analyses as they were; these rules
decide the steps before that.
"""

from __future__ import annotations

import re

METHODS = {"fishbone": "Fishbone", "five_why": "5 Why"}
BONES = ("People", "Machines", "Materials", "Methods", "Environment", "Measurement")
MAX_LEVEL = 7
MAX_TEXT = 500
MAX_REFS = 8
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class CauseError(ValueError):
    pass


def text(v, what: str = "the cause", n: int = MAX_TEXT) -> str:
    s = re.sub(r"\s+", " ", CONTROL.sub(" ", str(v if v is not None else ""))).strip()
    if not s:
        raise CauseError(f"write {what}")
    if len(s) > n:
        raise CauseError(f"{what} is longer than {n} characters")
    return s


def categories(v) -> list[str]:
    """The bones of a fishbone: the six usual ones unless the company names its own (2 to 10, no repeats)."""
    if v in (None, "", []):
        return list(BONES)
    if not isinstance(v, list):
        raise CauseError("the categories are a list")
    out: list[str] = []
    for raw in v:
        c = text(raw, "a category", 40)
        if c.lower() not in {x.lower() for x in out}:
            out.append(c)
    if not 2 <= len(out) <= 10:
        raise CauseError("a fishbone has 2 to 10 categories")
    return out


def refs(v) -> list[str]:
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        v = [v]
    out: list[str] = []
    for raw in v:
        r = CONTROL.sub("", str(raw)).strip()[:60]
        if r and r not in out:
            out.append(r)
    return out[:MAX_REFS]


def accepted(items: list[dict], level: int) -> list[dict]:
    return [i for i in items if i["level"] == level and i["status"] == "accepted"]


def frontier(items: list[dict]) -> int:
    """The why to ask next: one below the deepest answer a person accepted (1 when none is)."""
    levels = [i["level"] for i in items if i["status"] == "accepted" and i["level"]]
    return (max(levels) if levels else 0) + 1


def can_add(analysis: dict, items: list[dict], *, category: str | None, level: int | None) -> None:
    """Where a new cause may go. A fishbone cause goes on one of its bones; a why goes one level below an accepted
    answer: each level is confirmed by a person before the next is asked."""
    if analysis["status"] != "open":
        raise CauseError(f"{analysis['name']} is {analysis['status']}; add an addendum instead")
    if analysis["method"] == "fishbone":
        if category not in analysis["categories"]:
            raise CauseError(f"choose one of the categories: {', '.join(analysis['categories'])}")
        return
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= MAX_LEVEL:
        raise CauseError(f"a why is at level 1 to {MAX_LEVEL}")
    if level > 1 and not accepted(items, level - 1):
        raise CauseError(f"accept an answer to why {level - 1} first; each why is confirmed before the next")


def can_accept(analysis: dict, items: list[dict], item: dict) -> None:
    """A 5 Why keeps one accepted answer per level, on top of an accepted answer to the level above."""
    if analysis["method"] != "five_why":
        return
    lv = item["level"]
    if lv > 1 and not accepted(items, lv - 1):
        raise CauseError(f"accept an answer to why {lv - 1} first")
    other = [i for i in accepted(items, lv) if i["id"] != item["id"]]
    if other:
        raise CauseError(f"why {lv} already has an accepted answer; remove it first")


def can_remove(analysis: dict, items: list[dict], item: dict) -> None:
    if analysis["method"] == "five_why" and item["status"] == "accepted" and accepted(items, item["level"] + 1):
        raise CauseError(f"remove the answer to why {item['level'] + 1} first: it rests on this one")


def verify(proposals: list[dict], shown: set[str]) -> tuple[list[dict], list[dict]]:
    """Keep the model's suggestions that cite at least one record it was shown; drop cited numbers it was not shown.
    Returns (kept, dropped) with the reason for each dropped one."""
    kept, dropped = [], []
    for p in proposals:
        cited = refs(p.get("refs"))
        good = [r for r in cited if r in shown]
        bad = [r for r in cited if r not in shown]
        if not good:
            dropped.append({"text": str(p.get("text") or "")[:200], "refs": cited,
                            "reason": "cites no record it was shown" if cited else "cites no record"})
            continue
        kept.append(p | {"refs": good, "unshown": bad})
    return kept, dropped


def ready(analysis: dict, items: list[dict]) -> list[str]:
    """What still stands between the analysis and its conclusion (empty when ready)."""
    out = []
    if analysis["status"] != "open":
        out.append(f"{analysis['name']} is {analysis['status']}")
    if any(i["status"] == "proposed" for i in items):
        out.append("accept, edit or remove every suggestion first")
    if not any(i["status"] == "accepted" for i in items):
        out.append("accept at least one cause" if analysis["method"] == "fishbone" else "accept an answer to why 1")
    return out


def write_back(existing: str | None, conclusion: str, name: str, method: str) -> str:
    """The root cause text with the conclusion added; what was there is kept."""
    line = f"{conclusion} (from {METHODS[method]} {name})"
    return f"{existing.strip()}\n\n{line}" if (existing or "").strip() else line
