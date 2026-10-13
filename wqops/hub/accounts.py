"""Accounts, passwords and sessions (ADR-0005).

People come from the company manifest; ``sync`` creates, updates and deactivates them. Passwords are stored as
scrypt hashes; 5 wrong passwords lock the account for 10 minutes. Session tokens are random; only their hash is stored.

    python -m wqops.hub.accounts sync               # from $WQO_COMPANY_FILE into $WQO_DB
    python -m wqops.hub.accounts set-password EMAIL # reads the password from stdin
    python -m wqops.hub.accounts set-owner-password # the first owner in the manifest; password from stdin
    python -m wqops.hub.accounts list
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import secrets
import sys

from wqops import company as C
from wqops.hub import db as DB

MAX_FAILED = 5
LOCK_MINUTES = 10
SESSION_DAYS = 7
MIN_PASSWORD = 10


class AccountError(ValueError):
    pass


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), h)


def password_problem(pw: str) -> str | None:
    if len(pw) < MIN_PASSWORD:
        return f"at least {MIN_PASSWORD} characters"
    if not (any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)):
        return "letters and digits"
    return None


def event(conn, email: str | None, what: str, detail: str = "") -> None:
    conn.execute("insert into auth_events (email, event, detail) values (%s, %s, %s)", (email, what, detail))


def sync(conn, manifest: dict) -> dict[str, list[str]]:
    """Make the users table match the manifest's people."""
    out: dict[str, list[str]] = {"created": [], "updated": [], "deactivated": [], "reactivated": []}
    wanted = {p["email"].lower(): p for p in manifest.get("people", [])}
    existing = {r["email"]: r for r in conn.execute("select * from users").fetchall()}
    for email, p in wanted.items():
        roles, dept = sorted(set(p["roles"])), p.get("department")
        u = existing.get(email)
        if u is None:
            conn.execute("insert into users (email, name, roles, department) values (%s, %s, %s, %s)",
                         (email, p["name"], roles, dept))
            event(conn, email, "user_created")
            out["created"].append(email)
            continue
        if not u["active"]:
            out["reactivated"].append(email)
        if (u["name"], sorted(u["roles"]), u["department"], u["active"]) != (p["name"], roles, dept, True):
            conn.execute("update users set name=%s, roles=%s, department=%s, active=true, updated_at=now() "
                         "where email=%s", (p["name"], roles, dept, email))
            out["updated"].append(email)
    for email, u in existing.items():
        if email not in wanted and u["active"]:
            conn.execute("update users set active=false, updated_at=now() where email=%s", (email,))
            conn.execute("delete from sessions where user_id=%s", (u["id"],))
            event(conn, email, "user_deactivated", "no longer in the company manifest")
            out["deactivated"].append(email)
    return out


def get(conn, email: str) -> dict | None:
    return conn.execute("select * from users where email=%s", (email.lower(),)).fetchone()


def set_password(conn, email: str, pw: str, *, by: str | None = None) -> None:
    """Set the password, unlock, and end all the person's sessions (they sign in again with the new password).
    ``by`` is who set it, when not the person."""
    u = get(conn, email)
    if u is None or not u["active"]:
        raise AccountError(f"no active person with email {email}")
    problem = password_problem(pw)
    if problem:
        raise AccountError(f"password needs {problem}")
    conn.execute("update users set password_hash=%s, failed_logins=0, locked_until=null, updated_at=now() "
                 "where id=%s", (hash_password(pw), u["id"]))
    conn.execute("delete from sessions where user_id=%s", (u["id"],))
    event(conn, u["email"], "password_set", f"by {by}" if by and by != u["email"] else "")


def people(conn, now: dt.datetime | None = None) -> list[dict]:
    """Everyone in the manifest with what the people page shows (ADR-0005 item 6)."""
    now = now or dt.datetime.now(dt.UTC)
    rows = conn.execute("select u.*, (select max(at) from auth_events e where e.email = u.email and e.event = 'login')"
                        " as last_login from users u order by u.active desc, u.name").fetchall()
    return [public(u) | {"locked": bool(u["locked_until"] and u["locked_until"] > now),
                         "last_login": u["last_login"].isoformat() if u["last_login"] else None} for u in rows]


