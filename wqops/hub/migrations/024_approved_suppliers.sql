-- Approved supplier list, step 17c (ADR-0017; dee-qms PLAN-ASL): one entry per supplier and item, or per supplier
-- for all its items. Approving and re-evaluating are signed; nothing is deleted; every change is logged.

create table asl_entries (
    id          bigserial primary key,
    supplier    text not null,                   -- the ERPNext supplier
    item_code   text,                            -- null: every item from this supplier
    risk        text not null default 'medium' check (risk in ('low', 'medium', 'high')),
    status      text not null default 'draft'
                check (status in ('draft', 'approved', 'conditional', 'suspended', 'disqualified')),
    basis       text not null default '',        -- what the approval rests on: certificates, audit, samples
    condition   text not null default '',        -- for a conditional approval
    review_due  date,
    source      text not null default '',        -- e.g. brought in from the supplier approval register
    created_by  text not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    approved_by text,
    approved_at timestamptz,
    check (status not in ('approved', 'conditional') or (approved_by is not null and approved_at is not null
                                                         and basis <> '')),
    check (status <> 'conditional' or condition <> '')
);
create unique index asl_entries_pair on asl_entries (supplier, coalesce(item_code, ''));

create or replace function wqo_asl_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'approved supplier list entries are kept: disqualify the supplier instead';
    end if;
    if (new.supplier, new.item_code, new.created_by, new.created_at) is distinct from
            (old.supplier, old.item_code, old.created_by, old.created_at) then
        raise exception 'entry % keeps its supplier and item', old.id;
    end if;
    -- approved or conditional content changes only with a new signed approval (a re-evaluation)
    if old.status in ('approved', 'conditional') and new.status = old.status
            and (new.basis, new.condition, new.review_due, new.risk) is distinct from
                (old.basis, old.condition, old.review_due, old.risk)
            and new.approved_at is not distinct from old.approved_at then
        raise exception 'entry % is %: re-evaluate it, or suspend it to change it', old.id, old.status;
    end if;
    if old.status = 'disqualified' and new.status = old.status and (new.basis, new.condition, new.review_due,
            new.risk) is distinct from (old.basis, old.condition, old.review_due, old.risk) then
        raise exception 'entry % is disqualified: qualify it again first', old.id;
    end if;
    if not (old.status = new.status
            or (old.status in ('draft', 'suspended') and new.status in ('approved', 'conditional'))
            or (old.status in ('approved', 'conditional') and new.status in ('approved', 'conditional', 'suspended'))
            or (old.status <> 'disqualified' and new.status = 'disqualified')
            or (old.status = 'disqualified' and new.status = 'draft')) then
        raise exception 'entry % cannot go from % to %', old.id, old.status, new.status;
    end if;
    return new;
end $$;
create trigger asl_entries_kept before update or delete on asl_entries
    for each row execute function wqo_asl_kept();

create table asl_log (
    id       bigserial primary key,
    entry_id bigint not null references asl_entries (id),
    at       timestamptz not null default now(),
    email    text,
    action   text not null,
    note     text not null default ''
);
create index asl_log_entry on asl_log (entry_id, id);
create trigger asl_log_append_only before update or delete on asl_log
    for each row execute function wqo_append_only();

-- what the approved supplier list said when a lot's inspection started (null: the list was not consulted)
alter table iqc_inspections add column supplier_standing text;
