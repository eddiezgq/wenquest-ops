-- Drafts that stay in the hub (ADR-0008 item 3): customer messages and nonconformance reports.
alter table erp_drafts add column target text not null default 'erpnext' check (target in ('erpnext', 'hub'));
alter table erp_drafts add column record text;   -- what confirming made in the hub, e.g. NCR-00001

-- Nonconformance reports (ADR-0008 item 3). Phase 1 item 8 adds disposition, 8D and CAPA.
create table ncr_records (
    id          bigserial primary key,
    name        text not null unique,
    draft_id    bigint references erp_drafts (id),
    title       text not null,
    description text not null,
    inspection  text,
    item_code   text,
    receipt     text,
    supplier    text,
    quantity    numeric,
    status      text not null default 'open',
    created_by  text not null,
    created_at  timestamptz not null default now()
);
