"""Opening ERPNext without signing in again (ADR-0005, 4c): WenQuest Ops as OAuth2 provider for ERPNext."""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient

from wqops import company as C
from wqops.erp import ErpClient
from wqops.hub import accounts as A
from wqops.hub import db as DB
from wqops.hub import erp_sso as S
from wqops.hub.app import create_app

ERP = "https://erp.ops.example.com"
CB = ERP + S.CALLBACK_PATH
SECRET = "sso-secret-for-tests"


class FakeErpUsers:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.calls = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path))
        name = urllib.parse.unquote(req.url.path.split("/")[-1])
        if req.method == "GET":
            return httpx.Response(200, json={"data": self.users[name]}) if name in self.users \
                else httpx.Response(404, json={})
        body = json.loads(req.content)
        if req.method == "POST":
            self.users[body["email"]] = {**body, "name": body["email"]}
            return httpx.Response(200, json={"data": self.users[body["email"]]})
        self.users[name].update(body)
        return httpx.Response(200, json={"data": self.users[name]})

    def client(self):
        return ErpClient("http://erp", "k", "s", transport=httpx.MockTransport(self.handler))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("WQO_ERP_PUBLIC_URL", ERP)
    monkeypatch.setenv("WQO_ERP_SSO_SECRET", SECRET)


def demo():
    return C.load(C.DEMO_FILE), "ok"


def app_client(db_url, erp):
    c = TestClient(create_app({}, demo, db_url=db_url, erp=erp.client()))
    c.__enter__()
    with DB.connect(db_url) as conn:
        A.set_password(conn, "jordan@demo.example", "Quality pass 1")
    return c


def test_role_mapping():
    assert S.erp_roles(["warehouse"]) == ["Stock User"]
    assert S.erp_roles(["sales", "quality"]) == ["Quality Manager", "Sales User", "Stock User"]
    assert "System Manager" in S.erp_roles(["owner"]) and "System Manager" not in S.erp_roles(["ops_manager"])
    assert set(S.ERP_ROLES) == set(C.ROLES)


def test_full_flow(db_url, env):
    erp = FakeErpUsers()
    c = app_client(db_url, erp)
    q = {"client_id": S.CLIENT_ID, "redirect_uri": CB, "state": "st1", "response_type": "code", "scope": "openid"}
    r = c.get("/api/oauth/authorize", params=q, follow_redirects=False)
    assert r.headers["location"].startswith("/login?next=/api/oauth/authorize")       # sign in first
    nxt = urllib.parse.unquote(r.headers["location"].split("next=")[1])
    assert f"value='{nxt}'".replace("&", "&amp;") in c.get("/login", params={"next": nxt}).text
    r = c.post("/api/login", data={"email": "jordan@demo.example", "password": "Quality pass 1", "next": nxt},
               follow_redirects=False)
    assert r.headers["location"] == nxt
    r = c.get(nxt, follow_redirects=False)
    loc = urllib.parse.urlparse(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == CB
    got = dict(urllib.parse.parse_qsl(loc.query))
    assert got["state"] == "st1"
    u = erp.users["jordan@demo.example"]
    assert u["first_name"] == "Jordan" and sorted(r["role"] for r in u["roles"]) == ["Quality Manager", "Stock User"]

    form = {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": CB, "client_id": S.CLIENT_ID}
    assert c.post("/api/oauth/token", data={**form, "client_secret": "wrong"}).status_code == 400
    code = got["code"]
    tok = c.post("/api/oauth/token", data={**form, "client_secret": SECRET}).json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == S.TOKEN_SECONDS
    info = c.get("/api/oauth/userinfo", headers={"authorization": f"Bearer {tok['access_token']}"}).json()
    assert info == {"sub": "jordan@demo.example", "email": "jordan@demo.example", "email_verified": True,
                    "name": "Jordan Quality", "given_name": "Jordan", "family_name": "Quality"}
    assert c.get("/api/oauth/userinfo", headers={"authorization": "Bearer forged"}).status_code == 401
    r = c.post("/api/oauth/token", data={**form, "code": code, "client_secret": SECRET})
    assert r.status_code == 400                                                     # a code works once
    # roles changed in WenQuest Ops: the next sign-in brings ERPNext up to date
    with DB.connect(db_url) as conn:
        conn.execute("update users set roles='{quality,purchasing}' where email='jordan@demo.example'")
    c.get(nxt, follow_redirects=False)
    assert sorted(r["role"] for r in erp.users["jordan@demo.example"]["roles"]) == \
        ["Purchase Manager", "Purchase User", "Quality Manager", "Stock User"]


def test_authorize_rejects_unknown_client_and_redirect(db_url, env):
    c = app_client(db_url, FakeErpUsers())
    q = {"client_id": S.CLIENT_ID, "redirect_uri": "https://evil.example/cb", "state": "x"}
    assert c.get("/api/oauth/authorize", params=q, follow_redirects=False).status_code == 400
    q = {"client_id": "someone", "redirect_uri": CB, "state": "x"}
    assert c.get("/api/oauth/authorize", params=q, follow_redirects=False).status_code == 400


def test_next_only_same_site(db_url, env):
    c = app_client(db_url, FakeErpUsers())
    for bad in ("https://evil.example", "//evil.example", "/\\evil.example"):
        assert "name='next'" not in c.get("/login", params={"next": bad}).text
        r = c.post("/api/login", data={"email": "jordan@demo.example", "password": "Quality pass 1", "next": bad},
                   follow_redirects=False)
        assert r.headers["location"] == "/"


def test_codes_and_tokens_expire(conn, monkeypatch):
    A.sync(conn, C.load(C.DEMO_FILE))
    u = A.get(conn, "sam@demo.example")
    code = S.issue_code(conn, u, CB)
    later = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=S.CODE_SECONDS + 5)
    with pytest.raises(S.SsoError, match="expired"):
        S.exchange(conn, code, client_id=S.CLIENT_ID, client_secret=SECRET, redirect_uri=CB, secret=SECRET, now=later)
    code = S.issue_code(conn, u, CB)
    with pytest.raises(S.SsoError, match="does not match"):
        S.exchange(conn, code, client_id=S.CLIENT_ID, client_secret=SECRET, redirect_uri=CB + "x", secret=SECRET)
    code = S.issue_code(conn, u, CB)
    with pytest.raises(S.SsoError, match="invalid client"):
        S.exchange(conn, code, client_id=S.CLIENT_ID, client_secret="", redirect_uri=CB, secret="")
    tok = S.exchange(conn, S.issue_code(conn, u, CB), client_id=S.CLIENT_ID, client_secret=SECRET, redirect_uri=CB,
                     secret=SECRET)
    assert S.userinfo(conn, tok)["email"] == "sam@demo.example"
    with pytest.raises(S.SsoError):
        S.userinfo(conn, tok, now=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=S.TOKEN_SECONDS + 5))
    conn.execute("update users set active=false where email='sam@demo.example'")
    with pytest.raises(S.SsoError):
        S.userinfo(conn, tok)                                     # deactivated people lose access at once


def test_social_login_key():
    k = S.social_login_key("https://ops.example.com/", SECRET)
    assert k["base_url"] == "https://ops.example.com" and k["authorize_url"] == "/api/oauth/authorize"
    assert k["access_token_url"] == "http://hub:8100/api/oauth/token"       # ERPNext's server talks to the hub inside
    assert k["sign_ups"] == "Deny" and k["client_secret"] == SECRET and k["redirect_url"] == S.CALLBACK_PATH
