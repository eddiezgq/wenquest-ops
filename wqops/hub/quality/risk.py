"""Risk management, step 17h (ADR-0017; dee-qms PLAN-RISK).

The company keeps its own criteria: severity and probability levels and a matrix saying which combinations are
acceptable, to be reduced as far as possible, or unacceptable (changes logged; an example 5 x 5 can be loaded and
must be replaced). Each product has a risk management file: hazards, hazardous situations, harm, the initial risk,
controls and their verification, the residual risk, and a benefit-risk note where the residual risk is
unacceptable. Acceptability is looked up, never typed. A file is approved with a signature by someone who did not
own or edit it; the verdicts, the criteria used and a fingerprint are then kept and the file is fixed. A new version
is started from the approved one; approving it supersedes the old one. Drafts are withdrawn with a reason; nothing
is deleted.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.quality import records as Q
from wqops.hub.quality import risk_rules as RR
from wqops.i18n import say

FILE_FIELDS = {"product", "scope", "owner", "conclusion", "benefit_risk"}
ITEM_TEXT = {"hazard", "situation", "harm", "controls", "verification", "benefit_risk"}
ITEM_RANKS = {"severity": "severity", "probability": "probability", "res_severity": "severity",
              "res_probability": "probability"}


class RiskError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, fid: int | None, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into risk_log (file_id, email, action, note) values (%s, %s, %s, %s)",
                 (fid, email, action, (note or "")[:2000]))


# ---------------------------------------------------------------- criteria

def levels(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute("select * from risk_levels order by kind desc, rank")]


def matrix(conn, active_only: bool = True) -> dict[tuple[int, int], str]:
    """The matrix; by default only the cells of levels in use (a level no longer in use decides nothing)."""
    sql = ("select m.* from risk_matrix m join risk_levels s on s.kind = 'severity' and s.rank = m.severity and "
           "s.active join risk_levels p on p.kind = 'probability' and p.rank = m.probability and p.active"
           if active_only else "select * from risk_matrix")
    return {(r["severity"], r["probability"]): r["verdict"] for r in conn.execute(sql)}


def _used(conn, kind: str, rank: int) -> bool:
    cols = ("severity", "res_severity") if kind == "severity" else ("probability", "res_probability")
    return conn.execute(f"select 1 from risk_items i join risk_files f on f.id = i.file_id where f.status in "  # noqa: S608
                        f"('approved', 'superseded') and %s in (i.{cols[0]}, i.{cols[1]}) limit 1",
                        (rank,)).fetchone() is not None


def add_level(conn, email: str, data: dict) -> dict:
    kind, rank = data.get("kind"), data.get("rank")
    name = str(data.get("name") or "").strip()
    if kind not in RR.KINDS:
        raise RiskError(say("a level is a severity or a probability level"))
    if type(rank) is not int or not 1 <= rank <= 20:
        raise RiskError(say("the rank is a whole number from 1 to 20"))
    if not name:
        raise RiskError(say("name the level"))
    with conn.transaction():
        if conn.execute("select 1 from risk_levels where kind = %s and rank = %s", (kind, rank)).fetchone():
            raise RiskError(say("there is already a {kind} level {rank}", kind=kind, rank=rank))
        row = conn.execute("insert into risk_levels (kind, rank, name, description, created_by) values "
                           "(%s, %s, %s, %s, %s) returning *", (kind, rank, name[:200],
                                                                str(data.get("description") or "")[:2000],
                                                                email)).fetchone()
        log(conn, None, email, "level added", f"{kind} {rank} {name}")
    return _iso(row)


def update_level(conn, email: str, lid: int, data: dict) -> dict:
    """The description and whether it is in use can change; the name only while no approved file used it."""
    with conn.transaction():
        lv = conn.execute("select * from risk_levels where id = %s for update", (lid,)).fetchone()
        if lv is None:
            raise KeyError(lid)
        d = {}
        if "name" in data and str(data["name"] or "").strip() != lv["name"]:
            if not str(data["name"] or "").strip():
                raise RiskError(say("name the level"))
            if _used(conn, lv["kind"], lv["rank"]):
                raise RiskError(say("an approved risk file uses this level: its name stays (add a new level instead)"))
            d["name"] = str(data["name"]).strip()[:200]
        if "description" in data:
            d["description"] = str(data["description"] or "")[:2000]
        if "active" in data:
            d["active"] = bool(data["active"])
        d = {k: v for k, v in d.items() if v != lv[k]}
        if not d:
            return _iso(lv)
        row = conn.execute("update risk_levels set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *", {**d, "id": lid}).fetchone()
        log(conn, None, email, "level changed", f"{lv['kind']} {lv['rank']}: " + "; ".join(
            f"{k} {lv[k]!r} -> {v!r}" for k, v in d.items()))
    return _iso(row)


def set_cell(conn, email: str, severity, probability, verdict) -> dict:
    """Set one cell of the matrix, or clear it (None): the change is logged."""
    if type(severity) is not int or type(probability) is not int:
        raise RiskError(say("the cell is a severity rank and a probability rank"))
    if verdict not in (*RR.VERDICTS, None):
        raise RiskError("the verdict is one of: " + ", ".join(RR.VERDICTS))
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-risk-matrix'))")
        have = {(r["kind"], r["rank"]) for r in conn.execute("select kind, rank from risk_levels where active")}
        if verdict and (("severity", severity) not in have or ("probability", probability) not in have):
            raise RiskError(say("both levels must exist and be in use"))
        old = matrix(conn, active_only=False).get((severity, probability))
        if old == verdict:
            return {}
        if verdict is None:
            conn.execute("delete from risk_matrix where severity = %s and probability = %s", (severity, probability))
        else:
            conn.execute("insert into risk_matrix (severity, probability, verdict, updated_by) values (%s, %s, %s, %s) "
                         "on conflict (severity, probability) do update set verdict = excluded.verdict, "
                         "updated_by = excluded.updated_by, updated_at = now()",
                         (severity, probability, verdict, email))
        log(conn, None, email, "matrix changed", f"S{severity} x P{probability}: {old or '-'} -> {verdict or '-'}")
    return {"severity": severity, "probability": probability, "verdict": verdict}


def load_example(conn, email: str) -> None:
    """The example 5 x 5, only while the company has no criteria; marked to be replaced."""
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-risk-matrix'))")
        if conn.execute("select 1 from risk_levels limit 1").fetchone():
            raise RiskError(say("the company already has risk levels: change them instead"))
        for kind, names in RR.EXAMPLE_LEVELS.items():
            for rank, name in enumerate(names, 1):
                conn.execute("insert into risk_levels (kind, rank, name, description, created_by) values "
                             "(%s, %s, %s, %s, %s)", (kind, rank, name, RR.EXAMPLE_NOTE, email))
        for (s, p), v in RR.example_matrix().items():
            conn.execute("insert into risk_matrix (severity, probability, verdict, updated_by) values "
                         "(%s, %s, %s, %s)", (s, p, v, email))
        log(conn, None, email, "example loaded", RR.EXAMPLE_NOTE)


def criteria_history(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute("select at, email, action, note from risk_log where file_id is null "
                                          "order by id desc limit 200")]


# ---------------------------------------------------------------- files

def get(conn, fid: int, lock: bool = False) -> dict:
    sql = "select * from risk_files where id = %s for update" if lock else "select * from risk_files where id = %s"
    row = conn.execute(sql, (fid,)).fetchone()
    if row is None:
        raise KeyError(fid)
    return row


def items(conn, fid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from risk_items where file_id = %s order by seq", (fid,))]


def _owner(conn, v) -> str | None:
    o = str(v or "").strip().lower() or None
    if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
        raise RiskError(say("{o} is not a person in the company", o=o))
    return o


def create(conn, email: str, data: dict) -> dict:
    product = str(data.get("product") or "").strip()
    if not product:
        raise RiskError(say("name the product or product family"))
    owner = _owner(conn, data.get("owner"))
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-number:risk_files'))")
        n = conn.execute("select count(*) + 1 as n from risk_files where previous_id is null").fetchone()["n"]
        row = conn.execute("insert into risk_files (name, product, scope, owner, editors, created_by) values "
                           "(%s, %s, %s, %s, %s, %s) returning *",
                           (f"RMF-{n:05d}", product[:300], str(data.get("scope") or "")[:4000], owner, [email],
                            email)).fetchone()
        log(conn, row["id"], email, "started", product)
    return row


def _draft(conn, fid: int) -> dict:
    f = get(conn, fid, lock=True)
    if f["status"] != "draft":
        raise RiskError(say("the risk file is {status}: start a new version to change it", status=f['status']))
    return f


def _touch(conn, f: dict, email: str) -> None:
    if email not in f["editors"]:
        conn.execute("update risk_files set editors = array_append(editors, %s), updated_at = now() where id = %s",
                     (email, f["id"]))


def update(conn, email: str, fid: int, data: dict) -> dict:
    bad = set(data) - FILE_FIELDS
    if bad:
        raise RiskError(say("{bad} cannot be changed here", bad=sorted(bad)[0].replace('_', ' ')))
    with conn.transaction():
        f = _draft(conn, fid)
        d = {}
        for k, v in data.items():
            if k == "owner":
                d[k] = _owner(conn, v)
            elif k == "product":
                if not str(v or "").strip():
                    raise RiskError(say("name the product or product family"))
                d[k] = str(v).strip()[:300]
            else:
                d[k] = str(v or "").strip()[:4000]
        d = {k: v for k, v in d.items() if v != f[k]}
        if not d:
            return f
        conn.execute("update risk_files set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                     + ", updated_at = now() where id = %(id)s", {**d, "id": fid})
        _touch(conn, f, email)
        log(conn, fid, email, "changed", ", ".join(k.replace("_", " ") for k in sorted(d)))
    return get(conn, fid)


def _item_values(conn, data: dict, current: dict | None = None) -> dict:
    out = {}
    have = {(r["kind"], r["rank"]) for r in conn.execute("select kind, rank from risk_levels where active")}
    for k, v in data.items():
        if k in ITEM_TEXT:
            out[k] = str(v or "").strip()[:4000]
        elif k in ITEM_RANKS:
            if current is not None and v == current[k]:      # unchanged: kept even if the level is no longer in use
                out[k] = v
            elif v in (None, ""):
                out[k] = None
            elif type(v) is not int or (ITEM_RANKS[k], v) not in have:
                raise RiskError(say("{k} is the rank of a {ITEM_RANKS} level in use",
                                    k=k.replace('_', ' ').replace('res ', 'residual '), ITEM_RANKS=ITEM_RANKS[k]))
            else:
                out[k] = v
        elif k == "capa_id":
            if v not in (None, "") and (type(v) is not int or not conn.execute(
                    "select 1 from capas where id = %s", (v,)).fetchone()):
                raise RiskError(say("no such corrective action"))
            out[k] = v or None
        else:
            raise RiskError(say("{k} is not part of a risk item", k=k.replace('_', ' ')))
    return out


def _check_pair(it: dict) -> None:
    if (it.get("res_severity") is None) != (it.get("res_probability") is None):
        raise RiskError(say("give both the residual severity and the residual probability, or neither"))


def add_item(conn, email: str, fid: int, data: dict) -> dict:
    with conn.transaction():
        f = _draft(conn, fid)
        d = _item_values(conn, data)
        _check_pair(d)
        seq = conn.execute("select coalesce(max(seq), 0) + 1 as n from risk_items where file_id = %s",
                           (fid,)).fetchone()["n"]
        cols = ["file_id", "seq", *d]
        row = conn.execute(f"insert into risk_items ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *", [fid, seq, *d.values()]).fetchone()
        _touch(conn, f, email)
        log(conn, fid, email, "item added", f"{seq}: {d.get('hazard', '')}")
    return row


def update_item(conn, email: str, fid: int, iid: int, data: dict) -> dict:
    with conn.transaction():
        f = _draft(conn, fid)
        it = conn.execute("select * from risk_items where id = %s and file_id = %s", (iid, fid)).fetchone()
        if it is None:
            raise KeyError(iid)
        d = {k: v for k, v in _item_values(conn, data, it).items() if v != it[k]}
        _check_pair({**it, **d})
        if not d:
            return it
        row = conn.execute("update risk_items set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *", {**d, "id": iid}).fetchone()
        _touch(conn, f, email)
        log(conn, fid, email, "item changed", f"{it['seq']}: " + ", ".join(k.replace("_", " ") for k in sorted(d)))
    return row


def remove_item(conn, email: str, fid: int, iid: int) -> None:
    with conn.transaction():
        f = _draft(conn, fid)
        it = conn.execute("delete from risk_items where id = %s and file_id = %s returning *", (iid, fid)).fetchone()
        if it is None:
            raise KeyError(iid)
        _touch(conn, f, email)
        log(conn, fid, email, "item removed", f"{it['seq']}: {it['hazard']}")


def _not_involved(user: dict, f: dict) -> None:
    if user["email"] == f["owner"] or user["email"] in f["editors"] or user["email"] == f["created_by"]:
        raise PermissionError(say("someone who does not own and did not edit the risk file approves it"))


def approve(conn, user: dict, fid: int, password: str) -> dict:
    """Looked up once more against the current criteria; the verdicts, the criteria and a fingerprint are kept;
    the version it revises is superseded."""
    f = get(conn, fid)
    if f["status"] != "draft":
        raise RiskError(say("approve a draft risk file"))
    _not_involved(user, f)
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-risk-matrix'))")   # the criteria hold still
        f = _draft(conn, fid)
        _not_involved(user, f)
        m, its = matrix(conn), items(conn, fid)
        missing = RR.to_approve(f, its, m)
        if missing:
            raise RiskError("still needed: " + "; ".join(missing))
        for it in its:
            it["initial_verdict"] = RR.verdict(m, it["severity"], it["probability"])
            it["residual_verdict"] = RR.residual(it, m)
            conn.execute("update risk_items set initial_verdict = %s, residual_verdict = %s where id = %s",
                         (it["initial_verdict"], it["residual_verdict"], it["id"]))
        crit = RR.criteria(levels(conn), m)
        fp = RR.fingerprint(f, its, crit)
        Q._sign(conn, user, "Risk management file approved", "risk_file", fid, f"{f['name']} v{f['version']}")
        row = conn.execute("update risk_files set status = 'approved', approved_by = %s, approved_at = %s, "
                           "criteria = %s, fingerprint = %s, updated_at = now() where id = %s returning *",
                           (user["email"], dt.datetime.now(dt.UTC), Jsonb(crit), fp, fid)).fetchone()
        log(conn, fid, user["email"], "approved", fp)
        if f["previous_id"]:
            conn.execute("update risk_files set status = 'superseded', updated_at = now() where id = %s and "
                         "status = 'approved'", (f["previous_id"],))
            log(conn, f["previous_id"], user["email"], "superseded", f"by version {f['version']}")
    return row


def revise(conn, email: str, fid: int) -> dict:
    """A new draft version from the approved one, its items copied (without verdicts)."""
    with conn.transaction():
        f = get(conn, fid, lock=True)
        if f["status"] != "approved":
            raise RiskError(say("start a new version from the approved one"))
        if conn.execute("select 1 from risk_files where name = %s and status = 'draft'", (f["name"],)).fetchone():
            raise RiskError(say("a new version is already being drafted"))
        version = conn.execute("select max(version) + 1 as v from risk_files where name = %s",
                               (f["name"],)).fetchone()["v"]     # a withdrawn draft keeps its number
        row = conn.execute("insert into risk_files (name, version, previous_id, product, scope, owner, conclusion, "
                           "benefit_risk, editors, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                           "returning *", (f["name"], version, fid, f["product"], f["scope"], f["owner"],
                                           f["conclusion"], f["benefit_risk"], [email], email)).fetchone()
        keys = ["seq", "hazard", "situation", "harm", "severity", "probability", "controls", "verification",
                "res_severity", "res_probability", "benefit_risk", "capa_id"]
        for it in items(conn, fid):
            conn.execute(f"insert into risk_items (file_id, {', '.join(keys)}) values "  # noqa: S608 - fixed names
                         f"(%s, {', '.join(['%s'] * len(keys))})", [row["id"], *(it[k] for k in keys)])
        log(conn, row["id"], email, "new version", f"from version {f['version']}")
    return row


def withdraw(conn, email: str, fid: int, reason: str) -> dict:
    if not reason.strip():
        raise RiskError(say("give the reason"))
    with conn.transaction():
        _draft(conn, fid)
        row = conn.execute("update risk_files set status = 'withdrawn', withdraw_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], fid)).fetchone()
        log(conn, fid, email, "withdrawn", reason.strip())
    return row


def intact(conn, f: dict) -> bool | None:
    """Whether an approved file still matches the fingerprint taken at approval."""
    if not f["fingerprint"]:
        return None
    return RR.fingerprint(f, items(conn, f["id"]), f["criteria"]) == f["fingerprint"]


def listing(conn, status: str) -> list[dict]:
    where = {"current": "status in ('draft', 'approved')", "approved": "status = 'approved'",
             "draft": "status = 'draft'", "all": "true"}.get(status, "true")
    rows = conn.execute(f"select f.*, (select count(*) from risk_items i where i.file_id = f.id) as items "  # noqa: S608
                        f"from risk_files f where {where} order by name, version desc limit 500").fetchall()
    return [_iso(r) for r in rows]


def view(conn, fid: int) -> dict:
    f = get(conn, fid)
    its = items(conn, fid)
    m = matrix(conn)
    if f["status"] == "draft":
        for it in its:
            it["initial_verdict"] = RR.verdict(m, it["severity"], it["probability"])
            it["residual_verdict"] = RR.residual(it, m)
            it["needs"] = RR.item_needs(it, m)
    return {**_iso(f), "items": its,
            "to_approve": RR.to_approve(f, its, m) if f["status"] == "draft" else [],
            "intact": intact(conn, f),
            "versions": [_iso(r) for r in conn.execute("select id, version, status, approved_by, approved_at from "
                                                       "risk_files where name = %s order by version", (f["name"],))],
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from risk_log where "
                                                      "file_id = %s order by id", (fid,))],
            "signatures": Q.signatures(conn, "risk_file", fid)}


def summary(conn, since: dt.date, until: dt.date, tz: str = "UTC") -> dict:
    """For management review: files approved in the period, items in approved files whose residual risk is not
    acceptable, and drafts not yet approved."""
    return {
        "approved": conn.execute("select count(*) as n from risk_files where (approved_at at time zone %s)::date "
                                 "between %s and %s", (tz, since, until)).fetchone()["n"],
        "residual_not_acceptable": conn.execute(
            "select count(*) as n from risk_items i join risk_files f on f.id = i.file_id where f.status = 'approved' "
            "and i.residual_verdict <> 'acceptable'").fetchone()["n"],
        "drafts": conn.execute("select count(*) as n from risk_files where status = 'draft'").fetchone()["n"],
    }
