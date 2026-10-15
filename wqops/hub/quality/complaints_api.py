"""Complaint endpoints, step 17e (ADR-0017). Seeing needs quality:view; recording, changing, starting the
investigation, cancelling and opening an NCR or CAPA need quality:edit; approving no investigation, assessing
(signed), closing (signed) and the reporting deadlines need qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import complaints as C
from wqops.hub.quality import records as Q


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (C.ComplaintError, Q.QualityError) as exc:
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
        return {**run(lambda: C.view(c, cid, today())), "can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/complaints")
    def listing(status: str = "open", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"complaints": C.listing(c, status, today()), "deadlines": C.deadlines(c),
                "people": [r["email"] for r in c.execute("select email from users where active order by email")],
                "can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.post("/api/complaints", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: C.create(c, u["email"], d, today=today()))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/complaints/{cid}")
    def show(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(cid))

    @app.put("/api/complaints/{cid}")
    async def update(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: C.update(c, u, ident(cid), d, today=today()))
        return page(c, u, cid)

    @app.post("/api/complaints/{cid}/{action}")
    async def act(cid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(cid)
        if action in ("start", "cancel", "ncr", "capa"):
            need(u, "quality:edit")
            fn = {"start": lambda: C.start(c, u["email"], cid),
                  "cancel": lambda: C.cancel(c, u["email"], cid, str(d.get("reason") or "")),
                  "ncr": lambda: C.open_ncr(c, u["email"], cid),
                  "capa": lambda: C.open_capa(c, u["email"], cid)}[action]
        elif action in ("no-investigation", "assess", "close"):
            need(u, "qms:configure")
            dl = d.get("deadline_id")
            if dl is not None and (type(dl) is not int or not 0 < dl < 2**63):
                raise HTTPException(400, "deadline_id is a deadline number")
            fn = {"no-investigation": lambda: C.no_investigation(c, u["email"], cid, str(d.get("reason") or "")),
                  "assess": lambda: C.assess(c, u, cid, str(d.get("password") or ""),
                                             answers=d.get("answers") if isinstance(d.get("answers"), dict) else {},
                                             reportable=d.get("reportable"), reason=str(d.get("reason") or ""),
                                             deadline_id=dl),
                  "close": lambda: C.close(c, u, cid, str(d.get("password") or ""))}[action]
        else:
            raise HTTPException(404, "not found")
        run(fn)
        return page(c, u, cid)

    @app.post("/api/complaint-deadlines")
    async def deadline(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        did = d.get("id")
        if did is not None and (type(did) is not int or not 0 < did < 2**63):
            raise HTTPException(400, "id is a deadline number")
        return run(lambda: C.save_deadline(c, u["email"], did, str(d.get("label") or ""), d.get("days"),
                                           active=d.get("active", True)))
