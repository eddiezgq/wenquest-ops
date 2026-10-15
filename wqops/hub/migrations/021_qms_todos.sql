-- Quality system 16c (ADR-0016): to-dos for the gaps the checks find. A to-do is closed by a person, or by the check
-- itself once the control point is met. History only grows.

create table qms_todos (
    id          bigserial primary key,
    standard    text not null,
    control     text not null,
    title       text not null,
    owner       text,
    due         date,
    status      text not null default 'open' check (status in ('open', 'done', 'dropped')),
    note        text not null default '',
    created_by  text not null,
    created_at  timestamptz not null default now(),
    closed_by   text,
    closed_at   timestamptz
);
create index qms_todos_control on qms_todos (standard, control, status);
create unique index qms_todos_one_open on qms_todos (standard, control) where status = 'open';

create or replace function wqo_qms_todo_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'to-dos are kept: drop it with a reason';
    end if;
    if old.status <> 'open' then
        raise exception 'to-do % is %: it cannot change', old.id, old.status;
    end if;
    if (new.standard, new.control, new.created_by, new.created_at)
            is distinct from (old.standard, old.control, old.created_by, old.created_at) then
        raise exception 'to-do % cannot be changed that way', old.id;
    end if;
    return new;
end $$;
create trigger qms_todos_kept before update or delete on qms_todos
    for each row execute function wqo_qms_todo_kept();

create table qms_todo_log (
    id      bigserial primary key,
    todo_id bigint not null references qms_todos (id),
    at      timestamptz not null default now(),
    email   text not null,
    action  text not null,
    note    text not null default ''
);
create trigger qms_todo_log_append_only before update or delete on qms_todo_log
    for each row execute function wqo_append_only();

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document'));

-- a document the model drafted always needs a signed approval by someone else before it is in effect, whatever its
-- type (16c)
alter table documents add column ai_drafted boolean not null default false;
