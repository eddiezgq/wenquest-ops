-- Incoming inspection and sampling, step 17b (ADR-0017; dee-qms PLAN-IQC, PLAN-SEVERITY). The sampling table, the
-- inspection plans and the switching rules are the company's configuration; the judgement is code
-- (wqops/hub/quality/sampling.py). Records are kept: nothing is deleted, signed results cannot change.

-- one row of the company's sampling table, entered from its own controlled copy of the standard it uses
create table iqc_sampling_rows (
    id          bigserial primary key,
    aql         numeric not null check (aql > 0),
    level       text not null default 'normal' check (level in ('normal', 'tightened', 'reduced')),
    lot_min     integer not null check (lot_min >= 1),
    lot_max     integer not null,
    n           integer not null check (n >= 1),
    ac          integer not null check (ac >= 0),
    re          integer not null,
    source      text not null default '',          -- the standard (title, edition) the row was checked against
    verified_by text,
    verified_at timestamptz,
    active      boolean not null default true,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    check (lot_max >= lot_min), check (re = ac + 1),
    check ((verified_by is null) = (verified_at is null)),
    check (verified_by is null or source <> '')
);

-- an inspection plan for an item: its AQL and characteristics; frozen once enabled, changed by a new version
create table iqc_plans (
    id              bigserial primary key,
    item_code       text not null,
    version         integer not null,
    status          text not null default 'draft' check (status in ('draft', 'enabled', 'retired', 'discarded')),
    aql             numeric not null check (aql > 0),
    characteristics jsonb not null,               -- [{name, kind: measured|attribute, lsl, usl, unit, method}]
    note            text not null default '',
    fingerprint     text,
    created_by      text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    enabled_by      text,
    enabled_at      timestamptz,
    retired_at      timestamptz,
    unique (item_code, version)
);
create unique index iqc_plans_one_enabled on iqc_plans (item_code) where status = 'enabled';

create or replace function wqo_iqc_plan_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'inspection plans are kept: discard a draft or retire a plan';
    end if;
    if old.status <> 'draft' and (new.item_code, new.version, new.aql, new.characteristics::text, new.fingerprint,
            new.enabled_by, new.enabled_at, new.created_by) is distinct from (old.item_code, old.version, old.aql,
            old.characteristics::text, old.fingerprint, old.enabled_by, old.enabled_at, old.created_by) then
        raise exception 'plan % is % and cannot change: make a new version', old.id, old.status;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('enabled', 'discarded'))
            or (old.status = 'enabled' and new.status = 'retired')) then
        raise exception 'plan % cannot go from % to %', old.id, old.status, new.status;
    end if;
    return new;
end $$;
create trigger iqc_plans_kept before update or delete on iqc_plans
    for each row execute function wqo_iqc_plan_kept();

-- one inspection of one lot
create table iqc_inspections (
    id              bigserial primary key,
    name            text not null unique,
    plan_id         bigint not null references iqc_plans (id),
    item_code       text not null,
    receipt         text,                         -- the ERPNext purchase receipt, if the lot came on one
    supplier        text,
    lot_no          text not null default '',
    lot_qty         integer not null check (lot_qty >= 1),
    level           text not null check (level in ('normal', 'tightened', 'reduced')),
    sampling_row_id bigint not null references iqc_sampling_rows (id),
    n               integer not null check (n >= 1),
    ac              integer not null,
    re              integer not null,
    unverified      boolean not null,             -- the sampling table row was not checked against its source
    status          text not null default 'in_progress'
                    check (status in ('in_progress', 'judged', 'released', 'rejected', 'void')),
    result          text check (result in ('accept', 'reject')),
    defectives      integer,
    signed_by       text,
    signed_at       timestamptz,
    decided_by      text,
    decided_at      timestamptz,
    decision_note   text not null default '',
    void_reason     text,
    draft_id        bigint references erp_drafts (id),
    ncr_id          bigint references ncr_records (id),
    created_by      text not null,
    created_at      timestamptz not null default now(),
    check (status <> 'released' or result = 'accept'),
    check (status <> 'rejected' or result = 'reject'),
    check (status not in ('judged', 'released', 'rejected') or (result is not null and defectives is not null
                                                               and signed_by is not null and signed_at is not null)),
    check (status not in ('released', 'rejected') or (decided_by is not null and decided_at is not null)),
    check (status <> 'void' or void_reason is not null)
);
create index iqc_inspections_lot on iqc_inspections (supplier, item_code, id);
create unique index iqc_inspections_one_per_line on iqc_inspections (receipt, item_code)
    where receipt is not null and status <> 'void';

create or replace function wqo_iqc_inspection_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'inspections are kept: void it with a reason';
    end if;
    if (new.name, new.plan_id, new.item_code, new.receipt, new.supplier, new.lot_qty, new.level, new.sampling_row_id,
            new.n, new.ac, new.re, new.unverified, new.created_by, new.created_at)
            is distinct from (old.name, old.plan_id, old.item_code, old.receipt, old.supplier, old.lot_qty, old.level,
            old.sampling_row_id, old.n, old.ac, old.re, old.unverified, old.created_by, old.created_at) then
        raise exception 'inspection % cannot change what was sampled', old.id;
    end if;
    if old.status <> 'in_progress' and ((new.result, new.defectives, new.signed_by, new.signed_at, new.lot_no)
            is distinct from (old.result, old.defectives, old.signed_by, old.signed_at, old.lot_no)) then
        raise exception 'inspection % is signed: its result cannot change', old.id;
    end if;
    if old.status in ('released', 'rejected', 'void') and ((new.decided_by, new.decided_at, new.decision_note,
            new.void_reason) is distinct from (old.decided_by, old.decided_at, old.decision_note, old.void_reason)) then
        raise exception 'inspection % is %: the decision cannot change', old.id, old.status;
    end if;
    if (old.ncr_id is not null and new.ncr_id is distinct from old.ncr_id)
            or (old.draft_id is not null and new.draft_id is distinct from old.draft_id) then
        raise exception 'inspection % keeps its nonconformance report and its draft', old.id;
    end if;
    -- a signed inspection is decided, never voided: a rejected lot is not sampled again
    if not (old.status = new.status or (old.status = 'in_progress' and new.status in ('judged', 'void'))
            or (old.status = 'judged' and new.status in ('released', 'rejected'))) then
        raise exception 'inspection % cannot go from % to %', old.id, old.status, new.status;
    end if;
    return new;
