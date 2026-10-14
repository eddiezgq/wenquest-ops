"""Document library endpoints (ADR-0014): upload, classify, review, controlled documents, search and overview.

Reading needs documents:view; changes need documents:edit. Taking text and classifying run after the response,
in the background; the page polls the import.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import zipfile
from decimal import Decimal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from wqops.hub import db as DB
from wqops.hub import permissions as P
from wqops.hub.docs import ai_classify as AIC
from wqops.hub.docs import classify as K
from wqops.hub.docs import library as LIB
from wqops.hub.docs import store as F
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q

log = logging.getLogger("wqops.hub.docs")
MAX_FILES = 2000
MAX_ZIP_TOTAL = 2 * 1024 * 1024 * 1024
TEXT_SHOWN = 30000


def _iso(row: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else float(v) if isinstance(v, Decimal) else v
            for k, v in row.items()}


def _zip(c, imp_id: int, up: UploadFile, taken: list[int]) -> None:
    """Every accepted file inside a zip, under a folder named after the zip."""
    root = (up.filename or "archive.zip").rsplit(".", 1)[0]
    try:
        z = zipfile.ZipFile(up.file)
    except zipfile.BadZipFile:
        LIB.skip(c, imp_id, up.filename or "archive.zip", "not a readable zip file")
        return
    total = 0
    with z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or "__MACOSX" in name or name.rsplit("/", 1)[-1].startswith("."):
                continue
            if taken[0] >= MAX_FILES:
                LIB.skip(c, imp_id, name, f"more than {MAX_FILES} files in one import")
                continue
            if info.file_size > F.MAX_BYTES or total + info.file_size > MAX_ZIP_TOTAL:
                LIB.skip(c, imp_id, name, "too large")
                continue
            total += info.file_size
            try:
                with z.open(info) as fh:
                    data = fh.read(F.MAX_BYTES + 1)
                LIB.add_file(c, imp_id, f"{root}/{name}", data)
                taken[0] += 1
            except LIB.DocError as exc:
                LIB.skip(c, imp_id, name, str(exc))
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:  # encrypted or unknown method
                LIB.skip(c, imp_id, name, f"could not unpack: {exc}")


def resume(db_url: str) -> None:
    """Continue reading text of imports a restart interrupted (in the background, so start-up is not delayed)."""
    with DB.connect(db_url) as c:
        ids = LIB.recover(c)

    def work():
        for i in ids:
            try:
                with DB.connect(db_url) as c:
                    LIB.extract_import(c, i)
            except Exception:
                log.exception("taking text from import %s failed", i)

    if ids:
        threading.Thread(target=work, name="docs-resume", daemon=True).start()


def mount(app: FastAPI, conn_dep, user_dep, company, model, db_url: str | None) -> None:  # noqa: PLR0915, PLR0917
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(fn):
        try:
            return fn()
        except LIB.DocError as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "no such document") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    async def body(request: Request) -> dict:
        raw = await request.body()
        return (await request.json()) if raw else {}

    def ai_on() -> bool:
        return model is not None and model.configured()

    def extract_job(imp_id: int) -> None:
        try:
            with DB.connect(db_url) as c:
                LIB.extract_import(c, imp_id)
        except Exception:
            log.exception("taking text from import %s failed", imp_id)
            with DB.connect(db_url) as c:
                c.execute("update doc_imports set status = 'ready', error = 'taking the text stopped early; see the "
                          "hub log' where id = %s", (imp_id,))

    def classify_job(imp_id: int, user: dict, use_ai: bool) -> None:
        m = company()[0]
        try:
            with DB.connect(db_url) as c:
                AIC.run(c, user, imp_id, model, today=OA.today(m),
                        company=(m or {}).get("company", {}).get("name", "the company"), use_ai=use_ai)
        except Exception:
            log.exception("classifying import %s failed", imp_id)
            with DB.connect(db_url) as c:
                c.execute("update doc_imports set status = 'done', error = 'classification stopped early; see the "
                          "hub log' where id = %s", (imp_id,))

    def import_view(c, r: dict) -> dict:
        counts = {x["status"]: x["n"] for x in c.execute(
            "select status, count(*) as n from documents where import_id = %s group by 1", (r["id"],))}
        text = {x["text_status"]: x["n"] for x in c.execute(
            "select text_status, count(*) as n from documents where import_id = %s group by 1", (r["id"],))}
        dup = c.execute("select count(*) as n from documents where import_id = %s and duplicate_of is not null",
                        (r["id"],)).fetchone()["n"]
        return _iso(r) | {"counts": counts, "text": text, "duplicates": dup, "estimate": LIB.estimate(c, r["id"])}

    @app.get("/api/docs/meta")
    def meta(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        return {"types": K.TYPES, "controlled": sorted(K.CONTROLLED), "processes": LIB.processes(c),
                "ai": ai_on(), "model": model.model if ai_on() else None,
                "can_edit": P.allows(u["roles"], "documents:edit"), "max_mb": F.MAX_BYTES // (1024 * 1024),
                "batch_rule": "high confidence and every quote found in the file"}

    @app.post("/api/docs/imports", status_code=201)
    async def upload(request: Request, background: BackgroundTasks, u=Depends(user_dep), c=Depends(conn_dep)):
        """Files, folders (relative paths as file names) and zip files in one import batch."""
        need(u, "documents:edit")
        form = await request.form(max_files=MAX_FILES + 1, max_fields=MAX_FILES + 10)
        ups = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
        if not ups:
            raise HTTPException(400, "choose some files")
        imp = LIB.new_import(c, u["email"], str(form.get("label") or ""))
        taken = [0]
        try:
            for up in ups:
                name = up.filename or "file"
                if name.lower().endswith(".zip"):
                    _zip(c, imp["id"], up, taken)
                    continue
                if taken[0] >= MAX_FILES:
                    LIB.skip(c, imp["id"], name, f"more than {MAX_FILES} files in one import")
                    continue
                data = await up.read(F.MAX_BYTES + 1)
                try:
                    LIB.add_file(c, imp["id"], name, data)
                    taken[0] += 1
                except LIB.DocError as exc:
                    LIB.skip(c, imp["id"], name, str(exc))
        finally:                                     # also when the upload stops early (disk full): no stuck import
            if taken[0]:
                background.add_task(extract_job, imp["id"])
            else:
                c.execute("update doc_imports set status = 'done' where id = %s", (imp["id"],))
        return import_view(c, LIB.get_import(c, imp["id"]))

    @app.get("/api/docs/imports")
    def imports(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        return [import_view(c, r) for r in c.execute("select * from doc_imports order by id desc limit 100")]

    @app.get("/api/docs/imports/{imp_id}")
    def one_import(imp_id: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        return run(lambda: import_view(c, LIB.get_import(c, imp_id)))

    @app.post("/api/docs/imports/{imp_id}/classify", status_code=202)
    async def classify(imp_id: int, request: Request, background: BackgroundTasks, u=Depends(user_dep),
                       c=Depends(conn_dep)):
        """Classify with the model (default when there is one) or with the rules (``{"engine": "rules"}``)."""
        need(u, "documents:edit")
        d = await body(request)
        imp = run(lambda: LIB.get_import(c, imp_id))
        if imp["status"] not in ("ready", "done"):
            raise HTTPException(409, f"this import is {imp['status']}; wait until its text is taken")
        if not c.execute("select 1 from documents where import_id = %s and status = 'to_classify'",
                         (imp_id,)).fetchone():
            raise HTTPException(409, "nothing in this import is waiting for classification")
        if not c.execute("update doc_imports set status = 'classifying' where id = %s and status in ('ready', 'done') "
                         "returning id", (imp_id,)).fetchone():          # a second click does not start a second run
            raise HTTPException(409, "this import is already being classified")
        background.add_task(classify_job, imp_id, {"email": u["email"], "roles": u["roles"]},
                            d.get("engine", "ai") != "rules")
        return {"status": "classifying", "engine": "ai" if ai_on() and d.get("engine", "ai") != "rules" else "rules"}

    @app.get("/api/docs/overview")
    def overview(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        return LIB.overview(c)

    @app.get("/api/docs")
    def documents(*, status: str = "library", process: str = "", type: str = "", q: str = "",
                  import_id: int | None = None, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        rows = LIB.listing(c, status=status, process=process, doc_type=type, q=q, import_id=import_id)
        return [_iso(r) | {"batch_ok": K.batch_ok(r)} for r in rows]

    @app.post("/api/docs/confirm-batch")
    async def confirm_batch(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        ids = [int(i) for i in (await body(request)).get("ids", [])]
        return LIB.confirm_batch(c, u["email"], ids)

    def doc_view(c, doc: dict) -> dict:
        body_ = LIB.text(c, doc["id"])
        family = []
        if doc["number"]:
            family = c.execute("select id, number, title, revision, status, effective_date, approved_at from documents "
                               "where number = %s and status <> 'rejected' order by id", (doc["number"],)).fetchall()
        imp = c.execute("select id, label, created_by, created_at from doc_imports where id = %s",
                        (doc["import_id"],)).fetchone()
        same = c.execute("select id, original_name, path, status from documents where sha256 = %s and id <> %s "
                         "order by id", (doc["sha256"], doc["id"])).fetchall()
        return _iso(doc) | {
            "text": body_[:TEXT_SHOWN], "text_more": max(0, len(body_) - TEXT_SHOWN),
            "history": LIB.history(c, doc["id"]), "signatures": Q.signatures(c, "document", doc["id"]),
            "revisions": [_iso(r) for r in family], "import": _iso(imp) if imp else None,
            "same_file": same, "batch_ok": K.batch_ok(doc), "controlled": doc["doc_type"] in K.CONTROLLED,
            "involved": sorted(LIB.involved(c, doc)),
            "process_name": LIB.processes(c).get(doc["process"] or "", None)}

    @app.get("/api/docs/{doc_id}")
    def document(doc_id: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        return run(lambda: doc_view(c, LIB.get(c, doc_id)))

    @app.get("/api/docs/{doc_id}/file")
    def file(doc_id: int, inline: bool = False, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:view")
        doc = run(lambda: LIB.get(c, doc_id))
        p = F.path(doc["sha256"])
        if not p.exists():
            raise HTTPException(410, "the stored file is missing; restore it from a backup")
        show = inline and (doc["mime"] in ("application/pdf", "text/plain") or doc["mime"].startswith("image/"))
        return FileResponse(p, media_type=doc["mime"], filename=doc["original_name"],
                            content_disposition_type="inline" if show else "attachment",
                            headers={"x-content-type-options": "nosniff", "cache-control": "private, no-cache"})

    @app.post("/api/docs/{doc_id}/confirm")
    async def confirm(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        return doc_view(c, run(lambda: LIB.confirm(c, u["email"], doc_id, d.get("fields") or {})))

    @app.post("/api/docs/{doc_id}/reject")
    async def reject(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        return doc_view(c, run(lambda: LIB.reject(c, u["email"], doc_id, str(d.get("reason", "")))))

    @app.post("/api/docs/{doc_id}/edit")
    async def edit(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        return doc_view(c, run(lambda: LIB.edit(c, u["email"], doc_id, d.get("fields") or {})))

    @app.post("/api/docs/{doc_id}/submit")
    def submit(doc_id: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        return doc_view(c, run(lambda: LIB.submit(c, u["email"], doc_id)))

    @app.post("/api/docs/{doc_id}/send-back")
    async def send_back(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        return doc_view(c, run(lambda: LIB.send_back(c, u["email"], doc_id, str(d.get("reason", "")))))

    @app.post("/api/docs/{doc_id}/approve")
    async def approve(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        today = OA.today(company()[0])
        return doc_view(c, run(lambda: LIB.approve(c, u, doc_id, str(d.get("password", "")), today)))

    @app.post("/api/docs/{doc_id}/obsolete")
    async def make_obsolete(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        d = await body(request)
        return doc_view(c, run(lambda: LIB.obsolete(c, u["email"], doc_id, str(d.get("reason", "")))))

    @app.post("/api/docs/{doc_id}/revision", status_code=201)
    async def revision(doc_id: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "documents:edit")
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(400, "choose the file of the new revision")
        data = await up.read(F.MAX_BYTES + 1)
        return doc_view(c, run(lambda: LIB.new_revision(c, u["email"], doc_id, name=up.filename or "file", data=data,
                                                                 revision=str(form.get("revision") or ""))))
