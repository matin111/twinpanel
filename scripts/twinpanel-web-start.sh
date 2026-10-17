#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/twinpanel/current"
PORT="${1:-${TWINPANEL_WEB_PORT:-3000}}"
HOST="${TWINPANEL_WEB_HOST:-127.0.0.1}"

[[ "$PORT" =~ ^[0-9]+$ ]] || {
  echo "Invalid TwinPanel web port: $PORT" >&2
  exit 2
}

if [[ -f "$ROOT/.next/standalone/server.js" ]]; then
  cd "$ROOT/.next/standalone"
  export NODE_ENV="${NODE_ENV:-production}"
  export HOSTNAME="$HOST"
  export PORT="$PORT"
  exec /usr/bin/node server.js
fi

# Compatibility path for releases created before standalone artifacts were
# introduced. Keeping this fallback makes rollback to an older release safe.
if [[ -f "$ROOT/node_modules/next/dist/bin/next" ]]; then
  cd "$ROOT"
  exec /usr/bin/node "$ROOT/node_modules/next/dist/bin/next" start -H "$HOST" -p "$PORT"
fi

echo "TwinPanel frontend runtime is missing (standalone and legacy Next.js runtimes not found)." >&2
exit 1
