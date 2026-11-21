#!/usr/bin/env bash
# OFFLINE package of unsigned local SOCKS/HTTP runtime. No VPN or routing.
# Usage: bash tool/package_macos_local_proxy_runtime.sh /absolute/path/Runner.app
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" ]]; then echo "MACOS_ONLY" >&2; exit 2; fi
if [[ $# -ne 1 ]]; then echo "USAGE: supply absolute Runner.app path" >&2; exit 2; fi
app="$1"
if [[ "$app" != /* || "$app" != *.app || -L "$app" ||
      ! -d "$app/Contents/MacOS" || ! -d "$app/Contents/Resources" ||
      ! -f "$app/Contents/Info.plist" ]]; then
  echo "INVALID_MACOS_APP_PATH" >&2; exit 2
fi
signing="$(codesign -dv "$app" 2>&1 || true)"
if [[ "$signing" != *"code object is not signed at all"* ]]; then
  echo "SIGNED_APP_BUNDLE_REFUSED_USE_UNSIGNED_DEBUG_BUILD" >&2; exit 2
fi
destination="$app/Contents/Resources/twinconnect-runtime"
if [[ -L "$destination" || -e "$destination" ]]; then
  echo "RUNTIME_ALREADY_PRESENT_OR_SYMLINK" >&2; exit 2
fi
for source in macos_native/standalone_connection_manager.py macos_native/cisco_openconnect_auth.py; do
  if [[ ! -f "$source" || -L "$source" ]]; then
    echo "MISSING_OR_UNSAFE_RUNTIME_SOURCE: $source" >&2; exit 2
  fi
done
case "$(uname -m)" in
  x86_64) arch="amd64"; host_arch="x86_64";;
  arm64) arch="arm64"; host_arch="arm64";;
  *) echo "UNSUPPORTED_MAC_ARCHITECTURE" >&2; exit 2;;
esac
stage="$(mktemp -d -t twinconnect-runtime)"
trap 'rm -rf -- "$stage"' EXIT
mkdir -p "$stage/macos_native/build"
install -m 0755 macos_native/standalone_connection_manager.py \
  "$stage/macos_native/standalone_connection_manager.py"
install -m 0755 macos_native/cisco_openconnect_auth.py \
  "$stage/macos_native/cisco_openconnect_auth.py"
installed=0
for family in singbox xray; do
  if [[ "$family" == "singbox" ]]; then binary="sing-box"; else binary="xray"; fi
  source="macos_native/build/$family/$arch/$binary"
  if [[ -L "$source" ]]; then
    echo "UNSAFE_ENGINE_SYMLINK: $source" >&2; exit 2
  fi
  if [[ ! -f "$source" || ! -x "$source" ]]; then
    echo "ENGINE_SKIPPED_NOT_INSTALLED: $family/$arch/$binary"
    continue
  fi
  if ! /usr/bin/lipo -archs "$source" 2>/dev/null | tr ' ' '\n' |
       grep -Fxq "$host_arch"; then
    echo "ENGINE_ARCHITECTURE_MISMATCH: $source" >&2; exit 2
  fi
  mkdir -p "$stage/macos_native/build/$family/$arch"
  install -m 0755 "$source" "$stage/macos_native/build/$family/$arch/$binary"
  echo "ENGINE_PACKAGED: $family/$arch/$binary"
  installed=$((installed + 1))
done
if [[ "$installed" -eq 0 ]]; then
  echo "NO_LOCAL_PROXY_ENGINES_INSTALLED; BUNDLE_NOT_MODIFIED" >&2; exit 3
fi
mv "$stage" "$destination"
trap - EXIT
echo "MACOS_LOCAL_PROXY_RUNTIME_PACKAGED"
echo "Runtime: $destination"
echo "Engines: $installed"
echo "LOCAL_PROXY_ONLY; NO_SYSTEM_WIDE_VPN; UNSIGNED_BUILD"
