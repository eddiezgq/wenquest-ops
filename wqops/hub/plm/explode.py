"""Exploded views and English names for the parts manual (PLM step 27b, WenQuest round 124).

One page per BOM revision (an assembly): its direct lines numbered 1, 2, 3 in BOM order; a picture made in the
browser from the 3D models (pulled apart, turned, balloons placed) or an uploaded drawing with balloons placed on
it. A layout, not design data: it may change after the BOM is released (plm:edit), every save is logged. A new
revision starts from the layout of the one before it, matched by part. Standard parts (fasteners) are numbered and
listed but not drawn unless someone says so (round 124 rule 4).

PLM 33b (round 135, ADR-0030): the FreeCAD add-on makes a page too, sent with a machine token: how far each part is
moved, where the balloons are, the direction of view and a vector line drawing. It waits as "pending" until a person
confirms it; only confirmed pages go into the manual. The PLM's colour picture is drawn from the same moves."""

from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import parts as PT
from wqops.hub.plm.parts import PlmError
from wqops.i18n import say

IMAGE_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}
MAX_IMAGE = 20 * 1024 * 1024
NOT_DRAWN = frozenset({"fastener"})          # listed, not drawn, by default
MAX_SVG = 5 * 1024 * 1024
# an SVG is shown in the browser: nothing in it may run or load anything
SVG_BAD = re.compile(r"<\s*(script|foreignObject|iframe|object|embed|image|use|a|style)\b|<!(DOCTYPE|ENTITY)"
                     r"|\bon[a-z]+\s*=|javascript:|(xlink:)?href\s*=|url\s*\(", re.IGNORECASE)


def _kind_of(data: bytes) -> str | None:
    return next((k for sig, k in IMAGE_TYPES.items() if data.startswith(sig)), None)


def lines(conn, bid: int) -> list[dict]:
    """The page's table: number, part, English name and its state, quantity, drawn or not by default, and whether
    the line is an assembly with its own page."""
    out = []
    for n, ln in enumerate(conn.execute(
            "select l.pos, l.qty, l.uom, l.note, p.id as part_id, p.item_code as code, p.name, p.name_en, "
            "p.name_en_state, p.category, p.source from plm_bom_lines l join plm_parts p on p.id = l.part_id "
            "where l.bom_id = %s order by l.pos", (bid,)).fetchall(), start=1):
        sub = B._shown_bom(conn, ln["part_id"])
        out.append({**ln, "no": n, "qty": B.R.qty_text(ln["qty"]), "page": sub,
                    "drawn": ln["category"] not in NOT_DRAWN})
    return out


def _row(conn, bid: int) -> dict | None:
    r = conn.execute("select * from plm_explodes where bom_id = %s", (bid,)).fetchone()
    return dict(r) if r else None


def _inherited(conn, bid: int) -> dict | None:
    """The layout of the revision before, for a new revision that has none yet (parts matched by id)."""
    b = B.get(conn, bid)
    prev = conn.execute("select e.* from plm_explodes e join plm_boms b on b.id = e.bom_id where b.part_id = %s "
                        "and b.id < %s order by b.id desc limit 1", (b["part_id"], bid)).fetchone()
    if prev is None:
        return None
    here = {r["part_id"] for r in conn.execute("select part_id from plm_bom_lines where bom_id = %s", (bid,))}
    lay = dict(prev["layout"] or {})
    lay["moves"] = {k: v for k, v in (lay.get("moves") or {}).items() if int(k) in here}
    lay["drawn"] = {k: v for k, v in (lay.get("drawn") or {}).items() if int(k) in here}
    return {"kind": prev["kind"], "layout": lay, "balloons": [x for x in prev["balloons"] if x["part_id"] in here],
            "image_sha": prev["image_sha"], "image_name": prev["image_name"], "snapshot_sha": None,
            "state": "confirmed", "source": "browser", "svg_sha": None, "line_sha": None,
            "saved_by": None, "saved_at": None, "from_revision": B.get(conn, prev["bom_id"])["revision"]}


