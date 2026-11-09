"""Exploded views and English names for the parts manual (PLM step 27b, WenQuest round 124).

One page per BOM revision (an assembly): its direct lines numbered 1, 2, 3 in BOM order; a picture made in the
browser from the 3D models (pulled apart, turned, balloons placed) or an uploaded drawing with balloons placed on
it. A layout, not design data: it may change after the BOM is released (plm:edit), every save is logged. A new
revision starts from the layout of the one before it, matched by part. Standard parts (fasteners) are numbered and
listed but not drawn unless someone says so (round 124 rule 4)."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import parts as PT
from wqops.hub.plm.parts import PlmError
from wqops.i18n import say

IMAGE_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}
MAX_IMAGE = 20 * 1024 * 1024
NOT_DRAWN = frozenset({"fastener"})          # listed, not drawn, by default


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
            "saved_by": None, "saved_at": None, "from_revision": B.get(conn, prev["bom_id"])["revision"]}


def view(conn, bid: int) -> dict:
    b = B.get(conn, bid)
    part = PT.get(conn, b["part_id"])
    page = _row(conn, bid) or _inherited(conn, bid) or {"kind": "model", "layout": {}, "balloons": [],
                                                       "image_sha": None, "image_name": None,
                                                       "snapshot_sha": None, "saved_by": None, "saved_at": None}
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
            "saved_by = excluded.saved_by, saved_at = excluded.saved_at",
            (bid, kind, Jsonb(layout), Jsonb(balloons), img_sha,
             (image_name or old.get("image_name") or "")[:200] if img_sha else None, snap, user["email"]))
        PT.log(conn, "bom", bid, user["email"], "exploded view saved",
               say("{n} balloons", n=len(balloons)) + ("" if snap else "; " + say("no picture yet")))
    return view(conn, bid)


def picture(conn, bid: int, which: str) -> bytes:
    r = _row(conn, bid) or _inherited(conn, bid)
    sha = (r or {}).get("snapshot_sha" if which == "snapshot" else "image_sha")
    if not sha:
        raise KeyError(bid)
    return F.get(sha)


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
