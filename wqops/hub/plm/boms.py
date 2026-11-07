"""Design BOMs, step 26b (ADR-0026 item 4): a made part's BOM has revisions; the draft is edited in the hub,
released with a signature once its checks pass, and then becomes a Draft BOM in ERPNext that a person submits there
(WenQuest Ops never submits ERPNext documents). Production uses only released revisions. A new revision rests on an
approved product change (17g).
"""

from __future__ import annotations

from decimal import Decimal

from wqops.erp import ErpClient
from wqops.hub.plm import parts as PT
from wqops.hub.plm import rules as R
from wqops.hub.quality import records as Q
from wqops.i18n import say

PlmError = PT.PlmError
MAX_LINES = 2000


def get(conn, bid: int) -> dict:
    row = conn.execute("select * from plm_boms where id = %s", (bid,)).fetchone()
    if row is None:
        raise KeyError(bid)
    return row


def lines(conn, bid: int) -> list[dict]:
    rows = conn.execute("select l.pos, l.qty, l.uom, l.note, p.id as part_id, p.item_code as code, p.name, p.status "
                        "as part_status, p.source, p.category from plm_bom_lines l join plm_parts p "
                        "on p.id = l.part_id where l.bom_id = %s order by l.pos", (bid,)).fetchall()
    return [dict(r, qty=str(r["qty"].normalize() if isinstance(r["qty"], Decimal) else r["qty"])) for r in rows]


def _supplier(conn, code: str) -> bool | None:
    """Has the bought part an approved supplier in the approved supplier list? None when the list says nothing."""
    rows = conn.execute("select status from asl_entries where item_code = %s", (code,)).fetchall()
    if not rows:
        return None
    return any(r["status"] in ("approved", "conditional") for r in rows)


def _uses(conn, skip_part: int) -> dict[int, list[int]]:
    """For every part with a BOM: the parts its newest BOM revision uses."""
    out: dict[int, list[int]] = {}
    rows = conn.execute("select distinct on (b.part_id) b.part_id, b.id from plm_boms b where b.part_id <> %s "
                        "order by b.part_id, b.id desc", (skip_part,)).fetchall()
    for r in rows:
        out[r["part_id"]] = [x["part_id"] for x in conn.execute("select part_id from plm_bom_lines where bom_id = %s",
                                                                (r["id"],))]
    return out


def checks(conn, bom: dict) -> list[dict]:
    ls = lines(conn, bom["id"])
    for x in ls:
        x["approved_supplier"] = _supplier(conn, x["code"]) if x["source"] == "buy" else True
    loop = R.cycle(bom["part_id"], [x["part_id"] for x in ls], _uses(conn, bom["part_id"]))
    names = None
    if loop:
        codes = {r["id"]: r["item_code"] for r in conn.execute("select id, item_code from plm_parts where id = any(%s)",
                                                               (loop,))}
        names = [codes[i] for i in loop]
    out = R.bom_checks(ls, names)
    item = R.part_checks(PT.get(conn, bom["part_id"]), {"params": {}})[1]
    return [*out, {**item, "check": say("the assembly is an item in ERPNext")}]


def erp_status(erp: ErpClient | None, name: str | None) -> str:
    """draft | submitted | cancelled | none (not made yet) | unknown (ERPNext did not answer)."""
    if not name:
        return "none"
    try:
        doc = erp.get("BOM", name) if erp else None
    except Exception:
        return "unknown"
    if doc is None:
        return "unknown"
    return {0: "draft", 1: "submitted", 2: "cancelled"}.get(int(doc.get("docstatus") or 0), "unknown")


