"""Ledger import endpoints (ADR-0014 item 10): propose a mapping for a spreadsheet in the library, show and change
it, and import the rows with a signature. A ledger kind needs its own permission: quality:edit for the
nonconformance and corrective action logs, purchasing:draft for a supplier list.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops import i18n as I18N
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import permissions as P
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import ledger_ai as LAI
from wqops.hub.docs import ledgers as LS
from wqops.hub.docs import library as LIB
from wqops.hub.ont import api as OA
from wqops.hub.ont import project as OP
from wqops.hub.quality import records as Q
from wqops.i18n import say

log = logging.getLogger(__name__)


def _iso(row: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for k, v in row.items()}


def mount(app: FastAPI, conn_dep, user_dep, company, model, db_url: str | None,  # noqa: PLR0915, PLR0917
          erp_client=None) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                           PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def allowed(u: dict) -> list[str]:
        return [t for t, x in LG.TARGETS.items() if P.allows(u["roles"], x["perm"])]

    def number(v, what: str) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, say("{what} must be a whole number", what=what)) from exc

    def run(fn):
        try:
            return fn()
        except (LS.LedgerError, LIB.DocError, D.DraftError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        return (await request.json()) if raw else {}

    def view(c, imp: dict) -> dict:
        out = _iso(imp) | {"preview": run(lambda: LS.preview(c, imp)),
                           "signatures": Q.signatures(c, "ledger", imp["id"])}
        if imp["status"] == "imported":
            out["outcomes"] = LS.outcomes(c, imp["id"])
        return out

    @app.get("/api/ledgers")
    def ledgers(document_id: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        rows = c.execute("select * from ledger_imports where document_id = %s order by id desc",
                         (document_id,)).fetchall()
        return {"kinds": {t: LG.target_label(t) for t in allowed(u)}, "imports": [_iso(r) for r in rows]}

    @app.post("/api/ledgers", status_code=201)
    async def start(request: Request, u=Depends(user_dep)):
        """Read a spreadsheet of the library and propose its mapping (the model, else the rules)."""
        need(u, "documents:view")
        d = await body(request)
        kinds = allowed(u)
        if not kinds:
            raise HTTPException(403, say("your role does not allow importing any ledger"))
        target = str(d.get("target") or "")
        if target and target not in kinds:
            what = LG.target_label(target)
            raise HTTPException(403, say("your role does not allow importing a {what}", what=what))

        def work():
            with DB.connect(db_url) as c:
                doc = run(lambda: LIB.get(c, number(d.get("document_id"), "document_id")))
                hr = number(d.get("header_row"), "header_row")
                t = run(lambda: LS.table_of(c, doc, str(d.get("sheet") or ""), hr))
                targets = {k: LS.flds(c, k) for k in kinds}
                m = company()[0]
                p = LAI.propose(c, {"email": u["email"], "roles": u["roles"]}, t, targets, model, target=target,
                                today=OA.today(m), company=(m or {}).get("company", {}).get("name", "the company"))
                imp = LS.create(c, u["email"], doc, p["target"], t, p["proposal"], p["engine"], p["ai_run"])
                return view(c, imp)

        return await asyncio.to_thread(work)

    @app.get("/api/ledgers/{lid}")
    def one(lid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        imp = run(lambda: LS.get(c, lid))
        if imp["target"].startswith("erp_"):            # customers' and suppliers' contact details and tax ids
            need(u, LG.TARGETS[imp["target"]]["perm"])
        return view(c, imp)

    # plain functions: FastAPI runs them in its thread pool, so reading a large sheet does not hold up other requests
    @app.put("/api/ledgers/{lid}")
    def change(lid: int, d: dict, u=Depends(user_dep), c=Depends(conn_dep)):
        imp = run(lambda: LS.get(c, lid))
        need(u, LG.TARGETS[imp["target"]]["perm"])
        hr = d.get("header_row")
        return view(c, run(lambda: LS.update(c, u["email"], lid, mapping=d.get("mapping") or {},
                                             values=d.get("values") or {}, sheet=d.get("sheet"),
                                             header_row=number(hr, "header_row") if hr not in (None, "") else None)))

    @app.post("/api/ledgers/{lid}/import")
    def do_import(lid: int, d: dict, u=Depends(user_dep), c=Depends(conn_dep)):
        imp = run(lambda: LS.get(c, lid))
        need(u, LG.TARGETS[imp["target"]]["perm"])
        if imp["target"].startswith("erp_"):            # another system's rows into ERPNext (ADR-0020, 20a)
            from wqops.hub import erp_import as EI  # noqa: PLC0415
            from wqops.hub import sync as Y  # noqa: PLC0415

            m = company()[0] or {}
            try:
                erp = erp_client()
            except Exception as exc:
                raise HTTPException(
                    503, say("ERPNext is not set up for WenQuest Ops; ask whoever runs the system")) from exc
            out = run(lambda: EI.run(c, erp, u, lid, str(d.get("password", "")),
                                     company=(m.get("company") or {}).get("name", ""), today=OA.today(m),
                                     submit=d.get("submit") is True, seen=d.get("seen")))
            # what was created shows at once; if not, the regular sync brings it (earlier imports are known anyway)
            for step in (lambda: Y.run(c, erp, trigger="import"), lambda: OP.project(c, manifest=m)):
                try:
                    step()
                except Exception:  # logged; the regular sync catches up
                    log.exception("after the ERPNext import %s", lid)
            return view(c, out)
        out = run(lambda: LS.run_import(c, u, lid, str(d.get("password", ""))))
        if imp["target"] != "supplier":
            OP.project(c, manifest=company()[0])      # imported NCRs and CAPAs show in the ops hub at once
        return view(c, out)
