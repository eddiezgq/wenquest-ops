"""Quality endpoints (ADR-0009): nonconformance reports, 8D, corrective and preventive actions.

Reading needs quality:view; every change needs quality:edit, except that an action's owner may mark it done.
After a change the ops hub objects are brought up to date, so pages and anomalies see it at once.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import permissions as P
from wqops.hub.ont import project as OP
from wqops.hub.quality import records as Q


def _iso(row: dict) -> dict:
    """Dates as ISO text and numerics as numbers, for JSON."""
    return {k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else float(v) if isinstance(v, Decimal) else v
            for k, v in row.items()}


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per step
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(c, fn):
        try:
            out = fn()
        except Q.QualityError as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        OP.project(c, manifest=company()[0])
        return out

    async def body(request: Request) -> dict:
        raw = await request.body()
        return (await request.json()) if raw else {}

    def ncr_view(c, row: dict) -> dict:
        e = c.execute("select * from eightd where ncr_id = %s", (row["id"],)).fetchone()
        capas = c.execute("select id, name, title, status, kind from capas where ncr_id = %s order by id",
                          (row["id"],)).fetchall()
        return _iso(row) | {"history": Q.history(c, "ncr", row["id"]), "capas": capas,
                            "eightd": _iso(e) if e else None, "dispositions": Q.DISPOSITIONS,
                            "sections": Q.SECTIONS}

    @app.get("/api/quality/ncrs")
    def ncrs(status: str = "active", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        sql = "select * from ncr_records"
        if status == "active":
            sql += " where status not in ('closed', 'cancelled')"
        elif status != "all":
            sql += " where status = %(s)s"
        return [_iso(r) for r in c.execute(sql + " order by id desc limit 500", {"s": status}).fetchall()]

    @app.post("/api/quality/ncrs", status_code=201)
    async def new_ncr(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        keys = ("title", "description", "severity", "owner", "inspection", "item_code", "receipt", "supplier",
                "quantity")
        return ncr_view(c, run(c, lambda: Q.create_ncr(c, u["email"], **{k: d[k] for k in keys if k in d})))

    @app.get("/api/quality/ncrs/{nid}")
    def get_ncr(nid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        try:
            return ncr_view(c, Q.ncr(c, nid))
        except KeyError as exc:
            raise HTTPException(404, "no such report") from exc

    @app.post("/api/quality/ncrs/{nid}/{step}")
    async def ncr_step(nid: int, step: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        steps = {
            "contain": lambda: Q.contain(c, nid, u["email"], str(d.get("containment", ""))),
            "disposition": lambda: Q.disposition(c, nid, u["email"], str(d.get("disposition", "")),
                                                 d.get("quantity"), str(d.get("note", ""))),
            "close": lambda: Q.close_ncr(c, nid, u["email"], str(d.get("note", ""))),
            "cancel": lambda: Q.cancel_ncr(c, nid, u["email"], str(d.get("reason", ""))),
            "8d": lambda: Q.save_8d(c, nid, u["email"], d.get("sections") or {}) and Q.ncr(c, nid),
            "8d-complete": lambda: Q.complete_8d(c, nid, u["email"]) and Q.ncr(c, nid),
        }
        if step not in steps:
            raise HTTPException(404, f"no step {step}")
        run(c, steps[step])
        return ncr_view(c, Q.ncr(c, nid))

    def capa_view(c, row: dict) -> dict:
        ncr = c.execute("select id, name, title from ncr_records where id = %s", (row["ncr_id"],)).fetchone() \
            if row["ncr_id"] else None
        return _iso(row) | {"actions": [_iso(a) for a in Q.actions(c, row["id"])], "ncr": ncr,
                            "history": Q.history(c, "capa", row["id"])}

    @app.get("/api/quality/capas")
    def capas(status: str = "active", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        sql = "select * from capas"
        if status == "active":
            sql += " where status <> 'closed'"
        elif status != "all":
            sql += " where status = %(s)s"
        return [_iso(r) for r in c.execute(sql + " order by id desc limit 500", {"s": status}).fetchall()]

    @app.post("/api/quality/capas", status_code=201)
    async def new_capa(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(c, lambda: Q.create_capa(c, u["email"], kind=str(d.get("kind", "corrective")),
                                           title=str(d.get("title", "")), description=str(d.get("description", "")),
                                           ncr_id=d.get("ncr_id"), owner=d.get("owner"), actions=d.get("actions")))
        return capa_view(c, row)

    @app.get("/api/quality/capas/{cid}")
    def get_capa(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        try:
            return capa_view(c, Q.capa(c, cid))
        except KeyError as exc:
            raise HTTPException(404, "no such action") from exc

    @app.post("/api/quality/capas/{cid}/{step}")
    async def capa_step(cid: int, step: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        if step != "action-done":
            need(u, "quality:edit")
        edit = P.allows(u["roles"], "quality:edit")
        steps = {
            "action": lambda: Q.add_action(c, cid, u["email"], str(d.get("text", "")), d.get("owner"), d.get("due")),
            "action-done": lambda: Q.action_done(c, int(d.get("action_id", 0)), u["email"], edit),
            "start": lambda: Q.start_capa(c, cid, u["email"]),
            "verification": lambda: Q.to_verification(c, cid, u["email"]),
            "verify": lambda: Q.verify(c, cid, u["email"], str(d.get("result", "")), str(d.get("method", ""))),
        }
        if step not in steps:
            raise HTTPException(404, f"no step {step}")
        run(c, steps[step])
        return capa_view(c, Q.capa(c, cid))

    @app.get("/api/quality/my-actions")
    def my_actions(u=Depends(user_dep), c=Depends(conn_dep)):
        """Open corrective-action steps assigned to me (anyone may have some)."""
        rows = c.execute("select a.*, c.name as capa, c.title as capa_title from capa_actions a join capas c on "
                         "c.id = a.capa_id where a.owner = %s and not a.done order by a.due nulls last",
                         (u["email"],)).fetchall()
        return [_iso(r) for r in rows]
