"""Trial accounts in the demo company (ADR-0027).

People who ask for a trial on the WenQuest website get an account in the shared demo company: role quality,
source 'trial', ending after WQO_TRIAL_DAYS (30). The demo company is put back to its clean snapshot every night
(deploy/demo-reset.sh); the trial accounts are exported before and imported after, passwords unchanged.

    python -m wqops.hub.trial add --name NAME --email EMAIL [--days 30]   prints {email, password, expires}
    python -m wqops.hub.trial export                                      prints the live trial accounts (JSON)
    python -m wqops.hub.trial import < accounts.json                      puts them back after the night's restore
    python -m wqops.hub.trial expire                                      stops the accounts past their date
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import string
import sys

from wqops.hub import accounts as A
from wqops.hub import db as DB
from wqops.i18n import say

ROLE = "quality"


class TrialError(ValueError):
    pass


def new_password() -> str:
    """12 characters, letters and digits, no look-alikes; passes the hub's rules."""
    abc = "".join(ch for ch in string.ascii_letters + string.digits if ch not in "0O1lI")
    while True:
        pw = "".join(secrets.choice(abc) for _ in range(12))
        if A.password_problem(pw) is None:
            return pw


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def add(conn, *, name: str, email: str, days: int = 30, at: dt.datetime | None = None) -> dict:
    """Open (or, while it lasts, give a new first password to) a trial account."""
    t = at or now()
    email, name = (email or "").strip().lower(), (name or "").strip()
    if not name or not A.EMAIL.match(email):
        raise TrialError(say("give a name and a valid email"))
    u = A.get(conn, email)
    if u is not None and u["source"] != "trial":
        raise TrialError(say("{email} already has access", email=email))
    if u is not None and (not u["active"] or (u["expires_at"] and u["expires_at"] <= t)):
        raise TrialError(say("the trial of {email} has ended", email=email))
    if u is None:
        conn.execute("insert into users (email, name, roles, source, expires_at) values (%s, %s, %s, 'trial', %s)",
                     (email, name, [ROLE], t + dt.timedelta(days=days)))
        A.event(conn, email, "user_created", "trial account (ADR-0027)")
    pw = new_password()
    A.set_password(conn, email, pw, by="trial", must_change=True)
    u = A.get(conn, email)
    return {"email": email, "password": pw, "expires": u["expires_at"].date().isoformat()}


def export(conn, at: dt.datetime | None = None) -> list[dict]:
    t = at or now()
    rows = conn.execute("select email, name, password_hash, must_change, expires_at from users "
                        "where source='trial' and active and expires_at > %s order by email", (t,)).fetchall()
    return [{"email": r["email"], "name": r["name"], "password_hash": r["password_hash"],
             "must_change": bool(r["must_change"]), "expires_at": r["expires_at"].isoformat()} for r in rows]


def import_(conn, rows: list[dict]) -> int:
    """After the restore: the demo snapshot has no trial accounts (or old ones); put the live ones back."""
    n = 0
    for r in rows:
        email = str(r["email"]).lower()
        u = A.get(conn, email)
        if u is not None and u["source"] != "trial":
            continue                                   # never take over someone of the demo company
        exp = dt.datetime.fromisoformat(r["expires_at"])
        if u is None:
            conn.execute("insert into users (email, name, roles, source, expires_at, password_hash, must_change) "
                         "values (%s, %s, %s, 'trial', %s, %s, %s)",
                         (email, r["name"], [ROLE], exp, r["password_hash"], bool(r["must_change"])))
        else:
            conn.execute("update users set name=%s, roles=%s, active=true, expires_at=%s, password_hash=%s, "
                         "must_change=%s, updated_at=now() where id=%s",
                         (r["name"], [ROLE], exp, r["password_hash"], bool(r["must_change"]), u["id"]))
        n += 1
    return n


def expire(conn, at: dt.datetime | None = None) -> list[str]:
    t = at or now()
    rows = conn.execute("update users set active=false, updated_at=now() where source='trial' and active "
                        "and expires_at <= %s returning email", (t,)).fetchall()
    for r in rows:
        A.event(conn, r["email"], "user_deactivated", "trial ended (ADR-0027)")
    return [r["email"] for r in rows]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m wqops.hub.trial", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--name", required=True)
    a.add_argument("--email", required=True)
    a.add_argument("--days", type=int, default=int(os.environ.get("WQO_TRIAL_DAYS", "30") or 30))
    sub.add_parser("export")
    sub.add_parser("import")
    sub.add_parser("expire")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    conn = DB.connect(os.environ["WQO_DB"])
    DB.migrate(conn)
    try:
        if args.cmd == "add":
            print(json.dumps(add(conn, name=args.name, email=args.email, days=args.days), ensure_ascii=False))
        elif args.cmd == "export":
            print(json.dumps(export(conn), ensure_ascii=False))
        elif args.cmd == "import":
            print(f"{import_(conn, json.load(sys.stdin))} trial accounts back")
        else:
            print(f"{len(expire(conn))} trial accounts ended")
    except (TrialError, A.AccountError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
