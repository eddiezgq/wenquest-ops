-- PLM step 26e (ADR-0026): design data comes in three ways - FreeCAD pushes it with a machine token (scope plm:send),
-- an engineer uploads a STEP file or an Excel BOM - and waits in one inbox. Each batch is a list of parts and how they
-- are assembled. An engineer matches each row to an existing part or says it is new, then writes it with a signature:
-- new parts and BOMs become drafts; nothing is released. What came in is kept as it came.

alter table integration_tokens drop constraint integration_tokens_scopes_check;
alter table integration_tokens add constraint integration_tokens_scopes_check
    check (scopes <> '{}' and scopes <@ array['measurements:send', 'production:send', 'events:read', 'plm:send']);

create table plm_intake (
    id          bigserial primary key,
    source      text not null check (source in ('freecad', 'step', 'excel')),
    token_id    bigint references integration_tokens (id),
    sent_by     text not null,                     -- the person, or the token's name
    file_name   text not null default '',
    file_sha    text,                              -- the original file (STEP, Excel, FreeCAD model) in the file store
    data        jsonb not null,                    -- {nodes: [{key, code, name, ...}], links: [{parent, child, qty}]}
    files       jsonb not null default '{}',       -- node key -> {name, sha256, size} of its STEP (FreeCAD)
    plan        jsonb not null default '{}',       -- node key -> {action: match | new, part_id | category, source, uom}
    changes     jsonb not null default '{}',       -- parent node key -> approved change id for a released BOM
    status      text not null default 'pending' check (status in ('pending', 'written', 'rejected')),
    result      jsonb,
    decided_by  text,
    decided_at  timestamptz,
    note        text not null default '',
    created_at  timestamptz not null default now(),
    check ((status = 'pending') = (decided_at is null))
);

create or replace function wqo_plm_intake_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'design data that came in is kept';
    end if;
    if (new.source, new.token_id, new.sent_by, new.file_name, new.file_sha, new.data, new.files, new.created_at)
            is distinct from (old.source, old.token_id, old.sent_by, old.file_name, old.file_sha, old.data,
                              old.files, old.created_at) then
        raise exception 'design data is kept as it came';
    end if;
    if old.status <> 'pending' then
        raise exception 'this batch is %: it does not change', old.status;
    end if;
    return new;
end $$;
create trigger plm_intake_kept before update or delete on plm_intake
    for each row execute function wqo_plm_intake_kept();

alter table plm_log drop constraint plm_log_kind_check;
alter table plm_log add constraint plm_log_kind_check
    check (kind in ('part', 'bom', 'numbering', 'config', 'intake'));
