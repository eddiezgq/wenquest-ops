-- Drafts for ERPNext (ADR-0006 item 5): proposed by a person or the AI, written to ERPNext as a Draft only after a
-- person with the right permission confirms. Every step is kept in erp_draft_log.
create table erp_drafts (
    id          bigserial primary key,
    doctype     text not null,
    summary     text not null default '',
    payload     jsonb not null,
    source      text not null check (source in ('person', 'ai')),
    ai_run      text,
    proposed_by text not null,
    status      text not null default 'pending'
                check (status in ('pending', 'confirming', 'confirmed', 'rejected', 'failed')),
    decided_by  text,
    decided_at  timestamptz,
    erp_name    text,
    error       text,
    created_at  timestamptz not null default now()
);
create index erp_drafts_status on erp_drafts (status, id);

create table erp_draft_log (
    id       bigserial primary key,
    draft_id bigint not null references erp_drafts (id),
    email    text,
    action   text not null check (action in ('proposed', 'confirmed', 'rejected', 'failed')),
    detail   text not null default '',
    at       timestamptz not null default now()
);
