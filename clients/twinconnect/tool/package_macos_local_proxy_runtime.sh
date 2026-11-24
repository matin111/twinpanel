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
for source in macos_native/standalone_connection_manager.py macos_native/cisco_openconnect_auth.py macos_native/unsigned_tun_client.py macos_native/unsigned_tun_telemetry.py macos_native/unsigned_tun_policy.py macos_native/unsigned_mieru_profile.py macos_native/unsigned_trusttunnel_profile.py macos_native/unsigned_sudoku_profile.py macos_native/xray_unsigned_tun_candidate.py macos_native/l2tp_native_preflight.py macos_native/openvpn_profile_review.py macos_native/openvpn_traffic_telemetry.py; do
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
install -m 0755 macos_native/unsigned_tun_telemetry.py \
  "$stage/macos_native/unsigned_tun_telemetry.py"
install -m 0644 macos_native/unsigned_tun_policy.py \
  "$stage/macos_native/unsigned_tun_policy.py"
install -m 0755 macos_native/unsigned_mieru_profile.py   "$stage/macos_native/unsigned_mieru_profile.py"
install -m 0755 macos_native/unsigned_trusttunnel_profile.py   "$stage/macos_native/unsigned_trusttunnel_profile.py"
install -m 0644 macos_native/unsigned_sudoku_profile.py "$stage/macos_native/unsigned_sudoku_profile.py"
install -m 0755 macos_native/xray_unsigned_tun_candidate.py \
  "$stage/macos_native/xray_unsigned_tun_candidate.py"
install -m 0755 macos_native/l2tp_native_preflight.py \
  "$stage/macos_native/l2tp_native_preflight.py"
install -m 0644 macos_native/openvpn_profile_review.py \
  "$stage/macos_native/openvpn_profile_review.py"
install -m 0644 macos_native/openvpn_traffic_telemetry.py \
  "$stage/macos_native/openvpn_traffic_telemetry.py"
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
# Optional separate Mieru-enabled mbox engine; no privileged execution.
mbox_source="macos_native/build/mbox/$arch/sing-box"
if [[ -f "$mbox_source" && ! -L "$mbox_source" && -x "$mbox_source" ]]; then
  mkdir -p "$stage/macos_native/build/mbox/$arch"
  install -m 0755 "$mbox_source"       "$stage/macos_native/build/mbox/$arch/sing-box"
  echo "MIERU_MBOX_ENGINE_PACKAGED"
fi
# Official TrustTunnel CLI is an unprivileged, optional loopback-only test
# engine. Do not route macOS system traffic through it until HTTPS proof works.
sudoku_source="macos_native/build/sudoku/$arch/sudoku"
if [[ -e "$sudoku_source" ]]; then
  [[ -f "$sudoku_source" && ! -L "$sudoku_source" && -x "$sudoku_source" ]] ||
    { echo "SUDOKU_ENGINE_INVALID" >&2; exit 3; }
  /usr/bin/lipo -archs "$sudoku_source" | tr ' ' '\n' | grep -Fxq "$host_arch" ||
    { echo "SUDOKU_ARCH_MISMATCH" >&2; exit 3; }
  mkdir -p "$stage/macos_native/build/sudoku/$arch"
  install -m 0755 "$sudoku_source" "$stage/macos_native/build/sudoku/$arch/sudoku"
  install -m 0644 licenses/SUDOKU-LICENSE.txt "$stage/macos_native/build/sudoku/$arch/LICENSE.txt"
  install -m 0644 licenses/GPL-3.0.txt "$stage/macos_native/build/sudoku/$arch/GPL-3.0.txt"
  echo "SUDOKU_OFFICIAL_CORE_PACKAGED"
fi
trust_source="macos_native/build/trusttunnel/$arch/trusttunnel_client"
if [[ -f "$trust_source" && ! -L "$trust_source" && -x "$trust_source" ]]; then
  /usr/bin/lipo -archs "$trust_source" | tr ' ' '\n' |
    grep -Fxq "$host_arch" || {
      echo "TRUSTTUNNEL_ENGINE_ARCH_MISMATCH" >&2; exit 2;
    }
  mkdir -p "$stage/macos_native/build/trusttunnel/$arch"
  install -m 0755 "$trust_source"     "$stage/macos_native/build/trusttunnel/$arch/trusttunnel_client"
  echo "TRUSTTUNNEL_LOCAL_ONLY_CLIENT_PACKAGED"
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
  helper_parent="$(dirname "$helper_build")"
  mkdir -p "$helper_parent"
  if [[ -L "$helper_build" || ( -e "$helper_build" && ! -d "$helper_build" ) ]]; then
    echo "UNSAFE_OPENVPN_HELPER_BUILD_PATH" >&2; exit 3
  fi
  helper_source="$stage/macos_native/build/openvpn/$arch"
  if [[ -d "$helper_build" ]] &&
     /usr/bin/diff -qr "$helper_source" "$helper_build" >/dev/null 2>&1; then
    echo "OPENVPN_HELPER_BUILD_CURRENT"
  else
    # Prepare a complete candidate in the same filesystem. Keep the previous
    # version until replacement is ready; recover it if the final rename fails.
    helper_next="$(mktemp -d "$helper_parent/.openvpn-next.XXXXXXXX")"
    if ! cp -R "$helper_source/." "$helper_next/"; then
      rm -rf -- "$helper_next"
      echo "OPENVPN_HELPER_STAGING_FAILED" >&2; exit 3
    fi
    helper_previous=""
    if [[ -d "$helper_build" ]]; then
      helper_previous="$(mktemp -d "$helper_parent/.openvpn-prev.XXXXXXXX")"
      rmdir "$helper_previous"
      if ! mv "$helper_build" "$helper_previous"; then
        rm -rf -- "$helper_next"
        echo "OPENVPN_HELPER_BACKUP_FAILED" >&2; exit 3
      fi
    fi
    if ! mv "$helper_next" "$helper_build"; then
      if [[ -n "$helper_previous" ]]; then
        mv "$helper_previous" "$helper_build" || true
      fi
      rm -rf -- "$helper_next"
      echo "OPENVPN_HELPER_REPLACE_FAILED" >&2; exit 3
    fi
    if [[ -n "$helper_previous" ]]; then rm -rf -- "$helper_previous"; fi
    echo "OPENVPN_HELPER_BUILD_REFRESHED"
  fi
  installed=$((installed + 1))
