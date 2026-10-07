#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env
CURRENT="$(current_release)"
[[ -n "$CURRENT" && -d "$CURRENT" ]] || fail "Release فعلی پیدا نشد"
[[ -f "$CURRENT/deploy/systemd/twinpanel-api.service.tpl" ]] || fail "API service template پیدا نشد"
[[ -f "$CURRENT/deploy/systemd/twinpanel-web.service.tpl" ]] || fail "Web service template پیدا نشد"

say "TwinPanel repair"
export TWINPANEL_DOMAIN TWINPANEL_WEB_PORT TWINPANEL_API_PORT

render "$CURRENT/deploy/systemd/twinpanel-api.service.tpl" /etc/systemd/system/twinpanel-api.service
render "$CURRENT/deploy/systemd/twinpanel-web.service.tpl" /etc/systemd/system/twinpanel-web.service
chmod 644 /etc/systemd/system/twinpanel-api.service /etc/systemd/system/twinpanel-web.service

if [[ ! -f /etc/nginx/sites-available/twinpanel.conf || "${TWINPANEL_REBUILD_NGINX:-0}" == "1" ]]; then
  say "Rebuilding Nginx configuration"
  TMP_BACKUP=""
  if [[ -f /etc/nginx/sites-available/twinpanel.conf ]]; then
    TMP_BACKUP="$(mktemp)"
    cp -a /etc/nginx/sites-available/twinpanel.conf "$TMP_BACKUP"
  fi
  render "$CURRENT/deploy/nginx/twinpanel.conf.tpl" /etc/nginx/sites-available/twinpanel.conf
  ln -sfn /etc/nginx/sites-available/twinpanel.conf /etc/nginx/sites-enabled/twinpanel.conf

  if [[ "${TWINPANEL_SSL_ENABLED:-0}" == "1" ]]; then
    if command -v certbot >/dev/null 2>&1 && certbot --nginx -d "$TWINPANEL_DOMAIN" --non-interactive --redirect --keep-until-expiring; then
      info "SSL_CONFIG_REPAIRED"
    else
      warn "Certbot نتوانست HTTPS config را بازسازی کند"
      if [[ -n "$TMP_BACKUP" && -s "$TMP_BACKUP" ]]; then
        cp -a "$TMP_BACKUP" /etc/nginx/sites-available/twinpanel.conf
        warn "Nginx config قبلی برگردانده شد"
      else
        fail "HTTPS repair failed and no previous Nginx config exists"
      fi
    fi
  fi
  [[ -z "$TMP_BACKUP" ]] || rm -f "$TMP_BACKUP"
fi

nginx -t
systemctl daemon-reload
systemctl enable twinpanel-api.service twinpanel-web.service nginx.service
systemctl restart twinpanel-api.service twinpanel-web.service

bash "$CURRENT/installer/install-workers.sh" "$CURRENT"
install -m 755 "$CURRENT/installer/twinpanelctl" /usr/local/bin/twinpanel
systemctl reload nginx

if bash "$CURRENT/installer/healthcheck.sh"; then
  echo "REPAIR_OK release=$CURRENT"
  exit 0
fi

fail "Repair انجام شد اما Healthcheck هنوز ناموفق است"
