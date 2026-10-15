"""The approved supplier list, step 17c (ADR-0017; dee-qms PLAN-ASL).

One entry per supplier and item, or per supplier for all its items. An entry is entered as a draft, approved (or
approved with conditions) with a signature by someone other than the person who entered it (a setting),
re-evaluated the same way, suspended or disqualified with a reason, and qualified again from the start. Approved
entries change only by re-evaluation or after suspending them. Incoming inspection reads the list
(wqops/hub/quality/approval.py); the supplier approval register of ISO 9001 can be brought in once, signed.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt
import re

from wqops.hub.quality import approval as AP
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q


class AslError(ValueError):
    pass


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, entry_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into asl_log (entry_id, email, action, note) values (%s, %s, %s, %s)",
                 (entry_id, email, action, (note or "")[:2000]))


def history(conn, entry_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select at, email, action, note from asl_log where entry_id = %s "
                                          "order by id", (entry_id,)).fetchall()]


def get(conn, entry_id: int) -> dict:
    row = conn.execute("select * from asl_entries where id = %s", (entry_id,)).fetchone()
    if row is None:
        raise KeyError(entry_id)
    return row


def _date(v, what: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise AslError(f"{what} is a date like 2027-03-31") from exc


def _fields(data: dict) -> dict:
    out = {}
    if "risk" in data:
        if data["risk"] not in AP.RISKS:
            raise AslError("the risk is low, medium or high")
        out["risk"] = data["risk"]
    for k in ("basis", "condition"):
        if k in data:
            out[k] = str(data[k] or "").strip()[:4000]
    if "review_due" in data:
        out["review_due"] = _date(data["review_due"], "the re-evaluation date")
    return out


def add(conn, email: str, supplier: str, item_code: str | None, data: dict) -> dict:
    """A draft entry for a supplier ERPNext knows, for one item or (no item) for all its items."""
    supplier = str(supplier or "").strip()
    if supplier not in {s["key"] for s in I.suppliers(conn)}:
        raise AslError("choose a supplier ERPNext knows")
    item_code = str(item_code or "").strip() or None
    if item_code and item_code not in {x["item_code"] for x in I.items(conn)}:
        raise AslError(f"ERPNext has no item {item_code}")
    f = _fields(data)
    with conn.transaction():
        if conn.execute("select 1 from asl_entries where supplier = %s and coalesce(item_code, '') = %s",
                        (supplier, item_code or "")).fetchone():
            raise AslError(f"{supplier} already has an entry for {item_code or 'all items'}")
        row = conn.execute("insert into asl_entries (supplier, item_code, risk, basis, condition, review_due, "
                           "created_by) values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (supplier, item_code, f.get("risk", "medium"), f.get("basis", ""), f.get("condition", ""),
                            f.get("review_due"), email)).fetchone()
        log(conn, row["id"], email, "entered", f"{supplier}, {item_code or 'all items'}")
    return row


def change(conn, email: str, entry_id: int, data: dict) -> dict:
    """Change a draft or a suspended entry."""
    e = get(conn, entry_id)
    if e["status"] not in ("draft", "suspended"):
        raise AslError(f"the entry is {e['status']}: re-evaluate it, or suspend it to change it")
    f = _fields(data)
    if not f:
        raise AslError("nothing to change")
    sets = ", ".join(f"{k} = %({k})s" for k in f)
    with conn.transaction():
        row = conn.execute(f"update asl_entries set {sets}, updated_at = now() where id = %(id)s "  # noqa: S608
                           "and status in ('draft', 'suspended') returning *", {**f, "id": entry_id}).fetchone()
        if row is None:
            raise AslError("the entry changed meanwhile: open it again")
        log(conn, entry_id, email, "changed", ", ".join(f))
    return row


def approve(conn, user: dict, entry_id: int, password: str, *, reason: str, today: dt.date,
            basis: str | None = None, review_due=None, condition: str | None = None) -> dict:
    """Approve (or, with a condition, approve with conditions) a draft or suspended entry, or re-evaluate an
    approved one: signed, with a reason, by someone other than the person who entered it (a setting)."""
    e = get(conn, entry_id)
    if e["status"] not in ("draft", "suspended", "approved", "conditional"):
        raise AslError(f"a {e['status']} entry is qualified again first")
    if not reason.strip():
        raise AslError("give the reason")
    renew = e["status"] in ("approved", "conditional")
    if I.settings(conn)["asl_approve_by_other"] and e["created_by"] == user["email"]:
        raise PermissionError("someone other than the person who entered the supplier approves it")
    b = (basis if basis is not None else e["basis"]).strip()
    if not b:
        raise AslError("say what the approval rests on (certificates, audit, sample inspection)")
    due = _date(review_due, "the re-evaluation date") if review_due not in (None, "") else (
        None if renew else e["review_due"])
    if renew and (due is None or due <= today):
        raise AslError("a re-evaluation sets the next re-evaluation date, after today")
    if due is not None and due < today:
        raise AslError("the re-evaluation date is in the past")
    cond = (condition if condition is not None else e["condition"]).strip()
    to = "conditional" if cond else "approved"
    Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute("update asl_entries set status = %s, basis = %s, condition = %s, review_due = %s, "
                           "approved_by = %s, approved_at = now(), updated_at = now() where id = %s and status = %s "
                           "returning *", (to, b[:4000], cond[:4000], due, user["email"], entry_id,
                                           e["status"])).fetchone()
        if row is None:
            raise AslError("the entry changed meanwhile: open it again")
        what = ("re-evaluated" if renew else "approved") + (" with conditions" if cond else "")
        Q._sign(conn, user, f"Supplier {what}", "asl", entry_id, f"{e['supplier']}, {e['item_code'] or 'all items'}")
        log(conn, entry_id, user["email"], what, reason.strip())
    return row


def move(conn, email: str, entry_id: int, to: str, reason: str) -> dict:
    """Suspend, disqualify, or qualify a disqualified supplier again (back to a draft), with a reason."""
    allowed = {"suspended": ("approved", "conditional"), "disqualified": ("draft", "approved", "conditional",
                                                                          "suspended"), "draft": ("disqualified",)}
    if to not in allowed:
        raise AslError("suspend, disqualify or qualify again")
    if not reason.strip():
        raise AslError("give the reason")
    e = get(conn, entry_id)
    if e["status"] not in allowed[to]:
        raise AslError(f"a {e['status']} entry cannot be {'qualified again' if to == 'draft' else to}")
    with conn.transaction():
        row = conn.execute("update asl_entries set status = %s, updated_at = now() where id = %s and status = %s "
                           "returning *", (to, entry_id, e["status"])).fetchone()
        if row is None:
            raise AslError("the entry changed meanwhile: open it again")
        log(conn, entry_id, email, {"draft": "qualified again"}.get(to, to), reason.strip())
    return row


def stats(conn) -> dict[tuple[str, str | None], dict]:
    """Lots inspected (signed), lots rejected and open NCRs per supplier and item, and per supplier (item None)."""
    out: dict[tuple, dict] = {}
    for r in conn.execute("select supplier, item_code, count(*) as lots, count(*) filter (where result = 'reject') "
                          "as rejected from iqc_inspections where supplier is not null and status in ('judged', "
                          "'released', 'rejected') group by 1, 2").fetchall():
        for k in ((r["supplier"], r["item_code"]), (r["supplier"], None)):
            x = out.setdefault(k, {"lots": 0, "rejected": 0, "open_ncrs": 0})
            x["lots"] += r["lots"]
            x["rejected"] += r["rejected"]
    for r in conn.execute("select supplier, item_code, count(*) as n from ncr_records where supplier is not null "
                          "and status not in ('closed', 'cancelled') group by 1, 2").fetchall():
        for k in ((r["supplier"], r["item_code"]), (r["supplier"], None)):
            out.setdefault(k, {"lots": 0, "rejected": 0, "open_ncrs": 0})["open_ncrs"] += r["n"]
    return out


def listing(conn, today: dt.date) -> list[dict]:
    st = stats(conn)
    out = []
    for e in conn.execute("select * from asl_entries order by supplier, item_code nulls first").fetchall():
        s = st.get((e["supplier"], e["item_code"]), {"lots": 0, "rejected": 0, "open_ncrs": 0})
        out.append({**_iso(e), **s, "review": AP.review_state(e, today),
                    "reject_rate": round(100.0 * s["rejected"] / s["lots"], 1) if s["lots"] else None})
    return out


def check_lines(conn, supplier: str | None, items: list[str], today: dt.date) -> list[dict]:
    """For a purchase order: each item's standing with this supplier; what is not ok is listed."""
    entries = I.asl_entries(conn)
    out = []
    for code in items:
        s = AP.standing(entries, supplier, code, today)
        if s["outcome"] != "ok":
            out.append({"item_code": code, "outcome": s["outcome"], "why": s["why"]})
    return out


