"""Open ERPNext without signing in again (ADR-0005, Phase 1 item 4c).

WenQuest Ops is an OAuth2 provider; ERPNext's built-in social login ("Custom" provider) uses it:

    ERPNext login page -> "Login with WenQuest Ops" -> /api/oauth/authorize (needs a WenQuest Ops session; the ERPNext
    user and roles are brought up to date) -> one-time code back to ERPNext -> ERPNext's server exchanges it at
    /api/oauth/token (inside the deployment, http://hub:8100) -> /api/oauth/userinfo -> signed in as that person.

Adapted from the WenQuest digital factory, round 7 (freecad-ai-parts, factory/digital/hub/erp_sso.py).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from wqops.erp import ErpClient
from wqops.i18n import say

CLIENT_ID = "wenquest-ops-erp"
PROVIDER = "wenquest_ops"                      # ERPNext names the Social Login Key frappe.scrub("WenQuest Ops")
PROVIDER_LABEL = "WenQuest Ops"
CALLBACK_PATH = "/api/method/frappe.integrations.oauth2_logins.custom/" + PROVIDER
HUB_INTERNAL = "http://hub:8100"
CODE_SECONDS = 120
TOKEN_SECONDS = 300

# Standard ERPNext roles for each WenQuest Ops role
ERP_ROLES = {
    "owner": ["System Manager", "Accounts Manager", "Stock Manager", "Purchase Manager", "Sales Manager",
              "Quality Manager", "Item Manager"],
    "ops_manager": ["Stock Manager", "Purchase Manager", "Sales Manager", "Quality Manager", "Item Manager"],
    "warehouse": ["Stock User"],
    "purchasing": ["Purchase Manager", "Purchase User", "Stock User"],
    "sales": ["Sales User"],
    "quality": ["Quality Manager", "Stock User"],
    "ai_specialist": ["Stock User", "Sales User", "Purchase User"],
}


class SsoError(ValueError):
    pass


def erp_roles(roles) -> list[str]:
    out: set[str] = set()
    for r in roles or ():
        out.update(ERP_ROLES.get(r, []))
    return sorted(out)


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def social_login_key(public_url: str, secret: str) -> dict:
    """The Social Login Key document that makes ERPNext offer "Login with WenQuest Ops"."""
    return {"doctype": "Social Login Key", "provider_name": PROVIDER_LABEL, "social_login_provider": "Custom",
            "enable_social_login": 1, "client_id": CLIENT_ID, "client_secret": secret,
            "base_url": public_url.rstrip("/"), "custom_base_url": 1, "authorize_url": "/api/oauth/authorize",
            "access_token_url": HUB_INTERNAL + "/api/oauth/token", "api_endpoint": HUB_INTERNAL + "/api/oauth/userinfo",
            "redirect_url": CALLBACK_PATH, "user_id_property": "sub", "sign_ups": "Deny",
            "auth_url_data": '{"response_type": "code", "scope": "openid"}'}


def check_redirect(redirect_uri: str, erp_public_url: str) -> None:
    if redirect_uri != erp_public_url.rstrip("/") + CALLBACK_PATH:
        raise SsoError(say("unknown redirect address"))


def ensure_erp_user(erp: ErpClient, user: dict) -> str:
    """Create or update the person in ERPNext with the roles their WenQuest Ops roles map to."""
    first, _, last = user["name"].partition(" ")
    roles = [{"role": r} for r in erp_roles(user["roles"])]
    existing = erp.get("User", user["email"])
    if existing is None:
        erp.insert({"doctype": "User", "email": user["email"], "first_name": first, "last_name": last,
                    "enabled": 1, "send_welcome_email": 0, "user_type": "System User", "roles": roles})
        return "created"
    have = sorted(r["role"] for r in existing.get("roles", []) if r["role"] in {x for v in ERP_ROLES.values()
                                                                               for x in v})
    if have == [r["role"] for r in roles] and existing.get("enabled") == 1:
        return "unchanged"
    erp.update("User", user["email"], {"enabled": 1, "first_name": first, "last_name": last,
                                       "roles": [r for r in existing.get("roles", [])
                                                 if r["role"] not in {x for v in ERP_ROLES.values() for x in v}]
                                       + roles})
    return "updated"


def disable_erp_user(erp: ErpClient, email: str) -> bool:
    u = erp.get("User", email)
    if u is None or u.get("enabled") == 0:
        return False
    erp.update("User", email, {"enabled": 0})
    return True


def issue_code(conn, user: dict, redirect_uri: str) -> str:
    code = secrets.token_urlsafe(32)
    conn.execute("delete from oauth_codes where created_at < now() - make_interval(secs => %s)", (CODE_SECONDS,))
    conn.execute("insert into oauth_codes (code_hash, user_id, redirect_uri) values (%s, %s, %s)",
                 (_h(code), user["id"], redirect_uri))
    return code


def exchange(conn, code: str, *, client_id: str, client_secret: str, redirect_uri: str, secret: str,
             now: dt.datetime | None = None) -> str:
    """Trade a one-time code for a short-lived access token."""
    now = now or dt.datetime.now(dt.UTC)
    if client_id != CLIENT_ID or not secret or not hmac.compare_digest(client_secret or "", secret):
        raise SsoError(say("invalid client"))
    row = conn.execute("delete from oauth_codes where code_hash=%s returning *", (_h(code or ""),)).fetchone()
    if row is None or row["created_at"] < now - dt.timedelta(seconds=CODE_SECONDS):
        raise SsoError(say("invalid or expired code"))
    if row["redirect_uri"] != redirect_uri:
        raise SsoError(say("redirect address does not match"))
    token = secrets.token_urlsafe(32)
    conn.execute("insert into oauth_tokens (token_hash, user_id, expires_at) values (%s, %s, %s)",
                 (_h(token), row["user_id"], now + dt.timedelta(seconds=TOKEN_SECONDS)))
    return token


def userinfo(conn, token: str, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.UTC)
    u = conn.execute("select u.* from oauth_tokens t join users u on u.id = t.user_id "
                     "where t.token_hash=%s and t.expires_at > %s and u.active", (_h(token or ""), now)).fetchone()
    if u is None:
        raise SsoError(say("invalid or expired token"))
    first, _, last = u["name"].partition(" ")
    return {"sub": u["email"], "email": u["email"], "email_verified": True, "name": u["name"],
            "given_name": first, "family_name": last}
