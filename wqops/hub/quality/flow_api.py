"""Process flow chart endpoints, step 22d (ADR-0022). Seeing needs quality:view; starting and editing flow charts,
starting a new version and withdrawing a draft need quality:edit; approving (signed) needs qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import flow as FW
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.PERMISSIONS[perm]))

    def run(fn):
        try:
            return fn()
        except (FW.FlowError, Q.QualityError) as exc:
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

    def today():
        return OA.today(company()[0])

    def people(c) -> list[str]:
        return [r["email"] for r in c.execute("select email from users where active order by email")]

    def page(c, u, cid: int) -> dict:
        return {**run(lambda: FW.view(c, cid, today=today())), "people": people(c),
                "can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/flow")
    def home(status: str = "current", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"charts": FW.listing(c, status), "people": people(c),
                "can_edit": P.allows(u["roles"], "quality:edit")}

    @app.get("/api/flow/options")
    def options(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return FW.options(c)

    @app.post("/api/flow/charts", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: FW.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/flow/charts/{cid}")
    def show(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(cid))

    @app.put("/api/flow/charts/{cid}")
    async def change(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: FW.update(c, u["email"], ident(cid), d))
        return page(c, u, cid)

    @app.post("/api/flow/charts/{cid}/steps", status_code=201)
    async def add_step(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: FW.add_step(c, u["email"], ident(cid), d))
        return page(c, u, cid)

    @app.put("/api/flow/charts/{cid}/steps/{sid}")
    async def change_step(cid: int, sid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: FW.update_step(c, u["email"], ident(cid), ident(sid), d))
        return page(c, u, cid)

    @app.post("/api/flow/charts/{cid}/steps/{sid}/move")
    async def move_step(cid: int, sid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: FW.move_step(c, u["email"], ident(cid), ident(sid), str(d.get("direction") or "")))
        return page(c, u, cid)

    @app.delete("/api/flow/charts/{cid}/steps/{sid}")
    def remove_step(cid: int, sid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        run(lambda: FW.remove_step(c, u["email"], ident(cid), ident(sid)))
        return page(c, u, cid)

    @app.post("/api/flow/charts/{cid}/{action}")
    async def act(cid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(cid)
        if action == "approve":
            need(u, "qms:configure")
            run(lambda: FW.approve(c, u, cid, str(d.get("password") or ""), today=today()))
        elif action == "withdraw":
            need(u, "quality:edit")
            run(lambda: FW.withdraw(c, u["email"], cid, str(d.get("reason") or "")))
        elif action == "revise":
            need(u, "quality:edit")
            row = run(lambda: FW.revise(c, u["email"], cid))
            return page(c, u, row["id"])
        else:
            raise HTTPException(404, say("not found"))
        return page(c, u, cid)
