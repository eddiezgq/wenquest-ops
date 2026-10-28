"""Measurement files and control charts of the hub's readings (ADR-0020, 20c). Importing is quality:edit and signed
with the importer's password; the charts and the kept files are quality:view."""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import iqc as I
from wqops.hub.quality import meas_rules as MR
from wqops.hub.quality import measurements as ME
from wqops.hub.quality import records as Q
from wqops.i18n import say


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route after another
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.PERMISSIONS[perm]))

    def run(fn):
        try:
            return fn()
        except (ME.MeasurementError, MR.MeasError, I.IqcError, Q.QualityError, CAL.CalError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    def ident(v: int) -> int:
        if not 0 < v < 2**63:
            raise HTTPException(404, say("not found"))
        return v

    async def upload(request: Request) -> tuple[str, bytes, dict]:
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(400, say("choose the measurement file"))
        raw = await up.read(MR.MAX_BYTES + 1)
        if len(raw) > MR.MAX_BYTES:
            raise HTTPException(413, say("the file is larger than 5 MB"))
        opts: dict = {}
        if form.get("mapping"):
            try:
                m = json.loads(str(form.get("mapping")))
            except ValueError as exc:
                raise HTTPException(400, say("the matching is not JSON")) from exc
            if not isinstance(m, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in m.items()):
                raise HTTPException(400, say("the matching is feature -> characteristic"))
            opts["mapping"] = m
        for k in ("first_sample", "gauge_id"):
            v = str(form.get(k) or "").strip()
            if v:
                if not v.isdigit() or not 0 < int(v) < 2**31:
                    raise HTTPException(400, say("{k} is a number", k=say("upload field::" + k.replace("_", " "))))
                opts[k] = int(v)
        opts["password"] = str(form.get("password") or "")
        opts["seen"] = str(form.get("seen") or "")
        return (up.filename or "measurements.csv")[:200], raw, opts

    @app.post("/api/iqc/inspections/{iid}/measurements/preview")
    async def preview(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        name, raw, o = await upload(request)
        return run(lambda: ME.preview(c, ident(iid), name, raw, mapping=o.get("mapping"),
                                      first_sample=o.get("first_sample"), gauge_id=o.get("gauge_id")))

    @app.post("/api/iqc/inspections/{iid}/measurements", status_code=201)
    async def do_import(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        name, raw, o = await upload(request)
        return run(lambda: ME.import_file(c, u, ident(iid), name, raw, o["password"], seen=o["seen"],
                                          mapping=o.get("mapping"), first_sample=o.get("first_sample"),
                                          gauge_id=o.get("gauge_id"), today=OA.today(company()[0])))

    @app.get("/api/iqc/inspections/{iid}/measurements")
    def listing(iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return ME.imports(c, ident(iid))

    @app.get("/api/measurements/{mid}/file")
    def file(mid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        name, raw = run(lambda: ME.content(c, ident(mid)))
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        return Response(raw, media_type="application/octet-stream",
                        headers={"content-disposition": f'attachment; filename="{safe}"'})

    @app.get("/api/quality/measurements/parameters")
    def parameters(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return ME.parameters(c)

    @app.get("/api/quality/measurements/spc")
    def chart(source: str, item_code: str, parameter: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return run(lambda: ME.spc_for(c, source, item_code, parameter))
