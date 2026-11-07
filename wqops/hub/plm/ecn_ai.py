"""The AI drafts the impact note of a design change, step 26d (ADR-0026): it reads only the impact analysis code
made (``ecn.as_text``) and writes which models it touches, what to do with stock and open orders, and which way of
taking effect it suggests. Every number in the draft must be in the analysis (``agent.verify``); the draft goes into
the change's assessment only after a person edits and saves it. Without a model key the analysis itself is the draft.
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.plm import ecn as E
from wqops.i18n import say

SYSTEM = (
    "You help an engineering team assess a design change of a machine builder. You are shown the parts the change "
    "touches and, for each, the assemblies above it (* marks a finished machine), stock on hand, open purchase "
    "orders, open work orders and open sales orders of the machines. Write a short impact note for the change "
    "record: which machines and assemblies it touches, what to do with the stock and the open orders, and which way "
    "of taking effect you suggest (now, after the stock is used up, from a date, or from a serial number) and why. "
    "Use only what is shown; never invent a number, an order or a part. Where something is unknown, say it must be "
    "checked. A person edits and decides.")
TOOL = {"name": "impact_note", "description": "The impact note for a person to edit.",
        "input_schema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}


def draft(conn, user: dict, cid: int, model, *, today: dt.date) -> dict:
    imp = E.impact(conn, cid)
    if imp is None or not imp["current"]:
        raise E.PlmError(say("analyse the impact first"))
    text = E.as_text(imp["data"])
    if model is None or not model.configured():
        return {"note": text, "engine": "rules", "unverified": []}
    ctx = T.Ctx(conn=conn, user=user, today=today)
    c = conn.execute("select name, title from changes where id = %s", (cid,)).fetchone()
    AG.start(ctx, "plm-impact", say("impact note for {name} {title}", name=c["name"], title=c["title"]))
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        resp = model.create(SYSTEM, [{"role": "user", "content": f"Change {c['name']}: {c['title']}\n\n{text}"}],
                            [TOOL], 1500, tool_choice={"type": "tool", "name": "impact_note"})
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        note = str(((use or {}).get("input") or {}).get("note") or "").strip()[:4000]
        if not note:
            raise L.LlmError(say("the model did not suggest anything"))
        bad = AG.verify(note, text)
        out.update(usage=resp.get("usage", {}), answer=note, verified=not bad, unverified=bad)
        AG.finish(ctx, out)
        return {"note": note, "engine": "model", "unverified": bad, "run": ctx.run_id}
    except Exception as exc:
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
