"""Classification with the company's model (ADR-0014 item 3): the model reads each file's text (or, for a long file,
its start, headings and end) with its name and folder, and records a proposal through a tool. Every field carries a
quote from the file; code checks the quotes (classify.verify). Without a model, or when a call fails, the rules
classify that file. One ``ai_runs`` record per import batch.
"""

from __future__ import annotations

import datetime as dt
import json

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.docs import classify as K
from wqops.hub.docs import library as LIB


def _field(desc: str, enum: list[str] | None = None) -> dict:
    v = {"type": "string", "description": desc} | ({"enum": enum} if enum else {})
    return {"type": "object", "properties": {"value": v, "quote": {
        "type": "string", "description": "a sentence or line copied exactly from the file, its name or its folder, "
                                         "that shows this value"}}, "required": ["value", "quote"]}


def tool(processes: dict[str, str]) -> dict:
    return {
        "name": "record_classification",
        "description": "Record what this file is. Leave out any field the file does not show; never guess.",
        "input_schema": {"type": "object", "properties": {
            "doc_type": _field("what kind of document: " + "; ".join(f"{k} = {v}" for k, v in K.TYPES.items()),
                               list(K.TYPES)),
            "process": _field("which process it belongs to: " + "; ".join(f"{k} = {v}" for k, v in processes.items()),
                              list(processes)),
            "number": _field("the document number exactly as written (e.g. QP-08, F-QA-012)"),
            "title": _field("the document title as written"),
            "revision": _field("the revision or version as written (e.g. C, 3, 2.1), without the word Rev"),
            "effective_date": _field("the date it took effect, as YYYY-MM-DD; the quote holds the date as written"),
            "owner": _field("the person or role that owns or prepared it, as written"),
            "language": {"type": "string", "description": "ISO 639-1 code of the main language, e.g. en"},
            "summary": {"type": "string", "description": "one plain sentence: what this document is for"},
            "refs": {"type": "array", "items": {"type": "string"}, "description":
                     "numbers of the forms, records or other documents this one names, exactly as written"},
            "confidence": {"type": "string", "enum": list(K.LEVELS), "description":
                           "high only when type, process and title are plain in the file"},
        }, "required": ["doc_type", "process", "title", "confidence"]},
    }


def system(processes: dict[str, str], hints: list[dict], company: str) -> str:
    s = (f"You sort the existing documents of {company}, a small manufacturer, into its document library. "
         "For each file call record_classification once. Base every value on the file's text, name or folder path; "
         "copy the quote exactly (code checks that it is in the file, and fields whose quote is not found are "
         "marked unverified). Leave a field out when the file does not show it. A filled-in form is a record; a "
         "blank form or template is a form. Procedures say who does what; work instructions give the steps of one "
         "task. Certificates and supplier documents are certificate or external.")
    if hints:
        s += ("\n\nPeople at this company corrected earlier proposals as follows; follow their practice:\n"
              + "\n".join(f"- {h['file']}: " + "; ".join(f"{c['field']} {c['from'] or '(empty)'} -> "
                                                         f"{c['to'] or '(empty)'}" for c in h["changes"])
                          for h in hints))
    return s


def _proposal(inp: dict) -> dict:
    p: dict = {"evidence": {}, "refs": [str(r) for r in inp.get("refs") or [] if str(r).strip()],
               "confidence": inp.get("confidence", "low")}
    for f in K.QUOTED:
        x = inp.get(f)
        if isinstance(x, dict) and str(x.get("value") or "").strip():
            p[f] = str(x["value"]).strip()[:300]
            p["evidence"][f] = {"quote": str(x.get("quote") or "")}
    if p.get("doc_type") not in K.TYPES:
        p.pop("doc_type", None)
    if p.get("effective_date"):
        try:
            p["effective_date"] = dt.date.fromisoformat(p["effective_date"]).isoformat()
        except ValueError:
            p.pop("effective_date")
    for f in ("language", "summary"):
        if str(inp.get(f) or "").strip():
            p[f] = str(inp[f]).strip()[: 8 if f == "language" else 400]
    return p


