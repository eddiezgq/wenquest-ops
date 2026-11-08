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
    files = [str(D / s) for s in [*SCRIPTS, "lib.sh", "tenant.sh", "pilot-runner.sh", "demo-reset.sh"]]
    files.append(str(ROOT / ".github" / "scripts" / "ci_scope.sh"))
    r = subprocess.run([exe, "-S", "warning", "-x", *files], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout


def test_document_files_are_kept_and_backed_up():
    """ADR-0014 item 1: the library's files live on a hub volume that backup and restore include."""
    c = yaml.safe_load((D / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "hub-files:/data/files" in c["services"]["hub"]["volumes"] and "hub-files" in c["volumes"]
    assert "hub-files.tar" in (D / "backup.sh").read_text() and "hub-files.tar" in (D / "restore.sh").read_text()
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "tesseract-ocr" in docker and "WQO_FILES_DIR=/data/files" in docker


def test_pilot_company_script(tmp_path):
    """ADR-0025: tenant.sh parses, and the starting manifest it writes for a new pilot company passes the check in
    both languages, with any company name kept exactly as typed."""
    from wqops import company as C

    text = (D / "tenant.sh").read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(D / "tenant.sh")], check=True)
    assert os.access(D / "tenant.sh", os.X_OK)
    gen = re.search(r"<<'PY'\n(.*?)\nPY\n", text, re.S).group(1)
    (tmp_path / "gen.py").write_text(gen, encoding="utf-8")
    for lang, currency in (("zh", "CNY"), ("en", "USD")):
        out = tmp_path / f"{lang}.yaml"
        subprocess.run(["python3", str(tmp_path / "gen.py"), str(out), "acme-tools", 'Acme "Tools": 五金', "Li Ming",
                        "boss@acme.example", lang], check=True)
        m = C.load(out)                           # raises when the manifest has errors
        assert m["company"]["name"] == 'Acme "Tools": 五金' and m["company"]["currency"] == currency
        assert m["demo"] is False and [p["roles"] for p in m["people"]] == [["owner"]]
    for cmd in ("new", "list", "stop <id> | start", "upgrade-all"):
        assert f"./tenant.sh {cmd}" in text
    assert "WQO_TENANT_MIN_FREE_MB" in text and "qms-$id-edge" in text


def test_pilot_runner_hands_over_through_the_folder(tmp_path):
    """ADR-0025 25c: the runner takes a request from the shared folder, runs tenant.sh, and leaves the state, the
    sign-in (readable by the gateway) and the server's free memory; stop/start commands go to tenant.sh."""
    import json

    wd, q = tmp_path / "qms", tmp_path / "queue"
    wd.mkdir()
    q.mkdir()
    shutil.copy(D / "lib.sh", wd)
    shutil.copy(D / "pilot-runner.sh", wd)
    (wd / "tenant.sh").write_text("""#!/usr/bin/env bash
echo "$@" >> "$(dirname "$0")/calls"
if [ "$1" = new ]; then
  [ "$2" = broken ] && { echo "the installation stopped"; exit 1; }
  while [ $# -gt 0 ]; do [ "$1" = --result ] && printf '{"id":"acme","password":"pw-123456"}' > "$2"; shift; done
fi
""")
    (wd / "tenant.sh").chmod(0o755)
    acme = {"id": "acme", "name": 'Acme "Tools"', "contact": "Li", "email": "a@b.cn", "lang": "zh"}
    (q / "req-acme.json").write_text(json.dumps(acme))
    (q / "req-broken.json").write_text(json.dumps({"id": "broken", "name": "B", "contact": "C", "email": "b@b.cn",
                                                   "lang": "en"}))
    (q / "cmd-old.json").write_text(json.dumps({"id": "old", "cmd": "stop"}))
    env = {**os.environ, "WQO_PILOT_QUEUE": str(q), "WQO_DIR": str(wd)}
    subprocess.run(["bash", str(wd / "pilot-runner.sh")], env=env, check=True, capture_output=True)
    assert json.loads((q / "state-acme.json").read_text())["status"] == "active"
    res = q / "res-acme.json"
    assert json.loads(res.read_text())["password"] == "pw-123456" and oct(res.stat().st_mode)[-3:] == "644"
    failed = json.loads((q / "state-broken.json").read_text())
    assert failed["status"] == "failed" and "the installation stopped" in failed["error"]
    assert json.loads((q / "host.json").read_text())["mem_free_mb"] > 0
    calls = (wd / "calls").read_text()
    assert '--name Acme "Tools" --contact Li --email a@b.cn --lang zh' in calls and "stop old" in calls
    assert not list(q.glob("req-*")) and not list(q.glob("cmd-*")) and not list(q.glob("work-*"))
