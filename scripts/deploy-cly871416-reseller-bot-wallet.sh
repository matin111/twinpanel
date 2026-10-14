#!/usr/bin/env bash
set -Eeuo pipefail

# Race-safe production deploy for the reseller bot wallet runtime on CLY871416.
# Scope: TwinPanel API + reseller bot supervisor only.
# Explicitly does NOT restart/touch tunnel manager, mother relay, node agents, or preview web.

EXPECTED_HOST="${EXPECTED_HOST:-CLY871416}"
SOURCE="${SOURCE:-/opt/twinpanel-preview}"
RUNTIME="${RUNTIME:-/opt/twinpanel-product/backend}"
VENV="${VENV:-/opt/twinpanel/venv}"
API_SERVICE="${API_SERVICE:-twinpanel-api.service}"
BOT_SERVICE="${BOT_SERVICE:-twinpanel-reseller-bots.service}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8095/health}"
HEALTH_TRIES="${HEALTH_TRIES:-60}"
HEALTH_SLEEP="${HEALTH_SLEEP:-1}"

FILES=(
  "app/main.py"
  "app/reseller_bot_runtime_owned.py"
  "app/reseller_bot_payment_runtime.py"
  "app/reseller_bot_wallet_menu_runtime.py"
  "app/routers/reseller_bot_orders_owned_v3.py"
  "app/routers/reseller_bot_wallet_topups.py"
  "scripts/reseller_bot_payment_callbacks_smoke.py"
  "scripts/reseller_bot_wallet_smoke.py"
  "scripts/reseller_receipt_review_smoke.py"
)

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  echo "ERROR: $*" >&2
  return 1
}

