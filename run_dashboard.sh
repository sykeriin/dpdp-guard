#!/usr/bin/env bash
# builds + serves the dashboard on :3000 (pidfile: /tmp/dpdp_dash.pid). Runs the Next server directly so the pid is the real server.
cd "$(dirname "$0")/dashboard"
[ -f /tmp/dpdp_dash.pid ] && kill "$(cat /tmp/dpdp_dash.pid)" 2>/dev/null && sleep 1
[ "$1" = "--build" ] && npx next build >/tmp/next_build.log 2>&1
if (echo > /dev/tcp/127.0.0.1/3000) 2>/dev/null; then echo "port 3000 still in use by another process; refusing to serve a stale build" >&2; exit 1; fi
nohup node node_modules/next/dist/bin/next start -p 3000 > /tmp/next.log 2>&1 &
echo $! > /tmp/dpdp_dash.pid
