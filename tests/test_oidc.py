"""Sign in with Microsoft 365 / Google (ADR-0005). A fake identity provider; no network."""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from wqops import company as C
from wqops.hub import oidc as O
from wqops.hub.app import create_app

TENANT = "11111111-2222-3333-4444-555555555555"
ISS = {"microsoft": f"https://login.microsoftonline.com/{TENANT}/v2.0", "google": "https://accounts.google.com"}


class FakeIdP:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.claims: dict = {}
        self.sign_with_other = False
        self.codes: dict[str, str] = {}
        self.last_token_request: dict = {}

    def jwk(self):
        j = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {**j, "kid": "k1", "use": "sig", "alg": "RS256"}

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        for name, iss in ISS.items():
            if url == f"{iss}/.well-known/openid-configuration":
                return httpx.Response(200, json={"issuer": iss, "authorization_endpoint": f"https://idp/{name}/auth",
                                                 "token_endpoint": f"https://idp/{name}/token",
                                                 "jwks_uri": f"https://idp/{name}/keys"})
        if url.endswith("/keys"):
            return httpx.Response(200, json={"keys": [self.jwk()]})
        if url.endswith("/token"):
            form = dict(urllib.parse.parse_qsl(req.content.decode()))
            self.last_token_request = form
            if form.get("code") != "good-code":
                return httpx.Response(400, json={"error": "invalid_grant"})
            key = self.other if self.sign_with_other else self.key
            tok = jwt.encode(self.claims, key, algorithm="RS256", headers={"kid": "k1"})
            return httpx.Response(200, json={"id_token": tok, "access_token": "x"})
        return httpx.Response(404)


ENV = {"WQO_PUBLIC_URL": "https://ops.example.com", "WQO_OIDC_MICROSOFT_TENANT": TENANT,
       "WQO_OIDC_MICROSOFT_CLIENT_ID": "ms-client", "WQO_OIDC_MICROSOFT_CLIENT_SECRET": "ms-secret",
       "WQO_OIDC_GOOGLE_CLIENT_ID": "g-client", "WQO_OIDC_GOOGLE_CLIENT_SECRET": "g-secret"}


@pytest.fixture
def idp(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    return FakeIdP()


def demo():
    return C.load(C.DEMO_FILE), "ok"


def client(db_url, idp):
    http = httpx.Client(transport=httpx.MockTransport(idp.handler))
    c = TestClient(create_app({}, demo, db_url=db_url, oidc_http=http))
    c.__enter__()
    return c


def start(c, provider):
    r = c.get(f"/auth/oidc/{provider}/start", follow_redirects=False)
    assert r.status_code == 303
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))
    assert q["redirect_uri"] == f"https://ops.example.com/auth/oidc/{provider}/callback"
    assert q["code_challenge_method"] == "S256" and q["scope"] == "openid email profile"
    return q


def claims(provider, expected_nonce, **extra):
    now = int(time.time())
    aud = "ms-client" if provider == "microsoft" else "g-client"
    base = {"iss": ISS[provider], "aud": aud, "sub": "s1", "iat": now, "exp": now + 600, "nonce": expected_nonce}
    return {**base, **extra}


def test_providers_from_env():
    assert O.providers({}) == {}
    p = O.providers(ENV)
    assert set(p) == {"microsoft", "google"} and p["microsoft"].issuer == ISS["microsoft"]
    assert O.providers({**ENV, "WQO_OIDC_MICROSOFT_TENANT": ""}).keys() == {"google"}


