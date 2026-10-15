"""The checks behind a process pack's control points (ADR-0016): plain functions of the facts read from the records
(system/qms.py) that say whether a control point is met.

Every check answers "met", "not_met" or "unknown". Missing data is unknown, never met: a check with nothing to look
at (no reports in the period, no documents) says so and stays unknown. Each answer names the records it rests on, so a
person can open them.

Which records a check judges: those not cancelled that are still open, or that were closed within the period (a
record opened long ago and closed yesterday is judged). Records imported from old ledgers that were already closed
are history: counted, not judged, because they were not made under these rules; imported records still open are
worked in WenQuest Ops and judged from the day they were imported. Dates are the company's days, prepared by
system/qms.py (``opened``, ``closed_on``, ``contained_on``, ``when``). Plain code: no AI, no network, no database
(tests/test_isolation.py).
"""

from __future__ import annotations

MET, NOT_MET, UNKNOWN, NA = "met", "not_met", "unknown", "not_applicable"
SHOW = 25                                       # records listed per answer; the count says how many there are


def result(status: str, detail: str, problems: list[dict] | None = None, evidence: list[dict] | None = None) -> dict:
    problems, evidence = problems or [], evidence or []
    return {"status": status, "detail": detail, "problems": problems[:SHOW], "problem_count": len(problems),
            "evidence": evidence[:SHOW], "evidence_count": len(evidence)}


def ref(kind: str, row: dict, why: str = "") -> dict:
    return {"kind": kind, "id": row["id"], "label": row.get("name") or row.get("label") or str(row["id"]), "why": why}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def judged(rows: list[dict], facts: dict) -> tuple[list[dict], list[dict]]:
    """(records judged, imported history) of the period."""
    out, history = [], []
    for r in rows:
        if r["status"] == "cancelled":
            continue
        closed = r["status"] == "closed"
        if r.get("imported") and closed:
            if (r.get("when") or r["opened"]) >= facts["since"]:
                history.append(r)
        elif not closed or (r.get("closed_on") and r["closed_on"] >= facts["since"]):
            out.append(r)
    return out, history


def _history(rows: list[dict], what: str = "report") -> str:
    return f" {_plural(len(rows), 'imported ' + what)} counted as history, not judged." if rows else ""


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


def _controlled(facts: dict) -> list[dict]:
    return [d for d in facts["documents"] if d["doc_type"] in CONTROLLED and d["status"] not in ("rejected",
                                                                                                    "obsolete")]


def documents_current(facts: dict, settings: dict) -> dict:
    live = _controlled(facts)
    if not live:
        return result(UNKNOWN, "No procedures, work instructions or forms in the library yet.")
    ids = {d["id"] for d in live}
    bad = [i for i in facts["document_issues"] if i["kind"] in CLASHES and ids & set(i["docs"])]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'problem')} with revisions, numbers or copies.",
                      [{"kind": "document", "id": i["docs"][0], "label": i["title"], "why": i["detail"]} for i in bad])
    return result(MET, f"{_plural(len(live), 'controlled document')} checked: one current revision each, no clashing "
                       "numbers or copies.")


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

def ncr_contained(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    limit = int(settings["ncr_contain_days"])
    seen, late = 0, []
    for n in own:
        if n["status"] == "open":
            seen += 1
            age = (facts["today"] - n["opened"]).days
            if age > limit:
                late.append(ref("ncr", n, f"open for {age} days without containment"))
        elif n.get("contained_on"):
            seen += 1
            took = (n["contained_on"] - n["opened"]).days
            if took > limit:
                late.append(ref("ncr", n, f"contained after {took} days"))
    if not seen:
        return result(UNKNOWN, f"No nonconformance reports of the last {settings['window_days']} days to judge."
                      + _history(history))
    if late:
        return result(NOT_MET, f"{_plural(len(late), 'report')} not contained within {limit} days.", late)
    return result(MET, f"{_plural(seen, 'report')}: each contained within {limit} days, or still within them."
                  + _history(history))


def ncr_concession_approved(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    conc = [n for n in own if n.get("disposition") in facts["approval_dispositions"]
            and n["status"] in ("dispositioned", "closed")]
    if not conc:
        return result(UNKNOWN, f"No dispositions needing approval in the last {settings['window_days']} days."
                      + _history(history))
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
    own, history = judged(facts["ncrs"], facts)
    closed = [n for n in own if n["status"] == "closed"]
    if not closed:
        return result(UNKNOWN, f"No reports closed in WenQuest Ops in the last {settings['window_days']} days."
                      + _history(history))
    bad = []
    for n in closed:
        gaps = [w for w, ok in (("description", n.get("description")), ("disposition", n.get("disposition")),
                                ("reason for the disposition", n.get("disposition_reason")),
                                ("who decided the disposition", n.get("disposition_by")),
                                ("who closed it", n.get("closed_by"))) if not (ok or "").strip()]
        if n.get("closed_by") and n["closed_by"] not in facts["signatures"].get(("ncr", n["id"]), set()):
            gaps.append("the closing signature")
        if gaps:
            bad.append(ref("ncr", n, "missing: " + ", ".join(gaps)))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'closed report')} with something missing.", bad)
    return result(MET, f"{_plural(len(closed), 'closed report')}, each with description, disposition, reason, who "
                       "decided and the closing signature." + _history(history),
                  evidence=[ref("ncr", n) for n in closed])


