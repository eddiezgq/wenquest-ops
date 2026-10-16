-- 20a (ADR-0020): another system's exports (items, customers, suppliers, opening stock, open orders) brought into
-- ERPNext through the ledger import. A row ERPNext refused stays "skipped" with the reason and can be tried again.

alter table ledger_imports drop constraint ledger_imports_target_check;
alter table ledger_imports add constraint ledger_imports_target_check
    check (target in ('ncr', 'capa', 'supplier') or target like 'reg\_%' or target like 'erp\_%');
alter table ledger_imports add column submit boolean not null default false;   -- orders and stock submitted at once

-- What each ERPNext import brought in, by its key in the old system (a name, an old order number, an item and
-- warehouse of opening stock), so a later import of an overlapping export never doubles it. A key is taken before
-- ERPNext is asked (ref empty) and given its ERPNext name after; a key left without one means a run stopped half way:
-- that record is not tried again until someone checks ERPNext.
create table erp_import_keys (
    target    text not null,
    key       text not null,
    ref       text,
    import_id bigint not null references ledger_imports (id),
    row_no    integer not null,
    at        timestamptz not null default now(),
    primary key (target, key)
);
