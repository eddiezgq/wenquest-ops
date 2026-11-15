"""The instruction manual of a machine (PLM 33d, WenQuest round 135; ADR-0031).

Eight fixed chapters, each in Chinese and English with its pictures. The AI drafts a chapter from what the PLM knows
(the model and its options, the assemblies and parts of its BOM, the confirmed exploded views, the chapters already
confirmed); it never makes up a number: what the data does not say is written "〔待填 to be filled〕" for a person
to fill. A person edits and confirms each chapter; editing a confirmed chapter makes it a draft again. Only confirmed
chapters go into an edition. Editions are frozen like the parts manual's, with a print and a screen PDF."""

from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import explode as EX
from wqops.hub.plm import parts as PT
from wqops.hub.plm.parts import PlmError
from wqops.i18n import say

CHAPTERS = (
    ("safety", "安全须知", "Safety"),
    ("install", "开箱与安装", "Unpacking and installation"),
    ("parts", "各部分名称", "Names of the parts"),
    ("threading", "穿线与绕线", "Threading and winding the bobbin"),
    ("operation", "操作（针距、倒缝、压脚）", "Operation (stitch length, reverse, presser foot)"),
    ("maintenance", "日常保养（加油、清洁）", "Daily care (oiling, cleaning)"),
    ("troubles", "常见故障与处理", "Troubleshooting"),
    ("specs", "技术参数", "Specifications"),
)
KEYS = tuple(k for k, _z, _e in CHAPTERS)
TITLE = {k: (z, e) for k, z, e in CHAPTERS}
MAX_TEXT = 20000
MAX_FIGURES = 6
TO_FILL = "〔待填 to be filled〕"


def _part(conn, pid: int) -> dict:
    p = PT.get(conn, pid)
    if B._shown_bom(conn, pid) is None:
        raise PlmError(say("an instruction manual is made for a machine with a BOM"))
    return p


def _rows(conn, pid: int) -> dict[str, dict]:
    return {r["key"]: dict(r) for r in conn.execute("select * from plm_um_chapters where part_id = %s", (pid,))}


def explodes(conn, pid: int) -> list[dict]:
    """The assemblies under the machine with a confirmed exploded view: what a chapter's picture can be."""
    out = []
    for p in EX.tree_parts(conn, B._shown_bom(conn, pid)):
        bid = B._shown_bom(conn, p["id"])
        if bid is None:
            continue
        e = conn.execute("select snapshot_sha, svg_sha from plm_explodes where bom_id = %s and state = 'confirmed'",
                         (bid,)).fetchone()
        if e and (e["snapshot_sha"] or e["svg_sha"]):
            out.append({"code": p["item_code"], "name": p["name"], "name_en": p["name_en"], "bom": bid})
    return sorted(out, key=lambda x: x["code"])


def view(conn, pid: int) -> dict:
    p = _part(conn, pid)
    rows = _rows(conn, pid)
    chapters = []
    for k, zh, en in CHAPTERS:
        r = rows.get(k) or {"body_zh": "", "body_en": "", "figures": [], "state": "none"}
        chapters.append({"key": k, "title_zh": zh, "title_en": en, **{x: r.get(x) for x in (
            "body_zh", "body_en", "figures", "state", "drafted_by", "ai_run", "updated_by", "updated_at",
            "confirmed_by", "confirmed_at")}})
    eds = [PT._iso(dict(r)) for r in conn.execute(
        "select id, edition, created_by, created_at, jsonb_array_length(chapters) as chapters from plm_um_editions "
        "where part_id = %s order by edition desc", (pid,))]
    return {"part": {"id": p["id"], "code": p["item_code"], "name": p["name"], "name_en": p["name_en"]},
            "chapters": [PT._iso(c) for c in chapters], "explodes": explodes(conn, pid), "editions": eds,
            "confirmed": sum(1 for c in chapters if c["state"] == "confirmed")}


def _clean_text(s) -> str:
    s = str(s or "").replace("\r\n", "\n").replace("\x00", "")
    if len(s) > MAX_TEXT:
        raise PlmError(say("a chapter is at most {n} characters in each language", n=MAX_TEXT))
    return s.strip()