def test_microsoft_sign_in(db_url, idp):
    c = client(db_url, idp)
    assert "Sign in with Microsoft 365" in c.get("/login").text
    assert {p["name"] for p in c.get("/api/auth/methods").json()["providers"]} == {"microsoft", "google"}
    q = start(c, "microsoft")
    idp.claims = claims("microsoft", q["nonce"], preferred_username="Sam@demo.example")
    cb = {"code": "good-code", "state": q["state"]}
    r = c.get("/auth/oidc/microsoft/callback", params=cb, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert c.get("/api/me").json()["email"] == "sam@demo.example"
    assert idp.last_token_request["code_verifier"] and idp.last_token_request["client_secret"] == "ms-secret"
    r = c.get("/auth/oidc/microsoft/callback", params=cb, follow_redirects=False)
    assert "expired%20or%20was%20already%20used" in r.headers["location"]          # a state works once


@pytest.mark.parametrize(("provider", "change", "words"), [
    ("google", {"email": "alex@demo.example", "email_verified": False}, "did not confirm"),
    ("google", {"email": "stranger@elsewhere.example", "email_verified": True}, "not on the list"),
    ("microsoft", {"preferred_username": "sam@demo.example", "nonce": "other"}, "nonce"),
    ("microsoft", {"preferred_username": "sam@demo.example", "aud": "someone-else"}, "not valid"),
    ("microsoft", {"preferred_username": "sam@demo.example", "iss": "https://login.microsoftonline.com/x/v2.0"},
     "not valid"),
    ("microsoft", {"preferred_username": "sam@demo.example", "exp": int(time.time()) - 3600}, "expired"),
    ("microsoft", {}, "no email"),
])
def test_rejections(db_url, idp, provider, change, words):
    c = client(db_url, idp)
    q = start(c, provider)
    idp.claims = claims(provider, q["nonce"], **change)
    r = c.get(f"/auth/oidc/{provider}/callback", params={"code": "good-code", "state": q["state"]},
              follow_redirects=False)
    loc = urllib.parse.unquote(r.headers["location"])
    assert loc.startswith("/login?error=") and words in loc, loc
    assert c.get("/api/me").status_code == 401


def test_bad_signature_bad_code_and_cancel(db_url, idp):
    c = client(db_url, idp)
    q = start(c, "google")
    idp.claims = claims("google", q["nonce"], email="alex@demo.example", email_verified=True)
    idp.sign_with_other = True
    cb = {"code": "good-code", "state": q["state"]}
    r = c.get("/auth/oidc/google/callback", params=cb, follow_redirects=False)
    assert "not%20valid" in r.headers["location"]
    q = start(c, "google")
    r = c.get("/auth/oidc/google/callback", params={"code": "bad", "state": q["state"]}, follow_redirects=False)
    assert "did%20not%20accept" in r.headers["location"]
    r = c.get("/auth/oidc/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "cancelled" in urllib.parse.unquote(r.headers["location"])
    assert c.get("/auth/oidc/okta/start").status_code == 404


def test_google_workspace_domain(db_url, idp, monkeypatch):
    monkeypatch.setenv("WQO_OIDC_GOOGLE_DOMAIN", "demo.example")
    c = client(db_url, idp)
    q = start(c, "google")
    assert q["hd"] == "demo.example"
    idp.claims = claims("google", q["nonce"], email="alex@demo.example", email_verified=True, hd="other.example")
    cb = {"code": "good-code", "state": q["state"]}
    r = c.get("/auth/oidc/google/callback", params=cb, follow_redirects=False)
    assert "only%20demo.example" in r.headers["location"]
    q = start(c, "google")
    idp.claims = claims("google", q["nonce"], email="alex@demo.example", email_verified=True, hd="demo.example")
    c.get("/auth/oidc/google/callback", params={"code": "good-code", "state": q["state"]})
    assert c.get("/api/me").json()["name"] == "Alex Sales"


def test_next_survives_the_round_trip(db_url, idp):
    c = client(db_url, idp)
    r = c.get("/auth/oidc/microsoft/start", params={"next": "/api/oauth/authorize?x=1"}, follow_redirects=False)
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))
    idp.claims = claims("microsoft", q["nonce"], preferred_username="sam@demo.example")
    r = c.get("/auth/oidc/microsoft/callback", params={"code": "good-code", "state": q["state"]},
              follow_redirects=False)
    assert r.headers["location"] == "/api/oauth/authorize?x=1"
    assert "next%3D" not in c.get("/login", params={"next": "https://evil.example"}).text


def test_pending_sign_in_expires(conn, idp):
    p = O.providers()["google"]
    cl = O.Client(p, httpx.Client(transport=httpx.MockTransport(idp.handler)))
    url = cl.start(conn, "https://ops.example.com/cb")
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
    later = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=O.PENDING_MINUTES + 1)
    with pytest.raises(O.OidcError, match="expired"):
        cl.finish(conn, state, "good-code", "https://ops.example.com/cb", now=later)
