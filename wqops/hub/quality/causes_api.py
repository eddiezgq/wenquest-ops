"""Cause analysis endpoints, step 22b (ADR-0022). Reading is quality:view; starting, adding and deciding causes is
quality:edit; asking the model also needs ai:use; the conclusion is signed with the person's password."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import llm as L
from wqops.hub.ont import api as OA
from wqops.hub.quality import causes as C
from wqops.hub.quality import causes_ai as CAI
from wqops.hub.quality import causes_rules as CR
from wqops.hub.quality import complaints as CP
from wqops.hub.quality import records as Q


def mount(app: FastAPI, conn_dep, user_dep, company, model=None,  # noqa: PLR0915, PLR0917 - one route per action
          db_url: str | None = None) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (CR.CauseError, Q.QualityError, CP.ComplaintError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        try:
            d = (await request.json()) if raw else {}
        except ValueError as exc:
            raise HTTPException(400, "the request is not JSON") from exc
        return d if isinstance(d, dict) else {}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def ai_ready() -> bool:
        return model is not None and model.configured()

    def page(c, u, aid: int) -> dict:
        return run(lambda: C.view(c, ident(aid))) | {"can_edit": P.allows(u["roles"], "quality:edit"),
                                                     "can_ask": P.allows(u["roles"], "ai:use") and ai_ready()}

    @app.get("/api/quality/causes")
    def listing(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"analyses": C.listing(c), "methods": CR.METHODS, "bones": list(CR.BONES)}

    @app.get("/api/quality/causes/for/{kind}/{ref_id}")
    def for_record(kind: str, ref_id: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        if kind not in C.KINDS:
            raise HTTPException(404, "not found")
        s = run(lambda: C.subject(c, kind, ident(ref_id)))
        return {"analyses": C.for_record(c, kind, ref_id), "methods": CR.METHODS, "bones": list(CR.BONES),
                "can_start": P.allows(u["roles"], "quality:edit") and s["status"] in C.OPEN[kind] and not s["locked"]}

    @app.post("/api/quality/causes", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        rid = b.get("ref_id")
        if not isinstance(rid, int) or isinstance(rid, bool):
            raise HTTPException(400, "which record is analysed")
        return run(lambda: C.start(c, u["email"], str(b.get("kind")), ident(rid), str(b.get("method")),
                                   problem=b.get("problem"), categories=b.get("categories")))

    @app.get("/api/quality/causes/{aid}")
    def show(aid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, aid)

    @app.get("/api/quality/causes/{aid}/context")
    def context(aid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        """The records the model reads, and may cite, for this analysis."""
        need(u, "quality:view")
        a = run(lambda: C.get(c, ident(aid)))
        s = run(lambda: C.subject(c, a["ref_kind"], a["ref_id"]))
        recs = C.context(c, s, today=OA.today(company()[0]))
        return {"records": recs, "links": C.links(c, [r["ref"] for r in recs])}

    @app.post("/api/quality/causes/{aid}/items", status_code=201)
    async def add(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        run(lambda: C.add(c, u["email"], ident(aid), b))
        return page(c, u, aid)

    @app.post("/api/quality/causes/{aid}/items/{iid}")
    async def decide(aid: int, iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        run(lambda: C.decide(c, u["email"], ident(aid), ident(iid), str(b.get("action")), new_text=b.get("text")))
        return page(c, u, aid)

    @app.post("/api/quality/causes/{aid}/suggest")
    async def suggest(aid: int, u=Depends(user_dep)):
        """The model suggests causes citing records; a person decides each one."""
        for perm in ("quality:edit", "ai:use"):
            need(u, perm)
        if not ai_ready():
            raise HTTPException(409, "there is no model key; add the causes yourself")

        def work():
            with DB.connect(db_url) as c:
                try:
                    out = run(lambda: CAI.suggest(c, {"email": u["email"], "roles": u["roles"]}, ident(aid), model,
                                                  today=OA.today(company()[0])))
                except L.LlmError as exc:
                    raise HTTPException(502, f"the model could not suggest causes: {exc}") from exc
                return {"suggested": {k: out[k] for k in ("run", "dropped", "unusable", "note", "shown")}
                        | {"kept": len(out["items"])}} | page(c, u, aid)

        return await asyncio.to_thread(work)

    @app.post("/api/quality/causes/{aid}/conclude")
    async def conclude(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        run(lambda: C.conclude(c, u, ident(aid), str(b.get("conclusion") or ""), str(b.get("password") or ""),
                               today=OA.today(company()[0])))
        return page(c, u, aid)

    @app.post("/api/quality/causes/{aid}/addenda", status_code=201)
    async def addendum(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        run(lambda: C.addendum(c, u["email"], ident(aid), str(b.get("text") or "")))
        return page(c, u, aid)

    @app.post("/api/quality/causes/{aid}/cancel")
    async def cancel(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        run(lambda: C.cancel(c, u["email"], ident(aid), str(b.get("reason") or "")))
        return page(c, u, aid)
