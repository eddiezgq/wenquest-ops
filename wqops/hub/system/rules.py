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

import datetime as dt
import re

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


# ---------------------------------------------------------------- registers (16b)

def _d(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


WHEN = {"training": "trained_on", "calibration": "calibrated_on", "audits": "audit_date",
        "management_reviews": "review_date", "objectives": "reviewed_on", "risks": "reviewed_on",
        "complaints": "received_on", "suppliers": "approved_on"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _entries(facts: dict, name: str, signed_only: bool = False) -> list[dict]:
    """Entries of a register (approved ones only, if asked). An entry dated after today is a plan, not a record:
    it is left out."""
    rows = (facts.get("registers") or {}).get(name, [])
    when = WHEN.get(name)
    return [e for e in rows if (not signed_only or e["signed"])
            and not (when and (_d(e["values"].get(when)) or dt.date.min) > facts["today"])]


def _latest(rows: list[dict], key: list[str], when: str) -> list[dict]:
    """The latest entry about each thing (by the register's key and its date field)."""
    best: dict[tuple, dict] = {}
    for e in rows:
        k = tuple(str(e["values"].get(f, "")).strip().lower() for f in key)
        d = _d(e["values"].get(when)) or dt.date.min
        if k not in best or (d, e["id"]) >= (_d(best[k]["values"].get(when)) or dt.date.min, best[k]["id"]):
            best[k] = e
    return list(best.values())


def _entry(e: dict, label: str, why: str = "") -> dict:
    return {"kind": "entry", "id": e["id"], "label": label, "why": why}


def _empty(name: str) -> dict:
    return result(UNKNOWN, f"Nothing in the {name.replace('_', ' ')} register yet.")


def training_current(facts: dict, settings: dict) -> dict:
    rows = _entries(facts, "training")
    if not rows:
        return _empty("training")
    follow = int(settings["training_followup_days"])
    bad, latest = [], _latest(rows, ["person", "topic"], "trained_on")
    for e in latest:
        v, label = e["values"], f"{e['values'].get('person')}: {e['values'].get('topic')}"
        until, on = _d(v.get("valid_until")), _d(v.get("trained_on"))
        if until and until < facts["today"]:
            bad.append(_entry(e, label, f"expired on {until}"))
        elif v.get("result") == "needs follow-up" and on and (facts["today"] - on).days > follow:
            bad.append(_entry(e, label, f"needs follow-up since {on}"))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'training record')} out of date.", bad)
    return result(MET, f"{_plural(len(latest), 'person and skill')} with current training records.",
                  evidence=[_entry(e, f"{e['values'].get('person')}: {e['values'].get('topic')}") for e in latest])


def calibration_current(facts: dict, settings: dict) -> dict:
    rows = _entries(facts, "calibration")
    if not rows:
        return _empty("calibration")
    every = int(settings["calibration_interval_days"])
    bad, latest = [], _latest(rows, ["equipment"], "calibrated_on")
    for e in latest:
        v = e["values"]
        due = _d(v.get("next_due")) or ((_d(v.get("calibrated_on")) or facts["today"]) + dt.timedelta(days=every))
        if v.get("result") == "fail":
            bad.append(_entry(e, v.get("equipment"), "failed its last calibration"))
        elif due < facts["today"]:
            bad.append(_entry(e, v.get("equipment"), f"calibration was due on {due}"))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'piece')} of equipment not fit for use.", bad)
    return result(MET, f"{_plural(len(latest), 'piece')} of equipment, each calibrated and not due.",
                  evidence=[_entry(e, e["values"].get("equipment")) for e in latest])


def _done_within(facts: dict, name: str, when: str, days: int, what: str) -> tuple[dict | None, list[dict]]:
    rows = _entries(facts, name)
    if not rows:
        return _empty(name), []
    ok = _entries(facts, name, signed_only=True)
    if not ok:
        return result(NOT_MET, f"The {what} recorded are not approved yet.",
                      [_entry(e, f"{what} #{e['id']}", "not approved") for e in rows]), []
    last = max(ok, key=lambda e: _d(e["values"].get(when)) or dt.date.min)
    d = _d(last["values"].get(when))
    if d is None or (facts["today"] - d).days > days:
        return result(NOT_MET, f"The last {what} was on {d}; one is due every {days} days.",
                      [_entry(last, f"{what} of {d}", "overdue")]), ok
    return None, ok


