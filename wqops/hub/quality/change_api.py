"""Change control endpoints, step 17g (ADR-0017). Seeing needs quality:view; raising, changing, submitting,
implementing and cancelling need quality:edit; sending back, approving (signed) and closing (signed) need
qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import change_control as CC
from wqops.hub.quality import records as Q


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (CC.ChangeError, Q.QualityError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        d = (await request.json()) if raw else {}
        return d if isinstance(d, dict) else {}

    def today():
        return OA.today(company()[0])

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def page(c, u, cid: int) -> dict:
        return {**run(lambda: CC.view(c, cid, today())), "can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/changes")
    def listing(status: str = "open", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        docs = c.execute("select id, number, title, revision, status, supersedes from documents where status in "
                         "('effective', 'draft', 'in_review', 'approved') and number is not null order by number, "
                         "id").fetchall()
        return {"changes": CC.listing(c, status, today()), "kinds": list(CC.CR.KINDS),
                "people": [r["email"] for r in c.execute("select email from users where active order by email")],
                "documents": [dict(d) for d in docs], "can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.post("/api/changes", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: CC.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/changes/{cid}")
    def show(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(cid))

    @app.put("/api/changes/{cid}")
    async def update(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: CC.update(c, u["email"], ident(cid), d))
        return page(c, u, cid)

    @app.post("/api/changes/{cid}/{action}")
    async def act(cid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(cid)
        pw, why = str(d.get("password") or ""), str(d.get("reason") or "")
        steps = {"submit": ("quality:edit", lambda: CC.submit(c, u["email"], cid)),
                 "implement": ("quality:edit", lambda: CC.implement(c, u, cid)),
                 "cancel": ("quality:edit", lambda: CC.cancel(c, u["email"], cid, why)),
                 "send-back": ("qms:configure", lambda: CC.send_back(c, u["email"], cid, why)),
                 "approve": ("qms:configure", lambda: CC.approve(c, u, cid, pw)),
                 "close": ("qms:configure", lambda: CC.close(c, u, cid, pw))}
        if action not in steps:
            raise HTTPException(404, "not found")
        need(u, steps[action][0])
        run(steps[action][1])
        return page(c, u, cid)
