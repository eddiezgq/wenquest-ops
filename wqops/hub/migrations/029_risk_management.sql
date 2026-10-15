-- Risk management, step 17h (ADR-0017; dee-qms PLAN-RISK): a risk management file per product lists hazards, the
-- situations they lead to and the harm; the company's own severity and probability levels and its matrix decide
-- whether each risk is acceptable (looked up, never typed). A file is approved with a signature by someone who did
-- not own or edit it; it is then fixed, with the criteria used and a fingerprint of its content. Revised as a new
-- version; the old one is superseded. Nothing is deleted.

create table risk_levels (
    id          bigserial primary key,
    kind        text not null check (kind in ('severity', 'probability')),
    rank        integer not null check (rank between 1 and 20),
    name        text not null check (name <> ''),
    description text not null default '',
    active      boolean not null default true,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    unique (kind, rank)
);

create or replace function wqo_risk_level_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'risk levels are kept: stop using one instead';
    end if;
    if (new.kind, new.rank) is distinct from (old.kind, old.rank) then
        raise exception 'a risk level keeps its kind and rank: add a new level instead';
    end if;
    return new;
end $$;
create trigger risk_levels_kept before update or delete on risk_levels
    for each row execute function wqo_risk_level_kept();

-- severity rank x probability rank -> acceptability; a missing cell means "not determined"
create table risk_matrix (
    severity    integer not null,
    probability integer not null,
    verdict     text not null check (verdict in ('acceptable', 'reduce', 'unacceptable')),
    updated_by  text not null,
    updated_at  timestamptz not null default now(),
    primary key (severity, probability)
);

create table risk_files (
    id           bigserial primary key,
    name         text not null,
    version      integer not null default 1 check (version >= 1),
    previous_id  bigint references risk_files (id),
    product      text not null check (product <> ''),
    scope        text not null default '',
    owner        text,
    conclusion   text not null default '',   -- the overall residual risk
    benefit_risk text not null default '',   -- the overall benefit-risk conclusion
    status       text not null default 'draft' check (status in ('draft', 'approved', 'superseded', 'withdrawn')),
    editors      text[] not null default '{}',
    approved_by  text,
    approved_at  timestamptz,
    criteria     jsonb,                      -- the levels and matrix used, as they were at approval
    fingerprint  text,                       -- SHA-256 of the content and criteria at approval
    withdraw_reason text,
    created_by   text not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (name, version),
    check (status not in ('approved', 'superseded') or (approved_by is not null and approved_at is not null
           and criteria is not null and fingerprint is not null and conclusion <> ''
           and approved_by is distinct from owner and approved_by <> created_by
           and not (approved_by = any(editors)))),
    check (status in ('approved', 'superseded') or (approved_by is null and approved_at is null and criteria is null
           and fingerprint is null)),
    check (status <> 'withdrawn' or withdraw_reason is not null)
);
-- one draft revision of a version at a time
create unique index risk_files_one_draft on risk_files (previous_id) where status = 'draft';

create or replace function wqo_risk_file_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'risk files are kept: withdraw a draft with a reason';
    end if;
    if (new.name, new.version, new.previous_id, new.created_by, new.created_at)
            is distinct from (old.name, old.version, old.previous_id, old.created_by, old.created_at) then
        raise exception 'risk file % keeps its number, version and origin', old.name;
    end if;
    if not (old.editors <@ new.editors) then
        raise exception 'risk file % keeps everyone who edited it', old.name;
    end if;
    -- once approved (or withdrawn) nothing changes but the step to superseded, when a newer version is approved
    if old.status <> 'draft' and (to_jsonb(new) - 'status' - 'updated_at') is distinct from
            (to_jsonb(old) - 'status' - 'updated_at') then
        raise exception 'risk file % v% is %: it is fixed (revise it as a new version)', old.name, old.version,
            old.status;
    end if;
    if old.status = 'approved' and new.status = 'superseded' and not exists (
            select 1 from risk_files where previous_id = old.id and status = 'approved') then
        raise exception 'risk file % v% is superseded only by an approved newer version', old.name, old.version;
    end if;
    -- approval is signed by the approver
    if old.status = 'draft' and new.status = 'approved' and not exists (
            select 1 from signatures where kind = 'risk_file' and ref_id = old.id and email = new.approved_by) then
        raise exception 'risk file % is approved only with the approver''s signature', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('approved', 'withdrawn'))
            or (old.status = 'approved' and new.status = 'superseded')) then
        raise exception 'risk file % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger risk_files_kept before update or delete on risk_files
    for each row execute function wqo_risk_file_kept();

create table risk_items (
    id               bigserial primary key,
    file_id          bigint not null references risk_files (id),
    seq              integer not null,
    hazard           text not null default '',
    situation        text not null default '',
    harm             text not null default '',
    severity         integer,
    probability      integer,
    controls         text not null default '',
    verification     text not null default '',
    res_severity     integer,
    res_probability  integer,
    benefit_risk     text not null default '',
    capa_id          bigint references capas (id),
    initial_verdict  text,       -- written at approval, from the matrix
    residual_verdict text,
    unique (file_id, seq),
    check ((res_severity is null) = (res_probability is null))
);

create or replace function wqo_risk_item_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    -- the file row is shared-locked: an approval in progress (which locks it) finishes first
    select status into st from risk_files where id = (case when tg_op = 'DELETE' then old.file_id
                                                          else new.file_id end) for share;
    if st <> 'draft' then
        raise exception 'the risk file is %: its items are fixed', st;
    end if;
    if tg_op = 'UPDATE' then
        if new.file_id <> old.file_id then
            raise exception 'a risk item stays in its file';
        end if;
        select status into st from risk_files where id = old.file_id for share;
        if st <> 'draft' then
            raise exception 'the risk file is %: its items are fixed', st;
        end if;
    end if;
    return case when tg_op = 'DELETE' then old else new end;
end $$;
create trigger risk_items_kept before insert or update or delete on risk_items
    for each row execute function wqo_risk_item_kept();

create table risk_log (
    id      bigserial primary key,
    file_id bigint references risk_files (id),   -- null: a change of the criteria
    at      timestamptz not null default now(),
    email   text,
    action  text not null,
    note    text not null default ''
);
create index risk_log_ref on risk_log (file_id, id);
create trigger risk_log_append_only before update or delete on risk_log
    for each row execute function wqo_append_only();
