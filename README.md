# DPDP Guard

Compliance layer for chatbots and AI agents under India's DPDP Act / Rules 2025. A `guard()` call runs before your agent: it captures per-purpose consent in chat, masks PII before it reaches logs, recognises rights requests ("delete my data" / "meri details hatao"), and writes everything to a tamper-evident ledger that drives erasure jobs and an audit pack.

> **Not legal advice. Not a registered Consent Manager.** Notice and breach templates in `notices/` and `server/app/breach.py` are drafts that need review by a privacy lawyer before production use. Read the primary Rules text (Rules 3, 6, 7, 8, 10-12, 14) yourself.

## Layout
| Path | What |
|---|---|
| `sdk-python/` | `dpdp_guard`: Guard, PII extractor, intent classifier, minors heuristic, notices, local SQLite store, HTTP store |
| `server/` | FastAPI ledger + rights/erasure/breach/audit APIs, Postgres schema (append-only trigger, RLS), workers, connectors, bot checker |
| `dashboard/` | Next.js: overview, consents, rights queue, erasure, breach kit, audit pack, public bot checker |
| `sdk-node/` | thin client for `/v1/guard` (n8n, Node webhooks) |
| `examples/` | WhatsApp Cloud webhook, LangGraph wrapper, `e2e_demo.py` |
| `docs/` | `dpdp-mapping.md` (rule -> feature), `validation-kit.md` (interview script, outreach, kill rule) |

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
Create a tenant: `curl -XPOST :8000/admin/tenants -H 'X-Admin-Token: change-me' -H 'content-type: application/json' -d '{"id":"acme","name":"Acme"}'` -> API key. Paste it on the dashboard Overview page.

## Tests
```bash
cd sdk-python && python -m pytest            # 17: PII, consent, intent eval (158 phrasings), ledger tamper
cd server && PYTHONPATH=. python -m pytest tests   # 14: RLS isolation, append-only, erasure, breach, audit pack, hosted guard
cd sdk-node && ADMIN_TOKEN=adm node test.mjs       # needs API running
ADMIN_TOKEN=adm python examples/e2e_demo.py        # full flow against live API
```

## Status: what is and isn't verified
**Verified by tests/runs:** consent gate (per purpose, bare "yes" rejected), PII masking, EN/HI/Hinglish rights intents, hash-chain + tamper detection (including owner-level edits), RLS tenant isolation as a non-superuser role, erasure via built-in transcripts + generic SQL connector + signed webhook, retry on failure, retention expiry, breach kit, audit-pack ZIP, dashboard (Playwright), Node SDK.

**Not verified / known gaps**
- Intent accuracy 99% is on an eval set written by the same author as the rules: optimistic. Collect real chat phrasings before trusting it. LLM fallback (`use_llm=True`) is implemented but untested without an API key.
- HubSpot / Zoho / Pinecone connectors written from API docs, never run against live accounts. Google Sheets connector not built. The `pgvector` connector is a plain `DELETE ... WHERE principal=`; tested on a normal table, not the extension.
- Docker images not built in the dev environment.
- Erasure from external stores requires the customer to tag records with the principal hash (or use the webhook connector). The server only stores hashes, by design, so it cannot look up a phone number.
- Voice channel, parental-consent verification flow (we only detect likely minors and block), Consent Manager integration, name/address detection beyond the optional LLM pass: not built.
- Ledger events can't be deleted (append-only), which satisfies the 1-year log rule but means events must contain only hashed IDs and references. Don't put raw PII in event payloads.
- Dashboard auth is a pasted API key in localStorage; fine for a pilot, not for production. CORS origin set by `CORS_ORIGINS`.