def rejected_lots_have_ncr(facts: dict, settings: dict) -> dict:
    lots = facts["incoming_inspections"]
    if not lots:
        return result(UNKNOWN, f"No incoming inspections in the last {settings['window_days']} days.")
    rejected = [q for q in lots if q["rejected"]]
    missing = [{"kind": "inspection", "id": q["key"], "label": q["key"],
                "why": " ".join(x for x in ("rejected", q.get("item_code"), "without a nonconformance report") if x)}
               for q in rejected if q["key"] not in facts["ncr_inspections"]]
    if missing:
        return result(NOT_MET, f"{_plural(len(missing), 'rejected lot')} without a nonconformance report.", missing)
    return result(MET, f"{_plural(len(lots), 'incoming inspection')}, {len(rejected)} rejected; every rejected lot has "
                       "a nonconformance report.")


# ---------------------------------------------------------------- corrective actions

def capa_for_major(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    within = int(settings["capa_within_days"])
    major = [n for n in own if n["severity"] == "major"]
    if not major:
        return result(UNKNOWN, f"No major nonconformance reports of the last {settings['window_days']} days."
                      + _history(history))
    bad = [ref("ncr", n, "major, no corrective action") for n in major
           if n["id"] not in facts["ncr_capas"] and (facts["today"] - n["opened"]).days > within]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'major report')} without a corrective action after {within} "
                               "days.", bad)
    return result(MET, f"{_plural(len(major), 'major report')}: each has a corrective action (or was opened in the "
                       f"last {within} days)." + _history(history), evidence=[ref("ncr", n) for n in major])


def capa_on_time(facts: dict, settings: dict) -> dict:
    own, _ = judged(facts["capas"], facts)
    ids = {c["id"]: c for c in own}
    grace = int(settings["capa_overdue_days"])
    seen, late = 0, []
    for a in facts["capa_actions"]:
        due, c = a.get("due"), ids.get(a["capa_id"])
        if c is None or due is None or (a["done"] and a.get("done_on") is None):
            continue                                # nothing to judge it by
        seen += 1
        if (a["done"] and (a["done_on"] - due).days > grace) or (not a["done"] and (facts["today"] - due).days > grace):
            late.append({"kind": "capa", "id": c["id"], "label": c["name"],
                         "why": f"{a['text'][:80]}: due {due}" + (f", done {a['done_on']}" if a["done"] else
                                                                ", not done")})
    if not seen:
        return result(UNKNOWN, "No actions with due dates to judge.")
    if late:
        return result(NOT_MET, f"{_plural(len(late), 'action')} late.", late)
    return result(MET, f"{_plural(seen, 'action')} with due dates: none late.")


def capa_effective(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["capas"], facts)
    closed = [c for c in own if c["status"] == "closed"]
    if not closed:
        return result(UNKNOWN, f"No corrective actions closed in WenQuest Ops in the last {settings['window_days']} "
                               "days." + _history(history, "action"))
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
                       "someone other than the owner." + _history(history, "action"),
                  evidence=[ref("capa", c) for c in closed])


# ---------------------------------------------------------------- what people declare and link

def _usable(d: dict) -> bool:
    """A linked document counts while it is in effect: approved, for the kinds the library approves; confirmed and
    not obsolete, for the others (a policy or an organization chart kept as a record)."""
    return d["status"] == "effective" or (d["status"] == "confirmed" and d.get("doc_type") not in CONTROLLED)


