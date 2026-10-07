#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-3010}"
API_URL="${API_URL:-${TWINPANEL_BACKEND_URL:-}}"

fail(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info(){ printf '[TwinPanel] %s\n' "$*"; }

command -v node >/dev/null 2>&1 || fail "Node.js is not installed. Node >=22.13 is required."
command -v npm  >/dev/null 2>&1 || fail "npm is not installed."

node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && b<13)) process.exit(1)' \
  || fail "Node >=22.13 is required. Current: $(node -v)"

if command -v ss >/dev/null 2>&1; then
  if ss -lnt "( sport = :$PORT )" 2>/dev/null | tail -n +2 | grep -q .; then
    fail "Preview port $PORT is already in use."
  fi
fi

# Browser calls stay same-origin. Next rewrites /v1/* and /health to this backend.
export NEXT_PUBLIC_API_BASE=""
if [[ -n "$API_URL" ]]; then
  export TWINPANEL_BACKEND_URL="${API_URL%/}"
else
  export TWINPANEL_BACKEND_URL="http://127.0.0.1:8095"
fi

info "Backend proxy: $TWINPANEL_BACKEND_URL"
info "Project: $ROOT"

if [[ ! -x node_modules/.bin/next ]]; then
  info "Installing dependencies..."
  npm install --include=optional
fi

CURRENT_REV="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BUILT_REV=""
[[ -f .next/.twinpanel-preview-rev ]] && BUILT_REV="$(cat .next/.twinpanel-preview-rev 2>/dev/null || true)"

if [[ ! -f .next/BUILD_ID || "$BUILT_REV" != "$CURRENT_REV" ]]; then
  info "Building UI for $CURRENT_REV..."
  rm -rf .next
  npm run build
  printf '%s\n' "$CURRENT_REV" > .next/.twinpanel-preview-rev
else
  info "Build is current: $CURRENT_REV"
fi

info "Preview: http://127.0.0.1:$PORT"
info "Stop with Ctrl+C"

export PORT
exec npm run start
