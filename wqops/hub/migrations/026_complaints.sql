-- Complaints, step 17e (ADR-0017; dee-qms PLAN-COMPLAINT): the complaint, its investigation, whether it must be
-- reported to a regulator (three questions a person answers; the decision is theirs and signed), the report as
-- entered by a person, the reply, and closing signed by someone other than the owner. Nothing is deleted.

create table complaint_deadlines (
    id     bigserial primary key,
    label  text not null,
    days   integer not null check (days between 1 and 365),
    active boolean not null default true,
    sort   integer not null default 0
);
-- a default to change: set the days to what your regulations require
insert into complaint_deadlines (label, days, sort) values ('Report to the regulator (default: check your regulations)', 30, 1);
create trigger complaint_deadlines_kept before delete on complaint_deadlines
    for each row execute function wqo_append_only();

create table complaints (
    id                bigserial primary key,
    name              text not null unique,
    received_on       date not null,
    aware_on          date not null,
    source            text not null default 'customer' check (source in ('customer', 'distributor', 'field', 'other')),
    customer          text not null,
    contact           text not null default '',
    item_code         text,
    lot_no            text not null default '',
    quantity          numeric check (quantity is null or quantity > 0),
    description       text not null,
    injury            text not null default 'unknown' check (injury in ('yes', 'no', 'unknown')),
    malfunction       text not null default 'unknown' check (malfunction in ('yes', 'no', 'unknown')),
    owner             text,
    status            text not null default 'new'
                      check (status in ('new', 'investigation', 'assessed', 'closed', 'cancelled')),
    investigate       boolean not null default true,
    no_investigation_reason text not null default '',
    no_investigation_by     text,
    root_cause        text not null default '',
    investigation     text not null default '',
    q_harm            text check (q_harm in ('yes', 'no')),          -- may have caused or contributed to death or serious injury
    q_malfunction     text check (q_malfunction in ('yes', 'no')),   -- malfunctioned and could do so if it recurred
    q_recall          text check (q_recall in ('yes', 'no')),        -- concerns a recall, correction or removal
    reportable        boolean,
    reportable_reason text not null default '',
    exception         boolean not null default false,                -- a yes, yet decided not to report
    deadline_label    text,
    deadline_days     integer,
    deadline_on       date,
    assessed_by       text,
    assessed_at       timestamptz,
    report_ref        text not null default '',
    reported_on       date,
    response          text not null default '',
    ncr_id            bigint references ncr_records (id),
    capa_id           bigint references capas (id),
    closed_by         text,
    closed_at         timestamptz,
    cancel_reason     text,
    created_by        text not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    check (status not in ('assessed', 'closed') or (q_harm is not null and q_malfunction is not null
                                                     and q_recall is not null and reportable is not null
                                                     and reportable_reason <> '' and assessed_by is not null
                                                     and assessed_at is not null)),
    check (status <> 'closed' or (closed_by is not null and closed_at is not null and response <> ''
                                  and closed_by is distinct from owner and assessed_by is distinct from owner
                                  and (not reportable or (report_ref <> '' and reported_on is not null))
                                  and (investigation <> '' or (not investigate and no_investigation_reason <> '')))),
    check (status <> 'cancelled' or cancel_reason is not null)
);

create or replace function wqo_complaint_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'complaints are kept: cancel it with a reason';
    end if;
    if old.status in ('closed', 'cancelled') then
        raise exception 'complaint % is %: it cannot change', old.name, old.status;
    end if;
    if (new.name, new.created_by, new.created_at) is distinct from (old.name, old.created_by, old.created_at) then
        raise exception 'complaint % keeps its number and origin', old.name;
    end if;
    -- once assessed, what the decision rests on is fixed
    if old.status = 'assessed' and (new.received_on, new.aware_on, new.description, new.injury, new.malfunction,
            new.item_code, new.investigate, new.no_investigation_reason, new.root_cause, new.investigation,
            new.q_harm, new.q_malfunction, new.q_recall, new.reportable, new.reportable_reason, new.exception,
            new.deadline_label, new.deadline_days, new.deadline_on, new.assessed_by, new.assessed_at)
            is distinct from (old.received_on, old.aware_on, old.description, old.injury, old.malfunction,
            old.item_code, old.investigate, old.no_investigation_reason, old.root_cause, old.investigation,
            old.q_harm, old.q_malfunction, old.q_recall, old.reportable, old.reportable_reason, old.exception,
            old.deadline_label, old.deadline_days, old.deadline_on, old.assessed_by, old.assessed_at) then
        raise exception 'complaint % is assessed: the investigation and the decision are fixed', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'new' and new.status in ('investigation', 'cancelled'))
            or (old.status = 'investigation' and new.status in ('assessed', 'cancelled'))
            or (old.status = 'assessed' and new.status in ('closed', 'cancelled'))) then
        raise exception 'complaint % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger complaints_kept before update or delete on complaints
    for each row execute function wqo_complaint_kept();

create table complaint_log (
    id           bigserial primary key,
    complaint_id bigint not null references complaints (id),
    at           timestamptz not null default now(),
    email        text,
    action       text not null,
    note         text not null default ''
);
create index complaint_log_ref on complaint_log (complaint_id, id);
create trigger complaint_log_append_only before update or delete on complaint_log
    for each row execute function wqo_append_only();
