#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env
need curl
need systemctl

say "TwinPanel healthcheck"

failed=0
CURRENT="$(current_release)"
[[ -n "$CURRENT" && -d "$CURRENT" ]] || { warn "Current release symlink invalid"; failed=1; }

check_active(){
  local unit="$1"
  if systemctl is-active --quiet "$unit"; then
    info "$unit = active"
  else
    warn "$unit = inactive"
    systemctl status "$unit" --no-pager -l 2>/dev/null | tail -25 || true
    failed=1
  fi
}

for unit in postgresql.service redis-server.service nginx.service twinpanel-api.service twinpanel-web.service; do
  check_active "$unit"
done

if [[ -n "$CURRENT" && -f "$CURRENT/backend/app/tunnel_transport_manager.py" ]]; then
  check_active twinpanel-transport-manager.service
fi
if [[ -n "$CURRENT" && -f "$CURRENT/backend/app/reseller_bot_runtime.py" ]]; then
  check_active twinpanel-reseller-bots.service
fi
if [[ -n "$CURRENT" && -f "$CURRENT/backend/app/backup_worker.py" ]]; then
  check_active twinpanel-backup.timer
fi
if [[ -n "$CURRENT" && -f "$CURRENT/backend/app/telegram_runtime_bot.py" && -s /etc/twinpanel-telegram-api.env ]]; then
  check_active twinpanel-bot.service
elif [[ -n "$CURRENT" && -f "$CURRENT/backend/app/telegram_runtime_bot.py" ]]; then
  info "twinpanel-bot.service = configured unit / waiting for token"
fi

# The obsolete relay manager conflicts with the V3 transport manager single-writer model.
if systemctl is-active --quiet vpnshop-relay-manager.service 2>/dev/null; then
  warn "vpnshop-relay-manager.service must be inactive"
  failed=1
else
  info "vpnshop-relay-manager.service = inactive (expected)"
fi

if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    info "POSTGRES_READY"
  else
    warn "PostgreSQL readiness failed"
    failed=1
  fi
fi
if command -v redis-cli >/dev/null 2>&1; then
  if [[ "$(redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null || true)" == "PONG" ]]; then
    info "REDIS_READY"
  else
    warn "Redis readiness failed"
    failed=1
  fi
fi

API_URL="http://127.0.0.1:${TWINPANEL_API_PORT}/health"
WEB_URL="http://127.0.0.1:${TWINPANEL_WEB_PORT}/"
PUBLIC_URL="http://${TWINPANEL_DOMAIN}/"
PUBLIC_HEALTH="http://${TWINPANEL_DOMAIN}/health"

if wait_http "$API_URL" 20 1; then
  info "API_HEALTH_OK $API_URL"
else
  warn "API health failed: $API_URL"
  journalctl -u twinpanel-api.service -n 80 --no-pager 2>/dev/null || true
  failed=1
fi

if wait_http "$WEB_URL" 20 1; then
  info "WEB_HEALTH_OK $WEB_URL"
else
  warn "Web health failed: $WEB_URL"
  journalctl -u twinpanel-web.service -n 80 --no-pager 2>/dev/null || true
  failed=1
fi

if curl -fsS --resolve "${TWINPANEL_DOMAIN}:80:127.0.0.1" --max-time 6 "$PUBLIC_URL" >/dev/null 2>&1; then
  info "NGINX_ROUTE_OK $PUBLIC_URL"
else
  warn "Nginx local web route failed for $TWINPANEL_DOMAIN"
  nginx -t 2>&1 || true
  failed=1
fi

if curl -fsS --resolve "${TWINPANEL_DOMAIN}:80:127.0.0.1" --max-time 6 "$PUBLIC_HEALTH" >/dev/null 2>&1; then
  info "NGINX_API_ROUTE_OK $PUBLIC_HEALTH"
else
  warn "Nginx local API route failed for $TWINPANEL_DOMAIN"
  failed=1
fi

if ((failed)); then
  echo "HEALTHCHECK_FAILED"
  exit 1
fi

echo "HEALTHCHECK_OK"
