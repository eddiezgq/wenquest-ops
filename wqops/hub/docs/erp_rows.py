"""Checks on another system's rows before they go into ERPNext (ADR-0020, 20a). Reads what the hub has synced from
ERPNext and what earlier imports brought in; no AI, no network (tests/test_isolation.py).

A row whose record is already in ERPNext, or came in with an earlier import, is skipped, not doubled. A row that names
an item, customer, supplier or warehouse ERPNext does not have cannot be imported yet: import those first (items
before opening stock and orders). A value in a mapped column that cannot be read stops the row: nothing is guessed and
ERPNext's own defaults do not stand in for it. Order lines with the same order number become one order; their customer
(or supplier) and dates must agree, and the delivery date cannot be before the order date.
"""

from __future__ import annotations

from wqops.hub.docs import ledger as LG
from wqops.i18n import say

KEYS = {"erp_item": ("Item", "item_code"), "erp_customer": ("Customer", "customer_name"),
        "erp_supplier": ("Supplier", "supplier_name")}
ORDERS = {"erp_sales_order": ("customer", "Customer", "delivery_date"),
          "erp_purchase_order": ("supplier", "Supplier", "schedule_date")}
NAMES = {"Customer": "customer_name", "Supplier": "supplier_name", "Warehouse": "warehouse_name"}


def _names(conn, otype: str) -> tuple[dict[str, str], set[str]]:
    """lower-cased key (and name, for customers, suppliers and warehouses) -> the ERPNext name, and the names that
    belong to more than one record (ambiguous). Items are matched by their code only."""
    out: dict[str, str] = {}
    twice: set[str] = set()
    rows = conn.execute("select key, props from ont_objects where type = %s and not deleted", (otype,)).fetchall()
    for r in rows:
        out[r["key"].lower()] = r["key"]
    for r in rows:
        alt = str(r["props"].get(NAMES.get(otype, "")) or "").lower()
        if not alt or alt == r["key"].lower():
            continue
        if alt in out and out[alt] != r["key"]:
            twice.add(alt)
        else:
            out[alt] = r["key"]
    return out, twice


def earlier(conn, target: str) -> dict[str, str | None]:
    """Keys an earlier import of this kind took (the ERPNext name, or None if that run stopped half way)."""
    return {r["key"]: r["ref"] for r in conn.execute("select key, ref from erp_import_keys where target = %s",
                                                     (target,))}


def key_of(target: str, r: dict) -> str | None:
    """The row's key in the old system, for not doubling it: a name, an old order number, an item in a warehouse."""
    v = r["values"]
    if target in KEYS:
        return str(v.get(KEYS[target][1]) or "").strip().lower() or None
    if target == "erp_opening_stock":
        return f"{str(v.get('item_code') or '').strip().lower()}|{str(v.get('warehouse') or '').strip().lower()}"
    no = str(v.get("order_no") or "").strip().lower()
    return no or None


def group_key(r: dict) -> tuple[str, str]:
    """The order a line belongs to: its order number, or the row itself when the file has none."""
    no = str(r["values"].get("order_no") or "").strip()
    return ("order", no) if no else ("row", str(r["row"]))


def label(g: tuple[str, str]) -> str:
    return g[1] if g[0] == "order" else say("on row {n}", n=g[1])


def _before(why: str | None) -> str:
    return say("imported before as {ref}", ref=why) if why else say(
        "an earlier import of it stopped half way: check ERPNext, then ask whoever runs the system to clear it")


def annotate(conn, target: str, rows: list[dict]) -> list[dict]:  # noqa: PLR0912, PLR0915 - one branch per check
    """Add to each row: ``exists`` (already in ERPNext or imported before: skipped), ``erp`` (the ERPNext names it
    refers to), more problems, and ``ok`` False when it cannot be imported yet. ``rows`` come from ledger.rows."""
    if target not in LG.TARGETS or not target.startswith("erp_"):
        return rows
    spec = LG.TARGETS[target]["fields"]
    done = earlier(conn, target)
    for r in rows:                      # a mapped value that cannot be read is not left to ERPNext's defaults
        bad = [LG.field_name(spec[f], lower=True) for f in r.get("raw", {}) if f not in r["values"]]
        if bad:
            r["ok"] = False
            r["problems"].append(say("cannot be read, so not imported: {fields}", fields=LG.join_names(bad)))
        k = key_of(target, r)
        if k and k in done:
            r["exists"] = _before(done[k])
    if target in KEYS:
        otype, field = KEYS[target]
        have, _ = _names(conn, otype)
        seen: dict[str, int] = {}
        for r in rows:
            v = str(r["values"].get(field) or "").strip().lower()
            if not v or r.get("exists"):
                continue
            if v in have:
                r["exists"] = say("already in ERPNext as {name}", name=have[v])
            elif v in seen:
                r["exists"] = say("the same as row {n}", n=seen[v])
            else:
                seen[v] = r["row"]
        return rows
    refs = {"item_code": _names(conn, "Item")}
    if target == "erp_opening_stock":
        refs["warehouse"] = _names(conn, "Warehouse")
    else:
        party, ptype, _ = ORDERS[target]
        refs[party] = _names(conn, ptype)
    for r in rows:
        r["erp"] = {}
        for f, (have, twice) in refs.items():
            v = str(r["values"].get(f) or "").strip()
            if not v:
                continue
            what = LG.field_name(spec[f], lower=True)
            if v.lower() in twice:
                r["problems"].append(say("{field} {value} is the name of more than one record in ERPNext: use its code",
                                         field=what, value=repr(v)))
                r["ok"] = False
            elif v.lower() in have:
                r["erp"][f] = have[v.lower()]
            else:
                r["problems"].append(say("{field} {value} is not in ERPNext yet: import it first", field=what,
                                         value=repr(v)))
                r["ok"] = False
    if target == "erp_opening_stock":
        seen_pair: dict[str, int] = {}
        for r in rows:
            k = key_of(target, r)
            if k in seen_pair and not r.get("exists"):
                r["problems"].append(say("the same item and warehouse as row {n}: ERPNext takes one line each",
                                         n=seen_pair[k]))
                r["ok"] = False
            seen_pair.setdefault(k, r["row"])
        return rows
    party, _, due = ORDERS[target]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault(group_key(r), []).append(r)
    for g, lines in groups.items():
        for f in (party, "transaction_date", due):
            if len({str(x["values"].get(f) or "") for x in lines}) > 1:
                for x in lines:
                    x["problems"].append(say("the lines of order {order} differ in {field}", order=label(g),
                                             field=LG.field_name(spec[f], lower=True)))
                    x["ok"] = False
        for x in lines:
            start, end = x["values"].get("transaction_date"), x["values"].get(due)
            if start and end and end < start:
                x["problems"].append(say("{field} {end} is before the order date {start}",
                                         field=LG.field_name(spec[due], lower=True), end=end, start=start))
                x["ok"] = False
    return rows
