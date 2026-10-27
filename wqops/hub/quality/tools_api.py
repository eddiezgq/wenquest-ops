"""Quality tools, step 22a (ADR-0022): Pareto, histogram, scatter and check sheets. Reading charts is quality:view;
making check sheet forms and recording tallies is quality:edit, and a tally is signed with the counter's password."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import measurements as ME
from wqops.hub.quality import records as Q
from wqops.hub.quality import tools as TL
from wqops.hub.quality import tools_rules as TR
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.PERMISSIONS[perm]))

    def run(fn):
        try:
            return fn()
        except (TL.ToolsError, TR.ToolError, ME.MeasurementError, Q.QualityError) as exc:
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

    def ident(v: int | None) -> int | None:
        if v is not None and not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    @app.get("/api/quality/tools/options")
    def options(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return TL.options(c) | {"parameters": ME.parameters(c)}

    @app.get("/api/quality/tools/pareto")
    def pareto(source: str, by: str, since: str | None = None, until: str | None = None,  # noqa: PLR0917
               form_id: int | None = None, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return run(lambda: TL.pareto_for(c, source, by, since=since, until=until, form_id=ident(form_id)))

    @app.get("/api/quality/tools/histogram")
    def histogram(source: str, item_code: str, parameter: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return run(lambda: TL.histogram_for(c, source, item_code, parameter))

    @app.get("/api/quality/tools/scatter")
    def scatter(source: str, item_code: str, x: str, y: str, u=Depends(user_dep), c=Depends(conn_dep)):  # noqa: PLR0917
        need(u, "quality:view")
        return run(lambda: TL.scatter_for(c, source, item_code, x, y))

    @app.get("/api/quality/check-sheets")
    def sheets(form_id: int | None = None, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"forms": TL.forms(c), "sheets": TL.sheets(c, ident(form_id))}

    @app.post("/api/quality/check-sheets/forms", status_code=201)
    async def new_form(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        return run(lambda: TL.new_form(c, u["email"], b.get("name"), b.get("categories")))

    @app.post("/api/quality/check-sheets/forms/{fid}/active")
    async def set_active(fid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        return run(lambda: TL.retire_form(c, u["email"], ident(fid), bool(b.get("active"))))

    @app.post("/api/quality/check-sheets", status_code=201)
    async def record(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        b = await body(request)
        fid = b.get("form_id")
        if not isinstance(fid, int) or isinstance(fid, bool):
            raise HTTPException(400, say("choose the check sheet form"))
        return run(lambda: TL.record(c, u, ident(fid), b, str(b.get("password") or ""),
                                     today=OA.today(company()[0])))
