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
  # Resolve the real built product from Xcode build settings, not a guessed
  # DerivedData path (especially not Index.noindex/Build/Products).
  # Package both real engines into Runner.app; fail the build if either is
  # missing so we never claim to have a portable standalone client.
  built_app="$(python3 - "$workspace" <<'PY'
import json
import subprocess
import sys
command = [
    "xcodebuild", "-workspace", sys.argv[1], "-scheme", "Runner",
    "-configuration", "Debug", "-destination", "platform=macOS",
    "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO",
    "-showBuildSettings", "-json",
]
try:
    result = subprocess.run(command, check=True, capture_output=True,
                            text=True, timeout=120)
    rows = json.loads(result.stdout)
    targets = [row["buildSettings"] for row in rows
               if row.get("target") == "Runner"]
    if len(targets) != 1:
        raise ValueError("RUNNER_BUILD_SETTINGS_AMBIGUOUS")
    import os
    settings = targets[0]
    app = os.path.join(settings["TARGET_BUILD_DIR"],
                       settings["FULL_PRODUCT_NAME"])
    if not app.endswith(".app") or not os.path.isdir(app):
        raise ValueError("RUNNER_PRODUCT_NOT_FOUND")
    print(app)
except Exception as exc:
    print("RUNNER_PRODUCT_RESOLUTION_FAILED: " + type(exc).__name__,
          file=sys.stderr)
    sys.exit(3)
PY
  )" || exit 3
  bash tool/package_macos_local_proxy_runtime.sh "$built_app"
  echo "UNSIGNED BUILD + LOCAL PROXY ENGINE PACKAGING SUCCEEDED"
  echo "Runner.app: $built_app"
  echo "Build log: $log"
  echo "NOTE: local SOCKS/HTTP proxy only. System VPN extension not provisioned."
else
  code=$?
  echo "UNSIGNED BUILD FAILED (exit $code)" >&2
  grep -nE 'error:|fatal error:|BUILD FAILED|BUILD SUCCEEDED' "$log" | tail -30 >&2 || true
  echo "Build log: $log" >&2
  exit "$code"
fi
