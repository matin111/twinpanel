#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env
RELEASE="${1:-$(current_release)}"
[[ -n "$RELEASE" && -d "$RELEASE/backend/app" ]] || fail "Backend release پیدا نشد"
[[ -x "$RELEASE/backend/venv/bin/python" ]] || fail "Backend venv پیدا نشد"
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
rm -rf /etc/systemd/system/vpnshop-relay-manager.service.d

if [[ -f "$RELEASE/backend/app/tunnel_transport_manager.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-transport-manager.service.tpl" twinpanel-transport-manager.service
else
  systemctl disable --now twinpanel-transport-manager.service 2>/dev/null || true
  rm -f /etc/systemd/system/twinpanel-transport-manager.service
  warn "app.tunnel_transport_manager پیدا نشد؛ Transport Manager نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/reseller_bot_runtime.py" ]]; then
  # The legacy runtime expects a Fernet key at this exact path. Generate it locally;
  # never migrate or commit the old server key.
  if [[ ! -s /etc/twinpanel-reseller-bot.key ]]; then
    umask 077
    "$RELEASE/backend/venv/bin/python" - <<'PY' >/etc/twinpanel-reseller-bot.key
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
    chmod 600 /etc/twinpanel-reseller-bot.key
  fi
  install_unit "$RELEASE/deploy/systemd/twinpanel-reseller-bots.service.tpl" twinpanel-reseller-bots.service
else
  systemctl disable --now twinpanel-reseller-bots.service 2>/dev/null || true
  rm -f /etc/systemd/system/twinpanel-reseller-bots.service
  warn "app.reseller_bot_runtime پیدا نشد؛ Reseller Bots نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/telegram_runtime_bot.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-bot.service.tpl" twinpanel-bot.service
else
  systemctl disable --now twinpanel-bot.service 2>/dev/null || true
  rm -f /etc/systemd/system/twinpanel-bot.service
  warn "app.telegram_runtime_bot پیدا نشد؛ Main Bot unit نصب نشد"
fi

if [[ -f "$RELEASE/backend/app/backup_worker.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-backup.service.tpl" twinpanel-backup.service
  install -m 644 "$RELEASE/deploy/systemd/twinpanel-backup.timer" /etc/systemd/system/twinpanel-backup.timer
else
  systemctl disable --now twinpanel-backup.timer 2>/dev/null || true
  rm -f /etc/systemd/system/twinpanel-backup.service /etc/systemd/system/twinpanel-backup.timer
  warn "app.backup_worker پیدا نشد؛ Backup timer نصب نشد"
fi

if [[ -f "$RELEASE/quota-agent/agent.py" ]]; then
  install_unit "$RELEASE/deploy/systemd/twinpanel-quota-agent.service.tpl" twinpanel-quota-agent.service
else
  systemctl disable --now twinpanel-quota-agent.service 2>/dev/null || true
  rm -f /etc/systemd/system/twinpanel-quota-agent.service
  warn "Quota Agent code در Release موجود نیست؛ سرویس مرکزی Quota نصب نشد"
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

# Main bot requires its API token/secret. Install the unit now, but start it only
# after the panel writes /etc/twinpanel-telegram-api.env.
if [[ -f /etc/systemd/system/twinpanel-bot.service ]]; then
  if [[ -s /etc/twinpanel-telegram-api.env ]]; then
    chmod 600 /etc/twinpanel-telegram-api.env
    systemctl enable --now twinpanel-bot.service
  else
    systemctl disable --now twinpanel-bot.service 2>/dev/null || true
    info "MAIN_BOT_UNIT_READY token_not_configured"
  fi
fi

# Quota Agent is optional on the central host. Never copy PKI/config into Git.
# Start only when the local production configuration references existing mTLS files.
if [[ -f /etc/systemd/system/twinpanel-quota-agent.service ]]; then
  QUOTA_READY=0
  if [[ -s /etc/twinpanel-quota-agent/config.json ]]; then
    if python3 - <<'PY'
import json
from pathlib import Path
p=Path('/etc/twinpanel-quota-agent/config.json')
try:
    cfg=json.loads(p.read_text())
except Exception:
    raise SystemExit(1)
for key in ('client_cert','client_key','ca_cert'):
    value=str(cfg.get(key) or '').strip()
    if not value or not Path(value).is_file():
        raise SystemExit(1)
raise SystemExit(0)
PY
    then QUOTA_READY=1; fi
  fi

  if (( QUOTA_READY == 1 )); then
    install -d -m 700 /var/lib/twinpanel-quota-agent
    systemctl enable --now twinpanel-quota-agent.service
  else
    systemctl disable --now twinpanel-quota-agent.service 2>/dev/null || true
    info "QUOTA_AGENT_UNIT_READY config_or_mtls_not_configured"
  fi
fi

# The removed relay manager must remain disabled after daemon-reload too.
systemctl disable --now vpnshop-relay-manager.service 2>/dev/null || true

echo "WORKERS_READY"
