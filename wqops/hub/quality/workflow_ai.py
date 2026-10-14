"""The model's part in changing a quality workflow (ADR-0015, step 15c): it reads the company's own procedures next
to the workflow in use and proposes changes, each quoting the procedure it rests on. It never changes the workflow:
code checks every quote and every change (quality/workflow_proposals.py), a person accepts or rejects each one, and
someone else enables the draft with a signature. Without a model this is not offered; changing by hand still is.
"""

from __future__ import annotations

import datetime as dt
import json

from wqops.hub import permissions as P
from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_proposals as WP


class NoModel(RuntimeError):
    pass


def describe(conn, cfg: dict) -> str:
    """The workflow in use and what a change may name, for the model."""
    kind = cfg["kind"]
    lines = [f"Workflow in use: {cfg['label']} ({kind}); numbers {cfg['numbering']['prefix']}-"
             f"{'0' * (int(cfg['numbering']['digits']) - 1)}1",
             "States: " + ", ".join(f"{s} ({v.get('label')}{', final' if v.get('final') else ''})"
                                    for s, v in cfg["states"].items()),
             "Steps:"]
    for name, st in cfg["steps"].items():
        bits = [f"from {'/'.join(st['from'])}", f"to {st.get('to') or '(stays)'}"]
        if st.get("to_when_approval_needed"):
            bits.append(f"or to {st['to_when_approval_needed']} when the disposition type needs approval")
        if st.get("required"):
            bits.append("needs " + ", ".join(st["required"]))
        if st.get("sign"):
            bits.append(f"signed ({st['sign']})")
        if st.get("not_by"):
            bits.append("not by " + ", ".join(st["not_by"]))
        bits.append("roles " + ", ".join(st.get("roles") or W.view(cfg)["steps"][name]["who"]))
        lines.append(f"- {name} \"{st.get('label', name)}\": " + "; ".join(bits))
    lines.append("Own fields: " + (json.dumps(cfg.get("fields"), ensure_ascii=False) if cfg.get("fields") else "none"))
    lines.append("Extra approvals: " + (json.dumps(cfg.get("approvals"), ensure_ascii=False) if cfg.get("approvals")
                                         else "none"))
    lines.append("Rules: " + json.dumps(cfg.get("rules") or {}))
    if kind == "ncr":
        types = Q.disposition_types(conn)
        lines.append("Disposition types (code: name, needs approval): " + "; ".join(
            f"{k}: {t['name']}, {'yes' if t['requires_approval'] else 'no'}" for k, t in types.items()))
    lines += ["", "What a change may name:",
              "- fields a step can need (require): " + json.dumps(W.NEEDS[kind]),
              "- people a record names (not_by): " + json.dumps({k: W.WHO[k] for k in sorted(W.NOT_BY_FIELDS[kind])}),
              "- roles: " + json.dumps({r: sorted(p) for r, p in P.ROLE_PERMISSIONS.items()}),
              "- steps an own field can be needed before, or an extra approval can come before: "
              + ", ".join(sorted(W.GATES[kind])),
              "- conditions of an extra approval: " + json.dumps(
                  {k: list(v) if v else list(Q.disposition_types(conn)) for k, v in W.WHEN[kind].items()}),
              "- own field types: " + ", ".join(W.FIELD_TYPES)]
    return "\n".join(lines)


