"""Hub health check and landing page (Phase 1 item 3)."""

from fastapi.testclient import TestClient

from wqops import company as C
from wqops.hub import app as A
from wqops.hub.app import create_app


def demo():
    return C.load(C.DEMO_FILE), "ok"


def test_health_ok():
    c = TestClient(create_app({"database": lambda: "ok", "erpnext": lambda: "ok"}, demo))
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["checks"] == {"database": "ok", "erpnext": "ok", "company_manifest": "ok"}


def test_health_fails_when_any_check_fails():
    c = TestClient(create_app({"database": lambda: "ok", "erpnext": lambda: "error: no reply to ping"}, demo))
    r = c.get("/api/health")
    assert r.status_code == 503 and r.json()["ok"] is False
    c = TestClient(create_app({}, lambda: (None, "not configured")))
    assert c.get("/api/health").status_code == 503


def test_home_names_the_company_and_marks_demo():
    page = TestClient(create_app({}, demo)).get("/").text
    assert "Harbor Lane Supply (Demo)" in page and "fictional demo company" in page
    page = TestClient(create_app({}, lambda: (None, "not configured"))).get("/").text
    assert "WenQuest Ops" in page and "fictional" not in page


def test_unconfigured_checks_report_honestly(monkeypatch):
    monkeypatch.delenv("WQO_DB", raising=False)
    monkeypatch.delenv("WQO_COMPANY_FILE", raising=False)
    assert A.check_db() == "not configured"
    assert A.load_company() == (None, "not configured")
    monkeypatch.setenv("WQO_COMPANY_FILE", "/nonexistent/company.yaml")
    assert A.load_company()[1].startswith("error")
