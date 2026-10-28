"""AI assistant endpoints (ADR-0008): ask, status, run records and feedback."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import agent as AG
from wqops.hub.ai import brief as BR
from wqops.hub.ai import drafting as DR
from wqops.hub.ai import record_tool as RT
from wqops.hub.ai import tools as T
from wqops.hub.ont import api as OA
from wqops.i18n import say


def _run(r: dict) -> dict:
    return {**r, "created_at": r["created_at"].isoformat()}


def mount(app: FastAPI, conn_dep, user_dep, company, model, db_url: str | None) -> None:  # noqa: PLR0915, PLR0917
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.describe(perm)))

    def ctx(c, u) -> T.Ctx:
        m = company()[0]
        return T.Ctx(conn=c, user=u, today=OA.today(m), manifest=m)

    @app.get("/api/ai/status")
    def ai_status(u=Depends(user_dep)):
        need(u, "ai:use")
        on = model is not None and model.configured()
        return {"model_configured": on, "model": model.model if on else None,
                "engine": "model" if on else "rules", "provider": model.name if on else None}

    @app.post("/api/ai/ask")
    async def ai_ask(request: Request, u=Depends(user_dep)):
        need(u, "ai:use")
        q = str((await request.json()).get("question", "")).strip()
        if not q:
            raise HTTPException(400, say("ask a question"))

        def work():
            with DB.connect(db_url) as c:
                return AG.ask(ctx(c, u), q, model, [*DR.DRAFT_TOOLS, RT.TOOL])

        return await asyncio.to_thread(work)

    # ---------------------------------------------------------------- conversations (ADR-0021)

    def chat_of(c, u, cid: int) -> dict:
        r = c.execute("select * from ai_chats where id = %s", (cid,)).fetchone() if 0 < cid < 2**63 else None
        if r is None or r["email"] != u["email"]:
            raise HTTPException(404, say("no such conversation"))
        return r

    def page_of(raw) -> dict | None:
        """The page the question was asked on: plain text, and a record of a known kind with a whole id."""
        if not isinstance(raw, dict):
            return None
        page = {"path": str(raw.get("path") or "")[:200], "title": str(raw.get("title") or "")[:120]}
        rec = raw.get("record")
        if isinstance(rec, dict) and rec.get("kind") in RT.KINDS and type(rec.get("id")) is int \
                and 0 < rec["id"] < 2**63:
            page["record"] = {"kind": rec["kind"], "id": rec["id"]}
        return page

    def chat_out(c, r: dict) -> dict:
        runs = c.execute("select * from ai_runs where chat_id = %s order by id", (r["id"],)).fetchall()
        return {"id": r["id"], "title": r["title"], "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(), "turns": [_run(x) for x in runs]}

    @app.get("/api/ai/chats")
    def ai_chats(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        rows = c.execute("select h.*, (select count(*) from ai_runs r where r.chat_id = h.id) as turns from ai_chats h "
                         "where email = %s order by updated_at desc limit 50", (u["email"],)).fetchall()
        return [{"id": r["id"], "title": r["title"], "turns": r["turns"], "updated_at": r["updated_at"].isoformat()}
                for r in rows]

    @app.post("/api/ai/chats", status_code=201)
    def ai_new_chat(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        return chat_out(c, c.execute("insert into ai_chats (email) values (%s) returning *", (u["email"],)).fetchone())

    @app.get("/api/ai/chats/{cid}")
    def ai_chat(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        return chat_out(c, chat_of(c, u, cid))

    @app.post("/api/ai/chats/{cid}/ask")
    async def ai_chat_ask(cid: int, request: Request, u=Depends(user_dep)):
        need(u, "ai:use")
        try:
            data = await request.json()
        except ValueError as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        data = data if isinstance(data, dict) else {}
        q = str(data.get("question") or "").strip()
        if not q:
            raise HTTPException(400, say("ask a question"))
        page = page_of(data.get("page"))

        def work():
            with DB.connect(db_url) as c:
                chat = chat_of(c, u, cid)
                out = AG.ask(ctx(c, u), q, model, [*DR.DRAFT_TOOLS, RT.TOOL], chat_id=cid, page=page)
                c.execute("update ai_chats set updated_at = now(), title = case when title = '' then %s else title "
                          "end where id = %s", (q[:80], chat["id"]))
                return out

        return await asyncio.to_thread(work)

    @app.get("/api/ai/runs")
    def ai_runs(everyone: bool = False, limit: int = 50, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        if everyone:
            need(u, "ai:configure")
        sql, args = "select * from ai_runs", []
        if not everyone:
            sql += " where email = %s"
            args.append(u["email"])
        rows = c.execute(sql + " order by id desc limit %s", [*args, max(1, min(limit, 200))]).fetchall()
        return [_run(r) for r in rows]

    def own(c, u, rid: int) -> dict:
        r = c.execute("select * from ai_runs where id = %s", (rid,)).fetchone()
        if r is None or (r["email"] != u["email"] and not P.allows(u["roles"], "ai:configure")):
            raise HTTPException(404, say("no such run"))
        return r

    @app.get("/api/ai/runs/{rid}")
    def ai_run(rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        return _run(own(c, u, rid))

    @app.post("/api/ai/runs/{rid}/feedback")
    async def ai_feedback(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:use")
        r = own(c, u, rid)
        if r["email"] != u["email"]:
            raise HTTPException(403, say("only the person who asked can rate an answer"))
        useful = (await request.json()).get("useful")
        if not isinstance(useful, bool):
            raise HTTPException(400, say("useful must be true or false"))
        c.execute("update ai_runs set feedback = %s where id = %s", (1 if useful else -1, rid))
        return {"ok": True}

    @app.post("/api/ai/draft")
    async def ai_draft(request: Request, u=Depends(user_dep)):
        """Prepare a draft from an object: purchase_order (item), delay_message (sales order), nonconformance
        (inspection). It stays pending until a person confirms it."""
        need(u, "ai:use")
        data = await request.json()

        def work():
            with DB.connect(db_url) as c:
                return AG.draft(ctx(c, u), str(data.get("kind", "")), str(data.get("key", "")))

        try:
            return await asyncio.to_thread(work)
        except T.ToolError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/brief")
    def get_brief(u=Depends(user_dep), c=Depends(conn_dep)):
        """Today's brief (or the latest), showing only what this role may see."""
        need(u, "dashboard:view")
        row = c.execute("select * from briefs order by day desc limit 1").fetchone()
        if row is None:
            raise HTTPException(404, say("no brief yet; the first one is made at 7:30 company time"))
        m = company()[0]
        return BR.view(row, u["roles"], (m or {}).get("company", {}).get("name") or say("the company"))

    @app.post("/api/brief/generate")
    def make_brief(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "ai:configure")
        m = company()[0]
        row = BR.generate(c, OA.today(m), m, model)
        return BR.view(row, u["roles"], (m or {}).get("company", {}).get("name") or say("the company"))
