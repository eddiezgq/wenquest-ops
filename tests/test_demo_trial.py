"""ADR-0027: trial accounts in the shared demo company, opened from the WenQuest website and reset every night."""
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from wqops import company as C
from wqops.hub import accounts as A
from wqops.hub import trial as T
from wqops.hub.ai import agent as AG

D = Path(__file__).resolve().parents[1] / "deploy"
NOW = dt.datetime(2026, 11, 7, 12, tzinfo=dt.UTC)


def test_a_trial_account_signs_in_and_ends(conn):
    A.sync(conn, C.load(C.DEMO_FILE))
    r = T.add(conn, name="王建国", email="WJG@Example.com", days=30, at=NOW)
    assert r["email"] == "wjg@example.com" and r["expires"] == "2026-12-07"
    u = A.authenticate(conn, "wjg@example.com", r["password"], now=NOW)
    assert u["roles"] == ["quality"] and A.public(u)["must_change"] and A.public(u)["source"] == "trial"
    assert A.public(u)["expires"] == "2026-12-07"
    # asking again while it lasts: a new first password
    r2 = T.add(conn, name="王建国", email="wjg@example.com", at=NOW + dt.timedelta(days=3))
    assert r2["password"] != r["password"]
    # a person of the demo company is never turned into a trial account
    owner = C.load(C.DEMO_FILE)["people"][0]["email"]
    with pytest.raises(T.TrialError):
        T.add(conn, name="x", email=owner, at=NOW)
    # past its date: no sign-in, no session, and the night's run stops it
    later = NOW + dt.timedelta(days=31)
    with pytest.raises(A.AccountError, match="trial"):
        A.authenticate(conn, "wjg@example.com", r2["password"], now=later)
    tok = A.create_session(conn, u, "password", now=NOW)
    assert A.session_user(conn, tok, now=NOW) and A.session_user(conn, tok, now=later) is None
    assert T.expire(conn, at=later) == ["wjg@example.com"]
    with pytest.raises(T.TrialError, match="ended"):
        T.add(conn, name="王建国", email="wjg@example.com", at=later)


def test_trial_accounts_survive_the_nightly_restore(conn):
    T.add(conn, name="甲", email="a@trial.cn", days=30, at=NOW)
    b = T.add(conn, name="乙", email="b@trial.cn", days=1, at=NOW - dt.timedelta(days=2))   # already past its date
    kept = T.export(conn, at=NOW)
    assert [k["email"] for k in kept] == ["a@trial.cn"]
    pw_hash = A.get(conn, "a@trial.cn")["password_hash"]
    conn.execute("delete from users where source='trial'")                # what the restore of the snapshot does
    assert T.import_(conn, json.loads(json.dumps(kept))) == 1
    assert A.get(conn, "a@trial.cn")["password_hash"] == pw_hash and A.get(conn, "b@trial.cn") is None
    assert b["email"] == "b@trial.cn"


def test_a_trial_account_has_its_own_small_ai_limit(conn):
    user = {"email": "t@trial.cn", "source": "trial"}
    for _ in range(2):
        conn.execute("insert into ai_runs (email, kind, question, engine) values ('t@trial.cn', 'ask', 'q', 'rules')")
    AG.check_daily(conn, env={"WQO_TRIAL_AI_DAILY": "3"}, user=user)
    with pytest.raises(AG.DailyLimit, match=r"t@trial\.cn"):
        AG.check_daily(conn, env={"WQO_TRIAL_AI_DAILY": "2"}, user=user)
    AG.check_daily(conn, env={"WQO_TRIAL_AI_DAILY": "2"}, user={"email": "boss@x.cn", "source": "manifest"})


def test_runner_opens_trial_accounts_only_when_on(tmp_path):
    wd, q, bin_ = tmp_path / "qms", tmp_path / "queue", tmp_path / "bin"
    for d in (wd, q, bin_):
        d.mkdir()
    for f in ("lib.sh", "pilot-runner.sh"):
        shutil.copy(D / f, wd)
    (bin_ / "docker").write_text("""#!/usr/bin/env bash
echo "$@" >> "$CALLS"
case "$*" in *"--email bad@x.cn"*) echo "ERROR: bad@x.cn already has access" >&2; exit 1 ;; esac
echo '{"email": "w@x.cn", "password": "Abc123def456", "expires": "2026-12-07"}'
""")
    (bin_ / "docker").chmod(0o755)
    env = {**os.environ, "WQO_PILOT_QUEUE": str(q), "WQO_DIR": str(wd), "PATH": f"{bin_}:{os.environ['PATH']}",
           "CALLS": str(tmp_path / "calls")}
    (q / "trial-t1.json").write_text(json.dumps({"id": "t1", "name": "王", "email": "w@x.cn"}))
    (wd / ".env").write_text("WQO_DOMAIN=qms.example.cn\n")
    subprocess.run(["bash", str(wd / "pilot-runner.sh")], env=env, check=True, capture_output=True)
    assert "not open" in json.loads((q / "res-trial-t1.json").read_text())["error"]
    (wd / ".env").write_text("WQO_DOMAIN=qms.example.cn\nWQO_DEMO_TRIAL=1\n")
    (q / "trial-t2.json").write_text(json.dumps({"id": "t2", "name": "王", "email": "w@x.cn"}))
    (q / "trial-t3.json").write_text(json.dumps({"id": "t3", "name": "坏", "email": "bad@x.cn"}))
    subprocess.run(["bash", str(wd / "pilot-runner.sh")], env=env, check=True, capture_output=True)
    ok = json.loads((q / "res-trial-t2.json").read_text())
    assert ok == {"email": "w@x.cn", "password": "Abc123def456", "expires": "2026-12-07", "id": "t2",
                  "url": "https://qms.example.cn"}
    assert "already has access" in json.loads((q / "res-trial-t3.json").read_text())["error"]
    assert "wqops.hub.trial add --name 王 --email w@x.cn" in (tmp_path / "calls").read_text()
    assert not list(q.glob("trial-*"))


def test_nightly_reset_script():
    text = (D / "demo-reset.sh").read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(D / "demo-reset.sh")], check=True)
    assert os.access(D / "demo-reset.sh", os.X_OK)
    order = ["trial export", 'restore.sh" "$GOLD" --yes', "upgrade.sh", "\nsnapshot ", "trial import", "trial expire"]
    pos = [text.index(s) for s in order]
    assert pos == sorted(pos), "keep the accounts, restore, upgrade, re-snapshot (clean), then put the accounts back"
    assert "/tmp/wenquest-deploy.lock" in text and "WQO_DEMO_TRIAL" in text
    assert "WQO_SKIP_BACKUP" in (D / "upgrade.sh").read_text()
    wf = (D.parent / ".github" / "workflows" / "deploy-cn.yml").read_text(encoding="utf-8")
    assert "demo-reset.sh" in wf and "WQO_DEMO_TRIAL=1" in wf
