"""Checks of the document library (ADR-0014 item 4, step 14b): duplicates, several revisions of one number and which
is current, number conflicts, missing numbers, revisions and dates, numbers that differ from the company's own
convention, forms and records a procedure names that are missing, records without a procedure, and processes with no
documents. Also the suggested number and standard file name of a document.

The numbering convention of each type is the company's configured rule, else learned from the numbers it already
uses (the most common prefix), else a plain default. Original file names are never changed.

Plain code over the documents' fields: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict

from wqops.hub.docs import classify as K

NUMBERED = K.CONTROLLED | {"spec"}            # one number = one document with revisions
LIVE = ("to_classify", "to_review", "draft", "in_review", "effective", "confirmed")
DEFAULT_RULES = {"procedure": ("QP-{seq}", 2), "work_instruction": ("WI-{process}-{seq}", 2),
                 "form": ("F-{process}-{seq}", 3), "spec": ("SP-{seq}", 3)}
SEVERITY = {"high": 0, "medium": 1, "info": 2}


def norm_no(n: str | None) -> str:
    """Numbers compared as written, ignoring case and spaces or underscores in place of dashes (F RI 001 = F-RI-001)."""
    return re.sub(r"[\s_]+", "-", (n or "").strip()).upper()


def norm_rev(rev: str | None) -> str:
    """"Rev. C", "rev c" and "C" are one revision; so are "01" and "1"."""
    r = re.sub(r"^(REVISION|REV)[\s.:#-]*", "", (rev or "").strip().upper())
    return re.sub(r"\d+", lambda m: str(int(m.group(0))), r)


def rev_key(rev: str | None) -> tuple:
    """Order of revisions: numbers part by part (1.9 < 1.10), letters by the alphabet (A < B < ... < Z < AA),
    numbers before letters."""
    r = norm_rev(rev)
    if re.fullmatch(r"\d+(\.\d+)*", r):
        return (1, tuple(int(x) for x in r.split(".")), "")
    if re.fullmatch(r"[A-Z]{1,3}", r):
        return (2, (len(r),), r)
    return (0, (), r)


def _when(d: dict) -> dt.date:
    v = d.get("effective_date")
    if isinstance(v, str) and v:
        return dt.date.fromisoformat(v[:10])
    return v if isinstance(v, dt.date) else dt.date.min


def newest(docs: list[dict]) -> dict:
    """The current one among revisions: the effective one if there is one, else the highest revision, then the
    latest effective date, then the most recent upload."""
    eff = [d for d in docs if d["status"] == "effective"]
    pool = eff or docs
    kinds = {rev_key(d.get("revision"))[0] for d in pool}
    if len(kinds) == 1 and 0 not in kinds:
        return max(pool, key=lambda d: (rev_key(d.get("revision")), _when(d), d["id"]))
    return max(pool, key=lambda d: (_when(d), d["id"]))


def _shape(n: str) -> str:
    return re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", norm_no(n)))


def _prefix(n: str | None) -> tuple[str, int] | None:
    m = re.fullmatch(r"(.*?)(\d+)", norm_no(n))
    return (m.group(1), len(m.group(2))) if m and m.group(1) else None


# ---------------------------------------------------------------- numbering conventions

def process_codes(docs: list[dict], processes: dict[str, dict]) -> dict[str, str]:
    """The code a company uses for each process inside its numbers (the middle of F-QA-012), learned from the
    numbers it has; else the configured short code."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for d in docs:
        parts = norm_no(d.get("number")).split("-")
        if d.get("process") and len(parts) == 3 and parts[1].isalpha() and parts[1].isascii() \
                and 1 <= len(parts[1]) <= 4 and d["status"] in LIVE:
            seen[d["process"]][parts[1]] += 1
    return {p: (seen[p].most_common(1)[0][0] if seen[p] else (info.get("short") or "GEN"))
            for p, info in processes.items()}


