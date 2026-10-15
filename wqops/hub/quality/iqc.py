"""Incoming inspection and sampling, step 17b (ADR-0017; dee-qms PLAN-IQC, PLAN-SEVERITY).

The company keeps its sampling table and an inspection plan per item (frozen once enabled; a change is a new
version). An inspection of a lot looks up n, Ac and Re for the plan's AQL, the lot size and the supplier's inspection
level, makes the readings to enter, and is judged by code when the inspector signs. Someone else then releases or
rejects the lot. The result goes to ERPNext as a quality inspection draft that a person confirms (ADR-0008); a
rejected lot gets a nonconformance report. The switching rules suggest normal, tightened or reduced inspection; a
person confirms a switch with a reason.

Plain code: no AI, no network (tests/test_isolation.py). ERPNext is reached only through the drafts a person confirms.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math

from psycopg.types.json import Jsonb

from wqops.hub import drafts as D
from wqops.hub.ont import metrics as M
from wqops.hub.quality import approval as AP
from wqops.hub.quality import cal_rules as CALR
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import incoming as IN
from wqops.hub.quality import records as Q
from wqops.hub.quality import sampling as S

SETTINGS = {
    "plan_by_other": (True, "A plan is enabled by someone other than the person who drafted it"),
    "release_by_other": (True, "A lot is released or rejected by someone other than the inspector who signed it"),
    "unverified_reason": (True, "Releasing a lot sampled with an unchecked sampling table row needs a reason"),
    # the approved supplier list (17c)
    "asl_enforced": (True, "Once the approved supplier list has entries, lots from a supplier not approved for the "
                           "item cannot be inspected"),
    "asl_approve_by_other": (True, "A supplier is approved by someone other than the person who entered it"),
    # measuring equipment (17f)
    "gauge_required": (True, "Once measuring equipment is registered, each measured characteristic names the "
                             "equipment used, which must be in calibration when the inspector signs"),
    # production records (17i)
    "template_by_other": (True, "A production template is activated by someone who did not draft or edit it"),
    "production_training": (True, "An operator records a production step only after confirming reading the "
                                  "documents its template follows (when those documents need training)"),
}


class IqcError(ValueError):
    pass


def _iso(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: (float(v) if k == "aql" and v is not None else v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in row.items()}


def log(conn, kind: str, ref_id: int, email: str | None, action: str, note: str = "") -> None:  # noqa: PLR0917
    conn.execute("insert into iqc_log (kind, ref_id, email, action, note) values (%s, %s, %s, %s, %s)",
                 (kind, ref_id, email, action, (note or "")[:2000]))


def history(conn, kind: str, ref_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select at, email, action, note from iqc_log where kind = %s and "
                                          "ref_id = %s order by id", (kind, ref_id)).fetchall()]


# ---------------------------------------------------------------- settings

def settings(conn) -> dict:
    rows = conn.execute("select distinct on (key) key, value from iqc_settings order by key, id desc").fetchall()
    mine = {r["key"]: r["value"] for r in rows if r["key"] in SETTINGS}
    return {k: mine.get(k, d) for k, (d, _) in SETTINGS.items()}


def set_setting(conn, email: str, key: str, value) -> dict:
    if key not in SETTINGS:
        raise KeyError(key)
    if type(value) is not bool:
        raise IqcError(f"{SETTINGS[key][1]}: yes or no")
    with conn.transaction():
        row = conn.execute("insert into iqc_settings (key, value, email) values (%s, %s, %s) returning *",
                           (key, Jsonb(value), email)).fetchone()
        log(conn, "setting", row["id"], email, "changed", f"{key}: {'on' if value else 'off'}")
    return settings(conn)


# ---------------------------------------------------------------- the sampling table

def rows(conn, active_only: bool = False) -> list[dict]:
    used = {r["sampling_row_id"] for r in conn.execute("select distinct sampling_row_id from iqc_inspections")}
    out = []
    for r in conn.execute("select * from iqc_sampling_rows where active or not %s order by aql, level, lot_min, id",
                          (active_only,)).fetchall():
        out.append({**_iso(r), "used": r["id"] in used})
    return out


def _num(v, what: str) -> float | int:
    if isinstance(v, bool):
        raise IqcError(f"{what} is a number")
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise IqcError(f"{what} is a number") from exc
    if math.isnan(x) or math.isinf(x):
        raise IqcError(f"{what} is a number")
    return x


def _int(v, what: str) -> int:
    x = _num(v, what)
    if not x.is_integer():
        raise IqcError(f"{what} is a whole number")
    return int(x)


def add_row(conn, email: str, data: dict) -> dict:
    """A row of the sampling table; Re is Ac + 1. It may not overlap an active row of the same AQL and level."""
    r = {"aql": _num(data.get("aql"), "the AQL"), "level": data.get("level") or "normal",
         "lot_min": _int(data.get("lot_min"), "the smallest lot"),
         "lot_max": _int(data.get("lot_max"), "the largest lot"),
         "n": _int(data.get("n"), "n"), "ac": _int(data.get("ac"), "Ac")}
    r["re"] = r["ac"] + 1
    errs = S.check_row(r)
    if errs:
        raise IqcError("; ".join(errs))
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext('wqo-iqc-rows'))")
        clash = conn.execute("select id, lot_min, lot_max from iqc_sampling_rows where active and aql = %s and "
                             "level = %s and lot_min <= %s and lot_max >= %s", (r["aql"], r["level"], r["lot_max"],
                                                                               r["lot_min"])).fetchone()
        if clash:
            raise IqcError(f"it overlaps the row for lots {clash['lot_min']}-{clash['lot_max']}")
        row = conn.execute("insert into iqc_sampling_rows (aql, level, lot_min, lot_max, n, ac, re, created_by) "
                           "values (%(aql)s, %(level)s, %(lot_min)s, %(lot_max)s, %(n)s, %(ac)s, %(re)s, %(by)s) "
                           "returning *", {**r, "by": email}).fetchone()
        log(conn, "row", row["id"], email, "added",
            f"AQL {r['aql']:g} {r['level']}, lots {r['lot_min']}-{r['lot_max']}: n {r['n']}, Ac {r['ac']}")
    return _iso(row)


def verify_row(conn, email: str, row_id: int, source: str) -> dict:
    """Say the row was checked against the company's copy of the standard, and which one."""
    if not source.strip():
        raise IqcError("name what the row was checked against (the standard's title and edition)")
    with conn.transaction():
        row = conn.execute("select * from iqc_sampling_rows where id = %s for update", (row_id,)).fetchone()
        if row is None:
            raise KeyError(row_id)
        if row["verified_by"]:
            raise IqcError("it is already checked")
        row = conn.execute("update iqc_sampling_rows set source = %s, verified_by = %s, verified_at = now() where "
                           "id = %s returning *", (source.strip()[:300], email, row_id)).fetchone()
        log(conn, "row", row_id, email, "checked", source.strip())
    return _iso(row)