def view(conn, bid: int) -> dict:
    b = B.get(conn, bid)
    part = PT.get(conn, b["part_id"])
    page = _row(conn, bid) or _inherited(conn, bid) or {"kind": "model", "layout": {}, "balloons": [],
                                                       "image_sha": None, "image_name": None,
                                                       "snapshot_sha": None, "saved_by": None, "saved_at": None}
    page.setdefault("state", "confirmed")
    page.setdefault("source", "browser")
    page.pop("id", None)
    page.pop("bom_id", None)
    return {"bom": PT._iso(dict(b)), "part": {"id": part["id"], "code": part["item_code"], "name": part["name"],
                                              "name_en": part["name_en"], "name_en_state": part["name_en_state"]},
            "page": PT._iso(page), "lines": lines(conn, bid), "scene": B.scene(conn, bid, group=True)}


def _clean_layout(x, part_ids: set[int]) -> dict:
    if not isinstance(x, dict):
        raise PlmError(say("the layout is not readable"))
    out = {}
    cam = x.get("camera")
    if cam is not None:
        try:
            out["camera"] = {k: [float(v) for v in cam[k]][:3] for k in ("position", "target", "up") if k in cam}
        except (TypeError, ValueError, KeyError) as exc:
            raise PlmError(say("the layout is not readable")) from exc
    try:
        out["factor"] = min(max(float(x.get("factor", 0.6)), 0.0), 5.0)
        if x.get("view") is not None:
            v = [float(a) for a in x["view"]][:3]
            if len(v) != 3 or not any(v) or any(abs(a) > 1e6 for a in v):
                raise ValueError(v)
            out["view"] = v
        out["moves"] = {str(int(k)): [float(v) for v in m][:3] for k, m in (x.get("moves") or {}).items()
                        if int(k) in part_ids}
        out["drawn"] = {str(int(k)): bool(v) for k, v in (x.get("drawn") or {}).items() if int(k) in part_ids}
    except (TypeError, ValueError) as exc:
        raise PlmError(say("the layout is not readable")) from exc
    return out


def _clean_balloons(xs, part_ids: set[int]) -> list[dict]:
    if not isinstance(xs, list) or len(xs) > 500:
        raise PlmError(say("the balloons are not readable"))
    out = []
    for x in xs:
        try:
            pid = int(x["part_id"])
            v = {k: min(max(float(x[k]), -0.5), 1.5) for k in ("x", "y")}
            v.update({k: min(max(float(x[k]), -0.5), 1.5) for k in ("ax", "ay") if x.get(k) is not None})
        except (TypeError, ValueError, KeyError) as exc:
            raise PlmError(say("the balloons are not readable")) from exc
        if pid in part_ids:
            out.append({"part_id": pid, **v})
    return out


