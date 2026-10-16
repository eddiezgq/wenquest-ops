"""The assistant reads one quality or document record (ADR-0021 item 3), so it can talk about the record a person
has open: a nonconformance, corrective action, complaint, change, risk file, production lot, recall, management
review, incoming inspection, gauge, approved-supplier entry or document. Reading only, with the person's role.
"""

from __future__ import annotations

from wqops.hub import permissions as P
from wqops.hub.ai import tools as T

# kind: (permission, the app page of one record)
KINDS = {
    "ncr": ("quality:view", "/quality/ncr/"), "capa": ("quality:view", "/quality/capa/"),
    "complaint": ("quality:view", "/quality/complaints/"), "change": ("quality:view", "/quality/changes/"),
    "risk_file": ("quality:view", "/quality/risk/"), "production": ("quality:view", "/quality/production/"),
    "recall": ("quality:view", "/quality/recalls/"), "review": ("quality:view", "/quality/reviews/"),
    "iqc": ("quality:view", "/quality/iqc/"), "gauge": ("quality:view", "/quality/gauges/"),
    "asl": ("quality:view", "/quality/suppliers#a"), "document": ("documents:view", "/documents/"),
}
DROP = {"text", "body", "password_hash", "sha256", "storage", "content"}     # long or private: never sent


def _rows(conn, sql: str, rid: int) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, (rid,)).fetchall()]


def _load(ctx: T.Ctx, kind: str, rid: int) -> dict:  # noqa: PLR0911 - one branch per kind
    from wqops.hub.docs import library as LIB  # noqa: PLC0415 - kept out of the tools' import time
    from wqops.hub.quality import asl as ASL  # noqa: PLC0415
    from wqops.hub.quality import calibration as CAL  # noqa: PLC0415
    from wqops.hub.quality import change_control as CH  # noqa: PLC0415
    from wqops.hub.quality import complaints as CMP  # noqa: PLC0415
    from wqops.hub.quality import iqc as I  # noqa: PLC0415
    from wqops.hub.quality import production as PRD  # noqa: PLC0415
    from wqops.hub.quality import recall as RC  # noqa: PLC0415
    from wqops.hub.quality import records as Q  # noqa: PLC0415
    from wqops.hub.quality import review as MR  # noqa: PLC0415
    from wqops.hub.quality import risk as RK  # noqa: PLC0415

    c = ctx.conn
    if kind == "ncr":
        return dict(Q.ncr(c, rid))
    if kind == "capa":
        return {**Q.capa(c, rid), "actions": _rows(c, "select text, owner, due, done, done_at from capa_actions "
                                                      "where capa_id = %s order by id", rid)}
    if kind == "complaint":
        return dict(CMP.get(c, rid))
    if kind == "change":
        return dict(CH.get(c, rid))
    if kind == "risk_file":
        return {**RK.get(c, rid), "hazards": RK.items(c, rid)}
    if kind == "production":
        return {**PRD.record(c, rid), "steps": PRD.steps(c, rid), "materials": PRD.materials(c, rid)}
    if kind == "recall":
        return {**RC.get(c, rid), "consignees": RC.consignees(c, rid)}
    if kind == "review":
        return {**MR.get(c, rid), "actions": MR.actions(c, rid)}
    if kind == "iqc":
        return {**I.get(c, rid), "readings": I.readings(c, rid)}
    if kind == "gauge":
        return dict(CAL.get(c, rid))
    if kind == "asl":
        return dict(ASL.get(c, rid))
    return dict(LIB.get(c, rid))


def _clean(v):
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if k not in DROP}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def get_record(ctx: T.Ctx, kind: str, id: int) -> dict:
    if kind not in KINDS:
        raise T.ToolError(f"no record kind {kind}; kinds: {', '.join(KINDS)}")
    perm = KINDS[kind][0]
    if not P.allows(ctx.roles, perm):
        raise T.ToolError(f"this person's role cannot see {kind.replace('_', ' ')} records")
    try:
        rid = int(id)
        row = _load(ctx, kind, rid)
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise T.ToolError(f"no {kind} {id}") from exc
    name = row.get("name") or row.get("code") or row.get("number") or str(rid)
    return {"ref": ctx.ref("Record", f"{kind}/{rid}/{name}"), "kind": kind, "record": _clean(row)}


TOOL = T.Tool(
    "get_record",
    "Read one quality or document record by its kind and id: " + ", ".join(KINDS) + ". Use it when the person "
    "asks about the record they have open (the page tells you its kind and id).",
    {"properties": {"kind": {"type": "string", "enum": list(KINDS)}, "id": {"type": "integer"}},
     "required": ["kind", "id"]},
    get_record,
)
