#!/usr/bin/env bash
set -Eeuo pipefail

LEGACY_WEB_ROOT="${LEGACY_WEB_ROOT:-/opt/moviline-web/current}"
LEGACY_DOWNLOAD_ROOT="${LEGACY_DOWNLOAD_ROOT:-/opt/moviline-downloads/apps}"
TARGET_WEB_ROOT="${TARGET_WEB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
TARGET_DOWNLOAD_ROOT="${TARGET_DOWNLOAD_ROOT:-/var/lib/twinpanel/downloads/apps}"

log(){ printf '[TwinPanel migration] %s\n' "$*"; }

mkdir -p "$TARGET_WEB_ROOT/public/learning/apps" "$TARGET_DOWNLOAD_ROOT"

if [[ -d "$LEGACY_WEB_ROOT/public/learning/apps" ]]; then
  log "Copying learning images from $LEGACY_WEB_ROOT/public/learning/apps"
  for name in cisco.png openconnect.png openvpn.png wireguard.png v2rayn.png v2rayng.png hiddify.png; do
    [[ -f "$LEGACY_WEB_ROOT/public/learning/apps/$name" ]] && cp -a "$LEGACY_WEB_ROOT/public/learning/apps/$name" "$TARGET_WEB_ROOT/public/learning/apps/$name"
  done
else
  log "Learning image directory not found; UI will use text fallback until assets are copied."
fi

if [[ -d "$LEGACY_DOWNLOAD_ROOT" ]]; then
  log "Copying offline applications from $LEGACY_DOWNLOAD_ROOT"
  cp -a "$LEGACY_DOWNLOAD_ROOT/." "$TARGET_DOWNLOAD_ROOT/"
else
  log "Offline application directory not found: $LEGACY_DOWNLOAD_ROOT"
fi

find "$TARGET_WEB_ROOT/public/learning/apps" -type f -exec chmod 0644 {} + 2>/dev/null || true
find "$TARGET_DOWNLOAD_ROOT" -type f -exec chmod 0644 {} + 2>/dev/null || true

log "Learning assets: $TARGET_WEB_ROOT/public/learning/apps"
log "Offline apps:    $TARGET_DOWNLOAD_ROOT"
log "Done. Configure Nginx /downloads/apps/ alias to $TARGET_DOWNLOAD_ROOT/."
