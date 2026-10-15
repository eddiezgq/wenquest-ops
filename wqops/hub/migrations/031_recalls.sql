-- Recalls, step 17i (ADR-0017; dee-qms PLAN-TRACE, PLAN-SHIP, PLAN-RECALL). Who received a lot comes from ERPNext's
-- delivery notes (WenQuest Ops does not keep its own shipments): when a recall opens, its consignee list is taken
-- from them and fixed. People classify the recall and decide what to report; WenQuest Ops records notification,
-- confirmation and what came back, counts the effectiveness, and has it closed with a signature by someone who did
-- not own, raise or open it. Nothing is deleted.

create table recalls (
    id                  bigserial primary key,
    name                text not null unique,
    title               text not null check (title <> ''),
    reason              text not null default '',
    owner               text,
    owners              text[] not null default '{}',   -- everyone who has owned it
    classification      text not null default 'not yet classified'
                        check (classification in ('class I', 'class II', 'class III', 'not yet classified')),
    regulatory_decision text not null default '',
    strategy            text not null default '',
    scope               jsonb not null default '[]',    -- production record ids
    status              text not null default 'draft' check (status in ('draft', 'open', 'closed', 'cancelled')),
    opened_by           text,
    opened_at           timestamptz,
    opened_on           date,                           -- the company's date when it opened
    effectiveness       text not null default '',
    unconfirmed_note    text not null default '',
    closed_by           text,
    closed_at           timestamptz,
    closed_on           date,
    cancel_reason       text,
    created_by          text not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    check (status = 'draft' or status = 'cancelled' or (opened_by is not null and opened_at is not null
           and opened_on is not null)),
    check (status <> 'closed' or (closed_by is not null and closed_at is not null and closed_on is not null
           and effectiveness <> '' and regulatory_decision <> '' and closed_by is distinct from owner
           and not (closed_by = any(owners)) and closed_by <> created_by and closed_by <> opened_by)),
    check (status <> 'cancelled' or cancel_reason is not null)
);

create or replace function wqo_recall_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'recalls are kept: cancel a draft with a reason';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'draft' or new.opened_by is not null or new.closed_by is not null then
            raise exception 'a recall starts as a draft';
        end if;
        return new;
    end if;
    if old.status in ('closed', 'cancelled') then
        raise exception 'recall % is %: it cannot change', old.name, old.status;
    end if;
    if (new.name, new.created_by, new.created_at) is distinct from (old.name, old.created_by, old.created_at) then
        raise exception 'recall % keeps its number and origin', old.name;
    end if;
    if not (old.owners <@ new.owners) or (new.owner is not null and not (new.owner = any(new.owners))) then
        raise exception 'recall % keeps everyone who owned it', old.name;
    end if;
    if new.status <> 'draft' and (new.scope::text, coalesce(old.opened_by, new.opened_by),
            coalesce(old.opened_at, new.opened_at)) is distinct from (old.scope::text, new.opened_by, new.opened_at) then
        raise exception 'recall % is open: its scope is fixed', old.name;
    end if;
    if new.status = 'closed' and (not exists (select 1 from signatures where kind = 'recall' and ref_id = old.id
                                              and email = new.closed_by)
            or exists (select 1 from recall_consignees where recall_id = old.id and notified_on is null)) then
        raise exception 'recall % is closed with a signature once every consignee is notified', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('open', 'cancelled'))
            or (old.status = 'open' and new.status = 'closed')) then
        raise exception 'recall % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger recalls_kept before insert or update or delete on recalls
    for each row execute function wqo_recall_kept();

-- who received the lots, from ERPNext delivery notes as they were when the recall opened
create table recall_consignees (
    id             bigserial primary key,
    recall_id      bigint not null references recalls (id),
    delivery_note  text not null,
    posting_date   date,
    customer       text,
    customer_name  text not null default '',
    item_code      text not null,
    lot_no         text not null,                 -- the lot of the production record in scope
    batch_match    text not null check (batch_match in ('batch', 'item only', 'bundle')),
    qty            numeric not null,
    notified_on    date,
    notified_by    text,
    method         text not null default '',
    confirmed_on   date,
    returned_qty   numeric not null default 0 check (returned_qty >= 0),
    corrected_qty  numeric not null default 0 check (corrected_qty >= 0),
    note           text not null default '',
    check (returned_qty + corrected_qty <= qty),
    check ((notified_on is null) = (method = '')),
    check (confirmed_on is null or (notified_on is not null and confirmed_on >= notified_on))
);
create index recall_consignees_ref on recall_consignees (recall_id, id);

create or replace function wqo_recall_consignee_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    if tg_op = 'DELETE' then
        raise exception 'consignees of a recall are kept';
    end if;
    select status into st from recalls where id = new.recall_id for share;
    if tg_op = 'INSERT' then
        -- written only by the transaction that opens the recall
        if st <> 'draft' or coalesce(current_setting('wqo.recall_opening', true), '') <> new.recall_id::text then
            raise exception 'the consignee list is taken when the recall opens';
        end if;
        return new;
    end if;
    if st <> 'open' then
        raise exception 'the recall is %: its consignees are fixed', st;
    end if;
    if (new.recall_id, new.delivery_note, new.posting_date, new.customer, new.customer_name, new.item_code, new.lot_no,
        new.batch_match, new.qty) is distinct from (old.recall_id, old.delivery_note, old.posting_date, old.customer,
        old.customer_name, old.item_code, old.lot_no, old.batch_match, old.qty) then
        raise exception 'who received what is fixed';
    end if;
    return new;
end $$;
create trigger recall_consignees_kept before insert or update or delete on recall_consignees
    for each row execute function wqo_recall_consignee_kept();

create table recall_log (
    id        bigserial primary key,
    recall_id bigint not null references recalls (id),
    at        timestamptz not null default now(),
    email     text,
    action    text not null,
    note      text not null default ''
);
create index recall_log_ref on recall_log (recall_id, id);
create trigger recall_log_append_only before update or delete on recall_log
    for each row execute function wqo_append_only();
