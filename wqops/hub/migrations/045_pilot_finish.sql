-- ADR-0025 25d: a first password set by someone else must be changed; problems people report from the workspace.
alter table users add column if not exists must_change boolean not null default false;
create table if not exists feedback (
    id         bigserial primary key,
    email      text not null,
    page       text not null default '',
    text       text not null,
    errors     jsonb not null default '[]',
    created_at timestamptz not null default now(),
    sent_at    timestamptz
);
create index if not exists feedback_unsent on feedback (id) where sent_at is null;
