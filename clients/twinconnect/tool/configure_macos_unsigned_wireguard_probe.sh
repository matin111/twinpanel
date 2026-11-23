#!/usr/bin/env bash
# Install root-owned unsigned WireGuard and fixed sudo commands.
# No default routes, DNS, network settings or other VPNs are modified here.
set -euo pipefail
[[ "$(uname -s)" == Darwin && "$EUID" -eq 0 ]] || {
  echo "WG_MACOS_ROOT_REQUIRED" >&2; exit 2
}
cd "$(dirname "$0")/.."
base="/Library/PrivilegedHelperTools/TwinConnectWireGuard"
src="macos_native/build/wireguard-userspace/amd64/wireguard-go"
if [[ "$(uname -m)" == arm64 ]]; then
  src="macos_native/build/wireguard-userspace/arm64/wireguard-go"
fi
[[ -f "$src" && ! -L "$src" && -x "$src" ]] || {
  echo "WG_UNSIGNED_DAEMON_NOT_BUILT" >&2; exit 2
}
"$src" --version | /usr/bin/grep -q '^wireguard-go' || {
  echo "WG_UNSIGNED_DAEMON_INVALID" >&2; exit 2
}
/usr/bin/python3 -m py_compile macos_native/wireguard_unsigned_tunnel.py
watchdog="$base/wireguard_management_route_guard.py"
[[ -f "$watchdog" && ! -L "$watchdog" ]] || {
  echo "WG_INDEPENDENT_WATCHDOG_REQUIRED" >&2; exit 2
}
/bin/launchctl print system/com.twinconnect.wireguard-management-route-guard 2>/dev/null |
  /usr/bin/grep -q 'state = running' || {
  echo "WG_WATCHDOG_NOT_RUNNING" >&2; exit 2
}
[[ "$(/usr/bin/python3 "$watchdog" status)" == WG_MANAGEMENT_PIN_IDLE ]] || {
  echo "WG_GUARD_ALREADY_ACTIVE" >&2; exit 2
}
if /usr/bin/pgrep -f '^/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard-go -f utun[0-9]+$' >/dev/null; then
  echo "WG_ENGINE_ACTIVE_INSTALL_REFUSED" >&2; exit 2
fi
install -d -o root -g wheel -m 0755 "$base"
install -o root -g wheel -m 0755 "$src" "$base/wireguard-go"
install -o root -g wheel -m 0755 \
  macos_native/wireguard_unsigned_tunnel.py "$base/wireguard_unsigned_tunnel.py"
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-wireguard.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
printf '%s\n' \
  'macvps ALL=(root) NOPASSWD: /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_unsigned_tunnel.py system, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_unsigned_tunnel.py probe, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py status, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py status-uptime, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py stop' > "$tmp"
chown root:wheel "$tmp"
chmod 0440 "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" /private/etc/sudoers.d/twinconnect-wireguard
/usr/sbin/visudo -cf /private/etc/sudoers.d/twinconnect-wireguard >/dev/null
echo "WG_UNSIGNED_GUARDED_SYSTEM_VPN_INSTALLED; NO_NETWORK_CHANGE_PERFORMED"
