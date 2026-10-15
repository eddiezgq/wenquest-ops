-- Document control and training acknowledgement, step 17d (ADR-0017; dee-qms PLAN-DOC, PLAN-TRAINING): an approved
-- revision can take effect on a planned day; documents are reviewed at set intervals, each review approved by
-- someone other than the reviewer; people named for a document confirm with their password that they have read the
-- revision in effect.

alter table documents drop constraint documents_status_check;
alter table documents add constraint documents_status_check
    check (status in ('to_classify', 'to_review', 'confirmed', 'draft', 'in_review', 'approved', 'effective',
                      'obsolete', 'rejected'));
-- who must read a document (carried to its next revisions) and whether this revision needs it
alter table documents add column trainees jsonb not null default '{"roles": [], "people": []}';
alter table documents add column needs_training boolean not null default false;

-- per document type: how often it is reviewed and how long people have to read a new revision; the company's values
create table doc_type_settings (
    doc_type       text primary key,
    review_months  integer check (review_months is null or review_months between 1 and 120),
    training_days  integer not null default 30 check (training_days between 1 and 365),
    email          text not null,
    at             timestamptz not null default now()
);
insert into doc_type_settings (doc_type, review_months, training_days, email) values
    ('procedure', 36, 30, 'WenQuest Ops (default)'), ('work_instruction', 36, 30, 'WenQuest Ops (default)'),
    ('form', 36, 30, 'WenQuest Ops (default)');

-- a review of the revision in effect: the reviewer records it, someone else approves it (signed)
create table doc_reviews (
    id           bigserial primary key,
    document_id  bigint not null references documents (id),
    outcome      text not null check (outcome in ('no_change', 'change', 'postponed')),
    note         text not null default '',
    revision_id  bigint references documents (id),       -- the new revision a "change" review started
    next_due     date,                                    -- chosen by a person when postponed
    reviewed_by  text not null,
    reviewed_on  date not null,
    status       text not null default 'submitted' check (status in ('submitted', 'approved', 'rejected')),
    approved_by  text,
    approved_at  timestamptz,
    decision_note text not null default '',
    check (outcome <> 'postponed' or (next_due is not null and note <> '')),
    check (outcome <> 'change' or revision_id is not null),
    check (status <> 'approved' or (approved_by is not null and approved_at is not null and approved_by <> reviewed_by))
);
create index doc_reviews_doc on doc_reviews (document_id, id);

create or replace function wqo_doc_review_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'document reviews are kept';
    end if;
    if old.status <> 'submitted' or (new.document_id, new.outcome, new.note, new.revision_id, new.next_due,
            new.reviewed_by, new.reviewed_on) is distinct from (old.document_id, old.outcome, old.note,
            old.revision_id, old.next_due, old.reviewed_by, old.reviewed_on) then
        raise exception 'review % is decided or its content is fixed', old.id;
    end if;
    return new;
end $$;
create trigger doc_reviews_kept before update or delete on doc_reviews
    for each row execute function wqo_doc_review_kept();

-- read and understood: one record per person and revision
create table doc_training (
    id            bigserial primary key,
    document_id   bigint not null references documents (id),
    email         text not null,
    due           date not null,
    status        text not null default 'pending'
                  check (status in ('pending', 'acknowledged', 'waived', 'superseded')),
    done_at       timestamptz,
    done_by       text,                                  -- the person, or who waived it
    note          text not null default '',              -- why it was waived; which revision superseded it
    created_at    timestamptz not null default now(),
    unique (document_id, email),
    check (status = 'pending' or (done_at is not null)),
    check (status <> 'acknowledged' or done_by = email),
    check (status <> 'waived' or (done_by is not null and done_by <> email and note <> ''))
);
create index doc_training_person on doc_training (email, status);

create or replace function wqo_doc_training_kept() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'training records are kept';
    end if;
    if old.status <> 'pending' or (new.document_id, new.email, new.due, new.created_at) is distinct from
            (old.document_id, old.email, old.due, old.created_at) then
        raise exception 'training record % is %: it cannot change', old.id, old.status;
    end if;
    return new;
end $$;
create trigger doc_training_kept before update or delete on doc_training
    for each row execute function wqo_doc_training_kept();
