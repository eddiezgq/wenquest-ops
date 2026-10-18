-- Process FMEA, step 22c (ADR-0022): the company's own severity, occurrence and detection scales (ranks 1 to 10, its
-- own words, no standard's values) and its own rule for when a row needs action (an RPN or severity threshold, or a
-- lookup table of ranges). A PFMEA lists, per process step, failure modes, their effects and causes, the controls in
-- place and the three ranks; RPN = S x O x D is computed by code. A PFMEA is a controlled document: approved with a
-- signature by someone who did not own or edit it, then fixed with the criteria used and a fingerprint; revised as a
-- new version. The AI may draft rows (failure mode, effect, cause) citing records; it never gives a rank. Nothing is
-- deleted once approved.

create table fmea_scales (
    id          bigserial primary key,
    kind        text not null check (kind in ('severity', 'occurrence', 'detection')),
    rank        integer not null check (rank between 1 and 10),
    name        text not null check (name <> ''),
    description text not null default '',
    active      boolean not null default true,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    unique (kind, rank)
);

create or replace function wqo_fmea_scale_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'scale ranks are kept: stop using one instead';
    end if;
    if (new.kind, new.rank) is distinct from (old.kind, old.rank) then
        raise exception 'a scale rank keeps its kind and rank';
    end if;
    return new;
end $$;
create trigger fmea_scales_kept before update or delete on fmea_scales
    for each row execute function wqo_fmea_scale_kept();

-- the company's rule for when a row needs action; one row
create table fmea_settings (
    id               integer primary key default 1 check (id = 1),
    method           text not null check (method in ('rpn', 'lookup')),
    rpn_action       integer check (rpn_action between 1 and 1000),      -- method rpn: action when RPN >= this
    severity_action  integer check (severity_action between 1 and 10),   -- also when S >= this (optional)
    rules            jsonb not null default '[]',   -- method lookup: [{s: [lo, hi], o: [..], d: [..], priority}]
    needs_action     text[] not null default '{high}',                   -- lookup priorities that need action
    updated_by       text not null,
    updated_at       timestamptz not null default now(),
    check (method <> 'rpn' or rpn_action is not null)
);

create table fmea_files (
    id              bigserial primary key,
    name            text not null,
    version         integer not null default 1 check (version >= 1),
    previous_id     bigint references fmea_files (id),
    process         text not null check (process <> ''),      -- the process or product line
    item_code       text,                                     -- the item it makes, if one
    scope           text not null default '',
    owner           text,
    status          text not null default 'draft' check (status in ('draft', 'approved', 'superseded', 'withdrawn')),
    editors         text[] not null default '{}',
    approved_by     text,
    approved_at     timestamptz,
    criteria        jsonb,                                    -- the scales and rule used, as they were at approval
    fingerprint     text,
    withdraw_reason text,
    created_by      text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (name, version),
    check (status not in ('approved', 'superseded') or (approved_by is not null and approved_at is not null
           and criteria is not null and fingerprint is not null and approved_by is distinct from owner
           and approved_by <> created_by and not (approved_by = any(editors)))),
    check (status in ('approved', 'superseded') or (approved_by is null and approved_at is null and criteria is null
           and fingerprint is null)),
    check (status <> 'withdrawn' or withdraw_reason is not null)
);
create unique index fmea_files_one_draft on fmea_files (name) where status = 'draft';

create or replace function wqo_fmea_file_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'PFMEAs are kept: withdraw a draft with a reason';
    end if;
    if (new.name, new.version, new.previous_id, new.created_by, new.created_at)
            is distinct from (old.name, old.version, old.previous_id, old.created_by, old.created_at) then
        raise exception 'PFMEA % keeps its number, version and origin', old.name;
    end if;
    if not (old.editors <@ new.editors) then
        raise exception 'PFMEA % keeps everyone who edited it', old.name;
    end if;
    if old.status <> 'draft' and (to_jsonb(new) - 'status' - 'updated_at') is distinct from
            (to_jsonb(old) - 'status' - 'updated_at') then
        raise exception 'PFMEA % v% is %: it is fixed (revise it as a new version)', old.name, old.version, old.status;
    end if;
    if old.status = 'approved' and new.status = 'superseded' and not exists (
            select 1 from fmea_files where previous_id = old.id and status = 'approved') then
        raise exception 'PFMEA % v% is superseded only by an approved newer version', old.name, old.version;
    end if;
    if old.status = 'draft' and new.status = 'approved' and not exists (
            select 1 from signatures where kind = 'fmea' and ref_id = old.id and email = new.approved_by) then
        raise exception 'PFMEA % is approved only with the approver''s signature', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('approved', 'withdrawn'))
            or (old.status = 'approved' and new.status = 'superseded')) then
        raise exception 'PFMEA % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger fmea_files_kept before update or delete on fmea_files
    for each row execute function wqo_fmea_file_kept();

create table fmea_rows (
    id                 bigserial primary key,
    file_id            bigint not null references fmea_files (id),
    seq                integer not null,
    step               text not null default '',     -- the process step
    requirement        text not null default '',     -- what the step must achieve
    failure_mode       text not null default '',
    effect             text not null default '',
    severity           integer,
    cause              text not null default '',
    occurrence         integer,
    prevention         text not null default '',     -- current controls that prevent the cause
    detection_controls text not null default '',     -- current controls that detect the failure or cause
    detection          integer,
    action             text not null default '',     -- what is recommended
    action_owner       text,
    action_due         date,
    res_severity       integer,
    res_occurrence     integer,
    res_detection      integer,
    refs               text[] not null default '{}', -- records it rests on
    origin             text not null default 'person' check (origin in ('person', 'ai')),
    ai_run             bigint references ai_runs (id),
    confirmed          boolean not null default true, -- a row the AI drafted waits for a person
    rpn                integer,                       -- written at approval
    res_rpn            integer,
    priority           text,                          -- written at approval: the rule's result
    unique (file_id, seq),
    check (origin <> 'ai' or ai_run is not null),
    check ((res_severity is null) = (res_occurrence is null) and (res_occurrence is null) = (res_detection is null))
);

create or replace function wqo_fmea_row_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    select status into st from fmea_files where id = (case when tg_op = 'DELETE' then old.file_id
                                                           else new.file_id end) for share;
    if st <> 'draft' then
        raise exception 'the PFMEA is %: its rows are fixed', st;
    end if;
    if tg_op = 'UPDATE' and new.file_id <> old.file_id then
        raise exception 'a PFMEA row stays in its file';
    end if;
    return case when tg_op = 'DELETE' then old else new end;
end $$;
create trigger fmea_rows_kept before insert or update or delete on fmea_rows
    for each row execute function wqo_fmea_row_kept();

-- corrective or preventive actions opened from a row, at any time (also after approval)
create table fmea_capas (
    file_id     bigint not null references fmea_files (id),
    row_seq     integer not null,
    capa_id     bigint not null references capas (id),
    created_by  text not null,
    created_at  timestamptz not null default now(),
    primary key (file_id, row_seq, capa_id)
);
create trigger fmea_capas_append_only before update or delete on fmea_capas
    for each row execute function wqo_append_only();

create table fmea_log (
    id      bigserial primary key,
    file_id bigint references fmea_files (id),   -- null: a change of the criteria
    at      timestamptz not null default now(),
    email   text,
    action  text not null,
    note    text not null default ''
);
create index fmea_log_ref on fmea_log (file_id, id);
create trigger fmea_log_append_only before update or delete on fmea_log
    for each row execute function wqo_append_only();

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup', 'cause', 'fmea'));
