"""The interface for machines and other systems (ADR-0020, 20d): an MES, a test bench, a gauge station. Plain code: no
AI, no network (WenQuest Ops answers calls; it never makes one).

Each machine or system has its own access token, limited to what it may do (send measurements, send production step
results, read events) and revocable; only a hash is kept, and every call is logged. What it sends is checked when it
arrives and then waits in an inbox: a person accepts it, signed with their own password, into the incoming inspection
or the production record, or rejects it with a reason. A machine never signs, and nothing it sends is written to a
record before a person has looked at it. Events are written by the database when lots are decided and reports opened;
the other system reads them in order from where it stopped.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import secrets

from psycopg.types.json import Jsonb

from wqops.hub.quality import cal_rules as CALR
from wqops.hub.quality import iqc as I
from wqops.hub.quality import production as PRD
from wqops.hub.quality import records as Q

SCOPES = {"measurements:send": "Send measurements for incoming inspections in progress",
          "production:send": "Send results of production steps",
          "events:read": "Read events: lots released or rejected, nonconformance reports opened"}
PREFIX = "wqo_"
MAX_READINGS = 2000


class IntegrationError(ValueError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: v.isoformat() if isinstance(v, dt.datetime | dt.date) else v for k, v in dict(row).items()}


# ---------------------------------------------------------------- tokens

def new_token(conn, email: str, name: str, scopes: list[str]) -> tuple[dict, str]:
    """A new access token; the token itself is returned once and never stored."""
    name = str(name or "").strip()[:100]
    if not name:
        raise IntegrationError("name the machine or system the token is for")
    if not isinstance(scopes, list) or not scopes or not set(scopes) <= set(SCOPES):
        raise IntegrationError("choose what it may do: " + ", ".join(SCOPES))
    if conn.execute("select 1 from integration_tokens where lower(name) = lower(%s) and revoked_at is null",
                    (name,)).fetchone():
        raise IntegrationError(f"{name} already has a token: revoke it first")
    token = PREFIX + secrets.token_urlsafe(32)
    row = conn.execute("insert into integration_tokens (name, scopes, token_hash, prefix, created_by) values "
                       "(%s, %s, %s, %s, %s) returning *",
                       (name, sorted(set(scopes)), _hash(token), token[:10], email)).fetchone()
    return _public(row), token


def _public(row: dict) -> dict:
    out = _iso(row)
    out.pop("token_hash", None)
    out["active"] = row["revoked_at"] is None
    return out


def tokens(conn) -> list[dict]:
    return [_public(r) | {"calls": r["calls"]} for r in conn.execute(
        "select t.*, (select count(*) from integration_calls c where c.token_id = t.id) as calls "
        "from integration_tokens t order by t.revoked_at is not null, t.id")]


def revoke(conn, email: str, tid: int, note: str = "") -> dict:
    row = conn.execute("update integration_tokens set revoked_by = %s, revoked_at = now(), revoke_note = %s "
                       "where id = %s and revoked_at is null returning *", (email, str(note or "")[:300], tid)
                       ).fetchone()
    if row is None:
        if conn.execute("select 1 from integration_tokens where id = %s", (tid,)).fetchone() is None:
            raise KeyError(tid)
        raise IntegrationError("the token is already revoked")
    return _public(row)


def authenticate(conn, token: str | None) -> dict | None:
    """The active token this is, or None."""
    if not token or not token.startswith(PREFIX) or len(token) > 200:
        return None
    row = conn.execute("update integration_tokens set last_used_at = now() where token_hash = %s and revoked_at is "
                       "null returning *", (_hash(token),)).fetchone()
    return row


def called(conn, token_id: int | None, method: str, path: str, status: int) -> None:
    conn.execute("insert into integration_calls (token_id, method, path, status) values (%s, %s, %s, %s)",
                 (token_id, method, path[:300], status))


def calls(conn, tid: int, limit: int = 50) -> list[dict]:
    return [_iso(r) for r in conn.execute("select method, path, status, at from integration_calls where token_id = %s "
                                          "order by id desc limit %s", (tid, limit))]


# ---------------------------------------------------------------- receiving

def _number(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float | str):
        raise IntegrationError(f"{what}: a number")
    try:
        x = float(v)
    except ValueError as exc:
        raise IntegrationError(f"{what}: {v!r} is not a number") from exc
    if not math.isfinite(x):
        raise IntegrationError(f"{what}: not a finite number")
    return x


def _gauge_code(conn, v) -> str | None:
    if v in (None, ""):
        return None
    code = str(v).strip()
    if not conn.execute("select 1 from gauges where code = %s", (code,)).fetchone():
        raise IntegrationError(f"no measuring equipment {code!r} is registered")
    return code


def _note(d: dict) -> str:
    return str(d.get("note") or "").strip()[:500]


def _inbox(conn, tok: dict, kind: str, target: str, payload: dict) -> dict:
    row = conn.execute("insert into integration_inbox (token_id, kind, target, payload) values (%s, %s, %s, %s) "
                       "returning *", (tok["id"], kind, target, Jsonb(payload))).fetchone()
    return {"id": row["id"], "status": "pending", "received_at": row["received_at"].isoformat(),
            "message": "received: it waits for a person to accept it"}


def receive_measurements(conn, tok: dict, d: dict) -> dict:
    """{"inspection": "IQC-00005", "readings": [{"sample": 1, "characteristic": "Length", "value": 10.01}],
    "equipment": "CMM-01", "note": "..."}: checked now, written when a person accepts it."""
    if not isinstance(d, dict):
        raise IntegrationError("send a JSON object")
    name = str(d.get("inspection") or "").strip()
    ins = conn.execute("select * from iqc_inspections where name = %s", (name,)).fetchone()
    if ins is None:
        raise IntegrationError(f"there is no incoming inspection {name!r}")
    if ins["status"] != "in_progress":
        raise IntegrationError(f"{name} is {ins['status'].replace('_', ' ')}: it takes no more readings")
    measured = {c["name"] for c in I.plan(conn, ins["plan_id"])["characteristics"] if c["kind"] == "measured"}
    rd = d.get("readings")
    if not isinstance(rd, list) or not rd:
        raise IntegrationError("readings: a list of {sample, characteristic, value}")
    if len(rd) > MAX_READINGS:
        raise IntegrationError(f"at most {MAX_READINGS} readings at a time")
    out, seen, errors = [], set(), []
    for k, r in enumerate(rd, start=1):
        try:
            if not isinstance(r, dict):
                raise IntegrationError("an object")
            s, ch = r.get("sample"), str(r.get("characteristic") or "")
            if type(s) is not int or not 1 <= s <= ins["n"]:
                raise IntegrationError(f"sample is 1 to {ins['n']}")
            if ch not in measured:
                raise IntegrationError(f"{ch!r} is not a measured characteristic of the plan "
                                       f"({', '.join(sorted(measured)) or 'none'})")
            if (s, ch) in seen:
                raise IntegrationError(f"sample {s} {ch} is sent twice")
            seen.add((s, ch))
            out.append({"sample": s, "characteristic": ch, "value": _number(r.get("value"), "value")})
        except IntegrationError as exc:
            errors.append(f"reading {k}: {exc}")
    if errors:
        raise IntegrationError("; ".join(errors[:20]))
    payload = {"inspection": name, "readings": out, "equipment": _gauge_code(conn, d.get("equipment")),
               "note": _note(d)}
    return _inbox(conn, tok, "measurements", name, payload)


def receive_step(conn, tok: dict, d: dict) -> dict:
    """{"record": "DHR-00002", "step": 2, "value": 10.01 | "result": "pass" | "text": "...", "equipment": "CAL-01"}:
    the result of one step of a lot in production, recorded when a person accepts it."""
    if not isinstance(d, dict):
        raise IntegrationError("send a JSON object")
    name = str(d.get("record") or "").strip()
    r = conn.execute("select * from prod_records where name = %s", (name,)).fetchone()
    if r is None:
        raise IntegrationError(f"there is no production record {name!r}")
    if r["status"] != "in_production":
        raise IntegrationError(f"{name} is {r['status'].replace('_', ' ')}: it takes no more step results")
    seq = d.get("step")
    s = conn.execute("select * from prod_steps where record_id = %s and seq = %s", (r["id"], seq)).fetchone() \
        if type(seq) is int else None
    if s is None:
        raise IntegrationError("step: the number of a step of this record")
    if s["done_by"] is not None:
        raise IntegrationError(f"step {seq} is recorded already")
    payload: dict = {"record": name, "step": seq, "name": s["name"], "kind": s["kind"], "note": _note(d)}
    if s["kind"] == "measure":
        payload["value"] = _number(d.get("value"), "value")
        payload["equipment"] = _gauge_code(conn, d.get("equipment"))
    elif s["kind"] == "check":
        if d.get("result") not in ("pass", "fail"):
            raise IntegrationError("result: pass or fail")
        payload["result"] = d["result"]
    else:
        text = str(d.get("text") or "").strip()
        if not text:
            raise IntegrationError("text: what to record")
        payload["text"] = text[:4000]
    return _inbox(conn, tok, "production_step", name, payload)


# ---------------------------------------------------------------- the inbox

def inbox(conn, status: str = "pending") -> list[dict]:
    cond = "" if status == "all" else "where i.status = %(s)s"
    sql = ("select i.id, i.kind, i.target, i.status, i.received_at, i.decided_by, i.decided_at, i.note, i.result, "  # noqa: S608 - cond is one of two fixed strings
           "t.name as sender, i.payload from integration_inbox i join integration_tokens t on t.id = i.token_id "
           + cond + " order by i.id desc limit 500")
    return [_iso(r) for r in conn.execute(sql, {"s": status})]


def item(conn, iid: int) -> dict:
    r = conn.execute("select i.*, t.name as sender from integration_inbox i join integration_tokens t on "
                     "t.id = i.token_id where i.id = %s", (iid,)).fetchone()
    if r is None:
        raise KeyError(iid)
    out = _iso(r)
    p = r["payload"]
    if r["kind"] == "measurements":
        ins = conn.execute("select id, status from iqc_inspections where name = %s", (p["inspection"],)).fetchone()
        out["link"] = f"/quality/iqc/{ins['id']}"
        now = {(x["sample"], x["characteristic"]): float(x["value"]) for x in conn.execute(
            "select sample, characteristic, value from iqc_readings where inspection_id = %s and value is not null",
            (ins["id"],))}
        out["replaces"] = [dict(x, before=now[(x["sample"], x["characteristic"])]) for x in p["readings"]
                           if (x["sample"], x["characteristic"]) in now and now[(x["sample"], x["characteristic"])]
                           != x["value"]]
        out["target_status"] = ins["status"]
    else:
        rec = conn.execute("select id, status from prod_records where name = %s", (p["record"],)).fetchone()
        out["link"] = f"/quality/production/{rec['id']}"
        out["target_status"] = rec["status"]
    return out


def _pending(conn, iid: int) -> dict:
    r = conn.execute("select * from integration_inbox where id = %s for update", (iid,)).fetchone()
    if r is None:
        raise KeyError(iid)
    if r["status"] != "pending":
        raise IntegrationError(f"it was {r['status']} by {r['decided_by']}")
    return r


def _gauge(conn, code: str | None, today: dt.date) -> dict | None:
    if not code:
        return None
    g = conn.execute("select * from gauges where code = %s for share", (code,)).fetchone()
    ok, why = CALR.usable(g, today)
    if not ok:
        raise IntegrationError(f"{why}: the readings cannot be accepted with it")
    return g


def accept(conn, user: dict, iid: int, password: str, *, today: dt.date) -> dict:
    """Write what the machine sent, signed by the person who accepts it."""
    Q.check_signer(conn, user, password)
    with conn.transaction():
        r = _pending(conn, iid)
        p = r["payload"]
        sender = conn.execute("select name from integration_tokens where id = %s", (r["token_id"],)).fetchone()["name"]
        if r["kind"] == "measurements":
            result = _accept_measurements(conn, user, r, p, sender, today)
        else:
            rec = conn.execute("select id from prod_records where name = %s", (p["record"],)).fetchone()
            g = _gauge(conn, p.get("equipment"), today)
            data = {k: p[k] for k in ("value", "result", "text") if k in p}
            if g:
                data["gauge_id"] = g["id"]
            try:
                PRD.record_step(conn, user, rec["id"], p["step"], password, data, today=today)
            except PRD.ProdError as exc:
                raise IntegrationError(str(exc)) from exc
            PRD.log(conn, "record", rec["id"], user["email"], f"step {p['step']} from {sender}", f"inbox {iid}")
            result = f"step {p['step']} of {p['record']} recorded"
        conn.execute("update integration_inbox set status = 'accepted', decided_by = %s, decided_at = now(), "
                     "result = %s where id = %s", (user["email"], result, iid))
    return item(conn, iid)


def _accept_measurements(conn, user: dict, r: dict, p: dict, sender: str, today: dt.date) -> str:  # noqa: PLR0917
    ins = conn.execute("select * from iqc_inspections where name = %s for update", (p["inspection"],)).fetchone()
    if ins["status"] != "in_progress":
        raise IntegrationError(f"{ins['name']} is {ins['status'].replace('_', ' ')}: it takes no more readings")
    g = _gauge(conn, p.get("equipment"), today)
    chars = sorted({x["characteristic"] for x in p["readings"]})
    if g:
        named = {x["characteristic"]: x["gauge_code"] for x in conn.execute(
            "select characteristic, gauge_code from iqc_gauges where inspection_id = %s and gauge_id <> %s",
            (ins["id"], g["id"]))}
        clash = [c for c in chars if c in named]
        if clash:
            raise IntegrationError("; ".join(f"{c} is measured with {named[c]} in this inspection" for c in clash))
    now = dt.datetime.now(dt.UTC)
    for x in p["readings"]:
        conn.execute("update iqc_readings set value = %s, passed = null, entered_by = %s, entered_at = %s, "
                     "import_id = null, inbox_id = %s where inspection_id = %s and sample = %s and "
                     "characteristic = %s", (x["value"], user["email"], now, r["id"], ins["id"], x["sample"],
                                             x["characteristic"]))
    if g:
        for c in chars:
            I.set_gauge(conn, user["email"], ins["id"], c, g["id"], today=today)
    Q._sign(conn, user, f"Measurements from {sender} accepted ({len(p['readings'])} readings)", "integration_inbox",
            r["id"], ins["name"])
    I.log(conn, "inspection", ins["id"], user["email"], "accepted", f"{len(p['readings'])} readings from {sender}")
    return f"{len(p['readings'])} readings into {ins['name']}"


def reject(conn, email: str, iid: int, note: str) -> dict:
    note = str(note or "").strip()[:500]
    if not note:
        raise IntegrationError("say why it is rejected")
    with conn.transaction():
        _pending(conn, iid)
        conn.execute("update integration_inbox set status = 'rejected', decided_by = %s, decided_at = now(), note = %s "
                     "where id = %s", (email, note, iid))
    return item(conn, iid)


# ---------------------------------------------------------------- events

def events(conn, after: int = 0, limit: int = 100) -> dict:
    """Events after the one the caller saw last, oldest first; ``next`` is where to continue."""
    limit = max(1, min(int(limit), 500))
    rows = [_iso(r) for r in conn.execute("select * from hub_events where id > %s order by id limit %s",
                                          (max(0, int(after)), limit))]
    return {"events": rows, "next": rows[-1]["id"] if rows else max(0, int(after)), "more": len(rows) == limit}
