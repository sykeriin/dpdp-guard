#!/usr/bin/env bash
# Runs every suite against real Postgres + live API + built dashboard. Runs ALL steps, then exits non-zero if any failed.
# Needs: Postgres 16 with role/db from scripts/setup_db.sh, python venv at .venv, node 22, playwright (global).
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD; FAILED=(); export ADMIN_TOKEN="${ADMIN_TOKEN:-adm}"
. .venv/bin/activate

if command -v pg_lsclusters >/dev/null && pg_lsclusters | grep -q " down "; then pg_ctlcluster 16 main start; sleep 3; fi
step() { local name="$1"; shift; echo; echo "=== $name"; if "$@"; then echo "--- PASS: $name"; else echo "--- FAIL: $name"; FAILED+=("$name"); fi; }
wait_for() { for _ in $(seq 1 40); do curl -sf "$1" >/dev/null && return 0; sleep 1; done; return 1; }

step "sdk-python tests"   bash -c "cd sdk-python && python -m pytest -q tests"
step "server tests"       bash -c "cd server && PYTHONPATH=. python -m pytest -q tests 2>&1 | grep -vE \"couldn't stop|hint: you can try\""
step "scripts tests (kill-rule, llm-eval harness)" python -m pytest -q scripts/test_killrule.py scripts/test_eval_llm.py
step "example tests"      bash -c "PYTHONPATH=sdk-python python -m pytest -q examples/tests"

step "api start"       ./run_server.sh
step "api up"          wait_for http://localhost:8000/health
step "dashboard start" ./run_dashboard.sh --build
step "dashboard up"    wait_for http://localhost:3000/

step "node sdk (live API)"   bash -c "cd sdk-node && node test.mjs"
step "e2e demo (webhook)"    python examples/e2e_demo.py
step "dashboard e2e (browser)" env NODE_PATH="$(npm root -g)" node scripts/dashboard_e2e.js "${SHOTS:-}"

[ -f /tmp/dpdp_api.pid ] && kill "$(cat /tmp/dpdp_api.pid)" 2>/dev/null
[ -f /tmp/dpdp_dash.pid ] && kill "$(cat /tmp/dpdp_dash.pid)" 2>/dev/null
sleep 2
for port in 3000 8000; do if (echo > /dev/tcp/127.0.0.1/$port) 2>/dev/null; then echo "WARNING: port $port still open after shutdown (orphan process?)"; FAILED+=("shutdown:$port"); fi; done
echo; if [ ${#FAILED[@]} -eq 0 ]; then echo "ALL GREEN"; else echo "FAILED: ${FAILED[*]}"; exit 1; fi
