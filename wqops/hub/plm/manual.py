"""The parts manual (PLM step 27c, WenQuest round 124): from a machine (or any assembly whose BOM is released), one
page per assembly in its BOM tree: the exploded view as saved and the table of parts, Chinese and English. Kept as
editions: generating freezes what the BOMs and pages are then; a later change of a BOM needs a new edition. A PDF
for printing, and read-only links for dealers (no sign-in, revocable, counted) that show the pictures and tables:
never the 3D models, which are design data."""

from __future__ import annotations

import hashlib
import secrets

from psycopg.types.json import Jsonb

from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import explode as EX
from wqops.hub.plm import parts as PT
from wqops.hub.plm.parts import PlmError
from wqops.i18n import say

MAX_PAGES = 400


def _released_bom(conn, pid: int) -> dict | None:
    """The BOM the manual shows: the released one (a new revision being drafted does not count yet), else the
    newest draft (which stops the manual)."""
    bid = B._shown_bom(conn, pid)
    return dict(B.get(conn, bid)) if bid else None


def readiness(conn, pid: int) -> dict:
    """What generating would give, and what stops it: BOMs not released, pages without a picture, English names
    not confirmed."""
    part = PT.get(conn, pid)
    root = _released_bom(conn, pid)
    if root is None:
        return {"ok": False, "boms": [], "not_released": [{"code": part["item_code"], "name": part["name"]}],
                "no_picture": [], "names_open": 0}
    order, seen, todo, not_rel, no_pic = [], set(), [pid], [], []
    while todo:                              # depth first, in BOM order; an assembly used twice is one page
        p = todo.pop(0)
        if p in seen:
            continue
        seen.add(p)
        b = _released_bom(conn, p)
        if b is None:
            continue
        pp = PT.get(conn, p)
        if b["status"] != "released":
            not_rel.append({"code": pp["item_code"], "name": pp["name"], "bom": b["id"], "revision": b["revision"]})
        order.append(b)
        kids = [r["part_id"] for r in conn.execute("select part_id from plm_bom_lines where bom_id = %s order by pos",
                                                   (b["id"],))]
        todo[:0] = [k for k in kids if _released_bom(conn, k) is not None]
        if len(order) > MAX_PAGES:
            raise PlmError(say("more than {n} pages", n=MAX_PAGES))
    for b in order:
        e = conn.execute("select snapshot_sha from plm_explodes where bom_id = %s", (b["id"],)).fetchone()
        if not (e and e["snapshot_sha"]):
            pp = PT.get(conn, b["part_id"])
            no_pic.append({"code": pp["item_code"], "name": pp["name"], "bom": b["id"]})
    names_open = sum(1 for p in EX.tree_parts(conn, root["id"]) if p["name_en_state"] != "confirmed")
    return {"ok": not not_rel, "boms": [b["id"] for b in order], "not_released": not_rel, "no_picture": no_pic,
            "names_open": names_open}


def _page(conn, bid: int, page_of: dict[int, int]) -> dict:
    b = B.get(conn, bid)
    p = PT.get(conn, b["part_id"])
    e = conn.execute("select snapshot_sha from plm_explodes where bom_id = %s", (bid,)).fetchone()
    lines = []
    for ln in EX.lines(conn, bid):
        lines.append({"no": ln["no"], "code": ln["code"], "name": ln["name"],
                      "name_en": ln["name_en"] if ln["name_en_state"] == "confirmed" else "",
                      "qty": ln["qty"], "uom": ln["uom"], "page": page_of.get(ln["part_id"]), "note": ln["note"]})
    return {"bom": bid, "revision": b["revision"], "code": p["item_code"], "name": p["name"],
            "name_en": p["name_en"] if p["name_en_state"] == "confirmed" else "",
            "picture": e["snapshot_sha"] if e and e["snapshot_sha"] else None, "lines": lines}


def _changes(old: list[dict], new: list[dict]) -> list[dict]:
    """Per page (by assembly code): parts added, removed, quantity changed."""
    was = {p["code"]: {x["code"]: x for x in p["lines"]} for p in old}
    out = []
    for p in new:
        before, now = was.get(p["code"]), {x["code"]: x for x in p["lines"]}
        if before is None:
            out.append({"page": p["code"], "name": p["name"], "change": "new page"})
            continue
        for c in now.keys() - before.keys():
            out.append({"page": p["code"], "code": c, "name": now[c]["name"], "change": "added"})
        for c in before.keys() - now.keys():
            out.append({"page": p["code"], "code": c, "name": before[c]["name"], "change": "removed"})
        for c in now.keys() & before.keys():
            if now[c]["qty"] != before[c]["qty"]:
                out.append({"page": p["code"], "code": c, "name": now[c]["name"], "change": "quantity",
                            "old": before[c]["qty"], "new": now[c]["qty"]})
    gone = {p["code"] for p in old} - {p["code"] for p in new}
    out += [{"page": c, "change": "page removed"} for c in sorted(gone)]
    return out


