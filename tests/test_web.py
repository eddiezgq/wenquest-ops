"""The web workspace (ADR-0007, step 6d): the hub serves the built pages to people who are signed in."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wqops import company as C
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.app import create_app

ROOT = Path(__file__).resolve().parents[1]
DEMO = C.load(C.DEMO_FILE)


@pytest.fixture
def web(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=app></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return tmp_path


def test_spa_needs_sign_in_and_serves_every_route(db_url, web):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, web_dir=str(web)))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "alex@demo.example", "Demo pass 2026")
    r = c.get("/anomalies/3", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/anomalies/3"
    assert c.get("/api/workspace").status_code == 401
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    for path in ("/", "/objects", "/o/Item/WIDGET%2FA", "/anomalies", "/anomalies/3", "/drafts", "/assistant",
                 "/quality", "/quality/ncr/1", "/quality/capa/2", "/help", "/help/quality"):
        r = c.get(path)
        assert r.status_code == 200 and "id=app" in r.text, path
    assert c.get("/assets/app.js").text == "console.log(1)"
    ws = c.get("/api/workspace").json()
    assert ws["company"] == "Harbor Lane Supply (Demo)" and ws["demo"] and ws["currency"] == "USD"
    assert ws["user"]["email"] == "alex@demo.example" and "sales:view" in ws["user"]["permissions"]
    c.__exit__(None, None, None)


def test_without_a_build_the_plain_page_remains(db_url, tmp_path):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url, web_dir=str(tmp_path)))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "alex@demo.example", "Demo pass 2026")
    c.post("/api/login", json={"email": "alex@demo.example", "password": "Demo pass 2026"})
    assert "What you can do" in c.get("/").text
    assert c.get("/objects").status_code == 404
    c.__exit__(None, None, None)


def test_web_dependencies_are_pinned():
    pkg = json.loads((ROOT / "web/package.json").read_text())
    for deps in (pkg["dependencies"], pkg["devDependencies"]):
        assert all(v[0].isdigit() for v in deps.values()), deps   # exact versions, no ^ or ~
    assert (ROOT / "web/package-lock.json").is_file()


def test_web_builds(tmp_path):
    if shutil.which("npm") is None or not (ROOT / "web/node_modules").is_dir():
        if os.environ.get("CI"):
            pytest.fail("CI must run `npm ci` in web/ before the tests")
        pytest.skip("needs npm and web/node_modules: cd web && npm ci")
    out = subprocess.run(["npx", "vite", "build", "--outDir", str(tmp_path / "dist")], cwd=ROOT / "web",
                         capture_output=True, text=True, timeout=180, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert (tmp_path / "dist/index.html").is_file()
