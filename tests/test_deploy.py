"""Deployment files stay consistent (Phase 1 item 3). The real install runs in CI (nightly and on deploy changes)."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "deploy"
SCRIPTS = ["install.sh", "backup.sh", "restore.sh", "upgrade.sh", "status.sh"]


def test_scripts_parse_and_are_executable():
    for s in [*SCRIPTS, "lib.sh"]:
        subprocess.run(["bash", "-n", str(D / s)], check=True)
    for s in SCRIPTS:
        assert os.access(D / s, os.X_OK), s


def test_compose_services_and_no_secrets():
    text = (D / "docker-compose.yml").read_text(encoding="utf-8")
    c = yaml.safe_load(text)
    assert {"caddy", "db", "hub", "erp-backend", "erp-frontend", "erp-db"} <= set(c["services"])
    assert c["services"]["caddy"]["ports"] == ["80:80", "443:443"]
    exposed = [s for s, v in c["services"].items() if v.get("ports")]
    assert exposed == ["caddy"], "only Caddy is reachable from outside"
    assert "frappe/erpnext:v" in text                         # official image, pinned version (ADR-0001)
    assert not re.search(r"PASSWORD:\s*[A-Za-z0-9]{8,}", text), "passwords come from .env"


def test_caddy_serves_both_domains():
    caddy = (D / "Caddyfile").read_text(encoding="utf-8")
    assert "{$WQO_DOMAIN}" in caddy and "{$WQO_ERP_DOMAIN}" in caddy and "reverse_proxy hub:8100" in caddy


def test_runbook_covers_every_script():
    runbook = (ROOT / "docs" / "ops" / "README.md").read_text(encoding="utf-8")
    for s in SCRIPTS:
        assert s in runbook, f"docs/ops/README.md should explain {s}"
    for topic in ("Requirements", "Backup", "Restore", "Upgrade", "Monitoring", "Troubleshooting"):
        assert topic in runbook


def test_shellcheck_warnings():
    exe = shutil.which("shellcheck")
    assert exe, "shellcheck is missing: pip install -e '.[dev]'"
    files = [str(D / s) for s in [*SCRIPTS, "lib.sh"]] + [str(ROOT / ".github" / "scripts" / "ci_scope.sh")]
    r = subprocess.run([exe, "-S", "warning", "-x", *files], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout
