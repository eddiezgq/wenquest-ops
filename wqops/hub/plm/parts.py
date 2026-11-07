"""Parts, step 26a (ADR-0026): the part master is the ERPNext Item; the hub keeps its revisions, status, category
parameters and files. A part is created by a person (who confirms the ERPNext item it makes), released with that
person's signature, and changed only through a new revision under an approved product change (17g).

No AI here; ERPNext is reached only through the client passed in.
"""

from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from wqops.erp import ErpClient
from wqops.hub.docs import store as F
from wqops.hub.plm import catalog as CAT
from wqops.hub.plm import rules as R
from wqops.hub.quality import records as Q
from wqops.i18n import say

SOURCES = ("make", "buy")
FILE_KINDS = ("model", "drawing", "image", "other")
FILE_TYPES = {"model": (".step", ".stp", ".fcstd", ".stl", ".iges", ".igs"),
              "drawing": (".pdf", ".dxf", ".dwg", ".svg"),
              "image": (".png", ".jpg", ".jpeg", ".webp"), "other": None}
ERP_GROUP = "PLM"
LIST_MAX = 500
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,59}$")


class PlmError(ValueError):
    pass


class Similar(PlmError):
    """Parts that look the same exist: the person confirms it is new."""

    def __init__(self, parts: list[dict]):
        super().__init__(say("parts with the same required values exist; reuse one, or confirm this is a new part"))
        self.parts = parts


def log(conn, kind: str, ref_id: int, email: str | None, action: str, note: str = "") -> None:  # noqa: PLR0917
    conn.execute("insert into plm_log (kind, ref_id, email, action, note) values (%s, %s, %s, %s, %s)",
                 (kind, ref_id, email, action, (note or "")[:2000]))


def history(conn, kind: str, ref_id: int) -> list[dict]:
    rows = conn.execute("select at, email, action, note from plm_log where kind = %s and ref_id = %s order by id",
                        (kind, ref_id)).fetchall()
    return [dict(r, at=r["at"].isoformat(), action=Q.word(r["action"])) for r in rows]