def save(conn, user: dict, bid: int, data: dict, *, snapshot: bytes | None = None,
         image: bytes | None = None, image_name: str = "") -> dict:
    """Keep the page: the layout and balloons, the picture as seen (PNG), and for an uploaded drawing the drawing."""
    b = B.get(conn, bid)
    if b["status"] == "superseded":
        raise PlmError(say("this BOM revision is superseded: lay out the current one"))
    kind = data.get("kind", "model")
    if kind not in ("model", "image"):
        raise PlmError(say("an exploded view is made from the 3D models or from an uploaded drawing"))
    part_ids = {r["part_id"] for r in conn.execute("select part_id from plm_bom_lines where bom_id = %s", (bid,))}
    layout = _clean_layout(data.get("layout") or {}, part_ids)
    balloons = _clean_balloons(data.get("balloons") or [], part_ids)
    for blob, what in ((snapshot, say("the picture")), (image, say("the drawing"))):
        if blob is not None and (len(blob) > MAX_IMAGE or _kind_of(blob) is None):
            raise PlmError(say("{what} is a PNG or JPG picture of up to 20 MB", what=what))
    old = _row(conn, bid) or _inherited(conn, bid) or {}
    img_sha = F.put(image) if image is not None else old.get("image_sha")
    if kind == "image" and not img_sha:
        raise PlmError(say("upload the drawing first"))
    snap = F.put(snapshot) if snapshot is not None else None
    with conn.transaction():
        conn.execute(
            "insert into plm_explodes (bom_id, kind, layout, balloons, image_sha, image_name, snapshot_sha, saved_by, "
            "saved_at) values (%s, %s, %s, %s, %s, %s, %s, %s, now()) on conflict (bom_id) do update set "
            "kind = excluded.kind, layout = excluded.layout, balloons = excluded.balloons, image_sha = "
            "excluded.image_sha, image_name = excluded.image_name, snapshot_sha = excluded.snapshot_sha, "
            "saved_by = excluded.saved_by, saved_at = excluded.saved_at, state = 'confirmed', source = 'browser', "
            "svg_sha = null, line_sha = null, confirmed_by = excluded.saved_by, confirmed_at = now()",
            (bid, kind, Jsonb(layout), Jsonb(balloons), img_sha,
             (image_name or old.get("image_name") or "")[:200] if img_sha else None, snap, user["email"]))
        PT.log(conn, "bom", bid, user["email"], "exploded view saved",
               say("{n} balloons", n=len(balloons)) + ("" if snap else "; " + say("no picture yet")))
    return view(conn, bid)


def picture(conn, bid: int, which: str) -> bytes:
    """which: snapshot (the page's picture), image (an uploaded drawing), svg or line (FreeCAD's line drawing)."""
    r = _row(conn, bid) or _inherited(conn, bid)
    sha = (r or {}).get({"snapshot": "snapshot_sha", "image": "image_sha", "svg": "svg_sha", "line": "line_sha"}[which])
    if not sha:
        raise KeyError(bid)
    return F.get(sha)


# ---- from FreeCAD (33b, ADR-0030)

def for_freecad(conn, code: str) -> dict:
    """What the add-on needs before it draws an assembly: the BOM the page belongs to and its lines in order, so the
    balloons carry the numbers the manual will print."""
    p = PT.by_code(conn, code)
    if p is None:
        raise PlmError(say("no part has the code {code}", code=code))
    bid = B._shown_bom(conn, p["id"])
    if bid is None:
        raise PlmError(say("{code} has no BOM: push the assembly first", code=code))
    b = B.get(conn, bid)
    return {"code": p["item_code"], "name": p["name"], "bom": bid, "revision": b["revision"],
            "lines": [{"no": x["no"], "code": x["code"], "name": x["name"], "category": x["category"],
                       "drawn": x["drawn"]} for x in lines(conn, bid)]}


def clean_svg(data: bytes) -> bytes:
    if not data or len(data) > MAX_SVG:
        raise PlmError(say("the line drawing is an SVG of up to 5 MB"))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlmError(say("the line drawing is an SVG of up to 5 MB")) from exc
    head = re.sub(r"^\s*(<\?xml[^>]*\?>\s*)?", "", text)[:200]
    if not head.startswith("<svg") or SVG_BAD.search(text):
        raise PlmError(say("the line drawing holds something other than lines and text"))
    return data


