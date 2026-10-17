#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "TwinPanel CLI must run as root / این منو باید با root اجرا شود" >&2; exit 1; }

ROOT="/opt/twinpanel/current"
BACKEND="$ROOT/backend"
PY="/opt/twinpanel/venv/bin/python3"
BACKEND_ENV="/etc/twinpanel/backend.env"
INSTALL_ENV="/etc/twinpanel/install.env"
LANG_FILE="/etc/twinpanel/cli-language"
INITIAL_ADMIN_FILE="/root/twinpanel-initial-admin.txt"

C_PURPLE='\033[1;35m'
C_BLUE='\033[1;34m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[1;31m'
C_RESET='\033[0m'

LANG_MODE="fa"
if [[ -s "$LANG_FILE" ]]; then
  LANG_MODE="$(tr -d '[:space:]' < "$LANG_FILE" || true)"
fi
[[ "$LANG_MODE" == "fa" || "$LANG_MODE" == "en" ]] || LANG_MODE="fa"

trp(){
  local fa="$1" en="$2"
  if [[ "$LANG_MODE" == "fa" ]]; then printf '%s' "$fa"; else printf '%s' "$en"; fi
}

line(){ printf '%*s\n' 68 '' | tr ' ' '='; }
header(){
  clear 2>/dev/null || true
  printf "${C_PURPLE}"
  line
  printf "  TwinPanel 2027 — SSH Management\n"
  line
  printf "${C_RESET}\n"
}
pause(){ printf '\n'; read -r -p "$(trp 'برای ادامه Enter بزنید...' 'Press Enter to continue...')" _ || true; }

require_runtime(){
  [[ -d "$BACKEND" ]] || { echo "TwinPanel backend not found: $BACKEND" >&2; return 1; }
  [[ -x "$PY" ]] || { echo "TwinPanel Python not found: $PY" >&2; return 1; }
  [[ -f "$BACKEND_ENV" ]] || { echo "TwinPanel environment not found: $BACKEND_ENV" >&2; return 1; }
}

run_backend(){
  require_runtime
  (
    set -a
    # shellcheck disable=SC1090
    source "$BACKEND_ENV"
    set +a
    cd "$BACKEND"
    "$PY" "$@"
  )
}

runtime_ports(){
  WEB_PORT=3000
  API_PORT=8095
  if [[ -f "$INSTALL_ENV" ]]; then
    set +u
    # shellcheck disable=SC1090
    source "$INSTALL_ENV"
    set -u
    WEB_PORT="${TWINPANEL_WEB_PORT:-$WEB_PORT}"
    API_PORT="${TWINPANEL_API_PORT:-$API_PORT}"
  fi
}

status_menu(){
  header
  runtime_ports
  printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'وضعیت پنل' 'Panel status')"
  printf '%-24s %s\n' "Version:" "$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
  printf '%-24s %s\n' "Git commit:" "$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo release)"
  printf '%-24s %s\n' "API port:" "$API_PORT"
  printf '%-24s %s\n' "Web port:" "$WEB_PORT"
  echo
  for unit in twinpanel-api.service twinpanel-web.service twinpanel-updater.service twinpanel-transport-manager.service twinpanel-bot.service twinpanel-reseller-bots.service nginx postgresql redis-server; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    [[ "$state" == "active" ]] && color="$C_GREEN" || color="$C_YELLOW"
    printf '%-38s %b%s%b\n' "$unit" "$color" "${state:-not-found}" "$C_RESET"
  done
  echo
  printf 'API health: '
  curl -fsS --max-time 3 "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo "unreachable"
  echo
  pause
}

services_menu(){
  while true; do
    header
    printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'مدیریت سرویس‌ها' 'Service management')"
    echo "1) $(trp 'ریستارت API' 'Restart API')"
    echo "2) $(trp 'ریستارت Web' 'Restart Web')"
    echo "3) $(trp 'ریستارت Nginx' 'Restart Nginx')"
    echo "4) $(trp 'ریستارت API + Web + Nginx' 'Restart API + Web + Nginx')"
    echo "5) $(trp 'وضعیت سرویس‌ها' 'Service status')"
    echo "0) $(trp 'بازگشت' 'Back')"
    read -r -p "> " choice
    case "$choice" in
      1) systemctl restart twinpanel-api.service; pause ;;
      2) systemctl restart twinpanel-web.service; pause ;;
      3) nginx -t && systemctl restart nginx; pause ;;
      4) systemctl restart twinpanel-api.service twinpanel-web.service; nginx -t && systemctl restart nginx; pause ;;
      5) systemctl --no-pager --full status twinpanel-api.service twinpanel-web.service nginx || true; pause ;;
      0) return ;;
    esac
  done
}

