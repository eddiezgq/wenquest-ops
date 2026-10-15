"""The company's quality system against a standard (ADR-0016, step 16a): enabling a process pack with a signature,
declaring what does not apply, linking documents as evidence, reading the facts the checks need and keeping every
evaluation of the control points.

Plain code: no AI, no network (tests/test_isolation.py). Nothing here changes a quality record; an evaluation only
reads them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from psycopg.types.json import Json, Jsonb

from wqops.hub.docs import library as LIB
from wqops.hub.ont import metrics as M
from wqops.hub.quality import records as Q
from wqops.hub.system import rules as R

PACKS = Path(__file__).resolve().parent / "packs"
STANDARDS = ("iso9001",)


class QmsError(ValueError):
    pass


def load(standard: str) -> dict:
    if standard not in STANDARDS:
        raise KeyError(standard)
    return yaml.safe_load((PACKS / f"{standard}.yaml").read_text(encoding="utf-8"))


def fingerprint(pack: dict) -> str:
    return hashlib.sha256(json.dumps(pack, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def controls(pack: dict) -> dict[str, dict]:
    return {c["id"]: c for p in pack["processes"].values() for c in p["controls"]}


def enabled(conn, standard: str) -> dict | None:
    return conn.execute("select * from qms_packs where standard = %s and status = 'enabled'", (standard,)).fetchone()


def enable(conn, user: dict, standard: str, edition: str, password: str, today: dt.date,  # noqa: PLR0917
           tz: str = "UTC") -> dict:
    """Use a standard's pack in its current version for one edition; signed. The pack as enabled is kept."""
    pack = load(standard)
    bad = R.check_pack(pack)
    if bad:
        raise QmsError("the pack is wrong: " + "; ".join(bad))
    ed = (pack.get("editions") or {}).get(edition)
    if not ed:
        raise QmsError(f"{pack['label']} has no edition {edition!r}")
    if not ed.get("ready"):
        raise QmsError(f"{ed['label']} is not ready yet: {ed.get('note', '')}".rstrip(": "))
    fp = fingerprint(pack)
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-qms:{standard}",))
        old = enabled(conn, standard)
        if old and old["fingerprint"] == fp and old["edition"] == edition:
            raise QmsError(f"{ed['label']} is already in use with this version of the pack")
        if old:
            conn.execute("update qms_packs set status = 'retired', retired_at = now() where id = %s", (old["id"],))
        row = conn.execute("insert into qms_packs (standard, edition, version, content, fingerprint, enabled_by) "
                           "values (%s, %s, %s, %s, %s, %s) returning *",
                           (standard, edition, pack["version"], Json(pack), fp, user["email"])).fetchone()
        Q._sign(conn, user, f"{ed['label']} adopted", "qms", row["id"], f"{pack['label']} v{pack['version']}")
    evaluate(conn, standard, today, "enabled", user["email"], tz=tz)
    return row


def applicability(conn, standard: str) -> dict[str, dict]:
    rows = conn.execute("select distinct on (control) control, applies, reason, email, at from qms_applicability "
                        "where standard = %s order by control, id desc", (standard,)).fetchall()
    return {r["control"]: dict(r, at=r["at"].isoformat()) for r in rows}


def declare(conn, user: dict, standard: str, control: str, applies: bool, reason: str, password: str,  # noqa: PLR0917
            today: dt.date, tz: str = "UTC") -> dict:
    """Say, with a signature and a reason, whether a control point that may be excluded applies."""
    row = enabled(conn, standard)
    if row is None:
        raise QmsError("adopt the standard first")
    c = controls(row["content"]).get(control)
    if c is None:
        raise KeyError(control)
    if not c.get("may_exclude"):
        raise QmsError("this requirement always applies")
    if not reason.strip():
        raise QmsError("give the reason")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        out = conn.execute("insert into qms_applicability (standard, control, applies, reason, email) values "
                           "(%s, %s, %s, %s, %s) returning *",
                           (standard, control, applies, reason.strip()[:1000], user["email"])).fetchone()
        Q._sign(conn, user, "Applies" if applies else "Does not apply", "qms_applicability", out["id"],
                f"{standard} {control}")
    evaluate(conn, standard, today, "changed", user["email"], tz=tz)
    return out


def evidence(conn, standard: str) -> dict[str, list[dict]]:
    rows = conn.execute(
        "select distinct on (e.control, e.document_id) e.control, e.document_id, e.linked, e.email, e.at, d.status, "
        "d.number, d.title, d.revision, d.original_name, d.doc_type from qms_evidence e join documents d on "
        "d.id = e.document_id where e.standard = %s order by e.control, e.document_id, e.id desc",
        (standard,)).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r["linked"]:
            name = " ".join(x for x in (r["number"], r["title"]) if x) or r["original_name"]
            out.setdefault(r["control"], []).append({"id": r["document_id"], "name": name, "status": r["status"],
                                                     "doc_type": r["doc_type"],
                                                     "revision": r["revision"], "email": r["email"],
                                                     "at": r["at"].isoformat()})
    return out


