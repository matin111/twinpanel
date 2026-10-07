#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env

CURRENT="$(current_release)"
PREVIOUS="$(previous_release)"
[[ -n "$CURRENT" && -d "$CURRENT" ]] || fail "Release فعلی معتبر نیست"
[[ -n "$PREVIOUS" && -d "$PREVIOUS" ]] || fail "Release قبلی برای Rollback پیدا نشد"
[[ "$CURRENT" != "$PREVIOUS" ]] || fail "Release قبلی و فعلی یکسان هستند"

say "TwinPanel rollback"
info "Current : $CURRENT"
info "Previous: $PREVIOUS"

record_previous_release "$CURRENT"
atomic_activate "$PREVIOUS"
export TWINPANEL_DOMAIN TWINPANEL_WEB_PORT TWINPANEL_API_PORT
render "$PREVIOUS/deploy/systemd/twinpanel-api.service.tpl" /etc/systemd/system/twinpanel-api.service
render "$PREVIOUS/deploy/systemd/twinpanel-web.service.tpl" /etc/systemd/system/twinpanel-web.service
systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service

if [[ -x "$PREVIOUS/installer/install-workers.sh" || -f "$PREVIOUS/installer/install-workers.sh" ]]; then
  bash "$PREVIOUS/installer/install-workers.sh" "$PREVIOUS"
fi
install -m 755 "$PREVIOUS/installer/twinpanelctl" /usr/local/bin/twinpanel 2>/dev/null || true
systemctl reload nginx

if bash "$PREVIOUS/installer/healthcheck.sh"; then
  echo "ROLLBACK_OK release=$PREVIOUS"
  warn "Rollback فقط کد/Runtime را برگرداند. دیتابیس عمداً Restore نشد."
  exit 0
fi

warn "Rollback target healthcheck failed; restoring original release"
atomic_activate "$CURRENT"
record_previous_release "$PREVIOUS"
export TWINPANEL_DOMAIN TWINPANEL_WEB_PORT TWINPANEL_API_PORT
render "$CURRENT/deploy/systemd/twinpanel-api.service.tpl" /etc/systemd/system/twinpanel-api.service
render "$CURRENT/deploy/systemd/twinpanel-web.service.tpl" /etc/systemd/system/twinpanel-web.service
systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service
bash "$CURRENT/installer/install-workers.sh" "$CURRENT" 2>/dev/null || true
install -m 755 "$CURRENT/installer/twinpanelctl" /usr/local/bin/twinpanel 2>/dev/null || true
systemctl reload nginx
fail "Rollback ناموفق بود و Release اصلی دوباره فعال شد"
