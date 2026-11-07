-- PLM, steps 26a and 26b (ADR-0026): parts and their revisions, and design BOMs and theirs. The part master is the
-- ERPNext Item (item_code); the hub keeps what ERPNext does not have: revisions, status, category parameters,
-- files. A released revision is locked: changing it means a new revision under an approved product change (17g).
-- Nothing is deleted.

create table plm_numbering (
    category    text primary key,
    prefix      text not null check (prefix ~ '^[A-Z0-9][A-Z0-9-]{0,9}$'),
    digits      int not null default 5 check (digits between 3 and 8),
    updated_by  text not null,
    updated_at  timestamptz not null default now()
);

create table plm_parts (
    id          bigserial primary key,
    item_code   text not null unique,
    name        text not null,
    category    text not null,
    source      text not null check (source in ('make', 'buy')),
    uom         text not null,
    status      text not null default 'draft' check (status in ('draft', 'released', 'obsolete')),
    erp_state   text not null default 'pending' check (erp_state in ('pending', 'created', 'existing', 'failed')),
    erp_error   text,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table plm_part_revisions (
    id          bigserial primary key,
    part_id     bigint not null references plm_parts (id),
    revision    text not null,
    params      jsonb not null default '{}',
    description text not null default '',
    status      text not null default 'draft' check (status in ('draft', 'released', 'superseded')),
    change_id   bigint references changes (id),
    editors     text[] not null default '{}',
    created_by  text not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    released_by text,
    released_at timestamptz,
    unique (part_id, revision),
    check (status = 'draft' or (released_by is not null and released_at is not null))
);
create unique index plm_one_draft_revision on plm_part_revisions (part_id) where status = 'draft';

create table plm_files (
    id          bigserial primary key,
    revision_id bigint not null references plm_part_revisions (id),
    kind        text not null check (kind in ('model', 'drawing', 'image', 'other')),
    name        text not null,
    sha256      text not null,
    size_bytes  bigint not null,
    added_by    text not null,
    added_at    timestamptz not null default now(),
    removed_by  text,
    removed_at  timestamptz
);

create table plm_boms (
    id          bigserial primary key,
    part_id     bigint not null references plm_parts (id),
    revision    text not null,
    status      text not null default 'draft' check (status in ('draft', 'released', 'superseded')),
    change_id   bigint references changes (id),
    note        text not null default '',
    erp_bom     text,
    erp_error   text,
    editors     text[] not null default '{}',
    created_by  text not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    released_by text,
    released_at timestamptz,
    unique (part_id, revision),
    check (status = 'draft' or (released_by is not null and released_at is not null))
);
create unique index plm_one_draft_bom on plm_boms (part_id) where status = 'draft';

create table plm_bom_lines (
    id          bigserial primary key,
    bom_id      bigint not null references plm_boms (id),
    pos         int not null check (pos > 0),
    part_id     bigint not null references plm_parts (id),
    qty         numeric not null check (qty > 0),
    uom         text not null,
    note        text not null default '',
    unique (bom_id, pos)
);

create table plm_log (
    id          bigserial primary key,
    kind        text not null check (kind in ('part', 'bom', 'numbering')),
    ref_id      bigint not null,
    email       text,
    action      text not null,
    note        text not null default '',
    at          timestamptz not null default now()
);

-- Released content is locked and nothing is deleted. What may still change after release: the status moving on
-- (released -> superseded), and the ERPNext link of a BOM (its draft name, an error).
create or replace function wqo_plm_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'PLM records are kept';
    end if;
    if old.status <> 'draft' then
        -- (each table's own columns: PL/pgSQL would read the other table's columns in a single condition)
        if tg_table_name = 'plm_part_revisions' then
            if (new.part_id, new.revision, new.params, new.description, new.change_id, new.released_by,
                    new.released_at) is distinct from (old.part_id, old.revision, old.params, old.description,
                    old.change_id, old.released_by, old.released_at) then
                raise exception 'revision % is released: it cannot change', old.revision;
            end if;
        else
            if (new.part_id, new.revision, new.note, new.change_id, new.released_by, new.released_at)
                    is distinct from (old.part_id, old.revision, old.note, old.change_id, old.released_by,
                    old.released_at) then
                raise exception 'BOM revision % is released: it cannot change', old.revision;
            end if;
        end if;
        if new.status = 'draft' or (old.status = 'superseded' and new.status <> 'superseded') then
            raise exception 'a released revision does not go back';
        end if;
    end if;
    return new;
end $$;
create trigger plm_part_revisions_kept before update or delete on plm_part_revisions
    for each row execute function wqo_plm_kept();
create trigger plm_boms_kept before update or delete on plm_boms for each row execute function wqo_plm_kept();

-- lines and files of a released revision cannot change
create or replace function wqo_plm_lines_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    if tg_table_name = 'plm_bom_lines' then
        select status into st from plm_boms where id = coalesce(new.bom_id, old.bom_id);
        if tg_op = 'UPDATE' and new.bom_id <> old.bom_id then
            raise exception 'a BOM line stays in its BOM';
        end if;
    else
        select status into st from plm_part_revisions where id = coalesce(new.revision_id, old.revision_id);
        if tg_op = 'DELETE' then
            raise exception 'files are kept: remove them instead';
        end if;
        if tg_op = 'UPDATE' and (new.revision_id, new.kind, new.name, new.sha256, new.size_bytes, new.added_by,
                new.added_at) is distinct from (old.revision_id, old.kind, old.name, old.sha256, old.size_bytes,
                old.added_by, old.added_at) then
            raise exception 'a file record does not change';
        end if;
    end if;
    if st <> 'draft' then
        raise exception 'the revision is released: its lines and files cannot change';
    end if;
    return coalesce(new, old);
end $$;
create trigger plm_bom_lines_kept before insert or update or delete on plm_bom_lines
    for each row execute function wqo_plm_lines_kept();
create trigger plm_files_kept before insert or update or delete on plm_files
    for each row execute function wqo_plm_lines_kept();

create or replace function wqo_plm_log_kept() returns trigger language plpgsql as $$
begin
    raise exception 'the PLM log is kept';
end $$;
create trigger plm_log_kept before update or delete on plm_log for each row execute function wqo_plm_log_kept();

create or replace function wqo_plm_part_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'PLM records are kept';
    end if;
    if new.item_code <> old.item_code or new.created_by <> old.created_by or new.created_at <> old.created_at then
        raise exception 'part % keeps its code and origin', old.item_code;
    end if;
    return new;
end $$;
create trigger plm_parts_kept before update or delete on plm_parts for each row execute function wqo_plm_part_kept();