def _iso(row: dict | None) -> dict | None:
    return None if row is None else {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


# ---- numbering (ADR-0026 item 7)

def numbering(conn) -> dict[str, dict]:
    own = {r["category"]: r for r in conn.execute("select * from plm_numbering")}
    return {k: {"prefix": own[k]["prefix"] if k in own else c["prefix"], "digits": own[k]["digits"] if k in own else 5}
            for k, c in CAT.CATEGORIES.items()}


def set_numbering(conn, email: str, category: str, prefix: str, digits: int) -> None:
    CAT.get(category)
    prefix = str(prefix or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,9}", prefix):
        raise PlmError(say("the prefix is 1 to 10 letters, digits or -"))
    if type(digits) is not int or not 3 <= digits <= 8:
        raise PlmError(say("the number has 3 to 8 digits"))
    taken = [k for k, v in numbering(conn).items() if k != category and v["prefix"] == prefix]
    if taken:
        raise PlmError(say("prefix {prefix} is already used by another category", prefix=prefix))
    with conn.transaction():
        conn.execute("insert into plm_numbering (category, prefix, digits, updated_by) values (%s, %s, %s, %s) "
                     "on conflict (category) do update set prefix = excluded.prefix, digits = excluded.digits, "
                     "updated_by = excluded.updated_by, updated_at = now()", (category, prefix, digits, email))
        log(conn, "numbering", 0, email, "numbering changed", f"{category}: {prefix} / {digits}")


def _next_code(conn, erp: ErpClient, category: str) -> str:
    rule = numbering(conn)[category]
    conn.execute("select pg_advisory_xact_lock(hashtext('wqo-plm-code'))")
    pat = re.compile(rf"^{re.escape(rule['prefix'])}-(\d+)$")
    n = max([int(m.group(1)) for r in conn.execute("select item_code from plm_parts where item_code like %s",
                                                   (rule["prefix"] + "-%",))
             if (m := pat.match(r["item_code"]))], default=0)
    for _ in range(100):      # an item made in ERPNext by hand may already have the next number
        n += 1
        code = f"{rule['prefix']}-{n:0{rule['digits']}d}"
        if erp.get("Item", code) is None:
            return code
    raise PlmError(say("could not find a free number for {prefix}", prefix=rule["prefix"]))


# ---- reading

def get(conn, pid: int) -> dict:
    row = conn.execute("select * from plm_parts where id = %s", (pid,)).fetchone()
    if row is None:
        raise KeyError(pid)
    return row


def by_code(conn, code: str) -> dict | None:
    return conn.execute("select * from plm_parts where item_code = %s", (code,)).fetchone()


def revisions(conn, pid: int) -> list[dict]:
    return conn.execute("select * from plm_part_revisions where part_id = %s order by id", (pid,)).fetchall()


def current(conn, pid: int) -> dict | None:
    """The draft revision if there is one, else the latest released."""
    revs = revisions(conn, pid)
    draft = [r for r in revs if r["status"] == "draft"]
    return draft[0] if draft else (revs[-1] if revs else None)


def latest_released(conn, pid: int) -> dict | None:
    return conn.execute("select * from plm_part_revisions where part_id = %s and status = 'released' order by id desc "
                        "limit 1", (pid,)).fetchone()


def files(conn, rev_id: int) -> list[dict]:
    return [_iso(r) for r in conn.execute("select id, kind, name, sha256, size_bytes, added_by, added_at from "
                                          "plm_files "
                                          "where revision_id = %s and removed_at is null order by id", (rev_id,))]


def listing(conn, *, q: str = "", category: str = "", status: str = "") -> list[dict]:
    sql = ("select p.*, r.revision, r.status as rev_status, r.params from plm_parts p left join lateral "
           "(select revision, status, params from plm_part_revisions where part_id = p.id order by id desc limit 1) r "
           "on true where true")
    args: list = []
    if q:
        sql += " and (p.item_code ilike %s or p.name ilike %s)"
        args += [f"%{q}%", f"%{q}%"]
    if category:
        sql += " and p.category = %s"
        args.append(category)
    if status:
        sql += " and p.status = %s"
        args.append(status)
    rows = conn.execute(sql + " order by p.item_code limit %s", [*args, LIST_MAX + 1]).fetchall()
    return [{"id": r["id"], "code": r["item_code"], "name": r["name"], "category": r["category"],
             "source": r["source"], "uom": r["uom"], "status": r["status"], "revision": r["revision"],
             "rev_status": r["rev_status"], "erp_state": r["erp_state"]} for r in rows]


def where_used(conn, pid: int) -> list[dict]:
    rows = conn.execute("select b.id as bom_id, b.revision, b.status, p.id as part_id, p.item_code, p.name, l.qty, "
                        "l.uom from plm_bom_lines l join plm_boms b on b.id = l.bom_id join plm_parts p on "
                        "p.id = b.part_id where l.part_id = %s and b.status <> 'superseded' order by p.item_code, b.id",
                        (pid,)).fetchall()
    return [dict(r, qty=str(r["qty"])) for r in rows]


def view(conn, pid: int) -> dict:
    p = get(conn, pid)
    revs = []
    for r in revisions(conn, pid):
        x = _iso(dict(r))
        x["files"] = files(conn, r["id"])
        if r["change_id"]:
            ch = conn.execute("select name, title, status from changes where id = %s", (r["change_id"],)).fetchone()
            x["change"] = dict(ch) if ch else None
        if r["status"] == "draft":
            x["checks"] = R.part_checks(p, r)
            x["ready"] = R.passed(x["checks"])
        revs.append(x)
    return {"part": _iso(dict(p)), "category": next(c for c in CAT.shown() if c["key"] == p["category"]),
            "revisions": revs, "where_used": where_used(conn, pid),
            "boms": [_iso(dict(b)) for b in conn.execute("select id, revision, status, released_at from plm_boms "
                                                         "where part_id = %s order by id", (pid,))],
            "signatures": Q.signatures(conn, "plm-part", pid), "history": history(conn, "part", pid)}


# ---- creating and changing

def _erp_item(erp: ErpClient, part: dict, description: str) -> str:
    """Make the ERPNext item (in group PLM, made if missing). Returns 'created' or 'existing' (only when the person
    chose to link an item ERPNext already has, with the same unit)."""
    have = erp.get("Item", part["item_code"])
    if have is not None:
        _may_link(part, have)
        return "existing"
    if erp.get("Item Group", ERP_GROUP) is None:
        roots = erp.list("Item Group", filters=[["is_group", "=", 1], ["parent_item_group", "is", "not set"]],
                         fields=["name"], limit=1)
        erp.insert({"doctype": "Item Group", "item_group_name": ERP_GROUP,
                    "parent_item_group": roots[0]["name"] if roots else "All Item Groups", "is_group": 0})
    erp.insert({"doctype": "Item", "item_code": part["item_code"], "item_name": part["name"][:140],
                "item_group": ERP_GROUP, "stock_uom": part["uom"], "is_stock_item": 1,
                "description": description or part["name"]})
    return "created"


def _may_link(part: dict, have: dict) -> None:
    if not part.get("link_existing"):
        raise PlmError(say("ERPNext already has item {code}: to use it for this part, choose to link the existing item",
                           code=part["item_code"]))
    if have.get("stock_uom") and have["stock_uom"] != part["uom"]:
        raise PlmError(say("item {code} in ERPNext counts in {erp_uom}, not {uom}", code=part["item_code"],
                           erp_uom=have["stock_uom"], uom=part["uom"]))


def _push(conn, erp: ErpClient, pid: int, email: str) -> dict:
    p = get(conn, pid)
    rev = current(conn, pid)
    try:
        state = _erp_item(erp, p, (rev or {}).get("description") or "")
        err = None
    except Exception as exc:  # the part stays; the person tries again from its page
        state, err = "failed", f"{type(exc).__name__}: {exc}"[:1000]
    with conn.transaction():
        conn.execute("update plm_parts set erp_state = %s, erp_error = %s, updated_at = now() where id = %s",
                     (state, err, pid))
        log(conn, "part", pid, email, "item in ERPNext " + state, err or p["item_code"])
    return get(conn, pid)


def _others(conn, category: str) -> list[dict]:
    rows = conn.execute("select p.id, p.item_code, p.name, r.revision, r.params from plm_parts p join lateral "
                        "(select revision, params from plm_part_revisions where part_id = p.id order by id desc "
                        "limit 1) r on true where p.category = %s and p.status <> 'obsolete'", (category,)).fetchall()
    return [dict(r) for r in rows]


def check_similar(conn, category: str, params: dict) -> list[dict]:
    return [{"id": o["id"], "code": o["item_code"], "name": o["name"], "revision": o["revision"]}
            for o in R.similar(category, params, _others(conn, category))]


def create(conn, user: dict, data: dict, erp: ErpClient) -> dict:
    name = str(data.get("name") or "").strip()
    if not name:
        raise PlmError(say("give the part a name"))
    category = str(data.get("category") or "")
    if category not in CAT.CATEGORIES:
        raise PlmError(say("choose a category"))
    source = data.get("source") or "make"
    if source not in SOURCES:
        raise PlmError(say("a part is made or bought"))
    uom = str(data.get("uom") or "").strip() or "Nos"
    try:
        params = R.clean_params(category, data.get("params"))
    except ValueError as exc:
        raise PlmError(str(exc)) from exc
    same = check_similar(conn, category, params)
    if same and data.get("confirm_new") is not True:
        raise Similar(same)
    code = str(data.get("code") or "").strip()
    if code and not CODE_RE.match(code):
        raise PlmError(say("the code is letters, digits and . _ / - (up to 60)"))
    link = bool(code) and data.get("link_existing") is True
    if code:
        try:
            have = erp.get("Item", code)
        except Exception:      # ERPNext not answering: the part is made, its item is tried again later
            have = None
        if have is not None:
            _may_link({"item_code": code, "uom": uom, "link_existing": link}, have)
    with conn.transaction():
        if code:
            if by_code(conn, code):
                raise PlmError(say("part {code} already exists", code=code))
        else:
            code = _next_code(conn, erp, category)
        p = conn.execute("insert into plm_parts (item_code, name, category, source, uom, link_existing, created_by) "
                         "values (%s, %s, %s, %s, %s, %s, %s) returning *",
                         (code, name[:140], category, source, uom, link, user["email"])).fetchone()
        conn.execute("insert into plm_part_revisions (part_id, revision, params, description, editors, created_by) "
                     "values (%s, %s, %s, %s, %s, %s)", (p["id"], R.next_revision(None), Jsonb(params),
                                                         str(data.get("description") or "").strip()[:4000],
                                                         [user["email"]], user["email"]))
        log(conn, "part", p["id"], user["email"], "created", f"{code} {name}" + (" (confirmed new)" if same else ""))
    return _push(conn, erp, p["id"], user["email"])


def retry_erp(conn, user: dict, pid: int, erp: ErpClient) -> dict:
    if get(conn, pid)["erp_state"] in ("created", "existing"):
        raise PlmError(say("the item is already in ERPNext"))
    return _push(conn, erp, pid, user["email"])


def update(conn, user: dict, pid: int, data: dict, erp: ErpClient | None = None) -> dict:  # noqa: PLR0912
    """Change the draft revision (parameters, description); while nothing is released also the part's name, source,
    unit and category (a new category drops parameters it does not have). The unit is fixed once the ERPNext item
    exists; a new name goes to the ERPNext item too; a made part with a BOM stays made."""
    p = get(conn, pid)
    rev = current(conn, pid)
    if rev is None or rev["status"] != "draft":
        raise PlmError(say("the part has no draft revision: start a new revision under an approved change"))
    head = {k: data[k] for k in ("name", "source", "uom", "category") if k in data and data[k] != p[k]}
    if head and p["status"] != "draft":
        raise PlmError(say("the part is released: its name, source, unit and category no longer change"))
    if "uom" in head and p["erp_state"] in ("created", "existing"):
        raise PlmError(say("the unit is fixed: the ERPNext item already uses it"))
    if head.get("source") == "buy" and conn.execute("select 1 from plm_boms where part_id = %s", (pid,)).fetchone():
        raise PlmError(say("the part has a BOM: it stays a made part"))
    category = head.get("category", p["category"])
    if category not in CAT.CATEGORIES:
        raise PlmError(say("choose a category"))
    if head.get("source", p["source"]) not in SOURCES:
        raise PlmError(say("a part is made or bought"))
    if "name" in head and not str(head["name"]).strip():
        raise PlmError(say("give the part a name"))
    params = rev["params"]
    if "params" in data:
        params = data["params"]
    elif category != p["category"]:
        keys = {x["key"] for x in CAT.get(category)["fields"]}
        params = {k: v for k, v in params.items() if k in keys}
    try:
        params = R.clean_params(category, params)
    except ValueError as exc:
        raise PlmError(str(exc)) from exc
    with conn.transaction():
        locked = conn.execute("select status from plm_part_revisions where id = %s for update", (rev["id"],)).fetchone()
        if locked["status"] != "draft":
            raise PlmError(say("the part moved on meanwhile: open it again"))
        if head:
            conn.execute("update plm_parts set name = %s, source = %s, uom = %s, category = %s, updated_at = now() "
                         "where id = %s", (str(head.get("name", p["name"])).strip()[:140],
                                           head.get("source", p["source"]),
                                           str(head.get("uom", p["uom"])).strip() or p["uom"], category, pid))
        conn.execute("update plm_part_revisions set params = %s, description = %s, updated_at = now(), "
                     "editors = case when %s = any(editors) then editors else editors || %s end where id = %s",
                     (Jsonb(params), str(data.get("description", rev["description"]) or "").strip()[:4000],
                      user["email"], [user["email"]], rev["id"]))
        log(conn, "part", pid, user["email"], "edited", f"rev {rev['revision']}")
    if "name" in head and erp is not None and p["erp_state"] in ("created", "existing"):
        try:
            erp.update("Item", p["item_code"], {"item_name": str(head["name"]).strip()[:140]})
        except Exception as exc:
            with conn.transaction():
                log(conn, "part", pid, user["email"], "item in ERPNext failed", f"{type(exc).__name__}: {exc}"[:500])
    return view(conn, pid)


def change_still_holds(conn, change_id) -> None:
    """A revision started under a change is released only while that change stands (approved or implemented)."""
    if change_id is None:
        return
    st = conn.execute("select status from changes where id = %s", (change_id,)).fetchone()
    if st is None or st["status"] not in ("approved", "implemented"):
        raise PlmError(say("the change this revision rests on is no longer approved"))


def approved_change(conn, change_id) -> dict:
    """A new revision rests on an approved product change (17g)."""
    if type(change_id) is not int:
        raise PlmError(say("a new revision needs an approved product change"))
    ch = conn.execute("select id, name, kind, status from changes where id = %s", (change_id,)).fetchone()
    if ch is None or ch["kind"] != "product" or ch["status"] != "approved":
        raise PlmError(say("a new revision needs an approved product change"))
    return ch


def new_revision(conn, user: dict, pid: int, change_id) -> dict:
    p = get(conn, pid)
    ch = approved_change(conn, change_id)
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (pid,))
        last = latest_released(conn, pid)
        if current(conn, pid)["status"] == "draft" or last is None:
            raise PlmError(say("the part already has a draft revision"))
        rev = conn.execute("insert into plm_part_revisions (part_id, revision, params, description, change_id, "
                           "editors, created_by) values (%s, %s, %s, %s, %s, %s, %s) returning *",
                           (pid, R.next_revision(last["revision"]), Jsonb(last["params"]), last["description"],
                            ch["id"], [user["email"]], user["email"])).fetchone()
        conn.execute("insert into plm_files (revision_id, kind, name, sha256, size_bytes, added_by) select %s, kind, "
                     "name, sha256, size_bytes, added_by from plm_files where revision_id = %s and removed_at is null",
                     (rev["id"], last["id"]))
        log(conn, "part", pid, user["email"], "new revision", f"{rev['revision']} ({ch['name']})")
    del p
    return view(conn, pid)


