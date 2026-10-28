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

The explanations are written in the reader's language when the check runs (ADR-0023); they are kept with the check.
"""

from __future__ import annotations

import datetime as dt
import re

from wqops import i18n as I18N
from wqops.hub.quality import approval as AP
from wqops.i18n import say

MET, NOT_MET, UNKNOWN, NA = "met", "not_met", "unknown", "not_applicable"
SHOW = 25                                       # records listed per answer; the count says how many there are


def result(status: str, detail: str, problems: list[dict] | None = None, evidence: list[dict] | None = None) -> dict:
    problems, evidence = problems or [], evidence or []
    return {"status": status, "detail": detail, "problems": problems[:SHOW], "problem_count": len(problems),
            "evidence": evidence[:SHOW], "evidence_count": len(evidence)}


def ref(kind: str, row: dict, why: str = "") -> dict:
    return {"kind": kind, "id": row["id"], "label": row.get("name") or row.get("label") or str(row["id"]), "why": why}


def _zh() -> bool:
    return I18N.current() == "zh"


def _pick(n: int, one: str, many: str) -> str:
    """The singular or the plural sentence (each a whole text in the catalog)."""
    return one if n == 1 else many


def _list(items) -> str:
    return ("、" if _zh() else ", ").join(str(x) for x in items)


def _semi(items) -> str:
    return ("；" if _zh() else "; ").join(items)


def _sp() -> str:
    """The space before a following sentence: none between Chinese sentences."""
    return "" if _zh() else " "


def _cat(a: str, b: str) -> str:
    return a + _sp() + b


def _end(s: str) -> str:
    return s + ("。" if _zh() else ".")


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
    if not rows:
        return ""
    n = len(rows)
    if what == "action":
        t = _pick(n, say("{n} imported action counted as history, not judged.", n=n),
                  say("{n} imported actions counted as history, not judged.", n=n))
    else:
        t = _pick(n, say("{n} imported report counted as history, not judged.", n=n),
                  say("{n} imported reports counted as history, not judged.", n=n))
    return _sp() + t


# ---------------------------------------------------------------- documents

CONTROLLED = ("procedure", "work_instruction", "form")


def documents_approved(facts: dict, settings: dict) -> dict:
    docs = [d for d in facts["documents"] if d["doc_type"] in CONTROLLED and d["status"] not in ("rejected",
                                                                                                    "obsolete")]
    if not docs:
        return result(UNKNOWN, say("No procedures, work instructions or forms in the document library yet."))
    effective = [d for d in docs if d["status"] == "effective"]
    waiting = [d for d in docs if d["status"] != "effective"]
    unsigned = [ref("document", d, say("in effect without a recorded approval")) for d in effective
                if d["id"] not in facts["document_approvals"]]
    if unsigned:
        n = len(unsigned)
        return result(NOT_MET, _pick(n, say("{n} document in effect without a recorded approval.", n=n),
                                     say("{n} documents in effect without a recorded approval.", n=n)), unsigned)
    if not effective:
        n = len(docs)
        return result(NOT_MET, _pick(n, say("None of the {n} controlled document has been approved yet.", n=n),
                                     say("None of the {n} controlled documents has been approved yet.", n=n)),
                      [ref("document", d, say("not approved yet")) for d in waiting])
    w = len(waiting)
    note = _sp() + _pick(w, say("{n} other not approved yet, so not in use.", n=w),
                         say("{n} others not approved yet, so not in use.", n=w)) if waiting else ""
    n = len(effective)
    return result(MET, _pick(n, say("{n} document in effect, each approved with a signature.", n=n),
                             say("{n} documents in effect, each approved with a signature.", n=n)) + note,
                  evidence=[ref("document", d) for d in effective])


CLASHES = ("number_conflict", "same_revision", "revisions", "duplicate")


def _controlled(facts: dict) -> list[dict]:
    return [d for d in facts["documents"] if d["doc_type"] in CONTROLLED and d["status"] not in ("rejected",
                                                                                                    "obsolete")]


def documents_current(facts: dict, settings: dict) -> dict:
    live = _controlled(facts)
    if not live:
        return result(UNKNOWN, say("No procedures, work instructions or forms in the library yet."))
    ids = {d["id"] for d in live}
    bad = [i for i in facts["document_issues"] if i["kind"] in CLASHES and ids & set(i["docs"])]
    late = [d for d in facts.get("doc_reviews_overdue") or [] if d["id"] in ids]    # periodic review (17d)
    if bad or late:
        b, n = len(bad), len(late)
        what = [_pick(b, say("{n} problem with revisions, numbers or copies", n=b),
                      say("{n} problems with revisions, numbers or copies", n=b))] if bad else []
        what += [_pick(n, say("{n} periodic review overdue", n=n), say("{n} periodic reviews overdue", n=n))] \
            if late else []
        return result(NOT_MET, _end(_semi(what).capitalize()),
                      [{"kind": "document", "id": i["docs"][0], "label": i["title"], "why": i["detail"]} for i in bad]
                      + [{"kind": "document", "id": d["id"], "label": d["number"] or d["title"],
                          "why": say("periodic review due {date}", date=d["due"])} for d in late])
    n = len(live)
    return result(MET, _pick(
        n, say("{n} controlled document checked: one current revision each, no clashing numbers or copies.", n=n),
        say("{n} controlled documents checked: one current revision each, no clashing numbers or copies.", n=n)))


def documents_referenced(facts: dict, settings: dict) -> dict:
    procs = [d for d in facts["documents"] if d["doc_type"] in ("procedure", "work_instruction")
             and d["status"] not in ("rejected", "obsolete")]
    if not procs:
        return result(UNKNOWN, say("No procedures or work instructions in the library yet."))
    bad = [i for i in facts["document_issues"] if i["kind"] == "missing_ref"]
    if bad:
        n = len(bad)
        return result(NOT_MET, _pick(n, say("{n} procedure name documents that are not in the library.", n=n),
                                     say("{n} procedures name documents that are not in the library.", n=n)),
                      [{"kind": "document", "id": i["docs"][0], "label": i["title"], "why": i["detail"]} for i in bad])
    n = len(procs)
    return result(MET, _pick(n, say("Every form and record the {n} procedure name is in the library.", n=n),
                             say("Every form and record the {n} procedures name is in the library.", n=n)))


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
                late.append(ref("ncr", n, say("open for {n} days without containment", n=age)))
        elif n.get("contained_on"):
            seen += 1
            took = (n["contained_on"] - n["opened"]).days
            if took > limit:
                late.append(ref("ncr", n, say("contained after {n} days", n=took)))
    if not seen:
        return result(UNKNOWN, say("No nonconformance reports of the last {days} days to judge.",
                                   days=settings["window_days"]) + _history(history))
    if late:
        k = len(late)
        return result(NOT_MET, _pick(k, say("{n} report not contained within {days} days.", n=k, days=limit),
                                     say("{n} reports not contained within {days} days.", n=k, days=limit)), late)
    return result(MET, _pick(seen, say("{n} report: each contained within {days} days, or still within them.",
                                       n=seen, days=limit),
                             say("{n} reports: each contained within {days} days, or still within them.",
                                 n=seen, days=limit)) + _history(history))


def ncr_concession_approved(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    conc = [n for n in own if n.get("disposition") in facts["approval_dispositions"]
            and n["status"] in ("dispositioned", "closed")]
    if not conc:
        return result(UNKNOWN, say("No dispositions needing approval in the last {days} days.",
                                   days=settings["window_days"]) + _history(history))
    bad = []
    for n in conc:
        signed = facts["signatures"].get(("ncr", n["id"]), set())
        if not n.get("approved_by"):
            bad.append(ref("ncr", n, say("no approval recorded")))
        elif n["approved_by"] == n.get("disposition_by"):
            bad.append(ref("ncr", n, say("approved by the person who proposed it")))
        elif n["approved_by"] not in signed:
            bad.append(ref("ncr", n, say("the approval has no signature")))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} concession without a proper approval.", n=k),
                                     say("{n} concessions without a proper approval.", n=k)), bad)
    k = len(conc)
    return result(MET, _pick(k, say("{n} disposition needing approval, each signed by someone else.", n=k),
                             say("{n} dispositions needing approval, each signed by someone else.", n=k)),
                  evidence=[ref("ncr", n) for n in conc])


def ncr_recorded(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    closed = [n for n in own if n["status"] == "closed"]
    if not closed:
        return result(UNKNOWN, say("No reports closed in WenQuest Ops in the last {days} days.",
                                   days=settings["window_days"]) + _history(history))
    bad = []
    for n in closed:
        gaps = [w for w, ok in ((say("description"), n.get("description")),
                                (say("disposition"), n.get("disposition")),
                                (say("reason for the disposition"), n.get("disposition_reason")),
                                (say("who decided the disposition"), n.get("disposition_by")),
                                (say("who closed it"), n.get("closed_by"))) if not (ok or "").strip()]
        if n.get("closed_by") and n["closed_by"] not in facts["signatures"].get(("ncr", n["id"]), set()):
            gaps.append(say("the closing signature"))
        if gaps:
            bad.append(ref("ncr", n, say("missing: {list}", list=_list(gaps))))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} closed report with something missing.", n=k),
                                     say("{n} closed reports with something missing.", n=k)), bad)
    k = len(closed)
    return result(MET, _pick(k, say("{n} closed report, each with description, disposition, reason, who decided and "
                                    "the closing signature.", n=k),
                             say("{n} closed reports, each with description, disposition, reason, who decided and "
                                 "the closing signature.", n=k)) + _history(history),
                  evidence=[ref("ncr", n) for n in closed])


def rejected_lots_have_ncr(facts: dict, settings: dict) -> dict:
    lots = facts["incoming_inspections"]
    if not lots:
        return result(UNKNOWN, say("No incoming inspections in the last {days} days.", days=settings["window_days"]))
    rejected = [q for q in lots if q["rejected"]]
    missing = [{"kind": "inspection", "id": q["key"], "label": q["key"],
                "why": say("rejected {item} without a nonconformance report", item=q["item_code"])
                if q.get("item_code") else say("rejected without a nonconformance report")}
               for q in rejected if q["key"] not in facts["ncr_inspections"]]
    if missing:
        k = len(missing)
        return result(NOT_MET, _pick(k, say("{n} rejected lot without a nonconformance report.", n=k),
                                     say("{n} rejected lots without a nonconformance report.", n=k)), missing)
    k, r = len(lots), len(rejected)
    return result(MET, _pick(k, say("{n} incoming inspection, {rejected} rejected; every rejected lot has a "
                                    "nonconformance report.", n=k, rejected=r),
                             say("{n} incoming inspections, {rejected} rejected; every rejected lot has a "
                                 "nonconformance report.", n=k, rejected=r)))


# ---------------------------------------------------------------- corrective actions

def capa_for_major(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["ncrs"], facts)
    within = int(settings["capa_within_days"])
    major = [n for n in own if n["severity"] == "major"]
    if not major:
        return result(UNKNOWN, say("No major nonconformance reports of the last {days} days.",
                                   days=settings["window_days"]) + _history(history))
    bad = [ref("ncr", n, say("major, no corrective action")) for n in major
           if n["id"] not in facts["ncr_capas"] and (facts["today"] - n["opened"]).days > within]
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} major report without a corrective action after {days} days.",
                                            n=k, days=within),
                                     say("{n} major reports without a corrective action after {days} days.",
                                         n=k, days=within)), bad)
    k = len(major)
    return result(MET, _pick(k, say("{n} major report: each has a corrective action (or was opened in the last "
                                    "{days} days).", n=k, days=within),
                             say("{n} major reports: each has a corrective action (or was opened in the last "
                                 "{days} days).", n=k, days=within)) + _history(history),
                  evidence=[ref("ncr", n) for n in major])


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
                         "why": say("{text}: due {due}, done {done}", text=a["text"][:80], due=due, done=a["done_on"])
                         if a["done"] else say("{text}: due {due}, not done", text=a["text"][:80], due=due)})
    if not seen:
        return result(UNKNOWN, say("No actions with due dates to judge."))
    if late:
        k = len(late)
        return result(NOT_MET, _pick(k, say("{n} action late.", n=k), say("{n} actions late.", n=k)), late)
    return result(MET, _pick(seen, say("{n} action with due dates: none late.", n=seen),
                             say("{n} actions with due dates: none late.", n=seen)))


def capa_effective(facts: dict, settings: dict) -> dict:
    own, history = judged(facts["capas"], facts)
    closed = [c for c in own if c["status"] == "closed"]
    if not closed:
        return result(UNKNOWN, say("No corrective actions closed in WenQuest Ops in the last {days} days.",
                                   days=settings["window_days"]) + _history(history, "action"))
    bad = []
    for c in closed:
        gaps = []
        if c.get("verification_result") != "effective":
            gaps.append(say("an effective conclusion"))
        if not (c.get("verification_method") or "").strip():
            gaps.append(say("the evidence of effectiveness"))
        if not c.get("closed_by") or c["closed_by"] not in facts["signatures"].get(("capa", c["id"]), set()):
            gaps.append(say("the closing signature"))
        elif c["closed_by"] == c.get("owner"):
            gaps.append(say("someone other than the owner to close it"))
        if gaps:
            bad.append(ref("capa", c, say("missing: {list}", list=_list(gaps))))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} closed action without a recorded effectiveness review.", n=k),
                                     say("{n} closed actions without a recorded effectiveness review.", n=k)), bad)
    k = len(closed)
    return result(MET, _pick(k, say("{n} closed action, each with its effectiveness evidence, signed by someone other "
                                    "than the owner.", n=k),
                             say("{n} closed actions, each with its effectiveness evidence, signed by someone other "
                                 "than the owner.", n=k)) + _history(history, "action"),
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
    best: dict[tuple, tuple] = {}
    for n, e in enumerate(rows):          # rows come oldest first; on the same day the later one counts
        k = tuple(str(e["values"].get(f, "")).strip().lower() for f in key)
        d = _d(e["values"].get(when)) or dt.date.min
        if k not in best or (d, n) >= best[k][0]:
            best[k] = ((d, n), e)
    return [e for _, e in best.values()]


def _entry(e: dict, label: str, why: str = "") -> dict:
    return {"kind": "entry", "id": e["id"], "label": label, "why": why}


def _empty(name: str) -> dict:
    text = {"training": lambda: say("Nothing in the training register yet."),
            "calibration": lambda: say("Nothing in the calibration register yet."),
            "audits": lambda: say("Nothing in the audits register yet."),
            "management_reviews": lambda: say("Nothing in the management reviews register yet."),
            "objectives": lambda: say("Nothing in the objectives register yet."),
            "risks": lambda: say("Nothing in the risks register yet."),
            "suppliers": lambda: say("Nothing in the suppliers register yet.")}.get(name)
    return result(UNKNOWN, text() if text else say("Nothing in the {register} register yet.",
                                                    register=name.replace("_", " ")))


def training_current(facts: dict, settings: dict) -> dict:
    """The training register, and (17d) the reading of controlled documents: nothing expired or left to follow up,
    and no reading of a revision in effect overdue."""
    rows = _entries(facts, "training")
    reading = facts.get("doc_training") or []
    if not rows and not reading:
        return _empty("training")
    follow = int(settings["training_followup_days"])
    bad, latest = [], _latest(rows, ["person", "topic"], "trained_on")
    for e in latest:
        v, label = e["values"], f"{e['values'].get('person')}: {e['values'].get('topic')}"
        until, on = _d(v.get("valid_until")), _d(v.get("trained_on"))
        if until and until < facts["today"]:
            bad.append(_entry(e, label, say("expired on {date}", date=until)))
        elif v.get("result") == "needs follow-up" and on and (facts["today"] - on).days > follow:
            bad.append(_entry(e, label, say("needs follow-up since {date}", date=on)))
    for r in reading:
        due = _d(r.get("due"))
        if r["status"] == "pending" and due and due < facts["today"]:
            rev = say("rev {revision}", revision=r.get("revision"))
            doc = " ".join(str(x) for x in (r.get("number"), r.get("title"), rev) if x)
            bad.append({"kind": "reading", "id": r["id"], "label": f"{r['email']}: {doc}",
                        "why": say("reading was due on {date}", date=due)})
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} training record out of date.", n=k),
                                     say("{n} training records out of date.", n=k)), bad)
    done = [r for r in reading if r["status"] == "acknowledged"]
    d = len(done)
    if not latest:          # reading alone does not show people are competent: the register is still empty
        return result(UNKNOWN, _pick(d, say("Nothing in the training register yet; {n} reading of controlled documents "
                                            "confirmed, none overdue.", n=d),
                                     say("Nothing in the training register yet; {n} readings of controlled "
                                         "documents confirmed, none overdue.", n=d)))
    k = len(latest)
    parts = [_pick(k, say("{n} person and skill with current training records", n=k),
                   say("{n} person and skills with current training records", n=k))] + (
        [_pick(d, say("{n} reading of controlled documents confirmed, none overdue", n=d),
               say("{n} readings of controlled documents confirmed, none overdue", n=d))] if reading else [])
    return result(MET, _end(_semi(parts)),
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
            bad.append(_entry(e, v.get("equipment"), say("failed its last calibration")))
        elif due < facts["today"]:
            bad.append(_entry(e, v.get("equipment"), say("calibration was due on {date}", date=due)))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} piece of equipment not fit for use.", n=k),
                                     say("{n} pieces of equipment not fit for use.", n=k)), bad)
    k = len(latest)
    return result(MET, _pick(k, say("{n} piece of equipment, each calibrated and not due.", n=k),
                             say("{n} pieces of equipment, each calibrated and not due.", n=k)),
                  evidence=[_entry(e, e["values"].get("equipment")) for e in latest])


# the texts of the registers done at set intervals, each a whole sentence
DONE_TEXTS = {
    "audits": {"unapproved": lambda: say("The internal audit recorded are not approved yet."),
               "item": lambda i: say("internal audit #{id}", id=i),
               "last": lambda d, n: say("The last internal audit was on {date}; one is due every {days} days.",
                                        date=d, days=n),
               "of": lambda d: say("internal audit of {date}", date=d)},
    "management_reviews": {
        "unapproved": lambda: say("The management review recorded are not approved yet."),
        "item": lambda i: say("management review #{id}", id=i),
        "last": lambda d, n: say("The last management review was on {date}; one is due every {days} days.",
                                 date=d, days=n),
        "of": lambda d: say("management review of {date}", date=d)},
}


def _done_within(facts: dict, name: str, when: str, days: int) -> tuple[dict | None, list[dict]]:
    rows = _entries(facts, name)
    if not rows:
        return _empty(name), []
    t = DONE_TEXTS[name]
    ok = _entries(facts, name, signed_only=True)
    if not ok:
        return result(NOT_MET, t["unapproved"](), [_entry(e, t["item"](e["id"]), say("not approved"))
                                                    for e in rows]), []
    last = max(ok, key=lambda e: _d(e["values"].get(when)) or dt.date.min)
    d = _d(last["values"].get(when))
    if d is None or (facts["today"] - d).days > days:
        return result(NOT_MET, t["last"](d, days), [_entry(last, t["of"](d), say("overdue"))]), ok
    return None, ok


def audits_done(facts: dict, settings: dict) -> dict:
    days = int(settings["audit_interval_days"])
    out, ok = _done_within(facts, "audits", "audit_date", days)
    if out:
        return out
    open_ = [_entry(e, say("audit of {area} on {date}", area=e["values"].get("area"),
                           date=e["values"].get("audit_date")), say("findings not followed up")) for e in ok
             if _num(e["values"].get("nonconformities")) > 0 and e["values"].get("followed_up") is not True]
    if open_:
        k = len(open_)
        return result(NOT_MET, _pick(k, say("{n} audit with findings not followed up.", n=k),
                                     say("{n} audits with findings not followed up.", n=k)), open_)
    return result(MET, say("Internal audits within every {days} days; findings followed up.", days=days),
                  evidence=[_entry(e, say("audit of {area} on {date}", area=e["values"].get("area"),
                                          date=e["values"].get("audit_date"))) for e in ok])


def reviews_done(facts: dict, settings: dict) -> dict:
    days = int(settings["review_interval_days"])
    out, ok = _done_within(facts, "management_reviews", "review_date", days)
    return out or result(MET, say("Management reviews within every {days} days, approved.", days=days),
                         evidence=[_entry(e, say("review of {date}", date=e["values"].get("review_date")))
                                   for e in ok])


def _reviewed(facts: dict, name: str, key: str, days: int, extra=None) -> dict:
    rows = _entries(facts, name)
    if not rows:
        return _empty(name)
    bad, latest = [], _latest(rows, [key], "reviewed_on")
    for e in latest:
        d = _d(e["values"].get("reviewed_on"))
        if d is None or (facts["today"] - d).days > days:
            bad.append(_entry(e, e["values"].get(key), say("last reviewed {date}; due every {days} days", date=d,
                                                           days=days)))
        elif extra and extra(e):
            bad.append(_entry(e, e["values"].get(key), extra(e)))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} entry not reviewed in time or incomplete.", n=k),
                                     say("{n} entries not reviewed in time or incomplete.", n=k)), bad)
    k = len(latest)
    return result(MET, _pick(k, say("{n} entry, each reviewed within {days} days.", n=k, days=days),
                             say("{n} entries, each reviewed within {days} days.", n=k, days=days)),
                  evidence=[_entry(e, e["values"].get(key)) for e in latest])


def objectives_reviewed(facts: dict, settings: dict) -> dict:
    return _reviewed(facts, "objectives", "objective", int(settings["objectives_review_days"]))


def risks_reviewed(facts: dict, settings: dict) -> dict:
    def no_action(e):
        return say("no action planned") if e["values"].get("kind") == "risk" and not e["values"].get("action") \
            else None
    return _reviewed(facts, "risks", "title", int(settings["risks_review_days"]), no_action)


def complaints_answered(facts: dict, settings: dict) -> dict:
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") == "complaint"
            and (_d(e["values"].get("received_on")) or facts["today"]) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, say("No complaints recorded in the last {days} days.", days=settings["window_days"]))
    days = int(settings["complaint_days"])
    bad = []
    for e in rows:
        v = e["values"]
        got, ans = _d(v.get("received_on")), _d(v.get("answered_on"))
        label = f"{v.get('customer')}, {got}"
        if ans and v.get("response"):
            if got and (ans - got).days > days:
                bad.append(_entry(e, label, say("answered after {n} days", n=(ans - got).days)))
        elif got and (facts["today"] - got).days > days:
            bad.append(_entry(e, label, say("not answered after {n} days", n=(facts["today"] - got).days)))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} complaint not answered within {days} days.", n=k, days=days),
                                     say("{n} complaints not answered within {days} days.", n=k, days=days)), bad)
    k = len(rows)
    return result(MET, _pick(k, say("{n} complaint, each answered within {days} days (or still within them).",
                                    n=k, days=days),
                             say("{n} complaints, each answered within {days} days (or still within them).",
                                 n=k, days=days)),
                  evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                            for e in rows])


def _reporting(v: dict, late: bool, age: int) -> tuple[list[str], str]:
    """What is wrong with one complaint's investigation and reporting decision, and its state: decided, or waiting
    while still within the days."""
    why = []
    if _d(v.get("answered_on")) and not str(v.get("investigation") or "").strip():
        why.append(say("closed without an investigation or the reason none was needed"))
    rep = v.get("reportable")
    if type(rep) is not bool:
        return why + ([say("whether to report it is not decided after {n} days", n=age)] if late else []), "waiting"
    if not str(v.get("reportable_reason") or "").strip():
        return [*why, say("the reporting decision has no reason")], "decided"
    if rep and not _d(v.get("reported_on")):
        return why + ([say("to be reported, but no report date recorded")] if late else []), "waiting"
    return why, "decided"


def complaints_assessed(facts: dict, settings: dict) -> dict:
    """ISO 13485: each complaint investigated (or why not recorded) before it is closed, and whether it must be
    reported to a regulator decided with a reason, and the report made, within the company's set days. The decision
    itself is a person's; the check only reads that it was made and recorded."""
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") == "complaint"
            and (_d(e["values"].get("received_on")) or facts["today"]) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, say("No complaints recorded in the last {days} days.", days=settings["window_days"]))
    days = int(settings["reportability_days"])
    bad, waiting, decided = [], 0, []
    for e in rows:
        v = e["values"]
        got = _d(v.get("received_on"))
        if got is None:
            bad.append(_entry(e, f"{v.get('customer')}", say("no date received, so the days cannot be counted")))
            continue
        age = (facts["today"] - got).days
        why, state = _reporting(v, age > days, age)
        bad += [_entry(e, f"{v.get('customer')}, {got}", w) for w in why]
        if not why and state == "waiting":
            waiting += 1
        elif not why:
            decided.append(e)
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} problem with investigating or deciding on reporting complaints.", n=k),
                                     say("{n} problems with investigating or deciding on reporting complaints.",
                                         n=k)), bad)
    more = _sp() + say("{n} more still within the {days} days to decide or report.", n=waiting, days=days) \
        if waiting else ""
    if not decided:              # nothing decided yet: nothing to judge, so not met either
        return result(UNKNOWN, _pick(waiting, say("{n} complaint still within the {days} days to decide on reporting; "
                                                  "none decided yet.", n=waiting, days=days),
                                     say("{n} complaints still within the {days} days to decide on reporting; "
                                         "none decided yet.", n=waiting, days=days)))
    k = len(decided)
    return result(MET, _pick(k, say("{n} complaint decided on reporting with reasons, and reported where needed.", n=k),
                             say("{n} complaints decided on reporting with reasons, and reported where needed.",
                                 n=k)) + more,
                  evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                            for e in decided])


