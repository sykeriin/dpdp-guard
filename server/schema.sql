create table if not exists tenants(id text primary key, name text not null, created_at timestamptz default now());
alter table tenants add column if not exists config jsonb not null default '{}';
create table if not exists api_keys(key_hash text primary key, tenant_id text not null references tenants(id), label text, created_at timestamptz default now());

create table if not exists events(
  seq bigserial primary key, tenant_id text not null, ts timestamptz not null default now(),
  type text not null, principal text, event jsonb not null, prev_hash text not null, hash text not null);
create index if not exists events_tenant_seq on events(tenant_id, seq);
create or replace function events_immutable() returns trigger as $$ begin raise exception 'events is append-only'; end $$ language plpgsql;
drop trigger if exists events_no_update on events;
create trigger events_no_update before update or delete on events for each row execute function events_immutable();
drop trigger if exists events_no_truncate on events;
create trigger events_no_truncate before truncate on events for each statement execute function events_immutable();

create table if not exists consents(id bigserial primary key, tenant_id text not null, principal text not null, purpose text not null,
  granted boolean not null, channel text, notice_version text, ts timestamptz default now());
create table if not exists pii_records(id text primary key, tenant_id text not null, principal text not null, kind text, purpose text,
  masked text, expires_at timestamptz not null, location text default 'transcript', erased_at timestamptz);
create table if not exists state(tenant_id text not null, principal text not null, key text not null, value jsonb, primary key(tenant_id, principal, key));
create table if not exists rights_requests(ref text primary key, tenant_id text not null, principal text not null, kind text not null,
  status text not null default 'open', detail text, created_at timestamptz default now(), resolved_at timestamptz);
create table if not exists erasure_jobs(id bigserial primary key, tenant_id text not null, principal text not null, reason text,
  rights_ref text, status text not null default 'queued', attempts int default 0, run_after timestamptz default now(),
  created_at timestamptz default now(), finished_at timestamptz, results jsonb default '[]');
alter table erasure_jobs add column if not exists scope text not null default 'all';
create table if not exists connectors(id bigserial primary key, tenant_id text not null, kind text not null, name text, config jsonb default '{}');
create table if not exists breaches(id bigserial primary key, tenant_id text not null, title text, description text,
  detected_at timestamptz not null default now(), affected_principals text[] default '{}', data_kinds text[] default '{}',
  status text default 'open', board_report_due timestamptz, users_notified_at timestamptz, board_report_filed_at timestamptz);
-- built-in transcript store (what the bot keeps); erasure connector 'transcripts' deletes from here
create table if not exists transcripts(id bigserial primary key, tenant_id text not null, principal text not null, role text, text text, ts timestamptz default now());
create table if not exists access_log(id bigserial primary key, tenant_id text not null, actor text, action text, resource text, ts timestamptz default now());

do $$ declare t text; begin
  foreach t in array array['events','consents','pii_records','state','rights_requests','erasure_jobs','connectors','breaches','transcripts','access_log'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists tenant_iso on %I', t);
    execute format($p$create policy tenant_iso on %I using (tenant_id = current_setting('app.tenant', true)) with check (tenant_id = current_setting('app.tenant', true))$p$, t);
  end loop;
end $$;

do $$ begin
  if not exists (select from pg_roles where rolname='guard_app') then create role guard_app login password 'guard_app'; end if;
end $$;
grant select, insert, update, delete on all tables in schema public to guard_app;
grant usage, select on all sequences in schema public to guard_app;