def link(conn, email: str, standard: str, control: str, document_id: int, linked: bool, today: dt.date,  # noqa: PLR0917
         note: str = "", tz: str = "UTC") -> dict:
    row = enabled(conn, standard)
    if row is None:
        raise QmsError("adopt the standard first")
    c = controls(row["content"]).get(control)
    if c is None:
        raise KeyError(control)
    if c["rule"] not in R.LINKED:
        raise QmsError("this requirement is judged from the records, not from a linked document")
    doc = LIB.get(conn, document_id)
    if linked and doc["status"] in ("rejected", "to_classify", "to_review"):
        raise QmsError("link a document that is confirmed in the library")
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-qms-evidence:{standard}:{control}",))
        current = {d["id"] for d in evidence(conn, standard).get(control, [])}
        if linked == (document_id in current):
            raise QmsError("it is already linked" if linked else "it is not linked")
        out = conn.execute("insert into qms_evidence (standard, control, document_id, linked, email, note) values "
                           "(%s, %s, %s, %s, %s, %s) returning *",
                           (standard, control, document_id, linked, email, note.strip()[:1000])).fetchone()
    evaluate(conn, standard, today, "changed", email, tz=tz)
    return out


# ---------------------------------------------------------------- facts and evaluations

def facts(conn, pack: dict, standard: str, today: dt.date, tz: str = "UTC") -> dict:
    """Everything the checks read, in one place, with times turned into the company's days."""
    zone = ZoneInfo(tz)

    def day(v):
        return v.astimezone(zone).date() if isinstance(v, dt.datetime) else v

    since = today - dt.timedelta(days=int(pack["settings"]["window_days"]))
    state = LIB.check(conn)
    sig: dict[tuple[str, int], set[str]] = {}
    for s in conn.execute("select kind, ref_id, email from signatures where kind in ('ncr', 'capa', 'document')"):
        sig.setdefault((s["kind"], s["ref_id"]), set()).add(s["email"])
    contained = {r["ref_id"]: r["at"] for r in conn.execute(
        "select ref_id, min(at) as at from quality_log where kind = 'ncr' and action = 'contained' group by ref_id")}
    ncrs = [dict(n, opened=day(n["created_at"]), closed_on=day(n["closed_at"]),
                 contained_on=day(contained.get(n["id"])), when=n["reported_on"] or day(n["created_at"]),
                 imported=n["source_doc"] is not None)
            for n in conn.execute("select id, name, status, severity, description, disposition, disposition_reason, "
                                  "disposition_by, approved_by, closed_by, closed_at, inspection, created_at, "
                                  "reported_on, source_doc from ncr_records order by id")]
    capas = [dict(c, opened=day(c["created_at"]), closed_on=day(c["closed_at"]),
                  when=c["reported_on"] or day(c["created_at"]), imported=c["source_doc"] is not None)
             for c in conn.execute("select id, name, status, owner, verification_result, verification_method, "
                                   "closed_by, closed_at, created_at, reported_on, source_doc from capas order by id")]
    linked = {r["ncr_id"] for r in conn.execute(
        "select l.ncr_id from capa_ncrs l join capas c on c.id = l.capa_id where c.status <> 'cancelled'")}
    lots = []
    for q in M._objs(conn, "QualityInspection"):
        p = q["props"]
        d = M._d(p.get("report_date"))
        if M._submitted(p) and p.get("inspection_type") == "Incoming" and d and since <= d <= today:
            lots.append({"key": q["key"], "item_code": p.get("item_code"), "rejected": p.get("status") == "Rejected"})
    return {
        "today": today, "since": since,
        "documents": [dict(d, name=LIB.name_of(d)) for d in state["docs"]], "document_issues": state["issues"],
        "document_approvals": {k[1] for k in sig if k[0] == "document"},
        "ncrs": ncrs, "capas": capas, "ncr_capas": linked,
        "capa_actions": [dict(a, done_on=day(a["done_at"])) for a in conn.execute(
            "select capa_id, text, due, done, done_at from capa_actions order by id")],
        "signatures": sig,
        "approval_dispositions": {k for k, t in Q.disposition_types(conn, active_only=False).items()
                                  if t["requires_approval"]},
        "incoming_inspections": lots,
        "ncr_inspections": {n["inspection"] for n in ncrs if n["inspection"] and n["status"] != "cancelled"},
        "applicability": applicability(conn, standard),
        "excludable": {c: x.get("short", c) for c, x in controls(pack).items() if x.get("may_exclude")},
        "evidence": evidence(conn, standard),
    }


