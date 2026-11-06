"""Problems people report from the workspace (ADR-0025 25d): kept here, and once a day sent as one email to whoever
runs the pilot (WQO_FEEDBACK_TO), through the server's mail settings (WQO_SMTP_*). Without them nothing is sent and
the reports stay in the table."""
from __future__ import annotations

import datetime as dt
import json
import os
import smtplib
import ssl
from email.message import EmailMessage

from wqops.i18n import say

MAX_TEXT = 4000


class FeedbackError(ValueError):
    pass


def add(conn, user: dict, text: str, page: str = "", errors: list | None = None) -> int:
    text = (text or "").strip()
    if not text:
        raise FeedbackError(say("write what went wrong"))
    errs = [str(e)[:500] for e in (errors or [])][:10]
    return conn.execute("insert into feedback (email, page, text, errors) values (%s, %s, %s, %s) returning id",
                        (user["email"], (page or "")[:300], text[:MAX_TEXT], json.dumps(errs))).fetchone()["id"]


def digest(rows: list[dict], company: str) -> str:
    out = [f"{company}: {len(rows)}"]
    for r in rows:
        out.append(f"\n#{r['id']}  {r['created_at']:%Y-%m-%d %H:%M}  {r['email']}  {r['page']}\n{r['text']}")
        errs = r["errors"] if isinstance(r["errors"], list) else json.loads(r["errors"] or "[]")
        out += [f"  ! {e}" for e in errs]
    return "\n".join(out)


def mail_settings(env=None) -> dict | None:
    env = os.environ if env is None else env
    s = {k: env.get(f"WQO_SMTP_{k.upper()}", "") for k in ("host", "port", "secure", "user", "password", "sender")}
    s["to"] = env.get("WQO_FEEDBACK_TO", "")
    return s if s["host"] and s["to"] and (s["sender"] or s["user"]) else None


def send(s: dict, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["sender"] or s["user"], s["to"], subject
    msg.set_content(body)
    port = int(s["port"] or (465 if s["secure"] == "ssl" else 587))
    if s["secure"] == "ssl":
        with smtplib.SMTP_SSL(s["host"], port, context=ssl.create_default_context(), timeout=30) as m:
            if s["user"]:
                m.login(s["user"], s["password"])
            m.send_message(msg)
    else:
        with smtplib.SMTP(s["host"], port, timeout=30) as m:
            if s["secure"] == "tls":
                m.starttls(context=ssl.create_default_context())
            if s["user"]:
                m.login(s["user"], s["password"])
            m.send_message(msg)


def send_daily(conn, company: str, *, now: dt.datetime | None = None, sender=send, env=None) -> int:
    """Send the reports not sent yet, once a day (after 08:00 UTC); return how many went."""
    now = now or dt.datetime.now(dt.UTC)
    s = mail_settings(env)
    if s is None or now.hour < 8:
        return 0
    last = conn.execute("select max(sent_at) as t from feedback").fetchone()["t"]
    if last and last.date() == now.date():
        return 0
    rows = conn.execute("select * from feedback where sent_at is null order by id").fetchall()
    if not rows:
        return 0
    sender(s, f"WenQuest Ops feedback - {company} - {len(rows)}", digest(rows, company))
    conn.execute("update feedback set sent_at = %s where id = any(%s)", (now, [r["id"] for r in rows]))
    return len(rows)