def authenticate(conn, email: str, pw: str, now: dt.datetime | None = None) -> dict:
    """Return the user, or raise AccountError with a message safe to show (no hint whether the email exists)."""
    now = now or dt.datetime.now(dt.UTC)
    u = get(conn, email or "")
    if u is None or not u["active"]:
        event(conn, (email or "").lower(), "login_failed", "unknown or inactive")
        raise AccountError("wrong email or password")
    if u["locked_until"] and u["locked_until"] > now:
        event(conn, u["email"], "login_failed", "locked")
        raise AccountError(f"too many wrong passwords; try again after {LOCK_MINUTES} minutes")
    if not check_password(pw, u["password_hash"]):
        failed = u["failed_logins"] + 1
        locked = now + dt.timedelta(minutes=LOCK_MINUTES) if failed >= MAX_FAILED else None
        conn.execute("update users set failed_logins=%s, locked_until=%s where id=%s",
                     (0 if locked else failed, locked, u["id"]))
        event(conn, u["email"], "locked" if locked else "login_failed", "wrong password")
        raise AccountError("wrong email or password")
    conn.execute("update users set failed_logins=0, locked_until=null where id=%s", (u["id"],))
    return u


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user: dict, method: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.UTC)
    token = secrets.token_urlsafe(32)
    conn.execute("insert into sessions (token_hash, user_id, expires_at, method) values (%s, %s, %s, %s)",
                 (_token_hash(token), user["id"], now + dt.timedelta(days=SESSION_DAYS), method))
    event(conn, user["email"], "login", method)
    return token


def session_user(conn, token: str | None, now: dt.datetime | None = None) -> dict | None:
    if not token:
        return None
    now = now or dt.datetime.now(dt.UTC)
    return conn.execute("select u.* from sessions s join users u on u.id = s.user_id "
                        "where s.token_hash=%s and s.expires_at > %s and u.active",
                        (_token_hash(token), now)).fetchone()


def end_session(conn, token: str | None) -> None:
    if token:
        r = conn.execute("delete from sessions where token_hash=%s returning user_id", (_token_hash(token),)).fetchone()
        if r:
            u = conn.execute("select email from users where id=%s", (r["user_id"],)).fetchone()
            event(conn, u["email"] if u else None, "logout")


def public(u: dict) -> dict:
    from wqops.hub import permissions as P  # noqa: PLC0415

    return {"email": u["email"], "name": u["name"], "roles": list(u["roles"]), "department": u["department"],
            "active": u["active"], "has_password": bool(u["password_hash"]), "permissions": sorted(P.of(u["roles"]))}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    url = os.environ.get("WQO_DB")
    if not url or not argv or argv[0] not in ("sync", "set-password", "set-owner-password", "list"):
        print(__doc__, file=sys.stderr)
        return 2
    conn = DB.connect(url)
    DB.migrate(conn)
    try:
        if argv[0] == "sync":
            r = sync(conn, C.load(os.environ["WQO_COMPANY_FILE"]))
            print(", ".join(f"{k} {len(v)}" for k, v in r.items()))
        elif argv[0] in ("set-password", "set-owner-password"):
            if argv[0] == "set-password":
                email = argv[1]
            else:
                m = C.load(os.environ["WQO_COMPANY_FILE"])
                sync(conn, m)
                email = next(p["email"] for p in m["people"] if "owner" in p["roles"])
            set_password(conn, email, sys.stdin.readline().rstrip("\n"))
            print(f"Password set for {email}")
        else:
            for u in conn.execute("select * from users order by email").fetchall():
                print(f"{u['email']:40} {'active' if u['active'] else 'inactive':9} {','.join(u['roles'])}")
    except (AccountError, C.CompanyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
