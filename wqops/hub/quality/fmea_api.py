"""Process FMEA endpoints, step 22c (ADR-0022). Seeing needs quality:view; starting and editing PFMEAs, opening a
CAPA from a row, starting a new version and withdrawing a draft need quality:edit; asking the AI to draft rows also
needs ai:use; the criteria (scales, rule) and approving (signed) need qms:configure.
"""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops import i18n as I18N
from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import llm as L
from wqops.hub.ont import api as OA
from wqops.hub.quality import fmea as F
from wqops.hub.quality import fmea_ai as FAI
from wqops.hub.quality import fmea_rules as FR
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company, model=None,  # noqa: PLR0915, PLR0917 - one route per action
          db_url: str | None = None) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def run(fn):
        try:
            return fn()
        except (F.FmeaError, Q.QualityError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        try:
            d = (await request.json()) if raw else {}
        except ValueError as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        return d if isinstance(d, dict) else {}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    def ai_ready() -> bool:
        return model is not None and model.configured()

    def can(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure"),
                "can_ask": P.allows(u["roles"], "ai:use") and ai_ready()}

    def criteria(c) -> dict:
        cfg = F.rule(c)
        return {"scales": F.scales(c), "rule": cfg, "lookup_gaps": FR.lookup_gaps(cfg) if cfg else None,
                "priorities": list(FR.PRIORITIES)}

    def people(c) -> list[str]:
        return [r["email"] for r in c.execute("select email from users where active order by email")]

    @app.get("/api/fmea")
    def home(status: str = "current", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"files": F.listing(c, status), **criteria(c), "criteria_history": F.criteria_history(c),
                "people": people(c), **can(u)}

    # ------------------------------------------------ criteria

    @app.post("/api/fmea/scales", status_code=201)
    async def add_scale(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        return run(lambda: F.add_scale(c, u["email"], d))

    @app.put("/api/fmea/scales/{sid}")
    async def change_scale(sid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        return run(lambda: F.update_scale(c, u["email"], ident(sid), d))

    @app.put("/api/fmea/rule")
    async def set_rule(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: F.set_rule(c, u["email"], d))
        return criteria(c)

    # ------------------------------------------------ PFMEAs

    def page(c, u, fid: int) -> dict:
        return {**run(lambda: F.view(c, fid)), **criteria(c), **can(u), "people": people(c)}

    @app.post("/api/fmea/files", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: F.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/fmea/files/{fid}")
    def show(fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(fid))

    @app.get("/api/fmea/files/{fid}/context")
    def context(fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        """The records the AI reads, and may cite, when drafting rows."""
        need(u, "quality:view")
        f = run(lambda: F.get(c, ident(fid)))
        from wqops.hub.quality import causes as C  # noqa: PLC0415

        recs = F.context(c, f, today=OA.today(company()[0]))
        return {"records": recs, "links": C.links(c, [r["ref"] for r in recs])}

    @app.put("/api/fmea/files/{fid}")
    async def change(fid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: F.update(c, u["email"], ident(fid), d))
        return page(c, u, fid)

    @app.post("/api/fmea/files/{fid}/rows", status_code=201)
    async def add_row(fid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: F.add_row(c, u["email"], ident(fid), d))
        return page(c, u, fid)

    @app.put("/api/fmea/files/{fid}/rows/{rid}")
    async def change_row(fid: int, rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        confirm = bool(d.pop("confirm", False))
        run(lambda: F.update_row(c, u["email"], ident(fid), ident(rid), d, confirm=confirm))
        return page(c, u, fid)

    @app.delete("/api/fmea/files/{fid}/rows/{rid}")
    def remove_row(fid: int, rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        run(lambda: F.remove_row(c, u["email"], ident(fid), ident(rid)))
        return page(c, u, fid)

    @app.post("/api/fmea/files/{fid}/rows/{seq}/capa", status_code=201)
    async def capa(fid: int, seq: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: F.open_capa(c, u["email"], ident(fid), ident(seq), str(d.get("kind") or "preventive")))
        return {"id": row["id"], "name": row["name"]}

    @app.post("/api/fmea/files/{fid}/suggest")
    async def suggest(fid: int, u=Depends(user_dep)):
        """The AI drafts rows citing records, without ranks; a person confirms or removes each."""
        for perm in ("quality:edit", "ai:use"):
            need(u, perm)
        if not ai_ready():
            raise HTTPException(409, say("there is no model key; write the rows yourself"))

        def work():
            with DB.connect(db_url) as c:
                try:
                    out = run(lambda: FAI.suggest(c, {"email": u["email"], "roles": u["roles"]}, ident(fid), model,
                                                  today=OA.today(company()[0])))
                except L.LlmError as exc:
                    raise HTTPException(502, say("the model could not draft rows: {exc}", exc=exc)) from exc
                return {"suggested": {k: out[k] for k in ("run", "dropped", "unusable", "note", "shown")}
                        | {"kept": len(out["rows"])}} | page(c, u, fid)

        return await asyncio.to_thread(work)

    @app.post("/api/fmea/files/{fid}/{action}")
    async def act(fid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(fid)
        if action == "approve":
            need(u, "qms:configure")
            run(lambda: F.approve(c, u, fid, str(d.get("password") or "")))
        elif action == "withdraw":
            need(u, "quality:edit")
            run(lambda: F.withdraw(c, u["email"], fid, str(d.get("reason") or "")))
        elif action == "revise":
            need(u, "quality:edit")
            row = run(lambda: F.revise(c, u["email"], fid))
            return page(c, u, row["id"])
        else:
            raise HTTPException(404, say("not found"))
        return page(c, u, fid)
