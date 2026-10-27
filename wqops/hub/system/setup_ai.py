"""The model reads the company's own procedures and proposes how to set the quality system up to match them
(ADR-0016, step 16d): numbers of days, its own rules switched on or off, what does not apply, and which procedure
shows a requirement. Each proposal quotes the procedure; code checks it (system/setup.py) and a person accepts or
rejects each one. Without a model key this is not offered.
"""

from __future__ import annotations

import datetime as dt
import json

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R
from wqops.hub.system import setup as SU
from wqops.i18n import say


class NoModel(RuntimeError):
    pass


def describe(conn, standard: str) -> str:
    row = QMS.enabled(conn, standard)
    pack = row["content"]
    vals = QMS.settings(conn, standard, pack)
    lines = ["Settings (key: now; what it means; allowed):"]
    for k, s in pack["settings"].items():
        allowed = "yes/no" if type(s["value"]) is bool else f"{s.get('min', 0)}-{s.get('max', 3650)}"
        lines.append(f"- {k}: {json.dumps(vals[k])}; {s['label']}; {allowed}")
    decl = QMS.applicability(conn, standard)
    linked = QMS.evidence(conn, standard)
    lines.append("Requirements (id: summary; how it is shown):")
    for cid, c in QMS.controls(pack).items():
        how = "may not apply" if c.get("may_exclude") else ""
        if c["rule"] in R.LINKED or c.get("switch"):
            how += ("; " if how else "") + "shown by a document"
        now = []
        if cid in decl:
            now.append("declared " + ("applies" if decl[cid]["applies"] else "does not apply"))
        if linked.get(cid):
            now.append("linked: " + ", ".join(d["name"] for d in linked[cid]))
        lines.append(f"- {cid}: {c['summary']}" + (f" ({how})" if how else "") + (f" [{'; '.join(now)}]" if now
                                                                                  else ""))
    return "\n".join(lines)


def tool(doc_ids: list[int]) -> dict:
    doc = {"type": "integer", "enum": doc_ids, "description": "the procedure quoted"}
    return {
        "name": "propose_setup",
        "description": "Propose how to set the quality system up so it matches the company's procedures.",
        "input_schema": {"type": "object", "properties": {
            "changes": {"type": "array", "items": {"type": "object", "properties": {
                "change": {"type": "object", "properties": {
                    "kind": {"type": "string", "enum": list(SU.KINDS),
                             "description": "; ".join(f"{k}: {v}" for k, v in SU.KINDS.items())},
                    "key": {"type": "string", "description": "setting: its key"},
                    "value": {"description": "setting: a whole number or true/false"},
                    "control": {"type": "string", "description": "applies, evidence: the requirement id"},
                    "applies": {"type": "boolean"}, "reason": {"type": "string"}},
                    "required": ["kind"]},
                "document_id": doc,
                "quote": {"type": "string", "description": "the sentence of the procedure this rests on, copied "
                                                           "exactly"},
                "why": {"type": "string"}}, "required": ["change", "document_id", "quote"]}},
            "summary": {"type": "string"}}, "required": ["changes", "summary"]},
    }


def propose(conn, user: dict, standard: str, docs: list[dict], model: L.Anthropic | None, *, today: dt.date,
            company: str = "the company") -> dict:
    if model is None or not model.configured():
        raise NoModel(say("there is no model key; set the system up by hand"))
    if QMS.enabled(conn, standard) is None:
        raise QMS.QmsError(say("adopt the standard first"))
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "setup", f"set up {standard} from: {', '.join(d['name'] for d in docs)}"[:1000])
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        text = "\n\n".join(f"=== Document {d['id']}: {d['name']}, revision {d['revision'] or 'unknown'}"
                           + (f" (only the first {len(d['text'])} of {d['chars']} characters)" if d["cut"] else "")
                           + f"\n{d['text']}" for d in docs)
        resp = model.create(
            f"You help {company} set its quality management system up in WenQuest Ops. Read the company's own "
            "procedures and propose only what they actually say: a number of days the procedures set (for example "
            "how often gauges are calibrated or audits are held), a requirement that does not apply and why, or a "
            "procedure that shows a requirement. Every proposal quotes the sentence it rests on, copied exactly "
            "(code checks it), and names the procedure. Do not propose what is already so. A person accepts or "
            "rejects each proposal.",
            [{"role": "user", "content": describe(conn, standard) + "\n\nProcedures:\n\n" + text}],
            [tool([d["id"] for d in docs])], 6000, tool_choice={"type": "tool", "name": "propose_setup"})
        if resp.get("stop_reason") == "max_tokens":
            raise L.LlmError(say("the model's answer was cut off; choose fewer procedures"))
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None or not isinstance(use.get("input"), dict):
            raise L.LlmError(say("the model did not propose anything"))
        p = SU.store(conn, user["email"], standard, docs, use["input"], ctx.run_id)
        items = SU.view(conn, p["id"])["items"]
        bad = [f"change {i['seq']}: {'; '.join(i['problems'])}" for i in items if i["problems"]]
        out.update(usage=resp.get("usage", {}), answer=json.dumps(use["input"], ensure_ascii=False)[:8000],
                   verified=not bad, unverified=bad,
                   tool_calls=[{"tool": "propose_setup", "args": {"documents": [d["id"] for d in docs]}, "ok": True,
                                "summary": f"{len(items)} changes, {len(bad)} with problems"}])
        AG.finish(ctx, out)
        return p
    except Exception as exc:                    # the run is closed whatever went wrong, then the error goes on
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
