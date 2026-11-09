-- PLM step 27b (round 124): English names for the parts manual, and one exploded view per BOM revision.
alter table plm_parts add column name_en text not null default '',
    add column name_en_state text not null default 'none' check (name_en_state in ('none', 'draft', 'confirmed'));

-- the layout of a page of the parts manual: a picture, not design data, so it may change after the BOM is released
create table plm_explodes (
    id           bigserial primary key,
    bom_id       bigint not null unique references plm_boms (id),
    kind         text not null default 'model' check (kind in ('model', 'image')),
    layout       jsonb not null default '{}'::jsonb,   -- camera, how far apart, moves per part, parts drawn
    balloons     jsonb not null default '[]'::jsonb,   -- [{part_id, x, y, ax, ay}] as fractions of the picture
    image_sha    text,                                  -- an uploaded drawing (kind image)
    image_name   text,
    snapshot_sha text,                                  -- the picture as saved, balloons drawn in
    saved_by     text,
    saved_at     timestamptz
);

-- the AI's English name drafts are runs like any other
alter table ai_runs drop constraint ai_runs_kind_check;
alter table ai_runs add constraint ai_runs_kind_check
    check (kind in ('ask', 'brief', 'draft', 'classify', 'ledger', 'workflow', 'document', 'setup', 'cause', 'fmea',
                    'plm-impact', 'plm-names'));
