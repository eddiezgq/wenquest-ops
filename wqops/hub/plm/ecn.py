"""Design changes, step 26d (ADR-0026): a product change (17g) lists the parts it changes (the part, its BOM or
both), says how it takes effect, and is assessed on an impact analysis code makes: the assemblies above each part
(through released and draft BOMs), stock, open purchase orders and work orders, open sales orders of the
assemblies. The AI may draft the impact note from that table only; a person edits it into the assessment.

The change is submitted only with all of it, and implemented only when each part has its new revision (part, BOM or
both) released under this change.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from psycopg.types.json import Jsonb

from wqops.erp import ErpClient
from wqops.hub.plm import parts as PT
from wqops.hub.plm import rules as R
from wqops.i18n import say

SCOPES = ("part", "bom", "both")
MODES = ("now", "use_up", "date", "serial")
OPEN_PO = ("Completed", "Closed", "Cancelled", "Delivered")
OPEN_SO = ("Completed", "Closed", "Cancelled")
OPEN_WO = ["Not Started", "In Process"]

PlmError = PT.PlmError


def _change(conn, cid: int, *, lock: bool = False) -> dict:
    sql = "select * from changes where id = %s for update" if lock else "select * from changes where id = %s"
    c = conn.execute(sql, (cid,)).fetchone()
    if c is None:
        raise KeyError(cid)
    return c


def _draft_product(c: dict) -> None:
    if c["kind"] != "product":
        raise PlmError(say("parts are changed by a product change"))
    if c["status"] != "draft":
        raise PlmError(say("the change is {status}: what it changes is fixed", status=c["status"]))


def items(conn, cid: int) -> list[dict]:
    rows = conn.execute("select i.*, p.item_code, p.name, p.source, p.status as part_status from plm_change_items i "
                        "join plm_parts p on p.id = i.part_id where i.change_id = %s order by i.id", (cid,)).fetchall()
    out = []
    for r in rows:
        x = PT._iso(dict(r))
        new_part = conn.execute("select id, revision, status from plm_part_revisions where part_id = %s and "
                                "change_id = %s order by id desc limit 1", (r["part_id"], cid)).fetchone()
        new_bom = conn.execute("select id, revision, status from plm_boms where part_id = %s and change_id = %s "
                               "order by id desc limit 1", (r["part_id"], cid)).fetchone()
        x["new_part"] = dict(new_part) if new_part else None
        x["new_bom"] = dict(new_bom) if new_bom else None
        out.append(x)
    return out


def effect(conn, cid: int) -> dict | None:
    e = conn.execute("select * from plm_change_effect where change_id = %s", (cid,)).fetchone()
    return PT._iso(dict(e)) if e else None


def key(conn, cid: int) -> str:
    rows = conn.execute("select part_id, scope from plm_change_items where change_id = %s order by part_id",
                        (cid,)).fetchall()
    return hashlib.sha256(json.dumps([[r["part_id"], r["scope"]] for r in rows]).encode()).hexdigest()[:16]


def impact(conn, cid: int) -> dict | None:
    r = conn.execute("select * from plm_change_impact where change_id = %s", (cid,)).fetchone()
    if r is None:
        return None
    return {"data": r["data"], "made_by": r["made_by"], "made_at": r["made_at"].isoformat(),
            "current": r["items_key"] == key(conn, cid)}


def view(conn, cid: int) -> dict:
    c = _change(conn, cid)
    return {"items": items(conn, cid), "effect": effect(conn, cid), "impact": impact(conn, cid),
            "scopes": list(SCOPES), "modes": list(MODES), "editable": c["kind"] == "product" and c["status"] == "draft"}


def add_item(conn, user: dict, cid: int, data: dict) -> dict:
    scope = data.get("scope") or "part"
    if scope not in SCOPES:
        raise PlmError(say("say whether the part, its BOM or both change"))
    p = None
    if type(data.get("part_id")) is int:
        p = conn.execute("select * from plm_parts where id = %s", (data["part_id"],)).fetchone()
    elif data.get("code"):
        p = PT.by_code(conn, str(data["code"]).strip())
    if p is None:
        raise PlmError(say("no such part {code}", code=data.get("code") or data.get("part_id") or ""))
    rel = PT.latest_released(conn, p["id"])
    bom = conn.execute("select revision from plm_boms where part_id = %s and status = 'released' order by id desc "
                       "limit 1", (p["id"],)).fetchone()
    if scope in ("part", "both") and rel is None:
        raise PlmError(say("{code} has no released revision: a draft changes without a change", code=p["item_code"]))
    if scope in ("bom", "both") and bom is None:
        raise PlmError(say("{code} has no released BOM", code=p["item_code"]))
    with conn.transaction():
        _draft_product(_change(conn, cid, lock=True))
        if conn.execute("select 1 from plm_change_items where change_id = %s and part_id = %s",
                        (cid, p["id"])).fetchone():
            raise PlmError(say("{code} is already on the change", code=p["item_code"]))
        conn.execute("insert into plm_change_items (change_id, part_id, scope, from_part, from_bom, note, added_by) "
                     "values (%s, %s, %s, %s, %s, %s, %s)",
                     (cid, p["id"], scope, rel["revision"] if rel and scope != "bom" else None,
                      bom["revision"] if bom and scope != "part" else None, str(data.get("note") or "").strip()[:500],
                      user["email"]))
        _log(conn, cid, user["email"], say("part added: {code}", code=p["item_code"]))
    return view(conn, cid)


def remove_item(conn, user: dict, cid: int, part_id: int) -> dict:
    with conn.transaction():
        _draft_product(_change(conn, cid, lock=True))
        row = conn.execute("delete from plm_change_items where change_id = %s and part_id = %s returning part_id",
                           (cid, part_id)).fetchone()
        if row is None:
            raise KeyError(part_id)
        _log(conn, cid, user["email"], say("part removed: {code}", code=PT.get(conn, part_id)["item_code"]))
    return view(conn, cid)


def set_effect(conn, user: dict, cid: int, data: dict) -> dict:
    mode = data.get("mode")
    if mode not in MODES:
        raise PlmError(say("choose how the change takes effect"))
    on_date = str(data.get("on_date") or "")[:10] or None
    serial = str(data.get("from_serial") or "").strip()[:60] or None
    if mode == "date" and not on_date:
        raise PlmError(say("give the date it takes effect"))
    if mode == "serial" and not serial:
        raise PlmError(say("give the first serial number it applies to"))
    with conn.transaction():
        _draft_product(_change(conn, cid, lock=True))
        conn.execute("insert into plm_change_effect (change_id, mode, on_date, from_serial, note, set_by) values "
                     "(%s, %s, %s, %s, %s, %s) on conflict (change_id) do update set mode = excluded.mode, "
                     "on_date = excluded.on_date, from_serial = excluded.from_serial, note = excluded.note, "
                     "set_by = excluded.set_by, set_at = now()",
                     (cid, mode, on_date if mode == "date" else None, serial if mode == "serial" else None,
                      str(data.get("note") or "").strip()[:500], user["email"]))
        _log(conn, cid, user["email"], say("takes effect: {mode}", mode=say("effect::" + mode)))
    return view(conn, cid)


def _log(conn, cid: int, email: str, note: str) -> None:
    """In the change's own log; the person becomes one of its editors (so cannot approve it, 17g)."""
    conn.execute("insert into change_log (change_id, email, action, note) values (%s, %s, %s, %s)",
                 (cid, email, "design change", note[:2000]))
    conn.execute("update changes set editors = case when %s = any(editors) then editors else editors || %s end, "
                 "updated_at = now() where id = %s", (email, [email], cid))


