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
C_RESET='\033[0m'

line(){ printf '%*s\n' 68 '' | tr ' ' '='; }

header(){
  clear 2>/dev/null || true
  printf "${C_PURPLE}"
  line
  printf "  TwinPanel 2027 - SSH Management\n"
  line
  printf "${C_RESET}\n"
}

pause(){
  printf '\n'
  read -r -p "Press Enter to continue..." _ || true
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

show_unit(){
  local unit="$1" state color
  state="$(unit_state "$unit")"
  case "$state" in
    active) color="$C_GREEN" ;;
    failed) color="$C_RED" ;;
    *) color="$C_YELLOW" ;;
  esac
  printf '%-38s %b%s%b\n' "$unit" "$color" "${state:-unknown}" "$C_RESET"
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
    printf "${C_YELLOW}%s is not installed.${C_RESET}\n" "$unit"
    return 1
  fi
  if systemctl restart "$unit"; then
    printf "${C_GREEN}%s restarted successfully.${C_RESET}\n" "$unit"
    return 0
  fi
  printf "${C_RED}Failed to restart %s.${C_RESET}\n" "$unit"
  systemctl --no-pager --full status "$unit" 2>/dev/null | tail -n 25 || true
  return 1
}

restart_nginx(){
  if ! command -v nginx >/dev/null 2>&1; then
    printf "${C_YELLOW}Nginx is not installed.${C_RESET}\n"
    return 1
  fi
  if ! nginx -t; then
    printf "${C_RED}Nginx configuration test failed. Restart cancelled.${C_RESET}\n"
    return 1
  fi
  restart_unit nginx.service
}

http_health(){
  local label="$1" url="$2"
  if curl -fsS --max-time 4 "$url" >/dev/null 2>&1; then
    printf '%-24s %b%s%b\n' "$label" "$C_GREEN" "OK" "$C_RESET"
  else
    printf '%-24s %b%s%b\n' "$label" "$C_RED" "UNREACHABLE" "$C_RESET"
  fi
}

journal_unit(){
  local unit="$1"
  if ! unit_exists "$unit"; then
    printf "${C_YELLOW}%s is not installed on this server.${C_RESET}\n" "$unit"
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
  header
  runtime_ports
  printf "${C_BLUE}Panel status${C_RESET}\n\n"
  printf '%-24s %s\n' "Version:" "$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
  printf '%-24s %s\n' "Active release:" "$(readlink -f "$ROOT" 2>/dev/null || echo "$ROOT")"
  printf '%-24s %s\n' "API port:" "$API_PORT"
  printf '%-24s %s\n' "Web port:" "$WEB_PORT"
  echo
  printf "${C_BLUE}Services${C_RESET}\n"
  show_service_table
  echo
  printf "${C_BLUE}Health${C_RESET}\n"
  http_health "API ready:" "http://127.0.0.1:${API_PORT}/health/ready"
  http_health "Web health:" "http://127.0.0.1:${WEB_PORT}/health"
  http_health "Nginx health:" "http://127.0.0.1/health"
  pause
}

services_menu(){
  while true; do
    header
    printf "${C_BLUE}Service management${C_RESET}\n\n"
    echo "1) Restart API"
    echo "2) Restart Web"
    echo "3) Restart Nginx"
    echo "4) Restart API + Web + Nginx"
    echo "5) Show service status"
    echo "0) Back"
    if ! read -r -p "> " choice; then return; fi
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
      5)
        echo
        show_service_table
        pause
        ;;
      0) return ;;
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

admin_menu(){
  while true; do
    header
    printf "${C_BLUE}Administrator management${C_RESET}\n\n"
    echo "1) Show current administrator"
    echo "2) Show initial login credentials"
    echo "3) Reset administrator password"
    echo "4) Change administrator email"
    echo "5) Change administrator name"
    echo "6) Delete initial credentials file"
    echo "0) Back"
    if ! read -r -p "> " choice; then return; fi
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
        else
          read -r -p "Type YES to delete: " confirm || confirm=""
          if [[ "$confirm" == "YES" ]]; then
            rm -f "$INITIAL_ADMIN_FILE"
            echo "Deleted."
          else
            echo "Cancelled."
          fi
        fi
        pause
        ;;
      0) return ;;
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

