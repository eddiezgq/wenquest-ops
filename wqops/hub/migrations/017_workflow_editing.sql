-- Quality workflows 15b (ADR-0015): drafts edited by people, enabled by someone else with a signature; custom fields
-- and extra signed approvals on records.

alter table workflow_versions drop constraint workflow_versions_status_check;
alter table workflow_versions add constraint workflow_versions_status_check
    check (status in ('draft', 'enabled', 'retired', 'discarded'));
alter table workflow_versions add column edited_by text[] not null default '{}';
alter table workflow_versions add column discarded_reason text;

create or replace function wqo_workflow_frozen() returns trigger language plpgsql as $$
begin
    if old.status <> 'draft' and (new.config::text is distinct from old.config::text
            or new.fingerprint is distinct from old.fingerprint or new.kind is distinct from old.kind
            or new.version is distinct from old.version or new.created_by is distinct from old.created_by
            or new.enabled_by is distinct from old.enabled_by or new.enabled_at is distinct from old.enabled_at
            or new.edited_by is distinct from old.edited_by) then
        raise exception 'workflow % version % is frozen: make a new version', old.kind, old.version;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('enabled', 'discarded'))
            or (old.status = 'enabled' and new.status = 'retired')) then
        raise exception 'workflow % version % cannot go from % to %', old.kind, old.version, old.status, new.status;
    end if;
    return new;
end $$;

-- what happened to workflow versions: who drafted, changed, enabled or discarded them
create table workflow_log (
    id         bigserial primary key,
    version_id bigint not null references workflow_versions (id),
    at         timestamptz not null default now(),
    email      text not null,
    action     text not null,
    note       text not null default ''
);
create trigger workflow_log_append_only before update or delete on workflow_log
    for each row execute function wqo_append_only();

-- values of a company's own fields on a record
alter table ncr_records add column custom jsonb not null default '{}';
alter table capas add column custom jsonb not null default '{}';

-- extra signed approvals a workflow asks for before a step
create table quality_approvals (
    id       bigserial primary key,
    kind     text not null check (kind in ('ncr', 'capa')),
    ref_id   bigint not null,
    name     text not null,
    email    text not null,
    at       timestamptz not null default now()        -- counts until the record goes back a step
);
create index quality_approvals_ref on quality_approvals (kind, ref_id, name, at);
create trigger quality_approvals_append_only before update or delete on quality_approvals
    for each row execute function wqo_append_only();
