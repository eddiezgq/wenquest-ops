"""PLM endpoints, steps 26a and 26b (ADR-0026). Only when the company manifest turns the module ``plm`` on.
Seeing needs plm:view; creating and editing parts and draft BOMs needs plm:edit; releasing (signed) and the numbering
rules need plm:release.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from wqops import i18n as I18N
from wqops.erp import ErpError
from wqops.hub import permissions as P
from wqops.hub.docs import store as F
from wqops.hub.plm import boms as B
from wqops.hub.plm import catalog as CAT
from wqops.hub.plm import config as CFG
from wqops.hub.plm import ecn as ECN
from wqops.hub.plm import explode as EX
from wqops.hub.plm import intake as IN
from wqops.hub.plm import manual as MAN
from wqops.hub.plm import manual_html as MANH
from wqops.hub.plm import parts as PT
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company, erp_client, ai_model=None) -> None:  # noqa: PLR0915, PLR0917
    def on() -> None:
        if "plm" not in (((company() or (None,))[0] or {}).get("modules") or []):
            raise HTTPException(404, say("the PLM module is not turned on for this company"))

    def need(u: dict, perm: str) -> None:
        on()
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=I18N.label(P.PERMISSIONS[perm])))

    def run(fn):
        try:
            return fn()
        except PT.Similar:
            raise
        except (PT.PlmError, Q.QualityError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except psycopg.errors.RaiseException as exc:      # the database kept a released record from changing
            raise HTTPException(409, say("someone released it meanwhile: open it again")) from exc
        except ErpError as exc:
            raise HTTPException(502, say("ERPNext did not answer as expected: {exc}", exc=exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        try:
            d = (await request.json()) if raw else {}
        except ValueError as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        return d if isinstance(d, dict) else {}

    def has_nul(v) -> bool:
        if isinstance(v, str):
            return "\x00" in v
        if isinstance(v, dict):
            return any(has_nul(k) or has_nul(x) for k, x in v.items())
        if isinstance(v, list):
            return any(has_nul(x) for x in v)
        return False

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    def flags(u: dict) -> dict:
        return {"can_edit": P.allows(u["roles"], "plm:edit"), "can_release": P.allows(u["roles"], "plm:release")}

    def erp_or_none():
        try:
            return erp_client()
        except Exception:
            return None

    @app.get("/api/plm/catalog")
    def catalog(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {"categories": CAT.shown(), "numbering": PT.numbering(c), "sources": list(PT.SOURCES),
                "file_kinds": list(PT.FILE_KINDS), **flags(u)}

    @app.put("/api/plm/numbering/{category}")
    async def set_numbering(category: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:release")
        d = await body(request)
        run(lambda: PT.set_numbering(c, u["email"], category, d.get("prefix"), d.get("digits", 5)))
        return {"numbering": PT.numbering(c)}

    @app.get("/api/plm/parts")
    def parts(q: str = "", category: str = "", status: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        rows = PT.listing(c, q=q[:100], category=category[:40], status=status[:20])
        return {"parts": rows[:PT.LIST_MAX], "more": len(rows) > PT.LIST_MAX, **flags(u)}

    @app.post("/api/plm/parts/similar")
    async def similar(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        d = await body(request)

        def go():
            from wqops.hub.plm import rules as R  # noqa: PLC0415

            cat = str(d.get("category") or "")
            CAT.get(cat)
            return {"similar": PT.check_similar(c, cat, R.clean_params(cat, d.get("params")))}
        return run(go)

    @app.post("/api/plm/parts", status_code=201)
    async def create(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        try:
            p = run(lambda: PT.create(c, u, d, erp_client()))
        except PT.Similar as exc:      # the similar parts go back with the message; the person confirms or reuses
            return JSONResponse({"detail": str(exc), "similar": exc.parts}, status_code=409)
        return {"id": p["id"], "code": p["item_code"], "erp_state": p["erp_state"]}

    @app.get("/api/plm/parts/{pid}")
    def show(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: PT.view(c, ident(pid))), **flags(u)}

    @app.put("/api/plm/parts/{pid}")
    async def update(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: PT.update(c, u, ident(pid), d, erp_or_none())), **flags(u)}

    @app.post("/api/plm/parts/{pid}/files")
    async def add_file(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(400, say("choose a file"))
        raw = await up.read(F.MAX_BYTES + 1)
        return {**run(lambda: PT.add_file(c, u, ident(pid), str(form.get("kind") or "other"), up.filename or "file",
                                          raw)), **flags(u)}

    @app.post("/api/plm/parts/{pid}/files/{fid}/remove")
    def remove_file(pid: int, fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        return {**run(lambda: PT.remove_file(c, u, ident(pid), ident(fid))), **flags(u)}

    @app.get("/api/plm/parts/{pid}/files/{fid}")
    def get_file(pid: int, fid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        row, data = run(lambda: PT.file_of(c, ident(pid), ident(fid)))
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['name'])}"})

    @app.post("/api/plm/parts/{pid}/bom", status_code=201)
    async def start_bom(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: B.start(c, u, ident(pid), d.get("change_id"))), **flags(u)}

    # ---- model configuration, 26c (before the generic part actions below)

    @app.get("/api/plm/parts/{pid}/config")
    def config(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: CFG.view(c, ident(pid))), **flags(u)}

    @app.put("/api/plm/parts/{pid}/config")
    async def save_config(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: CFG.save(c, u, ident(pid), d)), **flags(u)}

    @app.post("/api/plm/parts/{pid}/models", status_code=201)
    async def generate(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        try:
            return run(lambda: CFG.generate(c, u, ident(pid), d.get("choice"), erp_client(), d.get("version")))
        except psycopg.errors.UniqueViolation as exc:      # the same choice generated at the same moment elsewhere
            raise HTTPException(409, say("this model is being made by someone else: open the list again")) from exc

    @app.post("/api/plm/parts/{pid}/{action}")
    async def act(pid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(pid)
        steps = {"release": ("plm:release", lambda: PT.release(c, u, pid, str(d.get("password") or ""))),
                 "new-revision": ("plm:edit", lambda: PT.new_revision(c, u, pid, d.get("change_id"))),
                 "retry-erp": ("plm:edit", lambda: PT.view(c, PT.retry_erp(c, u, pid, erp_client())["id"]))}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        need(u, steps[action][0])
        return {**run(steps[action][1]), **flags(u)}

    @app.get("/api/plm/boms/compare")
    def compare(a: int, b: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return run(lambda: B.compare(c, ident(a), ident(b)))

    # ---- exploded views and English names (round 124, 27b)
    @app.get("/api/plm/explode/{bid}")
    def explode_view(bid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: EX.view(c, ident(bid))), **flags(u)}

    @app.post("/api/plm/explode/{bid}")
    async def explode_save(bid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        form = await request.form(max_files=2, max_fields=5, max_part_size=EX.MAX_IMAGE + 1)
        try:
            data = json.loads(str(form.get("data") or "{}"))
        except (ValueError, RecursionError) as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        if not isinstance(data, dict) or has_nul(data):
            raise HTTPException(400, say("the request is not JSON"))
        blobs = {}
        for k in ("snapshot", "image"):
            up = form.get(k)
            blobs[k] = (await up.read(EX.MAX_IMAGE + 1), up.filename or k) if isinstance(up, UploadFile) else None
        return {**run(lambda: EX.save(c, u, ident(bid), data,
                                      snapshot=blobs["snapshot"][0] if blobs["snapshot"] else None,
                                      image=blobs["image"][0] if blobs["image"] else None,
                                      image_name=blobs["image"][1] if blobs["image"] else "")), **flags(u)}

    @app.get("/api/plm/explode/{bid}/{which}")
    def explode_picture(bid: int, which: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        if which not in ("snapshot", "image"):
            raise HTTPException(404, say("not found"))
        data = run(lambda: EX.picture(c, ident(bid), which))
        return Response(data, media_type="image/png" if data.startswith(b"\x89PNG") else "image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.post("/api/plm/explode/{bid}/names")
    def explode_names(bid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        from wqops.hub.ai import agent as AG  # noqa: PLC0415
        from wqops.hub.ont import api as OA  # noqa: PLC0415

        need(u, "plm:edit")
        need(u, "ai:use")
        try:
            return run(lambda: EX.draft_names(c, u, ident(bid), ai_model, today=OA.today(company()[0])))
        except (AG.DailyLimit, HTTPException):
            raise
        except Exception as exc:
            raise HTTPException(502, say("the model did not answer: {exc}", exc=exc)) from exc

    @app.put("/api/plm/parts/{pid}/name-en")
    async def name_en(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return run(lambda: EX.set_name_en(c, u, ident(pid), d.get("name_en"), confirm=bool(d.get("confirm"))))

    # ---- the parts manual (round 124, 27c)
    @app.get("/api/plm/manuals/part/{pid}")
    def manual_overview(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: MAN.overview(c, ident(pid))), **flags(u)}

    @app.post("/api/plm/manuals/part/{pid}")
    async def manual_make(pid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        from wqops.hub.ont import api as OA  # noqa: PLC0415

        need(u, "plm:edit")
        today = OA.today(company()[0])
        await run_in_threadpool(lambda: run(lambda: MAN.generate(c, u, ident(pid), today=today)))
        return {**run(lambda: MAN.overview(c, ident(pid))), **flags(u)}

    @app.get("/api/plm/manuals/{mid}")
    def manual_get(mid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return run(lambda: MAN.get(c, ident(mid)))

    @app.get("/api/plm/manuals/{mid}/pdf")
    def manual_pdf(mid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        name, data = run(lambda: MAN.pdf(c, ident(mid)))
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})

    @app.get("/api/plm/manuals/{mid}/picture/{n}")
    def manual_picture(mid: int, n: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        data = run(lambda: MAN.picture(c, ident(mid), n))
        return Response(data, media_type="image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png")

    @app.post("/api/plm/manuals/part/{pid}/links")
    async def manual_link(pid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:release")           # giving the manual out of the company is the release-holder's call
        d = await body(request)
        return run(lambda: MAN.add_link(c, u, ident(pid), d.get("label") or ""))

    @app.post("/api/plm/manual-links/{lid}/revoke")
    def manual_revoke(lid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:release")
        return {**run(lambda: MAN.revoke(c, u, ident(lid))), **flags(u)}

    # read-only for dealers: no sign-in, only the pictures and tables of the newest edition (never the models)
    def public(c, token: str, count: bool = False) -> dict:
        m = MAN.by_token(c, token, count=count)
        if m is None:
            raise HTTPException(404, say("not found"))
        if m.get("revoked"):
            raise HTTPException(410, say("this link is revoked: please ask the maker"))
        return m

    @app.get("/m/{token}", response_class=HTMLResponse, include_in_schema=False)
    def manual_public(token: str, c=Depends(conn_dep)):
        try:
            m = public(c, token, count=True)
        except HTTPException as exc:          # a dealer may read either language: both, as on the page
            return HTMLResponse(MANH.message(MANH.GONE if exc.status_code == 410 else MANH.UNKNOWN),
                                status_code=exc.status_code)
        return HTMLResponse(MANH.page(m, f"/m/{quote(token)}"), headers={"Cache-Control": "no-store",
                                                                         "X-Robots-Tag": "noindex"})

    @app.get("/m/{token}/pdf", include_in_schema=False)
    def manual_public_pdf(token: str, c=Depends(conn_dep)):
        m = public(c, token)
        name, data = MAN.pdf(c, m["id"])
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}",
                                 "X-Robots-Tag": "noindex"})

    @app.get("/m/{token}/picture/{n}", include_in_schema=False)
    def manual_public_picture(token: str, n: int, c=Depends(conn_dep)):
        m = public(c, token)
        data = run(lambda: MAN.picture(c, m["id"], n))
        return Response(data, media_type="image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png",
                        headers={"X-Robots-Tag": "noindex"})

    @app.get("/api/plm/boms/{bid}/scene")
    def bom_scene(bid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return run(lambda: B.scene(c, ident(bid)))

    @app.get("/api/plm/boms/{bid}")
    def bom(bid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: B.view(c, ident(bid), erp_or_none())), **flags(u)}

    @app.put("/api/plm/boms/{bid}")
    async def bom_lines(bid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: B.set_lines(c, u, ident(bid), d.get("lines"), note=d.get("note"), erp=erp_or_none())),
                **flags(u)}

    @app.post("/api/plm/boms/{bid}/{action}")
    async def bom_act(bid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        ident(bid)
        steps = {"release": ("plm:release", lambda: B.release(c, u, bid, str(d.get("password") or ""), erp_client())),
                 "to-erp": ("plm:edit", lambda: B.to_erp(c, u, bid, erp_client()))}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        need(u, steps[action][0])
        return {**run(steps[action][1]), **flags(u)}

    @app.get("/api/plm/changes")
    def changes(u=Depends(user_dep), c=Depends(conn_dep)):
        """Approved product changes a new revision can rest on (17g)."""
        need(u, "plm:view")
        rows = c.execute("select id, name, title from changes where kind = 'product' and status = 'approved' "
                         "order by id desc limit 200").fetchall()
        return {"changes": [dict(r) for r in rows]}

    # ---- design changes, 26d: the parts a product change lists, how it takes effect, its impact analysis

    @app.get("/api/plm/changes/{cid}")
    def ecn_view(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: ECN.view(c, ident(cid))), **flags(u), "can_ai": P.allows(u["roles"], "ai:use")}

    @app.post("/api/plm/changes/{cid}/{action}")
    async def ecn_act(cid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        ident(cid)
        if action == "draft-note":
            from wqops.hub.ai import agent as AG  # noqa: PLC0415
            from wqops.hub.ont import api as OA  # noqa: PLC0415
            from wqops.hub.plm import ecn_ai as EAI  # noqa: PLC0415

            need(u, "ai:use")
            need(u, "quality:edit")         # the note goes into the change's assessment, which Quality edits
            try:
                return run(lambda: EAI.draft(c, u, cid, ai_model, today=OA.today(company()[0])))
            except AG.DailyLimit:
                raise
            except Exception as exc:
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(502, say("the model did not answer: {exc}", exc=exc)) from exc
        steps = {"add": lambda: ECN.add_item(c, u, cid, d),
                 "remove": lambda: ECN.remove_item(c, u, cid, d.get("part_id") if type(d.get("part_id")) is int
                                                   else 0),
                 "effect": lambda: ECN.set_effect(c, u, cid, d),
                 "analyse": lambda: ECN.analyse(c, u, cid, erp_or_none())}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        return {**run(steps[action]), **flags(u), "can_ai": P.allows(u["roles"], "ai:use")}

    # ---- design data inbox, 26e: FreeCAD (machine token), STEP and Excel uploads

    @app.get("/api/plm/intake")
    def intake_list(status: str = "pending", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        if status not in ("pending", "written", "rejected"):
            raise HTTPException(404, say("not found"))
        return {"batches": IN.listing(c, status), **flags(u)}

    @app.post("/api/plm/intake/upload", status_code=201)
    async def intake_upload(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        form = await request.form()
        up = form.get("file")
        kind = str(form.get("kind") or "")
        if not isinstance(up, UploadFile) or kind not in ("step", "excel"):
            raise HTTPException(400, say("choose a STEP or an Excel file"))
        raw = await up.read(F.MAX_BYTES + 1)
        try:     # reading a big STEP or workbook takes a while: off the event loop
            data = await run_in_threadpool(IN.read_file, kind, raw)
        except PT.PlmError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {**run(lambda: IN.upload(c, u, kind, up.filename or kind, raw, data)), **flags(u)}

    @app.get("/api/plm/intake/{iid}")
    def intake_view(iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        return {**run(lambda: IN.view(c, ident(iid), erp_or_none())), **flags(u)}

    @app.get("/api/plm/intake/{iid}/file")
    def intake_file(iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:view")
        name, data = run(lambda: IN.original(c, ident(iid)))
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    @app.put("/api/plm/intake/{iid}")
    async def intake_plan(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        return {**run(lambda: IN.set_plan(c, u, ident(iid), d.get("plan") or {}, d.get("changes"))), **flags(u)}

    @app.post("/api/plm/intake/{iid}/{action}")
    async def intake_act(iid: int, action: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "plm:edit")
        d = await body(request)
        ident(iid)
        steps = {"write": lambda: IN.write(c, u, iid, str(d.get("password") or ""), erp_client()),
                 "reject": lambda: IN.reject(c, u, iid, d.get("note"))}
        if action not in steps:
            raise HTTPException(404, say("not found"))
        return {**run(steps[action]), **flags(u)}