# ---- impact analysis (code only)

def ancestors(conn, pid: int) -> list[dict]:
    """The assemblies above a part through released and draft BOMs, nearest first; top ones are used nowhere."""
    parents: dict[int, set[int]] = {}
    for r in conn.execute("select distinct b.part_id as parent, l.part_id as child from plm_boms b join "
                          "plm_bom_lines l on l.bom_id = b.id where b.status <> 'superseded'"):
        parents.setdefault(r["child"], set()).add(r["parent"])
    seen, order, queue = set(), [], [pid]
    while queue:
        n = queue.pop(0)
        for p in sorted(parents.get(n, ())):
            if p not in seen and p != pid:
                seen.add(p)
                order.append(p)
                queue.append(p)
    if not order:
        return []
    rows = {r["id"]: r for r in conn.execute("select id, item_code, name from plm_parts where id = any(%s)", (order,))}
    return [{"id": i, "code": rows[i]["item_code"], "name": rows[i]["name"], "top": not parents.get(i)}
            for i in order]


def _synced(conn, doctype: str) -> bool:
    return bool(conn.execute("select 1 from erp_docs where doctype = %s limit 1", (doctype,)).fetchone())


def stock(conn, code: str) -> str | None:
    """On hand from the synced stock ledger; None when nothing was ever synced (unknown, not zero)."""
    if not _synced(conn, "Stock Ledger Entry"):
        return None
    r = conn.execute("select coalesce(sum((data->>'actual_qty')::numeric), 0) as q from erp_docs where doctype = "
                     "'Stock Ledger Entry' and not deleted and docstatus = 1 and coalesce(data->>'is_cancelled', '0') "
                     "in ('0', 'false') and data->>'item_code' = %s", (code,)).fetchone()
    return R.qty_text(r["q"]) if r["q"] else "0"


def open_orders(conn, doctype: str, code: str, done_field: str, closed: tuple[str, ...]) -> list[dict] | None:
    if not _synced(conn, doctype):
        return None
    out = []
    for d in conn.execute("select name, data from erp_docs where doctype = %s and not deleted and docstatus = 1 and "
                          "coalesce(data->>'status', '') <> all(%s)", (doctype, list(closed))):
        left = sum((Decimal(str(i.get("qty") or 0)) - Decimal(str(i.get(done_field) or 0)))
                   for i in d["data"].get("items") or [] if i.get("item_code") == code)
        if left > 0:
            out.append({"name": d["name"], "party": d["data"].get("supplier") or d["data"].get("customer") or "",
                        "open": R.qty_text(left)})
    return out


