-- Anomalies (ADR-0007 item 5): found by rules after each sync; their life cycle and notes survive rebuilds.
create table anomalies (
    id           bigserial primary key,
    rule         text not null,
    subject_type text not null,
    subject_key  text not null,
    title        text not null,
    detail       text not null default '',
    severity     text not null check (severity in ('info', 'warn', 'critical')),
    status       text not null default 'open' check (status in ('open', 'ack', 'doing', 'resolved', 'closed')),
    vals         jsonb not null default '{}',
    related      jsonb not null default '[]',
    misses       integer not null default 0,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    ended_at     timestamptz
);
create unique index anomalies_active on anomalies (rule, subject_type, subject_key)
    where status in ('open', 'ack', 'doing');

create table anomaly_log (
    id         bigserial primary key,
    anomaly_id bigint not null references anomalies (id),
    at         timestamptz not null default now(),
    email      text,
    action     text not null,
    note       text not null default ''
);
create index anomaly_log_a on anomaly_log (anomaly_id, id);
