"""Hub service (docs/plan.md, Phase 1 item 3: deployment).

Phase 1 item 3 only needs a health endpoint for installers and monitoring, and a landing page; later items add
accounts, sync, the ops hub, the AI assistant and quality.

Environment:
    WQO_DB              PostgreSQL URL of the hub database
    WQO_COMPANY_FILE    path of company.yaml (mounted read-only)
    WQO_ERP_URL         ERPNext base URL inside the deployment (default http://erp-frontend:8080)
    WQO_ERP_SITE        ERPNext site name sent as Host header (default frontend)
    WQO_ERP_API_KEY / WQO_ERP_API_SECRET
"""

from __future__ import annotations

import html
import os
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import wqops
from wqops import company as C


def check_db() -> str:
    url = os.environ.get("WQO_DB")
    if not url:
        return "not configured"
    try:
        import psycopg  # noqa: PLC0415

        with psycopg.connect(url, connect_timeout=5) as conn:
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


def create_app(checks: dict[str, Callable[[], str]] | None = None,
               company: Callable[[], tuple[dict | None, str]] = load_company) -> FastAPI:
    checks = checks if checks is not None else {"database": check_db, "erpnext": check_erp}
    app = FastAPI(title="WenQuest Ops", version=wqops.__version__)

    @app.get("/api/health")
    def health():
        """200 when every check is ok, 503 otherwise (for installers, status.sh and monitoring tools)."""
        _, cstate = company()
        result = {name: fn() for name, fn in checks.items()}
        result["company_manifest"] = cstate
        ok = all(v == "ok" for v in result.values())
        return JSONResponse({"ok": ok, "version": wqops.__version__, "checks": result}, status_code=200 if ok else 503)

    @app.get("/", response_class=HTMLResponse)
    def home():
        m, _ = company()
        name = html.escape(m["company"]["name"]) if m else "WenQuest Ops"
        demo = " <small>(fictional demo company)</small>" if m and m.get("demo") else ""
        return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{name} - WenQuest Ops</title>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'></head>"
                "<body style='font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem'>"
                f"<h1>{name}{demo}</h1><p>WenQuest Ops {wqops.__version__} is running.</p>"
                "<p>Sign-in and the workspace arrive in the next steps of Phase 1.</p>"
                "<p><a href='/api/health'>Health check</a></p></body></html>")

    return app


app = create_app()
