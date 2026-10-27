"""The assistant's question-answering (ADR-0008 items 1, 2, 4, 5).

With a model key, the model decides which tools to call (at most ``MAX_ROUNDS`` rounds). Without one, or when the
model cannot be reached, the rule engine answers common questions by calling the same tools in fixed steps.
Every number in the answer must appear in the question or a tool result; sentences with other numbers are marked
unverified. Every run is stored in ``ai_runs``.
"""

from __future__ import annotations

import json
import re

from psycopg.types.json import Jsonb

from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.i18n import say

MAX_ROUNDS = 8
HISTORY = 6        # earlier questions and answers of the conversation sent with a follow-up (ADR-0021)
MAX_RESULT = 20000
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
SMALL = 10  # small counts ("3 orders") may be counted by the model itself


def page_line(page: dict | None) -> str:
    """What the person is looking at, from the chat panel (ADR-0021 item 3); only plain words go to the model."""
    if not page:
        return ""
    title = str(page.get("title") or "")[:120]
    path = str(page.get("path") or "")[:200]
    rec = page.get("record") or {}
    line = f"\nThe person is looking at the page {title!r} ({path})."
    if rec.get("kind") and rec.get("id"):
        line += (f" It shows the record kind {str(rec['kind'])[:20]!r} with id {int(rec['id'])}: when they say "
                 "'this' or 'here', read it with get_record.")
    return line


def system_prompt(ctx: T.Ctx, page: dict | None = None) -> str:
    company = (ctx.manifest or {}).get("company", {}).get("name", "the company")
    return (
        f"You are the operations assistant of {company}, inside WenQuest Ops. Today is {ctx.today}. "
        "Answer in English, briefly and concretely, for a busy operations person.\n"
        "Rules:\n"
        "- Get every fact from the tools. Never guess or invent numbers, names or dates; if the tools do not say, "
        "say it is unknown.\n"
        "- Cite the objects you rely on exactly as the tools write them, e.g. [SalesOrder:SO-0042].\n"
        "- A metric value of null means unknown, not zero.\n"
        "- You cannot change anything in ERPNext and cannot send messages. You may only prepare drafts with the "
        "draft tools, if offered; a person must confirm them. Never say something was ordered, sent or submitted.\n"
        "- If the person's role cannot see something, say so rather than working around it."
        + page_line(page)
    )


def _numbers(text: str) -> list[str]:
    return DATE.findall(text) + NUM.findall(DATE.sub(" ", text))


def _value(n: str) -> float | None:
    try:
        return float(n.replace(",", ""))
    except ValueError:
        return None


def verify(answer: str, corpus: str) -> list[str]:
    """Sentences of the answer with a number that is not in the corpus (question and tool results)."""
    dates = set(DATE.findall(corpus))
    known = [v for v in (_value(n) for n in NUM.findall(DATE.sub(" ", corpus))) if v is not None]
    known += [float(p) for d in dates for p in d.split("-")]
    bad = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for n in _numbers(sentence):
            if DATE.fullmatch(n):
                if n not in dates:
                    bad.append(sentence.strip())
                    break
                continue
            v = _value(n)
            if v is None or (v.is_integer() and 0 <= v <= SMALL):
                continue
            decimals = len(n.split(".")[1]) if "." in n else 0
            if not any(abs(v - k) < 1e-9 or abs(v - round(k, decimals)) < 1e-9 for k in known):
                bad.append(sentence.strip())
                break
    return bad


def _summary(result: dict) -> str:
    s = json.dumps(result, default=str)
    return s[:300] + ("..." if len(s) > 300 else "")


def start(ctx: T.Ctx, kind: str, question: str) -> int:
    """Open the run record first, so drafts made during the run can point to it."""
    ctx.run_id = ctx.conn.execute(
        "insert into ai_runs (email, kind, question, engine) values (%s, %s, %s, 'running') returning id",
        (ctx.user["email"], kind, question),
    ).fetchone()["id"]
    return ctx.run_id


def finish(ctx: T.Ctx, out: dict) -> None:
    ctx.conn.execute(
        "update ai_runs set engine = %s, model = %s, tool_calls = %s, answer = %s, verified = %s, unverified = %s, "
        "refs = %s, drafts = %s, usage = %s, error = %s where id = %s",
        (
            out["engine"],
            out.get("model"),
            Jsonb(out["tool_calls"]),
            out["answer"],
            out["verified"],
            Jsonb(out["unverified"]),
            Jsonb(ctx.refs),
            Jsonb(ctx.drafts),
            Jsonb(out.get("usage", {})),
            out.get("error"),
            ctx.run_id,
        ),
    )


def _run_tool(ctx, tools, name, args, calls, corpus):  # noqa: PLR0917 - internal helper
    try:
        result = T.call(ctx, tools, name, args)
        ok = True
    except T.ToolError as exc:
        result, ok = {"error": str(exc)}, False
    text = json.dumps(result, default=str)[:MAX_RESULT]
    corpus.append(text)
    calls.append({"tool": name, "args": args, "ok": ok, "summary": _summary(result)})
    return text, ok


