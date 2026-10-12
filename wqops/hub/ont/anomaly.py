"""Anomalies (ADR-0007 item 5): rules find problems in the objects; each problem has a life cycle.

Life cycle: open -> ack (seen) -> doing (being handled) -> resolved (the condition went away for two runs in a row)
or closed (by a person). One active anomaly per rule and subject; a higher severity is logged as escalated.
Rules only read the objects. Life cycle adapted from freecad-ai-parts factory/digital/hub/ont/anomaly.py (Round 17B).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from psycopg.types.json import Jsonb

from wqops.hub import permissions as P
from wqops.hub.ont import metrics as M

RULES_FILE = Path(__file__).resolve().parents[2] / "ontology" / "rules" / "anomalies.yaml"
SEVERITY = {"info": 0, "warn": 1, "critical": 2}
ACTIVE = ("open", "ack", "doing")
MISSES_TO_RESOLVE = 2
CLOSED_PO = ("Completed", "Closed", "Cancelled", "To Bill", "On Hold")


@dataclass
class Finding:
    subject: tuple[str, str]
    title: str
    detail: str
    severity: str
    vals: dict = field(default_factory=dict)
    related: list[tuple[str, str]] = field(default_factory=list)


def load_rules(path: Path = RULES_FILE) -> dict[str, dict]:
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]
    for rid, r in rules.items():
        missing = [k for k in ("name", "severity", "view", "owner", "hint") if k not in r]
        if missing or r["severity"] not in SEVERITY or r["view"] not in P.PERMISSIONS or rid not in DETECTORS:
            raise ValueError(f"rule {rid}: check name, severity, view, owner, hint and that its detector exists")
    return rules


def _d(v) -> dt.date | None:
    return M._d(v)


def _open_orders(conn):
    for o in M._objs(conn, "SalesOrder"):
        if M._submitted(o["props"]) and o["props"].get("status") in M.OPEN_SO:
            yield o


def order_late(conn, rule: dict, today: dt.date) -> list[Finding]:
    out = []
    for o in _open_orders(conn):
        due = _d(o["props"].get("delivery_date"))
        if due and due < today:
            late = (today - due).days
            sev = "critical" if late > rule.get("critical_after_days", 7) else rule["severity"]
            out.append(
                Finding(
                    ("SalesOrder", o["key"]),
                    f"{o['title']} is {late} days late",
                    f"Delivery date {due}; {o['props'].get('per_delivered', 0):g}% delivered.",
                    sev,
                    {"days_late": late, "delivery_date": str(due)},
                )
            )
    return out


def order_at_risk(conn, rule: dict, today: dt.date) -> list[Finding]:
    short = {x["item"]: x for x in M.shortages(conn)["items"]}
    out = []
    for o in _open_orders(conn):
        due = _d(o["props"].get("delivery_date"))
        if not due or not today <= due <= today + dt.timedelta(days=rule.get("within_days", 7)):
            continue
        items = sorted(
            {
                ln["item_code"]
                for ln in o["props"].get("lines", [])
                if ln.get("item_code") in short and (ln.get("qty") or 0) > (ln.get("delivered_qty") or 0)
            }
        )
        if items:
            out.append(
                Finding(
                    ("SalesOrder", o["key"]),
                    f"{o['title']} is due {due} with items short",
                    "Short: " + ", ".join(f"{i} ({short[i]['short']:g})" for i in items),
                    rule["severity"],
                    {"delivery_date": str(due), "short_items": items},
                    [("Item", i) for i in items],
                )
            )
    return out


def item_short(conn, rule: dict, today: dt.date) -> list[Finding]:
    return [
        Finding(
            ("Item", x["item"]),
            f"{x['title']} is short by {x['short']:g}",
            f"On hand {x['on_hand']:g}, open orders need {x['demand']:g}.",
            rule["severity"],
            {"on_hand": x["on_hand"], "demand": x["demand"], "short": x["short"]},
            [("SalesOrder", s) for s in x["orders"]],
        )
        for x in M.shortages(conn)["items"]
    ]


def late_po_lines(o: dict, today: dt.date) -> list[dict]:
    p = o["props"]
    if not M._submitted(p) or p.get("status") in CLOSED_PO:
        return []
    out = []
    for ln in p.get("lines", []):
        due = _d(ln.get("schedule_date") or p.get("schedule_date"))
        left = (ln.get("qty") or 0) - (ln.get("received_qty") or 0)
        if due and due < today and left > 0:
            out.append({"item": ln.get("item_code"), "due": str(due), "days_late": (today - due).days, "left": left})
    return out


def po_late(conn, rule: dict, today: dt.date) -> list[Finding]:
    out = []
    for o in M._objs(conn, "PurchaseOrder"):
        late = late_po_lines(o, today)
        if late:
            worst = max(x["days_late"] for x in late)
            out.append(
                Finding(
                    ("PurchaseOrder", o["key"]),
                    f"{o['title']} is {worst} days late",
                    "; ".join(f"{x['item']}: {x['left']:g} not received, due {x['due']}" for x in late),
                    rule["severity"],
                    {"lines": late},
                    [("Item", x["item"]) for x in late if x["item"]],
                )
            )
    return out


def supplier_on_time_low(conn, rule: dict, today: dt.date) -> list[Finding]:
    r = M.supplier_on_time(conn, today, rule.get("days", 90))
    keys = {o["props"].get("supplier_name"): o["key"] for o in M._objs(conn, "Supplier")}
    out = []
    for s in r["suppliers"]:
        if s["total"] >= rule.get("min_lines", 3) and s["value"] < rule.get("target_pct", 90):
            out.append(
                Finding(
                    ("Supplier", keys.get(s["supplier"], s["supplier"])),
                    f"{s['supplier']} on time {s['value']:g}%",
                    f"{s['on_time']} of {s['total']} receipt lines on time in {rule.get('days', 90)} days "
                    f"(target {rule.get('target_pct', 90)}%).",
                    rule["severity"],
                    {"on_time_pct": s["value"], "lines": s["total"]},
                )
            )
    return out


def inspection_rejected(conn, rule: dict, today: dt.date) -> list[Finding]:
    out = []
    for x in M.open_nonconformances(conn, today, rule.get("days", 30))["inspections"]:
        rel = [("Item", x["item"])] if x["item"] else []
        if x["reference"]:
            rel.append(("PurchaseReceipt", x["reference"]))
        out.append(
            Finding(
                ("QualityInspection", x["key"]),
                f"{x['title']}",
                f"Rejected on {x['date']}.",
                rule["severity"],
                {"date": x["date"]},
                rel,
            )
        )
    return out


DETECTORS = {
    "order_late": order_late,
    "order_at_risk": order_at_risk,
    "item_short": item_short,
    "po_late": po_late,
    "supplier_on_time_low": supplier_on_time_low,
    "inspection_rejected": inspection_rejected,
}


def _log(conn, aid: int, action: str, email: str | None = None, note: str = "") -> None:
    conn.execute(
        "insert into anomaly_log (anomaly_id, email, action, note) values (%s, %s, %s, %s)",
        (aid, email, action, note[:1000]),
    )


def detect(conn, today: dt.date, rules: dict | None = None) -> dict:
    """One detection run: open new anomalies, update active ones, resolve those gone for two runs."""
    rules = rules or load_rules()
    counts = {"opened": 0, "updated": 0, "escalated": 0, "resolved": 0}
    with conn.transaction():
        seen: set[int] = set()
        for rid, rule in rules.items():
            for f in DETECTORS[rid](conn, rule, today):
                row = conn.execute(
                    "select * from anomalies where rule = %s and subject_type = %s and subject_key = %s "
                    "and status in ('open', 'ack', 'doing')",
                    (rid, *f.subject),
                ).fetchone()
                related = Jsonb([list(r) for r in f.related])
                if row is None:
                    row = conn.execute(
                        "insert into anomalies (rule, subject_type, subject_key, title, detail, severity,"
                        " vals, related) values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
                        (rid, *f.subject, f.title, f.detail, f.severity, Jsonb(f.vals), related),
                    ).fetchone()
                    _log(conn, row["id"], "opened", note=f.detail)
                    counts["opened"] += 1
                else:
                    if SEVERITY[f.severity] > SEVERITY[row["severity"]]:
                        _log(conn, row["id"], "escalated", note=f"{row['severity']} -> {f.severity}: {f.title}")
                        counts["escalated"] += 1
                    conn.execute(
                        "update anomalies set title = %s, detail = %s, severity = %s, vals = %s, related = %s,"
                        " misses = 0, last_seen = now() where id = %s",
                        (f.title, f.detail, f.severity, Jsonb(f.vals), related, row["id"]),
                    )
                    counts["updated"] += 1
                seen.add(row["id"])
        for row in conn.execute(
            "select id, misses from anomalies where status in ('open', 'ack', 'doing') and rule = any(%s)",
            (list(rules),),
        ).fetchall():
            if row["id"] in seen:
                continue
            if row["misses"] + 1 >= MISSES_TO_RESOLVE:
                conn.execute(
                    "update anomalies set status = 'resolved', misses = misses + 1, ended_at = now() where id = %s",
                    (row["id"],),
                )
                _log(conn, row["id"], "resolved", note="the condition is gone")
                counts["resolved"] += 1
            else:
                conn.execute("update anomalies set misses = misses + 1 where id = %s", (row["id"],))
    return counts


def visible_rules(roles, rules: dict) -> list[str]:
    return [rid for rid, r in rules.items() if P.allows(roles, r["view"])]


def public(row: dict, rules: dict) -> dict:
    r = rules.get(row["rule"], {})
    return {
        "id": row["id"],
        "rule": row["rule"],
        "rule_name": r.get("name", row["rule"]),
        "hint": r.get("hint", ""),
        "owner": r.get("owner"),
        "subject": [row["subject_type"], row["subject_key"]],
        "title": row["title"],
        "detail": row["detail"],
        "severity": row["severity"],
        "status": row["status"],
        "values": row["vals"],
        "related": row["related"],
        "first_seen": row["first_seen"].isoformat(),
        "last_seen": row["last_seen"].isoformat(),
        "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
    }


TRANSITIONS = {"open": {"ack", "doing", "closed"}, "ack": {"doing", "closed"}, "doing": {"closed", "ack"}}


def set_status(conn, aid: int, status: str, email: str, note: str = "") -> dict:
    row = conn.execute("select * from anomalies where id = %s", (aid,)).fetchone()
    if row is None:
        raise KeyError(aid)
    if status not in TRANSITIONS.get(row["status"], set()):
        raise ValueError(f"cannot change an anomaly from {row['status']} to {status}")
    with conn.transaction():
        row = conn.execute(
            "update anomalies set status = %s, ended_at = case when %s = 'closed' then now() end "
            "where id = %s returning *",
            (status, status, aid),
        ).fetchone()
        _log(conn, aid, status, email, note)
    return row