def feedback_collected(facts: dict, settings: dict) -> dict:
    rows = [e for e in _entries(facts, "complaints") if e["values"].get("kind") in ("feedback", "survey")
            and (_d(e["values"].get("received_on")) or dt.date.min) >= facts["since"]]
    if not rows:
        return result(UNKNOWN, say("No customer feedback or surveys recorded in the last {days} days.",
                                   days=settings["window_days"]))
    k = len(rows)
    return result(MET, _pick(k, say("{n} piece of customer feedback in the last {days} days.", n=k,
                                    days=settings["window_days"]),
                             say("{n} pieces of customer feedback in the last {days} days.", n=k,
                                 days=settings["window_days"])),
                  evidence=[_entry(e, f"{e['values'].get('customer')}, {e['values'].get('received_on')}")
                            for e in rows])


def _name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _asl_label(e: dict) -> str:
    return f"{e['supplier']}, {e.get('item_code') or say('all items')}"


def _asl_approved(facts: dict, settings: dict) -> dict:
    """The approved supplier list (17c), once it has entries: every item bought in the window is from a supplier
    approved for it (the same judgement as incoming inspection), and no approval is past its re-evaluation date."""
    asl = facts["asl"]
    used = facts.get("suppliers_used") or {}
    items = facts.get("supplier_items_used") or {}
    ok = ("approved", "conditional")
    bad = []
    for key, name in sorted(used.items()):
        for item in sorted(items.get(key) or [None], key=lambda x: x or ""):
            s = AP.standing(asl, key, item, facts["today"])
            if s["outcome"] == "block":
                bad.append({"kind": "supplier", "id": key, "label": name,
                            "why": say("bought from but {why}", why=s["why"])})
                break
    for e in asl:
        due = _d(e.get("review_due"))
        if e["status"] in ok and due and due < facts["today"]:
            bad.append({"kind": "asl", "id": e["id"], "label": _asl_label(e),
                        "why": say("re-evaluation was due on {date}", date=due)})
    approved = [e for e in asl if e["status"] in ok]
    evidence = [{"kind": "asl", "id": e["id"], "label": _asl_label(e), "why": ""} for e in approved]
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} supplier not approved or not re-evaluated in time (approved supplier "
                                            "list).", n=k),
                                     say("{n} suppliers not approved or not re-evaluated in time (approved supplier "
                                         "list).", n=k)), bad)
    if not used:
        return result(UNKNOWN, say("No purchases in the last {days} days to check the approved supplier list against.",
                                   days=settings["window_days"]), evidence=evidence)
    k = len(approved)
    return result(MET, _pick(k, say("{n} entry on the approved supplier list; every item bought in the last {days} "
                                    "days is from a supplier approved for it.", n=k, days=settings["window_days"]),
                             say("{n} entries on the approved supplier list; every item bought in the last {days} "
                                 "days is from a supplier approved for it.", n=k, days=settings["window_days"])),
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
            bad.append({"kind": "supplier", "id": key, "label": name, "why": say("bought from without an approval")})
        elif e["values"].get("status") == "removed":
            bad.append(_entry(e, name, say("bought from but removed from the approved list")))
    for e in latest.values():
        nxt = _d(e["values"].get("next_review"))
        if e["values"].get("status") != "removed" and nxt and nxt < facts["today"]:
            bad.append(_entry(e, e["values"].get("supplier"), say("re-evaluation was due on {date}", date=nxt)))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} supplier not approved or not re-evaluated in time.", n=k),
                                     say("{n} suppliers not approved or not re-evaluated in time.", n=k)), bad)
    if not used:
        return result(UNKNOWN, say("No purchases in the last {days} days to check the list against.",
                                   days=settings["window_days"]),
                      evidence=[_entry(e, e["values"].get("supplier")) for e in latest.values()])
    k = len(latest)
    return result(MET, _pick(k, say("{n} supplier on the list; every supplier bought from in the last {days} days is "
                                    "approved.", n=k, days=settings["window_days"]),
                             say("{n} suppliers on the list; every supplier bought from in the last {days} days is "
                                 "approved.", n=k, days=settings["window_days"])),
                  evidence=[_entry(e, e["values"].get("supplier")) for e in latest.values()])