def _clean_figures(conn, pid: int, xs) -> list[dict]:
    if not isinstance(xs, list) or len(xs) > MAX_FIGURES:
        raise PlmError(say("a chapter has at most {n} pictures", n=MAX_FIGURES))
    ok = {e["code"] for e in explodes(conn, pid)}
    out = []
    for x in xs:
        if not isinstance(x, dict):
            raise PlmError(say("the pictures are not readable"))
        cap = " ".join(str(x.get("caption") or "").split())[:200]
        if x.get("kind") == "explode" and str(x.get("code")) in ok:
            out.append({"kind": "explode", "code": str(x["code"]), "caption": cap})
        elif x.get("kind") == "upload" and re.fullmatch(r"[0-9a-f]{64}", str(x.get("sha") or "")):
            out.append({"kind": "upload", "sha": x["sha"], "name": str(x.get("name") or "")[:120], "caption": cap})
        else:
            raise PlmError(say("a picture is an exploded view of an assembly of this machine, or an uploaded one"))
    return out


def _key(key: str) -> str:
    if key not in KEYS:
        raise KeyError(key)
    return key


def save(conn, user: dict, pid: int, key: str, data: dict) -> dict:
    """A person writes a chapter: it is a draft (again) until confirmed."""
    _part(conn, pid)
    key = _key(key)
    zh, en = _clean_text(data.get("body_zh")), _clean_text(data.get("body_en"))
    figs = _clean_figures(conn, pid, data.get("figures") or [])
    _write(conn, pid, key, (zh, en), figs, who=user["email"], drafted_by=user["email"], run=None)
    PT.log(conn, "part", pid, user["email"], "instruction manual chapter saved", TITLE[key][1])
    return view(conn, pid)


def _write(conn, pid, key, text: tuple[str, str], figs, *, who, drafted_by, run):
    zh, en = text
    conn.execute(
        "insert into plm_um_chapters (part_id, key, body_zh, body_en, figures, state, drafted_by, ai_run, updated_by) "
        "values (%s, %s, %s, %s, %s, 'draft', %s, %s, %s) on conflict (part_id, key) do update set body_zh = "
        "excluded.body_zh, body_en = excluded.body_en, figures = excluded.figures, state = 'draft', drafted_by = "
        "excluded.drafted_by, ai_run = excluded.ai_run, updated_by = excluded.updated_by, updated_at = now(), "
        "confirmed_by = null, confirmed_at = null", (pid, key, zh, en, Jsonb(figs), drafted_by, run, who))


def confirm(conn, user: dict, pid: int, key: str) -> dict:
    key = _key(key)
    r = _rows(conn, pid).get(key)
    if r is None or not (r["body_zh"] and r["body_en"]):
        raise PlmError(say("write the chapter in Chinese and English first"))
    with conn.transaction():
        conn.execute("update plm_um_chapters set state = 'confirmed', confirmed_by = %s, confirmed_at = now() where "
                     "part_id = %s and key = %s", (user["email"], pid, key))
        PT.log(conn, "part", pid, user["email"], "instruction manual chapter confirmed", TITLE[key][1])
    return view(conn, pid)


def upload(conn, user: dict, pid: int, name: str, data: bytes) -> dict:
    """A picture of one's own for a chapter (PNG or JPG); returns the figure to add."""
    _part(conn, pid)
    if len(data) > EX.MAX_IMAGE or EX._kind_of(data) is None:
        raise PlmError(say("{what} is a PNG or JPG picture of up to 20 MB", what=say("the picture")))
    sha = F.put(data)
    PT.log(conn, "part", pid, user["email"], "instruction manual picture uploaded", name[:120])
    return {"kind": "upload", "sha": sha, "name": name[:120], "caption": ""}


def uploaded(conn, pid: int, sha: str) -> bytes:
    """A picture someone uploaded for a chapter of this machine (and only such a picture)."""
    used = {f.get("sha") for r in _rows(conn, pid).values() for f in r["figures"] if f.get("kind") == "upload"}
    if sha not in used:
        raise KeyError(sha)
    return F.get(sha)