def archive_row(conn, email: str, row_id: int, active: bool) -> dict:
    with conn.transaction():
        row = conn.execute("select * from iqc_sampling_rows where id = %s for update", (row_id,)).fetchone()
        if row is None:
            raise KeyError(row_id)
        if row["active"] == active:
            raise IqcError("it is already " + ("in use" if active else "archived"))
        if active and conn.execute("select 1 from iqc_sampling_rows where active and aql = %s and level = %s and "
                                   "lot_min <= %s and lot_max >= %s", (row["aql"], row["level"], row["lot_max"],
                                                                       row["lot_min"])).fetchone():
            raise IqcError("an active row covers these lots: archive it first")
        row = conn.execute("update iqc_sampling_rows set active = %s where id = %s returning *",
                           (active, row_id)).fetchone()
        log(conn, "row", row_id, email, "restored" if active else "archived")
    return _iso(row)


# ---------------------------------------------------------------- inspection plans

def _chars(raw) -> list[dict]:
    """A draft's characteristics, checked; a draft may have none yet (enabling needs at least one)."""
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise IqcError("characteristics are a list")
    if not raw:
        return []
    out = []
    for c in raw:
        if not isinstance(c, dict):
            raise IqcError("each characteristic is described by its fields")
        x = {"name": str(c.get("name") or "").strip()[:100], "kind": c.get("kind"),
             "unit": str(c.get("unit") or "").strip()[:30], "method": str(c.get("method") or "").strip()[:300]}
        for lim in ("lsl", "usl"):
            v = c.get(lim)
            x[lim] = None if v in (None, "") else _num(v, f"{x['name'] or 'a characteristic'}: the limit")
        out.append(x)
    errs = S.check_characteristics(out)
    if errs:
        raise IqcError("; ".join(errs))
    return out


def plans(conn, item_code: str | None = None) -> list[dict]:
    return [_iso(r) for r in conn.execute("select * from iqc_plans where %s::text is null or item_code = %s "
                                          "order by item_code, version desc", (item_code, item_code)).fetchall()]


def plan(conn, plan_id: int) -> dict:
    row = conn.execute("select * from iqc_plans where id = %s", (plan_id,)).fetchone()
    if row is None:
        raise KeyError(plan_id)
    return row


def enabled_plan(conn, item_code: str) -> dict | None:
    return conn.execute("select * from iqc_plans where item_code = %s and status = 'enabled'",
                        (item_code,)).fetchone()


def new_plan(conn, email: str, item_code: str, aql, characteristics, note: str = "") -> dict:  # noqa: PLR0917
    item_code = str(item_code or "").strip()
    if not item_code:
        raise IqcError("which item is the plan for?")
    a, chars = _num(aql, "the AQL"), _chars(characteristics)
    if a <= 0:
        raise IqcError("the AQL is a number above 0")
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-iqc-plan:{item_code}",))
        if conn.execute("select 1 from iqc_plans where item_code = %s and status = 'draft'", (item_code,)).fetchone():
            raise IqcError(f"{item_code} already has a draft plan: change that one")
        v = conn.execute("select coalesce(max(version), 0) + 1 as v from iqc_plans where item_code = %s",
                         (item_code,)).fetchone()["v"]
        row = conn.execute("insert into iqc_plans (item_code, version, aql, characteristics, note, created_by) "
                           "values (%s, %s, %s, %s, %s, %s) returning *",
                           (item_code, v, a, Jsonb(chars), note.strip()[:1000], email)).fetchone()
        log(conn, "plan", row["id"], email, "drafted", f"{item_code} version {v}")
    return row