protocol_menu(){
  header
  printf "${C_BLUE}Protocol management${C_RESET}\n\n"
  echo "Available protocols:"
  echo "  1) Cisco / OpenConnect"
  echo "  2) OpenVPN"
  echo "  3) WireGuard"
  echo "  4) L2TP / IPsec"
  echo "  5) V2Ray / Xray"
  echo
  echo "The selected protocol can be managed on this server or a remote Exit node."
  echo "Remove creates a backup on the selected target before changing protocol files."
  echo
  run_backend scripts/twinpanel_protocol_cli_en.py || true
  pause
}

update_menu(){
  while true; do
    header
    printf "${C_BLUE}Panel update${C_RESET}\n\n"
    echo "1) Check for update"
    echo "2) Start update"
    echo "3) Show updater status"
    echo "0) Back"
    if ! read -r -p "> " choice; then return; fi
    case "$choice" in
      1)
        run_backend -c 'import json; from app.system_release import release_status; s=release_status(refresh_license_state=False); print(json.dumps({"current_version":s.get("current_version"),"latest_version":s.get("latest_version"),"channel":s.get("channel"),"update_available":s.get("update_available"),"released_at":s.get("released_at"),"manifest_error":s.get("manifest_error"),"update":s.get("update")},ensure_ascii=True,indent=2,default=str))' || true
        pause
        ;;
      2)
        read -r -p "Type UPDATE to start: " confirm || confirm=""
        if [[ "$confirm" == "UPDATE" ]]; then
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
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

backup_menu(){
  while true; do
    header
    printf "${C_BLUE}Backup${C_RESET}\n\n"
    echo "1) Create manual backup"
    echo "2) List backup files"
    echo "3) Show automatic backup timer"
    echo "0) Back"
    if ! read -r -p "> " choice; then return; fi
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
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

logs_menu(){
  while true; do
    header
    printf "${C_BLUE}Logs and diagnostics${C_RESET}\n\n"
    echo "1) API"
    echo "2) Web"
    echo "3) Updater"
    echo "4) Backup"
    echo "5) Reseller Bots       [$(option_unit_state twinpanel-reseller-bots.service)]"
    echo "6) Transport Manager   [$(option_unit_state twinpanel-transport-manager.service)]"
    echo "7) Telegram Bot        [$(option_unit_state twinpanel-bot.service)]"
    echo "8) Nginx"
    echo "0) Back"
    if ! read -r -p "> " choice; then return; fi
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
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

version_menu(){
  header
  version="$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
  printf 'TwinPanel version: %s\n' "$version"
  printf 'Active release: %s\n' "$(readlink -f "$ROOT" 2>/dev/null || echo "$ROOT")"
  printf 'GitHub: https://github.com/matin111/twinpanel\n'
  printf 'Public installer: https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh\n'
  printf 'Stable manifest: https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json\n'
  if git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
    printf 'Git commit: %s\n' "$(git -C "$ROOT" rev-parse HEAD)"
  fi
  pause
}

main_menu(){
  while true; do
    header
    version="$(cat "$ROOT/VERSION" 2>/dev/null || echo unknown)"
    printf "${C_GREEN}TwinPanel v%s${C_RESET}\n\n" "$version"
    echo "1) Panel status"
    echo "2) Service management"
    echo "3) Administrator management"
    echo "4) Protocol management"
    echo "5) Panel update"
    echo "6) Backup"
    echo "7) Logs and diagnostics"
    echo "8) Version and GitHub"
    echo "0) Exit"
    echo
    if ! read -r -p "> " choice; then
      echo
      exit 0
    fi
    case "$choice" in
      1) status_menu ;;
      2) services_menu ;;
      3) admin_menu ;;
      4) protocol_menu ;;
      5) update_menu ;;
      6) backup_menu ;;
      7) logs_menu ;;
      8) version_menu ;;
      0) clear 2>/dev/null || true; exit 0 ;;
      *) echo "Invalid selection."; pause ;;
    esac
  done
}

main_menu
