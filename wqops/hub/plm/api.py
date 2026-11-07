"""PLM endpoints, steps 26a and 26b (ADR-0026). Only when the company manifest turns the module ``plm`` on.
Seeing needs plm:view; creating and editing parts and draft BOMs needs plm:edit; releasing (signed) and the numbering
rules need plm:release.
"""

from __future__ import annotations

from urllib.parse import quote

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile

from wqops import i18n as I18N
from wqops.erp import ErpError
from wqops.hub import permissions as P
from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import catalog as CAT
from wqops.hub.plm import parts as PT
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company, erp_client) -> None:  # noqa: PLR0915 - routes inside
    def on() -> None:
        if "plm" not in (((company() or (None,))[0] or {}).get("modules") or []):
            raise HTTPException(404, say("the PLM module is not turned on for this company"))

    def need(u: dict, perm: str) -> None:
        on()
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def run(fn):
        try:
            return fn()
        except PT.Similar:
            raise
        except (PT.PlmError, Q.QualityError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except psycopg.errors.RaiseException as exc:      # the database kept a released record from changing
            raise HTTPException(409, say("someone released it meanwhile: open it again")) from exc
        except ErpError as exc:
            raise HTTPException(502, say("ERPNext did not answer as expected: {exc}", exc=exc)) from exc

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

    def flags(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "plm:edit"), "can_release": P.allows(u["roles"], "plm:release")}

    def erp_or_none():
        try:
            return erp_client()
        except Exception:
            return None

    @app.get("/api/plm/catalog")
    def catalog(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {"categories": CAT.shown(), "numbering": PT.numbering(c), "sources": list(PT.SOURCES),
                "file_kinds": list(PT.FILE_KINDS), **flags(u)}

    @app.put("/api/plm/numbering/{category}")
    async def set_numbering(category: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:release")
        d = await body(request)
        run(lambda: PT.set_numbering(c, u["email"], category, d.get("prefix"), d.get("digits", 5)))
        return {"numbering": PT.numbering(c)}

    @app.get("/api/plm/parts")
    def parts(q: str = "", category: str = "", status: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        rows = PT.listing(c, q=q[:100], category=category[:40], status=status[:20])
        return {"parts": rows[:PT.LIST_MAX], "more": len(rows) > PT.LIST_MAX, **flags(u)}

    @app.post("/api/plm/parts/similar")
    async def similar(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        d = await body(request)

        def go():
            from wqops.hub.plm import rules as R  # noqa: PLC0415

            cat = str(d.get("category") or "")
            CAT.get(cat)
            return {"similar": PT.check_similar(c, cat, R.clean_params(cat, d.get("params")))}
        return run(go)

    @app.post("/api/plm/parts", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        try:
            p = run(lambda: PT.create(c, u, d, erp_client()))
        except PT.Similar as exc:      # the similar parts go back with the message; the person confirms or reuses
            return JSONResponse({"detail": str(exc), "similar": exc.parts}, status_code=409)
        return {"id": p["id"], "code": p["item_code"], "erp_state": p["erp_state"]}

    @app.get("/api/plm/parts/{pid}")
    def show(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: PT.view(c, ident(pid))), **flags(u)}

    @app.put("/api/plm/parts/{pid}")
    async def update(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: PT.update(c, u, ident(pid), d, erp_or_none())), **flags(u)}

    @app.post("/api/plm/parts/{pid}/files")
    async def add_file(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(400, say("choose a file"))
        raw = await up.read(F.MAX_BYTES + 1)
        return {**run(lambda: PT.add_file(c, u, ident(pid), str(form.get("kind") or "other"), up.filename or "file",
                                          raw)), **flags(u)}

    @app.post("/api/plm/parts/{pid}/files/{fid}/remove")
    def remove_file(pid: int, fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        return {**run(lambda: PT.remove_file(c, u, ident(pid), ident(fid))), **flags(u)}

    @app.get("/api/plm/parts/{pid}/files/{fid}")
    def get_file(pid: int, fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        row, data = run(lambda: PT.file_of(c, ident(pid), ident(fid)))
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['name'])}"})

    @app.post("/api/plm/parts/{pid}/bom", status_code=201)
    async def start_bom(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: B.start(c, u, ident(pid), d.get("change_id"))), **flags(u)}

    @app.post("/api/plm/parts/{pid}/{action}")
    async def act(pid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(pid)
        steps = {"release": ("plm:release", lambda: PT.release(c, u, pid, str(d.get("password") or ""))),
                 "new-revision": ("plm:edit", lambda: PT.new_revision(c, u, pid, d.get("change_id"))),
                 "retry-erp": ("plm:edit", lambda: PT.view(c, PT.retry_erp(c, u, pid, erp_client())["id"]))}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        need(u, steps[action][0])
        return {**run(steps[action][1]), **flags(u)}

    @app.get("/api/plm/boms/compare")
    def compare(a: int, b: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return run(lambda: B.compare(c, ident(a), ident(b)))

    @app.get("/api/plm/boms/{bid}")
    def bom(bid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: B.view(c, ident(bid), erp_or_none())), **flags(u)}

    @app.put("/api/plm/boms/{bid}")
    async def bom_lines(bid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: B.set_lines(c, u, ident(bid), d.get("lines"), note=d.get("note"), erp=erp_or_none())),
                **flags(u)}

    @app.post("/api/plm/boms/{bid}/{action}")
    async def bom_act(bid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(bid)
        steps = {"release": ("plm:release", lambda: B.release(c, u, bid, str(d.get("password") or ""), erp_client())),
                 "to-erp": ("plm:edit", lambda: B.to_erp(c, u, bid, erp_client()))}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        need(u, steps[action][0])
        return {**run(steps[action][1]), **flags(u)}

    @app.get("/api/plm/changes")
    def changes(u=Depends(user_dep), c=Depends(conn_dep)):
        """Approved product changes a new revision can rest on (17g)."""
        need(u, "plm:view")
        rows = c.execute("select id, name, title from changes where kind = 'product' and status = 'approved' "
                         "order by id desc limit 200").fetchall()
        return {"changes": [dict(r) for r in rows]}