def update_plan(conn, email: str, plan_id: int, *, aql=None, characteristics=None, note: str | None = None) -> dict:
    p = plan(conn, plan_id)
    if p["status"] != "draft":
        raise IqcError(f"the plan is {p['status']}: make a new version to change it")
    a = p["aql"] if aql is None else _num(aql, "the AQL")
    chars = p["characteristics"] if characteristics is None else _chars(characteristics)
    if float(a) <= 0:
        raise IqcError("the AQL is a number above 0")
    with conn.transaction():
        row = conn.execute("update iqc_plans set aql = %s, characteristics = %s, note = %s, updated_at = now() "
                           "where id = %s and status = 'draft' returning *",
                           (a, Jsonb(chars), p["note"] if note is None else note.strip()[:1000], plan_id)).fetchone()
        if row is None:
            raise IqcError("the plan changed meanwhile: open it again")
        log(conn, "plan", plan_id, email, "changed")
    return row


def fingerprint(p: dict) -> str:
    body = {"item_code": p["item_code"], "version": p["version"], "aql": float(p["aql"]),
            "characteristics": p["characteristics"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def enable_plan(conn, user: dict, plan_id: int, password: str, seen: str | None = None) -> dict:
    """Put a draft plan in use, signed; the plan it replaces is retired. The sampling table must cover its AQL.
    ``seen``: the plan's last change as the signer saw it; if it changed since, nothing is enabled."""
    p = plan(conn, plan_id)
    if p["status"] != "draft":
        raise IqcError(f"the plan is {p['status']}")
    errs = S.check_characteristics(p["characteristics"])
    if errs:
        raise IqcError("; ".join(errs))
    if settings(conn)["plan_by_other"] and p["created_by"] == user["email"]:
        raise PermissionError("someone other than the person who drafted the plan enables it")
    if not conn.execute("select 1 from iqc_sampling_rows where active and aql = %s and level = 'normal'",
                        (p["aql"],)).fetchone():
        raise IqcError(f"the sampling table has no normal rows for AQL {float(p['aql']):g}: add them first")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-iqc-plan:{p['item_code']}",))
        now = conn.execute("select * from iqc_plans where id = %s for update", (plan_id,)).fetchone()
        if now["status"] != "draft" or now["updated_at"] != p["updated_at"] or (
                seen and seen != now["updated_at"].isoformat()):
            raise IqcError("the plan changed since you opened it: look at it again before enabling")
        p = now
        old = enabled_plan(conn, p["item_code"])
        if old:
            conn.execute("update iqc_plans set status = 'retired', retired_at = now() where id = %s", (old["id"],))
            log(conn, "plan", old["id"], user["email"], "retired", f"replaced by version {p['version']}")
        row = conn.execute("update iqc_plans set status = 'enabled', fingerprint = %s, enabled_by = %s, "
                           "enabled_at = now() where id = %s and status = 'draft' returning *",
                           (fingerprint(p), user["email"], plan_id)).fetchone()
        if row is None:
            raise IqcError("the plan changed meanwhile: open it again")
        Q._sign(conn, user, "Inspection plan enabled", "iqc_plan", plan_id, f"{p['item_code']} v{p['version']}")
        log(conn, "plan", plan_id, user["email"], "enabled")
    return row


def discard_plan(conn, email: str, plan_id: int) -> dict:
    with conn.transaction():
        row = conn.execute("update iqc_plans set status = 'discarded' where id = %s and status = 'draft' returning *",
                           (plan_id,)).fetchone()
        if row is None:
            raise IqcError("only a draft plan can be discarded")
        log(conn, "plan", plan_id, email, "discarded")
    return row


def new_version(conn, email: str, plan_id: int) -> dict:
    p = plan(conn, plan_id)
    if p["status"] not in ("enabled", "retired"):
        raise IqcError("a new version is made from a plan that was in use")
    return new_plan(conn, email, p["item_code"], p["aql"], p["characteristics"], p["note"])


# ---------------------------------------------------------------- inspection levels and switching

def switch_rules(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("select * from iqc_switch_rules order by sort, id").fetchall()]


def save_rule(conn, email: str, rule_id: int | None, data: dict) -> list[dict]:
    """Add a switching rule, or change or switch off one (rules are never deleted)."""
    r = {"from_level": data.get("from_level"), "to_level": data.get("to_level"), "condition": data.get("condition"),
         "n": data.get("n"), "k": data.get("k"), "active": data.get("active", True)}
    if r["condition"] == "any_rejected":
        r["n"] = r["k"] = None
    elif r["condition"] == "consecutive_accepted":
        r["k"] = None
    errs = S.check_rule(r) + ([] if isinstance(r["active"], bool) else ["active is yes or no"])
    if errs:
        raise IqcError("; ".join(errs))
    with conn.transaction():
        if rule_id is None:
            row = conn.execute("insert into iqc_switch_rules (from_level, to_level, condition, n, k, active, sort) "
                               "values (%(from_level)s, %(to_level)s, %(condition)s, %(n)s, %(k)s, %(active)s, "
                               "(select coalesce(max(sort), 0) + 1 from iqc_switch_rules)) returning *", r).fetchone()
        else:
            row = conn.execute("update iqc_switch_rules set from_level = %(from_level)s, to_level = %(to_level)s, "
                               "condition = %(condition)s, n = %(n)s, k = %(k)s, active = %(active)s where id = %(id)s "
                               "returning *", {**r, "id": rule_id}).fetchone()
            if row is None:
                raise KeyError(rule_id)
        log(conn, "rule", row["id"], email, "added" if rule_id is None else "changed",
            f"{r['from_level']} to {r['to_level']}: {r['condition']} N={r['n']} K={r['k']}"
            + ("" if r["active"] else " (off)"))
    return switch_rules(conn)


def level_of(conn, supplier: str | None, item_code: str) -> dict:
    """The inspection level for a supplier's item now: the latest switch, or normal."""
    if not supplier:
        return {"level": "normal", "since": None}
    r = conn.execute("select to_level, at from iqc_level_switches where supplier = %s and item_code = %s "
                     "order by id desc limit 1", (supplier, item_code)).fetchone()
    return {"level": r["to_level"], "since": r["at"]} if r else {"level": "normal", "since": None}


def results_at_level(conn, supplier: str, item_code: str) -> tuple[str, list[str]]:
    """The current level and the lots decided at it since the last switch, oldest first."""
    lv = level_of(conn, supplier, item_code)
    rs = conn.execute("select result from iqc_inspections where supplier = %s and item_code = %s and level = %s and "
                      "status in ('released', 'rejected') and (%s::timestamptz is null or decided_at >= %s) "
                      "order by decided_at, id",
                      (supplier, item_code, lv["level"], lv["since"], lv["since"])).fetchall()
    return lv["level"], [r["result"] for r in rs]


def suggestion(conn, supplier: str | None, item_code: str) -> dict:
    if not supplier:
        return {"level": "normal", "lots": [], "suggestion": None}
    level, results = results_at_level(conn, supplier, item_code)
    return {"level": level, "lots": results, "suggestion": S.suggest(switch_rules(conn), level, results)}


def levels(conn) -> list[dict]:
    """Every supplier's item inspected or switched, with its level and what the rules suggest."""
    pairs = {(r["supplier"], r["item_code"]) for r in conn.execute(
        "select distinct supplier, item_code from iqc_inspections where supplier is not null and status <> 'void' "
        "union select distinct supplier, item_code from iqc_level_switches").fetchall()}
    out = []
    for sup, item in sorted(pairs):
        s = suggestion(conn, sup, item)
        out.append({"supplier": sup, "item_code": item, **s,
                    "since": _iso({"x": level_of(conn, sup, item)["since"]})["x"]})
    return out


def switch(conn, user: dict, supplier: str, item_code: str, to_level: str, reason: str) -> dict:  # noqa: PLR0917
    """A person moves a supplier's item to another inspection level, with a reason; the rules' suggestion at the
    time and the lots behind it are kept with the switch."""
    if not supplier or not item_code:
        raise IqcError("say which supplier's item")
    if to_level not in S.LEVELS:
        raise IqcError("the level is normal, tightened or reduced")
    if not reason.strip():
        raise IqcError("give the reason for the switch")
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-iqc-level:{supplier}:{item_code}",))
        s = suggestion(conn, supplier, item_code)
        if to_level == s["level"]:
            raise IqcError(f"it is already at {to_level} inspection")
        if (s["level"], to_level) == ("reduced", "tightened"):
            raise IqcError("reduced cannot go straight to tightened: go back to normal first")
        p = enabled_plan(conn, item_code)
        if p and not conn.execute("select 1 from iqc_sampling_rows where active and aql = %s and level = %s",
                                  (p["aql"], to_level)).fetchone():
            raise IqcError(f"the sampling table has no {to_level} rows for AQL {float(p['aql']):g}, so lots could "
                           "not be sampled: add them first")
        sug = s["suggestion"]
        row = conn.execute(
            "insert into iqc_level_switches (supplier, item_code, from_level, to_level, reason, suggestion, history, "
            "email) values (%s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (supplier, item_code, s["level"], to_level, reason.strip()[:1000],
             f"{sug['to']}: {sug['reason']}" if sug else None,
             " ".join("A" if r == "accept" else "R" for r in s["lots"]), user["email"])).fetchone()
    return _iso(row)


def switches(conn, supplier: str | None = None, item_code: str | None = None) -> list[dict]:
    return [_iso(r) for r in conn.execute("select * from iqc_level_switches where %s::text is null or "
                                          "(supplier = %s and item_code = %s) order by id desc limit 500",
                                          (supplier, supplier, item_code)).fetchall()]


# ---------------------------------------------------------------- inspections

def _receipt_line(conn, receipt: str, item_code: str) -> dict | None:
    r = conn.execute("select props from ont_objects where type = 'PurchaseReceipt' and key = %s", (receipt,)).fetchone()
    if r is None:
        return None
    # the lot in stock units (a line of 10 boxes of 100 is a lot of 1000); the purchase quantity if there is no other
    qty = sum(float(ln.get("stock_qty") if ln.get("stock_qty") is not None else ln.get("qty") or 0)
              for ln in r["props"].get("lines", []) if ln.get("item_code") == item_code)
    link = conn.execute("select dst_key from ont_links where src_type = 'PurchaseReceipt' and src_key = %s and "
                        "type = 'supplier'", (receipt,)).fetchone()
    return {"qty": qty, "supplier": link["dst_key"] if link else None} if qty else None


def awaiting(conn) -> list[dict]:
    """Receipt lines waiting for incoming inspection, less those already being inspected here, with the plan."""
    started = {(r["receipt"], r["item_code"]) for r in conn.execute(
        "select receipt, item_code from iqc_inspections where receipt is not null and status <> 'void'")}
    has_plan = {r["item_code"] for r in conn.execute("select item_code from iqc_plans where status = 'enabled'")}
    return [{**x, "plan": x["item_code"] in has_plan} for x in IN.awaiting(conn)
            if (x["receipt"], x["item_code"]) not in started]


def _receipt_lot(conn, receipt: str, item_code: str, supplier, lot_qty) -> tuple[str | None, float]:
    """A lot on a receipt is the receipt's: its supplier and quantity, not what is typed."""
    line = _receipt_line(conn, receipt, item_code)
    if line is None:
        raise IqcError(f"receipt {receipt} has no {item_code}")
    if supplier and supplier != line["supplier"]:
        raise IqcError(f"receipt {receipt} is from {line['supplier']}, not {supplier}")
    if lot_qty not in (None, "") and _num(lot_qty, "the lot size") != line["qty"]:
        raise IqcError(f"receipt {receipt} has {line['qty']:g} of {item_code}")
    if not float(line["qty"]).is_integer():
        raise IqcError(f"receipt {receipt} has {line['qty']:g} of {item_code}, not a whole number of pieces: "
                       "inspect it as a lot not on a receipt, in pieces")
    if conn.execute("select 1 from iqc_inspections where receipt = %s and item_code = %s and status <> 'void'",
                    (receipt, item_code)).fetchone():
        raise IqcError(f"{item_code} on {receipt} is already being inspected")
    return line["supplier"], line["qty"]


def start(conn, email: str, item_code: str, lot_qty=None, *, receipt: str | None = None,
          supplier: str | None = None, lot_no: str = "", today: dt.date | None = None) -> dict:
    """Begin the inspection of a lot: n, Ac and Re from the sampling table for the plan's AQL, the lot size and the
    supplier's inspection level; one reading per sample unit and characteristic."""
    item_code = str(item_code or "").strip()
    p = enabled_plan(conn, item_code)
    if p is None:
        raise IqcError(f"{item_code or 'the item'} has no inspection plan in use: enable one first")
    if receipt:
        supplier, lot_qty = _receipt_lot(conn, receipt, item_code, supplier, lot_qty)
    elif not supplier or supplier not in {x["key"] for x in suppliers(conn)}:
        # the supplier decides the inspection level, so it must be one ERPNext knows
        raise IqcError("choose the supplier from the list (a supplier in ERPNext)")
    qty = _int(lot_qty, "the lot size")
    if qty < 1:
        raise IqcError("the lot size is at least 1")
    standing = None
    entries = asl_entries(conn)
    if settings(conn)["asl_enforced"] and entries:      # the list is in use once it has entries
        st = AP.standing(entries, supplier, item_code, today or dt.datetime.now(dt.UTC).date())
        if st["outcome"] == "block":
            raise IqcError(f"{st['why']}: approve the supplier first (Approved suppliers)")
        standing = st["why"] if st["outcome"] == "flag" else "approved"
    level = level_of(conn, supplier, item_code)["level"]
    try:
        row = S.lookup(rows(conn, active_only=True), float(p["aql"]), level, qty)
    except S.SamplingError as exc:
        raise IqcError(str(exc)) from exc
    sp = S.plan_for(row, qty)
    with conn.transaction():
        if receipt:
            conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-iqc-line:{receipt}:{item_code}",))
            if conn.execute("select 1 from iqc_inspections where receipt = %s and item_code = %s and "
                            "status <> 'void'", (receipt, item_code)).fetchone():
                raise IqcError(f"{item_code} on {receipt} is already being inspected")
        name = Q._next_name(conn, "iqc_inspections", "IQC")
        ins = conn.execute(
            "insert into iqc_inspections (name, plan_id, item_code, receipt, supplier, lot_no, lot_qty, level, "
            "sampling_row_id, n, ac, re, unverified, supplier_standing, created_by) values (%s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (name, p["id"], item_code, receipt, supplier, str(lot_no or "").strip()[:100], qty, level, row["id"],
             sp["n"], sp["ac"], sp["re"], row["verified_by"] is None, standing, email)).fetchone()
        with conn.cursor() as cur:
            cur.executemany("insert into iqc_readings (inspection_id, sample, characteristic) values (%s, %s, %s)",
                            [(ins["id"], i, c["name"]) for i in range(1, sp["n"] + 1) for c in p["characteristics"]])
        note = (f"{level} inspection of {qty}: n {sp['n']}, Ac {sp['ac']}, Re {sp['re']}"
                + (" (every piece)" if sp["all"] else "") + ("; the sampling table row is not checked"
                                                            if row["verified_by"] is None else "")
                + (f"; {standing}" if standing and standing != "approved" else ""))
        if lot_no and supplier and conn.execute(
                "select 1 from iqc_inspections where supplier = %s and lot_no = %s and status <> 'void' and id <> %s",
                (supplier, str(lot_no).strip(), ins["id"])).fetchone():
            note += f"; lot {lot_no} from {supplier} has another inspection"
        log(conn, "inspection", ins["id"], email, "started", note)
    return ins


