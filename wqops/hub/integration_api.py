"""The interface for machines and other systems (ADR-0020, 20d). Machines call /api/integration/v1/ with their own
access token (Authorization: Bearer wqo_...); every call is logged. People manage tokens (integrations:manage) and
decide what machines sent (quality:edit, signed)."""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from wqops.hub import integration as IG
from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.quality import records as Q
from wqops.i18n import say

MAX_BODY = 1_000_000


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route after another
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}", PERMISSIONS=P.PERMISSIONS[perm]))

    def run(fn):
        try:
            return fn()
        except (IG.IntegrationError, Q.QualityError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, say("not found")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    def has_nul(v) -> bool:
        if isinstance(v, str):
            return "\x00" in v
        if isinstance(v, dict):
            return any(has_nul(k) or has_nul(x) for k, x in v.items())
        return isinstance(v, list) and any(has_nul(x) for x in v)

    async def body(request: Request) -> dict:
        """The JSON body, read only up to 1 MB."""
        size = request.headers.get("content-length", "")
        if size.isdigit() and int(size) > MAX_BODY:
            raise HTTPException(413, say("the request is larger than 1 MB"))
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY:
                raise HTTPException(413, say("the request is larger than 1 MB"))
        try:
            d = json.loads(bytes(raw) or b"{}")
        except (ValueError, RecursionError) as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        if has_nul(d):
            raise HTTPException(400, say("the request holds a NUL character"))
        return d if isinstance(d, dict) else {}

    # ---------------------------------------------------------------- machines

    async def machine(request: Request, scope: str, c, fn):
        """Check the token and its scope, run the call, log it with its status."""
        auth = request.headers.get("authorization", "")
        tok = IG.authenticate(c, auth[7:].strip() if auth[:7].lower() == "bearer " else None)
        path = request.url.path
        if tok is None:
            IG.called(c, None, request.method, path, 401)
            return JSONResponse({"detail": "a valid access token is needed (Authorization: Bearer wqo_...)"}, 401)
        if scope and scope not in tok["scopes"]:
            IG.called(c, tok["id"], request.method, path, 403)
            return JSONResponse({"detail": f"this token may not: {IG.SCOPES[scope]}"}, 403)
        try:
            out = await fn(tok)
            status = 202 if request.method == "POST" else 200
        except HTTPException as exc:
            IG.called(c, tok["id"], request.method, path, exc.status_code)
            return JSONResponse({"detail": exc.detail}, exc.status_code)
        except IG.IntegrationError as exc:
            IG.called(c, tok["id"], request.method, path, 422)
            return JSONResponse({"detail": str(exc)}, 422)
        except Exception:
            IG.called(c, tok["id"], request.method, path, 500)
            raise
        IG.called(c, tok["id"], request.method, path, status)
        return JSONResponse(out, status)

    @app.get("/api/integration/v1/whoami")
    async def whoami(request: Request, c=Depends(conn_dep)):
        async def go(tok):
            return {"name": tok["name"], "scopes": tok["scopes"]}
        return await machine(request, "", c, go)

    @app.post("/api/integration/v1/measurements")
    async def send_measurements(request: Request, c=Depends(conn_dep)):
        async def go(tok):
            return IG.receive_measurements(c, tok, await body(request))
        return await machine(request, "measurements:send", c, go)

    @app.post("/api/integration/v1/production-steps")
    async def send_step(request: Request, c=Depends(conn_dep)):
        async def go(tok):
            return IG.receive_step(c, tok, await body(request))
        return await machine(request, "production:send", c, go)

    @app.get("/api/integration/v1/events")
    async def read_events(request: Request, after: int = 0, limit: int = 100, c=Depends(conn_dep)):
        async def go(tok):
            if not 0 <= after < 2**63 or not 1 <= limit <= 500:
                raise HTTPException(400, say("after is an event id; limit is 1 to 500"))
            return IG.events(c, after, limit)
        return await machine(request, "events:read", c, go)

    # ---------------------------------------------------------------- people

    @app.get("/api/integrations/tokens")
    def list_tokens(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "integrations:manage")
        return {"tokens": IG.tokens(c), "scopes": IG.SCOPES}

    @app.post("/api/integrations/tokens", status_code=201)
    async def create_token(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "integrations:manage")
        d = await body(request)
        row, token = run(lambda: IG.new_token(c, u["email"], d.get("name"), d.get("scopes")))
        return row | {"token": token}

    @app.post("/api/integrations/tokens/{tid}/revoke")
    async def revoke_token(tid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "integrations:manage")
        d = await body(request)
        return run(lambda: IG.revoke(c, u["email"], tid, d.get("note") or ""))

    @app.get("/api/integrations/tokens/{tid}/calls")
    def token_calls(tid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "integrations:manage")
        return IG.calls(c, tid)

    @app.get("/api/integrations/inbox")
    def list_inbox(status: str = "pending", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        if status not in ("pending", "accepted", "rejected", "all"):
            raise HTTPException(400, say("status is pending, accepted, rejected or all"))
        return {"items": IG.inbox(c, status), "can_decide": P.allows(u["roles"], "quality:edit")}

    @app.get("/api/integrations/inbox/{iid}")
    def get_item(iid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return run(lambda: IG.item(c, iid))

    @app.post("/api/integrations/inbox/{iid}/accept")
    async def accept(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        return run(lambda: IG.accept(c, u, iid, str(d.get("password") or ""), seen=str(d.get("seen") or ""),
                                     today=OA.today(company()[0])))

    @app.post("/api/integrations/inbox/{iid}/reject")
    async def reject(iid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        return run(lambda: IG.reject(c, u["email"], iid, d.get("note")))
