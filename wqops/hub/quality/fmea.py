"""Process FMEA, step 22c (ADR-0022).

The company keeps its own severity, occurrence and detection scales (ranks 1 to 10 in its own words) and its own rule
for when a row needs action (``fmea_rules``); changes are logged. A PFMEA covers one process (and the item it makes):
per step, failure modes, effects, causes, the controls in place and the three ranks. RPN and the rule's result are
computed by code, shown while drafting and written at approval. A PFMEA is approved with a signature by someone who did
not own or edit it; the criteria used and a fingerprint are kept and it is fixed. A new version starts from the
approved one; approving it supersedes the old. The AI may draft rows (``fmea_ai``); they wait for a person and carry no
ranks. Nonconformance reports on the item since approval are listed so a person can decide whether occurrence needs
re-rating. Actions may open a CAPA from a row at any time.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub.quality import causes as C
from wqops.hub.quality import fmea_rules as FR
from wqops.hub.quality import records as Q

FILE_FIELDS = {"process", "item_code", "scope", "owner"}
ROW_TEXT = {"step", "requirement", "failure_mode", "effect", "cause", "prevention", "detection_controls", "action"}


class FmeaError(ValueError):
    pass


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, fid: int | None, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into fmea_log (file_id, email, action, note) values (%s, %s, %s, %s)",
                 (fid, email, action, (note or "")[:2000]))


# ---------------------------------------------------------------- criteria

def scales(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute("select * from fmea_scales order by kind, rank")]


def ranks(conn) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {k: set() for k in FR.KINDS}
    for r in conn.execute("select kind, rank from fmea_scales where active"):
        out[r["kind"]].add(r["rank"])
    return out


def rule(conn) -> dict | None:
    r = conn.execute("select * from fmea_settings where id = 1").fetchone()
    if r is None:
        return None
    return {"method": r["method"], "rpn_action": r["rpn_action"], "severity_action": r["severity_action"],
            "rules": r["rules"], "needs_action": list(r["needs_action"])}


def _used(conn, kind: str, rank: int) -> bool:
    cols = {"severity": ("severity", "res_severity"), "occurrence": ("occurrence", "res_occurrence"),
            "detection": ("detection", "res_detection")}[kind]
    return conn.execute(f"select 1 from fmea_rows r join fmea_files f on f.id = r.file_id where f.status in "  # noqa: S608
                        f"('approved', 'superseded') and %s in (r.{cols[0]}, r.{cols[1]}) limit 1",
                        (rank,)).fetchone() is not None


def add_scale(conn, email: str, data: dict) -> dict:
    kind, rank = data.get("kind"), data.get("rank")
    name = str(data.get("name") or "").strip()
    if kind not in FR.KINDS:
        raise FmeaError("a scale is severity, occurrence or detection")
    if type(rank) is not int or not 1 <= rank <= 10:
        raise FmeaError("the rank is a whole number from 1 to 10")
    if not name:
        raise FmeaError("say what the rank means in your company")
    with conn.transaction():
        if conn.execute("select 1 from fmea_scales where kind = %s and rank = %s", (kind, rank)).fetchone():
            raise FmeaError(f"{kind} {rank} is already on the scale")
        row = conn.execute("insert into fmea_scales (kind, rank, name, description, created_by) values "
                           "(%s, %s, %s, %s, %s) returning *",
                           (kind, rank, name[:200], str(data.get("description") or "")[:2000], email)).fetchone()
        log(conn, None, email, "scale rank added", f"{kind} {rank} {name}")
    return _iso(row)


def update_scale(conn, email: str, sid: int, data: dict) -> dict:
    """The description and whether it is in use can change; the name only while no approved PFMEA used the rank."""
    with conn.transaction():
        sc = conn.execute("select * from fmea_scales where id = %s for update", (sid,)).fetchone()
        if sc is None:
            raise KeyError(sid)
        d = {}
        if "name" in data and str(data["name"] or "").strip() != sc["name"]:
            if not str(data["name"] or "").strip():
                raise FmeaError("say what the rank means in your company")
            if _used(conn, sc["kind"], sc["rank"]):
                raise FmeaError("an approved PFMEA uses this rank: its name stays")
            d["name"] = str(data["name"]).strip()[:200]
        if "description" in data:
            d["description"] = str(data["description"] or "")[:2000]
        if "active" in data:
            d["active"] = bool(data["active"])
        d = {k: v for k, v in d.items() if v != sc[k]}
        if not d:
            return _iso(sc)
        row = conn.execute("update fmea_scales set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *", {**d, "id": sid}).fetchone()
        log(conn, None, email, "scale rank changed", f"{sc['kind']} {sc['rank']}: " + "; ".join(
            f"{k} {sc[k]!r} -> {v!r}" for k, v in d.items()))
    return _iso(row)


def set_rule(conn, email: str, data: dict) -> dict:
    try:
        cfg = FR.check_rule(data)
    except FR.FmeaRuleError as exc:
        raise FmeaError(str(exc)) from exc
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-fmea-criteria'))")
        old = rule(conn)
        if old == cfg:
            return cfg
        conn.execute("insert into fmea_settings (id, method, rpn_action, severity_action, rules, needs_action, "
                     "updated_by) values (1, %s, %s, %s, %s, %s, %s) on conflict (id) do update set method = "
                     "excluded.method, rpn_action = excluded.rpn_action, severity_action = excluded.severity_action, "
                     "rules = excluded.rules, needs_action = excluded.needs_action, updated_by = excluded.updated_by, "
                     "updated_at = now()", (cfg["method"], cfg["rpn_action"], cfg["severity_action"],
                                            Jsonb(cfg["rules"]), cfg["needs_action"], email))
        desc = (f"RPN >= {cfg['rpn_action']}" + (f" or S >= {cfg['severity_action']}" if cfg["severity_action"]
                                                  else "") if cfg["method"] == "rpn"
                else f"lookup table, {len(cfg['rules'])} rows; action for {', '.join(cfg['needs_action'])}")
        log(conn, None, email, "rule changed", desc)
    return cfg


def criteria_history(conn) -> list[dict]:
    return [_iso(r) for r in conn.execute("select at, email, action, note from fmea_log where file_id is null "
                                          "order by id desc limit 200")]


# ---------------------------------------------------------------- PFMEAs

def get(conn, fid: int, lock: bool = False) -> dict:
    sql = "select * from fmea_files where id = %s for update" if lock else "select * from fmea_files where id = %s"
    row = conn.execute(sql, (fid,)).fetchone()
    if row is None:
        raise KeyError(fid)
    return row


def rows(conn, fid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from fmea_rows where file_id = %s order by seq", (fid,))]


def _owner(conn, v) -> str | None:
    o = str(v or "").strip().lower() or None
    if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
        raise FmeaError(f"{o} is not a person in the company")
    return o


def create(conn, email: str, data: dict) -> dict:
    process = str(data.get("process") or "").strip()
    if not process:
        raise FmeaError("name the process (and the product it makes)")
    owner = _owner(conn, data.get("owner"))
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-number:fmea_files'))")
        n = conn.execute("select count(*) + 1 as n from fmea_files where previous_id is null").fetchone()["n"]
        row = conn.execute("insert into fmea_files (name, process, item_code, scope, owner, editors, created_by) "
                           "values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (f"PFMEA-{n:05d}", process[:300], str(data.get("item_code") or "").strip()[:140] or None,
                            str(data.get("scope") or "")[:4000], owner, [email], email)).fetchone()
        log(conn, row["id"], email, "started", process)
    return row


def _draft(conn, fid: int) -> dict:
    f = get(conn, fid, lock=True)
    if f["status"] != "draft":
        raise FmeaError(f"the PFMEA is {f['status']}: start a new version to change it")
    return f


def _touch(conn, f: dict, email: str) -> None:
    if email not in f["editors"]:
        conn.execute("update fmea_files set editors = array_append(editors, %s), updated_at = now() where id = %s",
                     (email, f["id"]))


def update(conn, email: str, fid: int, data: dict) -> dict:
    bad = set(data) - FILE_FIELDS
    if bad:
        raise FmeaError(f"{sorted(bad)[0].replace('_', ' ')} cannot be changed here")
    with conn.transaction():
        f = _draft(conn, fid)
        d = {}
        for k, v in data.items():
            if k == "owner":
                d[k] = _owner(conn, v)
            elif k == "process":
                if not str(v or "").strip():
                    raise FmeaError("name the process (and the product it makes)")
                d[k] = str(v).strip()[:300]
            elif k == "item_code":
                d[k] = str(v or "").strip()[:140] or None
            else:
                d[k] = str(v or "").strip()[:4000]
        d = {k: v for k, v in d.items() if v != f[k]}
        if not d:
            return f
        conn.execute("update fmea_files set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                     + ", updated_at = now() where id = %(id)s", {**d, "id": fid})
        _touch(conn, f, email)
        log(conn, fid, email, "changed", ", ".join(k.replace("_", " ") for k in sorted(d)))
    return get(conn, fid)


def _row_values(conn, data: dict, current: dict | None = None) -> dict:  # noqa: PLR0912 - one branch per kind
    out = {}
    have = ranks(conn)
    for k, v in data.items():
        if k in ROW_TEXT:
            out[k] = str(v or "").strip()[:4000]
        elif k in FR.RANK_KEYS:
            if current is not None and v == current[k]:      # unchanged: kept even if the rank is no longer in use
                out[k] = v
            elif v in (None, ""):
                out[k] = None
            elif type(v) is not int or v not in have[FR.RANK_KEYS[k]]:
                raise FmeaError(f"{k.replace('res_', '').replace('_', ' ')} is a rank on the company's "
                                f"{FR.RANK_KEYS[k]} scale")
            else:
                out[k] = v
        elif k == "action_owner":
            out[k] = _owner(conn, v)
        elif k == "action_due":
            try:
                out[k] = dt.date.fromisoformat(str(v)[:10]) if v not in (None, "") else None
            except ValueError as exc:
                raise FmeaError("the due date is a date (YYYY-MM-DD)") from exc
        elif k == "refs":
            refs = [str(x).strip()[:60] for x in (v if isinstance(v, list) else [v] if v else []) if str(x).strip()]
            missing = [r for r in refs if r not in C.exists(conn, refs)]
            if missing:
                raise FmeaError(f"no record with the number: {', '.join(missing)}")
            out[k] = refs[:8]
        else:
            raise FmeaError(f"{k.replace('_', ' ')} is not part of a PFMEA row")
    return out


def _check_after(r: dict) -> None:
    given = [r.get(k) is not None for k in ("res_severity", "res_occurrence", "res_detection")]
    if any(given) and not all(given):
        raise FmeaError("give all three ranks after action, or none")


def add_row(conn, email: str, fid: int, data: dict) -> dict:
    with conn.transaction():
        f = _draft(conn, fid)
        d = _row_values(conn, data)
        _check_after(d)
        seq = conn.execute("select coalesce(max(seq), 0) + 1 as n from fmea_rows where file_id = %s",
                           (fid,)).fetchone()["n"]
        cols = ["file_id", "seq", *d]
        row = conn.execute(f"insert into fmea_rows ({', '.join(cols)}) values "  # noqa: S608 - fixed column names
                           f"({', '.join(['%s'] * len(cols))}) returning *", [fid, seq, *d.values()]).fetchone()
        _touch(conn, f, email)
        log(conn, fid, email, "row added", f"{seq}: {d.get('step', '')} / {d.get('failure_mode', '')}")
    return row


def _row(conn, fid: int, rid: int) -> dict:
    r = conn.execute("select * from fmea_rows where id = %s and file_id = %s", (rid, fid)).fetchone()
    if r is None:
        raise KeyError(rid)
    return r


def update_row(conn, email: str, fid: int, rid: int, data: dict, *, confirm: bool = False) -> dict:
    """Change a row; ``confirm`` also confirms a row the AI drafted (a person read and kept it)."""
    with conn.transaction():
        f = _draft(conn, fid)
        r = _row(conn, fid, rid)
        d = {k: v for k, v in _row_values(conn, data, r).items() if v != r[k]}
        _check_after({**r, **d})
        if confirm and not r["confirmed"]:
            d["confirmed"] = True
        if not d:
            return r
        row = conn.execute("update fmea_rows set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *", {**d, "id": rid}).fetchone()
        _touch(conn, f, email)
        what = ", ".join(k.replace("_", " ") for k in sorted(d) if k != "confirmed")
        log(conn, fid, email, "row confirmed" if d.get("confirmed") else "row changed",
            f"{r['seq']}: " + (what or r["failure_mode"]))
    return row


def remove_row(conn, email: str, fid: int, rid: int) -> None:
    with conn.transaction():
        f = _draft(conn, fid)
        r = conn.execute("delete from fmea_rows where id = %s and file_id = %s returning *", (rid, fid)).fetchone()
        if r is None:
            raise KeyError(rid)
        _touch(conn, f, email)
        log(conn, fid, email, "row removed", f"{r['seq']}: {r['step']} / {r['failure_mode']}"
            + (" (drafted by the AI)" if r["origin"] == "ai" else ""))


def propose(conn, email: str, fid: int, run_id: int, drafted: list[dict]) -> list[dict]:
    """The AI's checked rows, added unconfirmed and without ranks (``fmea_ai``)."""
    out = []
    with conn.transaction():
        f = _draft(conn, fid)
        seq = conn.execute("select coalesce(max(seq), 0) as n from fmea_rows where file_id = %s",
                           (fid,)).fetchone()["n"]
        for p in drafted:
            seq += 1
            out.append(conn.execute(
                "insert into fmea_rows (file_id, seq, step, failure_mode, effect, cause, prevention, "
                "detection_controls, refs, origin, ai_run, confirmed) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "'ai', %s, false) returning *",
                (fid, seq, p["step"], p["failure_mode"], p["effect"], p["cause"], p.get("prevention", ""),
                 p.get("detection_controls", ""), p["refs"], run_id)).fetchone())
        _touch(conn, f, email)
        log(conn, fid, email, "AI drafted rows", f"{len(out)} rows (run {run_id}), without ranks")
    return out