def from_freecad(conn, sent_by: str, code: str, data: dict, svg: bytes, *, png: bytes | None = None) -> dict:
    """Keep the add-on's page, waiting for a person: moves {part code: [dx, dy, dz]} (mm, the assembly frame, the
    whole pull), balloons [{code, no, x, y, ax, ay}] on the line drawing, view [x, y, z] (towards the viewer). The
    numbers must still be the BOM's: if a line moved since, the drawing is made again."""
    if not isinstance(data, dict):
        raise PlmError(say("the layout is not readable"))
    info = for_freecad(conn, code)
    bid = info["bom"]
    if B.get(conn, bid)["status"] == "superseded":
        raise PlmError(say("this BOM revision is superseded: lay out the current one"))
    by = {x["code"]: x for x in lines(conn, bid)}
    for x in data.get("balloons") or []:
        ln = by.get(str((x or {}).get("code") if isinstance(x, dict) else ""))
        if ln is None or str(x.get("no")) != str(ln["no"]):
            raise PlmError(say("the BOM of {code} changed since the drawing was made: make it again", code=code))
    try:
        moves = {str(by[c]["part_id"]): m for c, m in (data.get("moves") or {}).items() if c in by}
    except AttributeError as exc:
        raise PlmError(say("the layout is not readable")) from exc
    ids = {x["part_id"] for x in by.values()}
    layout = _clean_layout({"factor": 0, "moves": moves, "view": data.get("view")}, ids)
    balloons = _clean_balloons([{**{k: b.get(k) for k in ("x", "y", "ax", "ay")}, "part_id": by[b["code"]]["part_id"]}
                                for b in data.get("balloons") or []], ids)
    clean_svg(svg)
    if png is not None and (len(png) > MAX_IMAGE or _kind_of(png) != "png"):
        raise PlmError(say("{what} is a PNG or JPG picture of up to 20 MB", what=say("the picture")))
    svg_sha = F.put(svg)
    line_sha = F.put(png) if png is not None else None
    who = f"FreeCAD: {sent_by}"[:200]
    with conn.transaction():
        conn.execute(
            "insert into plm_explodes (bom_id, kind, layout, balloons, image_sha, image_name, snapshot_sha, saved_by, "
            "saved_at, state, source, svg_sha, line_sha) values (%s, 'model', %s, %s, null, null, %s, %s, now(), "
            "'pending', 'freecad', %s, %s) on conflict (bom_id) do update set kind = 'model', layout = "
            "excluded.layout, balloons = excluded.balloons, image_sha = null, image_name = null, snapshot_sha = "
            "excluded.snapshot_sha, saved_by = excluded.saved_by, saved_at = excluded.saved_at, state = 'pending', "
            "source = 'freecad', svg_sha = excluded.svg_sha, line_sha = excluded.line_sha, confirmed_by = null, "
            "confirmed_at = null",
            (bid, Jsonb(layout), Jsonb(balloons), line_sha, who, svg_sha, line_sha))
        PT.log(conn, "bom", bid, who, "exploded view from FreeCAD",
               say("{n} balloons", n=len(balloons)) + "; " + say("waiting to be confirmed"))
    return {"bom": bid, "revision": info["revision"], "state": "pending", "balloons": len(balloons)}


def confirm(conn, user: dict, bid: int, snapshot: bytes | None = None) -> dict:
    """A person has looked at the add-on's page and lets it into the manual; the colour picture they saw (with its
    balloons) becomes the page's picture, the line drawing stays for print."""
    r = _row(conn, bid)
    if r is None or r["state"] != "pending":
        raise PlmError(say("there is no exploded view waiting to be confirmed here"))
    if snapshot is not None and (len(snapshot) > MAX_IMAGE or _kind_of(snapshot) is None):
        raise PlmError(say("{what} is a PNG or JPG picture of up to 20 MB", what=say("the picture")))
    snap = F.put(snapshot) if snapshot is not None else r["snapshot_sha"]
    with conn.transaction():
        conn.execute("update plm_explodes set state = 'confirmed', confirmed_by = %s, confirmed_at = now(), "
                     "snapshot_sha = %s where bom_id = %s", (user["email"], snap, bid))
        PT.log(conn, "bom", bid, user["email"], "exploded view confirmed", r["saved_by"] or "")
    return view(conn, bid)


# ---- English names

def set_name_en(conn, user: dict, pid: int, name_en: str, *, confirm: bool) -> dict:
    """A person writes or confirms a part's English name (confirmed: it goes into the manual as it is)."""
    PT.get(conn, pid)
    n = " ".join(str(name_en or "").split())[:140]
    state = "none" if not n else ("confirmed" if confirm else "draft")
    with conn.transaction():
        conn.execute("update plm_parts set name_en = %s, name_en_state = %s, updated_at = now() where id = %s",
                     (n, state, pid))
        PT.log(conn, "part", pid, user["email"], "English name", f"{n} ({state})")
    return {"id": pid, "name_en": n, "name_en_state": state}


