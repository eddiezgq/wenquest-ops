-- PLM step 27c (round 124): editions of the parts manual, frozen when made, and read-only links for dealers.
create table plm_manuals (
    id          bigserial primary key,
    part_id     bigint not null references plm_parts (id),
    edition     int not null check (edition > 0),
    pages       jsonb not null,             -- per assembly: code, names, revision, picture, lines
    changes     jsonb not null default '[]'::jsonb,
    pdf_sha     text not null,
    names_open  int not null default 0,     -- English names not confirmed when it was made
    created_by  text not null,
    created_at  timestamptz not null default now(),
    unique (part_id, edition)
);

create table plm_manual_links (
    id           bigserial primary key,
    part_id      bigint not null references plm_parts (id),
    token_sha    text not null unique,     -- the token is shown once; only its hash is kept
    label        text not null default '',
    created_by   text not null,
    created_at   timestamptz not null default now(),
    revoked_at   timestamptz,
    revoked_by   text,
    views        int not null default 0,
    last_view_at timestamptz
);

-- an edition is what was given out: it never changes
create or replace function wqo_plm_manual_kept() returns trigger language plpgsql as $$
begin
    raise exception 'an edition of the parts manual is kept as it was made';
end $$;
create trigger plm_manuals_kept before update or delete on plm_manuals for each row execute function wqo_plm_manual_kept();