admin_menu(){
  while true; do
    header
    printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'مدیریت ادمین' 'Administrator management')"
    echo "1) $(trp 'نمایش ادمین فعلی' 'Show current administrator')"
    echo "2) $(trp 'نمایش اطلاعات ورود اولیه' 'Show initial login credentials')"
    echo "3) $(trp 'ریست رمز ادمین' 'Reset administrator password')"
    echo "4) $(trp 'تغییر ایمیل ادمین' 'Change administrator email')"
    echo "5) $(trp 'تغییر نام ادمین' 'Change administrator name')"
    echo "6) $(trp 'حذف فایل اطلاعات ورود اولیه' 'Delete initial credentials file')"
    echo "0) $(trp 'بازگشت' 'Back')"
    read -r -p "> " choice
    case "$choice" in
      1) run_backend scripts/twinpanel_admin_cli.py show || true; pause ;;
      2)
        if [[ -s "$INITIAL_ADMIN_FILE" ]]; then cat "$INITIAL_ADMIN_FILE"; else echo "$(trp 'فایل ورود اولیه وجود ندارد.' 'Initial credentials file does not exist.')"; fi
        pause
        ;;
      3)
        echo "$(trp 'اگر خالی بگذاری یک رمز قوی تصادفی ساخته می‌شود.' 'Leave blank to generate a strong random password.')"
        read -r -s -p "$(trp 'رمز جدید: ' 'New password: ')" pass || true
        echo
        if [[ -n "$pass" ]]; then run_backend scripts/twinpanel_admin_cli.py reset-password --password "$pass" || true; else run_backend scripts/twinpanel_admin_cli.py reset-password || true; fi
        unset pass
        pause
        ;;
      4)
        read -r -p "$(trp 'ایمیل جدید: ' 'New email: ')" email
        run_backend scripts/twinpanel_admin_cli.py change-email "$email" || true
        pause
        ;;
      5)
        read -r -p "$(trp 'نام جدید: ' 'New name: ')" name
        run_backend scripts/twinpanel_admin_cli.py change-name "$name" || true
        pause
        ;;
      6)
        if [[ -f "$INITIAL_ADMIN_FILE" ]]; then
          read -r -p "$(trp 'برای حذف YES وارد کنید: ' 'Type YES to delete: ')" confirm
          [[ "$confirm" == "YES" ]] && rm -f "$INITIAL_ADMIN_FILE" && echo "$(trp 'حذف شد.' 'Deleted.')"
        fi
        pause
        ;;
      0) return ;;
    esac
  done
}

protocol_menu(){
  header
  printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'مدیریت پروتکل‌ها' 'Protocol management')"
  echo "$(trp 'ابتدا سرور خروجی، سپس پروتکل و عملیات را انتخاب کن.' 'Select the Exit node, protocol and action.')"
  echo "$(trp 'حذف پروتکل قبل از تغییر فایل‌ها روی همان نود بکاپ می‌گیرد.' 'Protocol removal creates a backup on that node before changing files.')"
  echo
  run_backend scripts/twinpanel_protocol_cli.py || true
  pause
}

update_menu(){
  while true; do
    header
    printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'بروزرسانی پنل' 'Panel update')"
    echo "1) $(trp 'بررسی بروزرسانی' 'Check for update')"
    echo "2) $(trp 'شروع بروزرسانی' 'Start update')"
    echo "3) $(trp 'وضعیت Updater' 'Updater status')"
    echo "0) $(trp 'بازگشت' 'Back')"
    read -r -p "> " choice
    case "$choice" in
      1)
        run_backend -c 'import json; from app.system_release import release_status; print(json.dumps(release_status(refresh_license_state=True),ensure_ascii=False,indent=2,default=str))' || true
        pause
        ;;
      2)
        read -r -p "$(trp 'برای شروع UPDATE وارد کنید: ' 'Type UPDATE to start: ')" confirm
        if [[ "$confirm" == "UPDATE" ]]; then
          run_backend -c 'import json; from app.system_release import request_update; print(json.dumps(request_update(),ensure_ascii=False,indent=2,default=str))' || true
        fi
        pause
        ;;
      3) systemctl --no-pager --full status twinpanel-updater.service || true; pause ;;
      0) return ;;
    esac
  done
}

