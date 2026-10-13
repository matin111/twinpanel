#!/usr/bin/env bash
set -Eeuo pipefail

# Guarded TwinPanel preview deployment for CLY871416.
# Source:  /opt/twinpanel-preview
# Backend: /opt/twinpanel/current/backend -> twinpanel-api.service :8095
# Web:     /opt/twinpanel-preview        -> twinpanel-preview.service :3010

EXPECTED_HOST="CLY871416"
REPO_DIR="${REPO_DIR:-/opt/twinpanel-preview}"
BRANCH="${BRANCH:-fix/customer-panel-entry-crash-v2}"
API_DST="${API_DST:-/opt/twinpanel/current/backend}"
VENV_DIR="${VENV_DIR:-/opt/twinpanel/venv}"
API_SERVICE="${API_SERVICE:-twinpanel-api.service}"
WEB_SERVICE="${WEB_SERVICE:-twinpanel-preview.service}"
API_URL="${API_URL:-http://127.0.0.1:8095}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3010}"
BACKUP_ROOT="${BACKUP_ROOT:-/root/twinpanel-backups}"
RECEIPT_DIR="${TWINPANEL_PAYMENT_RECEIPT_DIR:-/var/lib/twinpanel/payment-receipts}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/deploy-$TS"
DEPLOY_OK=0
BACKEND_BACKED_UP=0
WEB_WAS_ACTIVE=0
API_WAS_ACTIVE=0
OLD_HEAD=""
OLD_BRANCH=""
STASH_REF=""

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  echo "ERROR: $*" >&2
  return 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