def get(conn, ins_id: int) -> dict:
    row = conn.execute("select * from iqc_inspections where id = %s", (ins_id,)).fetchone()
    if row is None:
        raise KeyError(ins_id)
    return row


def readings(conn, ins_id: int) -> list[dict]:
    return [{**_iso(r), "value": float(r["value"]) if r["value"] is not None else None} for r in conn.execute(
        "select * from iqc_readings where inspection_id = %s order by sample, id", (ins_id,)).fetchall()]


def enter(conn, email: str, ins_id: int, values: list[dict]) -> int:
    """Readings for the inspection in progress: a number for a measured characteristic, pass or fail for an
    attribute; empty clears one."""
    ins = get(conn, ins_id)
    if ins["status"] != "in_progress":
        raise IqcError(f"the inspection is {ins['status'].replace('_', ' ')}: readings cannot change")
    kinds = {c["name"]: c["kind"] for c in plan(conn, ins["plan_id"])["characteristics"]}
    if not isinstance(values, list):
        raise IqcError("readings are a list")
    n = 0
    with conn.transaction():
        st = conn.execute("select status from iqc_inspections where id = %s for update", (ins_id,)).fetchone()
        if st["status"] != "in_progress":
            raise IqcError(f"the inspection is {st['status'].replace('_', ' ')}: readings cannot change")
        for v in values:
            if not isinstance(v, dict) or v.get("characteristic") not in kinds or type(v.get("sample")) is not int:
                raise IqcError("each reading names its sample and characteristic")
            kind = kinds[v["characteristic"]]
            val = passed = None
            if kind == "measured" and v.get("value") not in (None, ""):
                val = _num(v["value"], f"{v['characteristic']}, sample {v['sample']}")
            if kind == "attribute" and v.get("passed") is not None:
                if not isinstance(v["passed"], bool):
                    raise IqcError(f"{v['characteristic']}, sample {v['sample']}: pass or fail")
                passed = v["passed"]
            done = val is not None or passed is not None
            r = conn.execute("update iqc_readings set value = %s, passed = %s, entered_by = %s, entered_at = %s "
                             "where inspection_id = %s and sample = %s and characteristic = %s returning id",
                             (val, passed, email if done else None, dt.datetime.now(dt.UTC) if done else None,
                              ins_id, v["sample"], v["characteristic"])).fetchone()
            if r is None:
                raise IqcError(f"there is no sample {v['sample']} for {v['characteristic']}")
            n += 1
    return n


