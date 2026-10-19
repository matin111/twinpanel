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

C_PURPLE='\033[1;35m'
C_BLUE='\033[1;34m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[1;31m'
C_DIM='\033[2m'
C_RESET='\033[0m'

WIDTH=58

line(){ printf '%*s\n' "$WIDTH" '' | tr ' ' '-'; }
strong_line(){ printf '%*s\n' "$WIDTH" '' | tr ' ' '='; }

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
    active) printf '%bONLINE%b' "$C_GREEN" "$C_RESET" ;;
    failed) printf '%bFAILED%b' "$C_RED" "$C_RESET" ;;
    inactive) printf '%bOFFLINE%b' "$C_YELLOW" "$C_RESET" ;;
    not-installed) printf '%bN/A%b' "$C_DIM" "$C_RESET" ;;
    *) printf '%b%s%b' "$C_YELLOW" "${state:-unknown}" "$C_RESET" ;;
  esac
}

header(){
  local title="${1:-Server management}"
  local version api_state web_state
  clear 2>/dev/null || true
  version="$(version_value)"
  api_state="$(unit_state twinpanel-api.service)"
  web_state="$(unit_state twinpanel-web.service)"

  printf '%b' "$C_PURPLE"
  strong_line
  printf '  TwinPanel  |  Simple SSH Manager\n'
  strong_line
  printf '%b' "$C_RESET"
  printf '  Version: %b%s%b\n' "$C_GREEN" "$version" "$C_RESET"
  printf '  API: %-18b Web: %b\n' "$(state_badge "$api_state")" "$(state_badge "$web_state")"
  line
  printf '  %b%s%b\n' "$C_BLUE" "$title" "$C_RESET"
  line
  printf '\n'
}

pause(){
  printf '\n'
  read -r -p "Press Enter to continue..." _ || true
}

invalid_choice(){
  printf '\n%bInvalid selection.%b\n' "$C_RED" "$C_RESET"
  pause
}

confirm_yes(){
  local prompt="$1" answer
  read -r -p "$prompt [y/N]: " answer || answer=""
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
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
  local unit="$1" state
  state="$(unit_state "$unit")"
  printf '  %-38s %b\n' "$unit" "$(state_badge "$state")"
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
    printf "%b%s is not installed.%b\n" "$C_YELLOW" "$unit" "$C_RESET"
    return 1
  fi
  if systemctl restart "$unit"; then
    printf "%b%s restarted successfully.%b\n" "$C_GREEN" "$unit" "$C_RESET"
    return 0
  fi
  printf "%bFailed to restart %s.%b\n" "$C_RED" "$unit" "$C_RESET"
  systemctl --no-pager --full status "$unit" 2>/dev/null | tail -n 25 || true
  return 1
}

restart_nginx(){
  if ! command -v nginx >/dev/null 2>&1; then
    printf "%bNginx is not installed.%b\n" "$C_YELLOW" "$C_RESET"
    return 1
  fi
  if ! nginx -t; then
    printf "%bNginx configuration test failed. Restart cancelled.%b\n" "$C_RED" "$C_RESET"
    return 1
  fi
  restart_unit nginx.service
}

restart_stack(){
  header "Restart TwinPanel"
  printf 'This restarts only the panel API, Web and Nginx.\n\n'
  if ! confirm_yes "Restart TwinPanel now?"; then
    echo "Cancelled."
    pause
    return
  fi
  echo
  restart_unit twinpanel-api.service || true
  restart_unit twinpanel-web.service || true
  restart_nginx || true
  pause
}

http_health(){
  local label="$1" url="$2"
  if curl -fsS --max-time 4 "$url" >/dev/null 2>&1; then
    printf '  %-24s %bOK%b\n' "$label" "$C_GREEN" "$C_RESET"
  else
    printf '  %-24s %bUNREACHABLE%b\n' "$label" "$C_RED" "$C_RESET"
  fi
}

journal_unit(){
  local unit="$1"
  if ! unit_exists "$unit"; then
    printf "%b%s is not installed on this server.%b\n" "$C_YELLOW" "$unit" "$C_RESET"
    return 0
  fi
  journalctl -u "$unit" -n 120 --no-pager || true
}

