-- Production records, step 17i (ADR-0017; dee-qms PLAN-DHR): a controlled template of steps (checks, measurements
-- with limits, records) is activated with a signature and then fixed; each lot of an ERPNext item is made against an
-- active template whose steps are copied, recorded one by one with the operator's password, judged by code against
-- the limits, and released or rejected by Quality with a signature. A failed step needs a nonconformance report.
-- Material lots come from incoming inspections that were released. Nothing is deleted.

create table prod_templates (
    id           bigserial primary key,
    code         text not null check (code <> ''),
    version      integer not null default 1 check (version >= 1),
    previous_id  bigint references prod_templates (id),
    item_code    text not null check (item_code <> ''),
    title        text not null default '',
    documents    jsonb not null default '[]',   -- numbers of the controlled documents the steps follow
    materials    jsonb not null default '[]',   -- item codes a lot must consume
    status       text not null default 'draft' check (status in ('draft', 'active', 'retired', 'withdrawn')),
    editors      text[] not null default '{}',
    activated_by text,
    activated_at timestamptz,
    fingerprint  text,
    created_by   text not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (code, version),
    check (status not in ('active', 'retired') or (activated_by is not null and activated_at is not null
           and fingerprint is not null)),
    check (status in ('active', 'retired') or (activated_by is null and fingerprint is null))
);
create unique index prod_templates_one_draft on prod_templates (code) where status = 'draft';
create unique index prod_templates_one_active on prod_templates (code) where status = 'active';

create or replace function wqo_prod_template_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'production templates are kept: withdraw a draft or retire a version';
    end if;
    if (new.code, new.version, new.previous_id, new.created_by, new.created_at)
            is distinct from (old.code, old.version, old.previous_id, old.created_by, old.created_at) then
        raise exception 'template % keeps its code, version and origin', old.code;
    end if;
    if not (old.editors <@ new.editors) then
        raise exception 'template % keeps everyone who edited it', old.code;
    end if;
    if old.status <> 'draft' and (to_jsonb(new) - 'status' - 'updated_at') is distinct from
            (to_jsonb(old) - 'status' - 'updated_at') then
        raise exception 'template % v% is %: it is fixed (start a new version)', old.code, old.version, old.status;
    end if;
    if old.status = 'draft' and new.status = 'active' and not exists (
            select 1 from signatures where kind = 'prod_template' and ref_id = old.id and email = new.activated_by) then
        raise exception 'template % is activated only with a signature', old.code;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('active', 'withdrawn'))
            or (old.status = 'active' and new.status = 'retired')) then
        raise exception 'template % cannot go from % to %', old.code, old.status, new.status;
    end if;
    return new;
end $$;
create trigger prod_templates_kept before update or delete on prod_templates
    for each row execute function wqo_prod_template_kept();

-- a template starts as a draft
create or replace function wqo_prod_template_new() returns trigger language plpgsql as $$
begin
    if new.status <> 'draft' or new.activated_by is not null or new.fingerprint is not null then
        raise exception 'a template starts as a draft';
    end if;
    return new;
end $$;
create trigger prod_templates_new before insert on prod_templates
    for each row execute function wqo_prod_template_new();

create table prod_template_steps (
    id             bigserial primary key,
    template_id    bigint not null references prod_templates (id),
    seq            integer not null,
    name           text not null check (name <> ''),
    instruction    text not null default '',
    kind           text not null check (kind in ('check', 'measure', 'record')),
    low            numeric,
    high           numeric,
    unit           text not null default '',
    gauge_required boolean not null default false,
    unique (template_id, seq),
    check (kind = 'measure' or (low is null and high is null and not gauge_required)),
    check (low is null or high is null or low <= high)
);

create or replace function wqo_prod_template_step_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    select status into st from prod_templates where id = (case when tg_op = 'DELETE' then old.template_id
                                                              else new.template_id end) for share;
    if st <> 'draft' then
        raise exception 'the template is %: its steps are fixed', st;
    end if;
    if tg_op = 'UPDATE' and new.template_id <> old.template_id then
        raise exception 'a step stays in its template';
    end if;
    return case when tg_op = 'DELETE' then old else new end;
end $$;
create trigger prod_template_steps_kept before insert or update or delete on prod_template_steps
    for each row execute function wqo_prod_template_step_kept();

