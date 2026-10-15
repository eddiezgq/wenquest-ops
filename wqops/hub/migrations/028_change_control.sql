-- Change control, step 17g (ADR-0017; dee-qms PLAN-CHANGE): a change is assessed (four questions a person answers),
-- approved with a signature by someone who did not raise, own, submit or edit it, implemented (the new revisions of
-- the documents it affects in effect, validation done when needed) and closed with a signature by someone other
-- than the owner once its effectiveness is confirmed. Nothing is deleted.

create table changes (
    id                  bigserial primary key,
    name                text not null unique,
    title               text not null,
    kind                text not null check (kind in ('product', 'process', 'supplier', 'document', 'software',
                                                       'equipment', 'other')),
    description         text not null default '',
    reason              text not null default '',
    owner               text,
    target_date         date,
    capa_id             bigint references capas (id),
    documents           jsonb not null default '[]',    -- the documents in effect that it changes (ids)
    revisions           jsonb not null default '[]',    -- their new revisions (ids)
    q_product           text check (q_product in ('yes', 'no')),
    q_regulatory        text check (q_regulatory in ('yes', 'no')),
    q_risk              text check (q_risk in ('yes', 'no')),
    q_validation        text check (q_validation in ('yes', 'no')),
    assessment          text not null default '',
    regulatory_decision text not null default '',
    validation_plan     text not null default '',
    validation_result   text not null default '',
    implementation      text not null default '',
    effectiveness       text not null default '',
    status              text not null default 'draft'
                        check (status in ('draft', 'submitted', 'approved', 'implemented', 'closed', 'cancelled')),
    editors             text[] not null default '{}',   -- everyone who changed its content
    submitted_by        text,
    approved_by         text,
    approved_at         timestamptz,
    implemented_by      text,
    implemented_at      timestamptz,
    closed_by           text,
    closed_at           timestamptz,
    cancel_reason       text,
    created_by          text not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    check (status not in ('approved', 'implemented', 'closed') or (approved_by is not null and approved_at is not null
           and approved_by is distinct from owner and approved_by <> created_by
           and approved_by is distinct from submitted_by and not (approved_by = any(editors)))),
    check (status not in ('implemented', 'closed') or (implemented_by is not null and implementation <> '')),
    check (status <> 'closed' or (closed_by is not null and closed_by is distinct from owner and effectiveness <> '')),
    check (status <> 'cancelled' or cancel_reason is not null)
);

create or replace function wqo_change_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'changes are kept: cancel it with a reason';
    end if;
    if old.status in ('closed', 'cancelled') then
        raise exception 'change % is %: it cannot change', old.name, old.status;
    end if;
    if (new.name, new.created_by, new.created_at) is distinct from (old.name, old.created_by, old.created_at) then
        raise exception 'change % keeps its number and origin', old.name;
    end if;
    -- everyone who was involved stays involved; who signed stays who signed
    if not (old.editors <@ new.editors) then
        raise exception 'change % keeps everyone who edited, owned or submitted it', old.name;
    end if;
    if (old.approved_by is not null and (new.approved_by, new.approved_at) is distinct from
            (old.approved_by, old.approved_at))
       or (old.implemented_by is not null and (new.implemented_by, new.implemented_at) is distinct from
            (old.implemented_by, old.implemented_at))
       or ((new.approved_by, new.approved_at) is distinct from (old.approved_by, old.approved_at)
            and not (old.status = 'submitted' and new.status = 'approved'))
       or ((new.implemented_by, new.implemented_at) is distinct from (old.implemented_by, old.implemented_at)
            and not (old.status = 'approved' and new.status = 'implemented'))
       or ((new.closed_by, new.closed_at) is distinct from (old.closed_by, old.closed_at)
            and not (old.status = 'implemented' and new.status = 'closed')) then
        raise exception 'change %: signatures are given by their steps and kept', old.name;
    end if;
    -- submitted: what was assessed is fixed (also when it is sent back: it is changed as a draft afterwards)
    if old.status <> 'draft' and (new.title, new.kind, new.description, new.reason,
            new.owner, new.capa_id, new.documents::text, new.q_product, new.q_regulatory, new.q_risk, new.q_validation,
            new.assessment, new.regulatory_decision, new.validation_plan) is distinct from (old.title, old.kind,
            old.description, old.reason, old.owner, old.capa_id, old.documents::text, old.q_product, old.q_regulatory,
            old.q_risk, old.q_validation, old.assessment, old.regulatory_decision, old.validation_plan) then
        raise exception 'change % is %: what was assessed is fixed', old.name, old.status;
    end if;
    if old.status in ('implemented') and (new.revisions::text, new.validation_result, new.implementation)
            is distinct from (old.revisions::text, old.validation_result, old.implementation) then
        raise exception 'change % is implemented: only its effectiveness is still written', old.name;
    end if;
    if old.status in ('draft', 'submitted') and (new.effectiveness, new.validation_result, new.implementation)
            is distinct from (old.effectiveness, old.validation_result, old.implementation) then
        raise exception 'change % is not approved yet', old.name;
    end if;
    if old.status = 'approved' and new.effectiveness is distinct from old.effectiveness then
        raise exception 'change % is not implemented yet', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('submitted', 'cancelled'))
            or (old.status = 'submitted' and new.status in ('draft', 'approved', 'cancelled'))
            or (old.status = 'approved' and new.status in ('implemented', 'cancelled'))
            or (old.status = 'implemented' and new.status = 'closed')) then
        raise exception 'change % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger changes_kept before update or delete on changes
    for each row execute function wqo_change_kept();

create table change_log (
    id        bigserial primary key,
    change_id bigint not null references changes (id),
    at        timestamptz not null default now(),
    email     text,
    action    text not null,
    note      text not null default ''
);
create index change_log_ref on change_log (change_id, id);
create trigger change_log_append_only before update or delete on change_log
    for each row execute function wqo_append_only();
