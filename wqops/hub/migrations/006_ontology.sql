-- Ops hub objects (ADR-0007): projected from erp_events and the company manifest; can be rebuilt from scratch.
create table ont_objects (
    type       text not null,
    key        text not null,
    domain     text not null,
    title      text not null,
    props      jsonb not null default '{}',
    deleted    boolean not null default false,
    search     text not null default '',
    updated_at timestamptz not null default now(),
    primary key (type, key)
);
create index ont_objects_search on ont_objects (lower(search) text_pattern_ops);

create table ont_links (
    type     text not null,
    src_type text not null,
    src_key  text not null,
    dst_type text not null,
    dst_key  text not null,
    primary key (src_type, src_key, type, dst_type, dst_key)
);
create index ont_links_dst on ont_links (dst_type, dst_key);

-- what happened to each object, with the ERPNext event it came from
create table ont_history (
    id       bigserial primary key,
    type     text not null,
    key      text not null,
    event_id bigint,
    kind     text not null,
    at       text not null,
    changes  jsonb not null default '{}'
);
create index ont_history_obj on ont_history (type, key, id);

create table ont_state (
    name  text primary key,
    value jsonb not null
);
