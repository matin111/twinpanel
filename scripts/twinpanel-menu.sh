#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "TwinPanel CLI must run as root." >&2; exit 1; }

ROOT="/opt/twinpanel/current"
BACKEND="$ROOT/backend"
PY="/opt/twinpanel/venv/bin/python3"
BACKEND_ENV="/etc/twinpanel/backend.env"
INSTALL_ENV="/etc/twinpanel/install.env"
INITIAL_ADMIN_FILE="/root/twinpanel-initial-admin.txt"
BACKUP_ROOT="/var/lib/twinpanel-backups"
UPDATE_STATE_FILE="/var/lib/twinpanel-license/update-state.json"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_PURPLE='\033[1;35m'
  C_CYAN='\033[1;36m'
  C_BLUE='\033[1;34m'
  C_GREEN='\033[1;32m'
  C_YELLOW='\033[1;33m'
  C_RED='\033[1;31m'
  C_WHITE='\033[1;37m'
  C_DIM='\033[2m'
  C_RESET='\033[0m'
else
  C_PURPLE=''
  C_CYAN=''
  C_BLUE=''
  C_GREEN=''
  C_YELLOW=''
  C_RED=''
  C_WHITE=''
  C_DIM=''
  C_RESET=''
fi

CHOICE=""

version_value(){
  tr -d '\r\n' < "$ROOT/VERSION" 2>/dev/null || printf 'unknown'
}

unit_exists(){
  systemctl cat "$1" >/dev/null 2>&1
}

unit_state(){
  local unit="$1"
  if ! unit_exists "$unit"; then
    printf 'not-installed'
    return 0
  fi
  systemctl is-active "$unit" 2>/dev/null || true
}

state_badge(){
  local state="$1"
  case "$state" in
    active) printf '%b● ONLINE%b' "$C_GREEN" "$C_RESET" ;;
    failed) printf '%b● FAILED%b' "$C_RED" "$C_RESET" ;;
    inactive) printf '%b● OFFLINE%b' "$C_YELLOW" "$C_RESET" ;;
    not-installed) printf '%b○ N/A%b' "$C_DIM" "$C_RESET" ;;
    *) printf '%b● %s%b' "$C_YELLOW" "${state:-unknown}" "$C_RESET" ;;
  esac
}

brand(){
  printf '%b' "$C_PURPLE"
  cat <<'BANNER'
  ████████╗██╗    ██╗██╗███╗   ██╗██████╗  █████╗ ███╗   ██╗███████╗██╗
  ╚══██╔══╝██║    ██║██║████╗  ██║██╔══██╗██╔══██╗████╗  ██║██╔════╝██║
     ██║   ██║ █╗ ██║██║██╔██╗ ██║██████╔╝███████║██╔██╗ ██║█████╗  ██║
     ██║   ██║███╗██║██║██║╚██╗██║██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝  ██║
     ██║   ╚███╔███╔╝██║██║ ╚████║██║     ██║  ██║██║ ╚████║███████╗███████╗
     ╚═╝    ╚══╝╚══╝ ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝
BANNER
  printf '%b' "$C_RESET"
}

separator(){
  printf '%b%s%b\n' "$C_DIM" '  ────────────────────────────────────────────────────────────────────────' "$C_RESET"
}

header(){
  local title="${1:-Management}"
  local version api_state web_state
  [[ -t 1 ]] && clear 2>/dev/null || true
  version="$(version_value)"
  api_state="$(unit_state twinpanel-api.service)"
  web_state="$(unit_state twinpanel-web.service)"

  brand
  printf '  %bSelf-Hosted VPN Control Plane%b  %b•%b  v%s\n' "$C_CYAN" "$C_RESET" "$C_DIM" "$C_RESET" "$version"
  printf '  API %s    Web %s\n' "$(state_badge "$api_state")" "$(state_badge "$web_state")"
  separator
  printf '  %b%s%b\n' "$C_WHITE" "$title" "$C_RESET"
  separator
  printf '\n'
}

menu_item(){
  printf '  %b[%s]%b  %s\n' "$C_PURPLE" "$1" "$C_RESET" "$2"
}

menu_back(){
  printf '\n'
  menu_item 0 "Back"
}