def evaluate(conn, standard: str, today: dt.date, trigger: str, email: str | None = None, *,
             tz: str = "UTC") -> dict | None:
    """Judge every control point of the enabled pack now and keep the result."""
    row = enabled(conn, standard)
    if row is None:
        return None
    pack = row["content"]
    results = R.evaluate(pack, row["edition"], facts(conn, pack, standard, today, tz))
    return conn.execute("insert into qms_evaluations (pack_id, day, trigger, email, results, counts) values "
                        "(%s, %s, %s, %s, %s, %s) returning *",
                        (row["id"], today, trigger, email, Jsonb(results), Jsonb(R.counts(results)))).fetchone()


def evaluate_if_due(conn, today: dt.date, tz: str = "UTC") -> list[str]:
    """The daily evaluation of every standard in use, once per company day."""
    done = []
    for s in STANDARDS:
        row = enabled(conn, s)
        if row is None:
            continue
        last = conn.execute("select max(day) as d from qms_evaluations where pack_id = %s and trigger = 'daily'",
                            (row["id"],)).fetchone()["d"]
        if last is None or last < today:
            evaluate(conn, s, today, "daily", tz=tz)
            done.append(s)
    return done


def pick(conn, standard: str, eval_id: int | None = None, day: dt.date | None = None) -> dict | None:
    """An evaluation of this standard: the one asked for, the last one of a day, or the latest."""
    if eval_id:
        ev = conn.execute("select e.* from qms_evaluations e join qms_packs p on p.id = e.pack_id where e.id = %s and "
                          "p.standard = %s", (eval_id, standard)).fetchone()
    elif day:
        ev = conn.execute("select e.* from qms_evaluations e join qms_packs p on p.id = e.pack_id where e.day = %s "
                          "and p.standard = %s order by e.id desc limit 1", (day, standard)).fetchone()
    else:
        ev = conn.execute("select e.* from qms_evaluations e join qms_packs p on p.id = e.pack_id where "
                          "p.standard = %s and p.status = 'enabled' order by e.id desc limit 1", (standard,)).fetchone()
        return ev
    if ev is None:
        raise KeyError(eval_id or day)
    return ev


def latest(conn, standard: str) -> dict | None:
    return pick(conn, standard)


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def view(conn, standard: str, eval_id: int | None = None, day: dt.date | None = None) -> dict:
    """The page: the pack in use, an evaluation (latest unless one or a day is asked for) shown with the pack it was
    made under, declarations, linked documents, and the days that have checks."""
    pack_file = load(standard)
    row = enabled(conn, standard)
    out = {"standard": standard, "label": pack_file["label"],
           "editions": {k: {"label": v["label"], "ready": bool(v.get("ready")), "note": v.get("note", "")}
                        for k, v in pack_file["editions"].items()},
           "pack_version": pack_file["version"], "enabled": None}
    if row is None:
        return out
    ev = pick(conn, standard, eval_id, day)
    shown = row if ev is None or ev["pack_id"] == row["id"] else \
        conn.execute("select * from qms_packs where id = %s", (ev["pack_id"],)).fetchone()
    pack = shown["content"]
    results = ev["results"] if ev else {}
    procs = []
    for pname, p in pack["processes"].items():
        procs.append({"id": pname, "label": p["label"], "controls": [
            {**c, "clauses": (c.get("clauses") or {}).get(shown["edition"], []), "result": results.get(c["id"])}
            for c in p["controls"]]})
    days = conn.execute(
        "select distinct on (e.day) e.id, e.day, e.at, e.trigger, e.email, e.counts from qms_evaluations e join "
        "qms_packs p on p.id = e.pack_id where p.standard = %s order by e.day desc, e.id desc limit 400",
        (standard,)).fetchall()
    return {**out, "enabled": {k: v for k, v in _iso(row).items() if k != "content"},
            "edition_label": pack["editions"][shown["edition"]]["label"],
            "shown_pack": {"id": shown["id"], "version": shown["version"], "edition": shown["edition"]},
            "newer_pack": pack_file["version"] != row["content"]["version"]
            or fingerprint(pack_file) != row["fingerprint"],
            "settings": pack.get("settings") or {},
            "evaluation": {k: v for k, v in _iso(ev).items() if k != "results"} if ev else None,
            "processes": procs, "applicability": applicability(conn, standard), "evidence": evidence(conn, standard),
            "history": [_iso(h) for h in days]}
