"""Device identifiers, scanning and labels (ADR-0020, 20b). Anyone signed in can scan; what a code is matched to
needs quality:view. Device identifiers and labels: quality:view to see, quality:edit to change and print."""

from __future__ import annotations

import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from wqops.hub import permissions as P
from wqops.hub import udi as UD
from wqops.hub import udi_rules as U
from wqops.hub.ont import api as OA


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (UD.UdiError, U.UdiError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc

    async def body(request: Request) -> dict:
        try:
            d = await request.json()
        except ValueError as exc:
            raise HTTPException(400, "the request is not JSON") from exc
        return d if isinstance(d, dict) else {}

    def tz() -> str:
        return ((company()[0] or {}).get("company") or {}).get("timezone") or "UTC"

    def date(v) -> dt.date | None:
        if v in (None, ""):
            return None
        try:
            return dt.date.fromisoformat(str(v)[:10])
        except ValueError as exc:
            raise HTTPException(400, "a date looks like 2028-12-31") from exc

    def rid_ok(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    @app.get("/api/udi/items")
    def udi_items(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"items": UD.items(c), "can_edit": P.allows(u["roles"], "quality:edit"),
                "erp_items": [r["key"] for r in c.execute(
                    "select key from ont_objects where type = 'Item' and not deleted order by key limit 2000")]}

    @app.put("/api/udi/items/{item_code}")
    async def udi_set(item_code: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        return dict(run(lambda: UD.set_di(c, u["email"], item_code, d)), history=UD.history(c, item_code))

    @app.get("/api/udi/items/{item_code}/history")
    def udi_history(item_code: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return UD.history(c, item_code)

    @app.post("/api/udi/scan")
    async def udi_scan(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        out = run(lambda: UD.look_up(c, str(d.get("code") or "")[:600], OA.today(company()[0])))
        if not P.allows(u["roles"], "quality:view"):        # the read is for anyone; the records are not
            out["found"] = {"item_code": None, "production": [], "incoming": []}
        return out

    @app.get("/api/production/{rid}/label")
    def label_view(rid: int, expiry: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return {"label": run(lambda: UD.label(c, rid_ok(rid), expiry=date(expiry), tz=tz())),
                "prints": UD.prints(c, rid), "can_print": P.allows(u["roles"], "quality:edit")}

    @app.post("/api/production/{rid}/label")
    async def label_print(rid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        fmt = d.get("format")
        copies = d.get("copies", 1)
        if fmt not in ("screen", "zpl") or type(copies) is not int or not 1 <= copies <= 500:
            raise HTTPException(400, "choose screen or zpl, and 1 to 500 copies")
        lab = run(lambda: UD.label(c, rid_ok(rid), expiry=date(d.get("expiry")), tz=tz()))
        text = run(lambda: U.zpl(lab["data"], lab["lines"], gs1=lab["agency"] == "gs1", copies=copies)) \
            if fmt == "zpl" else None
        UD.printed(c, u["email"], rid, lab, fmt=fmt, copies=copies)
        if text is not None:
            return PlainTextResponse(text, headers={"content-disposition":
                                                    f'attachment; filename="{lab["record"]}-label.zpl"'})
        return {"label": lab, "prints": UD.prints(c, rid)}
