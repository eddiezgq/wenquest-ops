"""AI assistant endpoints (ADR-0008): ask, status, run records and feedback."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import agent as AG
from wqops.hub.ai import drafting as DR
from wqops.hub.ai import tools as T
from wqops.hub.ont import api as OA


def _run(r: dict) -> dict:
    return {**r, "created_at": r["created_at"].isoformat()}


def mount(app: FastAPI, conn_dep, user_dep, company, model, db_url: str | None) -> None:  # noqa: PLR0917
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

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
            raise HTTPException(400, "ask a question")

        def work():
            with DB.connect(db_url) as c:
                return AG.ask(ctx(c, u), q, model, DR.DRAFT_TOOLS)

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
            raise HTTPException(404, "no such run")
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
            raise HTTPException(403, "only the person who asked can rate an answer")
        useful = (await request.json()).get("useful")
        if not isinstance(useful, bool):
            raise HTTPException(400, "useful must be true or false")
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
