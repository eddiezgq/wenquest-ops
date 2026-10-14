"""Changing a quality workflow (ADR-0015, step 15b): a draft made from the enabled version, changed by people with
workflows:configure, checked against the red lines and compared with the enabled version, then enabled with a
password signature by someone who did not change it. The enabled version is retired, the new one frozen. Records
already open finish under the version they started with. Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import copy

from psycopg.types.json import Json

from wqops.hub import permissions as P
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W


class AdminError(ValueError):
    pass


def log(conn, vid: int, email: str, action: str, note: str = "") -> None:
    conn.execute("insert into workflow_log (version_id, email, action, note) values (%s, %s, %s, %s)",
                 (vid, email, action, note[:4000]))


def get(conn, vid: int) -> dict:
    row = conn.execute("select * from workflow_versions where id = %s", (vid,)).fetchone()
    if row is None:
        raise KeyError(vid)
    return row


def in_use(conn, kind: str) -> set[str]:
    return {r["status"] for r in conn.execute(f"select distinct status from {W.KINDS[kind]}")}  # noqa: S608


def view(conn, row: dict) -> dict:
    """A version with its red-line check, the changes from the enabled version and its history."""
    enabled = W.ensure(conn, row["kind"])
    errors = W.validate(row["config"], in_use(conn, row["kind"])) if row["status"] == "draft" else []
    hist = conn.execute("select at, email, action, note from workflow_log where version_id = %s order by id",
                        (row["id"],)).fetchall()
    return {**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()},
            "errors": errors, "changes": W.diff(enabled["config"], row["config"]) if row["id"] != enabled["id"] else [],
            "enabled_version": enabled["version"], "view": W.view(row["config"]),
            "history": [dict(h, at=h["at"].isoformat()) for h in hist],
            "signatures": Q.signatures(conn, "workflow", row["id"]), "options": options(conn, row["kind"])}


def options(conn, kind: str) -> dict:
    """What the editor may offer: fields a step can need, people who can be kept from a step, roles, conditions."""
    when = {k: list(v) if v else list(Q.disposition_types(conn)) for k, v in W.WHEN[kind].items()}
    return {"needs": W.NEEDS[kind], "not_by": {f: W.WHO[f] for f in sorted(W.NOT_BY_FIELDS[kind])},
            "roles": sorted(P.ROLE_PERMISSIONS), "field_types": list(W.FIELD_TYPES), "when": when,
            "locked_required": {k: v.get("required", []) for k, v in W.default(kind)["steps"].items()},
            "locked_not_by": {k: v.get("not_by", []) for k, v in W.default(kind)["steps"].items()},
            "signed": [k for k, v in W.default(kind)["steps"].items() if v.get("sign")]}


def new_draft(conn, kind: str, email: str) -> dict:
    """A draft copy of the enabled version (one draft per kind at a time)."""
    if kind not in W.KINDS:
        raise KeyError(kind)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-workflow:{kind}",))
        if conn.execute("select 1 from workflow_versions where kind = %s and status = 'draft'", (kind,)).fetchone():
            raise AdminError("there is already a draft of this workflow; finish or discard it first")
        base = W.ensure(conn, kind)
        nxt = conn.execute("select max(version) + 1 as n from workflow_versions where kind = %s",
                           (kind,)).fetchone()["n"]
        row = conn.execute("insert into workflow_versions (kind, version, config, status, created_by, edited_by, note) "
                           "values (%s, %s, %s, 'draft', %s, %s, %s) returning *",
                           (kind, nxt, Json(copy.deepcopy(base["config"])), email, [email],
                            f"from version {base['version']}")).fetchone()
        log(conn, row["id"], email, "draft made", f"from version {base['version']}")
    return row


def save(conn, vid: int, email: str, cfg: dict, note: str | None = None) -> dict:
    """Store a changed draft. It may still break red lines (they are shown); it cannot be enabled until it does not."""
    row = get(conn, vid)
    if row["status"] != "draft":
        raise AdminError(f"version {row['version']} is {row['status']}; changes go into a new draft")
    if not isinstance(cfg, dict) or cfg.get("kind") != row["kind"]:
        raise AdminError(f"this is a {row['kind']} workflow")
    changes = W.diff(row["config"], cfg)
    with conn.transaction():
        out = conn.execute("update workflow_versions set config = %s, edited_by = (select array(select distinct "
                           "unnest(edited_by || %s::text[]))), note = coalesce(%s, note) where id = %s returning *",
                           (Json(cfg), [email], note, vid)).fetchone()
        log(conn, vid, email, "changed", "; ".join(changes) or "no change")
    return out


def enable(conn, vid: int, user: dict, password: str) -> dict:
    """Signed enabling by someone with workflows:configure who did not change the draft."""
    row = get(conn, vid)
    if row["status"] != "draft":
        raise AdminError(f"version {row['version']} is {row['status']}")
    if user["email"] in (row["edited_by"] or []):
        raise PermissionError("someone who did not change this draft must enable it")
    errors = W.validate(row["config"], in_use(conn, row["kind"]))
    if errors:
        raise AdminError("fix these first: " + "; ".join(errors))
    if not W.diff(W.ensure(conn, row["kind"])["config"], row["config"]):
        raise AdminError("this draft changes nothing; discard it instead")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-workflow:{row['kind']}",))
        old = conn.execute("update workflow_versions set status = 'retired' where kind = %s and status = 'enabled' "
                           "returning id, version", (row["kind"],)).fetchone()
        out = conn.execute("update workflow_versions set status = 'enabled', fingerprint = %s, enabled_by = %s, "
                           "enabled_at = now() where id = %s returning *",
                           (W.fingerprint(row["config"]), user["email"], vid)).fetchone()
        Q._sign(conn, user, "Workflow version enabled", "workflow", vid, f"{row['kind']} workflow v{row['version']}")
        log(conn, vid, user["email"], "enabled", f"replaces version {old['version']}" if old else "")
        if old:
            log(conn, old["id"], user["email"], "retired", f"replaced by version {row['version']}")
    return out


def discard(conn, vid: int, email: str, reason: str) -> dict:
    if not reason.strip():
        raise AdminError("say why the draft is discarded")
    row = get(conn, vid)
    if row["status"] != "draft":
        raise AdminError(f"version {row['version']} is {row['status']}; only a draft can be discarded")
    with conn.transaction():
        out = conn.execute("update workflow_versions set status = 'discarded', discarded_reason = %s where id = %s "
                           "returning *", (reason.strip(), vid)).fetchone()
        log(conn, vid, email, "discarded", reason.strip())
    return out