def figure_bytes(conn, pid: int, fig: dict) -> tuple[bytes | None, bytes | None]:
    """(colour picture, line drawing SVG) of a figure. An add-on page confirmed without a colour picture has only
    its line drawing; a page laid out in the browser has only its picture."""
    if fig.get("kind") == "upload":
        return F.get(fig["sha"]), None
    p = PT.by_code(conn, fig["code"])
    bid = B._shown_bom(conn, p["id"]) if p else None
    e = conn.execute("select snapshot_sha, svg_sha, line_sha from plm_explodes where bom_id = %s and state = "
                     "'confirmed'", (bid,)).fetchone() if bid else None
    if e is None:
        return None, None
    colour = F.get(e["snapshot_sha"]) if e["snapshot_sha"] and e["snapshot_sha"] != e["line_sha"] else None
    return colour, (F.get(e["svg_sha"]) if e["svg_sha"] else None)


# ---- AI drafts a chapter

SYSTEM = (
    "You write one chapter of the instruction manual of an industrial sewing machine, in simplified Chinese and in "
    "English (the same content in both), for the people who set up, run and look after the machine. You get the "
    "model, its options, its assemblies and parts from the bill of materials, the exploded views that exist and the "
    "chapters already confirmed. Rules: write only what the data supports or what is true of every industrial "
    "lockstitch machine of this kind; NEVER make up a number, a setting, a voltage, a weight, an oil type or a "
    "part that is not in the data: write \"〔待填 to be filled〕\" where a number or a fact is needed and missing. "
    "Name parts as the bill of materials names them. Plain short sentences; steps as numbered lines (\"1. \"); "
    "lists as lines starting \"- \"; a blank line between paragraphs; no headings, no Markdown emphasis. Suggest up "
    "to three exploded views (by assembly code, from the list given) that help this chapter. A person reads, "
    "corrects and confirms every chapter.")
TOOL = {"name": "chapter", "description": "The chapter in Chinese and English, and the pictures to show.",
        "input_schema": {"type": "object", "required": ["body_zh", "body_en"], "properties": {
            "body_zh": {"type": "string"}, "body_en": {"type": "string"},
            "figures": {"type": "array", "items": {"type": "object", "required": ["code"], "properties": {
                "code": {"type": "string"}, "caption": {"type": "string"}}}}}}}


def context(conn, pid: int, key: str) -> str:
    """What the AI is given, as text."""
    p = _part(conn, pid)
    lines = [f"Chapter: {TITLE[key][0]} / {TITLE[key][1]}",
             f"Machine: {p['item_code']} {p['name']} / {p['name_en'] or ''}", "", "Bill of materials (assemblies, "
             "then their parts; code, Chinese name, English name, quantity):"]

    def walk(bid, depth):
        for ln in EX.lines(conn, bid):
            en = ln["name_en"] if ln["name_en_state"] == "confirmed" else ""
            lines.append(f"{'  ' * depth}- {ln['code']} {ln['name']} / {en} x{ln['qty']} {ln['uom']}")
            if ln["page"] and depth < 2:
                walk(ln["page"], depth + 1)
    walk(B._shown_bom(conn, pid), 0)
    lines += ["", "Exploded views that exist (assembly code, name):"]
    lines += [f"- {e['code']} {e['name']}" for e in explodes(conn, pid)] or ["- none"]
    done = [r for k, r in _rows(conn, pid).items() if r["state"] == "confirmed" and k != key]
    if done:
        lines += ["", "Chapters already confirmed (for consistency):"]
        for r in done:
            lines += [f"## {TITLE[r['key']][1]}", r["body_en"][:3000]]
    return "\n".join(lines)