# ---------------------------------------------------------------- what people declare and link

def _usable(d: dict) -> bool:
    """A linked document counts while it is in effect: approved, for the kinds the library approves; confirmed and
    not obsolete, for the others (a policy or an organization chart kept as a record)."""
    return d["status"] == "effective" or (d["status"] == "confirmed" and d.get("doc_type") not in CONTROLLED)


def _doc_status(s: str) -> str:
    """A document's status as a word (the status itself stays the stored code)."""
    words = {"draft": lambda: say("docstatus::draft"), "in_review": lambda: say("docstatus::in review"),
             "approved": lambda: say("docstatus::approved"), "rejected": lambda: say("docstatus::rejected"),
             "obsolete": lambda: say("docstatus::obsolete"), "to_review": lambda: say("docstatus::to review"),
             "to_classify": lambda: say("docstatus::to classify"), "confirmed": lambda: say("docstatus::confirmed"),
             "effective": lambda: say("docstatus::effective")}
    w = words.get(s)
    return w() if w else str(s).replace("_", " ")


def linked_document(facts: dict, settings: dict, control: str) -> dict:
    docs = facts["evidence"].get(control, [])
    if not docs:
        return result(UNKNOWN, say("No document linked as evidence yet."))
    live = [d for d in docs if _usable(d)]
    gone = [ref("document", d, say("linked but {status}", status=_doc_status(d["status"]))) for d in docs
            if not _usable(d)]
    if not live:
        return result(NOT_MET, say("The linked documents are not in effect."), gone)
    return result(MET, say("Evidence: {list}.", list=_list(d["name"] for d in live)), gone,
                  [ref("document", d) for d in live])