pick(){
  CHOICE=""
  printf '\n  %bSelect a number:%b ' "$C_DIM" "$C_RESET"
  if ! IFS= read -r -n 1 CHOICE; then
    echo
    return 1
  fi
  echo "$CHOICE"
  return 0
}

pause(){
  printf '\n  %bPress any key to continue...%b' "$C_DIM" "$C_RESET"
  IFS= read -r -n 1 -s _ || true
  echo
}

invalid_choice(){
  printf '\n  %bInvalid selection. Use the menu numbers only.%b\n' "$C_RED" "$C_RESET"
  pause
}

confirm_action(){
  local title="$1"
  printf '%s\n\n' "$title"
  menu_item 1 "Continue"
  menu_item 0 "Cancel"
  pick || return 1
  [[ "$CHOICE" == "1" ]]
}

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
    export PYTHONPATH="$BACKEND${PYTHONPATH:+:$PYTHONPATH}"
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

show_unit(){
  local unit="$1"
  printf '  %-38s %s\n' "$unit" "$(state_badge "$(unit_state "$unit")")"
}

show_service_table(){
  show_unit twinpanel-api.service
  show_unit twinpanel-web.service
  show_unit twinpanel-updater.service
  show_unit twinpanel-backup.timer
  show_unit twinpanel-reseller-bots.service
  show_unit twinpanel-transport-manager.service
  show_unit twinpanel-bot.service
  show_unit nginx.service
  show_unit postgresql.service
  show_unit redis-server.service
}

restart_unit(){
  local unit="$1"
  if ! unit_exists "$unit"; then
    printf '%b%s is not installed.%b\n' "$C_YELLOW" "$unit" "$C_RESET"
    return 1
  fi
  if systemctl restart "$unit"; then
    printf '%b%s restarted successfully.%b\n' "$C_GREEN" "$unit" "$C_RESET"
    return 0
  fi
  printf '%bFailed to restart %s.%b\n' "$C_RED" "$unit" "$C_RESET"
  systemctl --no-pager --full status "$unit" 2>/dev/null | tail -n 25 || true
  return 1
}

restart_nginx(){
  if ! command -v nginx >/dev/null 2>&1; then
    printf '%bNginx is not installed.%b\n' "$C_YELLOW" "$C_RESET"
    return 1
  fi
  if ! nginx -t; then
    printf '%bNginx configuration test failed. Restart cancelled.%b\n' "$C_RED" "$C_RESET"
    return 1
  fi
  restart_unit nginx.service
}

restart_panel_now(){
  echo
  restart_unit twinpanel-api.service || true
  restart_unit twinpanel-web.service || true
  restart_nginx || true
}

http_health(){
  local label="$1" url="$2"
  if curl -fsS --max-time 4 "$url" >/dev/null 2>&1; then
    printf '  %-20s %b● OK%b\n' "$label" "$C_GREEN" "$C_RESET"
  else
    printf '  %-20s %b● UNREACHABLE%b\n' "$label" "$C_RED" "$C_RESET"
  fi
}

journal_unit(){
  local unit="$1"
  if ! unit_exists "$unit"; then
    printf '%b%s is not installed on this server.%b\n' "$C_YELLOW" "$unit" "$C_RESET"
    return 0
  fi
  journalctl -u "$unit" -n 120 --no-pager || true
}

status_menu(){
  header "Panel status"
  runtime_ports
  printf '  %-18s %s\n' "Version" "$(version_value)"
  printf '  %-18s %s\n' "API port" "$API_PORT"
  printf '  %-18s %s\n' "Web port" "$WEB_PORT"
  echo
  printf '  %bHealth%b\n' "$C_CYAN" "$C_RESET"
  http_health "API" "http://127.0.0.1:${API_PORT}/health/ready"
  http_health "Web" "http://127.0.0.1:${WEB_PORT}/health"
  http_health "Nginx" "http://127.0.0.1/health"
  echo
  printf '  %bCore services%b\n' "$C_CYAN" "$C_RESET"
  show_unit twinpanel-api.service
  show_unit twinpanel-web.service
  show_unit nginx.service
  show_unit postgresql.service
  show_unit redis-server.service
  pause
}

restart_menu(){
  header "Restart TwinPanel"
  echo "  Restarts API, Web and Nginx after validating Nginx configuration."
  echo
  if confirm_action "Restart TwinPanel now?"; then
    restart_panel_now
  else
    echo "  Cancelled."
  fi
  pause
}