def audits_done(facts: dict, settings: dict) -> dict:
    days = int(settings["audit_interval_days"])
    out, ok = _done_within(facts, "audits", "audit_date", days, "internal audit")
    if out:
        return out
    open_ = [_entry(e, f"audit of {e['values'].get('area')} on {e['values'].get('audit_date')}",
                    "findings not followed up") for e in ok
             if _num(e["values"].get("nonconformities")) > 0 and e["values"].get("followed_up") is not True]
    if open_:
        return result(NOT_MET, f"{_plural(len(open_), 'audit')} with findings not followed up.", open_)
    return result(MET, f"Internal audits within every {days} days; findings followed up.",
                  evidence=[_entry(e, f"audit of {e['values'].get('area')} on {e['values'].get('audit_date')}")
                            for e in ok])


def reviews_done(facts: dict, settings: dict) -> dict:
    days = int(settings["review_interval_days"])
    out, ok = _done_within(facts, "management_reviews", "review_date", days, "management review")
    return out or result(MET, f"Management reviews within every {days} days, approved.",
                         evidence=[_entry(e, f"review of {e['values'].get('review_date')}") for e in ok])


def _reviewed(facts: dict, name: str, key: str, days: int, extra=None) -> dict:
    rows = _entries(facts, name)
    if not rows:
        return _empty(name)
    bad, latest = [], _latest(rows, [key], "reviewed_on")
    for e in latest:
        d = _d(e["values"].get("reviewed_on"))
        if d is None or (facts["today"] - d).days > days:
            bad.append(_entry(e, e["values"].get(key), f"last reviewed {d}; due every {days} days"))
        elif extra and extra(e):
            bad.append(_entry(e, e["values"].get(key), extra(e)))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'entry')} not reviewed in time or incomplete.".replace(
            "entrys", "entries"), bad)
    return result(MET, f"{_plural(len(latest), 'entry').replace('entrys', 'entries')}, each reviewed within "
                       f"{days} days.", evidence=[_entry(e, e["values"].get(key)) for e in latest])


def objectives_reviewed(facts: dict, settings: dict) -> dict:
    return _reviewed(facts, "objectives", "objective", int(settings["objectives_review_days"]))


def risks_reviewed(facts: dict, settings: dict) -> dict:
    def no_action(e):
        return "no action planned" if e["values"].get("kind") == "risk" and not e["values"].get("action") else None
    return _reviewed(facts, "risks", "title", int(settings["risks_review_days"]), no_action)


def complaints_answered(facts: dict, settings: dict) -> dict:
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") == "complaint"
            and (_d(e["values"].get("received_on")) or facts["today"]) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, f"No complaints recorded in the last {settings['window_days']} days.")
    days = int(settings["complaint_days"])
    bad = []
    for e in rows:
        v = e["values"]
        got, ans = _d(v.get("received_on")), _d(v.get("answered_on"))
        label = f"{v.get('customer')}, {got}"
        if ans and v.get("response"):
            if got and (ans - got).days > days:
                bad.append(_entry(e, label, f"answered after {(ans - got).days} days"))
        elif got and (facts["today"] - got).days > days:
            bad.append(_entry(e, label, f"not answered after {(facts['today'] - got).days} days"))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'complaint')} not answered within {days} days.", bad)
    return result(MET, f"{_plural(len(rows), 'complaint')}, each answered within {days} days (or still within them).",
                  evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                            for e in rows])


def _reporting(v: dict, late: bool, age: int) -> tuple[list[str], str]:
    """What is wrong with one complaint's investigation and reporting decision, and its state: decided, or waiting
    while still within the days."""
    why = []
    if _d(v.get("answered_on")) and not str(v.get("investigation") or "").strip():
        why.append("closed without an investigation or the reason none was needed")
    rep = v.get("reportable")
    if type(rep) is not bool:
        return why + ([f"whether to report it is not decided after {age} days"] if late else []), "waiting"
    if not str(v.get("reportable_reason") or "").strip():
        return [*why, "the reporting decision has no reason"], "decided"
    if rep and not _d(v.get("reported_on")):
        return why + (["to be reported, but no report date recorded"] if late else []), "waiting"
    return why, "decided"