def work_orders(erp: ErpClient | None, codes: list[str]) -> list[dict] | None:
    if erp is None or not codes:
        return None if erp is None else []
    try:
        rows = erp.list("Work Order", filters=[["production_item", "in", codes], ["docstatus", "=", 1],
                                               ["status", "in", OPEN_WO]],
                        fields=["name", "production_item", "qty", "produced_qty", "status"], limit=200)
    except Exception:
        return None
    return [{"name": r["name"], "item": r["production_item"],
             "open": R.qty_text(Decimal(str(r.get("qty") or 0)) - Decimal(str(r.get("produced_qty") or 0)))}
            for r in rows]


def analyse(conn, user: dict, cid: int, erp: ErpClient | None) -> dict:
    c = _change(conn, cid)
    _draft_product(c)
    its = items(conn, cid)
    if not its:
        raise PlmError(say("add the parts it changes first"))
    rows = []
    for it in its:
        up = ancestors(conn, it["part_id"])
        tops = [a for a in up if a["top"]]
        codes = [it["item_code"], *[a["code"] for a in up]]
        wos = work_orders(erp, codes)
        sos = [] if tops else None
        for t in tops:
            got = open_orders(conn, "Sales Order", t["code"], "delivered_qty", OPEN_SO)
            if got is None:
                sos = None
                break
            sos += [{**s, "item": t["code"]} for s in got]
        rows.append({"code": it["item_code"], "name": it["name"], "scope": it["scope"],
                     "from_part": it["from_part"], "from_bom": it["from_bom"],
                     "used_in": up, "stock": stock(conn, it["item_code"]),
                     "purchase_orders": open_orders(conn, "Purchase Order", it["item_code"], "received_qty", OPEN_PO),
                     "work_orders": wos, "sales_orders": sos})
    data = {"parts": rows}
    with conn.transaction():
        _draft_product(_change(conn, cid, lock=True))
        conn.execute("insert into plm_change_impact (change_id, items_key, data, made_by) values (%s, %s, %s, %s) on "
                     "conflict (change_id) do update set items_key = excluded.items_key, data = excluded.data, "
                     "made_by = excluded.made_by, made_at = now()",
                     (cid, key(conn, cid), Jsonb(data), user["email"]))
        _log(conn, cid, user["email"], say("impact analysed: {n} parts", n=len(rows)))
    return view(conn, cid)


def as_text(data: dict) -> str:
    """The analysis as plain lines: what the AI reads, and the draft when there is no model."""
    unknown = say("unknown")
    lines = []
    for p in data.get("parts", []):
        lines.append(f"{p['code']} {p['name']} ({say('scope::' + p['scope'])})")
        used = ", ".join(f"{a['code']} {a['name']}" + (" *" if a["top"] else "") for a in p["used_in"])
        lines.append("  " + say("used in: {list}", list=used or say("none")))
        lines.append("  " + say("stock: {qty}", qty=unknown if p["stock"] is None else p["stock"]))
        for k, label in (("purchase_orders", say("open purchase orders")), ("work_orders", say("open work orders")),
                         ("sales_orders", say("open sales orders of the machines"))):
            v = p[k]
            shown = unknown if v is None else (", ".join(f"{o['name']} {o['open']}" for o in v) or say("none"))
            lines.append(f"  {label}: {shown}")
    return "\n".join(lines)


# ---- what a change with parts needs (added to 17g's own requirements)

def to_submit(conn, c: dict) -> list[str]:
    if c["kind"] != "product" or not conn.execute("select 1 from plm_change_items where change_id = %s",
                                                  (c["id"],)).fetchone():
        return []
    out = []
    if effect(conn, c["id"]) is None:
        out.append(say("how the design change takes effect"))
    imp = impact(conn, c["id"])
    if imp is None or not imp["current"]:
        out.append(say("an impact analysis of the parts it changes as they are now"))
    return out


def to_implement(conn, c: dict) -> list[str]:
    out = []
    for it in items(conn, c["id"]):
        if it["scope"] in ("part", "both") and (it["new_part"] or {}).get("status") != "released":
            out.append(say("a new revision of {code}, released under this change", code=it["item_code"]))
        if it["scope"] in ("bom", "both") and (it["new_bom"] or {}).get("status") != "released":
            out.append(say("a new BOM revision of {code}, released under this change", code=it["item_code"]))
    return out


def allows(conn, change_id: int, pid: int, what: str) -> None:
    """A change that lists parts starts new revisions only of those parts, for what it says changes."""
    rows = conn.execute("select part_id, scope from plm_change_items where change_id = %s", (change_id,)).fetchall()
    if not rows:
        return
    scope = next((r["scope"] for r in rows if r["part_id"] == pid), None)
    if scope not in ("both", what):
        raise PlmError(say("this change does not list this part for: {what}", what=say("scope::" + what)))
