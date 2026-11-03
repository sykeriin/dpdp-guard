#!/usr/bin/env bash
# One-time local setup (as a Postgres superuser). Idempotent. Dev credentials only: change them for anything real.
set -e
psql "${PG_SUPER_URL:-postgresql:///postgres}" -v ON_ERROR_STOP=1 <<'SQL'
select 'create role guard login password ''guard'' superuser' where not exists (select from pg_roles where rolname='guard') \gexec
select 'create database dpdpguard owner guard' where not exists (select from pg_database where datname='dpdpguard') \gexec
SQL
