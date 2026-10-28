"""Approved supplier list endpoints, step 17c (ADR-0017). Seeing the list needs quality:view; entering, changing,
approving, re-evaluating, suspending, disqualifying and bringing in the register need qms:configure. Approving and
re-evaluating are signed with the person's password.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops import i18n as I18N
from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import asl as A
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def run(fn):
        try:
            return fn()
        except (A.AslError, I.IqcError, Q.QualityError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        d = (await request.json()) if raw else {}
        return d if isinstance(d, dict) else {}

    def today():
        return OA.today(company()[0])

    def page(c, u) -> dict:
        reg = c.execute("select count(*) as n from qms_register_entries where register = 'suppliers' and "
                        "status <> 'void'").fetchone()["n"]
        return {"entries": A.listing(c, today()), "suppliers": I.suppliers(c), "items": I.items(c),
                "settings": {k: v for k, v in I.settings(c).items() if k.startswith("asl_")},
                "setting_labels": {k: I18N.label(v[1]) for k, v in I.SETTINGS.items()
                                   if k.startswith("asl_")},
                "register_entries": reg, "can_configure": P.allows(u["roles"], "qms:configure")}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    @app.get("/api/asl")
    def listing(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u)

    @app.post("/api/asl", status_code=201)
    async def add(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: A.add(c, u["email"], str(d.get("supplier") or ""), d.get("item_code"), d))
        return page(c, u)

    @app.put("/api/asl/{eid}")
    async def change(eid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: A.change(c, u["email"], ident(eid), d))
        return page(c, u)

    @app.get("/api/asl/{eid}/history")
    def history(eid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        run(lambda: A.get(c, ident(eid)))
        return {"history": A.history(c, eid), "signatures": Q.signatures(c, "asl", eid)}

    @app.post("/api/asl/from-register")
    def from_register(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        out = run(lambda: A.from_register(c, u["email"]))
        return {**page(c, u), **out}

    @app.post("/api/asl/{eid}/{action}")
    async def act(eid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        if action == "approve":
            run(lambda: A.approve(c, u, ident(eid), str(d.get("password") or ""), reason=str(d.get("reason") or ""),
                                  today=today(), basis=d["basis"] if isinstance(d.get("basis"), str) else None,
                                  review_due=d.get("review_due"),
                                  condition=d["condition"] if isinstance(d.get("condition"), str) else None,
                                  risk=d["risk"] if isinstance(d.get("risk"), str) else None))
        elif action in ("suspend", "disqualify", "requalify"):
            to = {"suspend": "suspended", "disqualify": "disqualified", "requalify": "draft"}[action]
            run(lambda: A.move(c, u["email"], ident(eid), to, str(d.get("reason") or "")))
        else:
            raise HTTPException(404, say("not found"))
        return page(c, u)
