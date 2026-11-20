#!/usr/bin/env bash
# Build an unsigned macOS debug candidate, including the PacketTunnel target.
# This validates Swift/Flutter compilation only. An unsigned PacketTunnel
# cannot establish a functioning Network Extension VPN connection.
# Does NOT change project signing settings, certificates or system routes.
set -euo pipefail
cd "$(dirname "$0")/.."
workspace="macos/Runner.xcworkspace"
test -d "$workspace" || { echo "Missing macOS workspace" >&2; exit 1; }
log="${TWINCONNECT_BUILD_LOG:-$HOME/twinconnect-unsigned-macos-build.log}"
if [ "${TWINCONNECT_SKIP_APPKIT_RELINK:-0}" != "1" ]; then
  ruby tool/link_macos_tracked_appkit_sources.rb
fi
if xcodebuild \
  -workspace "$workspace" \
  -scheme Runner \
  -configuration Debug \
  -destination 'platform=macOS' \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build > "$log" 2>&1; then
  echo 'UNSIGNED BUILD SUCCEEDED (VPN extension not provisioned)'
  echo "Build log: $log"
  echo "NOTE: use the actual Runner.app output path; do not open Index.noindex copies."
else
  code=$?
  echo "UNSIGNED BUILD FAILED (exit $code)" >&2
  grep -nE 'error:|fatal error:|BUILD FAILED|BUILD SUCCEEDED' "$log" | tail -30 >&2 || true
  echo "Build log: $log" >&2
  exit "$code"
fi
