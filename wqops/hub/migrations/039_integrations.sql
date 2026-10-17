-- 20d (ADR-0020): the interface for machines and other systems (an MES, a test bench, a gauge station). Each has its
-- own access token, limited to what it may do and revocable; only a hash of the token is kept. What a machine sends
-- waits in an inbox until a person accepts it, signed with their own password, into the inspection or the production
-- record: a machine cannot sign. Events (lots decided, nonconformance reports opened) are written by the database
-- itself and read by the other system in order; WenQuest Ops sends nothing out on its own.

create table integration_tokens (
    id           bigserial primary key,
    name         text not null check (name <> ''),
    scopes       text[] not null check (scopes <> '{}' and scopes <@ array['measurements:send', 'production:send',
                                                                            'events:read']),
    token_hash   text not null unique,              -- sha256 of the token; the token is shown once
    prefix       text not null,                     -- its first characters, to tell tokens apart
    created_by   text not null,
    created_at   timestamptz not null default now(),
    revoked_by   text,
    revoked_at   timestamptz,
    revoke_note  text,
    last_used_at timestamptz,
    check ((revoked_by is null) = (revoked_at is null))
);
create unique index integration_tokens_name on integration_tokens (lower(name)) where revoked_at is null;

create or replace function wqo_integration_token_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'access tokens are kept: revoke it';
    end if;
    if (new.name, new.scopes, new.token_hash, new.prefix, new.created_by, new.created_at)
            is distinct from (old.name, old.scopes, old.token_hash, old.prefix, old.created_by, old.created_at)
            or (old.revoked_at is not null and (new.revoked_by, new.revoked_at, new.revoke_note)
                is distinct from (old.revoked_by, old.revoked_at, old.revoke_note)) then
        raise exception 'access token % cannot change: revoke it and make a new one', old.id;
    end if;
    return new;
end $$;
create trigger integration_tokens_kept before update or delete on integration_tokens
    for each row execute function wqo_integration_token_kept();

-- what a machine sent: kept as it came, decided once by a person
create table integration_inbox (
    id          bigserial primary key,
    token_id    bigint not null references integration_tokens (id),
    kind        text not null check (kind in ('measurements', 'production_step')),
    target      text not null,                     -- the inspection or the production record it is for
    payload     jsonb not null,
    status      text not null default 'pending' check (status in ('pending', 'accepted', 'rejected')),
    received_at timestamptz not null default now(),
    decided_by  text,
    decided_at  timestamptz,
    note        text not null default '',
    result      text,                              -- what accepting it wrote
    check ((status = 'pending') = (decided_by is null) and (decided_by is null) = (decided_at is null)),
    check (status <> 'rejected' or note <> '')
);
create index integration_inbox_pending on integration_inbox (status, id);

create or replace function wqo_integration_inbox_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'what machines send is kept';
    end if;
    if (new.token_id, new.kind, new.target, new.payload::text, new.received_at)
            is distinct from (old.token_id, old.kind, old.target, old.payload::text, old.received_at) then
        raise exception 'what a machine sent cannot change';
    end if;
    if old.status <> 'pending' and to_jsonb(new) is distinct from to_jsonb(old) then
        raise exception 'inbox item % is %: it cannot change', old.id, old.status;
    end if;
    return new;
end $$;
create trigger integration_inbox_kept before update or delete on integration_inbox
    for each row execute function wqo_integration_inbox_kept();

-- every call a token made
create table integration_calls (
    id        bigserial primary key,
    token_id  bigint references integration_tokens (id),
    method    text not null,
    path      text not null,
    status    integer not null,
    at        timestamptz not null default now()
);
create index integration_calls_token on integration_calls (token_id, id);
create trigger integration_calls_append_only before update or delete on integration_calls
    for each row execute function wqo_append_only();

-- events for other systems, in order; written by triggers so no module can forget one
create table hub_events (
    id        bigserial primary key,
    kind      text not null,
    ref_kind  text not null,
    ref_id    bigint not null,
    ref_name  text not null,
    data      jsonb not null default '{}',
    at        timestamptz not null default now()
);
create trigger hub_events_append_only before update or delete on hub_events
    for each row execute function wqo_append_only();

create or replace function wqo_event_iqc() returns trigger language plpgsql as $$
begin
    if new.status in ('released', 'rejected') and old.status is distinct from new.status then
        insert into hub_events (kind, ref_kind, ref_id, ref_name, data) values
            ('incoming_lot.' || new.status, 'incoming_inspection', new.id, new.name,
             jsonb_build_object('item_code', new.item_code, 'lot_no', new.lot_no, 'supplier', new.supplier,
                                'receipt', new.receipt, 'lot_qty', new.lot_qty));
    end if;
    return new;
end $$;
create trigger iqc_inspections_events after update on iqc_inspections
    for each row execute function wqo_event_iqc();

create or replace function wqo_event_production() returns trigger language plpgsql as $$
begin
    if new.status in ('released', 'rejected') and old.status is distinct from new.status then
        insert into hub_events (kind, ref_kind, ref_id, ref_name, data) values
            ('production_lot.' || new.status, 'production_record', new.id, new.name,
             jsonb_build_object('item_code', new.item_code, 'lot_no', new.lot_no, 'work_order', new.work_order,
                                'good_qty', new.good_qty, 'scrap_qty', new.scrap_qty));
    end if;
    return new;
end $$;
create trigger prod_records_events after update on prod_records
    for each row execute function wqo_event_production();

create or replace function wqo_event_ncr() returns trigger language plpgsql as $$
begin
    insert into hub_events (kind, ref_kind, ref_id, ref_name, data) values
        ('ncr.opened', 'ncr', new.id, new.name,
         jsonb_build_object('title', new.title, 'item_code', new.item_code, 'inspection', new.inspection));
    return new;
end $$;
create trigger ncr_records_events after insert on ncr_records
    for each row execute function wqo_event_ncr();

-- readings a person accepted from a machine name that inbox item
alter table iqc_readings add column inbox_id bigint references integration_inbox (id);