services_menu(){
  while true; do
    header "Services"
    menu_item 1 "Restart TwinPanel"
    menu_item 2 "Restart API"
    menu_item 3 "Restart Web"
    menu_item 4 "Restart Nginx"
    menu_item 5 "Show all service states"
    menu_back
    pick || return
    case "$CHOICE" in
      1) restart_panel_now; pause ;;
      2) restart_unit twinpanel-api.service || true; pause ;;
      3) restart_unit twinpanel-web.service || true; pause ;;
      4) restart_nginx || true; pause ;;
      5) echo; show_service_table; pause ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

admin_account_info(){
  printf '%bAdministrator%b\n' "$C_CYAN" "$C_RESET"
  run_backend scripts/twinpanel_admin_cli.py show || true
  echo
  if [[ -s "$INITIAL_ADMIN_FILE" ]]; then
    printf '%bFirst-login credentials%b\n' "$C_CYAN" "$C_RESET"
    cat "$INITIAL_ADMIN_FILE"
  else
    echo "First-login credentials file: not available"
  fi
}

admin_edit_menu(){
  while true; do
    header "Administrator • Edit account"
    menu_item 1 "Change email"
    menu_item 2 "Change name"
    menu_item 3 "Set custom password"
    menu_back
    pick || return
    case "$CHOICE" in
      1)
        if read -r -p "  New email: " email && [[ -n "$email" ]]; then
          run_backend scripts/twinpanel_admin_cli.py change-email "$email" || true
        else
          echo "  Cancelled."
        fi
        pause
        ;;
      2)
        if read -r -p "  New name: " name && [[ -n "$name" ]]; then
          run_backend scripts/twinpanel_admin_cli.py change-name "$name" || true
        else
          echo "  Cancelled."
        fi
        pause
        ;;
      3)
        read -r -s -p "  New password: " pass || pass=""
        echo
        if [[ -n "$pass" ]]; then
          run_backend scripts/twinpanel_admin_cli.py reset-password --password "$pass" || true
        else
          echo "  Cancelled."
        fi
        unset pass
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

admin_menu(){
  while true; do
    header "Administrator"
    menu_item 1 "Account info"
    menu_item 2 "Generate a new password"
    menu_item 3 "Edit account"
    menu_item 4 "Delete saved first-login file"
    menu_back
    pick || return
    case "$CHOICE" in
      1) admin_account_info; pause ;;
      2)
        echo "  A new random password will be generated and shown once."
        echo
        if confirm_action "Reset administrator password?"; then
          run_backend scripts/twinpanel_admin_cli.py reset-password || true
        else
          echo "  Cancelled."
        fi
        pause
        ;;
      3) admin_edit_menu ;;
      4)
        if [[ ! -f "$INITIAL_ADMIN_FILE" ]]; then
          echo "  Saved first-login file does not exist."
        else
          echo "  This removes only the saved first-login credentials file."
          echo
          if confirm_action "Delete saved first-login file?"; then
            rm -f "$INITIAL_ADMIN_FILE"
            echo "  Deleted."
          else
            echo "  Cancelled."
          fi
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

protocol_menu(){
  header "VPN protocols"
  run_backend scripts/twinpanel_protocol_cli_en.py || true
  pause
}

update_summary(){
  run_backend -c 'from app.system_release import release_status; s=release_status(refresh_license_state=False); print("  Current :",s.get("current_version") or "unknown"); print("  Latest  :",s.get("latest_version") or "unknown"); print("  Update  :","AVAILABLE" if s.get("update_available") else "up to date"); e=s.get("manifest_error"); print("  Error   :",e) if e else None' || true
}

update_state_summary(){
  printf '  Updater : %s\n' "$(state_badge "$(unit_state twinpanel-updater.service)")"
  if [[ ! -s "$UPDATE_STATE_FILE" ]]; then
    echo "  State   : no update state yet"
    return
  fi
  python3 - "$UPDATE_STATE_FILE" <<'PY' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("  State   : unavailable")
    raise SystemExit(0)

for label, keys in (
    ("State", ("status", "state", "phase")),
    ("Version", ("version", "target_version", "latest_version")),
    ("Message", ("message", "detail")),
    ("Error", ("error", "last_error")),
):
    value = next((data.get(key) for key in keys if data.get(key)), None)
    if value is not None:
        print(f"  {label:<7}: {value}")
PY
}

