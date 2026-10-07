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
for unit in twinpanel-api.service twinpanel-web.service nginx.service; do
  if systemctl is-active --quiet "$unit"; then
    info "$unit = active"
  else
    warn "$unit = inactive"
    systemctl status "$unit" --no-pager -l 2>/dev/null | tail -25 || true
    failed=1
  fi
done

API_URL="http://127.0.0.1:${TWINPANEL_API_PORT}/health"
WEB_URL="http://127.0.0.1:${TWINPANEL_WEB_PORT}/"
PUBLIC_URL="http://${TWINPANEL_DOMAIN}/"

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
  warn "Nginx local route failed for $TWINPANEL_DOMAIN"
  nginx -t 2>&1 || true
  failed=1
fi

if ((failed)); then
  echo "HEALTHCHECK_FAILED"
  exit 1
fi

echo "HEALTHCHECK_OK"
