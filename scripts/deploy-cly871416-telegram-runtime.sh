#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_HOST="CLY871416"
REPO="/opt/twinpanel-preview"
LIVE="/opt/twinpanel-product/backend"
SOURCE_REF="origin/fix/customer-panel-entry-crash-v2"
PYTHON="/opt/twinpanel/venv/bin/python3"
API_SERVICE="twinpanel-api.service"
BOT_SERVICE="twinpanel-bot.service"
RESELLER_SERVICE="twinpanel-reseller-bots.service"
DEPLOY_STARTED="$(date --iso-8601=seconds)"

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
  "app/routers/reseller_bot.py"
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

grep -Fq 'TWINPANEL_TELEGRAM_TOKEN_OWNERSHIP_GUARD_V1' "$TMPDIR/reseller_bot.py" || {
  echo "ERROR: reseller token ownership guard not found"
  exit 1
}

echo "SOURCE_RUNTIME=OK"
echo "TOKEN_OWNERSHIP_GUARD=OK"

install -m 0644 "$TMPDIR/telegram_manager.py" "$LIVE/app/routers/telegram_manager.py"
install -m 0644 "$TMPDIR/reseller_bot.py" "$LIVE/app/routers/reseller_bot.py"
install -m 0644 "$TMPDIR/telegram_runtime_bot.py" "$LIVE/app/telegram_runtime_bot.py"
install -m 0644 "$TMPDIR/telegram_learning_center.py" "$LIVE/app/telegram_learning_center.py"

"$PYTHON" -m py_compile \
  "$LIVE/app/routers/telegram_manager.py" \
  "$LIVE/app/routers/reseller_bot.py" \
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
echo "===== TELEGRAM TOKEN OWNERSHIP AUDIT ====="
cd "$LIVE"
set -a
source /etc/twinpanel/backend.env
set +a

"$PYTHON" - <<'PY'
from datetime import datetime
import hmac

import httpx

from app.database import SessionLocal
from app.models_reseller import ResellerBotSettings
from app.reseller_bot_crypto import decrypt_bot_token
from app.routers import telegram_manager as t

main_token = t.load_bot_token()

with httpx.Client(timeout=10.0) as client:
    response = client.get(
        f"https://api.telegram.org/bot{main_token}/getMe"
    )
    data = response.json()

if response.status_code != 200 or not data.get("ok"):
    raise SystemExit("MAIN_BOT_GETME_FAILED")

bot = data.get("result") or {}
print("MAIN_BOT_ID       =", bot.get("id"))
print("MAIN_BOT_USERNAME = @" + str(bot.get("username") or "-"))
print("PROJECT_DIR       =", t.PROJECT_DIR)
print("PYTHON_BIN        =", t.PYTHON_BIN)
print("RUNTIME           =", t._runtime_file())
print("RUNTIME_OK        =", t._runtime_file().exists())

db = SessionLocal()
collisions = []

try:
    rows = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.bot_token_encrypted.isnot(None)
        )
        .all()
    )

    for row in rows:
        try:
            reseller_token = decrypt_bot_token(
                row.bot_token_encrypted
            )
        except Exception:
            continue

        if not hmac.compare_digest(main_token, reseller_token):
            continue

        collisions.append(int(row.reseller_id))
        print(
            "TOKEN_COLLISION reseller_id=%s username=@%s active=%s"
            % (
                row.reseller_id,
                row.bot_username or "-",
                bool(row.is_active),
            )
        )
        row.is_active = False
        row.updated_at = datetime.utcnow()

    if collisions:
        db.commit()
    else:
        db.rollback()
finally:
    db.close()

print("COLLISION_COUNT   =", len(collisions))
print("DEACTIVATED_RESELLERS =", ",".join(map(str, collisions)) or "none")

t._ensure_internal_secret()
t._repair_existing_service_env()
PY

echo
echo "===== RESTART RESELLER SUPERVISOR ====="
if systemctl cat "$RESELLER_SERVICE" >/dev/null 2>&1; then
  systemctl restart "$RESELLER_SERVICE"
  sleep 3
  if ! systemctl is-active --quiet "$RESELLER_SERVICE"; then
    echo "ERROR: reseller bot supervisor is not active"
    systemctl status "$RESELLER_SERVICE" --no-pager -l || true
    journalctl -u "$RESELLER_SERVICE" -n 100 --no-pager -l || true
    exit 1
  fi
  echo "RESELLER_SUPERVISOR=active"
else
  echo "RESELLER_SUPERVISOR=not-installed"
fi

echo
echo "===== RESTART MAIN BOT SERVICE ====="
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

# Give Telegram long polling enough time to expose a second getUpdates consumer.
sleep 7

echo
echo "===== MAIN BOT RECENT LOG ====="
journalctl -u "$BOT_SERVICE" --since "$DEPLOY_STARTED" --no-pager -l | tail -100 || true

echo
echo "===== RESELLER BOT RECENT LOG ====="
if systemctl cat "$RESELLER_SERVICE" >/dev/null 2>&1; then
  journalctl -u "$RESELLER_SERVICE" --since "$DEPLOY_STARTED" --no-pager -l | tail -100 || true
fi

if journalctl -u "$BOT_SERVICE" --since "$DEPLOY_STARTED" --no-pager -l \
  | grep -Eqi 'Conflict|TelegramConflictError|terminated by other getUpdates'; then
  echo "ERROR: MAIN BOT STILL HAS TELEGRAM POLLING CONFLICT"
  echo "Another process is consuming the same BotFather token."
  exit 1
fi

echo
echo "============================================================"
echo " TELEGRAM_RUNTIME_DEPLOY_OK"
echo " TELEGRAM_TOKEN_ISOLATION_OK"
echo " BACKUP=$BACKUP"
echo " API=$(systemctl is-active "$API_SERVICE")"
echo " BOT=$(systemctl is-active "$BOT_SERVICE")"
if systemctl cat "$RESELLER_SERVICE" >/dev/null 2>&1; then
  echo " RESELLER_BOTS=$(systemctl is-active "$RESELLER_SERVICE")"
fi
echo "============================================================"
