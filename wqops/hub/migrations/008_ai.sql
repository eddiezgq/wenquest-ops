-- AI runs (ADR-0008 item 5): every question, brief and draft run, with its tool calls, answer and checks.
create table ai_runs (
    id         bigserial primary key,
    email      text not null,
    kind       text not null check (kind in ('ask', 'brief', 'draft')),
    question   text not null default '',
    engine     text not null,
    model      text,
    tool_calls jsonb not null default '[]',
    answer     text not null default '',
    verified   boolean,
    unverified jsonb not null default '[]',
    refs       jsonb not null default '[]',
    drafts     jsonb not null default '[]',
    usage      jsonb not null default '{}',
    error      text,
    feedback   integer check (feedback in (-1, 1)),
    created_at timestamptz not null default now()
);
create index ai_runs_email on ai_runs (email, id);
