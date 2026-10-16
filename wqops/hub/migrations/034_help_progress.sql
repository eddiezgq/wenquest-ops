-- Help center checklist progress (ADR-0019 item 4): who ticked or unticked which "try it" item, when. Only added to,
-- never changed: the latest row per person and item is its state. It decides nothing; it is the tester's checklist.

create table help_progress (
    id     bigserial primary key,
    email  text not null,
    item   text not null check (item ~ '^[a-z0-9-]{1,60}/[a-z0-9-]{1,60}$'),   -- topic/item
    done   boolean not null,
    at     timestamptz not null default now()
);
create index help_progress_ref on help_progress (email, item, id);
create trigger help_progress_append_only before update or delete on help_progress
    for each row execute function wqo_append_only();
