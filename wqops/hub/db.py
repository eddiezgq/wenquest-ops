"""PostgreSQL access for the hub: connections and ordered SQL migrations (wqops/hub/migrations/NNN_name.sql)."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply migrations not yet applied, in file-name order; return the names applied."""
    conn.execute("create table if not exists schema_migrations (name text primary key, applied_at timestamptz "
                 "not null default now())")
    done = {r["name"] for r in conn.execute("select name from schema_migrations").fetchall()}
    applied = []
    for f in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name in done:
            continue
        with conn.transaction():
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
        applied.append(f.name)
    return applied