def scope_declared(facts: dict, settings: dict, control: str = "scope") -> dict:
    """The scope: a scope statement linked as evidence, and every control point that may be excluded declared."""
    names = {c: I18N.label(x) for c, x in facts["excludable"].items()}
    open_ = [names[c] for c in names if c not in facts["applicability"]]
    excluded = {c: a for c, a in facts["applicability"].items() if not a["applies"] and c in names}
    doc = linked_document(facts, settings, control)
    if doc["status"] == NOT_MET:
        return doc
    if doc["status"] == UNKNOWN or open_:
        need = ([say("link the scope statement")] if doc["status"] == UNKNOWN else []) + \
               ([say("say whether these apply: {list}", list=_list(open_))] if open_ else [])
        return result(UNKNOWN, say("To do: {items}.", items=_semi(need)), evidence=doc["evidence"])
    why = say("Every requirement applies.") if not excluded else \
        say("Excluded, with reasons: {list}.", list=_semi(say("{name} ({reason})", name=names[c], reason=a["reason"])
                                                          for c, a in excluded.items()))
    return result(MET, _cat(doc["detail"], why), evidence=doc["evidence"])


# ---------------------------------------------------------------- records of the regulated modules (17k)
# These read the module's own records. A company that does not use the module yet shows the control point with the
# documents it links, as before: no records falls back to the linked documents.