def _gauges(conn, ins_id: int) -> dict[str, dict]:
    return {r["characteristic"]: dict(r) for r in conn.execute("select * from iqc_gauges where inspection_id = %s",
                                                               (ins_id,))}


def set_gauge(conn, email: str, ins_id: int, characteristic: str, gauge_id: int | None, *,
              today: dt.date) -> dict:
    """Name the equipment a measured characteristic is measured with; it must be in calibration today."""
    ins = get(conn, ins_id)
    if ins["status"] != "in_progress":
        raise IqcError("the inspection is signed: the equipment it used is fixed")
    kinds = {c["name"]: c["kind"] for c in plan(conn, ins["plan_id"])["characteristics"]}
    if kinds.get(characteristic) != "measured":
        raise IqcError("equipment is named for a measured characteristic")
    with conn.transaction():
        if conn.execute("select status from iqc_inspections where id = %s for update",
                        (ins_id,)).fetchone()["status"] != "in_progress":
            raise IqcError("the inspection is signed: the equipment it used is fixed")
        if gauge_id is None:
            conn.execute("delete from iqc_gauges where inspection_id = %s and characteristic = %s",
                         (ins_id, characteristic))
        else:
            g = CAL.get(conn, gauge_id)
            ok, why = CALR.usable(g, today)
            if not ok:
                raise IqcError(f"{why}: it cannot be used")
            conn.execute("insert into iqc_gauges (inspection_id, characteristic, gauge_id, gauge_code, next_due) "
                         "values (%s, %s, %s, %s, %s) on conflict (inspection_id, characteristic) do update set "
                         "gauge_id = excluded.gauge_id, gauge_code = excluded.gauge_code, next_due = "
                         "excluded.next_due", (ins_id, characteristic, g["id"], g["code"], g["next_due"]))
        log(conn, "inspection", ins_id, email, "equipment", f"{characteristic}: "
            + (CAL.get(conn, gauge_id)["code"] if gauge_id else "none"))
    return _gauges(conn, ins_id)


