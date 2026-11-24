#!/usr/bin/env bash
# Unsigned, app-only architecture-specific preview installer. Does not install privileged
# services, alter networking, or claim fresh-machine VPN support.
set -euo pipefail
[[ "$(uname -s)" == Darwin && $# == 2 ]] || { echo "Usage: $0 /absolute/Release/twinconnect.app /absolute/output-directory" >&2; exit 2; }
app="$1"; out="$2"
[[ "$app" = /*/Release/*.app && "$out" = /* && -d "$app" && ! -L "$app" && ! -L "$out" ]] || exit 2
plist="$app/Contents/Info.plist"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist")" = com.twinpanel.twinconnect
case "$(/usr/bin/lipo -archs "$app/Contents/MacOS/twinconnect")" in
  x86_64) mach=x86_64; label=Intel; engine_arch=amd64 ;;
  arm64) mach=arm64; label=AppleSilicon; engine_arch=arm64 ;;
  *) echo "Expected a single-architecture Release app" >&2; exit 3 ;;
esac
runtime="$app/Contents/Resources/twinconnect-runtime/macos_native/build"
for spec in "singbox/$engine_arch/sing-box" "mbox/$engine_arch/sing-box" "xray/$engine_arch/xray" "sudoku/$engine_arch/sudoku" "trusttunnel/$engine_arch/trusttunnel_client" "openvpn/$engine_arch/bin/openvpn" "wireguard-userspace/$engine_arch/wireguard-go" "amneziawg/$engine_arch/amneziawg-go" "amneziawg/$engine_arch/awg" "l2tp/$engine_arch/twinconnect-l2tp-native"; do
  test -x "$runtime/$spec" || { echo "REQUIRED_ENGINE_MISSING: $spec" >&2; exit 3; }
  /usr/bin/lipo -archs "$runtime/$spec" | tr ' ' '\n' | grep -Fx "$mach" >/dev/null || { echo "ENGINE_ARCH_MISMATCH: $spec" >&2; exit 3; }
done
test -s "$app/Contents/Resources/AppIcon.icns"
test -z "$(find "$app" -name kernel_blob.bin -print -quit)"
version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist")"
minimum="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$plist")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$minimum" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] || exit 2
mkdir -p "$out"
name="TwinConnect-macOS-${label}-${version}-preview"
dest="$out/$name.pkg"
test ! -e "$dest"
work="$(mktemp -d "$out/.pkg-stage.XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
# Use an ordinary package payload, without preinstall/postinstall scripts.
mkdir "$work/root" "$work/resources"
/usr/bin/ditto "$app" "$work/root/TwinConnect.app"
/usr/bin/pkgbuild --analyze --root "$work/root" "$work/components.plist"
# Disable bundle relocation, so updates target /Applications/TwinConnect.app.
python3 - "$work/components.plist" <<'PY'
import plistlib,sys
p=sys.argv[1]
with open(p,"rb") as f: components=plistlib.load(f)
assert len(components)==1 and components[0]["RootRelativeBundlePath"]=="TwinConnect.app"
components[0]["BundleIsRelocatable"]=False
components[0]["BundleOverwriteAction"]="upgrade"
with open(p,"wb") as f: plistlib.dump(components,f)
PY
/usr/bin/pkgbuild --root "$work/root" --component-plist "$work/components.plist" --install-location /Applications --identifier com.twinpanel.twinconnect.preview --version "$version" --ownership recommended "$work/app.pkg"
cat > "$work/resources/Welcome.html" <<'HTML'
<html><body><h2>TwinConnect for macOS</h2><p>Architecture-specific Release preview. This installer places the app in Applications.</p><p>Unsigned test package. Privileged VPN helpers and Kill Switch services are not installed or activated by this package. Not a complete fresh-machine VPN installer.</p></body></html>
HTML
cat > "$work/Distribution.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
<title>TwinConnect</title>
<options customize="never" require-scripts="false" hostArchitectures="$mach"/>
<domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
<allowed-os-versions><os-version min="$minimum"/></allowed-os-versions>
<welcome file="Welcome.html" mime-type="text/html"/>
<choices-outline><line choice="app"/></choices-outline>
<choice id="app" visible="false"><pkg-ref id="com.twinpanel.twinconnect.preview"/></choice>
<pkg-ref id="com.twinpanel.twinconnect.preview" version="$version">app.pkg</pkg-ref>
</installer-gui-script>
XML
/usr/bin/productbuild --distribution "$work/Distribution.xml" --resources "$work/resources" --package-path "$work" "$work/result.pkg"
/usr/sbin/pkgutil --payload-files "$work/app.pkg" > "$work/payload.txt"
grep -q 'TwinConnect.app/Contents/MacOS/twinconnect' "$work/payload.txt"
grep -q 'TwinConnect.app/Contents/Resources/AppIcon.icns' "$work/payload.txt"
/usr/bin/xar -tf "$work/result.pkg" > "$work/archive-members.txt"
grep -qx Distribution "$work/archive-members.txt"
mv "$work/result.pkg" "$dest"
(cd "$out" && /usr/bin/shasum -a 256 "$name.pkg" > "$name.pkg.sha256")
printf 'INSTALLER_BYTES: '; /usr/bin/stat -f %z "$dest"
printf 'INSTALLER_PATH: %s\n' "$dest"
echo APP_ONLY_UNSIGNED_PREVIEW_NO_PRIVILEGED_HELPERS
