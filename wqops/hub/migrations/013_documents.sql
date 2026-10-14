-- Document library (ADR-0014, step 14a): imported files, their text, classification and controlled state.

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check check (kind in ('ask', 'brief', 'draft', 'classify'));

create table doc_imports (
    id          bigserial primary key,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    label       text not null default '',
    files       integer not null default 0,
    skipped     jsonb not null default '[]',            -- files not taken, with the reason
    -- extracting -> ready (text taken; usage estimate shown) -> classifying -> done
    status      text not null default 'extracting' check (status in ('extracting', 'ready', 'classifying', 'done')),
    engine      text,                                   -- ai | rules
    error       text
);

-- one row per imported file; the bytes live in the file store under their SHA-256
create table documents (
    id              bigserial primary key,
    import_id       bigint references doc_imports (id),
    sha256          text not null,
    size_bytes      bigint not null,
    original_name   text not null,
    path            text not null default '',          -- folder path inside the import
    mime            text not null default '',
    duplicate_of    bigint references documents (id),  -- same bytes as an earlier file
    text_status     text not null default 'pending' check (text_status in ('pending', 'ok', 'ocr', 'no_text', 'error')),
    text_chars      integer not null default 0,
    -- classification (a proposal until confirmed); evidence: {field: {"quote": ..., "verified": bool}}
    status          text not null default 'to_classify'
                    check (status in ('to_classify', 'to_review', 'confirmed', 'draft', 'in_review', 'effective',
                                      'obsolete', 'rejected')),
    engine          text,                               -- ai | rules | person
    confidence      text check (confidence in ('high', 'medium', 'low')),
    doc_type        text,
    process         text,
    number          text,
    title           text,
    revision        text,
    effective_date  date,
    owner           text,
    language        text,
    summary         text,
    refs            jsonb not null default '[]',        -- forms and records a procedure names
    evidence        jsonb not null default '{}',
    corrected       jsonb not null default '[]',        -- fields a person changed from the proposal
    ai_run          bigint,
    confirmed_by    text,
    confirmed_at    timestamptz,
    submitted_by    text,
    approved_by     text,
    approved_at     timestamptz,
    fingerprint     text,                               -- sha256 frozen when confirmed or effective
    supersedes      bigint references documents (id),
    obsolete_reason text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index documents_status on documents (status);
create index documents_sha on documents (sha256);
create index documents_number on documents (number);

create table doc_text (
    document_id bigint primary key references documents (id),
    body        text not null,
    tsv         tsvector generated always as (to_tsvector('simple', left(body, 200000))) stored
);
create index doc_text_tsv on doc_text using gin (tsv);

create table doc_log (
    id          bigserial primary key,
    document_id bigint not null references documents (id),
    at          timestamptz not null default now(),
    email       text,
    action      text not null,
    note        text not null default ''
);
create index doc_log_doc on doc_log (document_id, id);
create trigger doc_log_append_only before update or delete on doc_log
    for each row execute function wqo_append_only();

-- the bytes of a controlled document cannot change once frozen (ADR-0014 item 6)
create function wqo_doc_frozen() returns trigger language plpgsql as $$
begin
    if old.fingerprint is not null and new.sha256 is distinct from old.sha256 then
        raise exception 'document % is controlled: its file cannot be replaced, upload a new revision', old.id;
    end if;
    return new;
end $$;
create trigger documents_frozen before update on documents for each row execute function wqo_doc_frozen();
create trigger documents_no_delete before delete on documents for each row execute function wqo_append_only();

-- the process list is configuration (ISO process packs extend it later)
create table doc_processes (
    code   text primary key,
    name   text not null,
    sort   integer not null default 0
);
insert into doc_processes (code, name, sort) values
    ('document_control', 'Document control', 1), ('training', 'Training', 2),
    ('purchasing', 'Purchasing and suppliers', 3), ('receiving', 'Receiving inspection', 4),
    ('production', 'Production', 5), ('nonconformance', 'Nonconforming product', 6),
    ('capa', 'Corrective and preventive action', 7), ('calibration', 'Calibration', 8),
    ('complaints', 'Complaints', 9), ('internal_audit', 'Internal audit', 10),
    ('management_review', 'Management review', 11), ('other', 'Other', 99);