else
  echo "OPENVPN_CLI_NOT_INSTALLED; NOT_PACKAGED"
fi
# The unsigned WireGuard userspace daemon is packaged as an ENGINE ONLY.
# It never starts here, and this packaging must not alter the system network.
# The official AmneziaWG engine and tools are a separate optional pair.
awg_dir="macos_native/build/amneziawg/$arch"
if [[ -e "$awg_dir/amneziawg-go" || -e "$awg_dir/awg" ]]; then
  mkdir -p "$stage/macos_native/build/amneziawg/$arch"
  for name in amneziawg-go awg; do
    source="$awg_dir/$name"
    [[ -f "$source" && ! -L "$source" && -x "$source" ]] ||
      { echo "AMNEZIAWG_ENGINE_PAIR_INCOMPLETE" >&2; exit 3; }
    /usr/bin/lipo -archs "$source" | tr ' ' '\n' |
      grep -Fxq "$host_arch" ||
      { echo "AMNEZIAWG_ENGINE_ARCHITECTURE_MISMATCH" >&2; exit 3; }
    install -m 0755 "$source" "$stage/macos_native/build/amneziawg/$arch/$name"
  done
  echo "AMNEZIAWG_ENGINE_PAIR_PACKAGED"
fi
wg_source="macos_native/build/wireguard-userspace/$arch/wireguard-go"
wg_packaged=0
if [[ -f "$wg_source" && ! -L "$wg_source" && -x "$wg_source" ]]; then
  if ! /usr/bin/lipo -archs "$wg_source" 2>/dev/null |
       tr ' ' '\n' | grep -Fxq "$host_arch"; then
    echo "WIREGUARD_UNSIGNED_ARCH_MISMATCH" >&2; exit 3
  fi
  if ! "$wg_source" --version |
       grep -Fq "Userspace WireGuard daemon for darwin-$arch"; then
    echo "WIREGUARD_UNSIGNED_DAEMON_INVALID" >&2; exit 3
  fi
  mkdir -p "$stage/macos_native/build/wireguard-userspace/$arch"
  install -m 0755 "$wg_source" \
    "$stage/macos_native/build/wireguard-userspace/$arch/wireguard-go"
  wg_packaged=1
  installed=$((installed + 1))
  echo "WIREGUARD_UNSIGNED_ENGINE_PACKAGED: $arch"
else
  echo "WIREGUARD_UNSIGNED_ENGINE_NOT_BUILT; OPTIONAL_RUNTIME_NOT_PACKAGED"
fi
# Optional unsigned native macOS L2TP SystemConfiguration helper.
# This is a capability/provisioning tool, NOT an installed VPN or full route.
l2tp_source="macos_native/build/l2tp/$arch/twinconnect-l2tp-native"
if [[ -x "$l2tp_source" && ! -L "$l2tp_source" ]]; then
  /usr/bin/lipo -archs "$l2tp_source" | tr ' ' '\n' |
    grep -Fxq "$host_arch" || {
      echo "L2TP_NATIVE_ARCH_MISMATCH" >&2; exit 3
    }
  mkdir -p "$stage/macos_native/build/l2tp/$arch"
  install -m 0755 "$l2tp_source" \
    "$stage/macos_native/build/l2tp/$arch/twinconnect-l2tp-native"
  echo "L2TP_NATIVE_SERVICE_TOOL_PACKAGED: $arch"
else
  echo "L2TP_NATIVE_SERVICE_TOOL_NOT_BUILT"
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
if [[ "$wg_packaged" -eq 1 ]]; then
  test -x "$destination/macos_native/build/wireguard-userspace/$arch/wireguard-go" ||
    { echo "PACKAGED_WIREGUARD_USERSOURCE_MISSING" >&2; exit 3; }
fi
test -r "$destination/macos_native/standalone_connection_manager.py" ||
  { echo "PACKAGED_MANAGER_MISSING" >&2; exit 3; }
test -r "$destination/macos_native/xray_unsigned_tun_candidate.py" || { echo "PACKAGED_VLESS_TUN_CONVERTER_MISSING" >&2; exit 3; }
test -r "$destination/macos_native/unsigned_tun_policy.py" || { echo "PACKAGED_TUN_POLICY_MISSING" >&2; exit 3; }
echo "MACOS_LOCAL_PROXY_RUNTIME_PACKAGED"
echo "Runtime: $destination"
echo "Engines: $installed"
echo "PROXY_ENGINES_PACKAGED; OPENVPN_SYSTEM_IPV4_REQUIRES_PRIVILEGED_GUARD; UNSIGNED_NETWORK_EXTENSION"
