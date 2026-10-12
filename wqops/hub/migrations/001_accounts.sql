-- Accounts, sessions and sign-in events (ADR-0005)
create table if not exists users (
    id            bigserial primary key,
    email         text not null unique,          -- stored lower-case
    name          text not null,
    roles         text[] not null default '{}',
    department    text,
    password_hash text,
    active        boolean not null default true,
    failed_logins integer not null default 0,
    locked_until  timestamptz,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table if not exists sessions (
    token_hash  text primary key,
    user_id     bigint not null references users(id) on delete cascade,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null,
    method      text not null
);
create index if not exists sessions_user on sessions(user_id);

create table if not exists auth_events (
    id      bigserial primary key,
    at      timestamptz not null default now(),
    email   text,
    event   text not null,      -- login, login_failed, locked, logout, password_set, user_created, ...
    detail  text
);
