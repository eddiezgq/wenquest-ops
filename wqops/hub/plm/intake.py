"""The design data inbox, step 26e (ADR-0026): a batch from FreeCAD (machine token, scope plm:send), a STEP file or
an Excel BOM is a list of parts (nodes) and how they are assembled (links). An engineer matches each node to an
existing part or says it is new, picks an approved design change for any assembly whose BOM is released, and
writes the batch with a signature: new parts are made (with their ERPNext items), STEP files go onto draft
revisions, BOMs become drafts. Nothing is released; what came in is kept as it came.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from psycopg.types.json import Jsonb

from wqops.erp import ErpClient
from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import catalog as CAT
from wqops.hub.plm import parts as PT
from wqops.hub.plm import readers as RD
from wqops.hub.quality import records as Q
from wqops.i18n import say

PlmError = PT.PlmError
MAX_PENDING = 200
ERP_CHUNK = 80          # codes asked of ERPNext per request


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _t(v, n: int) -> str:
    """Text from a batch: control characters (NUL among them) dropped, trimmed, cut to n."""
    return _CTRL.sub(" ", str(v if v is not None else "")).strip()[:n]


def check_data(data) -> dict:  # noqa: PLR0912 - one check after another
    """The shape every source gives: nodes with unique keys, links between them with quantities above 0."""
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not data["nodes"]:
        raise PlmError(say("the batch names no parts"))
    if len(data["nodes"]) > RD.MAX_NODES:
        raise PlmError(say("more than {n} parts in one file", n=RD.MAX_NODES))
    nodes, keys = [], set()
    for n in data["nodes"]:
        if not isinstance(n, dict) or not _t(n.get("key"), 200):
            raise PlmError(say("every part in the batch needs a key"))
        k = _t(n["key"], 200)
        if k in keys:
            raise PlmError(say("the key {key} is used twice", key=k))
        keys.add(k)
        x = {"key": k, "code": _t(n.get("code"), 60), "name": _t(n.get("name"), 140) or k[:140]}
        for f in ("uom", "category", "source", "material"):
            if n.get(f) and _t(n[f], 60):
                x[f] = _t(n[f], 60)
        for f in ("volume_mm3", "mass_kg"):
            if isinstance(n.get(f), int | float) and not isinstance(n.get(f), bool) and n[f] >= 0:
                x[f] = n[f]
        nodes.append(x)
    links = []
    for raw_ln in data.get("links") or []:
        if not isinstance(raw_ln, dict):
            raise PlmError(say("a link joins two parts of the batch"))
        ln = {**raw_ln, "parent": _t(raw_ln.get("parent"), 200), "child": _t(raw_ln.get("child"), 200)}
        if ln["parent"] not in keys or ln["child"] not in keys:
            raise PlmError(say("a link joins two parts of the batch"))
        if ln["parent"] == ln["child"]:
            raise PlmError(say("a part is not in its own assembly"))
        try:
            q = Decimal(str(ln.get("qty", 1)))
        except (InvalidOperation, ValueError) as exc:
            raise PlmError(say("a link has a quantity above 0")) from exc
        if not q.is_finite() or q <= 0:
            raise PlmError(say("a link has a quantity above 0"))
        links.append({"parent": ln["parent"], "child": ln["child"], "qty": format(q.normalize(), "f")})
    loop = _cycle({k: [x["child"] for x in links if x["parent"] == k] for k in keys})
    if loop:
        names = {n["key"]: n["name"] for n in nodes}
        raise PlmError(say("the assembly contains itself: {path}", path=" → ".join(names.get(k, str(k)) for k in loop)))
    return {"nodes": nodes, "links": links}


def _cycle(graph: dict) -> list | None:
    """A path that comes back to where it started, if any."""
    state: dict = {}
    for start in graph:
        if state.get(start):
            continue
        stack = [(start, iter(graph.get(start, ())))]
        path, state[start] = [start], 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                path.pop()
                state[node] = 2
            elif state.get(nxt) == 1:
                return [*path[path.index(nxt):], nxt]
            elif not state.get(nxt):
                state[nxt] = 1
                path.append(nxt)
                stack.append((nxt, iter(graph.get(nxt, ()))))
    return None


def receive(conn, *, source: str, sent_by: str, data: dict, token_id: int | None = None, file_name: str = "",
            file_bytes: bytes | None = None, files: dict[str, tuple[str, bytes]] | None = None) -> dict:
    """A batch into the inbox. ``files``: node key -> (file name, STEP bytes) from FreeCAD."""
    clean = check_data(data)
    if token_id is not None and conn.execute("select count(*) as n from plm_intake where token_id = %s and status = "
                                             "'pending'", (token_id,)).fetchone()["n"] >= MAX_PENDING:
        raise PlmError(say("{n} batches from this sender wait already: decide them first", n=MAX_PENDING))
    keys = {n["key"] for n in clean["nodes"]}
    stored = {}
    for k, (name, raw) in (files or {}).items():
        if k not in keys:
            raise PlmError(say("a file belongs to no part of the batch: {key}", key=k))
        if not raw or len(raw) > F.MAX_BYTES:
            raise PlmError(say("the file is empty or larger than 50 MB"))
        stored[k] = {"name": str(name)[:200], "sha256": F.put(raw), "size": len(raw)}
    sha = F.put(file_bytes) if file_bytes else None
    with conn.transaction():
        row = conn.execute("insert into plm_intake (source, token_id, sent_by, file_name, file_sha, data, files, plan) "
                           "values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
                           (source, token_id, sent_by[:200], file_name[:200], sha, Jsonb(clean), Jsonb(stored),
                            Jsonb(suggest(conn, clean)))).fetchone()
        PT.log(conn, "intake", row["id"], None if token_id else sent_by, "batch received",
               say("{n} parts from {source}", n=len(clean["nodes"]), source=source))
    return view(conn, row["id"])


def read_file(kind: str, raw: bytes) -> dict:
    if not raw or len(raw) > F.MAX_BYTES:
        raise PlmError(say("the file is empty or larger than 50 MB"))
    try:
        return RD.read_step(raw) if kind == "step" else RD.read_excel(raw)
    except RD.ReadError as exc:
        raise PlmError(str(exc)) from exc
    except RecursionError as exc:
        raise PlmError(say("the file could not be read")) from exc


def upload(conn, user: dict, kind: str, name: str, raw: bytes, data: dict | None = None) -> dict:  # noqa: PLR0917
    if data is None:
        data = read_file(kind, raw)
    return receive(conn, source=kind, sent_by=user["email"], data=data, file_name=name, file_bytes=raw)


def suggest(conn, data: dict) -> dict:
    """A code that is a part already is matched; others are new, with a category guessed from the file or the name."""
    parents = {ln["parent"] for ln in data["links"]}
    plan = {}
    for n in data["nodes"]:
        p = PT.by_code(conn, n["code"]) if n["code"] else None
        if p:
            plan[n["key"]] = {"action": "match", "part_id": p["id"]}
        else:
            cat = CAT.guess(n.get("category"), n["name"], n["key"] in parents)
            src = n.get("source") if n.get("source") in PT.SOURCES else \
                ("buy" if cat in CAT.BOUGHT else "make")
            plan[n["key"]] = {"action": "new", "category": cat, "source": src, "uom": n.get("uom") or "Nos"}
    return plan


def listing(conn, status: str = "pending") -> list[dict]:
    rows = conn.execute("select id, source, sent_by, file_name, status, created_at, decided_by, decided_at, "
                        "jsonb_array_length(data->'nodes') as n from plm_intake where status = %s order by id desc "
                        "limit 200", (status,)).fetchall()
    return [PT._iso(dict(r)) for r in rows]


def _get(conn, iid: int, *, lock: bool = False) -> dict:
    sql = "select * from plm_intake where id = %s for update" if lock else "select * from plm_intake where id = %s"
    r = conn.execute(sql, (iid,)).fetchone()
    if r is None:
        raise KeyError(iid)
    return r


def _like(conn, name: str) -> list[dict]:
    words = [w for w in name.replace("（", " ").replace("(", " ").split() if len(w) >= 2][:3]
    if not words:
        return []
    rows = conn.execute("select id, item_code, name from plm_parts where status <> 'obsolete' and name ilike "
                        "any(%s) order by item_code limit 5", ([f"%{w}%" for w in words],)).fetchall()
    return [dict(r) for r in rows]


def _tree_order(data: dict) -> list[tuple[dict, int]]:
    """Nodes top down, each with its depth (0 at the top), so a long batch reads like the assembly."""
    kids, under = defaultdict(list), set()
    for ln in data["links"]:
        if ln["child"] not in kids[ln["parent"]]:
            kids[ln["parent"]].append(ln["child"])
        under.add(ln["child"])
    by, out, seen = {n["key"]: n for n in data["nodes"]}, [], set()
    stack = [(n["key"], 0) for n in reversed(data["nodes"]) if n["key"] not in under]
    while stack:
        k, d = stack.pop()
        if k in seen:                       # a part used in several assemblies is listed where it first comes
            continue
        seen.add(k)
        out.append((by[k], d))
        stack.extend((c, d + 1) for c in reversed(kids[k]))
    return out + [(n, 0) for n in data["nodes"] if n["key"] not in seen]


def view(conn, iid: int, erp: ErpClient | None = None) -> dict:
    r = _get(conn, iid)
    plan = r["plan"]
    children = defaultdict(list)
    for ln in r["data"]["links"]:
        children[ln["parent"]].append(ln)
    made = {}
    if r["status"] == "written" and (r["result"] or {}).get("ids"):
        made = {x["id"]: dict(x) for x in conn.execute("select id, item_code, name, status, source from plm_parts "
                                                        "where id = any(%s)", (list(r["result"]["ids"].values()),))}
    rows = []
    for n, depth in _tree_order(r["data"]):
        x = {**n, "plan": plan.get(n["key"]), "children": len(children.get(n["key"], [])),
             "file": r["files"].get(n["key"]), "depth": depth}
        p = plan.get(n["key"]) or {}
        if made:
            x["part"] = made.get(r["result"]["ids"].get(n["key"]))
        elif p.get("action") == "match":
            part = conn.execute("select id, item_code, name, status, source from plm_parts where id = %s",
                                (p["part_id"],)).fetchone()
            x["part"] = dict(part) if part else None
            if part and children.get(n["key"]):
                last = conn.execute("select id, revision, status from plm_boms where part_id = %s order by id desc "
                                    "limit 1", (part["id"],)).fetchone()
                x["bom"] = dict(last) if last else None
        elif r["status"] == "pending":
            x["like"] = _like(conn, n["name"])
        rows.append(x)
    return {**PT._iso({k: v for k, v in r.items() if k not in ("data", "plan", "files")}), "rows": rows,
            "links": r["data"]["links"], "changes": r["changes"], "history": PT.history(conn, "intake", iid),
            "problems": problems(conn, r, erp) if r["status"] == "pending" else [],
            "categories": [{"key": c["key"], "label": c["label"]} for c in CAT.shown()]}


def set_plan(conn, user: dict, iid: int, plan: dict, changes: dict | None = None) -> dict:
    if not isinstance(plan, dict) or (changes is not None and not isinstance(changes, dict)):
        raise PlmError(say("the plan is a list of parts and what each is"))
    with conn.transaction():
        r = _get(conn, iid, lock=True)
        if r["status"] != "pending":
            raise PlmError(say("this batch is decided"))
        keys = {n["key"] for n in r["data"]["nodes"]}
        clean = {}
        for k, p in (plan or {}).items():
            if k not in keys or not isinstance(p, dict):
                raise PlmError(say("no part {key} in the batch", key=k))
            if p.get("action") == "match":
                if type(p.get("part_id")) is not int or not conn.execute(
                        "select 1 from plm_parts where id = %s", (p["part_id"],)).fetchone():
                    raise PlmError(say("{key}: choose the part it is", key=k))
                clean[k] = {"action": "match", "part_id": p["part_id"]}
            elif p.get("action") == "new":
                if p.get("category") not in CAT.CATEGORIES or p.get("source") not in PT.SOURCES:
                    raise PlmError(say("{key}: choose a category and made or bought", key=k))
                clean[k] = {"action": "new", "category": p["category"], "source": p["source"],
                            "uom": str(p.get("uom") or "Nos").strip()[:40] or "Nos",
                            "link_existing": p.get("link_existing") is True}
            else:
                raise PlmError(say("{key}: match it to a part or make it new", key=k))
        ch = {}
        for k, cid in (changes or {}).items():
            if k not in keys or type(cid) is not int:
                raise PlmError(say("no part {key} in the batch", key=k))
            ch[k] = cid
        conn.execute("update plm_intake set plan = %s, changes = %s where id = %s",
                     (Jsonb({**r["plan"], **clean}), Jsonb(ch if changes is not None else r["changes"]), iid))
        PT.log(conn, "intake", iid, user["email"], "plan saved", say("{n} parts", n=len(clean)))
    return view(conn, iid)


def problems(conn, r: dict, erp: ErpClient | None = None, *, ask_erp: bool = True) -> list[str]:  # noqa: PLR0912, PLR0915
    """What stops writing the batch, all checked before anyone signs: every node planned; assemblies made in house;
    released BOMs under an approved product change that lists them; no part used twice; new parts whose code is a
    part already, or an ERPNext item not chosen to be linked; no part that ends up containing itself."""
    from wqops.hub.plm import ecn as ECN  # noqa: PLC0415 - ecn imports parts

    out = []
    plan = r["plan"]
    nodes = r["data"]["nodes"]
    parents = {ln["parent"] for ln in r["data"]["links"]}
    for n in nodes:
        p = plan.get(n["key"])
        if not p:
            out.append(say("{name}: match it to a part or make it new", name=n["name"]))
            continue
        part = None
        if p["action"] == "match":
            part = conn.execute("select source, status, item_code from plm_parts where id = %s",
                                (p["part_id"],)).fetchone()
            if part is None or part["status"] == "obsolete":
                out.append(say("{name}: the part it is matched to is obsolete", name=n["name"]))
                continue
        elif n["code"] and PT.by_code(conn, n["code"]):
            out.append(say("{name}: {code} is a part already: match it", name=n["name"], code=n["code"]))
        if n["key"] not in parents:
            continue
        if (part["source"] if part else p.get("source")) != "make":
            out.append(say("{name} has parts under it: it is a made assembly", name=n["name"]))
        elif part:
            last = conn.execute("select status from plm_boms where part_id = %s order by id desc limit 1",
                                (p["part_id"],)).fetchone()
            if last and last["status"] != "draft":
                cid = r["changes"].get(n["key"])
                if not cid:
                    out.append(say("{name}: its BOM is released: choose the approved design change it comes under",
                                   name=n["name"]))
                else:
                    try:
                        PT.approved_change(conn, cid)
                        ECN.allows(conn, cid, p["part_id"], "bom")
                    except PlmError as exc:
                        out.append(f"{n['name']}: {exc}")
    matched = [p["part_id"] for p in plan.values() if p.get("action") == "match"]
    if len(matched) != len(set(matched)):
        out.append(say("two rows are matched to the same part"))
    codes = [n["code"] for n in nodes if n["code"] and (plan.get(n["key"]) or {}).get("action") == "new"]
    twice = sorted({c for c in codes if codes.count(c) > 1})
    if twice:
        out.append(say("two new parts have the code {codes}: match one to the other's part", codes=", ".join(twice)))
    wanted = sorted({n["code"] for n in nodes if n["code"] and (plan.get(n["key"]) or {}).get("action") == "new"
                     and not (plan.get(n["key"]) or {}).get("link_existing")})
    if wanted and ask_erp and erp is not None:   # a page shown without ERPNext: it is asked on writing
        try:      # in pieces: a whole machine's codes in one request is too long a URL for ERPNext
            have = set()
            for i in range(0, len(wanted), ERP_CHUNK):
                part = wanted[i:i + ERP_CHUNK]
                have |= {x["name"] for x in erp.list("Item", filters=[["name", "in", part]], fields=["name"],
                                                      limit=len(part))}
        except Exception:
            have = None
        if have is None:
            out.append(say("ERPNext did not answer: whether these codes are items already is unknown"))
        for c in sorted(have or ()):
            out.append(say("{code} is an item in ERPNext already: tick 'link it' or match it", code=c))
    loop = _with_existing(conn, r)
    if loop:
        out.append(say("the assembly would contain itself: {path}", path=" → ".join(loop)))
    return out


def _with_existing(conn, r: dict) -> list[str] | None:
    """Cycles once the batch's BOMs replace those of the parts it matches."""
    plan, names = r["plan"], {n["key"]: n["name"] for n in r["data"]["nodes"]}
    ident = {k: ("p", p["part_id"]) if p.get("action") == "match" else ("n", k) for k, p in plan.items()}
    graph: dict = defaultdict(list)
    replaced = {ident[ln["parent"]] for ln in r["data"]["links"] if ln["parent"] in ident}
    for e in conn.execute("select distinct b.part_id as parent, l.part_id as child from plm_boms b join plm_bom_lines "
                          "l on l.bom_id = b.id where b.status <> 'superseded'"):
        if ("p", e["parent"]) not in replaced:
            graph[("p", e["parent"])].append(("p", e["child"]))
    for ln in r["data"]["links"]:
        if ln["parent"] in ident and ln["child"] in ident:
            graph[ident[ln["parent"]]].append(ident[ln["child"]])
    loop = _cycle(dict(graph))
    if not loop:
        return None
    codes = {}
    ids = [x[1] for x in loop if x[0] == "p"]
    if ids:
        codes = {row["id"]: row["item_code"] for row in conn.execute("select id, item_code from plm_parts where "
                                                                     "id = any(%s)", (ids,))}
    return [codes.get(x[1], str(x[1])) if x[0] == "p" else names.get(x[1], x[1]) for x in loop]