option_unit_state(){
  local unit="$1" state
  state="$(unit_state "$unit")"
  printf '%s' "$state"
}

status_menu(){
  header "Panel status"
  runtime_ports
  printf '  %-18s %s\n' "Version" "$(version_value)"
  printf '  %-18s %s\n' "API port" "$API_PORT"
  printf '  %-18s %s\n' "Web port" "$WEB_PORT"
  printf '  %-18s %s\n' "Release" "$(readlink -f "$ROOT" 2>/dev/null || echo "$ROOT")"
  echo
  printf '%bHealth%b\n' "$C_BLUE" "$C_RESET"
  http_health "API" "http://127.0.0.1:${API_PORT}/health/ready"
  http_health "Web" "http://127.0.0.1:${WEB_PORT}/health"
  http_health "Nginx" "http://127.0.0.1/health"
  echo
  printf '%bCore services%b\n' "$C_BLUE" "$C_RESET"
  show_unit twinpanel-api.service
  show_unit twinpanel-web.service
  show_unit nginx.service
  show_unit postgresql.service
  show_unit redis-server.service
  pause
}

services_menu(){
  while true; do
    header "Service management"
    echo "  [1] Restart API"
    echo "  [2] Restart Web"
    echo "  [3] Restart Nginx"
    echo "  [4] Restart panel stack"
    echo "  [5] Show all service states"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
      1) restart_unit twinpanel-api.service || true; pause ;;
      2) restart_unit twinpanel-web.service || true; pause ;;
      3) restart_nginx || true; pause ;;
      4)
        restart_unit twinpanel-api.service || true
        restart_unit twinpanel-web.service || true
        restart_nginx || true
        pause
        ;;
      5) echo; show_service_table; pause ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

admin_menu(){
  while true; do
    header "Administrator management"
    echo "  [1] Show administrator"
    echo "  [2] Show initial login credentials"
    echo "  [3] Reset password"
    echo "  [4] Change email"
    echo "  [5] Change name"
    echo "  [6] Delete initial credentials file"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
      1)
        run_backend scripts/twinpanel_admin_cli.py show || true
        pause
        ;;
      2)
        if [[ -s "$INITIAL_ADMIN_FILE" ]]; then
          cat "$INITIAL_ADMIN_FILE"
        else
          echo "Initial credentials file does not exist."
        fi
        pause
        ;;
      3)
        echo "Leave blank to generate a strong random password."
        read -r -s -p "New password: " pass || pass=""
        echo
        if [[ -n "$pass" ]]; then
          run_backend scripts/twinpanel_admin_cli.py reset-password --password "$pass" || true
        else
          run_backend scripts/twinpanel_admin_cli.py reset-password || true
        fi
        unset pass
        pause
        ;;
      4)
        if read -r -p "New email: " email; then
          run_backend scripts/twinpanel_admin_cli.py change-email "$email" || true
        fi
        pause
        ;;
      5)
        if read -r -p "New name: " name; then
          run_backend scripts/twinpanel_admin_cli.py change-name "$name" || true
        fi
        pause
        ;;
      6)
        if [[ ! -f "$INITIAL_ADMIN_FILE" ]]; then
          echo "Initial credentials file does not exist."
        elif confirm_yes "Delete the initial credentials file?"; then
          rm -f "$INITIAL_ADMIN_FILE"
          echo "Deleted."
        else
          echo "Cancelled."
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

protocol_menu(){
  header "Protocol management"
  echo "Available protocols:"
  echo "  [1] Cisco / OpenConnect"
  echo "  [2] OpenVPN"
  echo "  [3] WireGuard"
  echo "  [4] L2TP / IPsec"
  echo "  [5] V2Ray / Xray"
  echo
  printf '%bTip:%b choose a protocol first, then choose Local or an Exit node.\n' "$C_DIM" "$C_RESET"
  echo
  run_backend scripts/twinpanel_protocol_cli_en.py || true
  pause
}

