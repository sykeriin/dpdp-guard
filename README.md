# DPDP Guard

Compliance layer for chatbots and AI agents under India's DPDP Act / Rules 2025. A `guard()` call runs before your agent: it captures per-purpose consent in chat, masks PII before it reaches logs, recognises rights requests ("delete my data" / "meri details hatao"), and writes everything to a tamper-evident ledger that drives erasure jobs and an audit pack.

> **Not legal advice. Not a registered Consent Manager.** Notice and breach templates in `notices/` and `server/app/breach.py` are drafts that need review by a privacy lawyer before production use. Read the primary Rules text (Rules 3, 6, 7, 8, 10-12, 14) yourself.

## Layout
| Path | What |
|---|---|
| `sdk-python/` | `dpdp_guard`: Guard (consent, rights, guardian flow, fail-closed), PII extractor, intent classifier, notices, local SQLite store, HTTP store |
| `server/` | FastAPI ledger + rights/erasure/breach/audit APIs, Postgres schema (append-only trigger, RLS), workers, connectors, bot checker |
| `dashboard/` | Next.js: login (httpOnly cookie via same-origin proxy), consents, rights queue, erasure, connectors, principal lookup, notices, breach kit, audit pack, public bot checker |
| `sdk-node/` | thin client for `/v1/guard` (n8n, Node webhooks) |
| `examples/` | WhatsApp Cloud webhook, LangGraph wrapper, `e2e_demo.py` |
| `docs/` | `dpdp-mapping.md` (rule -> feature), `intent-eval.md` (measured accuracy), `validation-kit.md` (interview script, outreach, kill rule) |
| `scripts/` | `test_all.sh`, `setup_db.sh`, `dashboard_e2e.js` |

## Quick start (local, no server)
```python
from dpdp_guard import Guard
guard = Guard("acme", "Acme Store", required_purposes=["order_updates"], optional_purposes=["marketing"])
r = guard(message, user_id, "whatsapp")
send(agent(r.message) if r.action == "forward" else r.reply_text)
```
`r.message` is the raw text for your agent; `r.masked_message` is what gets logged. Tag records in your CRM / vector DB with `guard.pid(user_id)` so erasure can find them.

## Run the stack
```bash
cd sdk-python && pip install -e . && cd ..
pip install fastapi uvicorn "psycopg[binary]" psycopg_pool reportlab httpx pyyaml pytest
# needs Postgres with db `dpdpguard`, owner `guard`; see docker-compose.yml, or:
docker compose up --build        # db + api (:8000) + dashboard (:3000)
```
Create a tenant: `curl -XPOST :8000/admin/tenants -H 'X-Admin-Token: change-me' -H 'content-type: application/json' -d '{"id":"acme","name":"Acme"}'` -> API key. Log in with it on the dashboard Overview page.

## Tests
One command runs everything (real Postgres, live API, built dashboard, headless browser). It runs every step and fails if any failed:
```bash
./scripts/setup_db.sh        # once, as a Postgres superuser (dev credentials)
./scripts/test_all.sh
```
Individual suites: `cd sdk-python && python -m pytest` (26) | `cd server && PYTHONPATH=. python -m pytest tests` (24) | `PYTHONPATH=sdk-python python -m pytest examples/tests` (5) | `cd sdk-node && node test.mjs` | `python examples/e2e_demo.py` | `node scripts/dashboard_e2e.js`.

## Configuration
| Variable | Where | Purpose |
|---|---|---|
| `ADMIN_TOKEN` | api | required to create tenants (`POST /admin/tenants`) |
| `DATABASE_URL`, `ADMIN_DATABASE_URL` | api | app role (RLS enforced, not superuser) and owner role (schema, tenants) |
| `RUN_WORKERS=1` | api | background retention + erasure loop (30s) |
| `CHECKER_RATE_PER_MIN` | api | public checker limit per IP, default 20 (in-memory, single process; behind a proxy it sees the proxy's IP) |
| `GUARD_API_URL` | dashboard | server-side URL of the API (default `http://localhost:8000`) |
| `INSECURE_COOKIES=1` | dashboard | allow the session cookie over plain http outside Chromium-on-localhost. Leave unset in production (cookie is `Secure`) |
| `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | webhook example | Meta signature check (refuses all traffic if unset) and handshake token |

Per-tenant purposes, retention and business name: `PUT /v1/config` (see `server/tests/test_server.py::test_tenant_config_custom_purposes_drive_guard`).

## Status: what is and isn't verified
**Verified by `scripts/test_all.sh`:** per-purpose consent (a bare "yes" is rejected), PII masking, hash-chain + tamper detection (including owner-level edits), RLS tenant isolation as a non-superuser role, erasure via built-in transcripts + SQL connector + signed webhook, purpose-scoped erasure (withdrawing marketing leaves order-update data alone, including after a failed retry), retention expiry, fail-closed guard when the ledger is down, WhatsApp webhook signature check and duplicate-delivery handling, guardian-consent flow, breach kit, audit-pack ZIP, tenant-configurable purposes, the dashboard in a real browser (httpOnly cookie session; key never reachable from page JS; connectors, lookup, notices, checker, audit download), Node SDK.

**Intent classifier: measure, don't trust.** Rules-only accuracy on phrasings written after the rules was **73.9%** (0 false positives, 69 cases); the first fresh set scored **58.9%** before I tuned on it. Details and caveats in `docs/intent-eval.md`. Every miss means a rights request goes unrecognised. The LLM fallback (`use_llm=True`) is implemented but **has never been run**.

**Not verified / not built**
- HubSpot, Zoho, Pinecone and Google Sheets connectors are written from API docs and tested only against mocked HTTP (Sheets) or not at all. The `pgvector` connector is a plain `DELETE ... WHERE principal=`, tested on an ordinary table. Only the webhook connector honours single-purpose scope; the others are skipped for purpose-scoped jobs rather than over-deleting.
- Docker images are not built or tested (no daemon in the dev environment).
- **Guardian consent is self-asserted**: the child types a number and whoever replies from it is treated as the guardian. There is no identity or relationship verification (no DigiLocker etc.). The child learns the outcome on their next message. The guardian invite is a business-initiated message and outside the 24h window needs an approved WhatsApp template. Needs legal review before anyone relies on it for under-18s.
- Voice channel, Consent Manager integration, billing, multi-user accounts: not built.
- Erasure from external stores needs the customer to tag records with the principal hash (`guard.pid(user_id)`) or use the webhook connector: the server holds only hashes by design.
- Events are append-only, so never put raw PII in event payloads. Don't run `/v1/principals/lookup` or the audit pack from an untrusted network: the dashboard session is one API key per tenant.
- Webhook de-duplication and the checker rate limit are in-memory: use Redis/DB if you run more than one process.
- Notices and breach templates are drafts. A lawyer must review them. This is tooling, not legal advice.