def _check_gauges(conn, ins: dict, chars: list[dict], today: dt.date) -> None:
    """At signing: every measured characteristic names equipment that is in calibration today (a setting; only
    once equipment is registered). What was used, and its due date then, stays with the inspection."""
    used = _gauges(conn, ins["id"])
    if settings(conn)["gauge_required"] and CAL.in_use(conn):
        missing = [c["name"] for c in chars if c["kind"] == "measured" and c["name"] not in used]
        if missing:
            raise IqcError("name the equipment used for: " + ", ".join(missing))
    # equipment that is named is checked whatever the setting
    for ch, row in used.items():
        g = CAL.get(conn, row["gauge_id"])
        ok, why = CALR.usable(g, today)
        if not ok:
            raise IqcError(f"{ch}: {why}; measure with equipment in calibration")
        conn.execute("update iqc_gauges set next_due = %s, gauge_code = %s where inspection_id = %s and "
                     "characteristic = %s", (g["next_due"], g["code"], ins["id"], ch))


def sign(conn, user: dict, ins_id: int, password: str, *, today: dt.date | None = None) -> dict:
    """The inspector signs; the lot is judged by code from the readings."""
    ins = get(conn, ins_id)
    if ins["status"] != "in_progress":
        raise IqcError(f"the inspection is {ins['status'].replace('_', ' ')}")
    chars = plan(conn, ins["plan_id"])["characteristics"]
    Q.check_signer(conn, user, password)
    with conn.transaction():
        # locked, so no reading changes between judging and signing
        if conn.execute("select status from iqc_inspections where id = %s for update",
                        (ins_id,)).fetchone()["status"] != "in_progress":
            raise IqcError("the inspection changed meanwhile: open it again")
        try:
            j = S.judge(chars, readings(conn, ins_id), ins["n"], ins["ac"], ins["re"])
        except S.SamplingError as exc:
            raise IqcError(str(exc)) from exc
        _check_gauges(conn, ins, chars, today or dt.datetime.now(dt.UTC).date())
        row = conn.execute("update iqc_inspections set status = 'judged', result = %s, defectives = %s, "
                           "signed_by = %s, signed_at = now() where id = %s and status = 'in_progress' returning *",
                           (j["result"], j["defectives"], user["email"], ins_id)).fetchone()
        if row is None:
            raise IqcError("the inspection changed meanwhile: open it again")
        Q._sign(conn, user, "Incoming inspection signed", "iqc", ins_id, ins["name"])
        log(conn, "inspection", ins_id, user["email"], "signed",
            f"{j['defectives']} of {ins['n']} sample units failed (Ac {ins['ac']}, Re {ins['re']}): {j['result']}")
    return row


