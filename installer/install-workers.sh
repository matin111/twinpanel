#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env
RELEASE="${1:-$(current_release)}"
[[ -n "$RELEASE" && -d "$RELEASE/backend/app" ]] || fail "Backend release پیدا نشد"
export TWINPANEL_DOMAIN TWINPANEL_WEB_PORT TWINPANEL_API_PORT

install_unit(){
  local template="$1" unit="$2"
  [[ -f "$template" ]] || fail "Template missing: $template"
  render "$template" "/etc/systemd/system/$unit"
  chmod 644 "/etc/systemd/system/$unit"
}

say "Installing verified TwinPanel workers"

# V3 transport manager is the single writer. The obsolete relay manager must stay off.
systemctl disable --now vpnshop-relay-manager.service 2>/dev/null || true
rm -f /etc/systemd/system/vpnshop-relay-manager.service

if [[ -f "$RELEASE/backend/app/tunnel_transport_manager.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-transport-manager.service.tpl" twinpanel-transport-manager.service
else
  warn "app.tunnel_transport_manager پیدا نشد؛ Transport Manager نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/reseller_bot_runtime.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-reseller-bots.service.tpl" twinpanel-reseller-bots.service
else
  warn "app.reseller_bot_runtime پیدا نشد؛ Reseller Bots نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/telegram_runtime_bot.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-bot.service.tpl" twinpanel-bot.service
else
  warn "app.telegram_runtime_bot پیدا نشد؛ Main Bot unit نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/backup_worker.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-backup.service.tpl" twinpanel-backup.service
  install -m 644 "$RELEASE/deploy/systemd/twinpanel-backup.timer" /etc/systemd/system/twinpanel-backup.timer
else
  warn "app.backup_worker پیدا نشد؛ Backup timer نصب نشد"
fi

systemctl daemon-reload

if [[ -f /etc/systemd/system/twinpanel-transport-manager.service ]]; then
  systemctl enable --now twinpanel-transport-manager.service
fi
if [[ -f /etc/systemd/system/twinpanel-reseller-bots.service ]]; then
  systemctl enable --now twinpanel-reseller-bots.service
fi
if [[ -f /etc/systemd/system/twinpanel-backup.timer ]]; then
  systemctl enable --now twinpanel-backup.timer
fi

# Main bot requires its token/secret. Install the unit now, but start it only when configured.
if [[ -f /etc/systemd/system/twinpanel-bot.service ]]; then
  if [[ -s /etc/twinpanel-telegram-api.env ]]; then
    systemctl enable --now twinpanel-bot.service
  else
    systemctl disable --now twinpanel-bot.service 2>/dev/null || true
    info "MAIN_BOT_UNIT_READY token_not_configured"
  fi
fi

echo "WORKERS_READY"
