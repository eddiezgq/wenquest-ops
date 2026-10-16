-- The company overview's settings (ADR-0018): its own thresholds for the panel lights, and whether the big screen
-- hides amounts of money and names (visitor mode). Every change is kept.
create table overview_settings (
    id    bigserial primary key,
    key   text not null check (key in ('thresholds', 'visitor_mode')),
    value jsonb not null,
    email text not null,
    at    timestamptz not null default now()
);
create index overview_settings_key on overview_settings (key, id);
create trigger overview_settings_append_only before update or delete on overview_settings
    for each row execute function wqo_append_only();
