#!/usr/bin/env bash
# starts the ledger API on :8000 (pidfile: /tmp/dpdp_api.pid)
cd "$(dirname "$0")/server" && . ../.venv/bin/activate
[ -f /tmp/dpdp_api.pid ] && kill "$(cat /tmp/dpdp_api.pid)" 2>/dev/null && sleep 1
if (echo > /dev/tcp/127.0.0.1/8000) 2>/dev/null; then echo "port 8000 still in use; refusing to start" >&2; exit 1; fi
PYTHONPATH=. ADMIN_TOKEN="${ADMIN_TOKEN:-adm}" nohup python -m uvicorn app.main:app --port 8000 > /tmp/uv.log 2>&1 &
echo $! > /tmp/dpdp_api.pid
