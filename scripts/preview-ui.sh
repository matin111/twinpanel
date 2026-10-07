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

# Keep node_modules synchronized with package.json. This handles dependency
# additions after git pull even when Next.js was already installed previously.
DEPS_STAMP="node_modules/.twinpanel-package-hash"
PACKAGE_HASH="$(sha256sum package.json | awk '{print $1}')"
INSTALLED_HASH=""
[[ -f "$DEPS_STAMP" ]] && INSTALLED_HASH="$(cat "$DEPS_STAMP" 2>/dev/null || true)"

if [[ ! -x node_modules/.bin/next || "$INSTALLED_HASH" != "$PACKAGE_HASH" ]]; then
  info "Synchronizing dependencies..."
  npm install --include=optional --no-audit --no-fund
  mkdir -p node_modules
  printf '%s\n' "$PACKAGE_HASH" > "$DEPS_STAMP"
fi

# Extra integrity check for the QR dependency used by account delivery.
node -e 'require.resolve("qrcode.react")' >/dev/null 2>&1 || {
  info "Repairing missing qrcode.react dependency..."
  npm install --include=optional --no-audit --no-fund
  printf '%s\n' "$PACKAGE_HASH" > "$DEPS_STAMP"
}

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
