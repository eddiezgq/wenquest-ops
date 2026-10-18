"""Hub service: health check, sign-in, and the workspace shell (docs/plan.md, Phase 1 items 3-4).

Environment:
    WQO_DB              PostgreSQL URL of the hub database
    WQO_COMPANY_FILE    path of company.yaml (mounted read-only)
    WQO_ERP_URL         ERPNext base URL inside the deployment (default http://erp-frontend:8080)
    WQO_ERP_SITE        ERPNext site name sent as Host header (default frontend)
    WQO_ERP_API_KEY / WQO_ERP_API_SECRET
    WQO_ERP_PUBLIC_URL  ERPNext address people open in the browser (e.g. https://erp.ops.example.com)
    WQO_SYNC_SECONDS    pull changes from ERPNext this often (default 300; 0 turns it off; ADR-0006)
    WQO_WEB_DIR         the built web workspace (web/dist); without it "/" shows a plain page
    WQO_FILES_DIR       the document library's file volume (default /data/files; ADR-0014)
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import os
import urllib.parse
from collections.abc import Callable

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import wqops
from wqops import company as C
from wqops.erp import ErpError
from wqops.hub import accounts as A
from wqops.hub import db as DB
from wqops.hub import drafts as D
from wqops.hub import erp_sso as S
from wqops.hub import oidc as O
from wqops.hub import permissions as P
from wqops.hub import sync as Y
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import api as OA
from wqops.hub.ont import project as OP

log = logging.getLogger("wqops.hub")

COOKIE = "wqo_session"


def check_db() -> str:
    url = os.environ.get("WQO_DB")
    if not url:
        return "not configured"
    try:
        with DB.connect(url) as conn:
            conn.execute("select 1")
        return "ok"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


def check_erp() -> str:
    from wqops.erp_setup import client_from_env  # noqa: PLC0415

    return "ok" if client_from_env().ping() else "error: no reply to ping"


def load_company() -> tuple[dict | None, str]:
    path = os.environ.get("WQO_COMPANY_FILE")
    if not path:
        return None, "not configured"
    try:
        return C.load(path), "ok"
    except (OSError, C.CompanyError) as exc:
        return None, f"error: {str(exc).splitlines()[0]}"


def _page(title: str, body: str) -> str:
    """Plain server pages (sign-in, the page without a web build) in Frappe's look (ADR-0013), no scripts."""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;"
            "justify-content:center;background:#f8f8f8;color:#383838;padding:2rem 1rem;"
            "font:14px/1.5 InterVar,Inter,-apple-system,'Segoe UI',system-ui,sans-serif}"
            "main{width:100%;max-width:26rem;background:#fff;border:1px solid #ededed;border-radius:12px;"
            "padding:2rem;box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.04)}"
            "h1{font-size:13px;font-weight:500;color:#7c7c7c;margin:0 0 .25rem}"
            "h2{font-size:20px;font-weight:600;color:#171717;margin:0 0 1.25rem}"
            "label{display:block;margin:.9rem 0 .35rem;font-size:13px;color:#525252}"
            "input{width:100%;height:36px;padding:0 .7rem;font:inherit;color:#171717;background:#f3f3f3;"
            "border:1px solid #f3f3f3;border-radius:8px;outline:none}"
            "input:focus{background:#fff;border-color:#c7c7c7;box-shadow:0 0 0 2px #e2e2e2}"
            "button{width:100%;margin-top:1.4rem;height:36px;font:inherit;font-weight:500;color:#fff;"
            "background:#171717;border:0;border-radius:8px;cursor:pointer}button:hover{background:#383838}"
            "a{color:#171717}a.sso{display:block;text-align:center;padding:.5rem;border:1px solid #e2e2e2;"
            "border-radius:8px;text-decoration:none;font-weight:500}a.sso:hover{background:#f8f8f8}"
            ".err{color:#c71a1a;background:#fff5f5;border:1px solid #fbdada;border-radius:6px;padding:.5rem .7rem}"
            ".muted{color:#7c7c7c}small{font-size:12px}"
            "code{background:#f3f3f3;padding:0 .3rem;border-radius:4px}</style></head>"
            f"<body><main>{body}</main></body></html>")