def complaints_assessed(facts: dict, settings: dict) -> dict:
    """ISO 13485: each complaint investigated (or why not recorded) before it is closed, and whether it must be
    reported to a regulator decided with a reason, and the report made, within the company's set days. The decision
    itself is a person's; the check only reads that it was made and recorded."""
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") == "complaint"
            and (_d(e["values"].get("received_on")) or facts["today"]) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, f"No complaints recorded in the last {settings['window_days']} days.")
    days = int(settings["reportability_days"])
    bad, waiting, decided = [], 0, []
    for e in rows:
        v = e["values"]
        got = _d(v.get("received_on"))
        if got is None:
            bad.append(_entry(e, f"{v.get('customer')}", "no date received, so the days cannot be counted"))
            continue
        age = (facts["today"] - got).days
        why, state = _reporting(v, age > days, age)
        bad += [_entry(e, f"{v.get('customer')}, {got}", w) for w in why]
        if not why and state == "waiting":
            waiting += 1
        elif not why:
            decided.append(e)
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'problem')} with investigating or deciding on reporting "
                               "complaints.", bad)
    more = f" {waiting} more still within the {days} days to decide or report." if waiting else ""
    if not decided:              # nothing decided yet: nothing to judge, so not met either
        return result(UNKNOWN, f"{_plural(waiting, 'complaint')} still within the {days} days to decide on "
                               "reporting; none decided yet.")
    return result(MET, f"{_plural(len(decided), 'complaint')} decided on reporting with reasons, and reported where "
                       "needed." + more,
                  evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                            for e in decided])


def feedback_collected(facts: dict, settings: dict) -> dict:
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") in ("feedback", "survey")
            and (_d(e["values"].get("received_on")) or dt.date.min) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, f"No customer feedback or surveys recorded in the last {settings['window_days']} "
                               "days.")
    return result(MET, f"{_plural(len(rows), 'piece')} of customer feedback in the last {settings['window_days']} "
                       "days.", evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                                          for e in rows])


def _name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _asl_approved(facts: dict, settings: dict) -> dict:
    """The approved supplier list (17c), once it has entries: every supplier bought from in the window has an
    approved or conditional entry, and none of those is past its re-evaluation date."""
    asl = facts["asl"]
    used = facts.get("suppliers_used") or {}
    ok = ("approved", "conditional")
    bad = []
    for key, name in sorted(used.items()):
        mine = [e for e in asl if e["supplier"] == key]
        if not any(e["status"] in ok for e in mine):
            why = ("bought from but " + "/".join(sorted({e["status"] for e in mine})) + " on the approved supplier "
                   "list") if mine else "bought from but not on the approved supplier list"
            bad.append({"kind": "supplier", "id": key, "label": name, "why": why})
    for e in asl:
        due = _d(e.get("review_due"))
        if e["status"] in ok and due and due < facts["today"]:
            bad.append({"kind": "asl", "id": e["id"], "label": f"{e['supplier']}, {e.get('item_code') or 'all items'}",
                        "why": f"re-evaluation was due on {due}"})
    approved = [e for e in asl if e["status"] in ok]
    evidence = [{"kind": "asl", "id": e["id"], "label": f"{e['supplier']}, {e.get('item_code') or 'all items'}",
                 "why": ""} for e in approved]
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'supplier')} not approved or not re-evaluated in time "
                               "(approved supplier list).", bad)
    if not used:
        return result(UNKNOWN, f"No purchases in the last {settings['window_days']} days to check the approved "
                               "supplier list against.", evidence=evidence)
    return result(MET, f"{_plural(len(approved), 'entry').replace('entrys', 'entries')} on the approved supplier "
                       f"list; every supplier bought from in the last {settings['window_days']} days is approved.",
                  evidence=evidence)


def suppliers_approved(facts: dict, settings: dict) -> dict:
    if facts.get("asl"):
        return _asl_approved(facts, settings)
    rows = _entries(facts, "suppliers")
    used = facts.get("suppliers_used") or {}
    if not rows and not used:
        return _empty("suppliers")
    latest = {_name(e["values"].get("supplier")): e for e in _latest(rows, ["supplier"], "approved_on")}
    bad = []
    for key, name in sorted(used.items()):
        e = latest.get(_name(key)) or latest.get(_name(name))
        if e is None:
            bad.append({"kind": "supplier", "id": key, "label": name, "why": "bought from without an approval"})
        elif e["values"].get("status") == "removed":
            bad.append(_entry(e, name, "bought from but removed from the approved list"))
    for e in latest.values():
        nxt = _d(e["values"].get("next_review"))
        if e["values"].get("status") != "removed" and nxt and nxt < facts["today"]:
            bad.append(_entry(e, e["values"].get("supplier"), f"re-evaluation was due on {nxt}"))
    if bad:
        return result(NOT_MET, f"{_plural(len(bad), 'supplier')} not approved or not re-evaluated in time.", bad)
    if not used:
        return result(UNKNOWN, f"No purchases in the last {settings['window_days']} days to check the list against.",
                      evidence=[_entry(e, e["values"].get("supplier")) for e in latest.values()])
    return result(MET, f"{_plural(len(latest), 'supplier')} on the list; every supplier bought from in the last "
                       f"{settings['window_days']} days is approved.",
                  evidence=[_entry(e, e["values"].get("supplier")) for e in latest.values()])


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
                                  capa_on_time, capa_effective, scope_declared, training_current, calibration_current,
                                  audits_done, reviews_done, objectives_reviewed, risks_reviewed, complaints_answered,
                                  complaints_assessed, feedback_collected, suppliers_approved)}
