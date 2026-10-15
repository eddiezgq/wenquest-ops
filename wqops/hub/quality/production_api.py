"""Production record endpoints, step 17i (ADR-0017). Seeing needs quality:view; drafting templates, starting lots,
recording steps (signed), materials, quantities, opening a nonconformance report for a failed step and submitting
need quality:edit; activating and retiring templates, sending back, releasing and rejecting (signed) and cancelling
a lot need qms:configure.
"""

from __future__ import annotations

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import iqc as I
from wqops.hub.quality import production as PRD
from wqops.hub.quality import records as Q


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (PRD.ProdError, Q.QualityError, CAL.CalError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except psycopg.errors.UniqueViolation as exc:
            raise HTTPException(409, "someone else did the same just now: open it again") from exc
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

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def can(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/production")
    def home(status: str = "open", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"records": PRD.listing(c, status), "templates": PRD.templates(c), "items": I.items(c),
                "documents": [r["number"] for r in c.execute("select distinct number from documents where status = "
                                                             "'effective' and number is not null order by number")],
                **can(u)}

    # ------------------------------------------------ templates

    def tpage(c, u, tid: int) -> dict:
        return {**run(lambda: PRD.template_view(c, tid)), **can(u), "items": I.items(c),
                "documents_in_effect": [r["number"] for r in c.execute(
                    "select distinct number from documents where status = 'effective' and number is not null "
                    "order by number")]}

    @app.post("/api/production/templates", status_code=201)
    async def new_template(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: PRD.create_template(c, u["email"], d))
        return {"id": row["id"]}

    @app.get("/api/production/templates/{tid}")
    def show_template(tid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return tpage(c, u, ident(tid))

    @app.put("/api/production/templates/{tid}")
    async def change_template(tid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.update_template(c, u["email"], ident(tid), d))
        return tpage(c, u, tid)

    @app.post("/api/production/templates/{tid}/steps", status_code=201)
    async def add_step(tid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.add_step(c, u["email"], ident(tid), d))
        return tpage(c, u, tid)

    @app.put("/api/production/templates/{tid}/steps/{sid}")
    async def change_step(tid: int, sid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.update_step(c, u["email"], ident(tid), ident(sid), d))
        return tpage(c, u, tid)

    @app.delete("/api/production/templates/{tid}/steps/{sid}")
    def remove_step(tid: int, sid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        run(lambda: PRD.remove_step(c, u["email"], ident(tid), ident(sid)))
        return tpage(c, u, tid)

    @app.post("/api/production/templates/{tid}/{action}")
    async def template_action(tid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(tid)
        if action == "activate":
            need(u, "qms:configure")
            run(lambda: PRD.activate(c, u, tid, str(d.get("password") or "")))
        elif action == "end":
            t = run(lambda: PRD.template(c, tid))
            need(u, "qms:configure" if t["status"] == "active" else "quality:edit")
            run(lambda: PRD.end_template(c, u["email"], tid, str(d.get("reason") or "")))
        elif action == "new-version":
            need(u, "quality:edit")
            row = run(lambda: PRD.new_version(c, u["email"], tid))
            return tpage(c, u, row["id"])
        else:
            raise HTTPException(404, "not found")
        return tpage(c, u, tid)

    # ------------------------------------------------ production records

    def page(c, u, rid: int) -> dict:
        v = run(lambda: PRD.view(c, rid))
        return {**v, **can(u), "lots": [x for x in PRD.lots_released(c) if x["left_qty"] > 0],
                "gauges": CAL.usable_gauges(c, today())}

    @app.post("/api/production/records", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: PRD.start(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/production/records/{rid}")
    def show(rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(rid))

    @app.put("/api/production/records/{rid}")
    async def quantities(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.set_quantities(c, u["email"], ident(rid), d))
        return page(c, u, rid)

    @app.post("/api/production/records/{rid}/steps/{seq}")
    async def record_step(rid: int, seq: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.record_step(c, u, ident(rid), seq, str(d.get("password") or ""), d, today=today()))
        return page(c, u, rid)

    @app.post("/api/production/records/{rid}/steps/{seq}/ncr")
    def step_ncr(rid: int, seq: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        run(lambda: PRD.step_ncr(c, u["email"], ident(rid), seq))
        return page(c, u, rid)

    @app.post("/api/production/records/{rid}/materials", status_code=201)
    async def material(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: PRD.add_material(c, u["email"], ident(rid), d.get("inspection_id"), d.get("qty")))
        return page(c, u, rid)

    @app.post("/api/production/records/{rid}/{action}")
    async def act(rid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(rid)
        pw, why = str(d.get("password") or ""), str(d.get("reason") or "")
        steps = {"submit": ("quality:edit", lambda: PRD.submit(c, u["email"], rid)),
                 "cancel": ("qms:configure", lambda: PRD.cancel(c, u["email"], rid, why)),
                 "send-back": ("qms:configure", lambda: PRD.send_back(c, u["email"], rid, why)),
                 "release": ("qms:configure", lambda: PRD.decide(c, u, rid, pw, True, why)),
                 "reject": ("qms:configure", lambda: PRD.decide(c, u, rid, pw, False, why))}
        if action not in steps:
            raise HTTPException(404, "not found")
        need(u, steps[action][0])
        run(steps[action][1])
        return page(c, u, rid)
