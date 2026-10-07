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
systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service
systemctl reload nginx

if "$PREVIOUS/installer/healthcheck.sh"; then
  echo "ROLLBACK_OK release=$PREVIOUS"
  warn "Rollback فقط کد/Runtime را برگرداند. دیتابیس عمداً Restore نشد."
  exit 0
fi

warn "Rollback target healthcheck failed; restoring original release"
atomic_activate "$CURRENT"
record_previous_release "$PREVIOUS"
systemctl restart twinpanel-api.service twinpanel-web.service
systemctl reload nginx
fail "Rollback ناموفق بود و Release اصلی دوباره فعال شد"
