-- ERPNext sync (ADR-0006): per-doctype cursors, the event log, the current state, and the run log.

create table erp_sync_state (
    doctype         text primary key,
    cursor_modified text not null default '',
    cursor_name     text not null default '',
    updated_at      timestamptz not null default now()
);

create table erp_sync_runs (
    id          bigserial primary key,
    trigger     text not null,
    status      text not null default 'running' check (status in ('running', 'ok', 'error')),
    counts      jsonb not null default '{}',
    error       text,
    started_at  timestamptz not null default now(),
    finished_at timestamptz
);

create table erp_events (
    id          bigserial primary key,
    doctype     text not null,
    name        text not null,
    kind        text not null check (kind in ('created', 'updated', 'submitted', 'cancelled', 'deleted')),
    modified    text not null,
    docstatus   integer,
    data        jsonb,
    run_id      bigint references erp_sync_runs (id),
    recorded_at timestamptz not null default now()
);
create index erp_events_doc on erp_events (doctype, name, id);

create table erp_docs (
    doctype   text not null,
    name      text not null,
    modified  text not null,
    docstatus integer not null default 0,
    deleted   boolean not null default false,
    hash      text not null,
    data      jsonb not null,
    synced_at timestamptz not null default now(),
    primary key (doctype, name)
);