def decide(conn, user: dict, ins_id: int, password: str, note: str = "", *, today: dt.date) -> dict:
    """Release an accepted lot or reject a rejected one, signed by someone other than the inspector (a setting).
    The result is drafted for ERPNext; a rejected lot gets a nonconformance report."""
    ins = get(conn, ins_id)
    if ins["status"] != "judged":
        raise IqcError("the inspection is not signed yet" if ins["status"] == "in_progress"
                       else f"the inspection is {ins['status']}")
    st = settings(conn)
    if st["release_by_other"] and ins["signed_by"] == user["email"]:
        raise PermissionError("someone other than the inspector who signed releases or rejects the lot")
    accept = ins["result"] == "accept"
    if accept and ins["unverified"] and st["unverified_reason"] and not note.strip():
        raise IqcError("the sampling table row used is not checked against its source: give the reason to release "
                       "anyway")
    Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute("update iqc_inspections set status = %s, decided_by = %s, decided_at = now(), "
                           "decision_note = %s where id = %s and status = 'judged' returning *",
                           ("released" if accept else "rejected", user["email"], note.strip()[:1000],
                            ins_id)).fetchone()
        if row is None:
            raise IqcError("the inspection changed meanwhile: open it again")
        Q._sign(conn, user, "Lot released" if accept else "Lot rejected", "iqc", ins_id, ins["name"])
        log(conn, "inspection", ins_id, user["email"], "released" if accept else "rejected", note.strip())
        what = (f"{ins['name']}: {ins['defectives']} of {ins['n']} sample units failed (Ac {ins['ac']}, "
                f"Re {ins['re']}, {ins['level']} inspection, lot of {ins['lot_qty']})")
        ncr = None
        if not accept:
            chars = {c["name"]: c for c in plan(conn, ins["plan_id"])["characteristics"]}
            bad = [f"sample {r['sample']} {r['characteristic']}" for r in readings(conn, ins_id)
                   if S.conforms(chars[r["characteristic"]], r["value"], r["passed"]) is False]
            ncr = Q.create_ncr(conn, user["email"], title=f"Rejected {ins['item_code']} ({ins['name']})",
                               description=f"Incoming inspection {what}. Failed: {', '.join(bad[:20])}."
                               + (f" Lot {ins['lot_no']}." if ins["lot_no"] else ""),
                               item_code=ins["item_code"], receipt=ins["receipt"], supplier=ins["supplier"],
                               quantity=ins["lot_qty"])
            conn.execute("update iqc_inspections set ncr_id = %s where id = %s", (ncr["id"], ins_id))
        draft = None
        if ins["receipt"]:
            draft = D.propose(conn, user, "Quality Inspection", {
                "inspection_type": "Incoming", "reference_type": "Purchase Receipt", "reference_name": ins["receipt"],
                "item_code": ins["item_code"], "sample_size": ins["n"], "report_date": str(today),
                "status": "Accepted" if accept else "Rejected",
                "remarks": f"WenQuest Ops {what}; signed by {ins['signed_by']}, "
                           f"{'released' if accept else 'rejected'} by {user['email']}."},
                summary=f"Incoming inspection {ins['name']}: {ins['item_code']} {'accepted' if accept else 'rejected'}")
            conn.execute("update iqc_inspections set draft_id = %s where id = %s", (draft["id"], ins_id))
    return get(conn, ins_id)


