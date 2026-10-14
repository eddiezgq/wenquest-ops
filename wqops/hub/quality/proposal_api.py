"""Endpoints for workflow changes proposed from the company's procedures (ADR-0015, step 15c). Asking the model and
deciding on its changes needs workflows:configure (and documents:view to read the procedures); seeing proposals needs
quality:view.
"""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import llm as L
from wqops.hub.ont import api as OA
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_admin as WA
from wqops.hub.quality import workflow_ai as WAI
from wqops.hub.quality import workflow_proposals as WP


def mount(app: FastAPI, conn_dep, user_dep, company, model, db_url: str | None) -> None:  # noqa: PLR0915, PLR0917
    def need(u: dict, *perms: str) -> None:
        for perm in perms:
            if not P.allows(u["roles"], perm):
                raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def kind_of(kind: str) -> str:
        if kind not in W.KINDS:
            raise HTTPException(404, "no such workflow")
        return kind

    def run(fn):
        try:
            return fn()
        except (WA.AdminError, WP.ChangeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        d = (await request.json()) if raw else {}
        return d if isinstance(d, dict) else {}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def ai_ready() -> bool:
        return model is not None and model.configured()

    @app.get("/api/quality/workflows/{kind}/proposals")
    def proposals(kind: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        kind = kind_of(kind)
        can = all(P.allows(u["roles"], x) for x in ("workflows:configure", "documents:view", "ai:use"))
        procs = WP.procedures(c, kind) if can else []
        return {"ai": ai_ready(), "can_propose": can and ai_ready(), "proposals": WP.listing(c, kind),
                "procedures": [{k: r[k] for k in ("id", "number", "title", "revision", "status", "doc_type",
                                                  "original_name", "suggested", "text_chars")} for r in procs]}

    @app.post("/api/quality/workflows/{kind}/proposals", status_code=201)
    async def ask(kind: str, request: Request, u=Depends(user_dep)):
        """The model reads the chosen procedures and proposes changes; code checks each one."""
        need(u, "workflows:configure", "documents:view", "ai:use")
        kind = kind_of(kind)
        if not ai_ready():
            raise HTTPException(409, "there is no model key; the workflow can still be changed by hand")
        d = await body(request)
        raw = d.get("document_ids")
        if not isinstance(raw, list) or any(type(x) is not int or not 0 < x < 2**63 for x in raw):
            raise HTTPException(400, "document_ids is a list of document numbers")

        def work():
            with DB.connect(db_url) as c:
                docs = run(lambda: WP.read(c, kind, raw))
                m = company()[0]
                try:
                    p = WAI.propose(c, {"email": u["email"], "roles": u["roles"]}, kind, docs, model,
                                    today=OA.today(m), company=(m or {}).get("company", {}).get("name", "the company"))
                except L.LlmError as exc:
                    raise HTTPException(502, f"the model could not propose changes: {exc}") from exc
                return WP.view(c, p)

        return await asyncio.to_thread(work)

    @app.get("/api/quality/workflows/proposals/{pid}")
    def one(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view", "documents:view")          # the page quotes the procedures
        return {**WP.view(c, run(lambda: WP.get(c, ident(pid)))),
                "can_decide": P.allows(u["roles"], "workflows:configure")}

    @app.post("/api/quality/workflows/proposal-items/{iid}/accept")
    async def accept(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "workflows:configure")
        d = await body(request)
        it = run(lambda: WP.accept(c, ident(iid), u["email"], str(d.get("note") or "")))
        return {**WP.view(c, WP.get(c, it["proposal_id"])), "can_decide": True}

    @app.post("/api/quality/workflows/proposal-items/{iid}/reject")
    async def reject(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "workflows:configure")
        d = await body(request)
        it = run(lambda: WP.reject(c, ident(iid), u["email"], str(d.get("reason") or "")))
        return {**WP.view(c, WP.get(c, it["proposal_id"])), "can_decide": True}
