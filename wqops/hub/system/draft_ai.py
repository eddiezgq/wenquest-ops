"""The model drafts a document a control point is missing (ADR-0016, step 16c), such as the quality policy or a
procedure for customer property. The draft goes into the document library as a file to review: a person confirms
it, sends it for approval and someone else approves it (ADR-0014). The model never makes a document effective, and
anything it does not know about the company it leaves as "[to fill: ...]" for a person. Without a model key this is
not offered.
"""

from __future__ import annotations

import datetime as dt
import io
import re

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.docs import library as LIB
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R

TYPES = ("procedure", "work_instruction", "form", "other")
MAX_CHARS = 20000
PROCESS = {"production": "production", "traceability": "production", "customer_property": "production",
           "design": "production", "post_delivery": "complaints", "changes": "management_review",
           "scope": "management_review", "processes": "management_review", "policy": "management_review",
           "roles": "management_review", "ncr_concession": "nonconformance", "capa_for_major": "capa",
           "capa_on_time": "capa"}


class NoModel(RuntimeError):
    pass


def draftable(conn, standard: str) -> dict[str, dict]:
    """Control points shown by a document that have none in effect yet."""
    v = QMS.view(conn, standard)
    out = {}
    for p in v["processes"]:
        for c in p["controls"]:
            r = c.get("result") or {}
            if (r.get("rule") or c["rule"]) in R.LINKED and r.get("status") in (R.UNKNOWN, R.NOT_MET):
                out[c["id"]] = c
    return out


def tool() -> dict:
    return {
        "name": "write_document",
        "description": "Write the document as a draft for the company to review.",
        "input_schema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "the document's title, e.g. 'Quality Policy'"},
            "doc_type": {"type": "string", "enum": list(TYPES)},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "heading": {"type": "string"},
                "paragraphs": {"type": "array", "items": {"type": "string"}}}, "required": ["heading", "paragraphs"]}},
            "to_fill": {"type": "array", "items": {"type": "string"},
                        "description": "what a person must fill in or decide before approval"}},
            "required": ["title", "doc_type", "sections"]},
    }


def _docx(company: str, title: str, sections: list[dict], to_fill: list[str]) -> bytes:
    import docx as D  # noqa: PLC0415 - python-docx, a hub dependency

    d = D.Document()
    hdr = d.sections[0].header
    hdr.paragraphs[0].text = f"{company} - DRAFT written by AI for review; not in effect until approved"
    d.add_heading(title, level=1)
    for s in sections:
        d.add_heading(s["heading"], level=2)
        for para in s["paragraphs"]:
            d.add_paragraph(para)
    if to_fill:
        d.add_heading("To fill in before approval", level=2)
        for t in to_fill:
            d.add_paragraph(t, style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _clean(inp: dict) -> dict:
    title = re.sub(r"\s+", " ", str(inp.get("title") or "")).strip()[:120]
    sections = []
    for s in inp.get("sections") or []:
        if not isinstance(s, dict):
            continue
        paras = [str(x).strip()[:3000] for x in (s.get("paragraphs") or []) if str(x).strip()]
        if str(s.get("heading") or "").strip() and paras:
            sections.append({"heading": str(s["heading"]).strip()[:120], "paragraphs": paras[:40]})
    if not title or not sections:
        raise L.LlmError("the model's draft has no title or no text")
    if sum(len(p) for s in sections for p in s["paragraphs"]) > MAX_CHARS:
        raise L.LlmError("the model's draft is too long")
    return {"title": title, "doc_type": inp.get("doc_type") if inp.get("doc_type") in TYPES else "other",
            "sections": sections[:20], "to_fill": [str(x).strip()[:300] for x in (inp.get("to_fill") or [])
                                                   if str(x).strip()][:30]}


def draft(conn, user: dict, standard: str, control: str, model: L.Anthropic | None, *, today: dt.date,
          company: str = "the company") -> dict:
    """Write the draft and put it in the library for review. Returns the new document."""
    if model is None or not model.configured():
        raise NoModel("there is no model key; write the document yourself and link it")
    c = draftable(conn, standard).get(control)
    if c is None:
        raise QMS.QmsError("this control point is not shown by a document, or it already has one in effect")
    have = conn.execute("select number, title, doc_type from documents where status in ('effective', 'confirmed', "
                        "'draft') and title is not null order by number nulls last limit 80").fetchall()
    known = "\n".join(f"- {d['number'] or ''} {d['title']} ({d['doc_type']})".strip() for d in have) or "none yet"
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "document", f"draft for {standard} {control}: {c['summary']}"[:1000])
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        resp = model.create(
            f"You help {company} set up its quality management system. Write a short, plain draft document that "
            "shows how the company meets one requirement. Keep it practical: purpose, scope, responsibilities, what "
            "is done, which records are kept. Never invent facts about the company (names, numbers, dates, products, "
            "sites): write [to fill: ...] where they belong and list them under to_fill. Refer to the company's "
            "existing documents by number where they fit. A person reviews and approves the draft; you never make "
            "it effective.",
            [{"role": "user", "content": f"Requirement (ISO 9001 {', '.join(c['clauses'])}): {c['summary']}\n"
                                         f"Usually shown by: {c.get('hint') or 'a procedure'}\n\n"
                                         f"The company's documents:\n{known}"}],
            [tool()], 4000, tool_choice={"type": "tool", "name": "write_document"})
        if resp.get("stop_reason") == "max_tokens":
            raise L.LlmError("the model's draft was cut off")
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None or not isinstance(use.get("input"), dict):
            raise L.LlmError("the model did not write a draft")
        d = _clean(use["input"])
        data = _docx(company, d["title"], d["sections"], d["to_fill"])
        name = re.sub(r"[^\w .-]+", " ", f"DRAFT {d['title']}").strip()[:100] + ".docx"
        with conn.transaction():
            imp = LIB.new_import(conn, user["email"], f"AI draft for ISO 9001 {', '.join(c['clauses'])}")
            doc = LIB.add_file(conn, imp["id"], name, data)
            LIB.extract_one(conn, LIB.get(conn, doc["id"]))
            row = LIB.propose(conn, doc["id"], {"doc_type": d["doc_type"], "process": PROCESS.get(control, "other"),
                                                "title": d["title"], "confidence": "low",
                                                "summary": f"AI draft for: {c['summary']}"}, "ai", ctx.run_id)
            conn.execute("update doc_imports set status = 'done', engine = 'ai' where id = %s", (imp["id"],))
            LIB.log(conn, doc["id"], user["email"], "drafted by AI", f"for ISO 9001 {', '.join(c['clauses'])}; "
                    f"{len(d['to_fill'])} things to fill in")
        out.update(usage=resp.get("usage", {}), answer=d["title"],
                   tool_calls=[{"tool": "write_document", "args": {"control": control}, "ok": True,
                                "summary": f"{d['title']}: {len(d['sections'])} sections"}])
        AG.finish(ctx, out)
        return row
    except Exception as exc:                    # the run is closed whatever went wrong, then the error goes on
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
