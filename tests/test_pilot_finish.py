"""ADR-0025 25d: a first password set by someone else must be changed, problems reported from the workspace go by
email once a day, and a pilot company's AI runs are capped per day."""
import datetime as dt

import pytest

from wqops import company as C
from wqops.hub import accounts as A
from wqops.hub import feedback as FB
from wqops.hub.ai import agent as AG


def test_password_set_by_someone_else_must_be_changed(conn):
    m = C.load(C.DEMO_FILE)
    A.sync(conn, m)
    owner = m["people"][0]["email"]
    A.set_password(conn, "sam@demo.example", "given pass 12", by=owner)
    assert A.public(A.get(conn, "sam@demo.example"))["must_change"]
    A.set_password(conn, "sam@demo.example", "my own pass 34", by="sam@demo.example")
    assert not A.public(A.get(conn, "sam@demo.example"))["must_change"]
    A.set_password(conn, owner, "first pass 56")                       # the installer, no WQO_MUST_CHANGE
    assert not A.get(conn, owner)["must_change"]
    A.set_password(conn, owner, "first pass 78", must_change=True)     # a pilot company's emailed first password
    assert A.get(conn, owner)["must_change"]


def test_feedback_is_kept_and_sent_once_a_day(conn):
    user = {"email": "pat@acme.example"}
    with pytest.raises(FB.FeedbackError):
        FB.add(conn, user, "   ")
    FB.add(conn, user, "The NCR page shows nothing", "/quality/ncr/3", ["TypeError: x is undefined"] * 12)
    FB.add(conn, user, "Second thing", "/")
    sent = []
    env = {"WQO_SMTP_HOST": "smtp.example", "WQO_SMTP_SENDER": "noreply@example.com", "WQO_FEEDBACK_TO": "eddie@x.com"}
    morning = dt.datetime(2026, 11, 7, 7, 0, tzinfo=dt.UTC)
    assert FB.send_daily(conn, "Acme", now=morning, sender=lambda *a: sent.append(a), env=env) == 0   # before 08:00
    assert FB.send_daily(conn, "Acme", now=morning, sender=lambda *a: sent.append(a), env={}) == 0     # no mail set
    later = morning.replace(hour=9)
    assert FB.send_daily(conn, "Acme", now=later, sender=lambda *a: sent.append(a), env=env) == 2
    (settings, subject, body), = sent
    assert settings["to"] == "eddie@x.com" and "Acme" in subject and "The NCR page shows nothing" in body
    assert body.count("TypeError") == 10                                   # at most 10 errors per report
    FB.add(conn, user, "Third", "/")
    assert FB.send_daily(conn, "Acme", now=later.replace(hour=10), sender=lambda *a: sent.append(a), env=env) == 0
    assert FB.send_daily(conn, "Acme", now=later + dt.timedelta(days=1), sender=lambda *a: sent.append(a), env=env) == 1


def test_ai_runs_capped_per_day(conn):
    AG.check_daily(conn, env={})                                          # no cap set: nothing to check
    for _ in range(2):
        conn.execute("insert into ai_runs (email, kind, question, engine) values ('a@b.c', 'ask', 'q', 'rules')")
    AG.check_daily(conn, env={"WQO_AI_DAILY": "3"})
    with pytest.raises(AG.DailyLimit):
        AG.check_daily(conn, env={"WQO_AI_DAILY": "2"})