def _or_linked(facts: dict, settings: dict, control: str, none: str) -> dict:
    r = linked_document(facts, settings, control)
    return result(UNKNOWN, _cat(none, r["detail"])) if r["status"] == UNKNOWN else r


def _decided(facts: dict, status: str) -> list[dict]:
    return [p for p in facts.get("production") or [] if p["status"] == status and p["decided_on"]
            and p["decided_on"] >= facts["since"]]


def risk_managed(facts: dict, settings: dict, control: str = "risk_management") -> dict:
    """Approved risk files (17h) that still match their fingerprint; drafts are named, not judged."""
    files = facts.get("risk_files") or []
    approved = [f for f in files if f["status"] == "approved"]
    if not approved:
        return _or_linked(facts, settings, control, say("No approved risk file under Risk yet."))
    broken = [ref("risk_file", f, say("changed since it was approved")) for f in approved if f["intact"] is False]
    if broken:
        k = len(broken)
        return result(NOT_MET, _pick(k, say("{n} approved risk file no longer match what was approved.", n=k),
                                     say("{n} approved risk files no longer match what was approved.", n=k)), broken)
    drafts = [f for f in files if f["status"] == "draft"]
    k, d = len(approved), len(drafts)
    return result(MET, _pick(k, say("{n} approved risk file, each as approved.", n=k),
                             say("{n} approved risk files, each as approved.", n=k))
                  + (_sp() + _pick(d, say("{n} draft not approved yet.", n=d), say("{n} drafts not approved yet.", n=d))
                     if drafts else ""),
                  evidence=[ref("risk_file", f, f["product"]) for f in approved])


