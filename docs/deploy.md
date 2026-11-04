# Deployment checklist (nothing here has been deployed: this is a plan, not a record)

**Data residency:** buyers will ask. Host the API, Postgres and dashboard in an Indian region (AWS ap-south-1 Mumbai / GCP asia-south1). Check where the LLM provider processes data if you enable `use_llm`; messages sent to it contain raw text.

## Must do before a pilot touches real user data
1. **Secrets:** change every dev credential (`guard`/`guard`, `guard_app`/`guard_app`, `ADMIN_TOKEN=adm`). Use the platform's secret store, not env files in git.
2. **Postgres:** managed instance, TLS on, private network only. Two roles: the owner (schema, tenant creation) and `guard_app` (non-superuser, RLS enforced: never point `DATABASE_URL` at the owner or RLS is bypassed). Verify with `select rolsuper from pg_roles where rolname = current_user` as the app role.
3. **HTTPS everywhere:** the dashboard session cookie is `Secure` by default; do not set `INSECURE_COOKIES`. Put the API behind the same TLS terminator and don't expose `/admin/*` publicly (restrict by IP/VPN).
4. **Workers:** run exactly one API replica with `RUN_WORKERS=1`, or move the loop to a separate process. Erasure uses `FOR UPDATE SKIP LOCKED` so multiple workers are safe, but the in-memory rate limits and webhook dedupe are per-process.
5. **Proxy IPs:** behind a load balancer `request.client.host` is the balancer. Configure trusted proxy headers (uvicorn `--proxy-headers --forwarded-allow-ips`) or the per-IP rate limits all collapse to one bucket.
6. **Backups vs erasure:** the ledger is append-only and holds only hashes, so restores don't resurrect raw PII, but a restored `pii_records`/`transcripts` snapshot can. Document the backup retention window in your notice and re-run erasure jobs after any restore.
7. **Log retention (Rule 6):** keep access logs and the ledger for at least one year; don't let infra log rotation delete them earlier. Don't log request bodies at the proxy.
8. **Lawyer review** of notices (`notices/notice_v1.yaml`, `server/app/breach.py`), the waitlist notice, the guardian flow, and your customer contract (liability cap, "tooling not legal advice").
9. **Company entity** to sign B2B contracts and issue invoices (the report lists this as a prerequisite).

## Nice to have
- Move rate limiting and webhook dedupe to Redis or Postgres.
- Per-user dashboard accounts instead of one API key per tenant.
- Alerting on `ledger/verify` returning `ok: false` and on erasure jobs stuck in `queued`/`failed`.
- WhatsApp: guardian invites are business-initiated messages; outside the 24h window they need an approved template (and cost per message).
