"""Quality system endpoints (ADR-0016, step 16a). Seeing the system's state needs quality:view; adopting a standard,
saying what does not apply and linking evidence need qms:configure; adopting and declaring are signed.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.ai import llm as L
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.hub.system import draft_ai as DAI
from wqops.hub.system import gaps as G
from wqops.hub.system import qms as QMS
from wqops.hub.system import registers as RG


def mount(app: FastAPI, conn_dep, user_dep, company, model=None,  # noqa: PLR0915, PLR0917 - one route per action
          db_url: str | None = None) -> None:
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except (QMS.QmsError, Q.QualityError, RG.RegisterError, G.TodoError) as exc:
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

    # ---------------------------------------------------------------- registers (16b)

    def entry_view(c, e: dict) -> dict:
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in e.items()}

    def register_page(c, u, name: str) -> dict:
        s = run(lambda: RG.spec(name))
        return {"name": name, "spec": s, "can_edit": P.allows(u["roles"], "quality:edit"),
                "entries": [entry_view(c, e) for e in RG.entries(c, name)]}

    @app.get("/api/registers")
    def registers(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        counts = RG.counts(c)
        return [{"name": k, "label": s["label"], "signed": bool(s.get("sign")), "counts": counts.get(k, {})}
                for k, s in RG.specs().items()]

    @app.get("/api/registers/{name}")
    def register(name: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return register_page(c, u, name)

    @app.post("/api/registers/{name}", status_code=201)
    async def add_entry(name: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: RG.create(c, u["email"], name, d.get("values") or {}))
        QMS.evaluate_changed(c, today(), u["email"], tz())
        return register_page(c, u, name)

    def entry_of(c, eid: int) -> dict:
        if not 0 < eid < 2**63:
            raise HTTPException(404, "not found")
        return run(lambda: RG.get(c, eid))

    @app.get("/api/register-entries/{eid}")
    def entry(eid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        e = entry_of(c, eid)
        return {**entry_view(c, e), "history": RG.history(c, eid), "spec": RG.spec(e["register"]),
                "signatures": Q.signatures(c, "register", eid)}

    @app.put("/api/register-entries/{eid}")
    async def change_entry(eid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        e = entry_of(c, eid)
        d = await body(request)
        run(lambda: RG.update(c, u["email"], eid, d.get("values") or {}))
        QMS.evaluate_changed(c, today(), u["email"], tz())
        return register_page(c, u, e["register"])

    @app.post("/api/register-entries/{eid}/sign")
    async def sign_entry(eid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        e = entry_of(c, eid)
        d = await body(request)
        run(lambda: RG.sign(c, u, eid, str(d.get("password") or "")))
        QMS.evaluate_changed(c, today(), u["email"], tz())
        return register_page(c, u, e["register"])

    @app.post("/api/register-entries/{eid}/void")
    async def void_entry(eid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        e = entry_of(c, eid)
        d = await body(request)
        run(lambda: RG.void(c, u, eid, str(d.get("reason") or ""), str(d.get("password") or "")))
        QMS.evaluate_changed(c, today(), u["email"], tz())
        return register_page(c, u, e["register"])

    # ---------------------------------------------------------------- gaps, to-dos, audit checklist (16c)

    def day(v) -> dt.date | None:
        if v in (None, ""):
            return None
        try:
            return dt.date.fromisoformat(str(v))
        except ValueError as exc:
            raise HTTPException(400, "due is a date like 2026-11-30") from exc

    def ai_ready() -> bool:
        return model is not None and model.configured()

    def gaps_page(c, u, standard: str) -> dict:
        out = run(lambda: G.report(c, standard))
        can_draft = ai_ready() and all(P.allows(u["roles"], x) for x in ("qms:configure", "documents:edit", "ai:use"))
        return {**out, "can_edit": P.allows(u["roles"], "quality:edit"), "ai": ai_ready(),
                "draftable": sorted(DAI.draftable(c, standard)) if can_draft else []}

    @app.get("/api/qms/{standard}/gaps")
    def gap_report(standard: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return gaps_page(c, u, standard)

    @app.post("/api/qms/{standard}/todos", status_code=201)
    async def add_todo(standard: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: G.add(c, u["email"], standard, str(d.get("control") or ""), title=str(d.get("title") or ""),
                          owner=str(d.get("owner") or ""), due=day(d.get("due"))))
        return gaps_page(c, u, standard)

    @app.post("/api/qms/{standard}/todos/all")
    async def add_all_todos(standard: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        run(lambda: G.add_all(c, u["email"], standard, day(d.get("due"))))
        return gaps_page(c, u, standard)

    @app.put("/api/qms-todos/{tid}")
    async def change_todo(tid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        if not 0 < tid < 2**63:
            raise HTTPException(404, "not found")
        d = await body(request)
        row = run(lambda: G.change(c, u["email"], tid, owner=d.get("owner") if isinstance(d.get("owner"), str)
                                   else None, due=day(d.get("due")), clear_due=d.get("due") == "",
                                   status=d.get("status"), note=str(d.get("note") or "")))
        return gaps_page(c, u, row["standard"])

    @app.get("/api/qms/{standard}/checklist")
    def audit_checklist(standard: str, process: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return run(lambda: G.checklist(c, standard, process))

    @app.post("/api/qms/{standard}/controls/{control}/draft", status_code=201)
    async def draft(standard: str, control: str, u=Depends(user_dep)):
        """The model drafts the missing document into the library, for review and approval."""
        for perm in ("qms:configure", "documents:edit", "ai:use"):
            need(u, perm)
        if not ai_ready():
            raise HTTPException(409, "there is no model key; write the document yourself and link it")

        def work():
            with DB.connect(db_url) as c:
                m = company()[0]
                try:
                    doc = run(lambda: DAI.draft(c, {"email": u["email"], "roles": u["roles"]}, standard, control,
                                                model, today=OA.today(m),
                                                company=(m or {}).get("company", {}).get("name", "the company")))
                except L.LlmError as exc:
                    raise HTTPException(502, f"the model could not write the draft: {exc}") from exc
                return {"document_id": doc["id"], "title": doc["title"]}

        return await asyncio.to_thread(work)

