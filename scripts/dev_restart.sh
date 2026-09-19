#!/usr/bin/env bash
# Restart the local API and web servers cleanly. It does NOT build: use
# `make demo`, which builds with the API base inlined and then calls this.
#
# `next start` leaves a `next-server` process that keeps port 3000 bound; a new
# start then fails with EADDRINUSE and the browser silently keeps getting the
# *previous* build's chunks. That failure mode looks like a frontend bug, so
# this script always frees the ports first.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

# Match on the *start* of the command line only. A substring match would also
# hit this script's own shell, whose command line quotes the patterns.
kill_starting_with() {
  local prefix="$1"
  local label="$2"
  for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
    [ -r "/proc/$pid/cmdline" ] || continue
    [ "$pid" = "$$" ] && continue
    [ "$pid" = "$PPID" ] && continue
    local cmd
    cmd=$(tr "\0" " " < "/proc/$pid/cmdline" 2>/dev/null) || continue
    case "$cmd" in
      "$prefix"*) echo "[restart] killing $pid ($label)"; kill "$pid" 2>/dev/null ;;
    esac
  done
}

kill_starting_with "next-server" "web"
kill_starting_with "$ROOT/.venv/bin/python -m uvicorn" "api"
kill_starting_with ".venv/bin/python -m uvicorn" "api"
sleep 2

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

API_BASE="http://127.0.0.1:$API_PORT"

( cd "$ROOT" && PYTHONPATH=. .venv/bin/python -m uvicorn apps.api.main:app \
    --host 127.0.0.1 --port "$API_PORT" > /tmp/ecotwin-api.log 2>&1 & )
( cd "$ROOT/apps/web" && npx next start -p "$WEB_PORT" > /tmp/ecotwin-web.log 2>&1 & )

for _ in $(seq 1 40); do
  api=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$API_PORT/health" || true)
  # `/` redirects into the product, so accept the redirect as "serving".
  web=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/" || true)
  if [ "$api" = "200" ] && { [ "$web" = "200" ] || [ "$web" = "307" ] || [ "$web" = "308" ]; }; then
    # NEXT_PUBLIC_* is inlined when the bundle is BUILT, so setting it here
    # would do nothing. A build made without it serves a frontend that says
    # "Not configured" and calls no API -- correct behaviour for a
    # misconfigured deployment, and a baffling half-hour to debug locally.
    # Ask the page it actually serves, rather than guess from the bundle.
    if curl -s "http://127.0.0.1:$WEB_PORT/bms" \
       | grep -qs 'NEXT_PUBLIC_API_BASE is not set in this build'; then
      echo "[restart] the build in apps/web/.next has no API base baked in,"
      echo "[restart] so every panel will read \"Not configured\". Rebuild it:"
      echo "[restart]   cd apps/web && NEXT_PUBLIC_API_BASE=$API_BASE npm run build"
      echo "[restart] or simply: make demo"
      exit 1
    fi
    echo "[restart] api=$api web=$web ready (api base $API_BASE)"
    exit 0
  fi
  sleep 2
done
echo "[restart] timed out (api=$api web=$web)"
tail -5 /tmp/ecotwin-api.log /tmp/ecotwin-web.log
exit 1
