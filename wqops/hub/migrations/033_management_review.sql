-- Management review, step 17j (ADR-0017; dee-qms PLAN-MR): the inputs are counted from the records of every module
-- for the period and frozen with a fingerprint; top management meets, writes its assessment of each input, its
-- conclusion and the actions decided, and the chair signs. Nothing is deleted.

create table mgmt_reviews (
    id            bigserial primary key,
    name          text not null unique,
    title         text not null check (title <> ''),
    period_start  date not null,
    period_end    date not null,
    meeting_on    date,
    chair         text,
    attendees     text not null default '',
    status        text not null default 'draft' check (status in ('draft', 'frozen', 'closed', 'cancelled')),
    inputs        jsonb,                         -- the counted inputs, frozen
    fingerprint   text,                          -- SHA-256 of the inputs
    collected_by  text,
    collected_at  timestamptz,
    notes         jsonb not null default '{}',   -- the meeting's assessment of each input
    conclusion    text not null default '',
    involved      text[] not null default '{}',  -- everyone who prepared it: collected inputs, wrote notes or actions
    signed_by     text,
    signed_at     timestamptz,
    cancel_reason text,
    created_by    text not null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    check (period_start <= period_end),
    check (status = 'draft' or status = 'cancelled' or (inputs is not null and fingerprint is not null)),
    check (status <> 'closed' or (signed_by is not null and signed_at is not null and signed_by = chair
           and meeting_on is not null and attendees <> '' and conclusion <> '' and not (signed_by = any(involved)))),
    check (status <> 'cancelled' or cancel_reason is not null)
);

create or replace function wqo_mgmt_review_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'management reviews are kept: cancel one with a reason';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'draft' or new.signed_by is not null or new.signed_at is not null or new.inputs is not null
           or new.fingerprint is not null or new.collected_by is not null or new.collected_at is not null
           or new.involved <> '{}' or new.cancel_reason is not null then
            raise exception 'a management review starts as a draft';
        end if;
        return new;
    end if;
    if old.status in ('closed', 'cancelled') then
        raise exception 'management review % is %: it cannot change', old.name, old.status;
    end if;
    if (new.name, new.created_by, new.created_at) is distinct from (old.name, old.created_by, old.created_at) then
        raise exception 'management review % keeps its number and origin', old.name;
    end if;
    if old.status <> 'draft' and (new.period_start, new.period_end) is distinct from (old.period_start, old.period_end) then
        raise exception 'management review %: the inputs are collected for this period', old.name;
    end if;
    if (new.inputs, new.fingerprint, new.collected_by) is distinct from (old.inputs, old.fingerprint, old.collected_by)
       and (new.collected_at is not distinct from old.collected_at or new.inputs is null
            or not (new.collected_by = any(new.involved))) then
        raise exception 'management review %: the inputs change only when they are collected again', old.name;
    end if;
    if new.status <> 'closed' and (new.signed_by is not null or new.signed_at is not null) then
        raise exception 'management review % is not signed', old.name;
    end if;
    if new.status = 'closed' and (new.meeting_on < new.period_start
                                  or new.meeting_on > (now() at time zone 'UTC')::date + 1) then
        raise exception 'management review %: the meeting is held after the period starts and not in the future', old.name;
    end if;
    if not (old.involved <@ new.involved) then
        raise exception 'management review % keeps everyone who prepared it', old.name;
    end if;
    if new.status = 'closed' and not exists (select 1 from signatures where kind = 'mgmt_review' and ref_id = old.id
                                             and email = new.signed_by) then
        raise exception 'management review % is closed only with the chair''s signature', old.name;
    end if;
    if not (old.status = new.status or (old.status = 'draft' and new.status in ('frozen', 'cancelled'))
            or (old.status = 'frozen' and new.status in ('closed', 'cancelled'))) then
        raise exception 'management review % cannot go from % to %', old.name, old.status, new.status;
    end if;
    return new;
end $$;
create trigger mgmt_reviews_kept before insert or update or delete on mgmt_reviews
    for each row execute function wqo_mgmt_review_kept();

create table mgmt_review_actions (
    id          bigserial primary key,
    review_id   bigint not null references mgmt_reviews (id),
    text        text not null check (text <> ''),
    owner       text not null,
    due         date not null,
    capa_id     bigint references capas (id),
    status      text not null default 'open' check (status in ('open', 'done')),
    evidence    text not null default '',
    done_by     text,
    done_at     timestamptz,
    created_by  text not null,
    created_at  timestamptz not null default now(),
    check (status <> 'done' or (done_by is not null and done_at is not null and evidence <> ''))
);
create index mgmt_review_actions_ref on mgmt_review_actions (review_id, id);

create or replace function wqo_mgmt_action_kept() returns trigger language plpgsql as $$
declare
    st text;
begin
    if tg_op = 'DELETE' then
        raise exception 'decided actions are kept';
    end if;
    select status into st from mgmt_reviews where id = new.review_id for share;
    if tg_op = 'INSERT' then
        if st not in ('draft', 'frozen') or new.status <> 'open' then
            raise exception 'actions are decided before the review is signed';
        end if;
        return new;
    end if;
    if old.status = 'done' then
        raise exception 'the action is done: it cannot change';
    end if;
    if st = 'cancelled' then
        raise exception 'the review was cancelled: its actions are fixed';
    end if;
    if (new.review_id, new.created_by, new.created_at) is distinct from (old.review_id, old.created_by, old.created_at)
       or (st = 'closed' and (new.text, new.owner, new.due, new.capa_id) is distinct from
           (old.text, old.owner, old.due, old.capa_id)) then
        raise exception 'the review is signed: what was decided is fixed';
    end if;
    return new;
end $$;
create trigger mgmt_review_actions_kept before insert or update or delete on mgmt_review_actions
    for each row execute function wqo_mgmt_action_kept();

create table mgmt_review_log (
    id        bigserial primary key,
    review_id bigint not null references mgmt_reviews (id),
    at        timestamptz not null default now(),
    email     text,
    action    text not null,
    note      text not null default ''
);
create index mgmt_review_log_ref on mgmt_review_log (review_id, id);
create trigger mgmt_review_log_append_only before update or delete on mgmt_review_log
    for each row execute function wqo_append_only();
