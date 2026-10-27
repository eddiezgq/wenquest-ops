"""Traceability and recall endpoints, step 17i (ADR-0017). Tracing and seeing recalls need quality:view; drafting,
changing and recording contact with consignees need quality:edit; opening needs the recall's owner or
qms:configure; closing (signed) and cancelling need qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import recall as RC
from wqops.hub.quality import records as Q
from wqops.hub.quality import trace as TRC
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.PERMISSIONS[perm]))

    def run(fn):
        try:
            return fn()
        except (RC.RecallError, Q.QualityError) as exc:
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

    def can(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/trace")
    def trace(record: int = 0, incoming: int = 0, complaint: int = 0, u=Depends(user_dep), c=Depends(conn_dep)):
        """Trace from one starting point: a production record, an incoming inspection, or a complaint."""
        need(u, "quality:view")
        if record:
            return run(lambda: TRC.from_record(c, ident(record)))
        if incoming:
            return run(lambda: TRC.from_incoming(c, ident(incoming)))
        if complaint:
            return run(lambda: TRC.from_complaint(c, ident(complaint)))
        return {"records": [{"id": r["id"], "name": r["name"], "item_code": r["item_code"], "lot_no": r["lot_no"]}
                            for r in c.execute("select id, name, item_code, lot_no from prod_records where status <> "
                                               "'cancelled' order by id desc limit 500")],
                "incoming": [dict(r) for r in c.execute("select id, name, item_code, lot_no, supplier from "
                                                        "iqc_inspections where status <> 'void' order by id desc "
                                                        "limit 500")],
                "complaints": [dict(r) for r in c.execute("select id, name, item_code, lot_no, customer from "
                                                          "complaints where status <> 'cancelled' order by id desc "
                                                          "limit 500")]}

    # ------------------------------------------------ recalls

    def page(c, u, rid: int) -> dict:
        return {**run(lambda: RC.view(c, rid)), **can(u), "me": u["email"],
                "people": [r["email"] for r in c.execute("select email from users where active order by email")]}

    @app.get("/api/recalls")
    def listing(status: str = "open", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"recalls": RC.listing(c, status), **can(u)}

    @app.post("/api/recalls", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: RC.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/recalls/{rid}")
    def show(rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(rid))

    @app.get("/api/recalls/{rid}/consignees.csv")
    def export(rid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        text = run(lambda: RC.csv_text(c, ident(rid)))
        name = RC.get(c, rid)["name"]
        return Response(text, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}-consignees.csv"'})

    @app.put("/api/recalls/{rid}")
    async def change(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: RC.update(c, u, ident(rid), d))
        return page(c, u, rid)

    @app.put("/api/recall-consignees/{cid}")
    async def contact(cid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: RC.record_contact(c, u["email"], ident(cid), d, today=OA.today(company()[0])))
        return page(c, u, row["recall_id"])

    @app.post("/api/recalls/{rid}/{action}")
    async def act(rid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(rid)
        if action == "open":
            need(u, "quality:edit")
            run(lambda: RC.open_recall(c, u, rid, today=OA.today(company()[0])))
        elif action == "close":
            need(u, "qms:configure")
            run(lambda: RC.close(c, u, rid, str(d.get("password") or ""), today=OA.today(company()[0])))
        elif action == "cancel":
            need(u, "qms:configure")
            run(lambda: RC.cancel(c, u["email"], rid, str(d.get("reason") or "")))
        else:
            raise HTTPException(404, say("not found"))
        return page(c, u, rid)