NAMES_SYSTEM = (
    "You translate the names of machine parts from Chinese into the English a parts catalogue for overseas dealers "
    "uses (sewing machines and similar machinery). For each part you get its code, Chinese name and category. Give "
    "the usual catalogue term, short, in title case, keeping sizes, standards and model numbers as they are "
    "(\"螺钉 SM11/64(40)×8\" -> \"Screw SM11/64(40)x8\"). Never add a part or change a code. "
    "A person checks every name.")
NAMES_TOOL = {"name": "english_names", "description": "English catalogue names for the parts given.",
              "input_schema": {"type": "object", "required": ["names"], "properties": {"names": {
                  "type": "array", "items": {"type": "object", "required": ["code", "name_en"], "properties": {
                      "code": {"type": "string"}, "name_en": {"type": "string"}}}}}}}
NAMES_CHUNK = 60


def tree_parts(conn, bid: int) -> list[dict]:
    """Every part under the BOM (the BOM's own part included), each once."""
    b = B.get(conn, bid)
    seen, out, todo = set(), [], [b["part_id"]]
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(dict(conn.execute("select id, item_code, name, category, name_en, name_en_state from plm_parts "
                                     "where id = %s", (pid,)).fetchone()))
        sub = B._shown_bom(conn, pid)
        if sub:
            todo.extend(r["part_id"] for r in conn.execute("select part_id from plm_bom_lines where bom_id = %s",
                                                           (sub,)))
    return out


def draft_names(conn, user: dict, bid: int, model, *, today) -> dict:
    """AI drafts the English names still missing under the BOM; each stays a draft until a person confirms it.
    The run is kept like every AI run."""
    from wqops.hub.ai import agent as AG  # noqa: PLC0415
    from wqops.hub.ai import llm as L  # noqa: PLC0415
    from wqops.hub.ai import tools as T  # noqa: PLC0415

    todo = [p for p in tree_parts(conn, bid) if p["name_en_state"] == "none"]
    if not todo:
        return {"drafted": 0, "left": 0}
    if model is None or not model.configured():
        raise PlmError(say("there is no AI here: write the English names by hand"))
    drafted = 0
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "plm-names", say("English names under BOM {id}", id=bid))
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        drafted = _names(conn, user, bid, model, todo, L)
    except Exception as exc:
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
    AG.finish(ctx, out | {"answer": say("{n} names", n=drafted)})
    return {"drafted": drafted, "left": len(todo) - drafted, "run": ctx.run_id}


def _names(conn, user: dict, bid: int, model, todo: list[dict], L) -> int:  # noqa: PLR0917
    drafted = 0
    for i in range(0, len(todo), NAMES_CHUNK):
        part = todo[i:i + NAMES_CHUNK]
        text = "\n".join(f"{p['item_code']}\t{p['name']}\t{p['category']}" for p in part)
        resp = model.create(NAMES_SYSTEM, [{"role": "user", "content": text}], [NAMES_TOOL], 4000,
                            tool_choice={"type": "tool", "name": "english_names"})
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        got = {str(x.get("code") or ""): " ".join(str(x.get("name_en") or "").split())[:140]
               for x in ((use or {}).get("input") or {}).get("names") or [] if isinstance(x, dict)}
        if not got and i == 0:
            raise L.LlmError(say("the model did not suggest anything"))
        with conn.transaction():
            for p in part:
                n = got.get(p["item_code"])
                if n:           # only a name for a part that was asked about, and only where none was written
                    drafted += conn.execute("update plm_parts set name_en = %s, name_en_state = 'draft' where id = "
                                            "%s and name_en_state = 'none'", (n, p["id"])).rowcount
            PT.log(conn, "bom", bid, user["email"], "English names drafted by AI", say("{n} names", n=drafted))
    return drafted
