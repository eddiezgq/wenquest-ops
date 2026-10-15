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


def enable(conn, user: dict, standard: str, edition: str, password: str, today: dt.date) -> dict:  # noqa: PLR0917
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
    evaluate(conn, standard, today, "enabled", user["email"])
    return row


def applicability(conn, standard: str) -> dict[str, dict]:
    rows = conn.execute("select distinct on (control) control, applies, reason, email, at from qms_applicability "
                        "where standard = %s order by control, id desc", (standard,)).fetchall()
    return {r["control"]: dict(r, at=r["at"].isoformat()) for r in rows}


def declare(conn, user: dict, standard: str, control: str, applies: bool, reason: str, password: str,  # noqa: PLR0917
            today: dt.date) -> dict:
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
    evaluate(conn, standard, today, "changed", user["email"])
    return out


def evidence(conn, standard: str) -> dict[str, list[dict]]:
    rows = conn.execute(
        "select distinct on (e.control, e.document_id) e.control, e.document_id, e.linked, e.email, e.at, d.status, "
        "d.number, d.title, d.revision, d.original_name from qms_evidence e join documents d on d.id = e.document_id "
        "where e.standard = %s order by e.control, e.document_id, e.id desc", (standard,)).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r["linked"]:
            name = " ".join(x for x in (r["number"], r["title"]) if x) or r["original_name"]
            out.setdefault(r["control"], []).append({"id": r["document_id"], "name": name, "status": r["status"],
                                                     "revision": r["revision"], "email": r["email"],
                                                     "at": r["at"].isoformat()})
    return out


def link(conn, email: str, standard: str, control: str, document_id: int, linked: bool, today: dt.date,  # noqa: PLR0917
         note: str = "") -> dict:
    row = enabled(conn, standard)
    if row is None:
        raise QmsError("adopt the standard first")
    c = controls(row["content"]).get(control)
    if c is None:
        raise KeyError(control)
    if c["rule"] != "linked_document":
        raise QmsError("this requirement is judged from the records, not from a linked document")
    doc = LIB.get(conn, document_id)
    if linked and doc["status"] in ("rejected", "to_classify", "to_review"):
        raise QmsError("link a document that is confirmed in the library")
    current = {d["id"] for d in evidence(conn, standard).get(control, [])}
    if linked == (document_id in current):
        raise QmsError("it is already linked" if linked else "it is not linked")
    out = conn.execute("insert into qms_evidence (standard, control, document_id, linked, email, note) values "
                       "(%s, %s, %s, %s, %s, %s) returning *",
                       (standard, control, document_id, linked, email, note.strip()[:1000])).fetchone()
    evaluate(conn, standard, today, "changed", email)
    return out


# ---------------------------------------------------------------- facts and evaluations

def facts(conn, pack: dict, standard: str, today: dt.date) -> dict:
    """Everything the checks read, in one place."""
    since = today - dt.timedelta(days=int(pack["settings"]["window_days"]))
    state = LIB.check(conn)
    sig: dict[tuple[str, int], set[str]] = {}
    for s in conn.execute("select kind, ref_id, email from signatures where kind in ('ncr', 'capa', 'document')"):
        sig.setdefault((s["kind"], s["ref_id"]), set()).add(s["email"])
    ncrs = conn.execute("select id, name, status, severity, description, disposition, disposition_reason, "
                        "disposition_by, approved_by, closed_by, inspection, created_at, reported_on, source_doc "
                        "from ncr_records order by id").fetchall()
    capas = conn.execute("select id, name, status, owner, verification_result, verification_method, closed_by, "
                         "closed_at, created_at, reported_on, source_doc from capas order by id").fetchall()
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
        "capa_actions": conn.execute("select capa_id, text, due, done, done_at from capa_actions").fetchall(),
        "signatures": sig,
        "approval_dispositions": {k for k, t in Q.disposition_types(conn, active_only=False).items()
                                  if t["requires_approval"]},
        "incoming_inspections": lots,
        "ncr_inspections": {n["inspection"] for n in ncrs if n["inspection"] and n["status"] != "cancelled"},
        "applicability": applicability(conn, standard),
        "excludable": {c: x.get("short", c) for c, x in controls(pack).items() if x.get("may_exclude")},
        "evidence": evidence(conn, standard),
    }


def evaluate(conn, standard: str, today: dt.date, trigger: str, email: str | None = None) -> dict | None:
    """Judge every control point of the enabled pack now and keep the result."""
    row = enabled(conn, standard)
    if row is None:
        return None
    pack = row["content"]
    results = R.evaluate(pack, row["edition"], facts(conn, pack, standard, today))
    return conn.execute("insert into qms_evaluations (pack_id, day, trigger, email, results, counts) values "
                        "(%s, %s, %s, %s, %s, %s) returning *",
                        (row["id"], today, trigger, email, Jsonb(results), Jsonb(R.counts(results)))).fetchone()


def evaluate_if_due(conn, today: dt.date) -> list[str]:
    """The daily evaluation of every standard in use, once per company day."""
    done = []
    for s in STANDARDS:
        row = enabled(conn, s)
        if row is None:
            continue
        last = conn.execute("select max(day) as d from qms_evaluations where pack_id = %s and trigger = 'daily'",
                            (row["id"],)).fetchone()["d"]
        if last is None or last < today:
            evaluate(conn, s, today, "daily")
            done.append(s)
    return done


def latest(conn, standard: str, eval_id: int | None = None) -> dict | None:
    row = enabled(conn, standard)
    if row is None:
        return None
    if eval_id:
        ev = conn.execute("select e.* from qms_evaluations e join qms_packs p on p.id = e.pack_id where e.id = %s and "
                          "p.standard = %s", (eval_id, standard)).fetchone()
        if ev is None:
            raise KeyError(eval_id)
        return ev
    return conn.execute("select * from qms_evaluations where pack_id = %s order by id desc limit 1",
                        (row["id"],)).fetchone()


def view(conn, standard: str, eval_id: int | None = None) -> dict:
    """The page: the pack in use, the evaluation (latest unless one is asked for) grouped by process, declarations,
    linked documents and earlier evaluations."""
    pack_file = load(standard)
    row = enabled(conn, standard)
    out = {"standard": standard, "label": pack_file["label"],
           "editions": {k: {"label": v["label"], "ready": bool(v.get("ready")), "note": v.get("note", "")}
                        for k, v in pack_file["editions"].items()},
           "pack_version": pack_file["version"], "enabled": None}
    if row is None:
        return out
    pack = row["content"]
    ev = latest(conn, standard, eval_id)
    results = ev["results"] if ev else {}
    procs = []
    for pname, p in pack["processes"].items():
        procs.append({"id": pname, "label": p["label"], "controls": [
            {**c, "clauses": (c.get("clauses") or {}).get(row["edition"], []), "result": results.get(c["id"])}
            for c in p["controls"]]})
    history = conn.execute("select id, day, at, trigger, email, counts from qms_evaluations where pack_id = %s "
                           "order by id desc limit 30", (row["id"],)).fetchall()
    return {**out, "enabled": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()
                               if k != "content"},
            "edition_label": pack["editions"][row["edition"]]["label"], "newer_pack": pack_file["version"] !=
            pack["version"] or fingerprint(pack_file) != row["fingerprint"],
            "settings": pack.get("settings") or {},
            "evaluation": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in ev.items()
                           if k != "results"} if ev else None,
            "processes": procs, "applicability": applicability(conn, standard), "evidence": evidence(conn, standard),
            "history": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in h.items()} for h in history]}
