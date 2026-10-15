"""Quality system endpoints (ADR-0016, step 16a). Seeing the system's state needs quality:view; adopting a standard,
saying what does not apply and linking evidence need qms:configure; adopting and declaring are signed.
"""

from __future__ import annotations

import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
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

    def tz() -> str:
        m = company()[0]
        return m["company"]["timezone"] if m else "UTC"

    def page(c, u, standard: str, eval_id: int | None = None, day: dt.date | None = None) -> dict:
        return {**run(lambda: QMS.view(c, standard, eval_id, day)),
                "can_configure": P.allows(u["roles"], "qms:configure"),
                "can_check": P.allows(u["roles"], "quality:edit")}

    @app.get("/api/qms/{standard}")
    def show(standard: str, evaluation: int = 0, day: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        """The latest check, or one asked for by its number or by day."""
        need(u, "quality:view")
        if not 0 <= evaluation < 2**63:
            raise HTTPException(404, "not found")
        try:
            when = dt.date.fromisoformat(day) if day else None
        except ValueError as exc:
            raise HTTPException(400, "day is a date like 2026-10-14") from exc
        return page(c, u, standard, evaluation or None, when)

    @app.post("/api/qms/{standard}/enable")
    async def enable(standard: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: QMS.enable(c, u, standard, str(d.get("edition") or ""), str(d.get("password") or ""), today(),
                               tz()))
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/evaluate")
    def evaluate(standard: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        if run(lambda: QMS.evaluate(c, standard, today(), "manual", u["email"], tz=tz())) is None:
            raise HTTPException(409, "adopt the standard first")
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/controls/{control}/applies")
    async def declare(standard: str, control: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        if not isinstance(d.get("applies"), bool):
            raise HTTPException(400, "applies is true or false")
        run(lambda: QMS.declare(c, u, standard, control, d["applies"], str(d.get("reason") or ""),
                                str(d.get("password") or ""), today(), tz()))
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/settings")
    async def setting(standard: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        """Change one of the pack's settings: a number of days, or a rule of our own switched on or off."""
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: QMS.set_setting(c, u["email"], standard, str(d.get("key") or ""), d.get("value"), today(), tz()))
        return page(c, u, standard)

    @app.post("/api/qms/{standard}/controls/{control}/evidence")
    async def link(standard: str, control: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        doc = d.get("document_id")
        if type(doc) is not int or not 0 < doc < 2**63 or not isinstance(d.get("linked", True), bool):
            raise HTTPException(400, "document_id is a document number and linked is true or false")
        run(lambda: QMS.link(c, u["email"], standard, control, doc, d.get("linked", True), today(),
                             str(d.get("note") or ""), tz()))
        return page(c, u, standard)