update_menu(){
  while true; do
    header "Panel update"
    update_summary
    echo
    menu_item 1 "Refresh update check"
    menu_item 2 "Install latest update"
    menu_item 3 "Update status"
    menu_back
    pick || return
    case "$CHOICE" in
      1) echo; update_summary; pause ;;
      2)
        echo
        if confirm_action "Install the latest TwinPanel update?"; then
          echo
          run_backend -c 'from app.system_release import request_update; r=request_update(); print("Update request:", "accepted" if r else "submitted")' || true
        else
          echo "  Cancelled."
        fi
        pause
        ;;
      3) echo; update_state_summary; pause ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

backup_menu(){
  while true; do
    header "Backup"
    menu_item 1 "Create backup now"
    menu_item 2 "List backups"
    menu_item 3 "Automatic backup status"
    menu_back
    pick || return
    case "$CHOICE" in
      1)
        run_backend -c "from app.backup_service import create_backup; r=create_backup(kind='manual',send_telegram=False); print('Backup:', r.get('path') or r.get('filename') or 'created')" || true
        pause
        ;;
      2)
        if [[ -d "$BACKUP_ROOT" ]]; then
          find "$BACKUP_ROOT" -maxdepth 1 -type f -name '*.tpbak' -printf '%TY-%Tm-%Td %TH:%TM  %10s  %f\n' 2>/dev/null | sort -r || true
        else
          echo "  No backups found."
        fi
        pause
        ;;
      3)
        show_unit twinpanel-backup.timer
        if unit_exists twinpanel-backup.timer; then
          systemctl list-timers twinpanel-backup.timer --no-pager || true
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

logs_menu(){
  while true; do
    header "Logs & diagnostics"
    menu_item 1 "API"
    menu_item 2 "Web"
    menu_item 3 "Updater"
    menu_item 4 "Backup"
    menu_item 5 "Reseller Bots"
    menu_item 6 "Transport Manager"
    menu_item 7 "Telegram Bot"
    menu_item 8 "Nginx"
    menu_back
    pick || return
    case "$CHOICE" in
      1) journal_unit twinpanel-api.service; pause ;;
      2) journal_unit twinpanel-web.service; pause ;;
      3) journal_unit twinpanel-updater.service; pause ;;
      4) journal_unit twinpanel-backup.service; pause ;;
      5) journal_unit twinpanel-reseller-bots.service; pause ;;
      6) journal_unit twinpanel-transport-manager.service; pause ;;
      7) journal_unit twinpanel-bot.service; pause ;;
      8)
        if [[ -f /var/log/nginx/error.log ]]; then
          tail -n 120 /var/log/nginx/error.log || true
        else
          echo "  Nginx error log does not exist."
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

version_menu(){
  header "Version & GitHub"
  printf '  TwinPanel version : %s\n' "$(version_value)"
  printf '  Active release    : %s\n' "$(readlink -f "$ROOT" 2>/dev/null || echo "$ROOT")"
  printf '  GitHub            : https://github.com/matin111/twinpanel\n'
  printf '  Stable manifest   : https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json\n'
  pause
}

more_menu(){
  while true; do
    header "More tools"
    menu_item 1 "Administrator"
    menu_item 2 "Backup"
    menu_item 3 "Services"
    menu_item 4 "Logs & diagnostics"
    menu_item 5 "Version & GitHub"
    menu_back
    pick || return
    case "$CHOICE" in
      1) admin_menu ;;
      2) backup_menu ;;
      3) services_menu ;;
      4) logs_menu ;;
      5) version_menu ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

main_menu(){
  while true; do
    header "Quick actions"
    menu_item 1 "Panel status"
    menu_item 2 "Restart TwinPanel"
    menu_item 3 "VPN protocols"
    menu_item 4 "Panel update"
    menu_item 5 "More tools"
    printf '\n'
    menu_item 0 "Exit"
    if ! pick; then
      echo
      exit 0
    fi
    case "$CHOICE" in
      1) status_menu ;;
      2) restart_menu ;;
      3) protocol_menu ;;
      4) update_menu ;;
      5) more_menu ;;
      0) [[ -t 1 ]] && clear 2>/dev/null || true; exit 0 ;;
      *) invalid_choice ;;
    esac
  done
}

main_menu
