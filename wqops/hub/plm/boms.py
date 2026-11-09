"""Design BOMs, step 26b (ADR-0026 item 4): a made part's BOM has revisions; the draft is edited in the hub,
released with a signature once its checks pass, and then becomes a Draft BOM in ERPNext that a person submits there
(WenQuest Ops never submits ERPNext documents). Production uses only released revisions. A new revision rests on an
approved product change (17g).
"""

from __future__ import annotations

from decimal import Decimal

from psycopg.types.json import Jsonb

from wqops.erp import ErpClient
from wqops.hub.plm import parts as PT
from wqops.hub.plm import place as PL
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
    rows = conn.execute("select l.pos, l.qty, l.uom, l.note, jsonb_array_length(l.placements) as placed, p.id as "
                        "part_id, p.item_code as code, p.name, p.status as part_status, p.source, p.category from "
                        "plm_bom_lines l join plm_parts p on p.id = l.part_id where l.bom_id = %s order by l.pos",
                        (bid,)).fetchall()
    return [dict(r, qty=R.qty_text(r["qty"])) for r in rows]


def _count(q: Decimal) -> int | None:
    return int(q) if q == q.to_integral_value() else None


def _supplier(conn, code: str) -> bool | None:
    """Has the bought part an approved supplier in the approved supplier list? None when the list says nothing."""
    rows = conn.execute("select status from asl_entries where item_code = %s", (code,)).fetchall()
    if not rows:
        return None
    return any(r["status"] in ("approved", "conditional") for r in rows)


def _uses(conn, skip_part: int) -> dict[int, list[int]]:
    """For every other part with a BOM: the parts its released and its draft revisions use (both count: production
    uses the released one, the draft may be released next)."""
    out: dict[int, set[int]] = {}
    rows = conn.execute("select b.part_id, l.part_id as child from plm_boms b join plm_bom_lines l on l.bom_id = b.id "
                        "where b.part_id <> %s and b.status <> 'superseded'", (skip_part,)).fetchall()
    for r in rows:
        out.setdefault(r["part_id"], set()).add(r["child"])
    return {k: sorted(v) for k, v in out.items()}


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
            from wqops.hub.plm import ecn as ECN  # noqa: PLC0415 - ecn imports parts

            ECN.allows(conn, ch["id"], pid, "bom")
        last = next((r for r in reversed(revs) if r["status"] == "released"), None)
        b = conn.execute("insert into plm_boms (part_id, revision, change_id, editors, created_by) values "
                         "(%s, %s, %s, %s, %s) returning *",
                         (pid, R.next_revision(revs[-1]["revision"] if revs else None), ch["id"] if ch else None,
                          [user["email"]], user["email"])).fetchone()
        if last:
            conn.execute("insert into plm_bom_lines (bom_id, pos, part_id, qty, uom, note, placements) select %s, "
                         "pos, part_id, qty, uom, note, placements from plm_bom_lines where bom_id = %s",
                         (b["id"], last["id"]))
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
    before = {r["part_id"]: r["placements"] for r in conn.execute(
        "select part_id, placements from plm_bom_lines where bom_id = %s", (bid,))}
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
        uom = str(r.get("uom") or "").strip() or part["uom"]
        if uom != part["uom"]:      # unit conversions in a BOM: later, with ERPNext's conversion factors
            raise PlmError(say("line {n}: {code} counts in {uom}", n=n, code=part["item_code"], uom=part["uom"]))
        # where each use sits (FreeCAD, STEP): sent with the row, else kept from before while it still fits
        if "placements" in r:
            try:
                pl = PL.clean_list(r["placements"] or [], _count(Decimal(q)))
            except PL.PlaceError as exc:
                raise PlmError(say("line {n}: {error}", n=n, error=str(exc))) from exc
        else:
            pl = before.get(part["id"]) or []
            if len(pl) != (_count(Decimal(q)) or -1):
                pl = []
        clean.append((n, part["id"], q, uom, str(r.get("note") or "").strip()[:500], Jsonb(pl)))
    with conn.transaction():
        if conn.execute("select status from plm_boms where id = %s for update", (bid,)).fetchone()["status"] != "draft":
            raise PlmError(say("the BOM moved on meanwhile: open it again"))
        conn.execute("delete from plm_bom_lines where bom_id = %s", (bid,))
        for row in clean:
            conn.execute("insert into plm_bom_lines (bom_id, pos, part_id, qty, uom, note, placements) values "
                         "(%s, %s, %s, %s, %s, %s, %s)", (bid, *row))
        conn.execute("update plm_boms set note = %s, updated_at = now(), editors = case when %s = any(editors) then "
                     "editors else editors || %s end where id = %s",
                     (b["note"] if note is None else str(note).strip()[:2000], user["email"], [user["email"]], bid))
        PT.log(conn, "bom", bid, user["email"], "lines saved", say("{n} lines", n=len(clean)))
    return view(conn, bid, erp)


def _same_lines(doc: dict, ls: list[dict]) -> bool:
    have = sorted((r.get("item_code"), Decimal(str(r.get("qty") or 0)).normalize()) for r in doc.get("items") or [])
    want = sorted((x["code"], Decimal(x["qty"]).normalize()) for x in ls)
    return have == want