-- the production record of one lot (device history record)
create table prod_records (
    id              bigserial primary key,
    name            text not null unique,
    template_id     bigint not null references prod_templates (id),
    template_print  text not null,                -- the template's fingerprint when the lot was started
    item_code       text not null,
    lot_no          text not null check (lot_no <> ''),
    work_order      text,                         -- the ERPNext work order, if there is one
    planned_qty     integer not null check (planned_qty >= 1),
    good_qty        integer not null default 0 check (good_qty >= 0),
    scrap_qty       integer not null default 0 check (scrap_qty >= 0),
    status          text not null default 'in_production'
                    check (status in ('in_production', 'qa_review', 'released', 'rejected', 'cancelled')),
    involved        text[] not null default '{}', -- everyone who recorded a step or a material
    submitted_by    text,
    submitted_at    timestamptz,
    decided_by      text,
    decided_at      timestamptz,
    decision_note   text not null default '',
    fingerprint     text,                         -- of the steps, materials and quantities when decided
    cancel_reason   text,
    created_by      text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    check (good_qty + scrap_qty <= planned_qty),
    check (status in ('in_production', 'cancelled') or (submitted_by is not null and submitted_at is not null)),
    check (status not in ('released', 'rejected') or (decided_by is not null and decided_at is not null
           and fingerprint is not null and not (decided_by = any(involved)))),
    check (status <> 'rejected' or decision_note <> ''),
    check (status <> 'cancelled' or cancel_reason is not null)
);
create unique index prod_records_lot on prod_records (item_code, lower(btrim(lot_no))) where status <> 'cancelled';

create or replace function wqo_prod_record_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'production records are kept: cancel one with a reason';
    end if;
    if old.status in ('released', 'rejected', 'cancelled') then
        raise exception 'production record % is %: it cannot change', old.name, old.status;
    end if;
    if (new.name, new.template_id, new.template_print, new.item_code, new.lot_no, new.planned_qty, new.created_by,
        new.created_at) is distinct from (old.name, old.template_id, old.template_print, old.item_code, old.lot_no,
        old.planned_qty, old.created_by, old.created_at) then
        raise exception 'production record % keeps its lot, template and quantity planned', old.name;
    end if;
    if not (old.involved <@ new.involved) then
        raise exception 'production record % keeps everyone who recorded in it', old.name;
    end if;
    if old.status <> 'in_production' and (new.good_qty, new.scrap_qty, new.work_order)
            is distinct from (old.good_qty, old.scrap_qty, old.work_order) then
        raise exception 'production record % is submitted: its quantities are fixed', old.name;
    end if;
    if new.status in ('released', 'rejected') and old.status = 'qa_review' and not exists (
            select 1 from signatures where kind = 'prod_record' and ref_id = old.id and email = new.decided_by) then
        raise exception 'production record % is decided only with a signature', old.name;
    end if;
    if not (old.status = new.status
            or (old.status = 'in_production' and new.status in ('qa_review', 'cancelled'))
            or (old.status = 'qa_review' and new.status in ('in_production', 'released', 'rejected'))) then
        raise exception 'production record % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger prod_records_kept before update or delete on prod_records
    for each row execute function wqo_prod_record_kept();

-- a record starts in production, from an active template, with nothing recorded or decided
create or replace function wqo_prod_record_new() returns trigger language plpgsql as $$
begin
    if new.status <> 'in_production' or new.submitted_by is not null or new.decided_by is not null
            or new.fingerprint is not null or new.good_qty <> 0 or new.scrap_qty <> 0 or new.involved <> '{}' then
        raise exception 'a production record starts in production with nothing recorded';
    end if;
    if not exists (select 1 from prod_templates where id = new.template_id and status = 'active'
                   and fingerprint = new.template_print) then
        raise exception 'a production record starts from an active template';
    end if;
    return new;
end $$;
create trigger prod_records_new before insert on prod_records
    for each row execute function wqo_prod_record_new();

