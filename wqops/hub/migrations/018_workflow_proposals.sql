-- Quality workflows 15c (ADR-0015): the model reads the company's own procedures and proposes workflow changes. Each
-- proposed change quotes a procedure; code checks the quote and the red lines; a person accepts or rejects each one.
-- Accepted changes go into a draft version, which someone else enables with a signature (15b).

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow'));

create table workflow_proposals (
    id           bigserial primary key,
    kind         text not null check (kind in ('ncr', 'capa')),
    base_version bigint not null references workflow_versions (id),   -- the version the model compared with
    documents    jsonb not null default '[]',      -- [{id, name, revision, sha256, chars, cut}] as read
    created_by   text not null,
    created_at   timestamptz not null default now(),
    ai_run       bigint references ai_runs (id),
    summary      text not null default '',
    -- what the procedures say that a workflow cannot do: [{document_id, quote, why, verified}]
    cannot       jsonb not null default '[]'
);
create trigger workflow_proposals_append_only before update or delete on workflow_proposals
    for each row execute function wqo_append_only();

create table workflow_proposal_items (
    id            bigserial primary key,
    proposal_id   bigint not null references workflow_proposals (id),
    seq           integer not null,
    change        jsonb not null,                  -- one change in the shape quality/workflow_proposals.py applies
    document_id   bigint references documents (id),
    quote         text not null default '',
    why           text not null default '',
    verified      boolean not null,                -- code found the quote in that document
    problems      jsonb not null default '[]',     -- why it cannot be accepted (quote not found, red line, ...)
    already       boolean not null default false,  -- the workflow already does this
    lines         jsonb not null default '[]',     -- what it changes, in plain words
    decision      text not null default 'open' check (decision in ('open', 'accepted', 'rejected')),
    decided_by    text,
    decided_at    timestamptz,
    decision_note text,
    draft_version bigint references workflow_versions (id),
    unique (proposal_id, seq)
);

-- a proposed change is decided once; what the model proposed and what code found never change
create or replace function wqo_proposal_item_decided() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'proposed workflow changes are kept';
    end if;
    if old.decision <> 'open' or new.decision = 'open'
            or (new.change::text, new.document_id, new.quote, new.why, new.verified, new.problems::text, new.already,
                new.lines::text, new.proposal_id, new.seq)
               is distinct from
               (old.change::text, old.document_id, old.quote, old.why, old.verified, old.problems::text, old.already,
                old.lines::text, old.proposal_id, old.seq) then
        raise exception 'proposed change % is decided once and otherwise kept as proposed', old.id;
    end if;
    return new;
end $$;
create trigger workflow_proposal_items_decided before update or delete on workflow_proposal_items
    for each row execute function wqo_proposal_item_decided();