def conventions(docs: list[dict], rules: dict[str, dict]) -> dict[str, dict]:
    """For each numbered type: the template and digits used to suggest numbers, and where they come from."""
    out = {}
    for t in sorted(NUMBERED):
        if t in rules:
            out[t] = {"template": rules[t]["template"], "digits": rules[t]["digits"], "source": "rule"}
            continue
        nums = [d["number"] for d in docs if d.get("doc_type") == t and d.get("number") and d["status"] in LIVE]
        shapes = Counter(_shape(n) for n in nums)
        if len(nums) >= 2 and shapes.most_common(1)[0][1] / len(nums) >= 0.6:
            shape = shapes.most_common(1)[0][0]
            same = [n for n in nums if _shape(n) == shape]
            prefixes = Counter(p for p in map(_prefix, same) if p)
            if prefixes:                                 # numbers like 1001 have no prefix to learn: default
                (prefix, digits), _ = prefixes.most_common(1)[0]
                parts = prefix.rstrip("-").split("-")
                mid = len(parts) == 2 and prefix.endswith("-") and parts[1].isalpha() and parts[1].isascii()
                tmpl = f"{parts[0]}-{{process}}-{{seq}}" if mid else prefix + "{seq}"
                out[t] = {"template": tmpl, "digits": digits, "source": "learned", "examples": sorted(set(same))[:4]}
                continue
        tmpl, digits = DEFAULT_RULES[t]
        out[t] = {"template": tmpl, "digits": digits, "source": "default"}
    return out


def render(template: str, digits: int, code: str, seq: int) -> str:
    return template.replace("{process}", code or "GEN").replace("{seq}", str(seq).zfill(digits))


def matches(number: str, conv: dict) -> bool:
    """Whether a number follows the type's convention (any process code, any sequence number)."""
    rx = ""
    for part in re.split(r"(\{process\}|\{seq\})", conv["template"]):
        rx += r"[A-Z]{1,4}" if part == "{process}" else rf"\d{{{conv['digits']},}}" if part == "{seq}" \
            else re.escape(part.upper())
    return re.fullmatch(rx, norm_no(number)) is not None


def suggest_number(doc: dict, docs: list[dict], convs: dict[str, dict], codes: dict[str, str],
                   taken: set[str] | None = None) -> str | None:
    """The next free number in the type's convention, for a numbered document without a (proper) number. Numbers
    already suggested to other documents (``taken``) are not suggested again."""
    t = doc.get("doc_type")
    if t not in convs:
        return None
    conv = convs[t]
    code = codes.get(doc.get("process") or "", "GEN")
    base = render(conv["template"], conv["digits"], code, 0)
    prefix = base[: len(base) - conv["digits"]]
    taken = taken if taken is not None else set()
    used = {norm_no(d["number"]) for d in docs if d.get("number")} | taken
    seqs = [int(m.group(1)) for n in used if (m := re.fullmatch(re.escape(norm_no(prefix)) + r"(\d+)", n))]
    seq = max(seqs, default=0) + 1
    while norm_no(render(conv["template"], conv["digits"], code, seq)) in used:
        seq += 1
    out = render(conv["template"], conv["digits"], code, seq)
    taken.add(norm_no(out))
    return out


def standard_name(doc: dict) -> str | None:
    """"<number> <title> Rev <revision>.<ext>" for a document with a number and a title; never applied to the stored
    original name, only offered for downloads."""
    if not doc.get("number") or not doc.get("title"):
        return None
    ext = re.search(r"\.[A-Za-z0-9]{1,5}$", doc.get("original_name") or "")
    name = f"{doc['number']} {doc['title']}" + (f" Rev {doc['revision']}" if doc.get("revision") else "")
    name = re.sub(r'[\\/:*?"<>|]+', " ", name)
    return re.sub(r"\s+", " ", name).strip()[:180] + (ext.group(0).lower() if ext else "")


# ---------------------------------------------------------------- issues

def _issue(kind: str, severity: str, title: str, detail: str, docs: list[int], process: str | None = None,  # noqa: PLR0917
           **extra) -> dict:
    return {"kind": kind, "severity": severity, "title": title, "detail": detail, "docs": docs, "process": process,
            **extra}