def release(conn, user: dict, pid: int, password: str) -> dict:
    p = get(conn, pid)
    rev = current(conn, pid)
    if rev is None or rev["status"] != "draft":
        raise PlmError(say("there is no draft revision to release"))
    checks = R.part_checks(p, rev)
    if not R.passed(checks):
        raise PlmError(say("not ready to release: {list}", list=Q.join(
            [c["check"] for c in checks if c["result"] != "pass"])))
    change_still_holds(conn, rev["change_id"])
    Q.check_signer(conn, user, password)
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (pid,))
        rev = conn.execute("select * from plm_part_revisions where id = %s for update", (rev["id"],)).fetchone()
        if rev["status"] != "draft":
            raise PlmError(say("the part moved on meanwhile: open it again"))
        p = get(conn, pid)
        checks = R.part_checks(p, rev)                 # again under the lock: what is signed is what was checked
        if not R.passed(checks):
            raise PlmError(say("not ready to release: {list}", list=Q.join(
                [c["check"] for c in checks if c["result"] != "pass"])))
        change_still_holds(conn, rev["change_id"])
        conn.execute("update plm_part_revisions set status = 'superseded' where part_id = %s and status = 'released'",
                     (pid,))
        conn.execute("update plm_part_revisions set status = 'released', released_by = %s, released_at = now() "
                     "where id = %s", (user["email"], rev["id"]))
        conn.execute("update plm_parts set status = 'released', updated_at = now() where id = %s", (pid,))
        Q._sign(conn, user, say("Part revision released"), "plm-part", pid, f"{p['item_code']} rev {rev['revision']}")
        log(conn, "part", pid, user["email"], "revision released", f"rev {rev['revision']}")
    return view(conn, pid)


