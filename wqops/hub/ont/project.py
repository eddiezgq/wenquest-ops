"""Objects from ERPNext events (ADR-0007): read erp_events in order, write ont_objects, ont_links and ont_history.

    python -m wqops.hub.ont.project [--rebuild]

Each ERPNext doctype has a mapper that turns one document into one object and its outgoing links; stock levels are
the sum of the stock ledger (cancelled entries left out). People and departments come from the company manifest.
Replaying every event from scratch gives the same result as the incremental updates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from wqops.hub import db as DB
from wqops.hub.ont import schema as S

BATCH = 500


@dataclass
class Obj:
    type: str
    key: str
    props: dict
    links: list[tuple[str, str, str]] = field(default_factory=list)  # (link name, target type, target key)


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _date(v) -> str | None:
    return str(v)[:10] if v else None


def _bool(v) -> bool:
    return bool(int(v)) if isinstance(v, (int, float, str)) and str(v).isdigit() else bool(v)


def _lines(doc: dict, fields: dict[str, Callable]) -> list[dict]:
    out = []
    for row in doc.get("items") or []:
        line = {}
        for f, conv in fields.items():
            v = conv(row.get(f))
            if v is not None:
                line[f] = v
        out.append(line)
    return out


def _many(name: str, target: str, keys) -> list[tuple[str, str, str]]:
    return [(name, target, k) for k in sorted({k for k in keys if k})]


def _clean(props: dict) -> dict:
    """Leave out what ERPNext did not say (missing data stays missing, never 0)."""
    return {k: v for k, v in props.items() if v is not None and v != ""}


def _str(v) -> str | None:
    return None if v is None else str(v)


def item(d):
    return Obj(
        "Item",
        d["name"],
        _clean(
            {
                "item_name": d.get("item_name"),
                "item_group": d.get("item_group"),
                "stock_uom": d.get("stock_uom"),
                "is_stock_item": _bool(d.get("is_stock_item")),
                "disabled": _bool(d.get("disabled")),
                "inspection_required": None
                if d.get("inspection_required_before_purchase") is None
                else _bool(d["inspection_required_before_purchase"]),
            }
        ),
    )


def warehouse(d):
    return Obj(
        "Warehouse",
        d["name"],
        _clean(
            {
                "warehouse_name": d.get("warehouse_name"),
                "is_group": _bool(d.get("is_group")),
                "disabled": _bool(d.get("disabled")),
            }
        ),
        _many("parent", "Warehouse", [d.get("parent_warehouse")]),
    )


def customer(d):
    return Obj(
        "Customer",
        d["name"],
        _clean(
            {
                "customer_name": d.get("customer_name"),
                "customer_group": d.get("customer_group"),
                "territory": d.get("territory"),
                "disabled": _bool(d.get("disabled")),
            }
        ),
    )


def supplier(d):
    return Obj(
        "Supplier",
        d["name"],
        _clean(
            {
                "supplier_name": d.get("supplier_name"),
                "supplier_group": d.get("supplier_group"),
                "disabled": _bool(d.get("disabled")),
            }
        ),
    )


def stock_move(d):
    vt, vn = d.get("voucher_type"), d.get("voucher_no")
    links = _many("item", "Item", [d.get("item_code")]) + _many("warehouse", "Warehouse", [d.get("warehouse")])
    if vt == "Delivery Note":
        links += _many("delivery_note", "DeliveryNote", [vn])
    elif vt == "Purchase Receipt":
        links += _many("purchase_receipt", "PurchaseReceipt", [vn])
    return Obj(
        "StockMove",
        d["name"],
        _clean(
            {
                "posting_date": _date(d.get("posting_date")),
                "item_code": d.get("item_code"),
                "warehouse": d.get("warehouse"),
                "actual_qty": _num(d.get("actual_qty")),
                "stock_value_difference": _num(d.get("stock_value_difference")),
                "voucher_type": vt,
                "voucher_no": vn,
                "is_cancelled": _bool(d.get("is_cancelled")),
            }
        ),
        links,
    )


def sales_order(d):
    lines = _lines(
        d,
        {
            "item_code": _str,
            "qty": _num,
            "delivered_qty": _num,
            "delivery_date": _date,
            "warehouse": _str,
            "rate": _num,
            "amount": _num,
        },
    )
    return Obj(
        "SalesOrder",
        d["name"],
        _clean(
            {
                "customer_name": d.get("customer_name"),
                "transaction_date": _date(d.get("transaction_date")),
                "delivery_date": _date(d.get("delivery_date")),
                "status": d.get("status"),
                "docstatus": d.get("docstatus"),
                "grand_total": _num(d.get("grand_total")),
                "per_delivered": _num(d.get("per_delivered")),
                "lines": lines,
            }
        ),
        _many("customer", "Customer", [d.get("customer")])
        + _many("items", "Item", [x.get("item_code") for x in lines]),
    )


def delivery_note(d):
    lines = _lines(d, {"item_code": _str, "qty": _num, "against_sales_order": _str, "warehouse": _str})
    return Obj(
        "DeliveryNote",
        d["name"],
        _clean(
            {
                "customer_name": d.get("customer_name"),
                "posting_date": _date(d.get("posting_date")),
                "status": d.get("status"),
                "docstatus": d.get("docstatus"),
                "is_return": _bool(d.get("is_return")),
                "lines": lines,
            }
        ),
        _many("customer", "Customer", [d.get("customer")])
        + _many("sales_orders", "SalesOrder", [x.get("against_sales_order") for x in lines])
        + _many("items", "Item", [x.get("item_code") for x in lines]),
    )


def purchase_order(d):
    lines = _lines(
        d,
        {
            "item_code": _str,
            "qty": _num,
            "received_qty": _num,
            "schedule_date": _date,
            "warehouse": _str,
            "rate": _num,
            "name": _str,
        },
    )
    return Obj(
        "PurchaseOrder",
        d["name"],
        _clean(
            {
                "supplier_name": d.get("supplier_name"),
                "transaction_date": _date(d.get("transaction_date")),
                "schedule_date": _date(d.get("schedule_date")),
                "status": d.get("status"),
                "docstatus": d.get("docstatus"),
                "grand_total": _num(d.get("grand_total")),
                "per_received": _num(d.get("per_received")),
                "lines": lines,
            }
        ),
        _many("supplier", "Supplier", [d.get("supplier")])
        + _many("items", "Item", [x.get("item_code") for x in lines]),
    )


def purchase_receipt(d):
    lines = _lines(
        d,
        {
            "item_code": _str,
            "qty": _num,
            "rejected_qty": _num,
            "purchase_order": _str,
            "purchase_order_item": _str,
            "warehouse": _str,
        },
    )
    return Obj(
        "PurchaseReceipt",
        d["name"],
        _clean(
            {
                "supplier_name": d.get("supplier_name"),
                "posting_date": _date(d.get("posting_date")),
                "status": d.get("status"),
                "docstatus": d.get("docstatus"),
                "is_return": _bool(d.get("is_return")),
                "lines": lines,
            }
        ),
        _many("supplier", "Supplier", [d.get("supplier")])
        + _many("purchase_orders", "PurchaseOrder", [x.get("purchase_order") for x in lines])
        + _many("items", "Item", [x.get("item_code") for x in lines]),
    )


def _readings(d: dict) -> list[dict]:
    """Numeric readings of an inspection: parameter, the values entered (reading_1..reading_10), limits, result."""
    out = []
    for r in d.get("readings") or []:
        if not r.get("specification") or not _bool(r.get("numeric", 1)):
            continue
        values = [v for v in (_num(r.get(f"reading_{i}")) for i in range(1, 11)) if v is not None]
        if not values:
            continue
        out.append(_clean({"parameter": r["specification"], "values": values, "min": _num(r.get("min_value")),
                           "max": _num(r.get("max_value")), "status": r.get("status")}))
    return out


def quality_inspection(d):
    rt, rn = d.get("reference_type"), d.get("reference_name")
    links = _many("item", "Item", [d.get("item_code")])
    if rt == "Purchase Receipt":
        links += _many("purchase_receipt", "PurchaseReceipt", [rn])
    elif rt == "Delivery Note":
        links += _many("delivery_note", "DeliveryNote", [rn])
    return Obj(
        "QualityInspection",
        d["name"],
        _clean(
            {
                "inspection_type": d.get("inspection_type"),
                "report_date": _date(d.get("report_date")),
                "readings": _readings(d) or None,
                "status": d.get("status"),
                "docstatus": d.get("docstatus"),
                "item_code": d.get("item_code"),
                "reference_type": rt,
                "reference_name": rn,
                "sample_size": _num(d.get("sample_size")),
                "inspected_by": d.get("inspected_by"),
            }
        ),
        links,
    )


MAPPERS: dict[str, tuple[str, Callable[[dict], Obj]]] = {
    "Item": ("Item", item),
    "Warehouse": ("Warehouse", warehouse),
    "Customer": ("Customer", customer),
    "Supplier": ("Supplier", supplier),
    "Stock Ledger Entry": ("StockMove", stock_move),
    "Sales Order": ("SalesOrder", sales_order),
    "Delivery Note": ("DeliveryNote", delivery_note),
    "Purchase Order": ("PurchaseOrder", purchase_order),
    "Purchase Receipt": ("PurchaseReceipt", purchase_receipt),
    "Quality Inspection": ("QualityInspection", quality_inspection),
}


def _search(o: Obj, title: str) -> str:
    words = [o.key, title] + [str(v) for k, v in o.props.items() if isinstance(v, str) and k != "lines"]
    words += [str(x["item_code"]) for x in o.props.get("lines", []) if x.get("item_code")]  # find orders by item
    return " ".join(dict.fromkeys(words)).lower()


def _changes(old: dict, new: dict) -> dict:
    out = {}
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            out[k] = "changed" if k == "lines" else {"from": old.get(k), "to": new.get(k)}
    return out


def upsert(conn, onto: S.Ontology, o: Obj, *, kind: str, at: str, event_id: int | None = None) -> None:
    spec = onto.type(o.type)
    for k in o.props:
        if k not in spec["props"]:
            raise S.OntologyError(f"{o.type}.{k} is not in the ontology")
    for ln, dst, _ in o.links:
        if onto.link(o.type, ln)["to"] != dst:
            raise S.OntologyError(f"{o.type}.{ln} points to {onto.link(o.type, ln)['to']}, not {dst}")
    old = conn.execute(
        "select props, deleted from ont_objects where type = %s and key = %s", (o.type, o.key)
    ).fetchone()
    title = S.title_of(spec, o.key, o.props)
    conn.execute(
        "insert into ont_objects (type, key, domain, title, props, search) values (%s, %s, %s, %s, %s, %s) "
        "on conflict (type, key) do update set title = excluded.title, props = excluded.props, "
        "deleted = false, search = excluded.search, updated_at = now()",
        (o.type, o.key, spec["domain"], title, Jsonb(o.props), _search(o, title)),
    )
    conn.execute("delete from ont_links where src_type = %s and src_key = %s", (o.type, o.key))
    for ln, dst, dkey in o.links:
        conn.execute(
            "insert into ont_links (type, src_type, src_key, dst_type, dst_key) values (%s, %s, %s, %s, %s) "
            "on conflict do nothing",
            (ln, o.type, o.key, dst, dkey),
        )
    changes = _changes(old["props"] if old and not old["deleted"] else {}, o.props)
    if changes or old is None or old["deleted"]:
        conn.execute(
            "insert into ont_history (type, key, event_id, kind, at, changes) values (%s, %s, %s, %s, %s, %s)",
            (o.type, o.key, event_id, kind, at, Jsonb(changes)),
        )


def remove(conn, type_: str, key: str, *, at: str, event_id: int | None = None) -> None:
    hit = conn.execute(
        "update ont_objects set deleted = true, updated_at = now() where type = %s and key = %s "
        "and not deleted returning key",
        (type_, key),
    ).fetchone()
    conn.execute("delete from ont_links where src_type = %s and src_key = %s", (type_, key))
    if hit:
        conn.execute(
            "insert into ont_history (type, key, event_id, kind, at) values (%s, %s, %s, 'deleted', %s)",
            (type_, key, event_id, at),
        )


def _stock_pair(conn, key: str) -> tuple[str, str] | None:
    r = conn.execute("select props from ont_objects where type = 'StockMove' and key = %s", (key,)).fetchone()
    return (r["props"].get("item_code"), r["props"].get("warehouse")) if r else None


def stock_levels(conn, onto: S.Ontology, pairs: set[tuple[str, str]], at: str) -> None:
    """Stock level of each (item, warehouse) = sum of its stock movements that are not cancelled or deleted."""
    for it, wh in sorted(p for p in pairs if p[0] and p[1]):
        r = conn.execute(
            "select count(*) as n, coalesce(sum((props->>'actual_qty')::numeric), 0) as qty, "
            "sum((props->>'stock_value_difference')::numeric) as value, "
            "count(props->'stock_value_difference') as nvalue from ont_objects where type = 'StockMove' "
            "and not deleted and props->>'item_code' = %s and props->>'warehouse' = %s "
            "and not coalesce((props->>'is_cancelled')::boolean, false)",
            (it, wh),
        ).fetchone()
        key = f"{it}@{wh}"
        if r["n"] == 0:
            remove(conn, "StockLevel", key, at=at)
            continue
        props = {"item": it, "warehouse": wh, "actual_qty": float(r["qty"])}
        if r["nvalue"] == r["n"]:  # value only when every movement says it
            props["stock_value"] = round(float(r["value"]), 2)
        upsert(
            conn,
            onto,
            Obj("StockLevel", key, props, [("item", "Item", it), ("warehouse", "Warehouse", wh)]),
            kind="updated",
            at=at,
        )


def warehouse_kinds(conn, onto: S.Ontology, manifest: dict | None) -> None:
    """Purpose of each warehouse (receiving, stores, quarantine, ...) from the company manifest."""
    if not manifest:
        return
    abbr = manifest["company"]["abbr"]
    for w in manifest.get("warehouses", []):
        conn.execute(
            "update ont_objects set props = props || jsonb_build_object('kind', %s::text) "
            "where type = 'Warehouse' and key = %s",
            (w["kind"], f"{w['name']} - {abbr}"),
        )


def quality(conn, onto: S.Ontology) -> None:
    """Nonconformance reports and corrective / preventive actions from the quality module (ADR-0009 item 7)."""
    for r in conn.execute("select * from ncr_records order by id").fetchall():
        props = _clean({"title": r["title"], "status": r["status"], "severity": r["severity"],
                        "disposition": r["disposition"], "owner": r["owner"],
                        "opened": r["created_at"].date().isoformat(),
                        "quantity": float(r["quantity"]) if r["quantity"] is not None else None})
        links = (_many("item", "Item", [r["item_code"]]) + _many("supplier", "Supplier", [r["supplier"]])
                 + _many("receipt", "PurchaseReceipt", [r["receipt"]])
                 + _many("inspection", "QualityInspection", [r["inspection"]]))
        upsert(conn, onto, Obj("Nonconformance", r["name"], props, links), kind="updated",
               at=r["updated_at"].isoformat())
    for c in conn.execute("select c.*, array(select n.name from capa_ncrs l join ncr_records n on n.id = l.ncr_id "
                          "where l.capa_id = c.id) as ncr_names, (select min(due) from capa_actions a where "
                          "a.capa_id = c.id and not a.done) as next_due from capas c "
                          "order by c.id").fetchall():
        props = _clean({"title": c["title"], "kind": c["kind"], "status": c["status"], "owner": c["owner"],
                        "next_due": c["next_due"].isoformat() if c["next_due"] else None,
                        "result": c["verification_result"]})
        upsert(conn, onto, Obj("Capa", c["name"], props, _many("ncr", "Nonconformance", c["ncr_names"])),
               kind="updated", at=c["updated_at"].isoformat())


def people(conn, onto: S.Ontology, manifest: dict | None) -> None:
    if not manifest:
        return
    for d in manifest.get("departments", []):
        upsert(conn, onto, Obj("Department", d["id"], {"name": d["name"]}), kind="updated", at="manifest")
    for u in conn.execute("select email, name, roles, department, active from users order by email").fetchall():
        upsert(
            conn,
            onto,
            Obj(
                "Person",
                u["email"],
                {"name": u["name"], "roles": list(u["roles"]), "active": u["active"]},
                _many("department", "Department", [u["department"]]),
            ),
            kind="updated",
            at="manifest",
        )


def _state(conn, name: str, default=None):
    r = conn.execute("select value from ont_state where name = %s", (name,)).fetchone()
    return r["value"] if r else default


def _set_state(conn, name: str, value) -> None:
    conn.execute(
        "insert into ont_state (name, value) values (%s, %s) on conflict (name) do update set value = excluded.value",
        (name, Jsonb(value)),
    )


def project(
    conn, onto: S.Ontology | None = None, manifest: dict | None = None, *, rebuild: bool = False, batch: int = BATCH
) -> dict:
    """Apply the events not yet applied; return how many events and objects were touched."""
    onto = onto or S.get()
    if rebuild:
        with conn.transaction():
            for t in ("ont_history", "ont_links", "ont_objects", "ont_state"):
                conn.execute(f"delete from {t}")  # noqa: S608 - fixed table names
    last = _state(conn, "last_event", 0)
    n_events = 0
    touched: set[tuple[str, str]] = set()
    while True:
        events = conn.execute("select * from erp_events where id > %s order by id limit %s", (last, batch)).fetchall()
        if not events:
            break
        with conn.transaction():
            pairs: set[tuple[str, str]] = set()
            for e in events:
                if e["doctype"] not in MAPPERS:
                    continue
                type_, fn = MAPPERS[e["doctype"]]
                if type_ == "StockMove":
                    p = _stock_pair(conn, e["name"])
                    if p:
                        pairs.add(p)
                if e["kind"] == "deleted":
                    remove(conn, type_, e["name"], at=e["modified"], event_id=e["id"])
                else:
                    o = fn(e["data"])
                    upsert(conn, onto, o, kind=e["kind"], at=e["modified"], event_id=e["id"])
                    if type_ == "StockMove":
                        pairs.add((o.props.get("item_code"), o.props.get("warehouse")))
                touched.add((type_, e["name"]))
            stock_levels(conn, onto, pairs, events[-1]["modified"])
            last = events[-1]["id"]
            _set_state(conn, "last_event", last)
        n_events += len(events)
    with conn.transaction():
        warehouse_kinds(conn, onto, manifest)
        people(conn, onto, manifest)
        quality(conn, onto)
    return {"events": n_events, "objects": len(touched), "last_event": last}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wqops.hub.ont.project", description="Build ops hub objects")
    ap.add_argument("--rebuild", action="store_true", help="clear the objects and replay every event")
    a = ap.parse_args(argv)
    url = os.environ.get("WQO_DB")
    if not url:
        print("WQO_DB is not set", file=sys.stderr)
        return 2
    from wqops import company as C  # noqa: PLC0415

    path = os.environ.get("WQO_COMPANY_FILE")
    manifest = C.load(path) if path else None
    with DB.connect(url) as conn:
        DB.migrate(conn)
        print(json.dumps(project(conn, manifest=manifest, rebuild=a.rebuild)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
