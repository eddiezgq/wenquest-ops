-- 20c (ADR-0020): measurement files. A file a measuring machine exported (CMM, 3D scanner, gauge software) is read
-- into an incoming inspection in progress, signed by the person who imports it. The file itself, how its features
-- were matched to the plan and the samples its parts went to are kept; the import cannot be changed or deleted.

create table measurement_imports (
    id             bigserial primary key,
    inspection_id  bigint not null references iqc_inspections (id),
    file_name      text not null,
    sha256         text not null,
    format         text not null check (format in ('csv', 'dfq')),
    content        bytea not null check (octet_length(content) <= 5000000),
    mapping        jsonb not null,               -- {feature in the file: characteristic of the plan}
    samples        jsonb not null,               -- {part in the file: sample}
    readings       integer not null check (readings >= 1),
    left_out       jsonb not null default '[]',  -- what was not imported, and why
    gauge_id       bigint references gauges (id),
    gauge_code     text,
    imported_by    text not null,
    imported_at    timestamptz not null default now()
);
create unique index measurement_imports_once on measurement_imports (inspection_id, sha256);
create trigger measurement_imports_append_only before update or delete on measurement_imports
    for each row execute function wqo_append_only();

-- a reading that came from a file names its import; typing over it clears that
alter table iqc_readings add column import_id bigint references measurement_imports (id);
