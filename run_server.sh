#!/usr/bin/env bash
# starts the ledger API on :8000 (pidfile: /tmp/dpdp_api.pid)
cd "$(dirname "$0")/server" && . ../.venv/bin/activate
[ -f /tmp/dpdp_api.pid ] && kill "$(cat /tmp/dpdp_api.pid)" 2>/dev/null; sleep 1
PYTHONPATH=. ADMIN_TOKEN="${ADMIN_TOKEN:-adm}" nohup python -m uvicorn app.main:app --port 8000 > /tmp/uv.log 2>&1 &
echo $! > /tmp/dpdp_api.pid
