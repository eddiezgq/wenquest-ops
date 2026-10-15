"""Incoming inspection endpoints, step 17b (ADR-0017). Seeing needs quality:view; starting, entering, signing,
releasing and rejecting need quality:edit; drafting plans needs quality:edit; the sampling table, enabling plans,
the switching rules, inspection levels and the settings need qms:configure. Signing, enabling, releasing and
rejecting are signed with the person's password.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import drafts as D
from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import iqc as I
from wqops.hub.quality import records as Q
from wqops.hub.quality import sampling as S


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per action
    def need(u: dict, *perms: str) -> None:
        for perm in perms:
            if not P.allows(u["roles"], perm):
                raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (I.IqcError, Q.QualityError, D.DraftError, S.SamplingError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        d = (await request.json()) if raw else {}
        return d if isinstance(d, dict) else {}

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, "not found")
        return v

    def can(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "quality:edit"), "can_configure": P.allows(u["roles"],
                                                                                            "qms:configure")}

    @app.get("/api/iqc")
    def home(status: str = "open", u=Depends(user_dep), c=Depends(conn_dep)):
        """Inspections, receipt lines waiting, plans, the sampling table, levels, rules and settings."""
        need(u, "quality:view")
        return {"inspections": I.listing(c, status), "waiting": I.awaiting(c), "plans": I.plans(c),
                "rows": I.rows(c), "levels": I.levels(c), "rules": I.switch_rules(c), "settings": I.settings(c),
                "setting_labels": {k: v[1] for k, v in I.SETTINGS.items()}, "conditions": S.CONDITIONS,
                "items": I.items(c), "suppliers": I.suppliers(c), **can(u)}

    # ------------------------------------------------ inspections

    @app.post("/api/iqc/inspections", status_code=201)
    async def start(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: I.start(c, u["email"], str(d.get("item_code") or ""), d.get("lot_qty"),
                                  receipt=str(d["receipt"]) if d.get("receipt") else None,
                                  supplier=str(d["supplier"]) if d.get("supplier") else None,
                                  lot_no=str(d.get("lot_no") or ""), today=OA.today(company()[0])))
        return {"id": row["id"], "name": row["name"]}

    def page(c, u, iid: int) -> dict:
        return {**run(lambda: I.view(c, iid)), **can(u)}

    @app.get("/api/iqc/inspections/{iid}")
    def inspection(iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return page(c, u, ident(iid))

    @app.put("/api/iqc/inspections/{iid}/readings")
    async def enter(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: I.enter(c, u["email"], ident(iid), d.get("readings")))
        return page(c, u, iid)

    @app.post("/api/iqc/inspections/{iid}/sign")
    async def sign(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: I.sign(c, u, ident(iid), str(d.get("password") or "")))
        return page(c, u, iid)

    @app.post("/api/iqc/inspections/{iid}/decide")
    async def decide(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: I.decide(c, u, ident(iid), str(d.get("password") or ""), str(d.get("note") or ""),
                             today=OA.today(company()[0])))
        return page(c, u, iid)

    @app.post("/api/iqc/inspections/{iid}/void")
    async def void(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: I.void(c, u["email"], ident(iid), str(d.get("reason") or "")))
        return page(c, u, iid)

    # ------------------------------------------------ plans

    def plan_page(c, u, pid: int) -> dict:
        p = run(lambda: I.plan(c, pid))
        return {**I._iso(p), "history": I.history(c, "plan", pid), "signatures": Q.signatures(c, "iqc_plan", pid),
                "versions": I.plans(c, p["item_code"]), "settings": I.settings(c), **can(u)}

    @app.post("/api/iqc/plans", status_code=201)
    async def new_plan(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        row = run(lambda: I.new_plan(c, u["email"], str(d.get("item_code") or ""), d.get("aql"),
                                     d.get("characteristics"), str(d.get("note") or "")))
        return {"id": row["id"]}

    @app.get("/api/iqc/plans/{pid}")
    def show_plan(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return plan_page(c, u, ident(pid))

    @app.put("/api/iqc/plans/{pid}")
    async def change_plan(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: I.update_plan(c, u["email"], ident(pid), aql=d.get("aql"),
                                  characteristics=d.get("characteristics"),
                                  note=str(d["note"]) if isinstance(d.get("note"), str) else None))
        return plan_page(c, u, pid)

    @app.post("/api/iqc/plans/{pid}/{action}")
    async def plan_action(pid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        if action == "enable":
            need(u, "qms:configure")
            run(lambda: I.enable_plan(c, u, ident(pid), str(d.get("password") or ""),
                                      str(d["seen"]) if d.get("seen") else None))
        elif action == "discard":
            need(u, "quality:edit")
            run(lambda: I.discard_plan(c, u["email"], ident(pid)))
        elif action == "new-version":
            need(u, "quality:edit")
            row = run(lambda: I.new_version(c, u["email"], ident(pid)))
            return plan_page(c, u, row["id"])
        else:
            raise HTTPException(404, "not found")
        return plan_page(c, u, pid)

    # ------------------------------------------------ sampling table, rules, levels, settings

    @app.post("/api/iqc/rows", status_code=201)
    async def add_row(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: I.add_row(c, u["email"], d))
        return I.rows(c)

    @app.post("/api/iqc/rows/{rid}/{action}")
    async def row_action(rid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        if action == "check":
            run(lambda: I.verify_row(c, u["email"], ident(rid), str(d.get("source") or "")))
        elif action in ("archive", "restore"):
            run(lambda: I.archive_row(c, u["email"], ident(rid), action == "restore"))
        else:
            raise HTTPException(404, "not found")
        return I.rows(c)

    @app.post("/api/iqc/rules")
    async def save_rule(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        rid = d.get("id")
        if rid is not None and (type(rid) is not int or not 0 < rid < 2**63):
            raise HTTPException(400, "id is a rule number")
        return run(lambda: I.save_rule(c, u["email"], rid, d))

    @app.post("/api/iqc/levels")
    async def switch(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        run(lambda: I.switch(c, u, str(d.get("supplier") or ""), str(d.get("item_code") or ""),
                             str(d.get("to_level") or ""), str(d.get("reason") or "")))
        return I.levels(c)

    @app.get("/api/iqc/levels/history")
    def level_history(supplier: str = "", item_code: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return I.switches(c, supplier or None, item_code or None)

    @app.post("/api/iqc/settings")
    async def setting(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "qms:configure")
        d = await body(request)
        return run(lambda: I.set_setting(c, u["email"], str(d.get("key") or ""), d.get("value")))