def draft(conn, user: dict, pid: int, key: str, model, *, today) -> dict:
    """The AI drafts one chapter; it replaces the text as a draft, the run is kept, a person confirms."""
    from wqops.hub.ai import agent as AG  # noqa: PLC0415
    from wqops.hub.ai import llm as L  # noqa: PLC0415
    from wqops.hub.ai import tools as T  # noqa: PLC0415

    key = _key(key)
    _part(conn, pid)
    if model is None or not model.configured():
        raise PlmError(say("there is no AI here: write the chapter by hand"))
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "plm-manual", say("Instruction manual, {chapter}", chapter=TITLE[key][1]))
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        resp = model.create(SYSTEM, [{"role": "user", "content": context(conn, pid, key)}], [TOOL], 6000,
                            tool_choice={"type": "tool", "name": "chapter"})
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        got = (use or {}).get("input") or {}
        zh, en = _clean_text(got.get("body_zh")), _clean_text(got.get("body_en"))
        if not (zh and en):
            raise L.LlmError(say("the model did not write the chapter"))
        ok = {e["code"] for e in explodes(conn, pid)}
        figs = [{"kind": "explode", "code": str(f.get("code")), "caption": " ".join(str(f.get("caption") or "")
                                                                                   .split())[:200]}
                for f in got.get("figures") or [] if isinstance(f, dict) and str(f.get("code")) in ok][:3]
    except Exception as exc:
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
    AG.finish(ctx, out | {"answer": f"{zh}\n\n{en}"[:4000]})
    with conn.transaction():
        _write(conn, pid, key, (zh, en), figs, who=user["email"], drafted_by=f"AI ({model.model})", run=ctx.run_id)
        PT.log(conn, "part", pid, user["email"], "instruction manual chapter drafted by AI", TITLE[key][1])
    return view(conn, pid)


# ---- editions

def generate(conn, user: dict, pid: int, *, today) -> dict:
    """A new edition from the confirmed chapters (at least one), frozen, with its two PDFs."""
    from wqops.hub.plm import manual_print as MP  # noqa: PLC0415

    p = _part(conn, pid)
    rows = _rows(conn, pid)
    chapters = []
    for k, zh, en in CHAPTERS:
        r = rows.get(k)
        if r and r["state"] == "confirmed":
            chapters.append({"key": k, "title_zh": zh, "title_en": en, "body_zh": r["body_zh"],
                             "body_en": r["body_en"], "figures": r["figures"], "confirmed_by": r["confirmed_by"]})
    if not chapters:
        raise PlmError(say("no chapter is confirmed yet"))
    prev = conn.execute("select max(edition) as n from plm_um_editions where part_id = %s", (pid,)).fetchone()["n"]
    edition = (prev or 0) + 1
    head = {"code": p["item_code"], "name": p["name"],
            "name_en": p["name_en"] if p["name_en_state"] == "confirmed" else "", "edition": edition}
    figs = {}
    for c in chapters:
        for i, f in enumerate(c["figures"]):
            figs[(c["key"], i)] = figure_bytes(conn, pid, f)
    try:
        pdfs = MP.make_user(head, chapters, figs, today=today)
    except MP.ManualFontMissing as exc:
        raise PlmError(say("the manual's font is not installed on the server (fonts-wqy-microhei)")) from exc
    with conn.transaction():
        row = conn.execute("insert into plm_um_editions (part_id, edition, chapters, pdf_sha, print_sha, created_by) "
                           "values (%s, %s, %s, %s, %s, %s) returning id",
                           (pid, edition, Jsonb(chapters), F.put(pdfs["screen"]), F.put(pdfs["print"]),
                            user["email"])).fetchone()
        PT.log(conn, "part", pid, user["email"], "instruction manual",
               say("edition {n}, {p} chapters", n=edition, p=len(chapters)))
    return {"id": row["id"], "edition": edition, "chapters": len(chapters), "missing": 8 - len(chapters)}


def pdf(conn, eid: int, kind: str = "screen") -> tuple[str, bytes]:
    r = conn.execute("select e.*, p.item_code from plm_um_editions e join plm_parts p on p.id = e.part_id where "
                     "e.id = %s", (eid,)).fetchone()
    if r is None:
        raise KeyError(eid)
    tail = "-print" if kind == "print" else ""
    return (f"{r['item_code']}-instructions-{r['edition']}{tail}.pdf",
            F.get(r["print_sha"] if kind == "print" else r["pdf_sha"]))


def newest(conn, pid: int) -> int | None:
    r = conn.execute("select id from plm_um_editions where part_id = %s order by edition desc limit 1",
                     (pid,)).fetchone()
    return r["id"] if r else None
