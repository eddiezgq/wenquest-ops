-- Quality principles (ADR-0010): signatures, append-only logs, disposition types as configuration, staged CAPA.

create table signatures (
    id       bigserial primary key,
    email    text not null,
    name     text not null,          -- the signer's name at the time of signing
    meaning  text not null,          -- e.g. "Disposition approved", "NCR closed"
    kind     text not null,          -- ncr | capa
    ref_id   bigint not null,
    ref_name text not null,
    at       timestamptz not null default now()
);
create index signatures_ref on signatures (kind, ref_id, id);

create function wqo_append_only() returns trigger language plpgsql as $$
begin
    raise exception '% is append-only: records are added, never changed or deleted', tg_table_name;
end $$;
create trigger signatures_append_only before update or delete on signatures
    for each row execute function wqo_append_only();
create trigger quality_log_append_only before update or delete on quality_log
    for each row execute function wqo_append_only();

-- disposition types are configuration (the starting four match the dee-qms demo data)
create table ncr_disposition_types (
    code              text primary key,
    name              text not null,
    requires_approval boolean not null default false,
    active            boolean not null default true,
    sort              integer not null default 0
);
insert into ncr_disposition_types (code, name, requires_approval, sort) values
    ('return_to_supplier', 'Return to supplier', false, 1),
    ('rework', 'Rework / sort', false, 2),
    ('scrap', 'Scrap', false, 3),
    ('use_as_is', 'Use as is (concession)', true, 4);

alter table ncr_records drop constraint ncr_status;
alter table ncr_records drop constraint ncr_records_disposition_check;
alter table ncr_records add constraint ncr_status check (status in ('open', 'contained', 'pending_approval',
                                                                    'dispositioned', 'closed', 'cancelled'));
alter table ncr_records add constraint ncr_disposition_type foreign key (disposition)
    references ncr_disposition_types (code);
alter table ncr_records add column disposition_reason text;
alter table ncr_records add column approved_by text;
alter table ncr_records add column approved_at timestamptz;
alter table ncr_records add column closed_by text;

-- CAPA in stages: draft -> investigation -> implementation -> effectiveness -> closed; cancelled
alter table capas drop constraint capas_status_check;
update capas set status = case status when 'open' then 'draft' when 'in_progress' then 'implementation'
                                      when 'verification' then 'effectiveness' else status end;
alter table capas add constraint capas_status_check check (status in ('draft', 'investigation', 'implementation',
                                                                      'effectiveness', 'closed', 'cancelled'));
alter table capas add column risk text check (risk in ('low', 'medium', 'high'));
alter table capas add column containment text;
alter table capas add column root_cause text;
alter table capas add column cancel_reason text;
alter table capas add column closed_by text;

-- one CAPA may cover several NCRs
create table capa_ncrs (
    capa_id bigint not null references capas (id),
    ncr_id  bigint not null references ncr_records (id),
    primary key (capa_id, ncr_id)
);
insert into capa_ncrs (capa_id, ncr_id) select id, ncr_id from capas where ncr_id is not null;
alter table capas drop column ncr_id;

alter table capa_actions add column kind text not null default 'corrective'
    check (kind in ('correction', 'corrective', 'preventive'));
alter table capa_actions add column evidence text;
