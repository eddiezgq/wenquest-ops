-- Quality module (ADR-0009): nonconformance life cycle, 8D, corrective and preventive actions.
alter table ncr_records add column severity text not null default 'minor' check (severity in ('minor', 'major'));
alter table ncr_records add column owner text;
alter table ncr_records add column containment text;
alter table ncr_records add column disposition text
    check (disposition in ('use_as_is', 'rework', 'return_to_supplier', 'scrap'));
alter table ncr_records add column disposition_qty numeric;
alter table ncr_records add column disposition_by text;
alter table ncr_records add column cancel_reason text;
alter table ncr_records add column closed_at timestamptz;
alter table ncr_records add column updated_at timestamptz not null default now();
alter table ncr_records add constraint ncr_status check (status in ('open', 'contained', 'dispositioned', 'closed',
                                                                    'cancelled'));

create table capas (
    id                  bigserial primary key,
    name                text not null unique,
    kind                text not null check (kind in ('corrective', 'preventive')),
    title               text not null,
    description         text not null default '',
    ncr_id              bigint references ncr_records (id),
    owner               text,
    status              text not null default 'open' check (status in ('open', 'in_progress', 'verification', 'closed')),
    verification_method text,
    verification_result text check (verification_result in ('effective', 'ineffective')),
    verified_by         text,
    verified_at         timestamptz,
    created_by          text not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    closed_at           timestamptz
);

create table capa_actions (
    id      bigserial primary key,
    capa_id bigint not null references capas (id),
    text    text not null,
    owner   text,
    due     date,
    done    boolean not null default false,
    done_by text,
    done_at timestamptz
);

create table eightd (
    ncr_id       bigint primary key references ncr_records (id),
    sections     jsonb not null default '{}',
    complete     boolean not null default false,
    completed_by text,
    completed_at timestamptz,
    updated_at   timestamptz not null default now()
);

-- what happened to each quality record: who, when, what
create table quality_log (
    id      bigserial primary key,
    kind    text not null check (kind in ('ncr', 'capa')),
    ref_id  bigint not null,
    at      timestamptz not null default now(),
    email   text,
    action  text not null,
    note    text not null default ''
);
create index quality_log_ref on quality_log (kind, ref_id, id);
