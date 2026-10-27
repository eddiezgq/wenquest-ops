"""Sign in with Microsoft 365 (Entra ID) or Google Workspace: OpenID Connect, authorization code + PKCE (ADR-0005).

Configure with environment variables (only configured providers are offered):

    WQO_PUBLIC_URL                      https://ops.example.com (used for the redirect URI)
    WQO_OIDC_MICROSOFT_TENANT           the directory (tenant) ID - one organization only
    WQO_OIDC_MICROSOFT_CLIENT_ID / WQO_OIDC_MICROSOFT_CLIENT_SECRET
    WQO_OIDC_GOOGLE_CLIENT_ID / WQO_OIDC_GOOGLE_CLIENT_SECRET
    WQO_OIDC_GOOGLE_DOMAIN              optional: only accept accounts of this Google Workspace domain

Redirect URI to register with the provider: <WQO_PUBLIC_URL>/auth/oidc/<microsoft|google>/callback

Only people in the company manifest can sign in; the email from the identity provider must match theirs.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
import secrets
import urllib.parse
from dataclasses import dataclass

import httpx
import jwt

from wqops.i18n import say

PENDING_MINUTES = 10
LEEWAY_S = 60
LABELS = {"microsoft": "Microsoft 365", "google": "Google"}


class OidcError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    issuer: str
    client_id: str
    client_secret: str
    hosted_domain: str | None = None

    @property
    def label(self) -> str:
        return LABELS[self.name]


def providers(env=None) -> dict[str, Provider]:
    env = os.environ if env is None else env
    out = {}
    tenant = env.get("WQO_OIDC_MICROSOFT_TENANT")
    if tenant and env.get("WQO_OIDC_MICROSOFT_CLIENT_ID") and env.get("WQO_OIDC_MICROSOFT_CLIENT_SECRET"):
        out["microsoft"] = Provider("microsoft", f"https://login.microsoftonline.com/{tenant}/v2.0",
                                    env["WQO_OIDC_MICROSOFT_CLIENT_ID"], env["WQO_OIDC_MICROSOFT_CLIENT_SECRET"])
    if env.get("WQO_OIDC_GOOGLE_CLIENT_ID") and env.get("WQO_OIDC_GOOGLE_CLIENT_SECRET"):
        out["google"] = Provider("google", "https://accounts.google.com", env["WQO_OIDC_GOOGLE_CLIENT_ID"],
                                 env["WQO_OIDC_GOOGLE_CLIENT_SECRET"], env.get("WQO_OIDC_GOOGLE_DOMAIN") or None)
    return out


def redirect_uri(public_url: str, provider: str) -> str:
    return f"{public_url.rstrip('/')}/auth/oidc/{provider}/callback"


class Client:
    """Talks to an identity provider. ``http`` is injectable for tests."""

    def __init__(self, provider: Provider, http: httpx.Client | None = None):
        self.p = provider
        self.http = http or httpx.Client(timeout=15)
        self._meta: dict | None = None

    def meta(self) -> dict:
        if self._meta is None:
            r = self.http.get(f"{self.p.issuer}/.well-known/openid-configuration")
            r.raise_for_status()
            self._meta = r.json()
        return self._meta

    def start(self, conn, redirect: str, next_url: str | None = None) -> str:
        """Record a pending sign-in and return the URL to send the browser to."""
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        conn.execute("delete from oidc_pending where created_at < now() - make_interval(mins => %s)",
                     (PENDING_MINUTES,))
        conn.execute("insert into oidc_pending (state, provider, nonce, verifier, next) values (%s, %s, %s, %s, %s)",
                     (state, self.p.name, nonce, verifier, next_url))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        q = {"client_id": self.p.client_id, "response_type": "code", "redirect_uri": redirect,
             "scope": "openid email profile", "state": state, "nonce": nonce,
             "code_challenge": challenge, "code_challenge_method": "S256"}
        if self.p.hosted_domain:
            q["hd"] = self.p.hosted_domain
        return f"{self.meta()['authorization_endpoint']}?{urllib.parse.urlencode(q)}"

    def finish(self, conn, state: str, code: str, redirect: str,
               now: dt.datetime | None = None) -> tuple[str, str | None]:
        """Exchange the code, verify the ID token; return the person's email (lower-case) and where to go next."""
        row = conn.execute("delete from oidc_pending where state=%s and provider=%s returning *",
                           (state or "", self.p.name)).fetchone()
        now = now or dt.datetime.now(dt.UTC)
        if row is None or row["created_at"] < now - dt.timedelta(minutes=PENDING_MINUTES):
            raise OidcError(say("this sign-in link has expired or was already used; start again"))
        r = self.http.post(self.meta()["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
            "client_id": self.p.client_id, "client_secret": self.p.client_secret, "code_verifier": row["verifier"]})
        if r.status_code != 200:
            raise OidcError(say("{label} did not accept the sign-in ({status_code})",
                                label=self.p.label, status_code=r.status_code))
        token = r.json().get("id_token")
        if not token:
            raise OidcError(say("{label} returned no ID token", label=self.p.label))
        claims = self.verify(token, now)
        if claims.get("nonce") != row["nonce"]:
            raise OidcError(say("the sign-in response does not match this request (nonce)"))
        return self.email(claims), row.get("next")

    def verify(self, token: str, now: dt.datetime) -> dict:
        jwks = jwt.PyJWKClient(self.meta()["jwks_uri"])
        jwks.fetch_data = lambda: self.http.get(self.meta()["jwks_uri"]).json()  # use the injectable client
        try:
            key = jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.p.client_id, issuer=self.p.issuer,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"], "verify_exp": False,
                                         "verify_iat": False})
        except jwt.PyJWTError as exc:
            raise OidcError(say("the ID token is not valid: {exc}", exc=exc)) from exc
        t = now.timestamp()
        if claims["exp"] < t - LEEWAY_S or claims["iat"] > t + LEEWAY_S:
            raise OidcError(say("the ID token has expired or is not valid yet"))
        return claims

    def email(self, claims: dict) -> str:
        if self.p.name == "google":
            if not claims.get("email") or claims.get("email_verified") is not True:
                raise OidcError(say("Google did not confirm this email address"))
            if self.p.hosted_domain and claims.get("hd") != self.p.hosted_domain:
                raise OidcError(say("only {hosted_domain} accounts can sign in", hosted_domain=self.p.hosted_domain))
            return claims["email"].lower()
        # Microsoft: accounts of the one configured tenant (the issuer check above); the tenant manages them
        email = claims.get("email") or claims.get("preferred_username")
        if not email or "@" not in email:
            raise OidcError(say("Microsoft returned no email address for this account"))
        return email.lower()