def tool(kind: str, doc_ids: list[int]) -> dict:
    change = {"type": "object", "properties": {
        "op": {"type": "string", "enum": list(WP.OPS),
               "description": "; ".join(f"{k}: {v}" for k, v in WP.OPS.items())},
        "step": {"type": "string", "description": "require, not_by, roles: the step"},
        "field": {"type": "string", "description": "require: the field"},
        "person": {"type": "string", "description": "not_by: the person"},
        "roles": {"type": "array", "items": {"type": "string"}, "description": "roles, approval: the roles"},
        "rule": {"type": "string", "enum": list(WP.RULES), "description": "rule: which rule"},
        "severity": {"type": "string", "description": "rule: minor or major"},
        "name": {"type": "string", "description": "field, approval: a short name of lower-case letters and _"},
        "label": {"type": "string", "description": "field, approval: what people see"},
        "type": {"type": "string", "enum": list(W.FIELD_TYPES), "description": "field: its type"},
        "choices": {"type": "array", "items": {"type": "string"}, "description": "field of type choice"},
        "required_at": {"type": "array", "items": {"type": "string"}, "description": "field: steps it is needed "
                                                                                       "before"},
        "before": {"type": "string", "description": "approval: the step it comes before"},
        "when": {"type": "object", "description": "approval: conditions, e.g. {\"severity\": [\"major\"]}",
                 "additionalProperties": {"type": "array", "items": {"type": "string"}}},
        "not_by": {"type": "array", "items": {"type": "string"}, "description": "approval: people who may not "
                                                                                 "approve"},
        "sign": {"type": "string", "description": "approval: the meaning of the signature"},
        "prefix": {"type": "string"}, "digits": {"type": "integer"}}, "required": ["op"]}
    quote = {"type": "string", "description": "the sentence of the procedure this rests on, copied exactly"}
    doc = {"type": "integer", "enum": doc_ids, "description": "the procedure quoted"}
    return {
        "name": "propose_workflow_changes",
        "description": f"Propose changes to the {kind} workflow that the company's procedures call for.",
        "input_schema": {"type": "object", "properties": {
            "changes": {"type": "array", "items": {"type": "object", "properties": {
                "change": change, "document_id": doc, "quote": quote,
                "why": {"type": "string", "description": "one sentence: how the quote calls for this change"}},
                "required": ["change", "document_id", "quote", "why"]}},
            "cannot": {"type": "array", "description": "requirements of the procedures about these records that the "
                                                       "workflow cannot express with the changes above",
                       "items": {"type": "object", "properties": {"document_id": doc, "quote": quote,
                                                                  "why": {"type": "string"}},
                                 "required": ["document_id", "quote", "why"]}},
            "summary": {"type": "string", "description": "two or three sentences: how far the workflow already "
                                                         "follows the procedures"}},
            "required": ["changes", "summary"]},
    }


def _docs_text(docs: list[dict]) -> str:
    out = []
    for d in docs:
        cut = f" (only the first {len(d['text'])} of {d['chars']} characters)" if d["cut"] else ""
        out.append(f"=== Document {d['id']}: {d['name']}, revision {d['revision'] or 'unknown'}, {d['status']}{cut}\n"
                   f"{d['text']}")
    return "\n\n".join(out)


def propose(conn, user: dict, kind: str, docs: list[dict], model: L.Anthropic | None, *, today: dt.date,
            company: str = "the company") -> dict:
    """Ask the model and keep what it proposes, checked by code. NoModel without a model key; a failed call is kept
    as a run with its error and raised as LlmError."""
    if model is None or not model.configured():
        raise NoModel("there is no model key; the workflow can still be changed by hand")
    base = W.ensure(conn, kind)
    cfg = base["config"]
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "workflow", f"{kind} workflow from: {', '.join(d['name'] for d in docs)}"[:1000])
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        resp = model.create(
            f"You help {company} set up its quality system. Read the company's own procedures and compare them with "
            "the workflow in use. Propose only changes the procedures call for and the workflow does not already do; "
            "never propose loosening anything. Every change quotes the sentence of the procedure it rests on, copied "
            "exactly (code checks it), and names that procedure. Do not repeat what the workflow already does. When a "
            "procedure asks for something these changes cannot express, list it under cannot. You never change the "
            "workflow: a person accepts or rejects each change and someone else enables the new version.",
            [{"role": "user", "content": describe(conn, cfg) + "\n\nProcedures:\n\n" + _docs_text(docs)}],
            [tool(kind, [d["id"] for d in docs])], 8000,
            tool_choice={"type": "tool", "name": "propose_workflow_changes"})
        if resp.get("stop_reason") == "max_tokens":
            raise L.LlmError("the model's answer was cut off; choose fewer procedures")
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None:
            raise L.LlmError("the model did not propose changes")
        result = use.get("input") if isinstance(use.get("input"), dict) else {}
        if not isinstance(result.get("changes"), list):
            raise L.LlmError("the model's proposal has no list of changes")
        p = WP.store(conn, kind, user["email"], docs, result, ctx.run_id, base["id"])
        got = WP.items(conn, p["id"])
        bad = [f"change {i['seq']}: {'; '.join(i['problems'])}" for i in got if i["problems"]]
        out.update(usage=resp.get("usage", {}), answer=json.dumps(result, ensure_ascii=False)[:8000],
                   verified=not bad, unverified=bad,
                   tool_calls=[{"tool": "propose_workflow_changes", "args": {"documents": [d["id"] for d in docs]},
                                "ok": True, "summary": f"{len(got)} changes, {len(bad)} with problems"}])
        AG.finish(ctx, out)
        return p
    except Exception as exc:                    # the run is closed whatever went wrong, then the error goes on
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