def _words(s: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in {"the", "and", "for", "rev"}}


def label(d: dict) -> str:
    no, title = d.get("number"), d.get("title") or ""
    if no and norm_no(title).startswith(norm_no(no)):          # titles often repeat the number
        no = None
    return " ".join(x for x in (no, title, f"rev {d['revision']}" if d.get("revision") else "") if x) \
        or d["original_name"]


def issues(docs: list[dict], processes: dict[str, dict], convs: dict[str, dict],  # noqa: PLR0912, PLR0915
           codes: dict[str, str]) -> list[dict]:
    live = [d for d in docs if d["status"] in LIVE]
    out: list[dict] = []

    # identical files
    by_sha = defaultdict(list)
    for d in live:
        by_sha[d["sha256"]].append(d)
    for group in by_sha.values():
        if len(group) > 1:
            keep = min(group, key=lambda d: (d["status"] not in ("effective", "confirmed"), d["id"]))  # = keeper
            names = ", ".join(f"{d['path']}/{d['original_name']}".strip("/") for d in group)
            out.append(_issue("duplicate", "medium", f"Same file {len(group)} times: {group[0]['original_name']}",
                              f"Identical content: {names}. Keep one; mark the others as not kept.",
                              [d["id"] for d in group], keep["process"], keep=keep["id"]))
    def keeper(g):
        return min(g, key=lambda d: (d["status"] not in ("effective", "confirmed"), d["id"]))

    dup_ids = {d["id"] for g in by_sha.values() if len(g) > 1 for d in g if d is not keeper(g)}
    taken: set[str] = set()                         # suggested numbers, one per document

    # one number: revisions, which is current, and conflicts
    by_no = defaultdict(list)
    for d in live:
        if d.get("number") and d.get("doc_type") in NUMBERED and d["id"] not in dup_ids:
            by_no[norm_no(d["number"])].append(d)
    for no, everything in by_no.items():
        ids = {d["id"] for d in everything}
        # a new revision uploaded on purpose (it replaces one of these) is work in progress, not a problem
        group = [d for d in everything if not (d.get("supersedes") in ids and d["status"] in ("draft", "in_review"))]
        if len(group) < 2:
            continue
        types = {d["doc_type"] for d in group}
        titles = [_words(d.get("title")) for d in group]
        unlike = any(a and b and len(a & b) / len(a | b) < 0.34 for i, a in enumerate(titles) for b in titles[i + 1:])
        if len(types) > 1 or unlike:
            out.append(_issue("number_conflict", "high", f"{no} is used for different documents",
                              "; ".join(f"{label(d)} ({K.TYPES.get(d['doc_type'], d['doc_type'])})" for d in group)
                              + ". Give one of them a new number.", [d["id"] for d in group], group[0]["process"]))
            continue
        revs = [norm_rev(d.get("revision")) for d in group if d.get("revision")]
        if len(set(revs)) < len(revs):
            out.append(_issue("same_revision", "high", f"{no}: the same revision more than once",
                              ", ".join(f"{label(d)} ({d['original_name']})" for d in group)
                              + ". If the files differ, one of them needs another revision.",
                              [d["id"] for d in group], group[0]["process"]))
            continue
        if len(revs) < len(group):                  # without revisions the order is unknown; no_revision says so
            continue
        cur = newest(group)
        older = [d for d in group if d is not cur and d["status"] != "obsolete"]
        if older:
            out.append(_issue("revisions", "medium", f"{no}: {len(group)} revisions, rev {cur.get('revision')} is "
                                                     "current",
                              f"Current: {label(cur)}. Older: " + ", ".join(label(d) for d in older)
                              + ". Keep the older ones as obsolete so their history stays.",
                              [cur["id"]] + [d["id"] for d in older], cur["process"], keep=cur["id"],
                              older=[d["id"] for d in older]))

    # missing fields and numbers off the convention
    for d in live:
        if d["id"] in dup_ids or d.get("doc_type") not in NUMBERED:
            continue
        if not d.get("number"):
            sug = suggest_number(d, docs, convs, codes, taken)
            out.append(_issue("no_number", "medium", f"No number: {d.get('title') or d['original_name']}",
                              f"Suggested number: {sug}." if sug else "Give it a number.", [d["id"]], d.get("process"),
                              suggest=sug))
        elif convs.get(d["doc_type"], {}).get("source") != "default" and \
                not matches(d["number"], convs[d["doc_type"]]):
            sug = suggest_number(d, docs, convs, codes, taken)
            conv = convs[d["doc_type"]]
            example = render(conv["template"], conv["digits"], codes.get(d.get("process") or "", "XX"), 1)
            out.append(_issue("odd_number", "info", f"{d['number']} differs from your other "
                                                    f"{K.TYPES[d['doc_type']].lower()}s",
                              f"Convention: {example}"
                              + (f"; suggested {sug}" if sug else "") + ".", [d["id"]], d.get("process"), suggest=sug))
        if d["doc_type"] in K.CONTROLLED and not d.get("revision"):
            out.append(_issue("no_revision", "medium", f"No revision: {label(d)}",
                              "Give it a revision before it is sent for approval.", [d["id"]], d.get("process")))
    undated = [d for d in live if d["id"] not in dup_ids and d.get("doc_type") in K.CONTROLLED
               and not d.get("effective_date") and d["status"] != "effective"]
    if undated:
        out.append(_issue("no_date", "info", f"{len(undated)} document(s) show no effective date",
                          ", ".join(label(d) for d in undated) + ". Add the date if it is known; otherwise the "
                          "approval date will be used.", [d["id"] for d in undated]))

    # what procedures name, and what records rest on
    known = {norm_no(d["number"]) for d in live if d.get("number")}
    prefixes = {p[0] for p in map(_prefix, known) if p}       # a named code is a document only if it looks like one
    for d in live:
        if d.get("doc_type") not in ("procedure", "work_instruction") or d["id"] in dup_ids:
            continue
        own = norm_no(d.get("number"))
        missing = sorted({norm_no(r) for r in d.get("refs") or []} - known - {own})
        missing = [m for m in missing if not m.startswith(own + "-") and (_prefix(m) or ("",))[0] in prefixes]
        if missing:
            out.append(_issue("missing_ref", "medium", f"{label(d)} names documents that are not in the library",
                              "Missing: " + ", ".join(missing) + ". Import them, or correct the procedure.",
                              [d["id"]], d.get("process"), missing=missing))
    forms = [d for d in live if d.get("doc_type") == "form" and d.get("number") and d["id"] not in dup_ids]
    records = [d for d in live if d.get("doc_type") == "record"]
    unused = []
    for f in forms:
        no = norm_no(f["number"])
        if not any(norm_no(r.get("number")) == no or no in {norm_no(x) for x in r.get("refs") or []}
                   for r in records):
            unused.append(f)
    if unused:
        out.append(_issue("form_unused", "info", f"{len(unused)} form(s) without any record in the library",
                          ", ".join(label(f) for f in unused) + ". Import their filled-in records, or check whether "
                          "the forms are still used.", [f["id"] for f in unused]))
    procs_with_procedure = {d.get("process") for d in live if d.get("doc_type") in ("procedure", "work_instruction")}
    by_proc = defaultdict(list)
    for r in records:
        by_proc[r.get("process")].append(r)
    for p, rs in by_proc.items():
        if p and p != "other" and p not in procs_with_procedure:
            name = processes.get(p, {}).get("name", p)
            out.append(_issue("no_procedure", "medium", f"{name}: records but no procedure",
                              f"{len(rs)} record(s) and no procedure or work instruction saying how the work is done.",
                              [r["id"] for r in rs], p))
    present = {d.get("process") for d in live}
    for p, info in processes.items():
        if p != "other" and p not in present:
            out.append(_issue("empty_process", "info", f"{info['name']}: no documents",
                              "Nothing for this process yet.", [], p))
    out.sort(key=lambda i: (SEVERITY[i["severity"]], i["kind"], i["title"]))
    return out