update_menu(){
  while true; do
    header "Panel update"
    echo "  [1] Check for update"
    echo "  [2] Install update"
    echo "  [3] Update status"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
      1)
        run_backend -c 'from app.system_release import release_status; s=release_status(refresh_license_state=False); print("Current :",s.get("current_version") or "unknown"); print("Latest  :",s.get("latest_version") or "unknown"); print("Channel :",s.get("channel") or "unknown"); print("Update  :","AVAILABLE" if s.get("update_available") else "up to date"); e=s.get("manifest_error"); print("Error   :",e) if e else None' || true
        pause
        ;;
      2)
        if confirm_yes "Start the TwinPanel update?"; then
          run_backend -c 'import json; from app.system_release import request_update; print(json.dumps(request_update(),ensure_ascii=True,indent=2,default=str))' || true
        else
          echo "Cancelled."
        fi
        pause
        ;;
      3)
        if unit_exists twinpanel-updater.service; then
          systemctl --no-pager --full status twinpanel-updater.service || true
        else
          echo "twinpanel-updater.service is not installed."
        fi
        echo
        if [[ -s "$UPDATE_STATE_FILE" ]]; then
          echo "Update state:"
          cat "$UPDATE_STATE_FILE"
        else
          echo "No update state has been recorded yet."
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

backup_menu(){
  while true; do
    header "Backup"
    echo "  [1] Create backup now"
    echo "  [2] List backups"
    echo "  [3] Automatic backup status"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
      1)
        run_backend -c "from app.backup_service import create_backup; import json; print(json.dumps(create_backup(kind='manual',send_telegram=False),ensure_ascii=True,indent=2,default=str))" || true
        pause
        ;;
      2)
        if [[ -d "$BACKUP_ROOT" ]]; then
          find "$BACKUP_ROOT" -maxdepth 1 -type f \( -name '*.tpbak' -o -name '*.tpbak.meta.json' \) -printf '%TY-%Tm-%Td %TH:%TM  %10s  %f\n' 2>/dev/null | sort -r || true
        else
          echo "Backup directory does not exist."
        fi
        pause
        ;;
      3)
        if unit_exists twinpanel-backup.timer; then
          systemctl --no-pager --full status twinpanel-backup.timer || true
          echo
          systemctl list-timers twinpanel-backup.timer --no-pager || true
        else
          echo "twinpanel-backup.timer is not installed."
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
    header "Logs and diagnostics"
    echo "  [1] API"
    echo "  [2] Web"
    echo "  [3] Updater"
    echo "  [4] Backup"
    echo "  [5] Reseller Bots       [$(option_unit_state twinpanel-reseller-bots.service)]"
    echo "  [6] Transport Manager   [$(option_unit_state twinpanel-transport-manager.service)]"
    echo "  [7] Telegram Bot        [$(option_unit_state twinpanel-bot.service)]"
    echo "  [8] Nginx"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
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
          echo "Nginx error log does not exist."
        fi
        pause
        ;;
      0) return ;;
      *) invalid_choice ;;
    esac
  done
}

version_menu(){
  header "Version and GitHub"
  printf '  TwinPanel version : %s\n' "$(version_value)"
  printf '  Active release    : %s\n' "$(readlink -f "$ROOT" 2>/dev/null || echo "$ROOT")"
  printf '  GitHub            : https://github.com/matin111/twinpanel\n'
  printf '  Public installer  : https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh\n'
  printf '  Stable manifest   : https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json\n'
  if git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
    printf '  Git commit        : %s\n' "$(git -C "$ROOT" rev-parse HEAD)"
  fi
  pause
}

more_menu(){
  while true; do
    header "More options"
    echo "  [1] Administrator management"
    echo "  [2] Backup"
    echo "  [3] Service management"
    echo "  [4] Logs and diagnostics"
    echo "  [5] Version and GitHub"
    echo
    echo "  [0] Back"
    echo
    if ! read -r -p "Select: " choice; then return; fi
    case "$choice" in
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
    echo "  [1] Panel status"
    echo "  [2] Restart TwinPanel"
    echo "  [3] VPN protocols"
    echo "  [4] Panel update"
    echo "  [5] More options"
    echo
    echo "  [0] Exit"
    echo
    if ! read -r -p "Select: " choice; then
      echo
      exit 0
    fi
    case "$choice" in
      1) status_menu ;;
      2) restart_stack ;;
      3) protocol_menu ;;
      4) update_menu ;;
      5) more_menu ;;
      0) clear 2>/dev/null || true; exit 0 ;;
      *) invalid_choice ;;
    esac
  done
}

main_menu