def view(conn, bid: int, erp: ErpClient | None = None) -> dict:
    b = get(conn, bid)
    p = PT.get(conn, b["part_id"])
    ls = lines(conn, bid)
    out = {"bom": PT._iso(dict(b)), "part": {"id": p["id"], "code": p["item_code"], "name": p["name"],
                                              "status": p["status"], "uom": p["uom"]},
           "lines": ls, "revisions": [PT._iso(dict(r)) for r in conn.execute(
               "select id, revision, status, released_at, erp_bom from plm_boms where part_id = %s order by id",
               (b["part_id"],))],
           "signatures": Q.signatures(conn, "plm-bom", bid), "history": PT.history(conn, "bom", bid)}
    if b["change_id"]:
        ch = conn.execute("select id, name, title, status from changes where id = %s", (b["change_id"],)).fetchone()
        out["change"] = dict(ch) if ch else None
    if b["status"] == "draft":
        out["checks"] = checks(conn, b)
        out["ready"] = R.passed(out["checks"])
    if b["status"] != "draft":
        out["erp_status"] = erp_status(erp, b["erp_bom"])
    prev = conn.execute("select id, revision from plm_boms where part_id = %s and id < %s and status <> 'draft' "
                        "order by id desc limit 1", (b["part_id"], bid)).fetchone()
    if prev:
        out["previous"] = {"id": prev["id"], "revision": prev["revision"],
                           "diff": R.diff(lines(conn, prev["id"]), ls)}
    return out


def start(conn, user: dict, pid: int, change_id=None) -> dict:
    """The first BOM of a made part (revision A), or a new revision of a released one under an approved product
    change: the lines of the latest released revision are copied into it."""
    p = PT.get(conn, pid)
    if p["source"] != "make":
        raise PlmError(say("a bought part has no BOM"))
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (pid,))
        revs = conn.execute("select * from plm_boms where part_id = %s order by id", (pid,)).fetchall()
        if any(r["status"] == "draft" for r in revs):
            raise PlmError(say("the part already has a draft BOM"))
        ch = None
        if revs:
            ch = PT.approved_change(conn, change_id)
        last = next((r for r in reversed(revs) if r["status"] == "released"), None)
        b = conn.execute("insert into plm_boms (part_id, revision, change_id, editors, created_by) values "
                         "(%s, %s, %s, %s, %s) returning *",
                         (pid, R.next_revision(revs[-1]["revision"] if revs else None), ch["id"] if ch else None,
                          [user["email"]], user["email"])).fetchone()
        if last:
            conn.execute("insert into plm_bom_lines (bom_id, pos, part_id, qty, uom, note) select %s, pos, "
                         "part_id, qty, uom, note from plm_bom_lines where bom_id = %s", (b["id"], last["id"]))
        PT.log(conn, "bom", b["id"], user["email"], "created",
               f"{p['item_code']} BOM rev {b['revision']}" + (f" ({ch['name']})" if ch else ""))
    return view(conn, b["id"])


def set_lines(conn, user: dict, bid: int, rows, *, note: str | None = None,  # noqa: PLR0912
              erp: ErpClient | None = None) -> dict:
    """Replace the lines of a draft BOM. Each row: code (or part_id), qty, uom (the part's unit if left out), note."""
    b = get(conn, bid)
    if b["status"] != "draft":
        raise PlmError(say("the BOM is released: start a new revision under an approved change"))
    if not isinstance(rows, list) or len(rows) > MAX_LINES:
        raise PlmError(say("lines are a list of up to {n} rows", n=MAX_LINES))
    clean = []
    seen = set()
    for n, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            raise PlmError(say("line {n}: not a row", n=n))
        part = None
        if type(r.get("part_id")) is int:
            part = conn.execute("select * from plm_parts where id = %s", (r["part_id"],)).fetchone()
        elif r.get("code"):
            part = PT.by_code(conn, str(r["code"]).strip())
        if part is None:
            raise PlmError(say("line {n}: no such part {code}", n=n, code=r.get("code") or r.get("part_id") or ""))
        if part["id"] == b["part_id"]:
            raise PlmError(say("line {n}: a part is not in its own BOM", n=n))
        if part["status"] == "obsolete":
            raise PlmError(say("line {n}: {code} is obsolete", n=n, code=part["item_code"]))
        if part["id"] in seen:
            raise PlmError(say("line {n}: {code} is already on the BOM; change its quantity instead", n=n,
                               code=part["item_code"]))
        seen.add(part["id"])
        try:
            q = R.qty(r.get("qty"))
        except ValueError as exc:
            raise PlmError(say("line {n}: {error}", n=n, error=str(exc))) from exc
        clean.append((n, part["id"], q, str(r.get("uom") or part["uom"]).strip()[:40] or part["uom"],
                      str(r.get("note") or "").strip()[:500]))
    with conn.transaction():
        if get(conn, bid)["status"] != "draft":
            raise PlmError(say("the BOM moved on meanwhile: open it again"))
        conn.execute("delete from plm_bom_lines where bom_id = %s", (bid,))
        for row in clean:
            conn.execute("insert into plm_bom_lines (bom_id, pos, part_id, qty, uom, note) values (%s, %s, %s, %s, %s, "
                         "%s)", (bid, *row))
        conn.execute("update plm_boms set note = %s, updated_at = now(), editors = case when %s = any(editors) then "
                     "editors else editors || %s end where id = %s",
                     (b["note"] if note is None else str(note).strip()[:2000], user["email"], [user["email"]], bid))
        PT.log(conn, "bom", bid, user["email"], "lines saved", say("{n} lines", n=len(clean)))
    return view(conn, bid, erp)


