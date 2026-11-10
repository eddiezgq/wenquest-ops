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
    files = [str(D / s) for s in [*SCRIPTS, "lib.sh", "tenant.sh", "pilot-runner.sh", "demo-reset.sh",
                                  "demo-reinstall.sh"]]
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


def test_demo_company_installed_again_when_its_data_changes(tmp_path):
    """WenQuest round 132: `tenant.sh demo <id> --data-version V` installs the demo company again from nothing when it
    was loaded with another version (none, for one loaded before versions); the trial accounts and the owner's
    password hash go out before and back in after; the same version again changes nothing. Docker, the installation
    and the snapshot are stand-ins that write down what they were asked."""
    base, tenants, binr = tmp_path / "qms", tmp_path / "qms-tenants", tmp_path / "bin"
    for p in (base, tenants / "sewing", binr):
        p.mkdir(parents=True)
    shutil.copy(D / "lib.sh", base)
    shutil.copy(D / "tenant.sh", base)
    shutil.copy(D / "demo-reinstall.sh", base)
    calls = tmp_path / "calls"
    (base / ".env").write_text("WQO_INSTALLED=2026-11-01\nWQO_DOMAIN=qms.example.cn\nWQO_ERP_DOMAIN=erp.example.cn\n"
                               "WQO_HUB_IMAGE=127.0.0.1:5000/qms/wenquest-ops-hub:sha-new\n")
    (base / "install.sh").write_text(f"""#!/usr/bin/env bash
echo "install $*" >> {calls}
printf 'WQO_INSTALLED=now\\nWQO_ERP_API_KEY=new\\n' >> .env
""")
    (base / "demo-reset.sh").write_text(f'#!/usr/bin/env bash\necho "snapshot $*" >> {calls}\n')
    (base / "docker-compose.yml").write_text("services: {}\n")
    (base / "Caddyfile").write_text("")
    for f in ("install.sh", "demo-reset.sh"):
        (base / f).chmod(0o755)
    (binr / "docker").write_text(f"""#!/usr/bin/env bash
echo "docker $*" >> {calls}
case "$*" in
  *"trial export"*) echo '[{{"email": "visitor@example.com"}}]' ;;
  *export-owner*) echo '{{"email": "linhai@demo.example", "password_hash": "scrypt$x"}}' ;;
  *"trial import"*) cat > "{tmp_path}/got-trial-import" ;;
  *import-owner*) cat > "{tmp_path}/got-import-owner" ;;
esac
""")
    (binr / "docker").chmod(0o755)
    (binr / "crontab").write_text("#!/usr/bin/env bash\ncat > /dev/null\n")
    (binr / "crontab").chmod(0o755)
    company = tmp_path / "demo-sewing.yaml"
    company.write_text("demo: true\n")
    d = tenants / "sewing"
    (d / ".env").write_text("WQO_INSTALLED=2026-11-07\nWQO_ERP_API_KEY=old\nWQO_ERP_API_SECRET=old\n"
                            "WQO_DOMAIN=sewing.qms.example.cn\nPOSTGRES_PASSWORD=kept\n"
                            "WQO_HUB_IMAGE=127.0.0.1:5000/qms/wenquest-ops-hub:sha-old\n")
    (d / ".demo-loaded").write_text("")                   # loaded on 11-07, before the data had versions
    for f in ("lib.sh", "install.sh", "demo-reset.sh"):   # an installed company has the scripts beside it
        shutil.copy(base / f, d)
    env = {**os.environ, "PATH": f"{binr}:{os.environ['PATH']}", "WQO_DIR": str(base),
           "WQO_TENANT_MIN_FREE_MB": "1", "WQO_TENANTS_DIR": str(tenants)}
    run = ["bash", str(base / "tenant.sh"), "demo", "sewing", "--company", str(company), "--data-version", "abc123"]
    r = subprocess.run(run, env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls.read_text()
    order = [log.index(x) for x in ("trial export", "export-owner", "down -v", "install ", "wqops.demo.load",
                                     "snapshot snapshot", "trial import", "import-owner")]
    assert order == sorted(order), log
    assert (d / ".demo-loaded").read_text().strip() == "abc123"
    env_now = (d / ".env").read_text()
    assert "WQO_ERP_API_KEY=old" not in env_now and "POSTGRES_PASSWORD=kept" in env_now
    assert "wenquest-ops-hub:sha-new" in env_now and "sha-old" not in env_now
    assert "run --rm --no-deps -T hub python -m wqops.hub.accounts export-owner" in log     # the new image, not exec
    assert "visitor@example.com" in (tmp_path / "got-trial-import").read_text()
    assert "scrypt$x" in (tmp_path / "got-import-owner").read_text() and not (d / "backups" / "reinstall").exists()
    calls.write_text("")
    r = subprocess.run(run, env=env, capture_output=True, text=True, check=False)       # the same data: nothing happens
    assert r.returncode == 0 and "down -v" not in calls.read_text() and "install " not in calls.read_text()


def test_restore_starts_from_an_empty_hub_database(tmp_path, db_url):
    """WenQuest round 132: the demo's nightly reset restored a snapshot over a database where a newer table pointed to
    an older one; `pg_restore --clean` could not drop that one, so it kept a newer column while the list of migrations
    went back, and the hub failed to start on the migration it had already applied. restore.sh empties it first.
    Here docker is a stand-in that runs the database commands against a real PostgreSQL and passes over ERPNext."""
    import psycopg
    import pytest

    tools = [shutil.which(t) for t in ("psql", "pg_dump", "pg_restore")]
    if not all(tools):
        if os.environ.get("CI"):
            pytest.fail("psql, pg_dump and pg_restore are needed")
        pytest.skip("the PostgreSQL client tools are missing")
    name = "wqo_restore_check"
    admin = psycopg.connect(db_url, autocommit=True)
    admin.execute(f"drop database if exists {name}")
    admin.execute(f"create database {name}")
    url = db_url.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(url, autocommit=True) as c:          # the snapshot: migrations 001 and 002
            c.execute("create table schema_migrations (name text primary key); insert into schema_migrations values "
                      "('001'), ('002'); create table parts (id int primary key, code text); insert into parts values "
                      "(1, 'WQ88-1401')")
        work = tmp_path / "snap"
        work.mkdir()
        subprocess.run(["pg_dump", "-Fc", "-f", str(work / "wqo.dump"), url], check=True)
        with psycopg.connect(url, autocommit=True) as c:          # later: migration 003 adds a column and a table
            c.execute("alter table parts add column name_en text; create table manuals (id int primary key, "
                      "part_id int references parts (id)); insert into schema_migrations values ('003')")
        (work / "erpnext.tar").write_bytes(b"")
        backup = tmp_path / "wqo-snap.tar.gz"
        subprocess.run(["tar", "-czf", str(backup), "-C", str(work), "wqo.dump", "erpnext.tar"], check=True)
        inst, binr = tmp_path / "qms", tmp_path / "bin"
        inst.mkdir()
        binr.mkdir()
        for f in ("lib.sh", "restore.sh"):
            shutil.copy(D / f, inst)
        (inst / ".env").write_text("ERP_DB_ROOT_PASSWORD=x\n")
        (binr / "docker").write_text(f"""#!/usr/bin/env bash
args=("$@"); for i in "${{!args[@]}}"; do
  if [ "${{args[$i]}}" = db ] && [ "${{args[$((i-1))]}}" = -T ]; then
    cmd=("${{args[@]:$((i+1))}}"); keep=(); skip=""
    for a in "${{cmd[@]:1}}"; do                           # the container's -U and -d: the test database instead
      if [ -n "$skip" ]; then skip=""; elif [ "$a" = -U ] || [ "$a" = -d ]; then skip=1; else keep+=("$a"); fi
    done
    exec "${{cmd[0]}}" -d "{url}" "${{keep[@]}}"
  fi
done
case "$*" in *"ls -t /tmp/rs"*) echo /tmp/rs/x-database.sql.gz ;; esac
exit 0
""")
        (binr / "docker").chmod(0o755)
        env = {**os.environ, "PATH": f"{binr}:{os.environ['PATH']}", "WQO_DIR": str(inst)}
        r = subprocess.run(["bash", str(inst / "restore.sh"), str(backup), "--yes"], env=env, capture_output=True,
                           text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr
        with psycopg.connect(url, autocommit=True) as c:
            cols = {x[0] for x in c.execute("select column_name from information_schema.columns where table_name = "
                                            "'parts'")}
            assert cols == {"id", "code"}                         # as in the snapshot: 003 can apply again
            assert [x[0] for x in c.execute("select name from schema_migrations order by name")] == ["001", "002"]
            assert c.execute("select to_regclass('manuals')").fetchone()[0] is None
            assert c.execute("select code from parts").fetchone()[0] == "WQ88-1401"
    finally:
        admin.execute(f"drop database if exists {name} with (force)")
