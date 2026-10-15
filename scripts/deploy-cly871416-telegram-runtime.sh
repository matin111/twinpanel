#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_HOST="CLY871416"
REPO="/opt/twinpanel-preview"
LIVE="/opt/twinpanel-product/backend"
SOURCE_REF="origin/fix/customer-panel-entry-crash-v2"
PYTHON="/opt/twinpanel/venv/bin/python3"
API_SERVICE="twinpanel-api.service"
BOT_SERVICE="twinpanel-bot.service"

if [[ "$(hostname)" != "$EXPECTED_HOST" ]]; then
  echo "ERROR: run this only on $EXPECTED_HOST"
  echo "CURRENT_HOST=$(hostname)"
  exit 1
fi

for path in "$REPO" "$LIVE" "$PYTHON"; do
  [[ -e "$path" ]] || { echo "ERROR: missing $path"; exit 1; }
done

cd "$REPO"
git fetch origin --prune

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/root/twinpanel-backups/telegram-runtime-$STAMP"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
mkdir -p "$BACKUP"

echo "============================================================"
echo " TELEGRAM RUNTIME DEPLOY"
echo " SOURCE=$SOURCE_REF"
echo " LIVE=$LIVE"
echo " BACKUP=$BACKUP"
echo "============================================================"

FILES=(
  "app/routers/telegram_manager.py"
  "app/telegram_runtime_bot.py"
  "app/telegram_learning_center.py"
)

for rel in "${FILES[@]}"; do
  repo_path="backend/$rel"
  src="$TMPDIR/$(basename "$rel")"
  target="$LIVE/$rel"

  git cat-file -e "$SOURCE_REF:$repo_path" || {
    echo "ERROR: missing $repo_path in $SOURCE_REF"
    exit 1
  }

  git show "$SOURCE_REF:$repo_path" > "$src"
  "$PYTHON" -m py_compile "$src"

  mkdir -p "$(dirname "$target")"

  if [[ -f "$target" ]]; then
    cp -a "$target" "$BACKUP/$(basename "$rel")"
  fi

done

RUNTIME_TMP="$TMPDIR/telegram_runtime_bot.py"

if grep -Fq 'این ربات در حال حاضر فعال نیست' "$RUNTIME_TMP"; then
  echo "ERROR: source runtime still contains obsolete inactive /start response"
  exit 1
fi

grep -Fq 'TWINPANEL_SUBSCRIPTION_BOT_V2' "$RUNTIME_TMP" || {
  echo "ERROR: current Telegram runtime marker not found"
  exit 1
}

grep -Fq 'await session(' "$RUNTIME_TMP" || {
  echo "ERROR: current /start auto-session logic not found"
  exit 1
}

echo "SOURCE_RUNTIME=OK"

install -m 0644 "$TMPDIR/telegram_manager.py" "$LIVE/app/routers/telegram_manager.py"
install -m 0644 "$TMPDIR/telegram_runtime_bot.py" "$LIVE/app/telegram_runtime_bot.py"
install -m 0644 "$TMPDIR/telegram_learning_center.py" "$LIVE/app/telegram_learning_center.py"

"$PYTHON" -m py_compile \
  "$LIVE/app/routers/telegram_manager.py" \
  "$LIVE/app/telegram_runtime_bot.py" \
  "$LIVE/app/telegram_learning_center.py"

echo "LIVE_COMPILE=OK"

if grep -Fq 'این ربات در حال حاضر فعال نیست' "$LIVE/app/telegram_runtime_bot.py"; then
  echo "ERROR: obsolete runtime survived installation"
  exit 1
fi

echo
 echo "===== RESTART API ====="
systemctl restart "$API_SERVICE"

API_READY=0
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8095/health >/tmp/twinpanel-health.json 2>/dev/null; then
    API_READY=1
    echo "API_READY_AFTER=${i}s"
    cat /tmp/twinpanel-health.json
    echo
    break
  fi

  if (( i % 10 == 0 )); then
    echo "waiting API... ${i}s"
  fi
  sleep 1
done

if [[ "$API_READY" != "1" ]]; then
  echo "ERROR: API did not become ready"
  systemctl status "$API_SERVICE" --no-pager -l || true
  journalctl -u "$API_SERVICE" --since "5 minutes ago" --no-pager -l | tail -160 || true
  exit 1
fi

echo
 echo "===== REPAIR/RESTART BOT SERVICE ====="
cd "$LIVE"
set -a
source /etc/twinpanel/backend.env
set +a

"$PYTHON" - <<'PY'
from app.routers import telegram_manager as t

print("PROJECT_DIR =", t.PROJECT_DIR)
print("PYTHON_BIN  =", t.PYTHON_BIN)
print("RUNTIME     =", t._runtime_file())
print("RUNTIME_OK  =", t._runtime_file().exists())
print("STATUS      =", t._status_payload())

t._ensure_internal_secret()
t._repair_existing_service_env()
PY

systemctl daemon-reload
systemctl restart "$BOT_SERVICE"

BOT_READY=0
for i in $(seq 1 25); do
  if systemctl is-active --quiet "$BOT_SERVICE"; then
    BOT_READY=1
    echo "BOT_ACTIVE_AFTER=${i}s"
    break
  fi
  sleep 1
done

if [[ "$BOT_READY" != "1" ]]; then
  echo "ERROR: bot service is not active"
  systemctl status "$BOT_SERVICE" --no-pager -l || true
  journalctl -u "$BOT_SERVICE" -n 120 --no-pager -l || true
  exit 1
fi

echo
 echo "===== FINAL BOT LOG ====="
journalctl -u "$BOT_SERVICE" -n 50 --no-pager -l || true

echo
 echo "============================================================"
echo " TELEGRAM_RUNTIME_DEPLOY_OK"
echo " BACKUP=$BACKUP"
echo " API=$(systemctl is-active "$API_SERVICE")"
echo " BOT=$(systemctl is-active "$BOT_SERVICE")"
echo "============================================================"