def _erp_bom(erp: ErpClient, b: dict, part: dict, ls: list[dict]) -> str:
    """The ERPNext BOM with exactly these lines for the item: one made before an answer got lost is found again
    (no second one); else a new Draft."""
    for x in erp.list("BOM", filters=[["item", "=", part["item_code"]], ["docstatus", "<", 2]],
                      fields=["name", "docstatus"], order_by="modified desc", limit=20):
        doc = erp.get("BOM", x["name"])
        if doc is not None and _same_lines(doc, ls):
            return x["name"]
    doc = erp.insert({"doctype": "BOM", "item": part["item_code"], "quantity": 1, "is_active": 1, "is_default": 1,
                      "items": [{"item_code": x["code"], "qty": float(Decimal(x["qty"])), "uom": x["uom"]} for x in ls],
                      "docstatus": 0})
    if int(doc.get("docstatus") or 0) != 0:
        raise PlmError(say("ERPNext returned {name} with docstatus {docstatus}", name=doc["name"],
                           docstatus=doc["docstatus"]))
    return doc["name"]


def to_erp(conn, user: dict, bid: int, erp: ErpClient) -> dict:
    """Make the Draft BOM in ERPNext for a released revision (again, if it failed). The BOM row stays locked while
    ERPNext is asked, so two clicks make one BOM."""
    with conn.transaction():
        b = conn.execute("select * from plm_boms where id = %s for update", (bid,)).fetchone()
        if b is None:
            raise KeyError(bid)
        if b["status"] == "draft":
            raise PlmError(say("release the BOM first"))
        if b["erp_bom"]:
            raise PlmError(say("the BOM is already in ERPNext as {name}", name=b["erp_bom"]))
        part = PT.get(conn, b["part_id"])
        try:
            name, err = _erp_bom(erp, b, part, lines(conn, bid)), None
        except Exception as exc:
            name, err = None, f"{type(exc).__name__}: {exc}"[:1000]
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
    PT.change_still_holds(conn, b["change_id"])
    Q.check_signer(conn, user, password)
    part = PT.get(conn, b["part_id"])
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (b["part_id"],))
        b = conn.execute("select * from plm_boms where id = %s for update", (bid,)).fetchone()
        if b["status"] != "draft":
            raise PlmError(say("the BOM moved on meanwhile: open it again"))
        cs = checks(conn, b)                         # again under the lock: what is signed is what was checked
        if not R.passed(cs):
            bad = [c["check"] for c in cs if c["result"] != "pass"]
            raise PlmError(say("not ready to release: {list}", list=Q.join(bad)))
        PT.change_still_holds(conn, b["change_id"])
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


STEP_FILES = (".step", ".stp")
MAX_SCENE = 3000          # placed models in one 3D view
MAX_DEPTH = 8


def _model(conn, pid: int) -> dict | None:
    """The STEP model on the part's current revision, if it has one."""
    rev = PT.current(conn, pid)
    return next((f for f in PT.files(conn, rev["id"]) if f["name"].lower().endswith(STEP_FILES)), None) if rev else None


def _shown_bom(conn, pid: int) -> int | None:
    r = conn.execute("select id from plm_boms where part_id = %s and status <> 'superseded' order by "
                     "(status = 'released') desc, id desc limit 1", (pid,)).fetchone()
    return r["id"] if r else None


def scene(conn, bid: int, *, group: bool = False) -> dict:
    """Everything under the BOM in its frame, for the 3D view: each use of a part with a STEP model where it sits
    (a 4x4 matrix); an assembly without its own model is shown through its BOM. Lines without placements or
    models are listed, never guessed (round 124 rule 2). group: each item says which line of this BOM it belongs to
    (``line``: that line's part id), for the exploded view, where a sub-assembly moves as one block."""
    b = get(conn, bid)
    items, missing, cut = [], {}, False

    def miss(ln, why: str) -> None:
        missing.setdefault(ln["item_code"], {"code": ln["item_code"], "name": ln["name"], "why": why})

    def walk(bom_id: int, m: list[float], depth: int, trail: frozenset, top: int | None = None,  # noqa: PLR0917
             use: int = 0) -> None:
        nonlocal cut
        for ln in conn.execute("select l.part_id, l.placements, p.item_code, p.name from plm_bom_lines l join "
                               "plm_parts p on p.id = l.part_id where l.bom_id = %s order by l.pos",
                               (bom_id,)).fetchall():
            f = _model(conn, ln["part_id"])
            sub = None if f else _shown_bom(conn, ln["part_id"])
            if f is None and sub is None:
                miss(ln, "model")
                continue
            if not ln["placements"]:
                miss(ln, "placement")
                continue
            for i, pl in enumerate(ln["placements"]):
                mm = PL.mul(m, PL.matrix(pl))
                at = use if top else i          # which use of this BOM's own line it is part of
                if f is not None:
                    if len(items) >= MAX_SCENE:
                        cut = True
                        return
                    items.append({"part_id": ln["part_id"], "code": ln["item_code"], "name": ln["name"],
                                  "file": {"id": f["id"], "name": f["name"], "sha256": f["sha256"]}, "m": mm,
                                  **({"line": top or ln["part_id"], "use": at} if group else {})})
                elif depth < MAX_DEPTH and ln["part_id"] not in trail:
                    walk(sub, mm, depth + 1, trail | {ln["part_id"]}, top or ln["part_id"], at)

    walk(bid, PL.IDENTITY, 0, frozenset({b["part_id"]}))
    return {"bom": bid, "items": items, "missing": list(missing.values()), "cut": cut}
