#!/usr/bin/env bash
# builds + serves the dashboard on :3000 (pidfile: /tmp/dpdp_dash.pid)
cd "$(dirname "$0")/dashboard"
[ -f /tmp/dpdp_dash.pid ] && kill "$(cat /tmp/dpdp_dash.pid)" 2>/dev/null
[ "$1" = "--build" ] && npx next build >/tmp/next_build.log 2>&1
nohup npx next start -p 3000 > /tmp/next.log 2>&1 &
echo $! > /tmp/dpdp_dash.pid