class _Stop(PlmError):
    pass


def write(conn, user: dict, iid: int, password: str, erp: ErpClient) -> dict:
    """All or nothing in the hub: if any part or BOM cannot be made the batch stays pending and nothing is kept.
    The ERPNext items of new parts are made after that, outside the lock; one that fails is tried again from the
    part's page, as for any part."""
    r = _get(conn, iid)
    if r["status"] != "pending":
        raise PlmError(say("this batch is decided"))
    bad = problems(conn, r, erp)
    if bad:
        raise PlmError(say("not ready to write: {list}", list=Q.join(bad)))
    Q.check_signer(conn, user, password)
    with conn.transaction():          # one writer at a time: the batch row stays locked until it is written
        r = _get(conn, iid, lock=True)
        if r["status"] != "pending" or problems(conn, r, ask_erp=False):
            raise PlmError(say("the batch changed meanwhile: open it again"))
        result = _apply(conn, user, iid, r, erp)
        conn.execute("update plm_intake set status = 'written', decided_by = %s, decided_at = now(), result = %s "
                     "where id = %s", (user["email"], Jsonb(result), iid))
        Q._sign(conn, user, say("Design data written"), "plm-intake", iid, f"#{iid} {r['file_name']}")
        PT.log(conn, "intake", iid, user["email"], "written",
               say("{p} parts made, {b} BOMs drafted", p=len(result["parts_made"]), b=len(result["boms"])) +
               ("; " + "; ".join(result["notes"]) if result["notes"] else ""))
    for pid in result["new_ids"]:                      # ERPNext items, after the hub kept everything
        p = PT._push(conn, erp, pid, user["email"])
        if p["erp_state"] == "failed":
            with conn.transaction():
                PT.log(conn, "intake", iid, user["email"], "item in ERPNext failed",
                       f"{p['item_code']}: {p['erp_error'] or ''}"[:500])
    return view(conn, iid, erp)


