"""Hub health check and landing page (Phase 1 item 3)."""

from fastapi.testclient import TestClient

from wqops import company as C
from wqops.hub import app as A
from wqops.hub.app import create_app


def demo():
    return C.load(C.DEMO_FILE), "ok"


def test_health_ok():
    c = TestClient(create_app({"database": lambda: "ok", "erpnext": lambda: "ok"}, demo, db_url=""))
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["checks"] == {"database": "ok", "erpnext": "ok", "company_manifest": "ok"}


def test_health_fails_when_any_check_fails():
    failing = {"database": lambda: "ok", "erpnext": lambda: "error: no reply to ping"}
    c = TestClient(create_app(failing, demo, db_url=""))
    r = c.get("/api/health")
    assert r.status_code == 503 and r.json()["ok"] is False
    c = TestClient(create_app({}, lambda: (None, "not configured"), db_url=""))
    assert c.get("/api/health").status_code == 503


def test_login_page_names_the_company_and_marks_demo():
    page = TestClient(create_app({}, demo, db_url="")).get("/login").text
    assert "Harbor Lane Supply (Demo)" in page and "fictional demo company" in page
    page = TestClient(create_app({}, lambda: (None, "not configured"), db_url="")).get("/login").text
    assert "WenQuest Ops" in page and "fictional" not in page


def test_unconfigured_checks_report_honestly(monkeypatch):
    monkeypatch.delenv("WQO_DB", raising=False)
    monkeypatch.delenv("WQO_COMPANY_FILE", raising=False)
    assert A.check_db() == "not configured"
    assert A.load_company() == (None, "not configured")
    monkeypatch.setenv("WQO_COMPANY_FILE", "/nonexistent/company.yaml")
    assert A.load_company()[1].startswith("error")


def _client(db_url):
    app = create_app({}, demo, db_url=db_url)
    c = TestClient(app)
    c.__enter__()                       # runs startup: migrations and the people from the manifest
    return c


def test_sign_in_flow(db_url):
    from wqops.hub import accounts as Acc
    from wqops.hub import db as DB

    c = _client(db_url)
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"
    assert c.get("/api/me").status_code == 401
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "lee@demo.example", "Warehouse pass 1")
        Acc.set_password(conn, "dana@demo.example", "Owner pass 2026")
    r = c.post("/api/login", json={"email": "lee@demo.example", "password": "wrong one 1"})
    assert r.status_code == 401 and r.json()["detail"] == "wrong email or password"
    r = c.post("/api/login", json={"email": "lee@demo.example", "password": "Warehouse pass 1"})
    assert r.status_code == 200 and "inventory:view" in r.json()["permissions"]
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert c.get("/api/me").json()["name"] == "Lee Warehouse"
    assert "What you can do" in c.get("/").text
    r = c.get("/api/users")
    assert r.status_code == 403 and "your role does not allow" in r.json()["detail"]
    r = c.post("/api/users/password", json={"email": "sam@demo.example", "password": "Someone else 1"})
    assert r.status_code == 403
    r = c.post("/api/users/password", json={"current": "nope", "password": "New warehouse 2"})
    assert r.status_code == 400
    assert c.post("/api/users/password", json={"current": "Warehouse pass 1", "password": "New warehouse 2"}).json()
    assert c.get("/api/me").status_code == 401                 # changing the password ended the session
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Owner pass 2026"})
    assert len(c.get("/api/users").json()) == 7
    assert c.post("/api/users/password", json={"email": "sam@demo.example", "password": "Set by owner 1"}).json()
    assert c.post("/api/logout").json() == {"ok": True}
    assert c.get("/api/me").status_code == 401


def test_form_sign_in_redirects(db_url):
    from wqops.hub import accounts as Acc
    from wqops.hub import db as DB

    c = _client(db_url)
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "dana@demo.example", "Owner pass 2026")
    r = c.post("/api/login", data={"email": "dana@demo.example", "password": "bad pass 1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?error=")
    r = c.post("/api/login", data={"email": "dana@demo.example", "password": "Owner pass 2026"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    r = c.post("/api/login", json={"email": "dana@demo.example", "password": "Owner pass 2026"},
               headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()
