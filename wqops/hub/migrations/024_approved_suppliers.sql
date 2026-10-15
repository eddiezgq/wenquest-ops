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
declare
    signed boolean;
begin
    if tg_op = 'DELETE' then
        raise exception 'approved supplier list entries are kept: disqualify the supplier instead';
    end if;
    if tg_op = 'INSERT' then
        if new.status not in ('draft', 'disqualified') or new.approved_by is not null or new.approved_at is not null then
            raise exception 'a new entry is a draft (or disqualified): it is approved with a signature';
        end if;
        return new;
    end if;
    if (new.supplier, new.item_code, new.created_by, new.created_at, new.source) is distinct from
            (old.supplier, old.item_code, old.created_by, old.created_at, old.source) then
        raise exception 'entry % keeps its supplier, item and origin', old.id;
    end if;
    -- a new approval: approver and time change together, later than before, with the approver's signature made
    -- in the same change
    signed := (new.approved_by, new.approved_at) is distinct from (old.approved_by, old.approved_at);
    if signed and not (new.status in ('approved', 'conditional') and new.approved_by is not null
            and new.approved_at > coalesce(old.approved_at, '-infinity'::timestamptz)
            and exists (select 1 from signatures where kind = 'asl' and ref_id = new.id and email = new.approved_by
                        and at = now())) then
        raise exception 'entry % is approved only with the approver''s signature', old.id;
    end if;
    -- becoming approved or conditional, or changing while so, needs that new approval
    if new.status in ('approved', 'conditional') and not signed and (new.status <> old.status
            or (new.basis, new.condition, new.review_due, new.risk) is distinct from
               (old.basis, old.condition, old.review_due, old.risk)) then
        raise exception 'entry % is %: re-evaluate it, or suspend it to change it', old.id, new.status;
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
create trigger asl_entries_kept before insert or update or delete on asl_entries
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
