-- PLM step 26c (ADR-0026): model configuration of a base machine. Option groups (pick one option per group), what
-- each option does to the base BOM (add, remove, replace a part), rules between options (requires, excludes), and the
-- models generated from it: an ordinary ERPNext item each, coded base code + option codes, its BOM a draft a person
-- releases. The configuration is design data that may change; generated models are never changed by it.

create table plm_option_groups (
    id          bigserial primary key,
    base_id     bigint not null references plm_parts (id),
    code        text not null check (code ~ '^[A-Z0-9]{1,4}$'),
    name        text not null,
    pos         int not null,
    unique (base_id, code)
);

create table plm_options (
    id          bigserial primary key,
    group_id    bigint not null references plm_option_groups (id) on delete cascade,
    code        text not null check (code ~ '^[A-Z0-9]{1,4}$'),
    name        text not null,
    pos         int not null,
    unique (group_id, code)
);

create table plm_option_edits (
    id          bigserial primary key,
    option_id   bigint not null references plm_options (id) on delete cascade,
    action      text not null check (action in ('add', 'remove', 'replace')),
    part_id     bigint not null references plm_parts (id),        -- added, removed, or replaced
    with_id     bigint references plm_parts (id),                 -- the part put in its place (replace)
    qty         numeric check (qty > 0),                          -- add: required; replace: empty keeps the qty
    pos         int not null,
    check (action <> 'add' or qty is not null),
    check ((action = 'replace') = (with_id is not null))
);

create table plm_option_rules (
    id          bigserial primary key,
    base_id     bigint not null references plm_parts (id),
    kind        text not null check (kind in ('requires', 'excludes')),
    a_option    bigint not null references plm_options (id) on delete cascade,
    b_option    bigint not null references plm_options (id) on delete cascade,
    check (a_option <> b_option)
);

create table plm_models (
    id          bigserial primary key,
    base_id     bigint not null references plm_parts (id),
    part_id     bigint not null unique references plm_parts (id),
    choice      jsonb not null,                                   -- {group code: option code}
    choice_key  text not null,
    base_bom_id bigint not null references plm_boms (id),         -- the released base BOM it was made from
    created_by  text not null,
    created_at  timestamptz not null default now(),
    unique (base_id, choice_key)
);

create or replace function wqo_plm_models_kept() returns trigger language plpgsql as $$
begin
    raise exception 'generated models are kept as they were made';
end $$;
create trigger plm_models_kept before update or delete on plm_models
    for each row execute function wqo_plm_models_kept();

alter table plm_log drop constraint plm_log_kind_check;
alter table plm_log add constraint plm_log_kind_check check (kind in ('part', 'bom', 'numbering', 'config'));