def classify_one(model: L.Anthropic, sys_prompt: str, tool_def: dict, doc: dict, body: str) -> tuple[dict, dict]:
    """One model call for one file; returns (proposal, usage)."""
    where = f"{doc['path']}/{doc['original_name']}".strip("/")
    text = LIB.excerpt(body) if body else "(no text could be read from this file)"
    resp = model.create(sys_prompt, [{"role": "user", "content": f"File: {where}\n\nText:\n{text}"}], [tool_def],
                        1200, tool_choice={"type": "tool", "name": tool_def["name"]})
    use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
    if use is None:
        raise L.LlmError("the model did not record a classification")
    return _proposal(use.get("input") or {}), resp.get("usage", {})


def _copy(first: dict) -> dict | None:
    """The classification of an earlier identical file, as it stands now (a person may have corrected it)."""
    if not first["doc_type"]:
        return None
    prop = {k: first[k] for k in (*K.FIELDS, "summary") if first[k] is not None}
    prop = {k: v.isoformat() if isinstance(v, dt.date) else v for k, v in prop.items()}
    return prop | {"refs": first["refs"], "evidence": first["evidence"], "confidence": first["confidence"]}


def run(conn, user: dict, import_id: int, model: L.Anthropic | None, *, today: dt.date, company: str = "the company",
        use_ai: bool = True) -> dict:
    """Classify every unclassified file of an import: with the model when there is one, else by the rules."""
    procs = LIB.processes(conn)
    docs = conn.execute("select * from documents where import_id = %s and status = 'to_classify' order by id",
                        (import_id,)).fetchall()
    ai = use_ai and model is not None and model.configured()
    conn.execute("update doc_imports set status = 'classifying', engine = %s, error = null where id = %s",
                 ("ai" if ai else "rules", import_id))
    ctx = T.Ctx(conn=conn, user=user, today=today)
    if ai:
        AG.start(ctx, "classify", f"classify import {import_id}: {len(docs)} files")
        sys_prompt, tool_def = system(procs, LIB.hints(conn), company), tool(procs)
    calls, usage, failed, counts = [], {"input_tokens": 0, "output_tokens": 0}, [], {"ai": 0, "rules": 0}
    crash = None
    try:
        for doc in docs:
            body = LIB.text(conn, doc["id"])
            engine, prop = "rules", None
            if doc["duplicate_of"]:
                prop, engine = _copy(LIB.get(conn, doc["duplicate_of"])), "copy of an earlier identical file"
            if prop is None and ai:
                try:
                    prop, u = classify_one(model, sys_prompt, tool_def, doc, body)
                    for k in usage:
                        usage[k] += int(u.get(k, 0))
                    engine = "ai"
                except L.LlmError as exc:
                    failed.append(f"{doc['original_name']}: {exc}")
            if prop is None:
                engine, prop = "rules", K.rules(doc["original_name"], doc["path"], body, procs)
            if prop.get("process") not in procs:
                prop.pop("process", None)
            checked = K.verify(prop, doc["original_name"], doc["path"], body)   # copies too: values may differ
            LIB.propose(conn, doc["id"], checked, engine, ctx.run_id if engine == "ai" else None)
            counts["ai" if engine == "ai" else "rules"] += 1
            calls.append({"tool": "record_classification", "args": {"document": doc["id"]}, "ok": engine == "ai",
                          "summary": json.dumps({k: checked.get(k) for k in ("doc_type", "process", "number", "title",
                                                                              "confidence")})[:300]})
    except Exception as exc:
        crash = f"stopped: {type(exc).__name__}: {exc}"
        failed.append(crash)
        raise
    finally:
        if ai:                                       # the run record is completed even when the run stops early
            low = [f"document {c['args']['document']}" for c in calls if '"confidence": "low"' in c["summary"]]
            AG.finish(ctx, {"engine": "model" if counts["ai"] else "rules (model unavailable)", "model": model.model,
                            "tool_calls": calls, "answer": f"classified {len(calls)} of {len(docs)} files: "
                            f"{counts['ai']} by the model, {counts['rules']} by rules", "verified": not failed,
                            "unverified": low[:50], "usage": usage, "error": "; ".join(failed)[:2000] or None})
    conn.execute("update doc_imports set status = 'done', error = %s where id = %s",
                 ("; ".join(failed)[:2000] or None, import_id))
    return {"files": len(docs), "by_model": counts["ai"], "by_rules": counts["rules"], "failed": failed,
            "run_id": ctx.run_id, "usage": usage if ai else {}}