def linked_document(facts: dict, settings: dict, control: str) -> dict:
    docs = facts["evidence"].get(control, [])
    if not docs:
        return result(UNKNOWN, "No document linked as evidence yet.")
    live = [d for d in docs if _usable(d)]
    gone = [ref("document", d, f"linked but {d['status'].replace('_', ' ')}") for d in docs if not _usable(d)]
    if not live:
        return result(NOT_MET, "The linked documents are not in effect.", gone)
    return result(MET, "Evidence: " + ", ".join(d["name"] for d in live) + ".", gone,
                  [ref("document", d) for d in live])


def scope_declared(facts: dict, settings: dict, control: str = "scope") -> dict:
    """The scope: a scope statement linked as evidence, and every control point that may be excluded declared."""
    names = facts["excludable"]
    open_ = [names[c] for c in names if c not in facts["applicability"]]
    excluded = {c: a for c, a in facts["applicability"].items() if not a["applies"] and c in names}
    doc = linked_document(facts, settings, control)
    if doc["status"] == NOT_MET:
        return doc
    if doc["status"] == UNKNOWN or open_:
        need = (["link the scope statement"] if doc["status"] == UNKNOWN else []) + \
               ([f"say whether these apply: {', '.join(open_)}"] if open_ else [])
        return result(UNKNOWN, "To do: " + "; ".join(need) + ".", evidence=doc["evidence"])
    why = "Every requirement applies." if not excluded else \
        "Excluded, with reasons: " + "; ".join(f"{names[c]} ({a['reason']})" for c, a in excluded.items()) + "."
    return result(MET, doc["detail"] + " " + why, evidence=doc["evidence"])


def register(facts: dict, settings: dict, name: str) -> dict:
    return result(UNKNOWN, f"Evidence comes from the {name.replace('_', ' ')} register, which is not there yet "
                           "(next step).")


CHECKS = {f.__name__: f for f in (documents_approved, documents_current, documents_referenced, ncr_contained,
                                  ncr_concession_approved, ncr_recorded, rejected_lots_have_ncr, capa_for_major,
                                  capa_on_time, capa_effective, scope_declared)}
LINKED = ("linked_document", "scope_declared")          # rules that take documents linked as evidence


def defaults(pack: dict) -> dict:
    return {k: v["value"] for k, v in (pack.get("settings") or {}).items()}


def evaluate(pack: dict, edition: str, facts: dict, settings: dict | None = None) -> dict:
    """Every control point of the pack: {control: result with process, summary, clauses}. ``settings``: the
    company's values over the pack's defaults."""
    settings = {**defaults(pack), **(settings or {})}
    out = {}
    for pname, proc in pack["processes"].items():
        for c in proc["controls"]:
            rule = c["rule"]
            if c.get("switch") and not settings.get(c["switch"]):
                rule = "linked_document"            # our rule switched off: the company shows it its own way
            decl = facts["applicability"].get(c["id"])
            if c.get("may_exclude") and decl and not decl["applies"]:
                r = result(NA, f"Does not apply: {decl['reason']} (declared by {decl['email']})")
            elif rule in ("linked_document", "scope_declared"):
                r = (linked_document if rule == "linked_document" else scope_declared)(facts, settings, c["id"])
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


def check_pack(pack: dict) -> list[str]:  # noqa: PLR0912 - one line per kind of mistake
    """What is wrong with a pack file: unknown rules, duplicate control points, settings the checks need."""
    errs, seen = [], set()
    sets = pack.get("settings") or {}
    for need in ("window_days", "ncr_contain_days", "capa_within_days", "capa_overdue_days"):
        if not isinstance(sets.get(need), dict) or type(sets[need].get("value")) is not int:
            errs.append(f"setting {need} is a whole number")
    for k, v in sets.items():
        if not isinstance(v, dict) or not str(v.get("label") or "").strip() or type(v.get("value")) not in (int, bool):
            errs.append(f"setting {k}: a value (a whole number or yes/no) and a label")
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
            if c.get("switch") and type((sets.get(c["switch"]) or {}).get("value")) is not bool:
                errs.append(f"{c.get('id')}: its switch {c['switch']!r} is a yes/no setting")
            if (c.get("rule") in LINKED or c.get("switch")) and not str(c.get("hint") or "").strip():
                errs.append(f"{c.get('id')}: a hint of what document shows it")
            if not str(c.get("summary") or "").strip():
                errs.append(f"{c.get('id')}: a summary")
    return errs
