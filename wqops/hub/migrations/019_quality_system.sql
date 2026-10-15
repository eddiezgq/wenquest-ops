-- Quality system 16a (ADR-0016): a standard's process pack enabled with a signature, what the company declares does
-- not apply, documents linked as evidence, and every evaluation of the control points kept.

-- the pack in use for a standard: enabled with a signature, frozen with the fingerprint of the pack as enabled
create table qms_packs (
    id          bigserial primary key,
    standard    text not null,
    edition     text not null,
    version     integer not null,                  -- the pack's own version
    content     json not null,                     -- the pack as enabled (key order kept)
    fingerprint text not null,
    status      text not null default 'enabled' check (status in ('enabled', 'retired')),
    enabled_by  text not null,
    enabled_at  timestamptz not null default now(),
    retired_at  timestamptz
);
create unique index qms_packs_one_enabled on qms_packs (standard) where status = 'enabled';

create or replace function wqo_qms_pack_frozen() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'enabled packs are kept';
    end if;
    if (new.standard, new.edition, new.version, new.content::text, new.fingerprint, new.enabled_by, new.enabled_at)
            is distinct from
       (old.standard, old.edition, old.version, old.content::text, old.fingerprint, old.enabled_by, old.enabled_at)
       or not (old.status = new.status or (old.status = 'enabled' and new.status = 'retired')) then
        raise exception 'pack % is frozen: enable a new one', old.id;
    end if;
    return new;
end $$;
create trigger qms_packs_frozen before update or delete on qms_packs
    for each row execute function wqo_qms_pack_frozen();

-- "this control point does not apply" (or applies again), with the reason; the latest row per control point counts
create table qms_applicability (
    id         bigserial primary key,
    standard   text not null,
    control    text not null,
    applies    boolean not null,
    reason     text not null,
    email      text not null,
    at         timestamptz not null default now()
);
create index qms_applicability_control on qms_applicability (standard, control, id);
create trigger qms_applicability_append_only before update or delete on qms_applicability
    for each row execute function wqo_append_only();

-- documents a person names as the evidence of a control point; unlinking is a new row
create table qms_evidence (
    id          bigserial primary key,
    standard    text not null,
    control     text not null,
    document_id bigint not null references documents (id),
    linked      boolean not null,
    email       text not null,
    note        text not null default '',
    at          timestamptz not null default now()
);
create index qms_evidence_control on qms_evidence (standard, control, document_id, id);
create trigger qms_evidence_append_only before update or delete on qms_evidence
    for each row execute function wqo_append_only();

-- every evaluation of the control points, kept as it was
create table qms_evaluations (
    id       bigserial primary key,
    pack_id  bigint not null references qms_packs (id),
    day      date not null,                        -- the company's day it describes
    at       timestamptz not null default now(),
    trigger  text not null check (trigger in ('enabled', 'daily', 'manual', 'changed')),
    email    text,
    results  jsonb not null,                       -- {control: {status, detail, problems, evidence}}
    counts   jsonb not null                        -- {met, not_met, unknown, not_applicable}
);
create index qms_evaluations_pack on qms_evaluations (pack_id, id);
create trigger qms_evaluations_append_only before update or delete on qms_evaluations
    for each row execute function wqo_append_only();
