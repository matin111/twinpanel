#!/usr/bin/env bash
# Produce an offline, unsigned TwinConnect macOS candidate before VPS expiry.
# This is an app-local SOCKS/HTTP proxy candidate, NOT a system-wide VPN.
# Writes archives only to the requested export folder; no network changes.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "MACOS_ONLY" >&2
  exit 2
fi
output="${TWINCONNECT_EXPORT_DIR:-$HOME/TwinConnect-macOS-export}"
if [[ "$output" != /* || -L "$output" ]]; then
  echo "INVALID_EXPORT_DIRECTORY" >&2
  exit 2
fi
mkdir -p "$output"
if [[ ! -d "$output" || -L "$output" ]]; then
  echo "UNSAFE_EXPORT_DIRECTORY" >&2
  exit 2
fi

if [[ "${TWINCONNECT_SKIP_BUILD:-0}" != "1" ]]; then
  bash tool/build_macos_unsigned_debug.sh
fi

# Query Xcode rather than using a hard-coded DerivedData path.
app="$(python3 - <<'PY'
import json
import os
import subprocess
import sys
cmd = ["xcodebuild", "-workspace", "macos/Runner.xcworkspace",
       "-scheme", "Runner", "-configuration", "Debug",
       "-destination", "platform=macOS", "CODE_SIGNING_ALLOWED=NO",
       "CODE_SIGNING_REQUIRED=NO", "-showBuildSettings", "-json"]
try:
    result = subprocess.run(cmd, capture_output=True, text=True,
                            check=True, timeout=120)
    rows = json.loads(result.stdout)
    targets = [r["buildSettings"] for r in rows if r.get("target") == "Runner"]
    if len(targets) != 1:
        raise ValueError("RUNNER_BUILD_SETTINGS_AMBIGUOUS")
    settings = targets[0]
    app = os.path.join(settings["TARGET_BUILD_DIR"],
                       settings["FULL_PRODUCT_NAME"])
    if not app.endswith(".app") or not os.path.isdir(app):
        raise ValueError("APP_NOT_BUILT")
    print(app)
except Exception as exc:
    print("APP_RESOLUTION_FAILED: " + type(exc).__name__, file=sys.stderr)
    sys.exit(3)
PY
)"
test -d "$app/Contents/MacOS" || { echo "APP_EXECUTABLE_MISSING" >&2; exit 3; }
test -r "$app/Contents/Info.plist" || { echo "APP_INFO_MISSING" >&2; exit 3; }
runtime="$app/Contents/Resources/twinconnect-runtime"
manager="$runtime/macos_native/standalone_connection_manager.py"
test -r "$manager" || { echo "PACKAGED_MANAGER_MISSING" >&2; exit 3; }
test -r "$runtime/macos_native/xray_unsigned_tun_candidate.py" || { echo "PACKAGED_VLESS_TUN_CONVERTER_MISSING" >&2; exit 3; }
test -r "$runtime/macos_native/unsigned_tun_policy.py" || { echo "PACKAGED_TUN_POLICY_MISSING" >&2; exit 3; }
case "$(uname -m)" in
  x86_64) arch=amd64; macarch=x86_64;;
  arm64) arch=arm64; macarch=arm64;;
  *) echo "UNSUPPORTED_ARCH" >&2; exit 3;;
esac
for spec in "singbox:sing-box" "xray:xray"; do
  family="${spec%%:*}"
  binary="${spec##*:}"
  executable="$runtime/macos_native/build/$family/$arch/$binary"
  test -x "$executable" || { echo "PACKAGED_ENGINE_MISSING: $family" >&2; exit 3; }
  /usr/bin/lipo -archs "$executable" | tr ' ' '\n' | grep -Fxq "$macarch" ||
    { echo "PACKAGED_ENGINE_WRONG_ARCH: $family" >&2; exit 3; }
done

# Do not claim signed/fully tunneled installation. macOS may block
# launching an unsigned app; it requires user-approved local testing.
if /usr/bin/codesign -dv "$app" >/dev/null 2>&1; then
  echo "UNEXPECTED_SIGNED_BUNDLE_REFUSED" >&2
  exit 3
fi

commit="$(git rev-parse --short=12 HEAD)"
name="TwinConnect-macOS-${macarch}-unsigned-${commit}"
zip="$output/$name.zip"
if [[ -e "$zip" || -L "$zip" ]]; then
  echo "EXPORT_ALREADY_EXISTS: $zip" >&2
  exit 3
fi
staging="$output/.$name.partial.zip"
if [[ -e "$staging" || -L "$staging" ]]; then
  echo "PARTIAL_EXPORT_ALREADY_EXISTS: $staging" >&2
  exit 3
fi
trap 'rm -f -- "$staging"' EXIT
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$app" "$staging"
/usr/bin/unzip -tq "$staging" >/dev/null
mv "$staging" "$zip"
trap - EXIT

/usr/bin/shasum -a 256 "$zip" > "$zip.sha256"
cat > "$output/$name.README.txt" <<EOF
TwinConnect macOS unsigned debug export
Source commit: $commit
Host architecture: $macarch
Built application: $(basename "$app")
Archive: $(basename "$zip")
Engine binaries: sing-box and Xray
Status: UNSIGNED DEBUG, LOCAL SOCKS/HTTP PROXY ONLY
NOT a working system-wide VPN; Apple Network Extension signing is unavailable.
Do not claim internet traffic is tunneled unless verified via SOCKS egress.
No installer signing, notarization or Gatekeeper bypass is provided.
Keep the archive and SHA256 file off the expiring VPS.
EOF
printf '%s\n' "$commit" > "$output/$name.commit.txt"
printf 'MACOS_UNSIGNED_EXPORT_SUCCEEDED\nArchive: %s\nSHA256: %s\nREADME: %s\n' \
  "$zip" "$zip.sha256" "$output/$name.README.txt"