def _apply(conn, user: dict, iid: int, r: dict, erp: ErpClient) -> dict:  # noqa: PLR0912
    """Parts first, STEP files onto draft revisions, then draft BOMs. Anything that cannot be done stops the whole
    write (the transaction rolls back), with the reason."""
    plan, nodes = r["plan"], {n["key"]: n for n in r["data"]["nodes"]}
    ids, made, new_ids, notes = {}, [], [], []
    for k, n in nodes.items():
        p = plan[k]
        if p["action"] == "match":
            ids[k] = p["part_id"]
            continue
        code = n["code"] if n["code"] and PT.CODE_RE.match(n["code"]) else ""
        params = {}
        if n.get("material") and any(f["key"] == "material" for f in CAT.get(p["category"])["fields"]):
            params["material"] = n["material"]
        try:
            part = PT.create(conn, user, {"name": n["name"], "category": p["category"], "source": p["source"],
                                          "uom": p["uom"], "code": code, "params": params, "confirm_new": True,
                                          "link_existing": bool(p.get("link_existing")),
                                          "description": say("from design data #{id}", id=iid)}, erp, push=False)
        except PlmError as exc:
            raise _Stop(say("{name}: not made: {error}", name=n["name"], error=str(exc))) from exc
        ids[k] = part["id"]
        new_ids.append(part["id"])
        made.append(part["item_code"])
    for k, f in r["files"].items():
        if k not in ids:
            continue
        rev = PT.current(conn, ids[k])
        if rev is None or rev["status"] != "draft":
            notes.append(say("{name}: released, its model was not attached", name=nodes[k]["name"]))
            continue
        if any(x["sha256"] == f["sha256"] for x in PT.files(conn, rev["id"])):
            continue                                   # the same model pushed again
        try:
            PT.add_file(conn, user, ids[k], "model", f["name"], F.get(f["sha256"]))
        except PlmError as exc:
            raise _Stop(say("{name}: model not attached: {error}", name=nodes[k]["name"], error=str(exc))) from exc
    by_parent = defaultdict(lambda: defaultdict(Decimal))
    for ln in r["data"]["links"]:
        by_parent[ln["parent"]][ln["child"]] += Decimal(ln["qty"])
    boms = []
    for k, kids in by_parent.items():
        try:
            last = conn.execute("select id, status from plm_boms where part_id = %s order by id desc limit 1",
                                (ids[k],)).fetchone()
            if last and last["status"] == "draft":
                bid = last["id"]
            else:
                bid = B.start(conn, user, ids[k], r["changes"].get(k) if last else None)["bom"]["id"]
            B.set_lines(conn, user, bid, [{"part_id": ids[c], "qty": format(q.normalize(), "f")}
                                          for c, q in kids.items()], note=say("from design data #{id}", id=iid))
        except PlmError as exc:
            raise _Stop(say("{name}: BOM not made: {error}", name=nodes[k]["name"], error=str(exc))) from exc
        boms.append(bid)
    return {"parts_made": made, "boms": boms, "notes": notes, "ids": ids, "new_ids": new_ids}


def reject(conn, user: dict, iid: int, note: str) -> dict:
    note = str(note or "").strip()
    if not note:
        raise PlmError(say("say why it is not taken"))
    with conn.transaction():
        r = _get(conn, iid, lock=True)
        if r["status"] != "pending":
            raise PlmError(say("this batch is decided"))
        conn.execute("update plm_intake set status = 'rejected', decided_by = %s, decided_at = now(), note = %s "
                     "where id = %s", (user["email"], note[:1000], iid))
        PT.log(conn, "intake", iid, user["email"], "rejected", note[:500])
    return view(conn, iid)


def original(conn, iid: int) -> tuple[str, bytes]:
    r = _get(conn, iid)
    if not r["file_sha"]:
        raise KeyError(iid)
    return r["file_name"] or f"design-data-{iid}", F.get(r["file_sha"])
