"""Risk management endpoints, step 17h (ADR-0017). Seeing needs quality:view; starting and editing risk files,
starting a new version and withdrawing a draft need quality:edit; the criteria (levels, matrix, the example) and
approving (signed) need qms:configure.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops import i18n as I18N
from wqops.hub import permissions as P
from wqops.hub.quality import records as Q
from wqops.hub.quality import risk as R
from wqops.hub.quality import risk_rules as RR
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def run(fn):
        try:
            return fn()
        except (R.RiskError, Q.QualityError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        d = (await request.json()) if raw else {}
        return d if isinstance(d, dict) else {}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    def can(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"),
                "can_configure": P.allows(u["roles"], "qms:configure")}

    def criteria(c) -> dict:
        lv, m = R.levels(c), R.matrix(c)
        return {"levels": RR.shown_levels(lv),
                "matrix": [{"severity": s, "probability": p, "verdict": v} for (s, p), v in m.items()],
                "gaps": RR.matrix_gaps(lv, m), "verdicts": RR.verdicts(), "example_note": say(RR.EXAMPLE_NOTE)}

    @app.get("/api/risk")
    def home(status: str = "current", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"files": R.listing(c, status), **criteria(c), "criteria_history": R.criteria_history(c),
                "people": [r["email"] for r in c.execute("select email from users where active order by email")],
                **can(u)}

    # ------------------------------------------------ criteria

    @app.post("/api/risk/levels", status_code=201)
    async def add_level(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: R.add_level(c, u["email"], d))
        return criteria(c)

    @app.put("/api/risk/levels/{lid}")
    async def change_level(lid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: R.update_level(c, u["email"], ident(lid), d))
        return criteria(c)

    @app.put("/api/risk/matrix")
    async def cell(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: R.set_cell(c, u["email"], d.get("severity"), d.get("probability"), d.get("verdict") or None))
        return criteria(c)

    @app.post("/api/risk/example")
    def example(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        run(lambda: R.load_example(c, u["email"]))
        return criteria(c)

    # ------------------------------------------------ files

    def page(c, u, fid: int) -> dict:
        return {**run(lambda: R.view(c, fid)), **criteria(c), **can(u),
                "people": [r["email"] for r in c.execute("select email from users where active order by email")]}

    @app.post("/api/risk/files", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: R.create(c, u["email"], d))
        return {"id": row["id"], "name": row["name"]}

    @app.get("/api/risk/files/{fid}")
    def show(fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(fid))

    @app.put("/api/risk/files/{fid}")
    async def change(fid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: R.update(c, u["email"], ident(fid), d))
        return page(c, u, fid)

    @app.post("/api/risk/files/{fid}/items", status_code=201)
    async def add_item(fid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: R.add_item(c, u["email"], ident(fid), d))
        return page(c, u, fid)

    @app.put("/api/risk/files/{fid}/items/{iid}")
    async def change_item(fid: int, iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: R.update_item(c, u["email"], ident(fid), ident(iid), d))
        return page(c, u, fid)

    @app.delete("/api/risk/files/{fid}/items/{iid}")
    def remove_item(fid: int, iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        run(lambda: R.remove_item(c, u["email"], ident(fid), ident(iid)))
        return page(c, u, fid)

    @app.post("/api/risk/files/{fid}/{action}")
    async def act(fid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(fid)
        if action == "approve":
            need(u, "qms:configure")
            run(lambda: R.approve(c, u, fid, str(d.get("password") or "")))
        elif action == "withdraw":
            need(u, "quality:edit")
            run(lambda: R.withdraw(c, u["email"], fid, str(d.get("reason") or "")))
        elif action == "revise":
            need(u, "quality:edit")
            row = run(lambda: R.revise(c, u["email"], fid))
            return page(c, u, row["id"])
        else:
            raise HTTPException(404, say("not found"))
        return page(c, u, fid)
