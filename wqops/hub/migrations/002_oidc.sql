-- Pending OpenID Connect sign-ins (ADR-0005): state, nonce and PKCE verifier, kept for 10 minutes
create table if not exists oidc_pending (
    state       text primary key,
    provider    text not null,
    nonce       text not null,
    verifier    text not null,
    created_at  timestamptz not null default now()
);