LINKED = ("linked_document", "scope_declared")          # rules that take documents linked as evidence
# the settings each check reads besides window_days, so a pack that leaves one out is caught when it is checked
NEEDS = {"ncr_contained": ["ncr_contain_days"], "capa_for_major": ["capa_within_days"],
         "capa_on_time": ["capa_overdue_days"], "training_current": ["training_followup_days"],
         "calibration_current": ["calibration_interval_days"], "audits_done": ["audit_interval_days"],
         "reviews_done": ["review_interval_days"], "objectives_reviewed": ["objectives_review_days"],
         "risks_reviewed": ["risks_review_days"], "complaints_answered": ["complaint_days"],
         "complaints_assessed": ["reportability_days"]}


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
                try:
                    r = CHECKS[rule](facts, settings)
                except (TypeError, ValueError, KeyError, AttributeError) as exc:     # odd data: say so, go on
                    r = result(UNKNOWN, f"Could not be checked: a value is not as expected ({type(exc).__name__}).")
            out[c["id"]] = {**r, "process": pname, "summary": c["summary"], "clauses": (c.get("clauses") or {}).get(
                edition, []), "rule": rule}
    return out


def counts(results: dict) -> dict:
    out = {MET: 0, NOT_MET: 0, UNKNOWN: 0, NA: 0}
    for r in results.values():
        out[r["status"]] += 1
    return out


REGISTER_TYPES = ("text", "longtext", "number", "date", "choice", "yesno")


def check_registers(regs: dict) -> list[str]:
    errs = []
    for name, r in regs.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", str(name)) or not str((r or {}).get("label") or "").strip():
            errs.append(f"register {name}: a name of lower-case letters and a label")
        fields = (r or {}).get("fields") or {}
        if not fields:
            errs.append(f"register {name}: at least one field")
        for f, x in fields.items():
            if (x or {}).get("type") not in REGISTER_TYPES or not str((x or {}).get("label") or "").strip():
                errs.append(f"register {name}, field {f}: a label and a type ({', '.join(REGISTER_TYPES)})")
            elif x["type"] == "choice" and len(x.get("choices") or []) < 2:
                errs.append(f"register {name}, field {f}: at least two choices")
        for k in (r or {}).get("key") or []:
            if k not in fields:
                errs.append(f"register {name}: key {k} is not a field")
    return errs


def check_pack(pack: dict) -> list[str]:  # noqa: PLR0912 - one line per kind of mistake
    """What is wrong with a pack file: unknown rules, duplicate control points, settings the checks need."""
    errs, seen = check_registers(pack.get("registers") or {}), set()
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
            for need in NEEDS.get(rule, []):
                if type((sets.get(need) or {}).get("value")) is not int:
                    errs.append(f"{c.get('id')}: its rule needs the setting {need}")
            if c.get("register") and c["register"] not in (pack.get("registers") or {}):
                errs.append(f"{c.get('id')}: register {c['register']!r} is not defined")
            if c.get("switch") and type((sets.get(c["switch"]) or {}).get("value")) is not bool:
                errs.append(f"{c.get('id')}: its switch {c['switch']!r} is a yes/no setting")
            if (c.get("rule") in LINKED or c.get("switch")) and not str(c.get("hint") or "").strip():
                errs.append(f"{c.get('id')}: a hint of what document shows it")
            if not str(c.get("summary") or "").strip():
                errs.append(f"{c.get('id')}: a summary")
    excludable = {c["id"] for p in (pack.get("processes") or {}).values() for c in p.get("controls") or []
                  if c.get("may_exclude")}
    for k, q in (pack.get("questions") or {}).items():
        if not isinstance(q, dict) or q.get("type") not in ("text", "number", "yesno") or \
                not str(q.get("label") or "").strip() or set(q) - {"label", "type", "if_no"} or \
                not isinstance(q.get("if_no") or {}, dict):
            errs.append(f"question {k}: a label, a type (text, number, yesno) and what a no means (if_no)")
            continue
        for ctl, why in (q.get("if_no") or {}).items():
            if ctl not in excludable or not str(why or "").strip():
                errs.append(f"question {k}: {ctl} is not a control point that may be excluded, or has no reason")
    return errs
