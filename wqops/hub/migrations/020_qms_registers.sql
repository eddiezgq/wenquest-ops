-- Quality registers 16b (ADR-0016): simple records defined by the process pack (training, calibration, audits,
-- management reviews, objectives, risks and opportunities, customer feedback, supplier approval). Entries of signed
-- registers are locked once approved; a wrong entry is voided with a reason, never deleted. History only grows.

create table qms_register_entries (
    id          bigserial primary key,
    register    text not null,
    "values"    jsonb not null,
    status      text not null default 'open' check (status in ('open', 'signed', 'void')),
    created_by  text not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    signed_by   text,
    signed_at   timestamptz,
    void_reason text,
    source_doc  bigint references documents (id),     -- brought in from an old spreadsheet
    source_row  integer
);
create index qms_register_entries_register on qms_register_entries (register, id);

create or replace function wqo_register_entry_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'register entries are kept: void it with a reason';
    end if;
    if old.status <> 'open' and new."values"::text is distinct from old."values"::text then
        raise exception 'register entry % is %: it cannot change', old.id, old.status;
    end if;
    if new.register is distinct from old.register or new.created_by is distinct from old.created_by
            or new.created_at is distinct from old.created_at or new.source_doc is distinct from old.source_doc
            or (old.status = 'signed' and (new.signed_by, new.signed_at) is distinct from (old.signed_by, old.signed_at))
            or (old.status = 'void' and new.void_reason is distinct from old.void_reason)
            or not (old.status = new.status or (old.status = 'open' and new.status in ('signed', 'void'))
                    or (old.status = 'signed' and new.status = 'void')) then
        raise exception 'register entry % cannot be changed that way', old.id;
    end if;
    return new;
end $$;
create trigger qms_register_entries_kept before update or delete on qms_register_entries
    for each row execute function wqo_register_entry_kept();

create table qms_register_log (
    id       bigserial primary key,
    entry_id bigint not null references qms_register_entries (id),
    at       timestamptz not null default now(),
    email    text not null,
    action   text not null,
    note     text not null default ''
);
create index qms_register_log_entry on qms_register_log (entry_id, id);
create trigger qms_register_log_append_only before update or delete on qms_register_log
    for each row execute function wqo_append_only();

-- registers can be brought in from old spreadsheets with the ledger import (ADR-0014 item 10)
alter table ledger_imports drop constraint ledger_imports_target_check;
alter table ledger_imports add constraint ledger_imports_target_check
    check (target in ('ncr', 'capa', 'supplier') or target like 'reg\_%');
