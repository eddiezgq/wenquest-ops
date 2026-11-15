-- PLM 33d (WenQuest round 135; ADR-0031): the instruction manual of a machine. Eight fixed chapters, each in Chinese
-- and English with its pictures; AI drafts, a person edits and confirms; only confirmed chapters go into an edition.
create table plm_um_chapters (
    id           bigserial primary key,
    part_id      bigint not null references plm_parts (id),
    key          text not null check (key in ('safety', 'install', 'parts', 'threading', 'operation', 'maintenance',
                                              'troubles', 'specs')),
    body_zh      text not null default '',
    body_en      text not null default '',
    figures      jsonb not null default '[]'::jsonb,   -- [{kind: explode, code} | {kind: upload, sha, name}, caption]
    state        text not null default 'draft' check (state in ('draft', 'confirmed')),
    drafted_by   text,                                 -- who wrote the text last: a person, or the AI's run
    ai_run       bigint,
    updated_by   text,
    updated_at   timestamptz not null default now(),
    confirmed_by text,
    confirmed_at timestamptz,
    unique (part_id, key)
);

-- an edition: the confirmed chapters as they were, and the two PDFs; kept as it was made
create table plm_um_editions (
    id         bigserial primary key,
    part_id    bigint not null references plm_parts (id),
    edition    int not null check (edition > 0),
    chapters   jsonb not null,
    pdf_sha    text not null,
    print_sha  text not null,
    created_by text not null,
    created_at timestamptz not null default now(),
    unique (part_id, edition)
);
create or replace function wqo_plm_um_kept() returns trigger language plpgsql as $$
begin
    raise exception 'an edition of the instruction manual is kept as it was made';
end $$;
create trigger plm_um_editions_kept before update or delete on plm_um_editions for each row
    execute function wqo_plm_um_kept();

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup', 'cause', 'fmea',
                    'plm-impact', 'plm-names', 'plm-manual'));