def from_register(conn, user: dict, password: str) -> int:
    """Bring the ISO 9001 supplier approval register into the list, once, signed: the latest entry per supplier
    becomes an entry for all its items (approved, conditional, or disqualified if removed). Suppliers already on
    the list, or not known to ERPNext, are left out."""
    known = {s["key"]: s for s in I.suppliers(conn)}
    by_name = {_norm(s["name"]): k for k, s in known.items()} | {_norm(k): k for k in known}
    have = {r["supplier"] for r in conn.execute("select supplier from asl_entries where item_code is null")}
    latest: dict[str, dict] = {}
    for r in conn.execute("select id, \"values\" from qms_register_entries where register = 'suppliers' and "
                          "status <> 'void' order by id").fetchall():
        v = r["values"]
        key = by_name.get(_norm(v.get("supplier")))
        if key and key not in have:
            if key not in latest or str(v.get("approved_on") or "") >= str(latest[key]["values"].get("approved_on")
                                                                           or ""):
                latest[key] = r
    if not latest:
        raise AslError("there is nothing to bring in: no supplier in the register that ERPNext knows and the list "
                       "does not have yet")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        for key, r in latest.items():
            v = r["values"]
            status = {"approved": "approved", "conditional": "conditional", "removed": "disqualified"}[v["status"]]
            basis = " ".join(x for x in (str(v.get("basis") or ""), f"Approved or evaluated on {v.get('approved_on')}."
                                         if v.get("approved_on") else "") if x) or "See the supplier register."
            row = conn.execute(
                "insert into asl_entries (supplier, item_code, status, basis, condition, review_due, source, "
                "created_by, approved_by, approved_at) values (%s, null, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                (key, status, basis[:4000], "See the supplier register entry." if status == "conditional" else "",
                 _date(v.get("next_review"), "next review"), f"supplier register entry #{r['id']}", user["email"],
                 user["email"] if status != "disqualified" else None,
                 dt.datetime.now(dt.UTC) if status != "disqualified" else None)).fetchone()
            log(conn, row["id"], user["email"], "brought in", f"from supplier register entry #{r['id']}: "
                f"{v.get('status')}" + (f", supplies {v['supplies']}" if v.get("supplies") else ""))
        Q._sign(conn, user, "Supplier approvals brought in from the register", "asl", 0,
                f"{len(latest)} suppliers")
    return len(latest)
