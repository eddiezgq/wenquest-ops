"""Accounts, passwords, lockout and sessions (ADR-0005). Needs PostgreSQL (WQO_TEST_DB)."""

import copy
import datetime as dt

import pytest

from wqops import company as C
from wqops.hub import accounts as A
from wqops.hub import db as DB

NOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.UTC)


def test_password_hashing():
    h = A.hash_password("correct horse 42")
    assert h.startswith("scrypt$") and "correct" not in h
    assert A.check_password("correct horse 42", h)
    assert not A.check_password("correct horse 43", h)
    assert not A.check_password("x", None) and not A.check_password("x", "garbage")
    assert A.hash_password("same 1234567") != A.hash_password("same 1234567")   # salted
    assert A.password_problem("short1") and A.password_problem("onlyletterslong")
    assert not A.password_problem("good pass 1")


def test_migrations_are_idempotent(conn):
    assert DB.migrate(conn) == []


def test_sync_creates_updates_deactivates(conn):
    m = C.load(C.DEMO_FILE)
    r = A.sync(conn, m)
    assert len(r["created"]) == 7 and not r["updated"]
    assert A.sync(conn, m) == {"created": [], "updated": [], "deactivated": [], "reactivated": []}
    m2 = copy.deepcopy(m)
    m2["people"][1]["roles"] = ["ops_manager", "quality"]
    removed = m2["people"].pop()
    r = A.sync(conn, m2)
    assert r["updated"] == ["sam@demo.example"] and r["deactivated"] == [removed["email"]]
    assert sorted(A.get(conn, "sam@demo.example")["roles"]) == ["ops_manager", "quality"]
    assert A.get(conn, removed["email"])["active"] is False
    r = A.sync(conn, m)
    assert r["reactivated"] == [removed["email"]]


def test_login_lockout_and_sessions(conn):
    A.sync(conn, C.load(C.DEMO_FILE))
    with pytest.raises(A.AccountError, match="needs"):
        A.set_password(conn, "dana@demo.example", "short")
    A.set_password(conn, "dana@demo.example", "Harbor lane 2026")
    u = A.authenticate(conn, "DANA@demo.example", "Harbor lane 2026", now=NOW)
    for _ in range(A.MAX_FAILED - 1):
        with pytest.raises(A.AccountError, match="wrong email or password"):
            A.authenticate(conn, "dana@demo.example", "nope", now=NOW)
    with pytest.raises(A.AccountError, match="wrong email or password"):
        A.authenticate(conn, "dana@demo.example", "nope", now=NOW)        # the 5th locks
    with pytest.raises(A.AccountError, match="too many"):
        A.authenticate(conn, "dana@demo.example", "Harbor lane 2026", now=NOW + dt.timedelta(minutes=5))
    shown = {p["email"]: p for p in A.people(conn, now=NOW + dt.timedelta(minutes=5))}
    assert shown["dana@demo.example"]["locked"] and not shown["sam@demo.example"]["locked"]   # on the people page
    assert A.authenticate(conn, "dana@demo.example", "Harbor lane 2026", now=NOW + dt.timedelta(minutes=11))
    with pytest.raises(A.AccountError, match="wrong email or password"):
        A.authenticate(conn, "nobody@demo.example", "x", now=NOW)
    with pytest.raises(A.AccountError, match="wrong email or password"):
        A.authenticate(conn, "sam@demo.example", "anything 123", now=NOW)   # no password yet

    tok = A.create_session(conn, u, "password", now=NOW)
    assert A.session_user(conn, tok, now=NOW + dt.timedelta(days=1))["email"] == "dana@demo.example"
    assert A.session_user(conn, tok, now=NOW + dt.timedelta(days=A.SESSION_DAYS, minutes=1)) is None
    assert A.session_user(conn, "forged", now=NOW) is None
    assert conn.execute("select count(*) n from sessions where token_hash=%s", (tok,)).fetchone()["n"] == 0  # hashed
    A.end_session(conn, tok)
    assert A.session_user(conn, tok, now=NOW) is None
    tok = A.create_session(conn, u, "password", now=NOW)
    A.set_password(conn, "dana@demo.example", "Another pass 99")          # changing the password ends sessions
    assert A.session_user(conn, tok, now=NOW) is None
    events = [r["event"] for r in conn.execute("select event from auth_events order by id").fetchall()]
    assert {"user_created", "password_set", "login", "login_failed", "locked", "logout"} <= set(events)


def test_cli(db_url, monkeypatch, capsys):
    monkeypatch.setenv("WQO_DB", db_url)
    monkeypatch.setenv("WQO_COMPANY_FILE", str(C.DEMO_FILE))
    assert A.main(["sync"]) == 0
    assert "created 7" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("Good password 1\n"))
    assert A.main(["set-password", "dana@demo.example"]) == 0
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("weak\n"))
    assert A.main(["set-password", "dana@demo.example"]) == 1
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("Owner via cli 1\n"))
    assert A.main(["set-owner-password"]) == 0
    assert "dana@demo.example" in capsys.readouterr().out
    assert A.main(["list"]) == 0
    assert "riley@demo.example" in capsys.readouterr().out
    assert A.main([]) == 2