create table prod_steps (
    id             bigserial primary key,
    record_id      bigint not null references prod_records (id),
    seq            integer not null,
    name           text not null,
    instruction    text not null default '',
    kind           text not null check (kind in ('check', 'measure', 'record')),
    low            numeric,
    high           numeric,
    unit           text not null default '',
    gauge_required boolean not null default false,
    result         text check (result in ('pass', 'fail')),   -- what the operator chose (checks)
    value          numeric,                                    -- the reading (measurements), as stored
    text_value     text,                                       -- what was written (records)
    verdict        text check (verdict in ('pass', 'fail')),  -- decided by code
    gauge_id       bigint references gauges (id),
    gauge_code     text,
    gauge_due      date,
    done_by        text,
    done_at        timestamptz,
    ncr_id         bigint references ncr_records (id),
    unique (record_id, seq),
    check ((done_by is null) = (verdict is null) and (done_by is null) = (done_at is null)),
    check (verdict is null or kind <> 'measure' or value is not null),
    check (gauge_id is null or kind = 'measure')
);

create or replace function wqo_prod_step_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    if tg_op = 'DELETE' then
        raise exception 'production steps are kept';
    end if;
    if tg_op = 'INSERT' then
        -- steps are copied when the lot starts: into a record in production, nothing recorded yet
        select status into st from prod_records where id = new.record_id for share;
        if st <> 'in_production' or new.done_by is not null or new.verdict is not null or new.ncr_id is not null
                or new.gauge_id is not null or exists (select 1 from prod_steps where record_id = new.record_id
                                                       and done_by is not null) then
            raise exception 'steps are added when a lot starts';
        end if;
        return new;
    end if;
    select status into st from prod_records where id = old.record_id for share;
    if (to_jsonb(new) - 'ncr_id') is distinct from (to_jsonb(old) - 'ncr_id') then
        if st <> 'in_production' then
            raise exception 'the production record is %: its steps are fixed', st;
        end if;
        if old.done_by is not null then
            raise exception 'step % is recorded: it cannot change', old.seq;
        end if;
        if (new.id, new.record_id, new.seq, new.name, new.instruction, new.kind, new.low, new.high, new.unit,
            new.gauge_required) is distinct from (old.id, old.record_id, old.seq, old.name, old.instruction, old.kind,
            old.low, old.high, old.unit, old.gauge_required) then
            raise exception 'step % keeps what the template said', old.seq;
        end if;
    end if;
    if new.ncr_id is distinct from old.ncr_id and st not in ('in_production', 'qa_review') then
        raise exception 'the production record is %: its steps are fixed', st;
    end if;
    return new;
end $$;
create trigger prod_steps_kept before insert or update or delete on prod_steps
    for each row execute function wqo_prod_step_kept();

-- material lots a production lot consumed: released incoming inspections
create table prod_materials (
    id            bigserial primary key,
    record_id     bigint not null references prod_records (id),
    item_code     text not null,
    inspection_id bigint not null references iqc_inspections (id),
    lot_no        text not null default '',    -- of the incoming lot, as it was
    supplier      text,
    qty           numeric not null check (qty > 0),
    added_by      text not null,
    added_at      timestamptz not null default now()
);
create index prod_materials_lot on prod_materials (inspection_id);

create or replace function wqo_prod_material_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    if tg_op <> 'INSERT' then
        raise exception 'material records are kept';
    end if;
    select status into st from prod_records where id = new.record_id for share;
    if st <> 'in_production' then
        raise exception 'the production record is %: materials are added while in production', st;
    end if;
    return new;
end $$;
create trigger prod_materials_kept before insert or update or delete on prod_materials
    for each row execute function wqo_prod_material_kept();

create table prod_log (
    id        bigserial primary key,
    kind      text not null check (kind in ('template', 'record')),
    ref_id    bigint not null,
    at        timestamptz not null default now(),
    email     text,
    action    text not null,
    note      text not null default ''
);
create index prod_log_ref on prod_log (kind, ref_id, id);
create trigger prod_log_append_only before update or delete on prod_log
    for each row execute function wqo_append_only();

-- equipment found out of tolerance also lists the production lots it measured
alter table gauge_impacts add column production jsonb not null default '[]';
create or replace function wqo_gauge_impact_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'out-of-tolerance assessments are kept';
    end if;
    if old.status = 'assessed' then
        raise exception 'the assessment of % is signed: it cannot change', old.id;
    end if;
    if (new.gauge_id, new.calibration_id, new.since, new.inspections::text, new.production::text) is distinct from
            (old.gauge_id, old.calibration_id, old.since, old.inspections::text, old.production::text) then
        raise exception 'what the equipment measured is fixed';
    end if;
    return new;
end $$;
