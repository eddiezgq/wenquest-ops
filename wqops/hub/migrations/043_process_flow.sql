-- Process flow charts, step 22d (ADR-0022): a company draws its production process - operations, inspections, moves,
-- storage - in order, with branches such as rework loops and scrap. Each step can name what it rests on: controlled
-- documents (by number), the PFMEA rows that analyse it, the incoming inspection plan, the production template and
-- the measuring equipment. A flow chart is a controlled document: approved with a signature by someone who did not own
-- or edit it, then fixed with what its links pointed to and a fingerprint; revised as a new version. Nothing is
-- deleted once approved.

create table flow_charts (
    id              bigserial primary key,
    name            text not null,
    version         integer not null default 1 check (version >= 1),
    previous_id     bigint references flow_charts (id),
    title           text not null check (title <> ''),
    item_code       text,
    scope           text not null default '',
    owner           text,
    status          text not null default 'draft' check (status in ('draft', 'approved', 'superseded', 'withdrawn')),
    editors         text[] not null default '{}',
    approved_by     text,
    approved_at     timestamptz,
    resolved        jsonb,                 -- what each link pointed to at approval
    fingerprint     text,
    withdraw_reason text,
    created_by      text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (name, version),
    check (status not in ('approved', 'superseded') or (approved_by is not null and approved_at is not null
           and resolved is not null and fingerprint is not null and approved_by is distinct from owner
           and approved_by <> created_by and not (approved_by = any(editors)))),
    check (status in ('approved', 'superseded') or (approved_by is null and approved_at is null and resolved is null
           and fingerprint is null)),
    check (status <> 'withdrawn' or withdraw_reason is not null)
);
create unique index flow_charts_one_draft on flow_charts (name) where status = 'draft';

create or replace function wqo_flow_chart_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'flow charts are kept: withdraw a draft with a reason';
    end if;
    if (new.name, new.version, new.previous_id, new.created_by, new.created_at)
            is distinct from (old.name, old.version, old.previous_id, old.created_by, old.created_at) then
        raise exception 'flow chart % keeps its number, version and origin', old.name;
    end if;
    if not (old.editors <@ new.editors) then
        raise exception 'flow chart % keeps everyone who edited it', old.name;
    end if;
    if old.status <> 'draft' and (to_jsonb(new) - 'status' - 'updated_at') is distinct from
            (to_jsonb(old) - 'status' - 'updated_at') then
        raise exception 'flow chart % v% is %: it is fixed (revise it as a new version)', old.name, old.version,
            old.status;
    end if;
    if old.status = 'approved' and new.status = 'superseded' and not exists (
            select 1 from flow_charts where previous_id = old.id and status = 'approved') then
        raise exception 'flow chart % v% is superseded only by an approved newer version', old.name, old.version;
    end if;
    if old.status = 'draft' and new.status = 'approved' and not exists (
            select 1 from signatures where kind = 'flow_chart' and ref_id = old.id and email = new.approved_by) then
        raise exception 'flow chart % is approved only with the approver''s signature', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('approved', 'withdrawn'))
            or (old.status = 'approved' and new.status = 'superseded')) then
        raise exception 'flow chart % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger flow_charts_kept before update or delete on flow_charts
    for each row execute function wqo_flow_chart_kept();

create table flow_steps (
    id          bigserial primary key,
    chart_id    bigint not null references flow_charts (id),
    seq         integer not null,
    code        text not null default '',     -- the company's operation number, e.g. 10, 20
    kind        text not null check (kind in ('operation', 'inspection', 'move', 'store', 'delay')),
    name        text not null check (name <> ''),
    description text not null default '',
    branches    jsonb not null default '[]',  -- [{to: seq, label, kind: rework | scrap | other}]
    links       jsonb not null default '{}',  -- {documents: [number], fmea: [{name, seq}], plan: item, template:
                                              --  code, gauges: [code]}
    unique (chart_id, seq)
);

create or replace function wqo_flow_step_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    select status into st from flow_charts where id = (case when tg_op = 'DELETE' then old.chart_id
                                                            else new.chart_id end) for share;
    if st <> 'draft' then
        raise exception 'the flow chart is %: its steps are fixed', st;
    end if;
    if tg_op = 'UPDATE' and new.chart_id <> old.chart_id then
        raise exception 'a step stays in its flow chart';
    end if;
    return case when tg_op = 'DELETE' then old else new end;
end $$;
create trigger flow_steps_kept before insert or update or delete on flow_steps
    for each row execute function wqo_flow_step_kept();

create table flow_log (
    id       bigserial primary key,
    chart_id bigint not null references flow_charts (id),
    at       timestamptz not null default now(),
    email    text,
    action   text not null,
    note     text not null default ''
);
create index flow_log_ref on flow_log (chart_id, id);
create trigger flow_log_append_only before update or delete on flow_log
    for each row execute function wqo_append_only();
