#!/usr/bin/env bash
# Export the already built unsigned Release candidate. No network/root actions.
# The app still requires separately installed, compatible native helpers.
set -euo pipefail
[[ "$(uname -s)" == Darwin && $# -eq 2 ]] || { echo "USAGE: $0 /absolute/Release/twinconnect.app /absolute/export-directory"; exit 2; }
app="$1"
out="$2"
[[ "$app" = /*/Release/*.app && "$out" = /* && -d "$app" && ! -L "$app" && ! -L "$out" ]] ||
  { echo INVALID_RELEASE_EXPORT_PATH; exit 2; }
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")" = com.twinpanel.twinconnect
test -s "$app/Contents/Resources/AppIcon.icns"
if /usr/bin/codesign -dv "$app" >/dev/null 2>&1; then echo SIGNED_BUNDLE_REFUSED; exit 2; fi
if [[ -n "$(find "$app" -name kernel_blob.bin -print -quit)" ]]; then echo DEBUG_FLUTTER_PAYLOAD_REFUSED; exit 3; fi
case "$(uname -m)" in x86_64) arch=amd64; mach=x86_64;; arm64) arch=arm64; mach=arm64;; *) exit 2;; esac
build="$app/Contents/Resources/twinconnect-runtime/macos_native/build"
for spec in "singbox/$arch/sing-box" "mbox/$arch/sing-box" "xray/$arch/xray" \
 "sudoku/$arch/sudoku" "trusttunnel/$arch/trusttunnel_client" \
 "openvpn/$arch/bin/openvpn" "wireguard-userspace/$arch/wireguard-go" \
 "amneziawg/$arch/amneziawg-go" "amneziawg/$arch/awg" "l2tp/$arch/twinconnect-l2tp-native"; do
  test -x "$build/$spec" || { echo "REQUIRED_ENGINE_MISSING: $spec"; exit 3; }
  /usr/bin/lipo -archs "$build/$spec" | tr ' ' '\n' | grep -Fxq "$mach" || { echo "ENGINE_ARCH_MISMATCH: $spec"; exit 3; }
done
mkdir -p "$out"
name="TwinConnect-macOS-$mach-unsigned-release-candidate-$(date +%Y%m%d-%H%M%S)"
archive="$out/$name.zip"
staging="$out/.$name.partial.zip"
test ! -e "$archive" && test ! -e "$staging"
/usr/bin/ditto -c -k --zlibCompressionLevel 9 --sequesterRsrc --keepParent "$app" "$staging"
/usr/bin/unzip -tq "$staging" >/dev/null
mv "$staging" "$archive"
/usr/bin/shasum -a 256 "$archive" > "$archive.sha256"
cat > "$out/$name.README.txt" <<'EOF'
TwinConnect macOS unsigned Release candidate
This archive preserves the packaged engines; it is not a notarized installer.
System-wide VPN and Kill Switch depend on separately installed privileged
helpers, including Cisco/OpenConnect and native route/firewall controllers.
Fresh-machine installation and full live per-protocol acceptance are pending.
Do not distribute as a verified production release.
EOF
printf 'ARCHIVE_BYTES: '; /usr/bin/stat -f %z "$archive"
printf 'APP_DISK_SIZE: '; /usr/bin/du -sh "$app"
printf 'RELEASE_CANDIDATE_ARCHIVE: %s\n' "$archive"
