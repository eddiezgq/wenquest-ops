-- Quality system 16d (ADR-0016): the set-up questionnaire, changes the model proposes from the company's own
-- procedures (each quoting them, checked by code, decided by a person), and procedures written from the workflow in
-- use.

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup'));

create table qms_setup (
    id       bigserial primary key,
    standard text not null,
    answers  jsonb not null,
    email    text not null,
    at       timestamptz not null default now()
);
create trigger qms_setup_append_only before update or delete on qms_setup
    for each row execute function wqo_append_only();

create table qms_setup_proposals (
    id         bigserial primary key,
    standard   text not null,
    documents  jsonb not null default '[]',
    created_by text not null,
    created_at timestamptz not null default now(),
    ai_run     bigint references ai_runs (id),
    summary    text not null default ''
);
create trigger qms_setup_proposals_append_only before update or delete on qms_setup_proposals
    for each row execute function wqo_append_only();

create table qms_setup_items (
    id            bigserial primary key,
    proposal_id   bigint not null references qms_setup_proposals (id),
    seq           integer not null,
    change        jsonb not null,
    document_id   bigint references documents (id),
    quote         text not null default '',
    why           text not null default '',
    verified      boolean not null,
    problems      jsonb not null default '[]',
    already       boolean not null default false,
    decision      text not null default 'open' check (decision in ('open', 'accepted', 'rejected')),
    decided_by    text,
    decided_at    timestamptz,
    decision_note text,
    unique (proposal_id, seq)
);

create or replace function wqo_setup_item_decided() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'proposed set-up changes are kept';
    end if;
    if old.decision <> 'open' or new.decision = 'open'
            or (new.change::text, new.document_id, new.quote, new.why, new.verified, new.problems::text, new.already,
                new.proposal_id, new.seq)
               is distinct from
               (old.change::text, old.document_id, old.quote, old.why, old.verified, old.problems::text, old.already,
                old.proposal_id, old.seq) then
        raise exception 'proposed set-up change % is decided once and otherwise kept as proposed', old.id;
    end if;
    return new;
end $$;
create trigger qms_setup_items_decided before update or delete on qms_setup_items
    for each row execute function wqo_setup_item_decided();

-- a procedure written by WenQuest Ops from a workflow version ("ncr workflow v2"): like an AI draft, it is approved
-- by someone else before it is in effect
alter table documents add column generated_from text;
