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
if [[ -L "$destination" ]]; then
  echo "UNSAFE_RUNTIME_SYMLINK" >&2; exit 2
fi
if [[ -e "$destination" &&
      ! -f "$destination/macos_native/standalone_connection_manager.py" ]]; then
  echo "UNRECOGNIZED_EXISTING_RUNTIME_REFUSED" >&2; exit 2
fi
for source in macos_native/standalone_connection_manager.py macos_native/cisco_openconnect_auth.py macos_native/unsigned_tun_client.py macos_native/openvpn_profile_review.py; do
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
install -m 0755 macos_native/unsigned_tun_client.py \
  "$stage/macos_native/unsigned_tun_client.py"
install -m 0644 macos_native/openvpn_profile_review.py \
  "$stage/macos_native/openvpn_profile_review.py"
installed=0
for family in singbox xray; do
  if [[ "$family" == "singbox" ]]; then binary="sing-box"; else binary="xray"; fi
  source="macos_native/build/$family/$arch/$binary"
  if [[ -L "$source" ]]; then
    echo "UNSAFE_ENGINE_SYMLINK: $source" >&2; exit 2
  fi
  if [[ ! -f "$source" || ! -x "$source" ]]; then
    echo "REQUIRED_ENGINE_NOT_INSTALLED: $family/$arch/$binary" >&2
    exit 3
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
if [[ "$installed" -ne 2 ]]; then
  echo "INCOMPLETE_LOCAL_PROXY_ENGINE_SET" >&2; exit 3
fi
# Bundle OpenVPN and its dylib closure if already installed. This ONLY
# packages an executable; it does not run a VPN or change routes. A failed
# dependency rewrite must fail packaging rather than produce a broken app.
openvpn_candidate=""
for candidate in /usr/local/opt/openvpn/sbin/openvpn /opt/homebrew/opt/openvpn/sbin/openvpn; do
  if [[ -f "$candidate" && -x "$candidate" ]]; then
    openvpn_candidate="$candidate"
    break
  fi
done
if [[ -n "$openvpn_candidate" ]]; then
  /usr/bin/python3 tool/package_macos_openvpn_cli.py \
    "$openvpn_candidate" "$stage/macos_native/build/openvpn/$arch" "$host_arch"
  # An actual load/launch smoke test, NOT just an otool dependency check.
  # --version does not start OpenVPN, touch utun, or change routes.
  "$stage/macos_native/build/openvpn/$arch/bin/openvpn" --version \
      > "$stage/macos_native/build/openvpn/$arch/version.txt" 2>&1 ||
    { echo "OPENVPN_BUNDLED_EXECUTION_FAILED" >&2; exit 3; }
  grep -q '^OpenVPN ' "$stage/macos_native/build/openvpn/$arch/version.txt" ||
    { echo "OPENVPN_BUNDLED_VERSION_INVALID" >&2; exit 3; }
  echo "OPENVPN_BUNDLED_EXECUTION_VERIFIED"
  # Keep an identical unprivileged build artifact available for subsequent
  # administrator-controlled local-console installation. No sudo here.
  helper_build="macos_native/build/openvpn/$arch"
  if [[ -e "$helper_build" || -L "$helper_build" ]]; then
    echo "OPENVPN_HELPER_BUILD_ALREADY_EXISTS; REBUILD_REFUSED" >&2
    # Packaging the app itself remains possible on repeated builds.
  else
    mkdir -p "$(dirname "$helper_build")"
    cp -R "$stage/macos_native/build/openvpn/$arch" "$helper_build"
    echo "OPENVPN_PRIVILEGED_INSTALL_CANDIDATE_PREPARED"
  fi
  installed=$((installed + 1))
else
  echo "OPENVPN_CLI_NOT_INSTALLED; NOT_PACKAGED"
fi
# Repeatable builds: replace only our own previously packaged directory.
# Keep the previous runtime as rollback until the new copy is in place.
backup=""
if [[ -d "$destination" ]]; then
  backup="$app/Contents/Resources/.twinconnect-runtime-backup"
  if [[ -e "$backup" || -L "$backup" ]]; then
    echo "RUNTIME_BACKUP_ALREADY_EXISTS" >&2; exit 3
  fi
  mv "$destination" "$backup"
fi
if ! mv "$stage" "$destination"; then
  if [[ -n "$backup" ]]; then mv "$backup" "$destination"; fi
  echo "RUNTIME_PACKAGING_FAILED" >&2
  exit 3
fi
trap - EXIT
if [[ -n "$backup" ]]; then rm -rf -- "$backup"; fi
# Offline verification: exact packaged paths and executable bits.
for family in singbox xray; do
  if [[ "$family" == "singbox" ]]; then binary="sing-box"; else binary="xray"; fi
  test -x "$destination/macos_native/build/$family/$arch/$binary" ||
    { echo "PACKAGED_ENGINE_MISSING" >&2; exit 3; }
done
if [[ -n "$openvpn_candidate" ]]; then
  test -x "$destination/macos_native/build/openvpn/$arch/bin/openvpn" ||
    { echo "PACKAGED_OPENVPN_MISSING" >&2; exit 3; }
fi
test -r "$destination/macos_native/standalone_connection_manager.py" ||
  { echo "PACKAGED_MANAGER_MISSING" >&2; exit 3; }
echo "MACOS_LOCAL_PROXY_RUNTIME_PACKAGED"
echo "Runtime: $destination"
echo "Engines: $installed"
echo "LOCAL_PROXY_ONLY; NO_SYSTEM_WIDE_VPN; UNSIGNED_BUILD"