def _erp_bom(erp: ErpClient, b: dict, part: dict, ls: list[dict]) -> str:
    doc = erp.insert({"doctype": "BOM", "item": part["item_code"], "quantity": 1, "is_active": 1, "is_default": 1,
                      "remarks": f"WenQuest Ops PLM rev {b['revision']}",
                      "items": [{"item_code": x["code"], "qty": float(Decimal(x["qty"])), "uom": x["uom"]} for x in ls],
                      "docstatus": 0})
    if int(doc.get("docstatus") or 0) != 0:
        raise PlmError(say("ERPNext returned {name} with docstatus {docstatus}", name=doc["name"],
                           docstatus=doc["docstatus"]))
    return doc["name"]


def to_erp(conn, user: dict, bid: int, erp: ErpClient) -> dict:
    """Make the Draft BOM in ERPNext for a released revision (again, if it failed)."""
    b = get(conn, bid)
    if b["status"] == "draft":
        raise PlmError(say("release the BOM first"))
    if b["erp_bom"]:
        raise PlmError(say("the BOM is already in ERPNext as {name}", name=b["erp_bom"]))
    part = PT.get(conn, b["part_id"])
    try:
        name, err = _erp_bom(erp, b, part, lines(conn, bid)), None
    except Exception as exc:
        name, err = None, f"{type(exc).__name__}: {exc}"[:1000]
    with conn.transaction():
        conn.execute("update plm_boms set erp_bom = %s, erp_error = %s where id = %s", (name, err, bid))
        PT.log(conn, "bom", bid, user["email"], "draft BOM in ERPNext" if name else "ERPNext BOM failed", name or err)
    return view(conn, bid, erp)


def release(conn, user: dict, bid: int, password: str, erp: ErpClient) -> dict:
    b = get(conn, bid)
    if b["status"] != "draft":
        raise PlmError(say("there is no draft revision to release"))
    cs = checks(conn, b)
    if not R.passed(cs):
        bad = [c["check"] for c in cs if c["result"] != "pass"]
        raise PlmError(say("not ready to release: {list}", list=Q.join(bad)))
    Q.check_signer(conn, user, password)
    part = PT.get(conn, b["part_id"])
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (b["part_id"],))
        if get(conn, bid)["status"] != "draft":
            raise PlmError(say("the BOM moved on meanwhile: open it again"))
        conn.execute("update plm_boms set status = 'superseded' where part_id = %s and status = 'released'",
                     (b["part_id"],))
        conn.execute("update plm_boms set status = 'released', released_by = %s, released_at = now() where id = %s",
                     (user["email"], bid))
        Q._sign(conn, user, say("BOM revision released"), "plm-bom", bid,
                f"{part['item_code']} BOM rev {b['revision']}")
        PT.log(conn, "bom", bid, user["email"], "revision released", f"rev {b['revision']}")
    return to_erp(conn, user, bid, erp)


def compare(conn, a: int, b: int) -> dict:
    x, y = get(conn, a), get(conn, b)
    if x["part_id"] != y["part_id"]:
        raise PlmError(say("compare two revisions of the same BOM"))
    return {"from": x["revision"], "to": y["revision"], "diff": R.diff(lines(conn, a), lines(conn, b))}
