"""The model suggests causes for a fishbone or answers to the next why, step 22b (ADR-0022).

It reads the record analysed and the related records ``causes.context`` gathers, and nothing else. Every suggestion
must cite at least one of those records by number; code keeps only those that do (``causes_rules.verify``) and stores
them as proposed. A person accepts, edits or removes each one; the model never concludes. The run is recorded in
``ai_runs`` with what was dropped. Without a model key, people analyse by hand.
"""

from __future__ import annotations

import datetime as dt

from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.quality import causes as C
from wqops.hub.quality import causes_rules as CR

MAX_SUGGESTIONS = 12


class NoModel(RuntimeError):
    pass


def _tool(method: str, cats: list[str]) -> dict:
    ref = {"type": "array", "items": {"type": "string"}, "description": "numbers of the records it rests on"}
    if method == "fishbone":
        item = {"type": "object", "properties": {"category": {"type": "string", "enum": cats},
                                                 "text": {"type": "string"}, "refs": ref},
                "required": ["category", "text", "refs"]}
        name, key = "suggest_causes", "causes"
    else:
        item = {"type": "object", "properties": {"text": {"type": "string"}, "refs": ref}, "required": ["text", "refs"]}
        name, key = "suggest_answers", "answers"
    return {"name": name, "description": "Give the possible causes for a person to check, each citing records.",
            "input_schema": {"type": "object", "properties": {
                key: {"type": "array", "items": item},
                "note": {"type": "string", "description": "what the records do not show, in one or two sentences"}},
                "required": [key]}}


SYSTEM = (
    "You help a quality team find the root cause of a problem. You are shown one record and related records of the "
    "company. Suggest possible causes that these records support, each one short and specific, and cite the record "
    "numbers it rests on (refs). Use only the records shown; never invent a record, a number, a date or a fact. If the "
    "records do not support a cause, do not suggest it; say what is missing in the note instead. Never blame a named "
    "person; describe the condition (for example 'no work instruction for torque'). These are suggestions: a person "
    "checks every one and decides the root cause.")


def _ask(a: dict, its: list[dict], level: int | None) -> str:
    so_far = [i for i in its if i["status"] == "accepted"]
    if a["method"] == "fishbone":
        ask = f"Problem: {a['problem']}\nCategories: {', '.join(a['categories'])}\n"
        if so_far:
            ask += ("Causes the team already accepted:\n" + "\n".join(f"- {i['category']}: {i['text']}" for i in so_far)
                    + "\nSuggest other causes.\n")
        ask += f"Suggest up to {MAX_SUGGESTIONS} possible causes across the categories."
    else:
        chain = sorted(so_far, key=lambda x: x["level"])
        ask = f"Problem: {a['problem']}\n"
        if chain:
            ask += "The team's answers so far:\n" + "\n".join(f"Why {i['level']}: {i['text']}" for i in chain) + "\n"
            ask += f"Why {level}: why did this happen: '{chain[-1]['text']}'?"
        else:
            ask += "Why 1: why did the problem happen?"
        ask += " Suggest up to 3 answers."
    removed = [i["text"] for i in its if i["status"] == "removed"]
    if removed:
        ask += "\nThe team removed these; do not suggest them again:\n" + "\n".join(f"- {t}" for t in removed[:20])
    return ask


def _clean(a: dict, raw, level: int | None) -> tuple[list[dict], int]:
    """The suggestions in a usable shape, and how many were not (no text, or a category the fishbone lacks)."""
    raw = [p for p in (raw if isinstance(raw, list) else []) if isinstance(p, dict)][:MAX_SUGGESTIONS]
    clean, bad = [], 0
    for p in raw:
        cat = p.get("category") if a["method"] == "fishbone" else None
        try:
            t = CR.text(p.get("text"))
        except CR.CauseError:
            t = None
        if t is None or (a["method"] == "fishbone" and cat not in a["categories"]):
            bad += 1
            continue
        clean.append({"text": t, "category": cat, "level": level, "refs": p.get("refs")})
    return clean, bad


def suggest(conn, user: dict, aid: int, model: L.Anthropic | None, *, today: dt.date) -> dict:
    if model is None or not model.configured():
        raise NoModel("there is no model key; add the causes yourself")
    a = C.get(conn, aid)
    its = C.items(conn, aid)
    if a["status"] != "open":
        raise CR.CauseError(f"{a['name']} is {a['status']}")
    if any(i["status"] == "proposed" for i in its):
        raise CR.CauseError("decide the suggestions already made first")
    level = None
    if a["method"] == "five_why":
        level = CR.frontier(its)
        CR.can_add(a, its, category=None, level=level)
    recs = C.context(conn, C.subject(conn, a["ref_kind"], a["ref_id"]), today=today)
    shown = {r["ref"] for r in recs}
    listing = "\n".join(f"[{r['ref']}] {r['kind']}: {r['summary']}" for r in recs)
    ctx = T.Ctx(conn=conn, user=user, today=today)
    AG.start(ctx, "cause", f"{CR.METHODS[a['method']]} {a['name']} on {a['ref_name']}"
             + (f", why {level}" if level else ""))
    out = {"engine": "model", "model": model.model, "tool_calls": [], "verified": True, "unverified": [], "usage": {}}
    try:
        tool = _tool(a["method"], a["categories"])
        resp = model.create(SYSTEM, [{"role": "user", "content": f"{_ask(a, its, level)}\n\nRecords:\n{listing}"}],
                            [tool], 3000, tool_choice={"type": "tool", "name": tool["name"]})
        if resp.get("stop_reason") == "max_tokens":
            raise L.LlmError("the model's answer was cut off")
        use = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
        if use is None or not isinstance(use.get("input"), dict):
            raise L.LlmError("the model did not suggest anything")
        clean, bad = _clean(a, use["input"].get("causes" if a["method"] == "fishbone" else "answers"), level)
        kept, dropped = CR.verify(clean, shown)
        made = C.propose(conn, aid, ctx.run_id, user["email"], kept) if kept else []
        ctx.refs = sorted({r for p in kept for r in p["refs"]})
        note = CR.CONTROL.sub(" ", str(use["input"].get("note") or "")).strip()[:600]
        out.update(usage=resp.get("usage", {}), answer=note or f"{len(made)} suggestions",
                   verified=not dropped and not bad, unverified=dropped,
                   tool_calls=[{"tool": tool["name"], "args": {"analysis": a["name"], "level": level}, "ok": True,
                                "summary": f"{len(made)} kept, {len(dropped) + bad} dropped"}])
        AG.finish(ctx, out)
        return {"run": ctx.run_id, "items": made, "dropped": dropped, "unusable": bad, "note": note,
                "shown": len(recs)}
    except Exception as exc:                    # the run is closed whatever went wrong, then the error goes on
        AG.finish(ctx, out | {"engine": "model (failed)", "answer": "", "verified": False,
                              "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