def with_model(ctx: T.Ctx, question: str, model: L.Anthropic, tools: dict[str, T.Tool],  # noqa: PLR0917
               history: list[dict] | None = None, page: dict | None = None) -> dict:
    messages: list[dict] = []
    for h in (history or [])[-HISTORY:]:                 # the conversation so far, as plain text
        messages += [{"role": "user", "content": h["question"]}, {"role": "assistant", "content": h["answer"] or "-"}]
    messages.append({"role": "user", "content": question})
    calls: list[dict] = []
    corpus = [question] + [h["answer"] or "" for h in (history or [])[-HISTORY:]]
    usage = {"input_tokens": 0, "output_tokens": 0}
    specs = [t.spec() for t in tools.values()]
    for _ in range(MAX_ROUNDS):
        resp = model.create(system_prompt(ctx, page), messages, specs)
        for k in usage:
            usage[k] += int(resp.get("usage", {}).get(k, 0))
        content = resp.get("content", [])
        messages.append({"role": "assistant", "content": content})
        uses = [b for b in content if b.get("type") == "tool_use"]
        if resp.get("stop_reason") != "tool_use" or not uses:
            answer = "\n".join(b["text"] for b in content if b.get("type") == "text").strip()
            return {
                "engine": "model",
                "model": model.model,
                "answer": answer,
                "tool_calls": calls,
                "corpus": corpus,
                "usage": usage,
            }
        results = []
        for b in uses:
            text, ok = _run_tool(ctx, tools, b["name"], b.get("input") or {}, calls, corpus)
            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": text, "is_error": not ok})
        messages.append({"role": "user", "content": results})
    return {
        "engine": "model",
        "model": model.model,
        "tool_calls": calls,
        "corpus": corpus,
        "usage": usage,
        "answer": "I could not finish within the allowed number of steps. Please ask a narrower question.",
    }


# ---------------------------------------------------------------- rule engine

HELP = (
    "I can answer, without an AI model configured: late orders, items short, on-time delivery, supplier "
    "on-time, inventory value, days of inventory, open anomalies, and what is wrong with a given order, item, "
    "purchase order or supplier (name it by its number)."
)
TOPICS = [
    (("supplier", "vendor"), "supplier_on_time"),
    (("late", "overdue", "behind"), "late"),
    (("short", "shortage", "stockout", "out of stock"), "shortages"),
    (("on-time", "on time", "otd"), "on_time_delivery"),
    (("days of inventory", "days of stock", "doi"), "days_of_inventory"),
    (("inventory value", "stock value", "worth"), "inventory_value"),
    (("nonconform", "rejected", "inspection"), "open_nonconformances"),
    (("anomal", "problem", "attention", "issue", "wrong today"), "anomalies"),
]


def _cite(ref: str, title: str) -> str:
    """'[SalesOrder:SO-8]' + 'SO-8 Bayside Hardware is late' -> '[SalesOrder:SO-8] Bayside Hardware is late'."""
    key = ref[1:-1].split(":", 1)[1]
    rest = title[len(key) :].strip() if title.startswith(key) else title
    return f"{ref} {rest}".strip()


def _fmt(v, unit) -> str:
    if v is None:
        return "unknown"
    return {"%": f"{v:g}%", "currency": f"{v:,.2f}", "days": f"{v:g} days"}.get(unit, f"{v:g}")


THIS = ("this", "here", "summar", "status of it", "what is it")
SHOWN = ("name", "title", "product", "item_code", "lot_no", "customer", "supplier", "status", "severity", "owner",
         "due", "result", "description", "conclusion")