end $$;
create trigger iqc_inspections_kept before update or delete on iqc_inspections
    for each row execute function wqo_iqc_inspection_kept();

-- the readings: made when the inspection starts (n sample units x the plan's characteristics)
create table iqc_readings (
    id             bigserial primary key,
    inspection_id  bigint not null references iqc_inspections (id),
    sample         integer not null,
    characteristic text not null,
    value          numeric,
    passed         boolean,
    entered_by     text,
    entered_at     timestamptz,
    unique (inspection_id, sample, characteristic)
);

create or replace function wqo_iqc_reading_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'readings are kept';
    end if;
    if tg_op = 'INSERT' then
        if (select status from iqc_inspections where id = new.inspection_id) <> 'in_progress' then
            raise exception 'the inspection is signed: no readings can be added';
        end if;
        return new;
    end if;
    if (select status from iqc_inspections where id = old.inspection_id for share) <> 'in_progress' then
        raise exception 'the inspection is signed: its readings cannot change';
    end if;
    if (new.inspection_id, new.sample, new.characteristic) is distinct from
            (old.inspection_id, old.sample, old.characteristic) then
        raise exception 'a reading belongs to its sample and characteristic';
    end if;
    return new;
end $$;
create trigger iqc_readings_kept before insert or update or delete on iqc_readings
    for each row execute function wqo_iqc_reading_kept();

-- a sampling table row that an inspection used keeps its numbers and its source
create or replace function wqo_iqc_row_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'sampling table rows are kept: archive it';
    end if;
    if exists (select 1 from iqc_inspections where sampling_row_id = old.id) and (
            (new.aql, new.level, new.lot_min, new.lot_max, new.n, new.ac, new.re, new.source) is distinct from
            (old.aql, old.level, old.lot_min, old.lot_max, old.n, old.ac, old.re, old.source)
            or (old.verified_by is not null and new.verified_by is null)) then
        raise exception 'sampling table row % is used by an inspection: archive it and add a new one', old.id;
    end if;
    return new;
end $$;
create trigger iqc_sampling_rows_kept before update or delete on iqc_sampling_rows
    for each row execute function wqo_iqc_row_kept();

-- switching rules: configuration, never deleted (switched off instead); starting values are defaults to change
create table iqc_switch_rules (
    id         bigserial primary key,
    from_level text not null check (from_level in ('normal', 'tightened', 'reduced')),
    to_level   text not null check (to_level in ('normal', 'tightened', 'reduced')),
    condition  text not null check (condition in ('window_rejected', 'consecutive_accepted', 'any_rejected')),
    n          integer,
    k          integer,
    active     boolean not null default true,
    sort       integer not null default 0,
    check (from_level <> to_level), check (not (from_level = 'reduced' and to_level = 'tightened'))
);
create trigger iqc_switch_rules_kept before delete on iqc_switch_rules
    for each row execute function wqo_append_only();
insert into iqc_switch_rules (from_level, to_level, condition, n, k, sort) values
    ('normal', 'tightened', 'window_rejected', 5, 2, 1),
    ('tightened', 'normal', 'consecutive_accepted', 5, null, 2),
    ('normal', 'reduced', 'consecutive_accepted', 10, null, 3),
    ('reduced', 'normal', 'any_rejected', null, null, 4);

-- the inspection level of a supplier's item: the latest switch counts (normal when there is none)
create table iqc_level_switches (
    id         bigserial primary key,
    supplier   text not null,
    item_code  text not null,
    from_level text not null,
    to_level   text not null check (to_level in ('normal', 'tightened', 'reduced')),
    reason     text not null,
    suggestion text,                             -- what the rules suggested when the switch was made, and why
    history    text not null default '',         -- the lots at the old level, oldest first
    email      text not null,
    at         timestamptz not null default now()
);
create index iqc_level_switches_pair on iqc_level_switches (supplier, item_code, id);
create trigger iqc_level_switches_append_only before update or delete on iqc_level_switches
    for each row execute function wqo_append_only();

-- the company's choices for incoming inspection (who may do what); the latest row per key counts
create table iqc_settings (
    id    bigserial primary key,
    key   text not null,
    value jsonb not null,
    email text not null,
    at    timestamptz not null default now()
);
create trigger iqc_settings_append_only before update or delete on iqc_settings
    for each row execute function wqo_append_only();

-- what happened: rows, plans, inspections, rules
create table iqc_log (
    id     bigserial primary key,
    kind   text not null check (kind in ('row', 'plan', 'inspection', 'rule', 'setting')),
    ref_id bigint not null,
    at     timestamptz not null default now(),
    email  text,
    action text not null,
    note   text not null default ''
);
create index iqc_log_ref on iqc_log (kind, ref_id, id);
create trigger iqc_log_append_only before update or delete on iqc_log
    for each row execute function wqo_append_only();
