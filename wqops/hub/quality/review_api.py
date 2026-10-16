"""Management review endpoints, step 17j (ADR-0017). Seeing needs quality:view; drafting, collecting the inputs,
writing the meeting and deciding actions need qms:configure; the chair signs (with a password); an action's owner or
Quality marks it done.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.hub.quality import review as MR


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (MR.ReviewError, Q.QualityError) as exc:
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

    def today():
        return OA.today(company()[0])

    def tz() -> str:
        return ((company()[0] or {}).get("company") or {}).get("timezone") or "UTC"

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def page(c, u, rid: int) -> dict:
        return {**run(lambda: MR.view(c, rid, u, today())), "can_configure": P.allows(u["roles"], "qms:configure"),
                "me": u["email"],
                "people": [r["email"] for r in c.execute("select email from users where active order by email")]}

    @app.get("/api/reviews")
    def listing(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"reviews": MR.listing(c), "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.post("/api/reviews", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        row = run(lambda: MR.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/reviews/{rid}")
    def show(rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(rid))

    @app.put("/api/reviews/{rid}")
    async def change(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: MR.update(c, u["email"], ident(rid), d))
        return page(c, u, rid)

    @app.post("/api/reviews/{rid}/actions", status_code=201)
    async def add_action(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: MR.add_action(c, u["email"], ident(rid), d, today=today()))
        return page(c, u, rid)

    @app.post("/api/review-actions/{aid}/done")
    async def done(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        # the owner may lack quality:view: MR.action_done checks owner or qms:configure
        d = await body(request)
        row = run(lambda: MR.action_done(c, u, ident(aid), str(d.get("evidence") or "")))
        if not P.allows(u["roles"], "quality:view"):
            return {"id": row["id"], "status": row["status"]}
        return page(c, u, row["review_id"])

    @app.post("/api/reviews/{rid}/{action}")
    async def act(rid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(rid)
        if action == "collect":
            need(u, "qms:configure")
            run(lambda: MR.collect(c, u["email"], rid, today=today(), tz=tz()))
        elif action == "sign":
            need(u, "quality:view")       # the chair signs, whatever else their role allows
            run(lambda: MR.sign(c, u, rid, str(d.get("password") or ""), today=today()))
        elif action == "cancel":
            need(u, "qms:configure")
            run(lambda: MR.cancel(c, u["email"], rid, str(d.get("reason") or "")))
        else:
            raise HTTPException(404, "not found")
        return page(c, u, rid)
