"""Quality system endpoints (ADR-0016, step 16a). Seeing the system's state needs quality:view; adopting a standard,
saying what does not apply and linking evidence need qms:configure; adopting and declaring are signed.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (QMS.QmsError, Q.QualityError) as exc:
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

    def page(c, u, standard: str, eval_id: int | None = None) -> dict:
        return {**run(lambda: QMS.view(c, standard, eval_id)), "can_configure": P.allows(u["roles"], "qms:configure")}

    @app.get("/api/qms/{standard}")
    def show(standard: str, evaluation: int = 0, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        if not 0 <= evaluation < 2**63:
            raise HTTPException(404, "not found")
        return page(c, u, standard, evaluation or None)

    @app.post("/api/qms/{standard}/enable")
    async def enable(standard: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: QMS.enable(c, u, standard, str(d.get("edition") or ""), str(d.get("password") or ""), today()))
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/evaluate")
    def evaluate(standard: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        if run(lambda: QMS.evaluate(c, standard, today(), "manual", u["email"])) is None:
            raise HTTPException(409, "adopt the standard first")
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/controls/{control}/applies")
    async def declare(standard: str, control: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        if not isinstance(d.get("applies"), bool):
            raise HTTPException(400, "applies is true or false")
        run(lambda: QMS.declare(c, u, standard, control, d["applies"], str(d.get("reason") or ""),
                                str(d.get("password") or ""), today()))
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/controls/{control}/evidence")
    async def link(standard: str, control: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        doc = d.get("document_id")
        if type(doc) is not int or not 0 < doc < 2**63 or not isinstance(d.get("linked", True), bool):
            raise HTTPException(400, "document_id is a document number and linked is true or false")
        run(lambda: QMS.link(c, u["email"], standard, control, doc, d.get("linked", True), today(),
                             str(d.get("note") or "")))
        return page(c, u, standard)
