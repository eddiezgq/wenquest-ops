"""The checks behind a process pack's control points (ADR-0016): plain functions of the facts read from the records
(quality/system/qms.py) that say whether a control point is met.

Every check answers "met", "not_met" or "unknown". Missing data is unknown, never met: a check with nothing to look
at (no reports in the period, no documents) says so and stays unknown. Each answer names the records it rests on, so a
person can open them. Records imported from old ledgers are history: they are counted, not judged, because they
were not made under these rules. Plain code: no AI, no network, no database (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

MET, NOT_MET, UNKNOWN, NA = "met", "not_met", "unknown", "not_applicable"
SHOW = 25                                       # records listed per answer; the count says how many there are


def result(status: str, detail: str, problems: list[dict] | None = None, evidence: list[dict] | None = None) -> dict:
    problems, evidence = problems or [], evidence or []
    return {"status": status, "detail": detail, "problems": problems[:SHOW], "problem_count": len(problems),
            "evidence": evidence[:SHOW], "evidence_count": len(evidence)}


def ref(kind: str, row: dict, why: str = "") -> dict:
    return {"kind": kind, "id": row["id"], "label": row.get("name") or row.get("label") or str(row["id"]), "why": why}


def _day(v) -> dt.date | None:
    if v is None:
        return None
    return v.date() if isinstance(v, dt.datetime) else v


def _when(row: dict) -> dt.date | None:
    """When a record happened: the date written on an imported one, else when it was made."""
    return _day(row.get("reported_on")) or _day(row.get("created_at"))


def _in_window(row: dict, facts: dict) -> bool:
    d = _when(row)
    return d is not None and d >= facts["since"]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- documents

CONTROLLED = ("procedure", "work_instruction", "form")


def documents_approved(facts: dict, settings: dict) -> dict:
    docs = [d for d in facts["documents"] if d["doc_type"] in CONTROLLED and d["status"] not in ("rejected",
                                                                                                    "obsolete")]
    if not docs:
        return result(UNKNOWN, "No procedures, work instructions or forms in the document library yet.")
    effective = [d for d in docs if d["status"] == "effective"]
    waiting = [d for d in docs if d["status"] != "effective"]
    unsigned = [ref("document", d, "in effect without a recorded approval") for d in effective
                if d["id"] not in facts["document_approvals"]]
    if unsigned:
        return result(NOT_MET, f"{_plural(len(unsigned), 'document')} in effect without a recorded approval.", unsigned)
    if not effective:
        return result(NOT_MET, f"None of the {_plural(len(docs), 'controlled document')} has been approved yet.",
                      [ref("document", d, "not approved yet") for d in waiting])
    note = f" {_plural(len(waiting), 'other')} not approved yet, so not in use." if waiting else ""
    return result(MET, f"{_plural(len(effective), 'document')} in effect, each approved with a signature.{note}",
                  evidence=[ref("document", d) for d in effective])


CLASHES = ("number_conflict", "same_revision", "revisions", "duplicate")


def documents_current(facts: dict, settings: dict) -> dict:
    live = [d for d in facts["documents"] if d["status"] not in ("rejected", "obsolete")]
    if not live:
        return result(UNKNOWN, "No documents in the library yet.")
    bad = [i for i in facts["document_issues"] if i["kind"] in CLASHES]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'problem')} with revisions, numbers or copies.",
                      [{"kind": "document", "id": i["docs"][0], "label": i["title"], "why": i["detail"]} for i in bad])
    return result(MET, f"{_plural(len(live), 'document')} checked: one current revision each, no clashing numbers "
                       "or copies.")


def documents_referenced(facts: dict, settings: dict) -> dict:
    procs = [d for d in facts["documents"] if d["doc_type"] in ("procedure", "work_instruction")
             and d["status"] not in ("rejected", "obsolete")]
    if not procs:
        return result(UNKNOWN, "No procedures or work instructions in the library yet.")
    bad = [i for i in facts["document_issues"] if i["kind"] == "missing_ref"]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'procedure')} name documents that are not in the library.",
                      [{"kind": "document", "id": i["docs"][0], "label": i["title"], "why": i["detail"]} for i in bad])
    return result(MET, f"Every form and record the {_plural(len(procs), 'procedure')} name is in the library.")


# ---------------------------------------------------------------- nonconformances

def _ncrs(facts: dict) -> tuple[list[dict], list[dict]]:
    """Reports of the period made in WenQuest Ops, and those imported from old ledgers."""
    rows = [n for n in facts["ncrs"] if _in_window(n, facts)]
    return [n for n in rows if not n.get("source_doc")], [n for n in rows if n.get("source_doc")]


def _history(imported: list[dict]) -> str:
    return f" {_plural(len(imported), 'imported report')} counted as history, not judged." if imported else ""


def ncr_contained(facts: dict, settings: dict) -> dict:
    own, imported = _ncrs(facts)
    if not own:
        return result(UNKNOWN, f"No nonconformance reports in the last {settings['window_days']} days to judge."
                      + _history(imported))
    limit = int(settings["ncr_contain_days"])
    late = [ref("ncr", n, f"open for {(facts['today'] - _day(n['created_at'])).days} days without containment")
            for n in own if n["status"] == "open" and (facts["today"] - _day(n["created_at"])).days > limit]
    if late:
        return result(NOT_MET, f"{_plural(len(late), 'report')} not contained within {limit} days.", late)
    return result(MET, f"{_plural(len(own), 'report')}: none left uncontained for more than {limit} days."
                  + _history(imported))


def ncr_concession_approved(facts: dict, settings: dict) -> dict:
    own, imported = _ncrs(facts)
    needs = facts["approval_dispositions"]
    conc = [n for n in own if n.get("disposition") in needs and n["status"] in ("dispositioned", "closed")]
    if not conc:
        return result(UNKNOWN, f"No dispositions needing approval in the last {settings['window_days']} days."
                      + _history(imported))
    bad = []
    for n in conc:
        signed = facts["signatures"].get(("ncr", n["id"]), set())
        if not n.get("approved_by"):
            bad.append(ref("ncr", n, "no approval recorded"))
        elif n["approved_by"] == n.get("disposition_by"):
            bad.append(ref("ncr", n, "approved by the person who proposed it"))
        elif n["approved_by"] not in signed:
            bad.append(ref("ncr", n, "the approval has no signature"))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'concession')} without a proper approval.", bad)
    return result(MET, f"{_plural(len(conc), 'disposition')} needing approval, each signed by someone else.",
                  evidence=[ref("ncr", n) for n in conc])


def ncr_recorded(facts: dict, settings: dict) -> dict:
    own, imported = _ncrs(facts)
    closed = [n for n in own if n["status"] == "closed"]
    if not closed:
        return result(UNKNOWN, f"No reports closed in WenQuest Ops in the last {settings['window_days']} days."
                      + _history(imported))
    bad = []
    for n in closed:
        gaps = [w for w, ok in (("description", n.get("description")), ("disposition", n.get("disposition")),
                                ("reason for the disposition", n.get("disposition_reason")),
                                ("who closed it", n.get("closed_by"))) if not (ok or "").strip()]
        if n.get("closed_by") and n["closed_by"] not in facts["signatures"].get(("ncr", n["id"]), set()):
            gaps.append("the closing signature")
        if gaps:
            bad.append(ref("ncr", n, "missing: " + ", ".join(gaps)))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'closed report')} with something missing.", bad)
    return result(MET, f"{_plural(len(closed), 'closed report')}, each with description, disposition, reason and the "
                       "closing signature." + _history(imported), evidence=[ref("ncr", n) for n in closed])


def rejected_lots_have_ncr(facts: dict, settings: dict) -> dict:
    lots = facts["incoming_inspections"]
    if not lots:
        return result(UNKNOWN, f"No incoming inspections in the last {settings['window_days']} days.")
    rejected = [q for q in lots if q["rejected"]]
    missing = [{"kind": "inspection", "id": q["key"], "label": q["key"], "why": f"rejected {q.get('item_code') or ''} "
                "without a nonconformance report".replace("  ", " ")}
               for q in rejected if q["key"] not in facts["ncr_inspections"]]
    if missing:
        return result(NOT_MET, f"{_plural(len(missing), 'rejected lot')} without a nonconformance report.", missing)
    return result(MET, f"{_plural(len(lots), 'incoming inspection')}, {len(rejected)} rejected; every rejected lot has "
                       "a nonconformance report.")


# ---------------------------------------------------------------- corrective actions

def _capas(facts: dict) -> tuple[list[dict], list[dict]]:
    rows = [c for c in facts["capas"] if c["status"] != "cancelled" and (_in_window(c, facts)
                                                                          or c["status"] != "closed")]
    return [c for c in rows if not c.get("source_doc")], [c for c in rows if c.get("source_doc")]


def capa_for_major(facts: dict, settings: dict) -> dict:
    own, imported = _ncrs(facts)
    limit = int(settings["ncr_contain_days"])
    major = [n for n in own if n["severity"] == "major" and n["status"] != "cancelled"]
    if not major:
        return result(UNKNOWN, f"No major nonconformance reports in the last {settings['window_days']} days."
                      + _history(imported))
    linked = facts["ncr_capas"]
    bad = [ref("ncr", n, "major, no corrective action") for n in major
           if n["id"] not in linked and (facts["today"] - _day(n["created_at"])).days > limit]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'major report')} without a corrective action.", bad)
    return result(MET, f"{_plural(len(major), 'major report')}: each has a corrective action (or was opened in the "
                       f"last {limit} days)." + _history(imported), evidence=[ref("ncr", n) for n in major])


def capa_on_time(facts: dict, settings: dict) -> dict:
    own, _ = _capas(facts)
    ids = {c["id"]: c for c in own}
    actions = [a for a in facts["capa_actions"] if a["capa_id"] in ids]
    if not actions:
        return result(UNKNOWN, "No corrective or preventive actions with planned steps to judge.")
    grace = int(settings["capa_overdue_days"])
    late = []
    for a in actions:
        due = _day(a.get("due"))
        if due is None:
            continue
        done_on = _day(a.get("done_at"))
        if (a["done"] and done_on and (done_on - due).days > grace) or \
                (not a["done"] and (facts["today"] - due).days > grace):
            c = ids[a["capa_id"]]
            late.append({"kind": "capa", "id": c["id"], "label": c["name"],
                         "why": f"{a['text'][:80]}: due {due}" + (f", done {done_on}" if a["done"] else
                                                                       ", not done")})
    if late:
        return result(NOT_MET, f"{_plural(len(late), 'action')} late.", late)
    return result(MET, f"{_plural(len(actions), 'action')} with due dates: none late.")


def capa_effective(facts: dict, settings: dict) -> dict:
    own, imported = _capas(facts)
    closed = [c for c in own if c["status"] == "closed"]
    if not closed:
        note = f" {_plural(len(imported), 'imported action')} counted as history." if imported else ""
        return result(UNKNOWN, f"No corrective actions closed in WenQuest Ops in the last {settings['window_days']} "
                               "days." + note)
    bad = []
    for c in closed:
        gaps = []
        if c.get("verification_result") != "effective":
            gaps.append("an effective conclusion")
        if not (c.get("verification_method") or "").strip():
            gaps.append("the evidence of effectiveness")
        if not c.get("closed_by") or c["closed_by"] not in facts["signatures"].get(("capa", c["id"]), set()):
            gaps.append("the closing signature")
        elif c["closed_by"] == c.get("owner"):
            gaps.append("someone other than the owner to close it")
        if gaps:
            bad.append(ref("capa", c, "missing: " + ", ".join(gaps)))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'closed action')} without a recorded effectiveness review.", bad)
    return result(MET, f"{_plural(len(closed), 'closed action')}, each with its effectiveness evidence, signed by "
                       "someone other than the owner.", evidence=[ref("capa", c) for c in closed])


# ---------------------------------------------------------------- what people declare and link

def scope_declared(facts: dict, settings: dict) -> dict:
    """The scope: met once every control point that may be excluded has been declared, one way or the other."""
    names = facts["excludable"]
    open_ = [names[c] for c in names if c not in facts["applicability"]]
    excluded = {c: a for c, a in facts["applicability"].items() if not a["applies"] and c in names}
    if open_:
        return result(UNKNOWN, f"Say whether these apply: {', '.join(open_)}.")
    if not excluded:
        return result(MET, "Every requirement applies; nothing is excluded.")
    return result(MET, "Excluded, with reasons: " + "; ".join(f"{names[c]} ({a['reason']})"
                                                             for c, a in excluded.items()))


def linked_document(facts: dict, settings: dict, control: str) -> dict:
    docs = facts["evidence"].get(control, [])
    if not docs:
        return result(UNKNOWN, "No document linked as evidence yet.")
    live = [d for d in docs if d["status"] == "effective"]
    gone = [ref("document", d, f"linked but {d['status'].replace('_', ' ')}") for d in docs if d["status"] !=
            "effective"]
    if not live:
        return result(NOT_MET, "The linked documents are not in effect.", gone)
    return result(MET, "Evidence: " + ", ".join(d["name"] for d in live) + ".", gone,
                  [ref("document", d) for d in live])


def register(facts: dict, settings: dict, name: str) -> dict:
    return result(UNKNOWN, f"Evidence comes from the {name.replace('_', ' ')} register, which is not there yet "
                           "(next step).")


CHECKS = {f.__name__: f for f in (documents_approved, documents_current, documents_referenced, ncr_contained,
                                  ncr_concession_approved, ncr_recorded, rejected_lots_have_ncr, capa_for_major,
                                  capa_on_time, capa_effective, scope_declared)}


def evaluate(pack: dict, edition: str, facts: dict) -> dict:
    """Every control point of the pack: {control: result with process, summary, clauses}."""
    settings = pack.get("settings") or {}
    out = {}
    for pname, proc in pack["processes"].items():
        for c in proc["controls"]:
            rule = c["rule"]
            decl = facts["applicability"].get(c["id"])
            if c.get("may_exclude") and decl and not decl["applies"]:
                r = result(NA, f"Does not apply: {decl['reason']} (declared by {decl['email']})")
            elif rule == "linked_document":
                r = linked_document(facts, settings, c["id"])
            elif rule.startswith("register:"):
                r = register(facts, settings, rule.split(":", 1)[1])
            else:
                r = CHECKS[rule](facts, settings)
            out[c["id"]] = {**r, "process": pname, "summary": c["summary"], "clauses": (c.get("clauses") or {}).get(
                edition, []), "rule": rule}
    return out


def counts(results: dict) -> dict:
    out = {MET: 0, NOT_MET: 0, UNKNOWN: 0, NA: 0}
    for r in results.values():
        out[r["status"]] += 1
    return out


def check_pack(pack: dict) -> list[str]:
    """What is wrong with a pack file: unknown rules, duplicate control points, settings the checks need."""
    errs, seen = [], set()
    for need in ("window_days", "ncr_contain_days", "capa_overdue_days"):
        if not isinstance((pack.get("settings") or {}).get(need), int):
            errs.append(f"setting {need} is a whole number")
    for proc in (pack.get("processes") or {}).values():
        for c in proc.get("controls") or []:
            if c.get("id") in seen:
                errs.append(f"control point {c.get('id')} twice")
            seen.add(c.get("id"))
            rule = str(c.get("rule") or "")
            if rule not in CHECKS and rule != "linked_document" and not rule.startswith("register:"):
                errs.append(f"{c.get('id')}: unknown rule {rule!r}")
            for ed, cl in (c.get("clauses") or {}).items():
                if ed not in (pack.get("editions") or {}) or not isinstance(cl, list) or not cl:
                    errs.append(f"{c.get('id')}: clauses for edition {ed!r} are a list")
            if c.get("may_exclude") and not str(c.get("short") or "").strip():
                errs.append(f"{c.get('id')}: a short name, to say it does not apply")
            if not str(c.get("summary") or "").strip():
                errs.append(f"{c.get('id')}: a summary")
    return errs
