-- Document library 14c (ADR-0014 item 10): importing a company's historical ledgers (NCR log, CAPA log, supplier
-- list). The model proposes which column is which field; a person confirms (signed); code imports each row and
-- records where it came from.

alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger'));

create table ledger_imports (
    id          bigserial primary key,
    document_id bigint not null references documents (id),
    target      text not null check (target in ('ncr', 'capa', 'supplier')),
    sheet       text not null default '',
    header_row  integer not null,
    mapping     jsonb not null default '{}',     -- field -> {"column": header} or {"value": constant}
    values_map  jsonb not null default '{}',     -- field -> {ledger value: our code}
    engine      text not null,                   -- ai | rules | person
    confidence  text check (confidence in ('high', 'medium', 'low')),
    notes       text not null default '',
    ai_run      bigint references ai_runs (id),
    status      text not null default 'proposed' check (status in ('proposed', 'imported')),
    created_by  text not null,
    created_at  timestamptz not null default now(),
    imported_by text,
    imported_at timestamptz,
    result      jsonb not null default '{}'
);

-- one row of a ledger brought in once, whatever happened to it
create table ledger_rows (
    import_id   bigint not null references ledger_imports (id),
    document_id bigint not null references documents (id),
    target      text not null,
    sheet       text not null,
    row_no      integer not null,
    outcome     text not null check (outcome in ('imported', 'drafted', 'skipped')),
    ref         text,                            -- NCR-00012, CAPA-00003, draft 41
    note        text not null default '',
    at          timestamptz not null default now(),
    primary key (document_id, target, sheet, row_no, import_id)
);
create trigger ledger_rows_append_only before update or delete on ledger_rows
    for each row execute function wqo_append_only();

-- a ledger that does not say how serious a nonconformance was leaves it unknown; it is set before closing
alter table ncr_records alter column severity drop not null;

-- where an imported quality record came from, and the dates the ledger gives
alter table ncr_records add column external_no text;
alter table ncr_records add column reported_on date;
alter table ncr_records add column source_doc bigint references documents (id);
alter table ncr_records add column source_row integer;
alter table capas add column external_no text;
alter table capas add column reported_on date;
alter table capas add column source_doc bigint references documents (id);
alter table capas add column source_row integer;
