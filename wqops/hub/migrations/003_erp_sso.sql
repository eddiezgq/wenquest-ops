-- Signing in to ERPNext through WenQuest Ops (ADR-0005): the hub is an OAuth2 provider for ERPNext's social login
create table if not exists oauth_codes (
    code_hash    text primary key,
    user_id      bigint not null references users(id) on delete cascade,
    redirect_uri text not null,
    created_at   timestamptz not null default now()
);
create table if not exists oauth_tokens (
    token_hash  text primary key,
    user_id     bigint not null references users(id) on delete cascade,
    expires_at  timestamptz not null
);
-- where to go after an OpenID Connect sign-in (e.g. back to ERPNext)
alter table oidc_pending add column if not exists next text;
