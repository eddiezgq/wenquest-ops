"""The model's part in a ledger import (ADR-0014 item 10): it looks at the headers, a sample of rows and the words
used in short columns, and proposes which kind of ledger this is, which column fills which field and how the
ledger's words map to ours. It never writes data: code checks the proposal (ledger.check_mapping), a person confirms
it, and code imports the rows (ledgers.py). Without a model, or when the call fails, the rules propose.
"""

from __future__ import annotations

import datetime as dt
import json

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.docs import ledger as LG
from wqops.i18n import say

SAMPLE = 15


def describe(t: LG.Table) -> str:
    data = t.data()
    lines = [f"Sheet: {t.sheet} (sheets: {', '.join(t.sheets)}); header row {t.header_row}; {len(data)} data rows",
             "Columns: " + json.dumps([h for h in t.headers if h])]
    for n, r in data[:SAMPLE]:
        lines.append(f"Row {n}: " + json.dumps({k: v for k, v in r.items() if v}, ensure_ascii=False)[:1500])
    for h in t.headers:
        vals = sorted({r.get(h, "") for _, r in data} - {""})
        if h and 0 < len(vals) <= 20:
            lines.append(f"Values in {h!r}: " + json.dumps(vals, ensure_ascii=False))
    return "\n".join(lines)


def tool(targets: dict[str, dict[str, LG.Field]]) -> dict:
    spec = {t: {f: {"label": x.label, "kind": x.kind, "required": x.required, "choices": list(x.choices)}
                for f, x in fl.items()} for t, fl in targets.items()}
    return {
        "name": "propose_mapping",
        "description": "Propose how this ledger's columns fill the fields of one target. Fields of each target: "
                       + json.dumps(spec),
        "input_schema": {"type": "object", "properties": {
            "target": {"type": "string", "enum": list(targets)},
            "mapping": {"type": "array", "items": {"type": "object", "properties": {
                "field": {"type": "string"}, "column": {"type": "string", "description": "a column name exactly"},
                "value": {"type": "string", "description": "only for a choice field that is the same for every row"
                                                           " (for example a log of corrective actions only)"}},
                "required": ["field"]}},
            "values": {"type": "array", "description": "for choice fields: how each word used in the column maps to "
                                                       "one of the field's choices; leave out words you are unsure of",
                       "items": {"type": "object", "properties": {
                           "field": {"type": "string"}, "ledger_value": {"type": "string"},
                           "our_value": {"type": "string"}}, "required": ["field", "ledger_value", "our_value"]}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "notes": {"type": "string", "description": "one or two sentences: what this ledger is, anything doubtful"},
        }, "required": ["target", "mapping", "confidence"]},
    }


def _proposal(inp: dict) -> tuple[str, dict]:
    mapping, values = {}, {}
    for m in inp.get("mapping") or []:
        if not isinstance(m, dict) or not m.get("field"):
            continue
        if m.get("column"):
            mapping[m["field"]] = {"column": str(m["column"])}
        elif m.get("value"):
            mapping[m["field"]] = {"value": str(m["value"])}
    for v in inp.get("values") or []:
        if isinstance(v, dict) and v.get("field"):
            values.setdefault(v["field"], {})[str(v.get("ledger_value", ""))] = str(v.get("our_value", ""))
    return str(inp.get("target") or ""), {"mapping": mapping, "values": values, "confidence": inp.get("confidence"),
                                          "notes": str(inp.get("notes") or "")}


def rules_target(t: LG.Table, targets: dict[str, dict[str, LG.Field]]) -> str:
    """The target whose fields the column names fill best (required fields count double). The records of the
    quality modules come first; a quality register is guessed only when none of them fits at all (the person can
    always choose the register)."""
    def score(tg):
        m = LG.rules_mapping(tg, t, targets[tg])["mapping"]
        return sum(2 if targets[tg][f].required else 1 for f in m)
    base = [tg for tg in targets if not tg.startswith("reg_")]
    best = max(base, key=score) if base else None
    return best if best and score(best) > 0 else max(targets, key=score)


def propose(conn, user: dict, t: LG.Table, targets: dict[str, dict[str, LG.Field]], model: L.Anthropic | None, *,
            target: str = "", today: dt.date, company: str = "the company") -> dict:
    """{"target", "proposal", "engine", "ai_run"}: the model's proposal when there is a model, else the rules'."""
    if model is None or not model.configured():
        tg = target or rules_target(t, targets)
        return {"target": tg, "proposal": LG.rules_mapping(tg, t, targets[tg]), "engine": "rules", "ai_run": None}
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "ledger", f"ledger mapping: {t.sheet}, {len(t.data())} rows")
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    allowed = {target: targets[target]} if target else targets
    try:
        resp = model.create(
            f"You help {company} bring its historical spreadsheets into its quality system. Look at the ledger and "
            "propose which target it is, which column fills each field (use column names exactly) and how the words "
            "in choice columns map to the field's choices. Only map what the ledger shows; leave the rest out. You "
            "never write data: a person checks your proposal and code imports the rows.",
            [{"role": "user", "content": describe(t)}], [tool(allowed)], 1500,
            tool_choice={"type": "tool", "name": "propose_mapping"})
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None:
            raise L.LlmError(say("the model did not propose a mapping"))
        tg, prop = _proposal(use.get("input") or {})
        if tg not in allowed:
            raise L.LlmError(say("the model chose an unknown ledger kind {tg}", tg=repr(tg)))
        out.update(usage=resp.get("usage", {}), answer=json.dumps({"target": tg} | prop)[:4000],
                   tool_calls=[{"tool": "propose_mapping", "args": {"sheet": t.sheet}, "ok": True,
                                "summary": f"{tg}: {len(prop['mapping'])} fields"}])
        AG.finish(ctx, out)
        return {"target": tg, "proposal": prop, "engine": "ai", "ai_run": ctx.run_id}
    except L.LlmError as exc:
        tg = target or rules_target(t, targets)
        AG.finish(ctx, out | {"engine": "rules (model unavailable)", "answer": "", "verified": False,
                              "error": str(exc)[:1000]})
        prop = LG.rules_mapping(tg, t, targets[tg])
        prop["notes"] = f"The model could not propose ({exc}); matched by column names."
        return {"target": tg, "proposal": prop, "engine": "rules", "ai_run": ctx.run_id}
