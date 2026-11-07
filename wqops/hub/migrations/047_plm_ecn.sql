-- PLM step 26d (ADR-0026): a product change (17g) says which parts it changes (the part, its BOM or both), how the
-- change takes effect, and keeps the impact analysis it was assessed on. All of it is fixed once the change is
-- submitted, like the rest of what was assessed.

create table plm_change_items (
    id          bigserial primary key,
    change_id   bigint not null references changes (id),
    part_id     bigint not null references plm_parts (id),
    scope       text not null check (scope in ('part', 'bom', 'both')),
    from_part   text,                          -- the released part revision when it was added
    from_bom    text,                          -- the released BOM revision when it was added
    note        text not null default '',
    added_by    text not null,
    added_at    timestamptz not null default now(),
    unique (change_id, part_id)
);

create table plm_change_effect (
    change_id   bigint primary key references changes (id),
    mode        text not null check (mode in ('now', 'use_up', 'date', 'serial')),
    on_date     date,
    from_serial text,
    note        text not null default '',
    set_by      text not null,
    set_at      timestamptz not null default now(),
    check (mode <> 'date' or on_date is not null),
    check (mode <> 'serial' or coalesce(from_serial, '') <> '')
);

create table plm_change_impact (
    change_id   bigint primary key references changes (id),
    items_key   text not null,                 -- which parts and scopes it was made for: redo it after a change
    data        jsonb not null,
    made_by     text not null,
    made_at     timestamptz not null default now()
);

create or replace function wqo_plm_ecn_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    select status into st from changes where id = coalesce(new.change_id, old.change_id) for share;
    if st <> 'draft' then
        raise exception 'the change is %: what it changes, its effect and its impact analysis are fixed', st;
    end if;
    return coalesce(new, old);
end $$;
create trigger plm_change_items_kept before insert or update or delete on plm_change_items
    for each row execute function wqo_plm_ecn_kept();
create trigger plm_change_effect_kept before insert or update or delete on plm_change_effect
    for each row execute function wqo_plm_ecn_kept();
create trigger plm_change_impact_kept before insert or update or delete on plm_change_impact
    for each row execute function wqo_plm_ecn_kept();

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup', 'cause', 'fmea',
                    'plm-impact'));