wait_http_200() {
  local url="$1"
  local tries="${2:-40}"
  local sleep_s="${3:-1}"
  local i code

  for ((i=1; i<=tries; i++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    sleep "$sleep_s"
  done

  return 1
}

install_frontend_dependencies() {
  cd "$REPO_DIR"

  # The repository intentionally does not always carry a package-lock.json.
  # Match CI behavior: use npm ci only when a valid lockfile is present,
  # otherwise install from package.json without creating a new lockfile.
  if [[ -f package-lock.json || -f npm-shrinkwrap.json ]]; then
    echo "FRONTEND_DEPS_MODE=npm-ci"
    npm ci --include=optional --no-audit --no-fund
  else
    echo "FRONTEND_DEPS_MODE=npm-install-no-lock"
    npm install --include=optional --no-audit --no-fund --package-lock=false
  fi
}

rollback() {
  local exit_code=$?
  trap - ERR INT TERM
  set +e

  if [[ "$DEPLOY_OK" == "1" ]]; then
    exit "$exit_code"
  fi

  echo
  echo "============================================================"
  echo " TWINPANEL DEPLOY FAILED - STARTING ROLLBACK"
  echo " BACKUP: $BACKUP_DIR"
  echo "============================================================"

  systemctl stop "$API_SERVICE" >/dev/null 2>&1 || true

  if [[ "$BACKEND_BACKED_UP" == "1" && -f "$BACKUP_DIR/backend.tar.gz" ]]; then
    tar -C "$API_DST" -xzf "$BACKUP_DIR/backend.tar.gz" || true
  fi

  if [[ -n "$OLD_HEAD" && -d "$REPO_DIR/.git" ]]; then
    cd "$REPO_DIR" || true
    git reset --hard "$OLD_HEAD" || true

    if [[ -n "$OLD_BRANCH" ]]; then
      git switch "$OLD_BRANCH" >/dev/null 2>&1 || true
      git reset --hard "$OLD_HEAD" || true
    fi

    systemctl stop "$WEB_SERVICE" >/dev/null 2>&1 || true
    install_frontend_dependencies >/dev/null 2>&1 || true
    npm run build >/dev/null 2>&1 || true
  fi

  if [[ "$API_WAS_ACTIVE" == "1" ]]; then
    systemctl start "$API_SERVICE" >/dev/null 2>&1 || true
  fi

  if [[ "$WEB_WAS_ACTIVE" == "1" ]]; then
    systemctl start "$WEB_SERVICE" >/dev/null 2>&1 || true
  fi

  echo
  echo "Rollback attempted. Inspect:"
  echo "  $BACKUP_DIR"
  echo "  journalctl -u $API_SERVICE -n 150 --no-pager"
  echo "  journalctl -u $WEB_SERVICE -n 150 --no-pager"
  exit "$exit_code"
}

trap rollback ERR INT TERM

log "PRE-FLIGHT"

for cmd in git rsync tar curl systemctl npm node python3; do
  require_cmd "$cmd"
done

ACTUAL_HOST="$(hostname)"
if [[ "$ACTUAL_HOST" != "$EXPECTED_HOST" && "${ALLOW_HOST_MISMATCH:-0}" != "1" ]]; then
  fail "this deploy is pinned to $EXPECTED_HOST, current host is $ACTUAL_HOST"
fi

[[ -d "$REPO_DIR/.git" ]] || fail "git repository not found: $REPO_DIR"
[[ -d "$API_DST" ]] || fail "backend destination not found: $API_DST"
[[ -x "$VENV_DIR/bin/python" ]] || fail "python venv not found: $VENV_DIR"
[[ -f "$REPO_DIR/package.json" ]] || fail "frontend package.json not found: $REPO_DIR/package.json"
systemctl cat "$API_SERVICE" >/dev/null
systemctl cat "$WEB_SERVICE" >/dev/null

mkdir -p "$BACKUP_DIR"

if systemctl is-active --quiet "$API_SERVICE"; then API_WAS_ACTIVE=1; fi
if systemctl is-active --quiet "$WEB_SERVICE"; then WEB_WAS_ACTIVE=1; fi

cd "$REPO_DIR"
OLD_HEAD="$(git rev-parse HEAD)"
OLD_BRANCH="$(git symbolic-ref --short -q HEAD || true)"
printf '%s\n' "$OLD_HEAD" > "$BACKUP_DIR/old-head.txt"
printf '%s\n' "$OLD_BRANCH" > "$BACKUP_DIR/old-branch.txt"
git status --short > "$BACKUP_DIR/git-status-before.txt" || true
git diff > "$BACKUP_DIR/worktree-before.patch" || true
git diff --cached > "$BACKUP_DIR/index-before.patch" || true

if [[ -n "$(git status --porcelain)" ]]; then
  log "PRESERVING LOCAL WORKTREE IN GIT STASH"
  git stash push -u -m "predeploy-$TS"
  STASH_REF="$(git rev-parse -q --verify refs/stash || true)"
  printf '%s\n' "$STASH_REF" > "$BACKUP_DIR/stash-ref.txt"
fi

log "BACKING UP CURRENT BACKEND"
tar -C "$API_DST" -czf "$BACKUP_DIR/backend.tar.gz" .
BACKEND_BACKED_UP=1

log "UPDATING SOURCE FROM GITHUB"
git fetch origin --prune
git rev-parse --verify "origin/$BRANCH" >/dev/null
git switch -C "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
NEW_HEAD="$(git rev-parse HEAD)"
printf '%s\n' "$NEW_HEAD" > "$BACKUP_DIR/new-head.txt"

echo "OLD_HEAD=$OLD_HEAD"
echo "NEW_HEAD=$NEW_HEAD"
echo "BRANCH=$BRANCH"
echo "NODE=$(node --version)"
echo "NPM=$(npm --version)"

log "VERIFYING REQUIRED SOURCE FILES"
required_files=(
  "backend/app/download_asset_models.py"
  "backend/app/routers/download_assets.py"
  "backend/app/routers/public_connection_v3.py"
  "backend/app/routers/payment_receipts_local.py"
  "backend/app/routers/payment_crypto_discount.py"
  "backend/app/routers/payment_native_gateways.py"
  "backend/app/routers/payment_market_rates.py"
  "backend/app/routers/wallet_payment_v2.py"
  "backend/app/routers/wallet_admin_v2.py"
  "backend/app/routers/wallet_sms_reader.py"
  "backend/app/services/wallet_payment_automation.py"
  "components/admin-wallet-v2.tsx"
  "components/customer-wallet-v2.tsx"
  "components/customer-payments-runtime.tsx"
  "scripts/smoke-cly871416-runtime.sh"
)

for f in "${required_files[@]}"; do
  [[ -f "$REPO_DIR/$f" ]] || fail "required source file missing: $f"
done

log "SYNCING BACKEND FROM GITHUB SOURCE"
systemctl stop "$API_SERVICE"

rsync -a \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='instance/' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  "$REPO_DIR/backend/" "$API_DST/"

log "INSTALLING / VERIFYING BACKEND DEPENDENCIES"
"$VENV_DIR/bin/pip" install -q -r "$API_DST/requirements.txt"

log "COMPILING BACKEND"
"$VENV_DIR/bin/python" -m compileall -q "$API_DST/app"

log "PREPARING LOCAL RECEIPT STORAGE"
API_USER="$(systemctl show "$API_SERVICE" -p User --value)"
if [[ -z "$API_USER" ]]; then API_USER="root"; fi
API_GROUP="$(id -gn "$API_USER")"
install -d -m 0750 -o "$API_USER" -g "$API_GROUP" "$RECEIPT_DIR"

log "STARTING API"
systemctl start "$API_SERVICE"
if ! wait_http_200 "$API_URL/health" 50 1; then
  systemctl status "$API_SERVICE" --no-pager -l || true
  journalctl -u "$API_SERVICE" -n 150 --no-pager || true
  fail "API health check failed"
fi

log "VERIFYING NEW API ROUTES"
curl -fsS "$API_URL/openapi.json" -o "$BACKUP_DIR/openapi.json"
"$VENV_DIR/bin/python" - "$BACKUP_DIR/openapi.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    doc = json.load(fh)

paths = doc.get("paths", {})
required = {
    "/v1/admin/wallet/wallets",
    "/v1/admin/wallet/topups",
    "/v1/admin/wallet/topups/{topup_id}/approve",
    "/v1/payments/admin/crypto-discount",
    "/v1/payments/intents/{intent_id}/receipt-upload",
    "/v1/wallet/methods",
    "/v1/wallet/topups",
    "/v1/wallet/topups/{topup_id}/submit",
    "/v1/admin/telegram-bot",
}

missing = sorted(required - set(paths))
if missing:
    print("MISSING ROUTES:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

print("ROUTES_OK")
for item in sorted(required):
    print("OK", item)
PY

log "INSTALLING FRONTEND DEPENDENCIES"
install_frontend_dependencies

log "BUILDING FRONTEND"
cd "$REPO_DIR"
systemctl stop "$WEB_SERVICE"
npm run build
systemctl start "$WEB_SERVICE"

if ! wait_http_200 "$WEB_URL/login" 50 1; then
  systemctl status "$WEB_SERVICE" --no-pager -l || true
  journalctl -u "$WEB_SERVICE" -n 150 --no-pager || true
  fail "frontend /login health check failed"
fi

log "VERIFYING NEXT.JS API PROXY"
LOGIN_CODE="$(curl -sS \
  -o "$BACKUP_DIR/login-proxy-response.txt" \
  -w '%{http_code}' \
  -X POST "$WEB_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  --data '{"email":"invalid-deploy-smoke@example.com","password":"invalid-deploy-smoke-password"}' \
  || true)"

echo "LOGIN_PROXY_STATUS=$LOGIN_CODE"
case "$LOGIN_CODE" in
  000|502|503|504)
    cat "$BACKUP_DIR/login-proxy-response.txt" 2>/dev/null || true
    fail "frontend API proxy is unhealthy: HTTP $LOGIN_CODE"
    ;;
esac

log "FINAL SERVICE STATUS"
systemctl is-active "$API_SERVICE"
systemctl is-active "$WEB_SERVICE"
curl -fsS "$API_URL/health"
echo
curl -fsS "$WEB_URL/login" >/dev/null

DEPLOY_OK=1
trap - ERR INT TERM

echo
echo "============================================================"
echo " TWINPANEL DEPLOY SUCCESS"
echo " HOST:       $ACTUAL_HOST"
echo " BRANCH:     $BRANCH"
echo " HEAD:       $NEW_HEAD"
echo " API:        $API_URL/health"
echo " FRONTEND:   $WEB_URL/login"
echo " BACKUP:     $BACKUP_DIR"
if [[ -n "$STASH_REF" ]]; then
  echo " PREDEPLOY STASH: $STASH_REF"
fi
echo "============================================================"