def _not_involved(user: dict, f: dict) -> None:
    if user["email"] == f["owner"] or user["email"] in f["editors"] or user["email"] == f["created_by"]:
        raise PermissionError("someone who does not own and did not edit the PFMEA approves it")


def approve(conn, user: dict, fid: int, password: str) -> dict:
    """Judged once more against the current criteria; RPNs, results, the criteria and a fingerprint are kept; the
    version it revises is superseded."""
    f = get(conn, fid)
    if f["status"] != "draft":
        raise FmeaError("approve a draft PFMEA")
    _not_involved(user, f)
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-fmea-criteria'))")
        f = _draft(conn, fid)
        _not_involved(user, f)
        cfg, rk, rs = rule(conn), ranks(conn), rows(conn, fid)
        missing = FR.to_approve(f, rs, rk, cfg)
        if missing:
            raise FmeaError("still needed: " + "; ".join(missing))
        for r in rs:
            j = FR.judge(cfg, r["severity"], r["occurrence"], r["detection"])
            r["rpn"], r["priority"] = j["rpn"], j["priority"]
            r["res_rpn"] = FR.rpn(r["res_severity"], r["res_occurrence"], r["res_detection"])
            conn.execute("update fmea_rows set rpn = %s, res_rpn = %s, priority = %s where id = %s",
                         (r["rpn"], r["res_rpn"], r["priority"], r["id"]))
        crit = FR.criteria(scales(conn), cfg)
        fp = FR.fingerprint(f, rs, crit)
        Q._sign(conn, user, "Process FMEA approved", "fmea", fid, f"{f['name']} v{f['version']}")
        row = conn.execute("update fmea_files set status = 'approved', approved_by = %s, approved_at = %s, "
                           "criteria = %s, fingerprint = %s, updated_at = now() where id = %s returning *",
                           (user["email"], dt.datetime.now(dt.UTC), Jsonb(crit), fp, fid)).fetchone()
        log(conn, fid, user["email"], "approved", fp)
        if f["previous_id"]:
            conn.execute("update fmea_files set status = 'superseded', updated_at = now() where id = %s and "
                         "status = 'approved'", (f["previous_id"],))
            log(conn, f["previous_id"], user["email"], "superseded", f"by version {f['version']}")
    return row


