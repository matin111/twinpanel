#!/usr/bin/env bash
set -Eeuo pipefail

# This wrapper intentionally reuses the canonical deploy script, then installs
# the backend-env systemd drop-in and verifies the main bot is stable rather
# than merely momentarily active inside Restart=always.

EXPECTED_HOST="CLY871416"
REPO="/opt/twinpanel-preview"
BOT_SERVICE="twinpanel-bot.service"
DROPIN_SOURCE="$REPO/deploy/systemd/twinpanel-bot-backend-env.conf"
DROPIN_DIR="/etc/systemd/system/${BOT_SERVICE}.d"
DROPIN_TARGET="$DROPIN_DIR/20-backend-env.conf"

if [[ "$(hostname)" != "$EXPECTED_HOST" ]]; then
  echo "ERROR: run this only on $EXPECTED_HOST"
  echo "CURRENT_HOST=$(hostname)"
  exit 1
fi

cd "$REPO"

[[ -x scripts/deploy-cly871416-telegram-runtime.sh || -f scripts/deploy-cly871416-telegram-runtime.sh ]] || {
  echo "ERROR: canonical Telegram deploy script is missing"
  exit 1
}

[[ -f "$DROPIN_SOURCE" ]] || {
  echo "ERROR: bot backend-env drop-in is missing: $DROPIN_SOURCE"
  exit 1
}

install -d -m 0755 "$DROPIN_DIR"
install -m 0644 "$DROPIN_SOURCE" "$DROPIN_TARGET"
systemctl daemon-reload

echo "BOT_BACKEND_ENV_DROPIN=OK"

# Run the canonical ownership/collision repair after the drop-in is present so
# its main-bot restart starts with backend settings available from the first PID.
bash scripts/deploy-cly871416-telegram-runtime.sh

echo
echo "===== MAIN BOT STABILITY CHECK ====="

if ! systemctl is-active --quiet "$BOT_SERVICE"; then
  echo "ERROR: main bot is not active after deploy"
  systemctl status "$BOT_SERVICE" --no-pager -l || true
  journalctl -u "$BOT_SERVICE" -n 120 --no-pager -l || true
  exit 1
fi

PID_BEFORE="$(systemctl show -p MainPID --value "$BOT_SERVICE")"
RESTARTS_BEFORE="$(systemctl show -p NRestarts --value "$BOT_SERVICE")"

echo "BOT_PID_BEFORE=$PID_BEFORE"
echo "BOT_RESTARTS_BEFORE=$RESTARTS_BEFORE"

sleep 12

PID_AFTER="$(systemctl show -p MainPID --value "$BOT_SERVICE")"
RESTARTS_AFTER="$(systemctl show -p NRestarts --value "$BOT_SERVICE")"
STATE_AFTER="$(systemctl is-active "$BOT_SERVICE" || true)"

echo "BOT_PID_AFTER=$PID_AFTER"
echo "BOT_RESTARTS_AFTER=$RESTARTS_AFTER"
echo "BOT_STATE_AFTER=$STATE_AFTER"

if [[ "$STATE_AFTER" != "active" || "$PID_AFTER" == "0" || "$PID_BEFORE" != "$PID_AFTER" || "$RESTARTS_BEFORE" != "$RESTARTS_AFTER" ]]; then
  echo "ERROR: main bot is restart-looping or failed the stability window"
  systemctl status "$BOT_SERVICE" --no-pager -l || true
  journalctl -u "$BOT_SERVICE" -n 160 --no-pager -l || true
  exit 1
fi

if journalctl -u "$BOT_SERVICE" --since "2 minutes ago" --no-pager -l \
  | grep -Eqi 'ValidationError|Field required|Traceback|TelegramConflictError|terminated by other getUpdates'; then
  echo "ERROR: main bot log contains a startup/runtime failure"
  journalctl -u "$BOT_SERVICE" --since "2 minutes ago" --no-pager -l | tail -160 || true
  exit 1
fi

echo "MAIN_BOT_STABLE=YES"
echo "TELEGRAM_RUNTIME_V2_DEPLOY_OK"