# ---- files (ADR-0026 item 11)

def add_file(conn, user: dict, pid: int, kind: str, name: str, data: bytes) -> dict:  # noqa: PLR0917
    rev = current(conn, pid)
    if rev is None or rev["status"] != "draft":
        raise PlmError(say("files go on a draft revision"))
    if kind not in FILE_KINDS:
        raise PlmError(say("the kind of file is one of: {kinds}", kinds=", ".join(FILE_KINDS)))
    name = (name or "file").replace("\\", "/").rsplit("/", 1)[-1][:200]
    allowed = FILE_TYPES[kind]
    if allowed and not name.lower().endswith(allowed):
        raise PlmError(say("a {kind} file is one of: {types}", kind=kind, types=", ".join(allowed)))
    if not data or len(data) > F.MAX_BYTES:
        raise PlmError(say("the file is empty or larger than 50 MB"))
    sha = F.put(data)
    with conn.transaction():
        conn.execute("insert into plm_files (revision_id, kind, name, sha256, size_bytes, added_by) values "
                     "(%s, %s, %s, %s, %s, %s)", (rev["id"], kind, name, sha, len(data), user["email"]))
        log(conn, "part", pid, user["email"], "file added", name)
    return view(conn, pid)


def remove_file(conn, user: dict, pid: int, file_id: int) -> dict:
    rev = current(conn, pid)
    row = conn.execute("select * from plm_files where id = %s and removed_at is null", (file_id,)).fetchone()
    if row is None or rev is None or row["revision_id"] != rev["id"] or rev["status"] != "draft":
        raise PlmError(say("only a file of the draft revision can be removed"))
    with conn.transaction():
        conn.execute("update plm_files set removed_by = %s, removed_at = now() where id = %s", (user["email"], file_id))
        log(conn, "part", pid, user["email"], "file removed", row["name"])
    return view(conn, pid)


def file_of(conn, pid: int, file_id: int) -> tuple[dict, bytes]:
    row = conn.execute("select f.* from plm_files f join plm_part_revisions r on r.id = f.revision_id where f.id = %s "
                       "and r.part_id = %s", (file_id, pid)).fetchone()
    if row is None:
        raise KeyError(file_id)
    return row, F.get(row["sha256"])
