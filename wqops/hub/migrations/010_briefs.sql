-- Daily briefs (ADR-0008 item 6): the facts computed by code, the rule text, and the model's wording if checked.
create table briefs (
    id         bigserial primary key,
    day        date not null unique,
    facts      jsonb not null,
    rule_text  text not null,
    model_text text,
    engine     text not null,
    run_id     bigint references ai_runs (id),
    created_at timestamptz not null default now()
);
