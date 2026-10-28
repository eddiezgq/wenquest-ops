"""The AI drafts rows of a process FMEA, step 22c (ADR-0022).

It reads the PFMEA's process, its rows so far, and the records about its item that ``fmea.context`` gathers, and
proposes failure modes with their effects and causes, each citing those records. Code keeps only rows citing a record
it was shown (``fmea_rules.verify``) and adds them unconfirmed. **It never gives a rank**: the tool has no field for
one, and any rank it sends is ignored. A person confirms or removes each row and gives the ranks. The run is recorded
in ``ai_runs``. Without a model key, people write the rows.
"""

from __future__ import annotations

import datetime as dt
import re

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.quality import fmea as F
from wqops.hub.quality import fmea_rules as FR
from wqops.i18n import say

MAX_ROWS = 15
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
TEXT = ("step", "failure_mode", "effect", "cause", "prevention", "detection_controls")


class NoModel(RuntimeError):
    pass


TOOL = {
    "name": "draft_rows",
    "description": "Draft rows of the process FMEA for a person to check. Give no ranks.",
    "input_schema": {"type": "object", "properties": {
        "rows": {"type": "array", "items": {"type": "object", "properties": {
            "step": {"type": "string", "description": "the process step"},
            "failure_mode": {"type": "string"}, "effect": {"type": "string"}, "cause": {"type": "string"},
            "prevention": {"type": "string", "description": "a control already in place that the records show, or ''"},
            "detection_controls": {"type": "string", "description": "a detection the records show is in place, or ''"},
            "refs": {"type": "array", "items": {"type": "string"}, "description": "record numbers"}},
            "required": ["step", "failure_mode", "effect", "cause", "refs"]}},
        "note": {"type": "string", "description": "what the records do not show, in one or two sentences"}},
        "required": ["rows"]},
}

SYSTEM = (
    "You help a quality team draft a process FMEA. From the records shown, propose failure modes of the process, "
    "each with the step, the effect on the product or the customer, and the cause, citing the record numbers it rests "
    "on (refs). Use only the records shown; never invent a record, a number or a fact. Do not repeat rows the team "
    "already has. Do not rate severity, occurrence or detection: the team does that on its own scales. Never blame a "
    "named person. A person checks every row.")


def _t(v, n: int = 500) -> str:
    return re.sub(r"\s+", " ", CONTROL.sub(" ", str(v if v is not None else ""))).strip()[:n]


def suggest(conn, user: dict, fid: int, model: L.Anthropic | None, *, today: dt.date) -> dict:
    if model is None or not model.configured():
        raise NoModel(say("there is no model key; write the rows yourself"))
    f = F.get(conn, fid)
    if f["status"] != "draft":
        raise F.FmeaError(say("the PFMEA is {status}: start a new version to change it", status=f['status']))
    have = F.rows(conn, fid)
    if any(not r["confirmed"] for r in have):
        raise F.FmeaError(say("confirm or remove the rows the AI drafted before asking again"))
    recs = F.context(conn, f, today=today)
    if not recs:
        raise F.FmeaError(say("there are no records about this PFMEA's item for the AI to read (give the item, or "
                              "write the rows yourself)"))
    shown = {r["ref"] for r in recs}
    listing = "\n".join(f"[{r['ref']}] {r['kind']}: {r['summary']}" for r in recs)
    rows_now = "\n".join(f"- {r['step']}: {r['failure_mode']} ({r['cause']})" for r in have) or "none yet"
    ask = (f"Process: {f['process']}\nItem: {f['item_code']}\nScope: {f['scope'] or '-'}\n"
           f"Rows the team already has:\n{rows_now}\n\nDraft up to {MAX_ROWS} more rows.\n\nRecords:\n{listing}")
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "fmea", say("draft rows for {name} v{version} ({process})", name=f["name"], version=f["version"],
                              process=f["process"])[:1000])
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        resp = model.create(SYSTEM, [{"role": "user", "content": ask}], [TOOL], 4000,
                            tool_choice={"type": "tool", "name": "draft_rows"})
        if resp.get("stop_reason") == "max_tokens":
            raise L.LlmError(say("the model's answer was cut off"))
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None or not isinstance(use.get("input"), dict):
            raise L.LlmError(say("the model did not draft any rows"))
        raw = use["input"].get("rows")
        clean, bad = [], 0
        for p in (raw if isinstance(raw, list) else [])[:MAX_ROWS]:
            if not isinstance(p, dict):
                bad += 1
                continue
            row = {k: _t(p.get(k)) for k in TEXT} | {"refs": p.get("refs") if isinstance(p.get("refs"), list) else []}
            if not all(row[k] for k in ("step", "failure_mode", "effect", "cause")):
                bad += 1
                continue
            clean.append(row)                    # any rank the model sent is not carried over
        kept, dropped = FR.verify(clean, shown)
        made = F.propose(conn, user["email"], fid, ctx.run_id, kept) if kept else []
        ctx.refs = sorted({r for p in kept for r in p["refs"]})
        note = _t(use["input"].get("note"), 600)
        out.update(usage=resp.get("usage", {}), answer=note or say("{n} rows drafted", n=len(made)),
                   verified=not dropped and not bad, unverified=dropped,
                   tool_calls=[{"tool": "draft_rows", "args": {"fmea": f["name"]}, "ok": True,
                                "summary": say("{kept} kept, {dropped} dropped", kept=len(made),
                                               dropped=len(dropped) + bad)}])
        AG.finish(ctx, out)
        return {"run": ctx.run_id, "rows": made, "dropped": dropped, "unusable": bad, "note": note,
                "shown": len(recs)}
    except Exception as exc:                    # the run is closed whatever went wrong, then the error goes on
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