wait_api_health() {
  local i code
  for ((i=1; i<=HEALTH_TRIES; i++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 "$API_HEALTH_URL" 2>/dev/null || true)"
    if [[ "$code" == "200" ]]; then
      echo "API_HEALTH_OK attempt=$i code=$code"
      return 0
    fi

    if systemctl is-failed --quiet "$API_SERVICE"; then
      echo "API_ENTERED_FAILED_STATE attempt=$i code=${code:-none}" >&2
      return 1
    fi

    sleep "$HEALTH_SLEEP"
  done

  echo "API_HEALTH_TIMEOUT tries=$HEALTH_TRIES" >&2
  return 1
}

runtime_import_preflight() {
  local api_pid
  api_pid="$(systemctl show -p MainPID --value "$API_SERVICE")"
  [[ -n "$api_pid" && "$api_pid" != "0" ]] || fail "API process is not running; cannot capture live environment"

  API_PID="$api_pid" RUNTIME="$RUNTIME" VENV="$VENV" \
  "$VENV/bin/python" - <<'PY'
import os
import subprocess
import sys

pid = int(os.environ["API_PID"])
runtime = os.environ["RUNTIME"]
venv = os.environ["VENV"]

env = os.environ.copy()
with open(f"/proc/{pid}/environ", "rb") as fh:
    for item in fh.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode()] = value.decode()

env["PYTHONPATH"] = runtime

checks = [
    [f"{venv}/bin/python", "-c", "import app.main; print('APP_MAIN_IMPORT_OK')"],
    [f"{venv}/bin/python", "scripts/reseller_bot_payment_callbacks_smoke.py"],
    [f"{venv}/bin/python", "scripts/reseller_bot_wallet_smoke.py"],
]

for cmd in checks:
    print("RUN:", " ".join(cmd[1:]))
    result = subprocess.run(cmd, cwd=runtime, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

print("BACKEND_PREFLIGHT_OK")
PY
}

MUTATED=0
RESTART_PHASE=0
BACKUP=""

rollback() {
  local rc="$?"
  trap - ERR

  if [[ "$MUTATED" != "1" || -z "$BACKUP" ]]; then
    echo "ROLLBACK_NOT_REQUIRED rc=$rc" >&2
    exit "$rc"
  fi

  log "ROLLBACK: STOP API BEFORE RESTORING FILES"
  systemctl stop "$API_SERVICE" || true

  for file in "${FILES[@]}"; do
    if [[ -f "$BACKUP/$file" ]]; then
      mkdir -p "$RUNTIME/$(dirname "$file")"
      cp -a "$BACKUP/$file" "$RUNTIME/$file"
      echo "RESTORED: $file"
    elif grep -Fxq "$file" "$BACKUP/new-files.txt" 2>/dev/null; then
      rm -f "$RUNTIME/$file"
      echo "REMOVED_NEW_FILE: $file"
    fi
  done

  log "ROLLBACK: START API AND WAIT FOR REAL HEALTH"
  systemctl reset-failed "$API_SERVICE" || true
  systemctl start "$API_SERVICE" || true

  if wait_api_health; then
    echo "ROLLBACK_API_HEALTH_OK"
  else
    echo "ROLLBACK_API_HEALTH_FAILED" >&2
    journalctl -u "$API_SERVICE" -n 150 --no-pager -l >&2 || true
  fi

  # Bot is only restarted after a healthy new API, so there is normally nothing
  # to undo. If deploy reached bot restart, restart it once against restored API.
  if [[ "$RESTART_PHASE" == "2" ]]; then
    systemctl restart "$BOT_SERVICE" || true
  fi

  echo "ROLLBACK_FINISHED backup=$BACKUP" >&2
  exit "$rc"
}

trap rollback ERR

for cmd in git curl systemctl install; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"
done

[[ "$(hostname)" == "$EXPECTED_HOST" || "${ALLOW_HOST_MISMATCH:-0}" == "1" ]] \
  || fail "this deploy is pinned to $EXPECTED_HOST"
[[ -d "$SOURCE/.git" ]] || fail "source repo missing: $SOURCE"
[[ -x "$VENV/bin/python" ]] || fail "venv python missing: $VENV/bin/python"
[[ -d "$RUNTIME/app" ]] || fail "runtime backend missing: $RUNTIME"

systemctl is-active --quiet "$API_SERVICE" || fail "$API_SERVICE must be active before deploy"
systemctl cat "$BOT_SERVICE" >/dev/null

cd "$SOURCE"

git diff --quiet || fail "source has unstaged tracked changes"
git diff --cached --quiet || fail "source has staged tracked changes"

log "VERIFY REQUIRED SOURCE FILES"
for file in "${FILES[@]}"; do
  [[ -f "$SOURCE/backend/$file" ]] || fail "source file missing: backend/$file"
done

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="/root/twinpanel-backups/reseller-bot-wallet-safe-$TS"
mkdir -p "$BACKUP"
: > "$BACKUP/new-files.txt"

log "BACKUP CURRENT RUNTIME"
for file in "${FILES[@]}"; do
  mkdir -p "$BACKUP/$(dirname "$file")"
  if [[ -f "$RUNTIME/$file" ]]; then
    cp -a "$RUNTIME/$file" "$BACKUP/$file"
    echo "BACKUP: $file"
  else
    echo "$file" >> "$BACKUP/new-files.txt"
    echo "NEW: $file"
  fi
done

printf '%s\n' "$(git rev-parse HEAD)" > "$BACKUP/source-head.txt"

log "SYNC WALLET RUNTIME FILES"
for file in "${FILES[@]}"; do
  install -D -m 0644 "$SOURCE/backend/$file" "$RUNTIME/$file"
  echo "SYNCED: $file"
done
MUTATED=1

log "COMPILE ALL CHANGED PYTHON"
"$VENV/bin/python" -m py_compile \
  "$RUNTIME/app/main.py" \
  "$RUNTIME/app/reseller_bot_runtime_owned.py" \
  "$RUNTIME/app/reseller_bot_payment_runtime.py" \
  "$RUNTIME/app/reseller_bot_wallet_menu_runtime.py" \
  "$RUNTIME/app/routers/reseller_bot_orders_owned_v3.py" \
  "$RUNTIME/app/routers/reseller_bot_wallet_topups.py" \
  "$RUNTIME/scripts/reseller_bot_payment_callbacks_smoke.py" \
  "$RUNTIME/scripts/reseller_bot_wallet_smoke.py" \
  "$RUNTIME/scripts/reseller_receipt_review_smoke.py"
echo "RUNTIME_COMPILE_OK"

log "PRE-FLIGHT IMPORT + WALLET SMOKES USING LIVE API ENV"
runtime_import_preflight

log "RESTART API"
RESTART_PHASE=1
systemctl restart "$API_SERVICE"

# Critical safety rule: do not rollback merely because the port is not ready
# after a fixed sleep. Wait for the application to finish importing/starting.
wait_api_health
systemctl is-active --quiet "$API_SERVICE" || fail "$API_SERVICE is not active after health success"

log "VERIFY WALLET ROUTES"
curl -fsS http://127.0.0.1:8095/openapi.json > /tmp/twinpanel-wallet-safe-openapi.json
for route in \
  '"/v1/reseller/bot-commerce/wallet-topups"' \
  '"/v1/reseller/bot-commerce/wallet-topups/{topup_id}/approve"' \
  '"/v1/reseller/bot-commerce/wallet-topups/{topup_id}/reject"' \
  '"/v1/reseller/bot-commerce/wallets"'
do
  grep -q "$route" /tmp/twinpanel-wallet-safe-openapi.json || fail "missing route: $route"
  echo "ROUTE_OK: $route"
done

log "RESTART RESELLER BOT"
RESTART_PHASE=2
systemctl restart "$BOT_SERVICE"
sleep 8
systemctl is-active --quiet "$BOT_SERVICE" || fail "$BOT_SERVICE did not become active"

echo "BOT_SERVICE_OK"

log "READ-ONLY TUNNEL SERVICE STATES"
echo "MANAGER=$(systemctl is-active twinpanel-transport-manager.service 2>/dev/null || true)"
echo "MOTHER=$(systemctl is-active twinpanel-mother-relay-tls.service 2>/dev/null || true)"

trap - ERR

echo
echo "============================================================"
echo " RESELLER BOT WALLET SAFE DEPLOY SUCCESS"
echo " HEAD=$(git -C "$SOURCE" rev-parse HEAD)"
echo " BACKUP=$BACKUP"
echo " API=$(systemctl is-active "$API_SERVICE")"
echo " BOT=$(systemctl is-active "$BOT_SERVICE")"
echo "============================================================"
