-- Measuring equipment and calibration, step 17f (ADR-0017; dee-qms PLAN-CAL): the equipment list, calibrations
-- recorded and approved by someone else (signed), equipment found out of tolerance taken out of use with the
-- inspections it measured since its last good calibration listed for a signed assessment, and incoming inspection
-- naming the equipment it measured with. Nothing is deleted.

create table gauges (
    id              bigserial primary key,
    code            text not null,
    name            text not null,
    kind            text not null default '',
    range_text      text not null default '',
    location        text not null default '',
    owner           text,
    interval_months integer not null check (interval_months between 1 and 120),
    acceptance      text not null default '',      -- the company's acceptance criteria
    traceability    text not null default '',      -- to which standards calibration is traceable
    status          text not null default 'out_of_service'
                    check (status in ('out_of_service', 'in_service', 'retired')),
    last_pass       date,                          -- the last approved good calibration
    next_due        date,
    retired_reason  text,
    created_by      text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    check (status <> 'in_service' or (last_pass is not null and next_due is not null)),
    check (status <> 'retired' or retired_reason is not null)
);
create unique index gauges_code on gauges (lower(code));
create trigger gauges_no_delete before delete on gauges for each row execute function wqo_append_only();

create table gauge_calibrations (
    id           bigserial primary key,
    gauge_id     bigint not null references gauges (id),
    done_on      date not null,
    done_by      text not null,                    -- in house, or the laboratory
    certificate  text not null default '',
    result       text not null check (result in ('pass', 'fail')),
    as_found     text not null default '',
    as_left      text not null default '',
    status       text not null default 'draft' check (status in ('draft', 'approved')),
    recorded_by  text not null,
    changed_by   text not null,
    approved_by  text,
    approved_at  timestamptz,
    created_at   timestamptz not null default now(),
    check (status <> 'approved' or (approved_by is not null and approved_at is not null
                                    and approved_by <> recorded_by and approved_by <> changed_by))
);
create index gauge_calibrations_gauge on gauge_calibrations (gauge_id, id);

create or replace function wqo_gauge_calibration_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'calibrations are kept';
    end if;
    if old.status = 'approved' then
        raise exception 'calibration % is approved: it cannot change', old.id;
    end if;
    if new.gauge_id <> old.gauge_id or new.recorded_by <> old.recorded_by then
        raise exception 'calibration % keeps its equipment and who recorded it', old.id;
    end if;
    return new;
end $$;
create trigger gauge_calibrations_kept before update or delete on gauge_calibrations
    for each row execute function wqo_gauge_calibration_kept();

-- equipment found out of tolerance: what it measured since its last good calibration, assessed and signed
create table gauge_impacts (
    id             bigserial primary key,
    gauge_id       bigint not null references gauges (id),
    calibration_id bigint not null unique references gauge_calibrations (id),
    since          date,                           -- the last good calibration before the failure
    inspections    jsonb not null default '[]',    -- [{id, name, item_code, signed_at, result}]
    status         text not null default 'open' check (status in ('open', 'assessed')),
    conclusion     text not null default '',
    ncr_id         bigint references ncr_records (id),
    assessed_by    text,
    assessed_at    timestamptz,
    created_at     timestamptz not null default now(),
    check (status <> 'assessed' or (assessed_by is not null and conclusion <> ''))
);
create or replace function wqo_gauge_impact_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'out-of-tolerance assessments are kept';
    end if;
    if old.status = 'assessed' then
        raise exception 'the assessment of % is signed: it cannot change', old.id;
    end if;
    if (new.gauge_id, new.calibration_id, new.since, new.inspections::text) is distinct from
            (old.gauge_id, old.calibration_id, old.since, old.inspections::text) then
        raise exception 'what the equipment measured is fixed';
    end if;
    return new;
end $$;
create trigger gauge_impacts_kept before update or delete on gauge_impacts
    for each row execute function wqo_gauge_impact_kept();

-- the equipment an incoming inspection measured each measured characteristic with, as it stood then
create table iqc_gauges (
    inspection_id  bigint not null references iqc_inspections (id),
    characteristic text not null,
    gauge_id       bigint not null references gauges (id),
    gauge_code     text not null,
    next_due       date,
    primary key (inspection_id, characteristic)
);
create or replace function wqo_iqc_gauge_kept() returns trigger language plpgsql as $$
begin
    if (select status from iqc_inspections where id = coalesce(new.inspection_id, old.inspection_id)) <> 'in_progress'
            then
        raise exception 'the inspection is signed: the equipment it used is fixed';
    end if;
    return coalesce(new, old);
end $$;
create trigger iqc_gauges_kept before insert or update or delete on iqc_gauges
    for each row execute function wqo_iqc_gauge_kept();

create table gauge_log (
    id       bigserial primary key,
    gauge_id bigint not null references gauges (id),
    at       timestamptz not null default now(),
    email    text,
    action   text not null,
    note     text not null default ''
);
create index gauge_log_gauge on gauge_log (gauge_id, id);
create trigger gauge_log_append_only before update or delete on gauge_log
    for each row execute function wqo_append_only();
