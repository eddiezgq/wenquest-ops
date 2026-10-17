-- Check sheets, step 22a (ADR-0022): a company's own tally forms (the categories to count) and the tallies people
-- record on them, signed. Forms are kept as they were made: to change the categories, make a new form and retire the
-- old one. Tallies are append-only. Pareto charts read them.

create table check_sheet_forms (
    id          bigserial primary key,
    name        text not null unique,
    categories  text[] not null check (cardinality(categories) between 1 and 40),
    active      boolean not null default true,
    created_by  text not null,
    created_at  timestamptz not null default now()
);

create or replace function wqo_check_sheet_form_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'check sheet forms are kept: retire it instead';
    end if;
    if (new.name, new.categories, new.created_by, new.created_at)
            is distinct from (old.name, old.categories, old.created_by, old.created_at) then
        raise exception 'a check sheet form is kept as made: make a new one to change its categories';
    end if;
    return new;
end $$;
create trigger check_sheet_forms_kept before update or delete on check_sheet_forms
    for each row execute function wqo_check_sheet_form_kept();

create table check_sheets (
    id          bigserial primary key,
    name        text not null unique,
    form_id     bigint not null references check_sheet_forms (id),
    on_date     date not null,
    item_code   text,
    place       text not null default '',          -- line, station, shift: where the counting was done
    counts      jsonb not null,                    -- category -> count, every category of the form
    total       integer not null check (total >= 0),
    note        text not null default '',
    signed_by   text not null,
    signed_at   timestamptz not null default now()
);
create index check_sheets_form on check_sheets (form_id, on_date);
create trigger check_sheets_append_only before update or delete on check_sheets
    for each row execute function wqo_append_only();

create table check_sheet_log (
    id       bigserial primary key,
    form_id  bigint not null references check_sheet_forms (id),
    at       timestamptz not null default now(),
    email    text,
    action   text not null,
    note     text not null default ''
);
create trigger check_sheet_log_append_only before update or delete on check_sheet_log
    for each row execute function wqo_append_only();
