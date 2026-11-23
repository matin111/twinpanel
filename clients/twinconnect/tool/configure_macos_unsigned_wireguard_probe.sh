#!/usr/bin/env bash
# Install unsigned WireGuard engine with watchdog-verified system IPv4 support.
# Do not touch Cisco/OpenVPN settings, DNS, network services or default routes.
set -euo pipefail
[[ "$(uname -s)" == Darwin && "$EUID" -eq 0 ]] || {
  echo "WG_MACOS_ROOT_REQUIRED" >&2; exit 2
}
cd "$(dirname "$0")/.."
base=/Library/PrivilegedHelperTools/TwinConnectWireGuard
src="macos_native/build/wireguard-userspace/amd64/wireguard-go"
[[ "$(uname -m)" == arm64 ]] &&
  src="macos_native/build/wireguard-userspace/arm64/wireguard-go"
[[ -f "$src" && ! -L "$src" && -x "$src" ]] || {
  echo "WG_ENGINE_NOT_BUILT" >&2; exit 2
}
if ! "$src" --version | grep -q '^wireguard-go'; then
  echo "WG_ENGINE_INVALID" >&2; exit 2
fi
/usr/bin/python3 -m py_compile macos_native/wireguard_unsigned_tunnel.py
install -d -o root -g wheel -m 0755 "$base"
# Do not overwrite a helper while its process is still running.
if /usr/bin/pgrep -f '/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_unsigned_tunnel.py (probe|system)
  echo "WG_HELPER_ACTIVE_INSTALL_REFUSED" >&2; exit 2
fi
watchdog="$base/wireguard_management_route_guard.py"
if [[ ! -f "$watchdog" ]] || ! /bin/launchctl print   system/com.twinconnect.wireguard-management-route-guard 2>/dev/null |
  /usr/bin/grep -q 'state = running'; then
  echo "WG_INDEPENDENT_WATCHDOG_REQUIRED" >&2; exit 2
fi
if [[ "$(/usr/bin/python3 "$watchdog" status)" != WG_MANAGEMENT_PIN_IDLE ]]; then
  echo "WG_GUARD_ACTIVE_INSTALL_REFUSED" >&2; exit 2
fi
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
 >/dev/null; then
  echo "WG_HELPER_ACTIVE_INSTALL_REFUSED" >&2; exit 2
fi
install -o root -g wheel -m 0755 "$src" "$base/wireguard-go"
install -o root -g wheel -m 0755 \
  macos_native/wireguard_unsigned_tunnel.py "$base/wireguard_unsigned_tunnel.py"
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-wireguard.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
printf '%s\n' \
  'macvps ALL=(root) NOPASSWD: /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_unsigned_tunnel.py probe' > "$tmp"
chown root:wheel "$tmp"
chmod 0440 "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" /private/etc/sudoers.d/twinconnect-wireguard
/usr/sbin/visudo -cf /private/etc/sudoers.d/twinconnect-wireguard >/dev/null
echo "WG_UNSIGNED_HANDSHAKE_PROBE_INSTALLED; NO_SYSTEM_ROUTING_CHANGED"
