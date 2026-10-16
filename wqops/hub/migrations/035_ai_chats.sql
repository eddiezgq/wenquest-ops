-- AI chat panel (ADR-0021): a conversation is a series of questions to the assistant by one person. Each question
-- stays an ai_runs row (ADR-0008), now with its conversation and the page it was asked on.

create table ai_chats (
    id         bigserial primary key,
    email      text not null,
    title      text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index ai_chats_email on ai_chats (email, updated_at desc);

alter table ai_runs add column chat_id bigint references ai_chats (id);
alter table ai_runs add column page jsonb;
create index ai_runs_chat on ai_runs (chat_id, id);

create or replace function wqo_ai_chat_kept() returns trigger language plpgsql as $$
begin
    raise exception 'conversations are kept';
end $$;
create trigger ai_chats_kept before delete on ai_chats for each row execute function wqo_ai_chat_kept();