def create_app(checks: dict[str, Callable[[], str]] | None = None,  # noqa: PLR0915 - routes are defined inside
               company: Callable[[], tuple[dict | None, str]] = load_company,
               db_url: str | None = None, oidc_http=None, erp=None, *, sync_seconds: float = 0,
               web_dir: str | None = None, ai=None) -> FastAPI:
    """``sync_seconds`` > 0 pulls ERPNext changes in the background that often (the deployed app reads
    WQO_SYNC_SECONDS; tests leave it off)."""
    checks = checks if checks is not None else {"database": check_db, "erpnext": check_erp}
    db_url = db_url if db_url is not None else os.environ.get("WQO_DB")
    if ai is None:
        from wqops.hub.ai import llm as L  # noqa: PLC0415

        ai = L.Anthropic()
    ai_model = ai

    def sync_now(trigger: str) -> dict:
        """Pull ERPNext changes, then bring the ops hub objects up to date (ADR-0006, ADR-0007)."""
        with DB.connect(db_url) as c:
            out = Y.run(c, erp_client(), trigger=trigger)
            m = company()[0]
            out["objects"] = OP.project(c, manifest=m)
            from wqops.hub.quality import auto as QAUTO  # noqa: PLC0415

            out["ncrs_opened"] = QAUTO.open_for_rejected(c, OA.today(m))
            if out["ncrs_opened"]:
                OP.project(c, manifest=m)
            out["anomalies"] = AN.detect(c, OA.today(m))
            return out

    def brief_if_due() -> None:
        from wqops.hub.ai import brief as BR  # noqa: PLC0415

        m = company()[0]
        with DB.connect(db_url) as c:
            day = BR.due(c, m)
            if day:
                BR.generate(c, day, m, ai_model)
                log.info("daily brief for %s made", day)

    def qms_if_due() -> None:
        from wqops.hub.docs import library as LIB  # noqa: PLC0415
        from wqops.hub.system import qms as QMS  # noqa: PLC0415

        with DB.connect(db_url) as c:
            m = company()[0]
            if LIB.take_effect_due(c, OA.today(m)):          # revisions planned for today take effect first (17d)
                log.info("planned document revisions took effect")
            done = QMS.evaluate_if_due(c, OA.today(m), m["company"]["timezone"] if m else "UTC")
            if done:
                log.info("quality system evaluated: %s", ", ".join(done))

    async def sync_loop():
        await asyncio.sleep(min(15.0, sync_seconds))
        while True:
            try:
                out = await asyncio.to_thread(sync_now, "schedule")
                log.info("ERPNext sync: %s", out["events"])
            except Y.SyncBusy:
                pass
            except Exception:  # keep the loop alive; the run log has the error
                log.exception("ERPNext sync failed")
            try:
                await asyncio.to_thread(brief_if_due)
            except Exception:
                log.exception("daily brief failed")
            try:
                await asyncio.to_thread(qms_if_due)
            except Exception:
                log.exception("daily quality system evaluation failed")
            await asyncio.sleep(sync_seconds)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = None
        if db_url:
            with DB.connect(db_url) as c:
                DB.migrate(c)
                m, _state = company()
                if m:
                    A.sync(c, m)
                OP.project(c, manifest=m)
                AN.detect(c, OA.today(m))
            from wqops.hub.docs import api as DOCAPI  # noqa: PLC0415

            DOCAPI.resume(db_url)
            if sync_seconds > 0:
                task = asyncio.create_task(sync_loop())
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="WenQuest Ops", version=wqops.__version__, lifespan=lifespan)

    def conn():
        if not db_url:
            raise HTTPException(503, "the hub database is not configured")
        c = DB.connect(db_url)
        try:
            yield c
        finally:
            c.close()

    def user_or_none(request: Request, c=Depends(conn)) -> dict | None:
        return A.session_user(c, request.cookies.get(COOKIE))

    def current_user(u=Depends(user_or_none)) -> dict:
        if u is None:
            raise HTTPException(401, "sign in first")
        return u

    def require(permission: str):
        def dep(u=Depends(current_user)) -> dict:
            if not P.allows(u["roles"], permission):
                raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[permission]}")
            return u
        return dep

    def secure(request: Request) -> bool:
        return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"

    def company_name() -> tuple[str, bool]:
        m, _ = company()
        return (m["company"]["name"], bool(m.get("demo"))) if m else ("WenQuest Ops", False)

    @app.get("/api/health")
    def health():
        """200 when every check is ok, 503 otherwise (for installers, status.sh and monitoring tools)."""
        _, cstate = company()
        result = {name: fn() for name, fn in checks.items()}
        result["company_manifest"] = cstate
        ok = all(v == "ok" for v in result.values())
        return JSONResponse({"ok": ok, "version": wqops.__version__, "checks": result}, status_code=200 if ok else 503)

    def erp_client():
        if erp is not None:
            return erp
        from wqops.erp_setup import client_from_env  # noqa: PLC0415

        return client_from_env()

    def safe_next(url: str | None) -> str | None:
        """Only same-site paths, so a crafted link cannot send people elsewhere after signing in."""
        return url if url and url.startswith("/") and not url.startswith("//") and "\\" not in url else None

    def oidc_client(provider: str) -> O.Client:
        p = O.providers().get(provider)
        if p is None:
            raise HTTPException(404, f"sign-in with {provider} is not set up")
        return O.Client(p, oidc_http)

    def public_url(request: Request) -> str:
        return os.environ.get("WQO_PUBLIC_URL") or str(request.base_url).rstrip("/")

    def start_session(request: Request, c, u: dict, method: str, resp):
        token = A.create_session(c, u, method)
        resp.set_cookie(COOKIE, token, max_age=A.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=secure(request), path="/")
        return resp

    @app.get("/api/auth/methods")
    def methods():
        return {"password": True, "providers": [{"name": p.name, "label": p.label} for p in O.providers().values()]}

    @app.get("/auth/oidc/{provider}/start")
    def oidc_start(provider: str, request: Request, next: str = "", c=Depends(conn)):
        cl = oidc_client(provider)
        url = cl.start(c, O.redirect_uri(public_url(request), provider), safe_next(next))
        return RedirectResponse(url, status_code=303)

    @app.get("/auth/oidc/{provider}/callback")
    def oidc_callback(provider: str, request: Request, *, code: str = "", state: str = "", error: str = "",
                      c=Depends(conn)):
        cl = oidc_client(provider)

        def fail(msg: str):
            A.event(c, None, "login_failed", f"{provider}: {msg}")
            return RedirectResponse(f"/login?error={urllib.parse.quote(msg)}", status_code=303)

        if error:
            return fail(f"{cl.p.label} sign-in was cancelled or refused ({error})")
        try:
            email, nxt = cl.finish(c, state, code, O.redirect_uri(public_url(request), provider))
        except (O.OidcError, httpx.HTTPError) as exc:
            return fail(str(exc))
        u = A.get(c, email)
        if u is None or not u["active"]:
            return fail(f"{email} is not on the list of people for this company; ask the owner to add you")
        return start_session(request, c, u, f"oidc:{provider}", RedirectResponse(nxt or "/", status_code=303))

    @app.post("/api/login")
    async def login(request: Request, c=Depends(conn)):
        is_form = "form" in request.headers.get("content-type", "")
        data = dict(await request.form()) if is_form else await request.json()
        try:
            u = A.authenticate(c, str(data.get("email", "")), str(data.get("password", "")))
        except A.AccountError as exc:
            if is_form:
                return RedirectResponse(f"/login?error={urllib.parse.quote(str(exc))}", status_code=303)
            raise HTTPException(401, str(exc)) from exc
        resp = RedirectResponse(safe_next(str(data.get("next") or "")) or "/", status_code=303) if is_form \
            else JSONResponse(A.public(u))
        return start_session(request, c, u, "password", resp)

    @app.post("/api/logout")
    def logout(request: Request, c=Depends(conn)):
        A.end_session(c, request.cookies.get(COOKIE))
        resp = RedirectResponse("/login", status_code=303) if "form" in request.headers.get("content-type", "") \
            else JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    def sso_secret() -> str:
        return os.environ.get("WQO_ERP_SSO_SECRET", "")

    @app.get("/api/oauth/authorize")
    def oauth_authorize(request: Request, *, client_id: str = "", redirect_uri: str = "", state: str = "",
                        u=Depends(user_or_none), c=Depends(conn)):
        if client_id != S.CLIENT_ID:
            raise HTTPException(400, "unknown client")
        try:
            S.check_redirect(redirect_uri, os.environ.get("WQO_ERP_PUBLIC_URL", ""))
        except S.SsoError as exc:
            raise HTTPException(400, str(exc)) from exc
        if u is None:
            here = request.url.path + "?" + request.url.query
            return RedirectResponse("/login?next=" + urllib.parse.quote(here), status_code=303)
        try:
            S.ensure_erp_user(erp_client(), u)
        except (ErpError, httpx.HTTPError) as exc:
            raise HTTPException(502, f"could not prepare your ERPNext account: {exc}") from exc
        code = S.issue_code(c, u, redirect_uri)
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}{urllib.parse.urlencode({'code': code, 'state': state})}",
                                status_code=303)

    @app.post("/api/oauth/token")
    async def oauth_token(request: Request, c=Depends(conn)):
        f = dict(await request.form())
        cid, csec = f.get("client_id", ""), f.get("client_secret", "")
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("basic "):
            import base64  # noqa: PLC0415

            cid, _, csec = base64.b64decode(auth[6:]).decode().partition(":")
        try:
            token = S.exchange(c, str(f.get("code", "")), client_id=str(cid), client_secret=str(csec),
                               redirect_uri=str(f.get("redirect_uri", "")), secret=sso_secret())
        except S.SsoError as exc:
            return JSONResponse({"error": "invalid_grant", "error_description": str(exc)}, status_code=400)
        return {"access_token": token, "token_type": "Bearer", "expires_in": S.TOKEN_SECONDS}

    @app.get("/api/oauth/userinfo")
    def oauth_userinfo(request: Request, c=Depends(conn)):
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("access_token", "")
        try:
            return S.userinfo(c, token)
        except S.SsoError as exc:
            raise HTTPException(401, str(exc)) from exc

    @app.get("/api/me")
    def me(u=Depends(current_user)):
        return A.public(u)

    @app.get("/api/users")
    def users(_=Depends(require("users:view")), c=Depends(conn)):
        return A.people(c)

    @app.post("/api/users/password")
    async def set_password(request: Request, u=Depends(current_user), c=Depends(conn)):
        """Change your own password, or (users:manage) someone else's."""
        data = await request.json()
        email = str(data.get("email") or u["email"]).lower()
        if email != u["email"] and not P.allows(u["roles"], "users:manage"):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS['users:manage']}")
        if email == u["email"] and u["password_hash"] and not A.check_password(str(data.get("current", "")),
                                                                                u["password_hash"]):
            raise HTTPException(400, "current password is wrong")
        try:
            A.set_password(c, email, str(data.get("password", "")), by=u["email"])
        except A.AccountError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    OA.mount(app, conn, current_user)
    OA.mount_dashboard(app, conn, current_user, company)
    OA.mount_anomalies(app, conn, current_user, company)
    from wqops.hub.ai import api as AIA  # noqa: PLC0415

    AIA.mount(app, conn, current_user, company, ai_model, db_url)
    from wqops.hub.quality import api as QA  # noqa: PLC0415

    QA.mount(app, conn, current_user, company)
    from wqops.hub.quality import iqc_api as IQA  # noqa: PLC0415

    IQA.mount(app, conn, current_user, company)
    from wqops.hub.quality import asl_api as ASLA  # noqa: PLC0415

    ASLA.mount(app, conn, current_user, company)
    from wqops.hub.quality import complaints_api as CMPA  # noqa: PLC0415

    CMPA.mount(app, conn, current_user, company)
    from wqops.hub.quality import calibration_api as CALA  # noqa: PLC0415

    CALA.mount(app, conn, current_user, company)
    from wqops.hub.quality import change_api as CHGA  # noqa: PLC0415

    CHGA.mount(app, conn, current_user, company)
    from wqops.hub.quality import risk_api as RSKA  # noqa: PLC0415

    RSKA.mount(app, conn, current_user, company)
    from wqops.hub.quality import production_api as PRDA  # noqa: PLC0415

    PRDA.mount(app, conn, current_user, company)
    from wqops.hub.quality import recall_api as RCA  # noqa: PLC0415

    RCA.mount(app, conn, current_user, company)
    from wqops.hub.quality import review_api as MRA  # noqa: PLC0415

    MRA.mount(app, conn, current_user, company)
    from wqops.hub import udi_api as UDA  # noqa: PLC0415

    UDA.mount(app, conn, current_user, company)
    from wqops.hub.quality import meas_api as MEA  # noqa: PLC0415

    MEA.mount(app, conn, current_user, company)
    from wqops.hub.quality import tools_api as TLA  # noqa: PLC0415

    TLA.mount(app, conn, current_user, company)
    from wqops.hub import integration_api as IGA  # noqa: PLC0415

    IGA.mount(app, conn, current_user, company)
    from wqops.hub import help_api as HA  # noqa: PLC0415

    HA.mount(app, conn, current_user)
    from wqops.hub.docs import api as DA  # noqa: PLC0415

    DA.mount(app, conn, current_user, company, ai_model, db_url)
    from wqops.hub.docs import ledger_api as LA  # noqa: PLC0415

    LA.mount(app, conn, current_user, company, ai_model, db_url, erp_client=erp_client)
    from wqops.hub.quality import proposal_api as PA  # noqa: PLC0415

    PA.mount(app, conn, current_user, company, ai_model, db_url)
    from wqops.hub.system import api as SA  # noqa: PLC0415

    SA.mount(app, conn, current_user, company, ai_model, db_url)
    from wqops.hub.quality import causes_api as CSA  # noqa: PLC0415

    CSA.mount(app, conn, current_user, company, ai_model, db_url)
    from wqops.hub.quality import fmea_api as FMA  # noqa: PLC0415

    FMA.mount(app, conn, current_user, company, ai_model, db_url)

    @app.get("/api/workspace")
    def workspace(u=Depends(current_user)):
        """What the web workspace needs to start: who is signed in, the company, where ERPNext is."""
        m, _ = company()
        c = (m or {}).get("company", {})
        return {"company": c.get("name", "WenQuest Ops"), "demo": bool(m and m.get("demo")),
                "currency": c.get("currency", "USD"), "timezone": c.get("timezone", "UTC"),
                "erp_url": os.environ.get("WQO_ERP_PUBLIC_URL"), "user": A.public(u), "version": wqops.__version__,
                "may": [P.PERMISSIONS[p] for p in sorted(P.of(u["roles"]))]}

    @app.get("/api/sync/status")
    def sync_status(_=Depends(require("dashboard:view")), c=Depends(conn)):
        return Y.status(c)

    @app.post("/api/sync/run")
    async def sync_run(u=Depends(require("settings:edit"))):
        try:
            return await asyncio.to_thread(sync_now, f"person:{u['email']}")
        except Y.SyncBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ErpError, httpx.HTTPError) as exc:
            raise HTTPException(502, f"ERPNext did not answer as expected: {exc}") from exc

    def draft_out(d: dict) -> dict:
        base = os.environ.get("WQO_ERP_PUBLIC_URL")
        if base and d["erp_name"]:
            d["erp_url"] = D.erp_link(base, d["doctype"], d["erp_name"])
        return d

    def draft_call(fn):
        try:
            return draft_out(fn())
        except D.NotAllowed as exc:
            raise HTTPException(403, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "no such draft") from exc
        except D.Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except D.DraftError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ErpError, httpx.HTTPError) as exc:
            raise HTTPException(502, f"ERPNext did not accept the draft: {exc}") from exc

    @app.post("/api/erp/drafts", status_code=201)
    async def propose_draft(request: Request, u=Depends(current_user), c=Depends(conn)):
        """Propose a draft (ADR-0006). Nothing is written to ERPNext until someone confirms it."""
        data = await request.json()
        return draft_call(lambda: D.propose(c, u, str(data.get("doctype", "")), data.get("payload"),
                                            summary=str(data.get("summary", ""))))

    @app.get("/api/erp/drafts")
    def list_drafts(status: str = "", u=Depends(current_user), c=Depends(conn)):
        from wqops.hub.quality import asl as ASL  # noqa: PLC0415

        out = [draft_out(d) for d in D.visible(c, u, status or None)]
        day = OA.today(company()[0])
        for d in out:     # a purchase order for an item the supplier is not approved for says so (17c)
            if d["doctype"] == "Purchase Order" and d["status"] in ("pending", "failed"):
                p = d["payload"] if isinstance(d["payload"], dict) else {}
                lines = p.get("items") if isinstance(p.get("items"), list) else []
                d["asl"] = ASL.check_lines(c, str(p.get("supplier") or "") or None,
                                           [str(i["item_code"]) for i in lines if isinstance(i, dict)
                                            and i.get("item_code")], day)
        return out

    @app.post("/api/erp/drafts/{draft_id}/confirm")
    async def confirm_draft(draft_id: int, u=Depends(current_user), c=Depends(conn)):
        return await asyncio.to_thread(draft_call, lambda: D.confirm(c, u, draft_id, erp_client()))

    @app.post("/api/erp/drafts/{draft_id}/reject")
    async def reject_draft(draft_id: int, request: Request, u=Depends(current_user), c=Depends(conn)):
        body = await request.body()
        reason = str((await request.json()).get("reason", "")) if body else ""
        return draft_call(lambda: D.reject(c, u, draft_id, reason))

    @app.get("/login", response_class=HTMLResponse)
    def login_page(error: str = "", next: str = ""):
        name, demo = company_name()
        err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
        tag = " <small class='muted'>(fictional demo company)</small>" if demo else ""
        nxt = safe_next(next)
        q = f"?next={urllib.parse.quote(nxt)}" if nxt else ""
        sso = "".join(f"<p><a class='sso' href='/auth/oidc/{p.name}/start{q}'>"
                      f"Sign in with {html.escape(p.label)}</a></p>" for p in O.providers().values())
        hidden = f"<input type='hidden' name='next' value='{html.escape(nxt)}'>" if nxt else ""
        if sso:
            sso += "<p class='muted'>or with a password:</p>"
        return _page(f"Sign in - {name}", f"<h1>{html.escape(name)}{tag}</h1><h2>Sign in to WenQuest Ops</h2>{err}{sso}"
                     f"<form method='post' action='/api/login'>{hidden}"
                     "<label for='email'>Email</label><input id='email' name='email' type='email' required autofocus>"
                     "<label for='password'>Password</label>"
                     "<input id='password' name='password' type='password' required>"
                     "<button type='submit'>Sign in</button></form>")

    web = web_dir if web_dir is not None else os.environ.get("WQO_WEB_DIR", "")
    index = os.path.join(web, "index.html") if web else ""
    has_web = bool(index) and os.path.isfile(index)
    if has_web:
        app.mount("/assets", StaticFiles(directory=os.path.join(web, "assets")), name="assets")

    def spa(request: Request, u):
        if u is None:
            return RedirectResponse("/login?next=" + urllib.parse.quote(request.url.path), status_code=303)
        return FileResponse(index, headers={"cache-control": "no-cache"})

    def spa_page(request: Request, u=Depends(user_or_none)):
        return spa(request, u)

    if has_web:
        for path in ("/objects", "/o/{rest:path}", "/anomalies", "/anomalies/{rest:path}", "/drafts", "/assistant",
                     "/quality", "/quality/{rest:path}", "/help", "/help/{rest:path}", "/account", "/people",
                     "/documents", "/documents/{rest:path}", "/system", "/system/{rest:path}", "/wall", "/scan",
                     "/integrations"):
            app.add_api_route(path, spa_page, methods=["GET"], include_in_schema=False)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, u=Depends(user_or_none)):
        if u is None:
            return RedirectResponse("/login", status_code=303)
        if has_web:
            return spa(request, u)
        name, demo = company_name()
        tag = " <small class='muted'>(fictional demo company)</small>" if demo else ""
        roles = ", ".join(P_LABEL.get(r, r) for r in u["roles"])
        erp_url = os.environ.get("WQO_ERP_PUBLIC_URL")
        erp_link = (f"<p><a href='{html.escape(erp_url)}/login'>Open ERPNext</a> "
                    "(choose “Login with WenQuest Ops”)</p>") if erp_url else ""
        perms = "".join(f"<li>{html.escape(P.PERMISSIONS[p])}</li>" for p in sorted(P.of(u["roles"])))
        return _page(f"{name} - WenQuest Ops",
                     f"<h1>{html.escape(name)}{tag}</h1><p>Signed in as <b>{html.escape(u['name'])}</b> "
                     f"({html.escape(u['email'])}) - {html.escape(roles)}</p>{erp_link}"
                     f"<h3>What you can do</h3><ul>{perms}</ul>"
                     "<p class='muted'>The workspace (ops hub, AI assistant, quality) arrives in the next steps of "
                     "Phase 1.</p><form method='post' action='/api/logout'><button>Sign out</button></form>"
                     f"<p class='muted'>WenQuest Ops {wqops.__version__}</p>")

    return app


P_LABEL = C.ROLE_LABELS
app = create_app(sync_seconds=float(os.environ.get("WQO_SYNC_SECONDS", "300")))
