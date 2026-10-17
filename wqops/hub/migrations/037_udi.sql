-- 20b (ADR-0020): unique device identification. Each item the company labels has the device identifier its issuing
-- agency gave it (a GS1 GTIN, or a HIBC labeler code with the product number and unit); every change is logged.
-- Every label printed for a production lot is kept.

create table udi_items (
    item_code text primary key,
    agency    text not null check (agency in ('gs1', 'hibcc')),
    di        text not null,                     -- GTIN-14, or +LIC PCN U
    set_by    text not null,
    set_at    timestamptz not null default now()
);
create unique index udi_items_di on udi_items (di);

create table udi_log (
    id        bigserial primary key,
    item_code text not null,
    email     text not null,
    action    text not null,
    note      text not null default '',
    at        timestamptz not null default now()
);
create trigger udi_log_append_only before update or delete on udi_log
    for each row execute function wqo_append_only();

create table label_prints (
    id         bigserial primary key,
    record_id  bigint not null references prod_records (id),
    item_code  text not null,
    agency     text not null,
    udi        text not null,                    -- the code as printed (GS1 in brackets, or HIBC)
    format     text not null check (format in ('screen', 'zpl')),
    copies     integer not null check (copies between 1 and 500),
    expiry     date,
    printed_by text not null,
    at         timestamptz not null default now()
);
create index label_prints_record on label_prints (record_id, id);
create trigger label_prints_append_only before update or delete on label_prints
    for each row execute function wqo_append_only();
