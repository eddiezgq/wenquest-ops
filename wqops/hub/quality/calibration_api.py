"""Measuring equipment endpoints, step 17f (ADR-0017). Seeing needs quality:view; registering and changing equipment
and recording calibrations need quality:edit; approving calibrations (signed), assessing out-of-tolerance results
(signed) and retiring equipment need qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import records as Q


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (CAL.CalError, Q.QualityError) as exc:
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

    def can(u) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"), "can_configure": P.allows(u["roles"],
                                                                                            "qms:configure")}

    def page(c, u, gid: int) -> dict:
        return {**run(lambda: CAL.view(c, gid, today())), **can(u)}

    @app.get("/api/gauges")
    def listing(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"gauges": CAL.listing(c, today()), **can(u),
                "people": [r["email"] for r in c.execute("select email from users where active order by email")]}

    @app.post("/api/gauges", status_code=201)
    async def add(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        g = run(lambda: CAL.add(c, u["email"], str(d.pop("code", "") or ""), d))
        return {"id": g["id"]}

    @app.get("/api/gauges/{gid}")
    def show(gid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(gid))

    @app.put("/api/gauges/{gid}")
    async def change(gid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: CAL.change(c, u["email"], ident(gid), d))
        return page(c, u, gid)

    @app.post("/api/gauges/{gid}/retire")
    async def retire(gid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: CAL.retire(c, u["email"], ident(gid), str(d.get("reason") or "")))
        return page(c, u, gid)

    @app.post("/api/gauges/{gid}/calibrations", status_code=201)
    async def record(gid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: CAL.record(c, u["email"], ident(gid), d, today=today()))
        return page(c, u, gid)

    @app.put("/api/gauge-calibrations/{cid}")
    async def change_cal(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: CAL.change_calibration(c, u, ident(cid), d, today=today()))
        return page(c, u, row["gauge_id"])

    @app.post("/api/gauge-calibrations/{cid}/approve")
    async def approve(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        g = run(lambda: CAL.approve(c, u, ident(cid), str(d.get("password") or ""), today=today()))
        return page(c, u, g["id"])

    @app.post("/api/gauge-impacts/{iid}/assess")
    async def assess(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        g = run(lambda: CAL.assess(c, u, ident(iid), str(d.get("password") or ""), str(d.get("conclusion") or ""),
                                   open_ncr=d.get("open_ncr") is True))
        return page(c, u, g["id"])