def _lot_state(p: dict) -> str:
    if p["status"] == "released":
        return say("lot {lot}, released", lot=p["lot_no"])
    if p["status"] == "rejected":
        return say("lot {lot}, rejected", lot=p["lot_no"])
    return f"lot {p['lot_no']}, {p['status']}"


def production_recorded(facts: dict, settings: dict, control: str = "production") -> dict:
    """Lots decided in the period (17i): each with its record, released by someone who did not make it."""
    lots = _decided(facts, "released") + _decided(facts, "rejected")
    if not lots:
        return _or_linked(facts, settings, control, say("No production lot released or rejected in the period."))
    bad = [ref("production", p, say("decided by someone who recorded it")) for p in lots
           if p["decided_by"] in (p["involved"] or [])]
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} lot decided by someone who made it.", n=k),
                                     say("{n} lots decided by someone who made it.", n=k)), bad)
    rel = [p for p in lots if p["status"] == "released"]
    k = len(lots)
    return result(MET, _pick(k, say("{n} lot with a production record in the period, {released} released.", n=k,
                                    released=len(rel)),
                             say("{n} lots with a production record in the period, {released} released.", n=k,
                                 released=len(rel))),
                  evidence=[ref("production", p, _lot_state(p)) for p in lots])


def lots_traceable(facts: dict, settings: dict, control: str = "traceability") -> dict:
    """Each lot released in the period has a lot number and the incoming lots of every material it must use."""
    rel = _decided(facts, "released")
    if not rel:
        return _or_linked(facts, settings, control, say("No production lot released in the period."))
    bad = []
    for p in rel:
        missing = sorted(set(p["materials_needed"]) - set(p["materials_used"]))
        if missing:
            bad.append(ref("production", p, say("no incoming lot recorded for {list}", list=_list(missing))))
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} released lot cannot be traced to every material.", n=k),
                                     say("{n} released lots cannot be traced to every material.", n=k)), bad)
    k = len(rel)
    return result(MET, _pick(k, say("{n} released lot, each traced to the incoming lots of its materials.", n=k),
                             say("{n} released lots, each traced to the incoming lots of its materials.", n=k)),
                  evidence=[ref("production", p, say("lot {lot}", lot=p["lot_no"])) for p in rel])