def with_rules(ctx: T.Ctx, question: str, tools: dict[str, T.Tool], page: dict | None = None) -> dict:  # noqa: PLR0912
    calls: list[dict] = []
    corpus = [question]
    lines: list[str] = []

    def use(tool, **args):
        text, ok = _run_tool(ctx, tools, tool, args, calls, corpus)
        return json.loads(text) if ok else None

    q = question.lower()
    rec = (page or {}).get("record") or {}
    if rec.get("kind") and rec.get("id") and "get_record" in tools and any(w in q for w in THIS):
        got = use("get_record", kind=rec["kind"], id=rec["id"])     # "summarize this": the record on the page
        if got is None:
            lines.append(calls[-1]["summary"])
        else:
            r = got["record"]
            lines.append(f"{got['ref']}.")
            lines += [f"{k.replace('_', ' ').capitalize()}: {str(r[k]).rstrip('.')}." for k in SHOWN[1:]
                      if r.get(k) not in (None, "")]
            return {"engine": "rules", "model": None, "answer": "\n".join(lines), "tool_calls": calls,
                    "corpus": corpus}
    # a named object: answer about it first
    for word in re.findall(r"[A-Za-z0-9][\w./-]*\d[\w./-]*", question):
        found = ctx.conn.execute(
            "select type, key, title from ont_objects where not deleted and lower(key) = %s "
            "and type = any(%s) order by type limit 1",
            (word.lower(), [t for t in ctx.onto.types if ctx.onto.can_see(ctx.roles, t)]),
        ).fetchone()
        if found:
            obj = use("get_object", type=found["type"], key=found["key"])
            ex = use("explain", type=found["type"], key=found["key"])
            lines.append(f"{_cite(obj['ref'], obj['title'])}.")
            lines += [f"Open: {a['title']} ({a['severity']})." for a in obj["open_anomalies"]]
            lines += [f"Cause: {s['why']}" for s in ex["causes"]]
            lines += [f"Affects: {s['why']}" for s in ex["impact"]]
            if not obj["open_anomalies"] and not ex["causes"]:
                lines.append("No open problems and no causes found in the synced data.")
            break
    if not lines:
        for words, topic in TOPICS:
            if not any(w in q for w in words):
                continue
            if topic == "late":
                m = use("get_metric", name="on_time_delivery")
                a = use("list_anomalies")
                late = [x for x in (a or {}).get("anomalies", []) if x["rule"].startswith("Sales order past")]
                lines += [f"{_cite(x['about'], x['title'])}." for x in late] or [
                    "No sales order is past its delivery date."
                ]
                if m:
                    lines.append(f"On-time delivery over 30 days: {_fmt(m['value'], '%')}.")
            elif topic == "anomalies":
                a = use("list_anomalies")
                lines += [
                    f"{x['severity']}: {_cite(x['about'], x['title'])}." for x in (a or {}).get("anomalies", [])
                ] or ["No open anomalies."]
            else:
                m = use("get_metric", name=topic)
                if m is None:
                    lines.append(calls[-1]["summary"])
                    break
                lines.append(f"{m['label']}: {_fmt(m['value'], m['unit'])}. {m['definition']}")
                lines += [
                    f"{_cite('[Item:' + i['item'] + ']', i['title'])} short {i['short']:g}." for i in m.get("items", [])
                ]
                lines += [
                    f"{s['supplier']}: {_fmt(s['value'], '%')} ({s['on_time']} of {s['total']})."
                    for s in m.get("suppliers", [])
                ]
            break
    return {"engine": "rules", "model": None, "answer": "\n".join(lines) or HELP, "tool_calls": calls, "corpus": corpus}


def ask(ctx: T.Ctx, question: str, model: L.Anthropic | None = None,
        extra_tools: list[T.Tool] | None = None, *, chat_id: int | None = None, page: dict | None = None) -> dict:
    """Answer one question and record the run; in a conversation, with its earlier questions and the page."""
    question = question.strip()[:2000]
    tools = T.registry(extra_tools)
    history = [dict(r) for r in ctx.conn.execute(
        "select question, answer from ai_runs where chat_id = %s and kind = 'ask' order by id", (chat_id,))] \
        if chat_id else []
    start(ctx, "ask", question)
    if chat_id or page:
        ctx.conn.execute("update ai_runs set chat_id = %s, page = %s where id = %s",
                         (chat_id, Jsonb(page) if page else None, ctx.run_id))
    error = None
    if model is not None and model.configured():
        try:
            out = with_model(ctx, question, model, tools, history, page)
        except L.LlmError as exc:
            error = str(exc)
            out = with_rules(ctx, question, tools, page)
            out["engine"] = "rules (model unavailable)"
    else:
        out = with_rules(ctx, question, tools, page)
    bad = verify(out["answer"], "\n".join(out.pop("corpus")))
    out.update(verified=not bad, unverified=bad, error=error)
    finish(ctx, out)
    return out | {"run_id": ctx.run_id, "refs": ctx.refs, "drafts": ctx.drafts}


def draft(ctx: T.Ctx, kind: str, key: str) -> dict:
    """Prepare one draft directly (a button on an object page); recorded as a run like a question."""
    from wqops.hub.ai import drafting as DR  # noqa: PLC0415

    if kind not in DR.KINDS:
        raise T.ToolError(say("no draft kind {kind}; kinds: {KINDS}", kind=kind, KINDS=', '.join(DR.KINDS)))
    start(ctx, "draft", f"Draft {kind.replace('_', ' ')} for {key}")
    out = {"engine": "rules", "tool_calls": [], "unverified": [], "verified": True}
    try:
        res = DR.KINDS[kind](ctx, key)
        out["answer"] = res["summary"]
        out["tool_calls"].append({"tool": kind, "args": {"key": key}, "ok": True, "summary": res["summary"]})
    except T.ToolError as exc:
        out.update(answer=str(exc), error=str(exc))
        out["tool_calls"].append({"tool": kind, "args": {"key": key}, "ok": False, "summary": str(exc)})
        finish(ctx, out)
        raise
    finish(ctx, out)
    return out | {"run_id": ctx.run_id, "drafts": ctx.drafts, "draft": res}
