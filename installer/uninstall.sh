#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
PURGE=0
DROP_DB=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --drop-database) DROP_DB=1 ;;
    *) fail "Unknown option: $arg" ;;
  esac
done
((DROP_DB==0 || PURGE==1)) || fail "--drop-database فقط همراه --purge مجاز است"

say "TwinPanel uninstall"

UNITS=(
  twinpanel-web.service
  twinpanel-api.service
  twinpanel-transport-manager.service
  twinpanel-reseller-bots.service
  twinpanel-bot.service
  twinpanel-backup.timer
  twinpanel-backup.service
)
systemctl disable --now "${UNITS[@]}" 2>/dev/null || true
rm -f \
  /etc/systemd/system/twinpanel-web.service \
  /etc/systemd/system/twinpanel-api.service \
  /etc/systemd/system/twinpanel-transport-manager.service \
  /etc/systemd/system/twinpanel-reseller-bots.service \
  /etc/systemd/system/twinpanel-bot.service \
  /etc/systemd/system/twinpanel-backup.timer \
  /etc/systemd/system/twinpanel-backup.service
systemctl daemon-reload

rm -f /usr/local/bin/twinpanel
rm -f /etc/nginx/sites-enabled/twinpanel.conf /etc/nginx/sites-available/twinpanel.conf
if command -v nginx >/dev/null 2>&1 && nginx -t >/dev/null 2>&1; then systemctl reload nginx || true; fi

if ((PURGE==0)); then
  rm -f "$TP_CURRENT"
  echo "UNINSTALL_OK"
  warn "Releaseها، دیتابیس، بکاپ‌ها و Secretها عمداً نگه داشته شدند. برای حذف تنظیمات/Releaseها از --purge استفاده کنید."
  exit 0
fi

read -r -p "برای حذف Releaseها و تنظیمات عبارت PURGE TWINPANEL را وارد کنید: " CONFIRM
[[ "$CONFIRM" == "PURGE TWINPANEL" ]] || fail "Purge لغو شد"

rm -rf --one-file-system "$TP_ROOT"
rm -rf --one-file-system "$TP_ETC"
rm -f /etc/twinpanel-reseller-bot.key /etc/twinpanel-telegram-api.env

if ((DROP_DB)); then
  read -r -p "برای حذف کامل دیتابیس عبارت DROP TWINPANEL DATABASE را وارد کنید: " DB_CONFIRM
  [[ "$DB_CONFIRM" == "DROP TWINPANEL DATABASE" ]] || fail "حذف دیتابیس لغو شد"
  if command -v runuser >/dev/null 2>&1 && command -v psql >/dev/null 2>&1; then
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='twinpanel' AND pid <> pg_backend_pid();" >/dev/null || true
    runuser -u postgres -- dropdb --if-exists twinpanel
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "DROP ROLE IF EXISTS twinpanel;" || true
  else
    warn "PostgreSQL tools پیدا نشد؛ دیتابیس حذف نشد"
  fi
else
  warn "دیتابیس عمداً نگه داشته شد."
fi

warn "مسیر /var/lib/twinpanel و /var/lib/twinpanel-backups برای جلوگیری از حذف ناخواسته Backup/Data نگه داشته شدند."
echo "PURGE_OK"