def void(conn, email: str, ins_id: int, reason: str) -> dict:
    """An inspection started by mistake is voided with a reason, before it is signed. A signed one is released or
    rejected, so a rejected lot is never sampled again to get another result."""
    if not reason.strip():
        raise IqcError("give the reason")
    with conn.transaction():
        row = conn.execute("update iqc_inspections set status = 'void', void_reason = %s, decided_by = %s, "
                           "decided_at = now() where id = %s and status = 'in_progress' returning *",
                           (reason.strip()[:1000], email, ins_id)).fetchone()
        if row is None:
            ins = get(conn, ins_id)
            raise IqcError(f"a {ins['status'].replace('_', ' ')} inspection cannot be voided: once signed, the "
                           "lot is released or rejected")
        log(conn, "inspection", ins_id, email, "voided", reason.strip())
    return row


def listing(conn, status: str = "open") -> list[dict]:
    where = {"open": "status in ('in_progress', 'judged')", "all": "true", "void": "status = 'void'",
             "done": "status in ('released', 'rejected')"}.get(status, "true")
    return [_iso(r) for r in conn.execute(f"select * from iqc_inspections where {where} "  # noqa: S608 - fixed text
                                          "order by id desc limit 500").fetchall()]


def view(conn, ins_id: int, today: dt.date | None = None) -> dict:
    ins = get(conn, ins_id)
    p = plan(conn, ins["plan_id"])
    row = conn.execute("select * from iqc_sampling_rows where id = %s", (ins["sampling_row_id"],)).fetchone()
    rd = readings(conn, ins_id)
    chars = {c["name"]: c for c in p["characteristics"]}
    for r in rd:
        r["conforms"] = S.conforms(chars[r["characteristic"]], r["value"], r["passed"])
    draft = conn.execute("select id, status, erp_name from erp_drafts where id = %s",
                         (ins["draft_id"],)).fetchone() if ins["draft_id"] else None
    ncr = conn.execute("select id, name, status from ncr_records where id = %s",
                       (ins["ncr_id"],)).fetchone() if ins["ncr_id"] else None
    return {**_iso(ins), "plan": _iso(p), "sampling_row": _iso(row), "readings": rd,
            "gauges": {k: _iso(v) for k, v in _gauges(conn, ins_id).items()},
            "gauge_choices": [_iso(g) for g in CAL.usable_gauges(conn, today or dt.datetime.now(dt.UTC).date())]
            if ins["status"] == "in_progress" else [],
            "entered": sum(r["entered_by"] is not None for r in rd), "draft": draft, "ncr": ncr,
            "history": history(conn, "inspection", ins_id), "signatures": Q.signatures(conn, "iqc", ins_id),
            "level_now": suggestion(conn, ins["supplier"], ins["item_code"]) if ins["supplier"] else None}


def receipt_supplier(conn, receipt: str) -> str | None:
    r = conn.execute("select dst_key from ont_links where src_type = 'PurchaseReceipt' and src_key = %s and "
                     "type = 'supplier'", (receipt,)).fetchone()
    return r["dst_key"] if r else None


def items(conn) -> list[dict]:
    """Items there are, for choosing what a plan is for."""
    return [{"item_code": o["key"], "name": o["props"].get("item_name") or o["key"],
             "inspect": bool(o["props"].get("inspection_required"))} for o in M._objs(conn, "Item")]


def suppliers(conn) -> list[dict]:
    """Suppliers ERPNext knows: its supplier records and the suppliers of its purchase receipts."""
    names = {o["key"]: o["props"].get("supplier_name") or o["key"] for o in M._objs(conn, "Supplier")}
    for r in conn.execute("select distinct dst_key from ont_links where src_type = 'PurchaseReceipt' and "
                          "type = 'supplier'"):
        names.setdefault(r["dst_key"], r["dst_key"])
    return [{"key": k, "name": v} for k, v in sorted(names.items(), key=lambda x: x[1])]


def asl_entries(conn) -> list[dict]:
    """The approved supplier list as the judgement reads it (wqops/hub/quality/approval.py)."""
    return [dict(r) for r in conn.execute("select * from asl_entries order by id").fetchall()]
