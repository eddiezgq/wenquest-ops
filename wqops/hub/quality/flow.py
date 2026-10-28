"""Process flow charts, step 22d (ADR-0022).

A company draws its production process as steps in order - operations, inspections, moves, storage, waits - with
branches such as rework loops and scrap. Each step can link to what it rests on: controlled documents by number, the
PFMEA rows that analyse it, the incoming inspection plan of its item, the production template, the measuring
equipment. Links are checked against what is in effect now. A flow chart is approved with a signature by someone who
did not own or edit it; what every link pointed to and a fingerprint are kept and it is fixed; a new version starts
from the approved one and supersedes it once approved. Operations no PFMEA row analyses are shown to the team.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops import i18n as I18N
from wqops.hub.quality import flow_rules as FL
from wqops.hub.quality import records as Q
from wqops.i18n import say

FIELDS = {"title", "item_code", "scope", "owner"}


class FlowError(ValueError):
    pass


def _join(items, sep: str = "; ") -> str:
    """A list inside a sentence, with the separator of the reader's language."""
    if I18N.current() == "zh":
        sep = {", ": "、", "; ": "；"}.get(sep, sep)
    return sep.join(items)


def _iso(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


def log(conn, cid: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into flow_log (chart_id, email, action, note) values (%s, %s, %s, %s)",
                 (cid, email, action, (note or "")[:2000]))


def get(conn, cid: int, lock: bool = False) -> dict:
    sql = "select * from flow_charts where id = %s for update" if lock else "select * from flow_charts where id = %s"
    row = conn.execute(sql, (cid,)).fetchone()
    if row is None:
        raise KeyError(cid)
    return row


def steps(conn, cid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from flow_steps where chart_id = %s order by seq", (cid,))]


# ---------------------------------------------------------------- what links point to

def resolve(conn, all_steps: list[dict], *, today: dt.date) -> dict[str, dict]:  # noqa: PLR0912 - one block per kind
    """For every link of the chart, what it points to now: {ok, label, why, warn, url}. ok is False when nothing in
    effect answers to it (unknown is never a pass)."""
    keys = {k for s in all_steps for k in FL.link_keys(s.get("links") or {})}
    out: dict[str, dict] = {}
    for kind, key in sorted(keys):
        r = {"ok": False, "label": key, "why": "", "warn": "", "url": None}
        if kind == "documents":
            d = conn.execute("select id, number, title, revision from documents where number = %s and status = "
                             "'effective' order by effective_date desc nulls last, id desc limit 1", (key,)).fetchone()
            if d:
                r.update(ok=True, label=f"{d['number']} rev {d['revision'] or '-'} {d['title'] or ''}".strip(),
                         url=f"/documents/{d['id']}")
            else:
                r["why"] = say("no revision of it is in effect")
        elif kind == "fmea":
            name, seq = key.rsplit("#", 1)
            f = conn.execute("select id, version from fmea_files where name = %s and status = 'approved'",
                             (name,)).fetchone()
            row = f and conn.execute("select failure_mode, step, rpn from fmea_rows where file_id = %s and seq = %s",
                                     (f["id"], int(seq))).fetchone()
            if row:
                r.update(ok=True, label=f"{name} v{f['version']} row {seq}: {row['failure_mode']} (RPN {row['rpn']})",
                         url=f"/quality/fmea/{f['id']}")
            else:
                r["why"] = say("the approved PFMEA has no such row") if f else say("no approved version of the PFMEA")
        elif kind == "plan":
            p = conn.execute("select id, version from iqc_plans where item_code = %s and status = 'enabled'",
                             (key,)).fetchone()
            if p:
                r.update(ok=True, label=f"{key} plan v{p['version']}", url=f"/quality/iqc/plans/{p['id']}")
            else:
                r["why"] = say("no inspection plan of this item is in use")
        elif kind == "template":
            t = conn.execute("select id, version, title from prod_templates where code = %s and status = 'active'",
                             (key,)).fetchone()
            if t:
                r.update(ok=True, label=f"{key} v{t['version']} {t['title']}".strip(),
                         url=f"/quality/production/templates/{t['id']}")
            else:
                r["why"] = say("no version of this template is in use")
        else:
            g = conn.execute("select id, code, name, status, next_due from gauges where lower(code) = lower(%s)",
                             (key,)).fetchone()
            if g is None or g["status"] == "retired":
                r["why"] = say("retired") if g else say("no such measuring equipment")
            else:
                r.update(ok=True, label=f"{g['code']} {g['name']}", url=f"/quality/gauges/{g['id']}")
                if g["status"] != "in_service":
                    r["warn"] = say("out of service")
                elif g["next_due"] and g["next_due"] < today:
                    r["warn"] = say("calibration overdue")
        out[f"{kind}:{key}"] = r
    return out


# ---------------------------------------------------------------- charts

def _owner(conn, v) -> str | None:
    o = str(v or "").strip().lower() or None
    if o and not conn.execute("select 1 from users where email = %s and active", (o,)).fetchone():
        raise FlowError(say("{o} is not a person in the company", o=o))
    return o


def create(conn, email: str, data: dict) -> dict:
    title = str(data.get("title") or "").strip()
    if not title:
        raise FlowError(say("name the process"))
    owner = _owner(conn, data.get("owner"))
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-number:flow_charts'))")
        n = conn.execute("select count(*) + 1 as n from flow_charts where previous_id is null").fetchone()["n"]
        row = conn.execute("insert into flow_charts (name, title, item_code, scope, owner, editors, created_by) values "
                           "(%s, %s, %s, %s, %s, %s, %s) returning *",
                           (f"PF-{n:05d}", title[:300], str(data.get("item_code") or "").strip()[:140] or None,
                            str(data.get("scope") or "")[:4000], owner, [email], email)).fetchone()
        log(conn, row["id"], email, say("started"), title)
    return row


def _draft(conn, cid: int) -> dict:
    c = get(conn, cid, lock=True)
    if c["status"] != "draft":
        raise FlowError(say("the flow chart is {status}: start a new version to change it", status=c['status']))
    return c


def _touch(conn, c: dict, email: str) -> None:
    if email not in c["editors"]:
        conn.execute("update flow_charts set editors = array_append(editors, %s), updated_at = now() where id = %s",
                     (email, c["id"]))


def update(conn, email: str, cid: int, data: dict) -> dict:
    bad = set(data) - FIELDS
    if bad:
        raise FlowError(say("{bad} cannot be changed here", bad=sorted(bad)[0].replace('_', ' ')))
    with conn.transaction():
        c = _draft(conn, cid)
        d = {}
        for k, v in data.items():
            if k == "owner":
                d[k] = _owner(conn, v)
            elif k == "title":
                if not str(v or "").strip():
                    raise FlowError(say("name the process"))
                d[k] = str(v).strip()[:300]
            elif k == "item_code":
                d[k] = str(v or "").strip()[:140] or None
            else:
                d[k] = str(v or "").strip()[:4000]
        d = {k: v for k, v in d.items() if v != c[k]}
        if not d:
            return c
        conn.execute("update flow_charts set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                     + ", updated_at = now() where id = %(id)s", {**d, "id": cid})
        _touch(conn, c, email)
        log(conn, cid, email, say("changed"), ", ".join(k.replace("_", " ") for k in sorted(d)))
    return get(conn, cid)


def _values(data: dict, seqs: set[int], own: int | None, current: dict | None = None) -> dict:
    out = {}
    try:
        for k, v in data.items():
            if k == "kind":
                if v not in FL.KINDS:
                    raise FlowError(say("a step is one of: {KINDS}", KINDS=', '.join(FL.KINDS)))
                out[k] = v
            elif k == "name":
                if not str(v or "").strip():
                    raise FlowError(say("name the step"))
                out[k] = str(v).strip()[:200]
            elif k in ("code", "description"):
                out[k] = str(v or "").strip()[:20 if k == "code" else 2000]
            elif k == "branches":
                out[k] = FL.branches(v, seqs, own)
            elif k == "links":
                out[k] = FL.links(v)
            else:
                raise FlowError(say("{k} is not part of a step", k=k))
    except FL.FlowRuleError as exc:
        raise FlowError(str(exc)) from exc
    if current is None and "kind" not in out:
        out["kind"] = "operation"
    return out


def add_step(conn, email: str, cid: int, data: dict) -> dict:
    with conn.transaction():
        c = _draft(conn, cid)
        have = steps(conn, cid)
        seq = max((s["seq"] for s in have), default=0) + 1
        d = _values(data, {s["seq"] for s in have}, seq)
        if "name" not in d:
            raise FlowError(say("name the step"))
        row = conn.execute("insert into flow_steps (chart_id, seq, code, kind, name, description, branches, links) "
                           "values (%s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (cid, seq, d.get("code", ""), d["kind"], d["name"], d.get("description", ""),
                            Jsonb(d.get("branches", [])), Jsonb(d.get("links", {})))).fetchone()
        _touch(conn, c, email)
        log(conn, cid, email, say("step added"), f"{seq}: {d['name']}")
    return row


def update_step(conn, email: str, cid: int, sid: int, data: dict) -> dict:
    with conn.transaction():
        c = _draft(conn, cid)
        have = steps(conn, cid)
        s = next((x for x in have if x["id"] == sid), None)
        if s is None:
            raise KeyError(sid)
        d = {k: v for k, v in _values(data, {x["seq"] for x in have}, s["seq"], s).items() if v != s[k]}
        if not d:
            return s
        row = conn.execute("update flow_steps set " + ", ".join(f"{k} = %({k})s" for k in d)  # noqa: S608
                           + " where id = %(id)s returning *",
                           {**{k: Jsonb(v) if k in ("branches", "links") else v for k, v in d.items()},
                            "id": sid}).fetchone()
        _touch(conn, c, email)
        log(conn, cid, email, say("step changed"), f"{s['seq']} {s['name']}: " + ", ".join(sorted(d)))
    return row


def remove_step(conn, email: str, cid: int, sid: int) -> None:
    """Removed; branches of other steps that went to it are removed with it (the log says so)."""
    with conn.transaction():
        c = _draft(conn, cid)
        s = conn.execute("delete from flow_steps where id = %s and chart_id = %s returning *", (sid, cid)).fetchone()
        if s is None:
            raise KeyError(sid)
        cut = 0
        for o in steps(conn, cid):
            keep = [b for b in o["branches"] if b["to"] != s["seq"]]
            if len(keep) != len(o["branches"]):
                cut += len(o["branches"]) - len(keep)
                conn.execute("update flow_steps set branches = %s where id = %s", (Jsonb(keep), o["id"]))
        _touch(conn, c, email)
        note = (say("{seq} {name}; {cut} branches to it removed", seq=s["seq"], name=s["name"], cut=cut) if cut
                else f"{s['seq']} {s['name']}")
        log(conn, cid, email, say("step removed"), note)


def move_step(conn, email: str, cid: int, sid: int, direction: str) -> None:
    """Swap a step with the one before or after it; branches follow the steps they pointed to."""
    if direction not in ("up", "down"):
        raise FlowError(say("move a step up or down"))
    with conn.transaction():
        c = _draft(conn, cid)
        have = steps(conn, cid)
        i = next((k for k, x in enumerate(have) if x["id"] == sid), None)
        if i is None:
            raise KeyError(sid)
        j = i - 1 if direction == "up" else i + 1
        if not 0 <= j < len(have):
            return
        a, b = have[i], have[j]
        swap = {a["seq"]: b["seq"], b["seq"]: a["seq"]}
        conn.execute("update flow_steps set seq = -seq where id in (%s, %s)", (a["id"], b["id"]))
        conn.execute("update flow_steps set seq = %s where id = %s", (b["seq"], a["id"]))
        conn.execute("update flow_steps set seq = %s where id = %s", (a["seq"], b["id"]))
        for o in steps(conn, cid):
            new = [{**x, "to": swap.get(x["to"], x["to"])} for x in o["branches"]]
            if new != o["branches"]:
                conn.execute("update flow_steps set branches = %s where id = %s", (Jsonb(new), o["id"]))
        _touch(conn, c, email)
        log(conn, cid, email, say("step moved"),
            say("{name} up", name=a["name"]) if direction == "up" else say("{name} down", name=a["name"]))


def _not_involved(user: dict, c: dict) -> None:
    if user["email"] == c["owner"] or user["email"] in c["editors"] or user["email"] == c["created_by"]:
        raise PermissionError(say("someone who does not own and did not edit the flow chart approves it"))


def approve(conn, user: dict, cid: int, password: str, *, today: dt.date) -> dict:
    c = get(conn, cid)
    if c["status"] != "draft":
        raise FlowError(say("approve a draft flow chart"))
    _not_involved(user, c)
    Q.check_signer(conn, user, password)
    with conn.transaction():
        c = _draft(conn, cid)
        _not_involved(user, c)
        st = steps(conn, cid)
        res = resolve(conn, st, today=today)
        missing = FL.to_approve(c, st, res)
        if missing:
            raise FlowError(say("still needed: {list}", list=_join(missing)))
        fp = FL.fingerprint(c, st, res)
        Q._sign(conn, user, say("Process flow chart approved"), "flow_chart", cid, f"{c['name']} v{c['version']}")
        row = conn.execute("update flow_charts set status = 'approved', approved_by = %s, approved_at = now(), "
                           "resolved = %s, fingerprint = %s, updated_at = now() where id = %s returning *",
                           (user["email"], Jsonb(res), fp, cid)).fetchone()
        log(conn, cid, user["email"], say("approved"), fp)
        if c["previous_id"]:
            conn.execute("update flow_charts set status = 'superseded', updated_at = now() where id = %s and "
                         "status = 'approved'", (c["previous_id"],))
            log(conn, c["previous_id"], user["email"], say("superseded"),
                say("by version {version}", version=c["version"]))
    return row


def revise(conn, email: str, cid: int) -> dict:
    with conn.transaction():
        c = get(conn, cid, lock=True)
        if c["status"] != "approved":
            raise FlowError(say("start a new version from the approved one"))
        if conn.execute("select 1 from flow_charts where name = %s and status = 'draft'", (c["name"],)).fetchone():
            raise FlowError(say("a new version is already being drafted"))
        version = conn.execute("select max(version) + 1 as v from flow_charts where name = %s",
                               (c["name"],)).fetchone()["v"]
        row = conn.execute("insert into flow_charts (name, version, previous_id, title, item_code, scope, owner, "
                           "editors, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
                           (c["name"], version, cid, c["title"], c["item_code"], c["scope"], c["owner"], [email],
                            email)).fetchone()
        for s in steps(conn, cid):
            conn.execute("insert into flow_steps (chart_id, seq, code, kind, name, description, branches, links) "
                         "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                         (row["id"], s["seq"], s["code"], s["kind"], s["name"], s["description"],
                          Jsonb(s["branches"]), Jsonb(s["links"])))
        log(conn, row["id"], email, say("new version"), say("from version {version}", version=c["version"]))
    return row


def withdraw(conn, email: str, cid: int, reason: str) -> dict:
    if not reason.strip():
        raise FlowError(say("give the reason"))
    with conn.transaction():
        _draft(conn, cid)
        row = conn.execute("update flow_charts set status = 'withdrawn', withdraw_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], cid)).fetchone()
        log(conn, cid, email, say("withdrawn"), reason.strip())
    return row


def intact(conn, c: dict) -> bool | None:
    if not c["fingerprint"]:
        return None
    return FL.fingerprint(c, steps(conn, c["id"]), c["resolved"]) == c["fingerprint"]


def listing(conn, status: str) -> list[dict]:
    where = {"current": "status in ('draft', 'approved')", "approved": "status = 'approved'",
             "draft": "status = 'draft'", "all": "true"}.get(status, "true")
    return [_iso(r) for r in conn.execute(
        f"select c.*, (select count(*) from flow_steps s where s.chart_id = c.id) as steps from flow_charts c "  # noqa: S608
        f"where {where} order by name, version desc limit 500")]


def view(conn, cid: int, *, today: dt.date) -> dict:
    c = get(conn, cid)
    st = steps(conn, cid)
    now = resolve(conn, st, today=today)
    changed = []
    if c["resolved"]:                       # what moved since approval: the chart stays as approved
        for k, was in c["resolved"].items():
            cur = now.get(k)
            if cur and (cur["ok"], cur["label"]) != (was["ok"], was["label"]):
                changed.append({"link": k, "was": was["label"], "now": cur["label"] if cur["ok"] else cur["why"]})
    return {**_iso(c), "steps": st, "links_now": now, "changed_since": changed,
            "to_approve": FL.to_approve(c, st, now) if c["status"] == "draft" else [],
            "not_analysed": FL.not_analysed(st), "intact": intact(conn, c), "kinds": FL.kinds(),
            "versions": [_iso(r) for r in conn.execute("select id, version, status, approved_by, approved_at from "
                                                       "flow_charts where name = %s order by version", (c["name"],))],
            "history": [_iso(r) for r in conn.execute("select at, email, action, note from flow_log where "
                                                      "chart_id = %s order by id", (cid,))],
            "signatures": Q.signatures(conn, "flow_chart", cid)}


def options(conn) -> dict:
    """What a step can link to now, for the pickers."""
    return {
        "documents": [dict(r) for r in conn.execute(
            "select distinct on (number) number, title, revision from documents where status = 'effective' and "
            "number is not null order by number, effective_date desc nulls last")],
        "fmea": [dict(r) for r in conn.execute(
            "select f.name, r.seq, r.step, r.failure_mode from fmea_rows r join fmea_files f on f.id = r.file_id "
            "where f.status = 'approved' order by f.name, r.seq")],
        "plans": [r["item_code"] for r in conn.execute("select item_code from iqc_plans where status = 'enabled' "
                                                       "order by item_code")],
        "templates": [dict(r) for r in conn.execute("select code, title from prod_templates where status = 'active' "
                                                    "order by code")],
        "gauges": [dict(r) for r in conn.execute("select code, name from gauges where status <> 'retired' "
                                                 "order by code")],
    }