COPY = ["seq", "step", "requirement", "failure_mode", "effect", "severity", "cause", "occurrence", "prevention",
        "detection_controls", "detection", "action", "action_owner", "action_due", "res_severity", "res_occurrence",
        "res_detection", "refs", "origin", "ai_run", "confirmed"]


def revise(conn, email: str, fid: int) -> dict:
    """A new draft version from the approved one, its rows copied (without the results written at approval)."""
    with conn.transaction():
        f = get(conn, fid, lock=True)
        if f["status"] != "approved":
            raise FmeaError("start a new version from the approved one")
        if conn.execute("select 1 from fmea_files where name = %s and status = 'draft'", (f["name"],)).fetchone():
            raise FmeaError("a new version is already being drafted")
        version = conn.execute("select max(version) + 1 as v from fmea_files where name = %s",
                               (f["name"],)).fetchone()["v"]
        row = conn.execute("insert into fmea_files (name, version, previous_id, process, item_code, scope, owner, "
                           "editors, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (f["name"], version, fid, f["process"], f["item_code"], f["scope"], f["owner"], [email],
                            email)).fetchone()
        for r in rows(conn, fid):
            conn.execute(f"insert into fmea_rows (file_id, {', '.join(COPY)}) values "  # noqa: S608 - fixed names
                         f"(%s, {', '.join(['%s'] * len(COPY))})", [row["id"], *(r[k] for k in COPY)])
        log(conn, row["id"], email, "new version", f"from version {f['version']}")
    return row


