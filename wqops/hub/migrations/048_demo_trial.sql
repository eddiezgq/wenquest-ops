-- ADR-0027: trial accounts in the demo company, opened from the WenQuest website; they end after WQO_TRIAL_DAYS.
alter table users add column if not exists expires_at timestamptz;
alter table users drop constraint if exists users_source;
alter table users add constraint users_source check (source in ('manifest', 'app', 'trial'));
