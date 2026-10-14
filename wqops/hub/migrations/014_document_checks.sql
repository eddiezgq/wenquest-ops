-- Document library 14b (ADR-0014 item 4): numbering rules as configuration and short process codes for them.

alter table doc_processes add column short text not null default '';
update doc_processes set short = v.short from (values
    ('document_control', 'DC'), ('training', 'TR'), ('purchasing', 'PU'), ('receiving', 'RI'), ('production', 'PR'),
    ('nonconformance', 'NC'), ('capa', 'CA'), ('calibration', 'CL'), ('complaints', 'CP'), ('internal_audit', 'IA'),
    ('management_review', 'MR'), ('other', 'GEN')) as v (code, short) where doc_processes.code = v.code;

-- a company's own numbering rule for a type, e.g. "F-{process}-{seq}" with 3 digits; without one, the rule is
-- learned from the numbers the company already uses
create table doc_number_rules (
    doc_type   text primary key,
    template   text not null check (template like '%{seq}%'),
    digits     integer not null default 2 check (digits between 1 and 6),
    updated_by text not null,
    updated_at timestamptz not null default now()
);
