-- People added in the workspace (ADR-0025): a pilot company starts with only its owner in the manifest and the owner
-- adds colleagues on the People page. source tells where a person comes from; the manifest sync only deactivates
-- people who came from the manifest.
alter table users add column if not exists source text not null default 'manifest';
do $$ begin
    alter table users add constraint users_source check (source in ('manifest', 'app'));
exception when duplicate_object then null; end $$;
