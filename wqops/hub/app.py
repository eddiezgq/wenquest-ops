"""Hub service: health check, sign-in, and the workspace shell (docs/plan.md, Phase 1 items 3-4).

Environment:
    WQO_DB              PostgreSQL URL of the hub database
    WQO_COMPANY_FILE    path of company.yaml (mounted read-only)
    WQO_ERP_URL         ERPNext base URL inside the deployment (default http://erp-frontend:8080)
    WQO_ERP_SITE        ERPNext site name sent as Host header (default frontend)
    WQO_ERP_API_KEY / WQO_ERP_API_SECRET
    WQO_ERP_PUBLIC_URL  ERPNext address people open in the browser (e.g. https://erp.ops.example.com)
"""

from __future__ import annotations

import contextlib
import html
import os
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import wqops
from wqops import company as C
from wqops.hub import accounts as A
from wqops.hub import db as DB
from wqops.hub import permissions as P

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
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>body{font-family:system-ui,sans-serif;max-width:44rem;margin:3rem auto;padding:0 1rem;"
            "color:#1f2933}label{display:block;margin:.8rem 0 .2rem}"
            "input{width:100%;padding:.5rem;font-size:1rem;box-sizing:border-box}"
            "button{margin-top:1rem;padding:.55rem 1.2rem;font-size:1rem}.err{color:#b42318}.muted{color:#667085}"
            "code{background:#f2f4f7;padding:0 .3rem;border-radius:3px}</style></head>"
            f"<body>{body}</body></html>")


def create_app(checks: dict[str, Callable[[], str]] | None = None,  # noqa: PLR0915 - routes are defined inside
               company: Callable[[], tuple[dict | None, str]] = load_company,
               db_url: str | None = None) -> FastAPI:
    checks = checks if checks is not None else {"database": check_db, "erpnext": check_erp}
    db_url = db_url if db_url is not None else os.environ.get("WQO_DB")
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        if db_url:
            with DB.connect(db_url) as c:
                DB.migrate(c)
                m, _state = company()
                if m:
                    A.sync(c, m)
        yield

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

    @app.get("/api/auth/methods")
    def methods():
        return {"password": True}

    @app.post("/api/login")
    async def login(request: Request, c=Depends(conn)):
        is_form = "form" in request.headers.get("content-type", "")
        data = dict(await request.form()) if is_form else await request.json()
        try:
            u = A.authenticate(c, str(data.get("email", "")), str(data.get("password", "")))
        except A.AccountError as exc:
            if is_form:
                return RedirectResponse(f"/login?error={html.escape(str(exc))}", status_code=303)
            raise HTTPException(401, str(exc)) from exc
        token = A.create_session(c, u, "password")
        resp = RedirectResponse("/", status_code=303) if is_form else JSONResponse(A.public(u))
        resp.set_cookie(COOKIE, token, max_age=A.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=secure(request), path="/")
        return resp

    @app.post("/api/logout")
    def logout(request: Request, c=Depends(conn)):
        A.end_session(c, request.cookies.get(COOKIE))
        resp = RedirectResponse("/login", status_code=303) if "form" in request.headers.get("content-type", "") \
            else JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/api/me")
    def me(u=Depends(current_user)):
        return A.public(u)

    @app.get("/api/users")
    def users(_=Depends(require("users:view")), c=Depends(conn)):
        return [A.public(u) for u in c.execute("select * from users order by name").fetchall()]

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
            A.set_password(c, email, str(data.get("password", "")))
        except A.AccountError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(error: str = ""):
        name, demo = company_name()
        err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
        tag = " <small class='muted'>(fictional demo company)</small>" if demo else ""
        return _page(f"Sign in - {name}", f"<h1>{html.escape(name)}{tag}</h1><h2>Sign in to WenQuest Ops</h2>{err}"
                     "<form method='post' action='/api/login'>"
                     "<label for='email'>Email</label><input id='email' name='email' type='email' required autofocus>"
                     "<label for='password'>Password</label>"
                     "<input id='password' name='password' type='password' required>"
                     "<button type='submit'>Sign in</button></form>")

    @app.get("/", response_class=HTMLResponse)
    def home(u=Depends(user_or_none)):
        if u is None:
            return RedirectResponse("/login", status_code=303)
        name, demo = company_name()
        tag = " <small class='muted'>(fictional demo company)</small>" if demo else ""
        roles = ", ".join(P_LABEL.get(r, r) for r in u["roles"])
        erp = os.environ.get("WQO_ERP_PUBLIC_URL")
        erp_link = f"<p><a href='{html.escape(erp)}'>Open ERPNext</a></p>" if erp else ""
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
app = create_app()