def withdraw(conn, email: str, fid: int, reason: str) -> dict:
    if not reason.strip():
        raise FmeaError("give the reason")
    with conn.transaction():
        _draft(conn, fid)
        row = conn.execute("update fmea_files set status = 'withdrawn', withdraw_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], fid)).fetchone()
        log(conn, fid, email, "withdrawn", reason.strip())
    return row


def open_capa(conn, email: str, fid: int, seq: int, kind: str = "preventive") -> dict:
    """A corrective or preventive action for one row, linked to it; also after approval."""
    f = get(conn, fid)
    r = conn.execute("select * from fmea_rows where file_id = %s and seq = %s", (fid, seq)).fetchone()
    if r is None:
        raise KeyError(seq)
    if f["status"] == "withdrawn":
        raise FmeaError("the PFMEA is withdrawn")
    if kind not in ("corrective", "preventive"):
        raise FmeaError("kind is corrective or preventive")
    with conn.transaction():
        c = Q.create_capa(conn, email, kind=kind, title=f"{f['name']} row {seq}: {r['failure_mode']}"[:200],
                          description=f"Process step: {r['step']}. Failure mode: {r['failure_mode']}. Cause: "
                                      f"{r['cause']}. Recommended: {r['action'] or 'to decide'}.")
        conn.execute("insert into fmea_capas (file_id, row_seq, capa_id, created_by) values (%s, %s, %s, %s)",
                     (fid, seq, c["id"], email))
        log(conn, fid, email, "CAPA opened", f"row {seq}: {c['name']}")
    return c


def intact(conn, f: dict) -> bool | None:
    if not f["fingerprint"]:
        return None
    return FR.fingerprint(f, rows(conn, f["id"]), f["criteria"]) == f["fingerprint"]


def since_approval(conn, f: dict) -> list[dict]:
    """Nonconformance reports on the PFMEA's item opened after it was approved: a person decides whether occurrence
    needs re-rating (a new version)."""
    if not f["item_code"] or not f["approved_at"]:
        return []
    return [_iso(r) for r in conn.execute(
        "select id, name, title, status, created_at from ncr_records where item_code = %s and created_at > %s "
        "and status <> 'cancelled' order by created_at desc limit 50", (f["item_code"], f["approved_at"]))]


def listing(conn, status: str) -> list[dict]:
    where = {"current": "status in ('draft', 'approved')", "approved": "status = 'approved'",
             "draft": "status = 'draft'", "all": "true"}.get(status, "true")
    out = []
    for r in conn.execute(f"select f.*, (select count(*) from fmea_rows r where r.file_id = f.id) as rows "  # noqa: S608
                          f"from fmea_files f where {where} order by name, version desc limit 500").fetchall():
        x = _iso(r)
        x["ncrs_since"] = len(since_approval(conn, r)) if r["status"] == "approved" else 0
        out.append(x)
    return out


def view(conn, fid: int) -> dict:
    f = get(conn, fid)
    rs = rows(conn, fid)
    cfg, rk = rule(conn), ranks(conn)
    if f["status"] == "draft":
        for r in rs:
            j = FR.judge(cfg, r["severity"], r["occurrence"], r["detection"])
            r["rpn"], r["priority"], r["action_needed"] = j["rpn"], j["priority"], j["action"]
            r["res_rpn"] = FR.rpn(r["res_severity"], r["res_occurrence"], r["res_detection"])
            r["needs"] = FR.row_needs(r, rk, cfg)
    else:
        rule_then = (f["criteria"] or {}).get("rule")
        for r in rs:
            r["action_needed"] = FR.judge(rule_then, r["severity"], r["occurrence"], r["detection"])["action"]
    capas = conn.execute("select l.row_seq, c.id, c.name, c.status from fmea_capas l join capas c on c.id = l.capa_id "
                         "where l.file_id in (select id from fmea_files where name = %s) order by c.id",
                         (f["name"],)).fetchall()
    return {**_iso(f), "rows": [_iso(r) for r in rs],
            "to_approve": FR.to_approve(f, rs, rk, cfg) if f["status"] == "draft" else [],
            "intact": intact(conn, f), "ncrs_since": since_approval(conn, f), "capas": [dict(c) for c in capas],
            "links": C.links(conn, [x for r in rs for x in r["refs"]]),
            "flow_steps": [dict(x) for x in conn.execute(  # steps of process flow charts (22d) that cite this PFMEA
                "select c.id as chart_id, c.name, c.version, c.status, s.code, s.name as step from flow_steps s join "
                "flow_charts c on c.id = s.chart_id where c.status in ('draft', 'approved') and s.links -> 'fmea' @> "
                "%s order by c.name, s.seq", (Jsonb([{"name": f["name"]}]),))],
            "versions": [_iso(r) for r in conn.execute("select id, version, status, approved_by, approved_at from "
                                                       "fmea_files where name = %s order by version", (f["name"],))],
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from fmea_log where "
                                                      "file_id = %s order by id", (fid,))],
            "signatures": Q.signatures(conn, "fmea", fid)}


def context(conn, f: dict, *, today: dt.date) -> list[dict]:
    """The records the AI may read and cite when drafting rows: those about the PFMEA's item (``causes.context``)."""
    if not f["item_code"]:
        return []
    return C.context(conn, {"kind": None, "name": None, "items": [f["item_code"]], "supplier": None}, today=today)
