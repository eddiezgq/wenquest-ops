"""Drafts (ADR-0006 item 5, ADR-0008 item 3): propose, then a person confirms; only then does anything happen.

ERPNext drafts become Draft documents in ERPNext (docstatus 0); a person submits them in ERPNext. WenQuest Ops never
submits, cancels or deletes ERPNext documents. Hub drafts stay in the hub: a confirmed customer message is ready for a
person to send; a confirmed nonconformance report becomes an NCR record.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from wqops.erp import ErpClient
from wqops.hub import permissions as P

# doctype -> (permission needed to propose and confirm, fields that must be present)
DRAFTABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "Purchase Order": ("purchasing:draft", ("supplier", "items")),
    "Material Request": ("purchasing:draft", ("material_request_type", "items")),
    "Quality Inspection": ("quality:edit", ("inspection_type", "reference_type", "reference_name", "item_code")),
    "Customer Message": ("sales:view", ("customer", "sales_order", "subject", "body")),
    "Nonconformance Report": ("quality:edit", ("inspection", "item_code", "title", "description")),
    "Supplier": ("purchasing:draft", ("supplier_name",)),      # from an imported supplier list (ADR-0014 item 10)
}
HUB_KINDS = {"Customer Message", "Nonconformance Report"}
# set by ERPNext, or would turn a draft into something else
_NOT_ALLOWED = {"name", "docstatus", "amended_from", "owner", "creation", "modified", "modified_by", "idx"}


class DraftError(ValueError):
    pass


class NotAllowed(DraftError):
    pass


class Conflict(DraftError):
    """The draft was already decided."""


def permission(doctype: str) -> str:
    if doctype not in DRAFTABLE:
        raise DraftError(f"WenQuest Ops does not draft {doctype!r}; allowed: {', '.join(DRAFTABLE)}")
    return DRAFTABLE[doctype][0]


def check_allowed(user: dict, doctype: str) -> None:
    perm = permission(doctype)
    if not P.allows(user["roles"], perm):
        raise NotAllowed(f"your role does not allow: {P.PERMISSIONS[perm]}")


def clean(doctype: str, payload) -> dict:
    """The fields of the draft, checked: right doctype, required fields present, nothing ERPNext sets itself."""
    if not isinstance(payload, dict):
        raise DraftError("the draft must be an object of ERPNext fields")
    if payload.get("doctype", doctype) != doctype:
        raise DraftError(f"the draft says doctype {payload['doctype']!r}, not {doctype!r}")
    bad = sorted(k for k in payload if k in _NOT_ALLOWED or k.startswith("_"))
    if bad:
        raise DraftError(f"these fields are set by ERPNext, not by a draft: {', '.join(bad)}")
    missing = [f for f in DRAFTABLE[doctype][1] if payload.get(f) in (None, "", [])]
    if missing:
        raise DraftError(f"missing: {', '.join(missing)}")
    if "items" in payload:
        items = payload["items"]
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise DraftError("items must be a list of rows")
        for n, row in enumerate(items, start=1):
            if not row.get("item_code") or not isinstance(row.get("qty"), (int, float)) or row["qty"] <= 0:
                raise DraftError(f"items row {n}: needs item_code and a quantity above 0")
    return {k: v for k, v in payload.items() if k != "doctype"}


def _log(conn, draft_id: int, email: str | None, action: str, detail: str = "") -> None:
    conn.execute("insert into erp_draft_log (draft_id, email, action, detail) values (%s, %s, %s, %s)",
                 (draft_id, email, action, detail))


def public(row: dict) -> dict:
    out = {k: row[k] for k in ("id", "doctype", "summary", "payload", "source", "ai_run", "proposed_by", "status",
                               "decided_by", "erp_name", "error", "target", "record")}
    out["created_at"] = row["created_at"].isoformat()
    out["decided_at"] = row["decided_at"].isoformat() if row["decided_at"] else None
    return out


def propose(conn, user: dict, doctype: str, payload, *, summary: str = "", source: str = "person",
            ai_run: str | None = None) -> dict:
    check_allowed(user, doctype)
    if source == "ai" and not P.allows(user["roles"], "ai:use"):
        raise NotAllowed(f"your role does not allow: {P.PERMISSIONS['ai:use']}")
    if source not in ("person", "ai"):
        raise DraftError("source must be person or ai")
    fields = clean(doctype, payload)
    with conn.transaction():
        row = conn.execute("insert into erp_drafts (doctype, summary, payload, source, ai_run, proposed_by, target) "
                           "values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (doctype, summary[:500], Jsonb(fields), source, ai_run, user["email"],
                            "hub" if doctype in HUB_KINDS else "erpnext")).fetchone()
        _log(conn, row["id"], user["email"], "proposed", source if not ai_run else f"ai run {ai_run}")
    return public(row)


def get(conn, draft_id: int) -> dict | None:
    return conn.execute("select * from erp_drafts where id = %s", (draft_id,)).fetchone()


def visible(conn, user: dict, status: str | None = None) -> list[dict]:
    """Drafts of the doctypes this person may draft."""
    kinds = [d for d, (perm, _) in DRAFTABLE.items() if P.allows(user["roles"], perm)]
    sql, args = "select * from erp_drafts where doctype = any(%s)", [kinds]
    if status:
        sql += " and status = %s"
        args.append(status)
    return [public(r) for r in conn.execute(sql + " order by id desc limit 200", args).fetchall()]


def confirm(conn, user: dict, draft_id: int, erp: ErpClient) -> dict:
    """Create the Draft in ERPNext. Only one confirmation wins; a failed one can be confirmed again."""
    row = get(conn, draft_id)
    if row is None:
        raise KeyError(draft_id)
    check_allowed(user, row["doctype"])
    claimed = conn.execute("update erp_drafts set status = 'confirming' where id = %s and status in "
                           "('pending', 'failed') returning *", (draft_id,)).fetchone()
    if claimed is None:
        raise Conflict(f"this draft is already {row['status']}")
    if row["doctype"] in HUB_KINDS:
        return _confirm_hub(conn, user, row)
    try:
        doc = erp.insert({"doctype": row["doctype"], **row["payload"], **_erp_fields(erp, user, row), "docstatus": 0})
        if int(doc.get("docstatus") or 0) != 0:  # never expected; would mean ERPNext submitted it
            raise DraftError(f"ERPNext returned {doc['name']} with docstatus {doc['docstatus']}")
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"[:1000]
        with conn.transaction():
            conn.execute("update erp_drafts set status = 'failed', error = %s, decided_by = %s, decided_at = now() "
                         "where id = %s", (msg, user["email"], draft_id))
            _log(conn, draft_id, user["email"], "failed", msg)
        raise
    with conn.transaction():
        row = conn.execute("update erp_drafts set status = 'confirmed', erp_name = %s, error = null, decided_by = %s, "
                           "decided_at = now() where id = %s returning *",
                           (doc["name"], user["email"], draft_id)).fetchone()
        _log(conn, draft_id, user["email"], "confirmed", doc["name"])
    return public(row)


def _erp_fields(erp: ErpClient, user: dict, row: dict) -> dict:
    """Fields ERPNext needs that only the confirmation knows. A quality inspection needs an ERPNext user as the
    inspector: the person confirming if they have an ERPNext account (made at their first sign-in there),
    otherwise the account WenQuest Ops uses; the person is in the draft log either way. A supplier goes into the
    first supplier group ERPNext has, unless the draft names one."""
    if row["doctype"] == "Quality Inspection" and not row["payload"].get("inspected_by"):
        return {"inspected_by": user["email"] if erp.get("User", user["email"]) else erp.logged_user()}
    if row["doctype"] == "Supplier" and not row["payload"].get("supplier_group"):
        groups = erp.list("Supplier Group", filters=[["is_group", "=", 0]], order_by="name asc", limit=1)
        return {"supplier_group": groups[0]["name"]} if groups else {}     # ERPNext's own first group
    return {}


def _confirm_hub(conn, user: dict, row: dict) -> dict:
    p = row["payload"]
    with conn.transaction():
        record, note = None, "ready to send"
        if row["doctype"] == "Nonconformance Report":
            from wqops.hub.quality import records as Q  # noqa: PLC0415

            n = Q.create_ncr(conn, user["email"], title=p["title"], description=p["description"],
                             inspection=p.get("inspection"), item_code=p.get("item_code"), receipt=p.get("receipt"),
                             supplier=p.get("supplier"), quantity=p.get("quantity"), draft_id=row["id"])
            record = note = n["name"]
        out = conn.execute("update erp_drafts set status = 'confirmed', record = %s, error = null, decided_by = %s, "
                           "decided_at = now() where id = %s returning *",
                           (record, user["email"], row["id"])).fetchone()
        _log(conn, row["id"], user["email"], "confirmed", note)
    return public(out)


def reject(conn, user: dict, draft_id: int, reason: str = "") -> dict:
    row = get(conn, draft_id)
    if row is None:
        raise KeyError(draft_id)
    check_allowed(user, row["doctype"])
    with conn.transaction():
        row = conn.execute("update erp_drafts set status = 'rejected', decided_by = %s, decided_at = now() "
                           "where id = %s and status in ('pending', 'failed') returning *",
                           (user["email"], draft_id)).fetchone()
        if row is None:
            raise Conflict("only a pending or failed draft can be rejected")
        _log(conn, draft_id, user["email"], "rejected", reason[:500])
    return public(row)


def erp_link(base: str, doctype: str, name: str) -> str:
    return f"{base.rstrip('/')}/app/{doctype.lower().replace(' ', '-')}/{name}"