def release_signed(facts: dict, settings: dict, control: str = "product_release") -> dict:
    """Production lots and incoming lots released in the period: by a named person, not the one who checked."""
    lots = _decided(facts, "released")
    incoming = [i for i in facts.get("iqc_decided") or [] if i["decided_on"] and i["decided_on"] >= facts["since"]]
    if not lots and not incoming:
        return _or_linked(facts, settings, control, say("No lot released in the period."))
    bad = [ref("production", p, say("released by someone who made it")) for p in lots
           if not p["decided_by"] or p["decided_by"] in (p["involved"] or [])]
    bad += [ref("iqc", i, say("decided by the inspector who signed it")) for i in incoming
            if not i["decided_by"] or i["decided_by"] == i["signed_by"]]
    if bad:
        k = len(bad)
        return result(NOT_MET, _pick(k, say("{n} release not made by a second person.", n=k),
                                     say("{n} releases not made by a second person.", n=k)), bad)
    k = len(lots) + len(incoming)

    def by(i: dict) -> str:
        if i["status"] == "released":
            return say("released by {who}", who=i["decided_by"])
        if i["status"] == "rejected":
            return say("rejected by {who}", who=i["decided_by"])
        return f"{i['status']} by {i['decided_by']}"

    return result(MET, _pick(k, say("{n} release in the period, each signed by a named person who did not do the "
                                    "checks.", n=k),
                             say("{n} releases in the period, each signed by a named person who did not do the "
                                 "checks.", n=k)),
                  evidence=[ref("production", p, say("released by {who}", who=p["decided_by"])) for p in lots]
                  + [ref("iqc", i, by(i)) for i in incoming])


