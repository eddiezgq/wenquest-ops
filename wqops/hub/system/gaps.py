"""The gap report, to-dos and the internal audit checklist (ADR-0016, step 16c), all made from the latest check of the
control points. Nothing here judges: rules.py does; this module lists what the check found and what people plan
to do about it. Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R

SAMPLE = 5                                      # records shown per control point on the audit checklist


class TodoError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def todos(conn, standard: str, *, open_only: bool = False) -> list[dict]:
    rows = conn.execute("select * from qms_todos where standard = %s order by status <> 'open', due nulls last, id",
                        (standard,)).fetchall()
    return [_iso(r) for r in rows if not open_only or r["status"] == "open"]


def _log(conn, todo_id: int, email: str, action: str, note: str = "") -> None:
    conn.execute("insert into qms_todo_log (todo_id, email, action, note) values (%s, %s, %s, %s)",
                 (todo_id, email, action, note[:2000]))


def report(conn, standard: str) -> dict:
    """Every control point not met or unknown, by process, with its open to-do."""
    v = QMS.view(conn, standard)
    if not v["enabled"]:
        raise QMS.QmsError("adopt the standard first")
    open_ = {t["control"]: t for t in todos(conn, standard, open_only=True)}
    procs, n = [], {"not_met": 0, "unknown": 0, "with_todo": 0}
    for p in v["processes"]:
        rows = []
        for c in p["controls"]:
            r = c.get("result") or {}
            if r.get("status") not in (R.NOT_MET, R.UNKNOWN):
                continue
            n[r["status"]] += 1
            n["with_todo"] += c["id"] in open_
            rows.append({"id": c["id"], "summary": c["summary"], "clauses": c["clauses"], "status": r["status"],
                         "detail": r.get("detail"), "problems": r.get("problems", []),
                         "problem_count": r.get("problem_count", 0), "rule": r.get("rule") or c["rule"],
                         "register": c.get("register"), "hint": c.get("hint"), "todo": open_.get(c["id"])})
        if rows:
            rows.sort(key=lambda x: x["status"] != R.NOT_MET)
            procs.append({"id": p["id"], "label": p["label"], "gaps": rows})
    return {"edition_label": v["edition_label"], "evaluation": v["evaluation"], "counts": n, "processes": procs,
            "todos": todos(conn, standard)}


def _title(c: dict, r: dict) -> str:
    if r.get("status") == R.NOT_MET:
        return f"{c['summary']} Now: {r.get('detail', '')}"[:300]
    return f"Show: {c['summary']}"[:300]


def add(conn, email: str, standard: str, control: str, *, title: str = "", owner: str = "",
        due: dt.date | None = None) -> dict:
    v = QMS.view(conn, standard)
    if not v["enabled"]:
        raise QMS.QmsError("adopt the standard first")
    c = next((x for p in v["processes"] for x in p["controls"] if x["id"] == control), None)
    if c is None:
        raise KeyError(control)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-qms-todo:{standard}:{control}",))
        if conn.execute("select 1 from qms_todos where standard = %s and control = %s and status = 'open'",
                        (standard, control)).fetchone():
            raise TodoError("there is already an open to-do for this; change that one")
        row = conn.execute("insert into qms_todos (standard, control, title, owner, due, created_by) values "
                           "(%s, %s, %s, %s, %s, %s) returning *",
                           (standard, control, (title.strip() or _title(c, c.get("result") or {}))[:300],
                            owner.strip()[:200] or None, due, email)).fetchone()
        _log(conn, row["id"], email, "opened")
    return row


def add_all(conn, email: str, standard: str, due: dt.date | None = None) -> int:
    """A to-do for every gap that has none yet."""
    made = 0
    for p in report(conn, standard)["processes"]:
        for g in p["gaps"]:
            if not g["todo"]:
                add(conn, email, standard, g["id"], due=due)
                made += 1
    return made


def change(conn, email: str, todo_id: int, *, owner: str | None = None, due: dt.date | None = None,
           status: str | None = None, note: str = "", clear_due: bool = False) -> dict:
    with conn.transaction():
        row = conn.execute("select * from qms_todos where id = %s for update", (todo_id,)).fetchone()
        if row is None:
            raise KeyError(todo_id)
        if row["status"] != "open":
            raise TodoError(f"this to-do is {row['status']}")
        if status not in (None, "open", "done", "dropped"):
            raise TodoError("a to-do is open, done or dropped")
        if status == "dropped" and not note.strip():
            raise TodoError("say why it is dropped")
        closing = status in ("done", "dropped")
        out = conn.execute(
            "update qms_todos set owner = %s, due = %s, status = %s, note = %s, closed_by = %s, closed_at = %s "
            "where id = %s returning *",
            (row["owner"] if owner is None else (owner.strip()[:200] or None),
             None if clear_due else (due or row["due"]), status or "open",
             (note.strip() or row["note"])[:2000], email if closing else None,
             dt.datetime.now(dt.UTC) if closing else None, todo_id)).fetchone()
        what = []
        if out["owner"] != row["owner"]:
            what.append(f"owner {out['owner']}")
        if out["due"] != row["due"]:
            what.append(f"due {out['due']}")
        _log(conn, todo_id, email, status if closing else "changed", "; ".join(what + ([note] if note else [])))
    return out


def checklist(conn, standard: str, process: str = "") -> dict:
    """The internal audit checklist: for each control point of a process (or all), what to look for, what the
    records show and a sample of them."""
    v = QMS.view(conn, standard)
    if not v["enabled"]:
        raise QMS.QmsError("adopt the standard first")
    procs = [p for p in v["processes"] if not process or p["id"] == process]
    if process and not procs:
        raise KeyError(process)
    out = []
    for p in procs:
        items = []
        for c in p["controls"]:
            r = c.get("result") or {}
            items.append({"id": c["id"], "question": f"Can the company show that: {c['summary'][0].lower()}"
                                                     f"{c['summary'][1:]}", "clauses": c["clauses"],
                          "status": r.get("status"), "detail": r.get("detail"),
                          "sample": (r.get("evidence") or [])[:SAMPLE], "gaps": (r.get("problems") or [])[:SAMPLE],
                          "register": c.get("register")})
        out.append({"id": p["id"], "label": p["label"], "items": items})
    return {"edition_label": v["edition_label"], "evaluation": v["evaluation"],
            "processes_all": [{"id": p["id"], "label": p["label"]} for p in v["processes"]], "processes": out}