backup_menu(){
  while true; do
    header
    printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'بکاپ' 'Backup')"
    echo "1) $(trp 'ساخت بکاپ دستی' 'Create manual backup')"
    echo "2) $(trp 'لیست بکاپ‌ها' 'List backups')"
    echo "0) $(trp 'بازگشت' 'Back')"
    read -r -p "> " choice
    case "$choice" in
      1) run_backend -c "from app.backup_service import create_backup; print(create_backup(kind='manual',send_telegram=False))" || true; pause ;;
      2) ls -lah /var/lib/twinpanel-backups 2>/dev/null || true; pause ;;
      0) return ;;
    esac
  done
}

logs_menu(){
  while true; do
    header
    printf "${C_BLUE}%s${C_RESET}\n\n" "$(trp 'لاگ و عیب‌یابی' 'Logs and diagnostics')"
    echo "1) API"
    echo "2) Web"
    echo "3) Transport Manager"
    echo "4) Telegram Bot"
    echo "5) Nginx"
    echo "0) $(trp 'بازگشت' 'Back')"
    read -r -p "> " choice
    case "$choice" in
      1) journalctl -u twinpanel-api.service -n 120 --no-pager; pause ;;
      2) journalctl -u twinpanel-web.service -n 120 --no-pager; pause ;;
      3) journalctl -u twinpanel-transport-manager.service -n 120 --no-pager; pause ;;
      4) journalctl -u twinpanel-bot.service -n 120 --no-pager; pause ;;
      5) tail -n 120 /var/log/nginx/error.log 2>/dev/null || true; pause ;;
      0) return ;;
    esac
  done
}

version_menu(){
  header
  version="$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
  printf 'TwinPanel version: %s\n' "$version"
  printf 'GitHub: https://github.com/matin111/twinpanel\n'
  printf 'Public bootstrap: https://github.com/matin111/tp27-core\n'
  if git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
    printf 'Commit: %s\n' "$(git -C "$ROOT" rev-parse HEAD)"
  fi
  pause
}

language_menu(){
  header
  echo "1) فارسی"
  echo "2) English"
  read -r -p "> " choice
  case "$choice" in
    1) LANG_MODE="fa" ;;
    2) LANG_MODE="en" ;;
    *) return ;;
  esac
  install -d -m 700 /etc/twinpanel
  printf '%s\n' "$LANG_MODE" > "$LANG_FILE"
  chmod 600 "$LANG_FILE"
}

main_menu(){
  while true; do
    header
    version="$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
    printf "${C_GREEN}TwinPanel v%s${C_RESET}\n\n" "$version"
    echo "1) $(trp 'وضعیت پنل' 'Panel status')"
    echo "2) $(trp 'مدیریت سرویس‌ها' 'Service management')"
    echo "3) $(trp 'مدیریت ادمین' 'Administrator management')"
    echo "4) $(trp 'مدیریت پروتکل‌ها' 'Protocol management')"
    echo "5) $(trp 'بروزرسانی پنل' 'Panel update')"
    echo "6) $(trp 'بکاپ' 'Backup')"
    echo "7) $(trp 'لاگ و عیب‌یابی' 'Logs and diagnostics')"
    echo "8) $(trp 'نسخه و GitHub' 'Version and GitHub')"
    echo "9) $(trp 'زبان / Language' 'Language / زبان')"
    echo "0) $(trp 'خروج' 'Exit')"
    echo
    read -r -p "> " choice
    case "$choice" in
      1) status_menu ;;
      2) services_menu ;;
      3) admin_menu ;;
      4) protocol_menu ;;
      5) update_menu ;;
      6) backup_menu ;;
      7) logs_menu ;;
      8) version_menu ;;
      9) language_menu ;;
      0) clear 2>/dev/null || true; exit 0 ;;
    esac
  done
}

main_menu