def register(facts: dict, settings: dict, name: str) -> dict:
    return result(UNKNOWN, say("Evidence comes from the {register} register, which is not there yet (next step).",
                               register=name.replace("_", " ")))


CHECKS = {f.__name__: f for f in (documents_approved, documents_current, documents_referenced, ncr_contained,
                                  ncr_concession_approved, ncr_recorded, rejected_lots_have_ncr, capa_for_major,
                                  capa_on_time, capa_effective, scope_declared, training_current, calibration_current,
                                  audits_done, reviews_done, objectives_reviewed, risks_reviewed, complaints_answered,
                                  complaints_assessed, feedback_collected, suppliers_approved, risk_managed,
                                  production_recorded, lots_traceable, release_signed)}
# rules that read the module's records and fall back to the documents linked to the control point
WITH_DOCUMENTS = ("risk_managed", "production_recorded", "lots_traceable", "release_signed")
LINKED = ("linked_document", "scope_declared", *WITH_DOCUMENTS)   # rules that take documents linked as evidence
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
                r = result(NA, say("Does not apply: {reason} (declared by {email})", reason=decl["reason"],
                                   email=decl["email"]))
            elif rule in ("linked_document", "scope_declared"):
                r = (linked_document if rule == "linked_document" else scope_declared)(facts, settings, c["id"])
            elif rule.startswith("register:"):
                r = register(facts, settings, rule.split(":", 1)[1])
            else:
                try:
                    args = (c["id"],) if rule in WITH_DOCUMENTS else ()
                    r = CHECKS[rule](facts, settings, *args)
                except (TypeError, ValueError, KeyError, AttributeError) as exc:     # odd data: say so, go on
                    r = result(UNKNOWN, say("Could not be checked: a value is not as expected ({error}).",
                                               error=type(exc).__name__))
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
