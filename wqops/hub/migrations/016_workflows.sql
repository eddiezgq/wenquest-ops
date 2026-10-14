-- Quality workflows as configuration (ADR-0015, step 15a): versions of each workflow, and the version each record
-- was started under (it finishes under the same rules).

create table workflow_versions (
    id          bigserial primary key,
    kind        text not null check (kind in ('ncr', 'capa')),
    version     integer not null,
    config      json not null,                   -- json, not jsonb: states and steps keep their order
    status      text not null check (status in ('draft', 'enabled', 'retired')),
    fingerprint text,
    note        text not null default '',
    created_by  text not null,
    created_at  timestamptz not null default now(),
    enabled_by  text,
    enabled_at  timestamptz,
    unique (kind, version)
);
create unique index workflow_one_enabled on workflow_versions (kind) where status = 'enabled';

-- an enabled or retired version is frozen: its rules never change
create function wqo_workflow_frozen() returns trigger language plpgsql as $$
begin
    if old.status <> 'draft' and (new.config::text is distinct from old.config::text or
                                  new.fingerprint is distinct from old.fingerprint) then
        raise exception 'workflow % version % is frozen: make a new version', old.kind, old.version;
    end if;
    return new;
end $$;
create trigger workflow_versions_frozen before update on workflow_versions
    for each row execute function wqo_workflow_frozen();
create trigger workflow_versions_no_delete before delete on workflow_versions
    for each row execute function wqo_append_only();

alter table ncr_records add column workflow_version bigint references workflow_versions (id);
alter table capas add column workflow_version bigint references workflow_versions (id);