def generate(conn, user: dict, pid: int, *, today) -> dict:
    """A new edition: the pages frozen as they are now, the PDF made, the changes from the edition before."""
    from wqops.hub.plm import manual_pdf as MP  # noqa: PLC0415 - ReportLab only when a manual is made

    r = readiness(conn, pid)
    if not r["ok"]:
        raise PlmError(say("not every BOM in the tree is released: {list}",
                           list=", ".join(f"{x['code']} {x['name']}" for x in r["not_released"][:10])))
    page_of = {}
    for n, bid in enumerate(r["boms"], start=1):
        page_of[B.get(conn, bid)["part_id"]] = n
    pages = [_page(conn, bid, page_of) for bid in r["boms"]]
    part = PT.get(conn, pid)
    prev = conn.execute("select edition, pages from plm_manuals where part_id = %s order by edition desc limit 1",
                        (pid,)).fetchone()
    edition = (prev["edition"] + 1) if prev else 1
    changes = _changes(prev["pages"], pages) if prev else []
    head = {"code": part["item_code"], "name": part["name"],
            "name_en": part["name_en"] if part["name_en_state"] == "confirmed" else "", "edition": edition}
    pdf = MP.build(head, pages, changes, picture=F.get, today=today)
    with conn.transaction():
        row = conn.execute("insert into plm_manuals (part_id, edition, pages, changes, pdf_sha, names_open, "
                           "created_by) values (%s, %s, %s, %s, %s, %s, %s) returning id",
                           (pid, edition, Jsonb(pages), Jsonb(changes), F.put(pdf), r["names_open"],
                            user["email"])).fetchone()
        PT.log(conn, "part", pid, user["email"], "parts manual",
               say("edition {n}, {p} pages", n=edition, p=len(pages)))
    return get(conn, row["id"])


def get(conn, mid: int) -> dict:
    r = conn.execute("select m.*, p.item_code, p.name from plm_manuals m join plm_parts p on p.id = m.part_id where "
                     "m.id = %s", (mid,)).fetchone()
    if r is None:
        raise KeyError(mid)
    return PT._iso(dict(r))


def overview(conn, pid: int) -> dict:
    eds = [PT._iso(dict(r)) for r in conn.execute(
        "select id, edition, created_by, created_at, names_open, jsonb_array_length(pages) as pages, "
        "jsonb_array_length(changes) as changes from plm_manuals where part_id = %s order by edition desc", (pid,))]
    links = [PT._iso(dict(r)) for r in conn.execute(
        "select id, label, created_by, created_at, revoked_at, revoked_by, views, last_view_at from "
        "plm_manual_links where part_id = %s order by id desc", (pid,))]
    return {"readiness": readiness(conn, pid), "editions": eds, "links": links}


def pdf(conn, mid: int) -> tuple[str, bytes]:
    m = get(conn, mid)
    return f"{m['item_code']}-manual-{m['edition']}.pdf", F.get(m["pdf_sha"])


def picture(conn, mid: int, n: int) -> bytes:
    pages = get(conn, mid)["pages"]
    if not 1 <= n <= len(pages) or not pages[n - 1]["picture"]:
        raise KeyError(n)
    return F.get(pages[n - 1]["picture"])


# ---- read-only links for dealers

def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def add_link(conn, user: dict, pid: int, label: str) -> dict:
    """A link to the newest edition. The token is shown once; only its hash is kept."""
    PT.get(conn, pid)
    if not conn.execute("select 1 from plm_manuals where part_id = %s", (pid,)).fetchone():
        raise PlmError(say("make an edition of the manual first"))
    token = secrets.token_urlsafe(24)
    with conn.transaction():
        r = conn.execute("insert into plm_manual_links (part_id, token_sha, label, created_by) values (%s, %s, %s, %s) "
                         "returning id", (pid, _sha(token), " ".join(str(label or "").split())[:120],
                                          user["email"])).fetchone()
        PT.log(conn, "part", pid, user["email"], "manual link", label or "")
    return {"id": r["id"], "token": token}


def revoke(conn, user: dict, lid: int) -> dict:
    with conn.transaction():
        r = conn.execute("update plm_manual_links set revoked_at = now(), revoked_by = %s where id = %s and "
                         "revoked_at is null returning part_id", (user["email"], lid)).fetchone()
        if r is None:
            raise PlmError(say("no such link, or it is revoked already"))
        PT.log(conn, "part", r["part_id"], user["email"], "manual link revoked", str(lid))
    return overview(conn, r["part_id"])


def by_token(conn, token: str, *, count: bool = False) -> dict | None:
    """The newest edition behind a link; None when the link is unknown; {"revoked": True} when revoked."""
    if not token or len(token) > 100:
        return None
    ln = conn.execute("select * from plm_manual_links where token_sha = %s", (_sha(token),)).fetchone()
    if ln is None:
        return None
    if ln["revoked_at"] is not None:
        return {"revoked": True}
    m = conn.execute("select id from plm_manuals where part_id = %s order by edition desc limit 1",
                     (ln["part_id"],)).fetchone()
    if count:
        conn.execute("update plm_manual_links set views = views + 1, last_view_at = now() where id = %s", (ln["id"],))
    return get(conn, m["id"])
