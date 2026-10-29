"""Daily brief (ADR-0008 item 6): every number computed by code; a model may only reword it, and its wording is used
only when every number checks out. Generated at 7:30 company time, or on request.

People see the parts their role allows: the stored facts are filtered per viewer and the rule text is rebuilt from
them; the model's wording is shown only to people who may see every part.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from wqops import i18n as I18N
from wqops.hub import drafts as D
from wqops.hub import permissions as P
from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import metrics as M
from wqops.i18n import say

AT = dt.time(7, 30)
SYSTEM = "brief@wenquest-ops"


def facts(conn, today: dt.date) -> dict:
    rules = AN.load_rules()
    metrics = {}
    for n in M.LABELS:
        r = M.compute(conn, n, today, 30)
        metrics[n] = {"label": M.LABELS[n], "value": r["value"], "unit": r["unit"]}
    since = dt.datetime.combine(today - dt.timedelta(days=1), dt.time(0), tzinfo=dt.UTC)
    anomalies = [{"id": a["id"], "rule": a["rule"], "title": a["title"], "severity": a["severity"],
                  "new": a["first_seen"] >= since, "about": [a["subject_type"], a["subject_key"]]}
                 for a in conn.execute("select * from anomalies where status in ('open', 'ack', 'doing') "
                                       "order by id").fetchall() if a["rule"] in rules]
    drafts = [{"id": d["id"], "kind": d["doctype"], "summary": d["summary"]}
              for d in conn.execute("select * from erp_drafts where status = 'pending' order by id").fetchall()]
    due = []
    for o in M._objs(conn, "SalesOrder"):
        if M._submitted(o["props"]) and o["props"].get("status") in M.OPEN_SO and \
                o["props"].get("delivery_date") == str(today):
            due.append({"type": "SalesOrder", "key": o["key"], "title": o["title"]})
    for o in M._objs(conn, "PurchaseOrder"):
        if M._submitted(o["props"]) and o["props"].get("status") not in AN.CLOSED_PO and \
                o["props"].get("schedule_date") == str(today):
            due.append({"type": "PurchaseOrder", "key": o["key"], "title": o["title"]})
    return {"day": str(today), "metrics": metrics, "anomalies": anomalies, "drafts": drafts, "due_today": due}


def for_roles(f: dict, roles) -> dict:
    """The parts of a brief this role may see."""
    rules = AN.load_rules()
    seen = set(AN.visible_rules(roles, rules))
    kinds = {k for k in D.DRAFTABLE if P.allows(roles, D.DRAFTABLE[k][0])}
    due_view = {"SalesOrder": "sales:view", "PurchaseOrder": "purchasing:view"}
    return {"day": f["day"], "metrics": {n: m for n, m in f["metrics"].items() if P.allows(roles, M.VIEW[n])},
            "anomalies": [a for a in f["anomalies"] if a["rule"] in seen],
            "drafts": [d for d in f["drafts"] if d["kind"] in kinds],
            "due_today": [d for d in f["due_today"] if P.allows(roles, due_view[d["type"]])]}


def _fmt(m: dict) -> str:
    v, u = m["value"], m["unit"]
    if v is None:
        return say("unknown")
    if u == "days":
        return say("{n} days", n=format(v, "g"))
    return {"%": f"{v:g}%", "currency": f"{v:,.2f}"}.get(u, f"{v:g}")


def text(f: dict, company: str) -> str:
    zh = I18N.current() == "zh"
    lines = [say("Good morning. Brief for {company}, {day}.", company=company, day=f["day"])]
    if f["metrics"]:
        lines.append(say("Last 30 days: {metrics}.", metrics=("；" if zh else "; ").join(
            f"{I18N.label(f['metrics'][n]['label'])} {_fmt(f['metrics'][n])}" for n in M.LABELS if n in f["metrics"])))
    new = [a for a in f["anomalies"] if a["new"]]
    crit = [a for a in f["anomalies"] if a["severity"] == "critical"]
    if f["anomalies"]:
        lines.append(say("Open problems: {n}, of which {new} new since yesterday and {critical} critical.",
                         n=len(f["anomalies"]), new=len(new), critical=len(crit)))
        lines += [say("- {severity}: {title}", severity=I18N.label(a["severity"]), title=a["title"])
                  for a in (crit + [a for a in new if a not in crit])[:8]]
    else:
        lines.append(say("No open problems."))
    if f["due_today"]:
        titles = ("、" if zh else ", ").join(d["title"] for d in f["due_today"])
        lines.append(say("Due today: {titles}.", titles=titles))
    if f["drafts"]:
        lines.append(say("Drafts waiting for confirmation: {n}.", n=len(f["drafts"])))
    return "\n".join(lines)


def generate(conn, today: dt.date, manifest: dict | None, model: L.Anthropic | None = None) -> dict:
    """Make (or remake) the brief for ``today``."""
    company = (manifest or {}).get("company", {}).get("name") or say("the company")
    f = facts(conn, today)
    rule_text = text(f, company)
    ctx = T.Ctx(conn=conn, user={"email": SYSTEM, "roles": ["owner"]}, today=today, manifest=manifest)
    AG.start(ctx, "brief", f"daily brief {today}")
    out = {"engine": "rules", "model": None, "tool_calls": [], "answer": rule_text, "verified": True,
           "unverified": [], "usage": {}}
    model_text = None
    if model is not None and model.configured():
        try:
            resp = model.create(
                "Rewrite this operations brief for a small business owner: friendly, short, plain words, keep every "
                "number and date exactly as given, add nothing that is not in the facts.",
                [{"role": "user", "content": "Facts (JSON):\n" + json.dumps(f, ensure_ascii=False)
                                             + f"\n\nBrief:\n{rule_text}"}], [], 800)
            draft = "\n".join(b["text"] for b in resp.get("content", []) if b.get("type") == "text").strip()
            bad = AG.verify(draft, json.dumps(f, ensure_ascii=False) + "\n" + rule_text)
            out.update(model=model.model, usage=resp.get("usage", {}), unverified=bad, verified=not bad)
            if draft and not bad:
                model_text, out["engine"], out["answer"] = draft, "model", draft
            else:
                out["engine"] = "rules (model wording failed the number check)"
        except L.LlmError as exc:
            out.update(engine="rules (model unavailable)", error=str(exc))
    AG.finish(ctx, out)
    row = conn.execute("insert into briefs (day, facts, rule_text, model_text, engine, run_id) values "
                       "(%s, %s, %s, %s, %s, %s) on conflict (day) do update set facts = excluded.facts, "
                       "rule_text = excluded.rule_text, model_text = excluded.model_text, engine = excluded.engine, "
                       "run_id = excluded.run_id, created_at = now() returning *",
                       (today, Jsonb(f), rule_text, model_text, out["engine"], ctx.run_id)).fetchone()
    return row


def due(conn, manifest: dict | None, now: dt.datetime | None = None) -> dt.date | None:
    """The day whose brief should be made now: today, after 7:30 company time, if not made yet."""
    tz = ZoneInfo(manifest["company"]["timezone"]) if manifest else dt.UTC
    local = (now or dt.datetime.now(dt.UTC)).astimezone(tz)
    if local.time() < AT:
        return None
    exists = conn.execute("select 1 from briefs where day = %s", (local.date(),)).fetchone()
    return None if exists else local.date()


def view(row: dict, roles, company: str) -> dict:
    full = set(P.of(roles)) >= {"sales:view", "inventory:view", "purchasing:view", "quality:view",
                                "purchasing:draft", "quality:edit"}
    f = for_roles(row["facts"], roles)
    body = row["model_text"] if full and row["model_text"] else text(f, company)
    return {"day": str(row["day"]), "text": body, "facts": f, "engine": row["engine"] if full else "rules",
            "created_at": row["created_at"].isoformat(), "run_id": row["run_id"] if full else None}
