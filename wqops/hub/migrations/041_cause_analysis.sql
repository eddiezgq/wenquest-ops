-- Cause analysis, step 22b (ADR-0022): fishbone diagrams and 5 Why on a nonconformance report, a CAPA or a complaint.
-- The model may suggest causes, each citing records; a person accepts, edits or removes every one. The conclusion is
-- signed and written back to the record's root cause; after that the analysis is kept as it was and only addenda
-- are added.

create table cause_analyses (
    id            bigserial primary key,
    name          text not null unique,
    method        text not null check (method in ('fishbone', 'five_why')),
    ref_kind      text not null check (ref_kind in ('ncr', 'capa', 'complaint')),
    ref_id        bigint not null,
    ref_name      text not null,
    problem       text not null check (problem <> ''),
    categories    text[] not null default '{}',     -- the fishbone's bones; empty for 5 Why
    status        text not null default 'open' check (status in ('open', 'concluded', 'cancelled')),
    conclusion    text,
    written_to    text,                             -- where the conclusion was written, e.g. "8D D4 of NCR-00002"
    concluded_by  text,
    concluded_at  timestamptz,
    cancel_reason text,
    created_by    text not null,
    created_at    timestamptz not null default now(),
    check (method <> 'fishbone' or cardinality(categories) between 2 and 10),
    check (status <> 'concluded' or (conclusion <> '' and concluded_by is not null and concluded_at is not null
                                     and written_to is not null)),
    check (status <> 'cancelled' or cancel_reason <> '')
);
create index cause_analyses_ref on cause_analyses (ref_kind, ref_id);

create or replace function wqo_cause_analysis_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'cause analyses are kept: cancel it instead';
    end if;
    if old.status <> 'open' then
        raise exception 'cause analysis % is %: it is kept as it was; add an addendum', old.name, old.status;
    end if;
    if (new.name, new.method, new.ref_kind, new.ref_id, new.ref_name, new.problem, new.categories, new.created_by,
        new.created_at) is distinct from (old.name, old.method, old.ref_kind, old.ref_id, old.ref_name, old.problem,
                                           old.categories, old.created_by, old.created_at) then
        raise exception 'cause analysis %: what it analyses is fixed when it is started', old.name;
    end if;
    return new;
end $$;
create trigger cause_analyses_kept before update or delete on cause_analyses
    for each row execute function wqo_cause_analysis_kept();

create table cause_items (
    id           bigserial primary key,
    analysis_id  bigint not null references cause_analyses (id),
    category     text,                              -- fishbone: the bone
    level        integer check (level is null or level between 1 and 7),   -- 5 Why: which why
    text         text not null check (text <> ''),
    refs         text[] not null default '{}',      -- the records it rests on, by number
    origin       text not null check (origin in ('person', 'ai')),
    ai_run       bigint references ai_runs (id),
    status       text not null check (status in ('proposed', 'accepted', 'removed')),
    edited       boolean not null default false,
    decided_by   text,
    decided_at   timestamptz,
    created_by   text not null,
    created_at   timestamptz not null default now(),
    check ((category is null) <> (level is null)),
    check (origin <> 'ai' or ai_run is not null),
    check (status = 'proposed' or decided_by is not null)
);
create index cause_items_analysis on cause_items (analysis_id, id);

create or replace function wqo_cause_item_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'causes are kept: remove it instead (it stays in the record)';
    end if;
    if (select status from cause_analyses where id = old.analysis_id) <> 'open' then
        raise exception 'the cause analysis is closed: its causes are kept as they were';
    end if;
    if (new.analysis_id, new.category, new.level, new.origin, new.ai_run, new.created_by, new.created_at)
            is distinct from (old.analysis_id, old.category, old.level, old.origin, old.ai_run, old.created_by,
                              old.created_at) then
        raise exception 'a cause keeps where it came from';
    end if;
    return new;
end $$;
create trigger cause_items_kept before update or delete on cause_items
    for each row execute function wqo_cause_item_kept();

create table cause_addenda (
    id           bigserial primary key,
    analysis_id  bigint not null references cause_analyses (id),
    text         text not null check (text <> ''),
    email        text not null,
    at           timestamptz not null default now()
);
create trigger cause_addenda_append_only before update or delete on cause_addenda
    for each row execute function wqo_append_only();

create table cause_log (
    id           bigserial primary key,
    analysis_id  bigint not null references cause_analyses (id),
    at           timestamptz not null default now(),
    email        text,
    action       text not null,
    note         text not null default ''
);
create trigger cause_log_append_only before update or delete on cause_log
    for each row execute function wqo_append_only();

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup', 'cause'));
