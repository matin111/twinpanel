#!/usr/bin/env bash
# Install independent WireGuard management pin watchdog; no VPN or routes altered.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "${EUID}" == 0 ]] ||
  { echo "WG_MACOS_ROOT_REQUIRED" >&2; exit 2; }
helper="/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py"
plist="/Library/LaunchDaemons/com.twinconnect.wireguard-management-route-guard.plist"
install -d -o root -g wheel -m 0755 "$(dirname "$helper")"
if [[ -f "$helper" ]] && /usr/bin/python3 "$helper" status 2>/dev/null | /usr/bin/grep -q WG_SYSTEM_IPV4_CONNECTED; then
  echo "WG_ACTIVE_GUARD_REINSTALL_REFUSED" >&2; exit 2
fi
install -o root -g wheel -m 0755 \
  macos_native/wireguard_management_route_guard.py "$helper"
/usr/bin/python3 -m py_compile "$helper"
cat > "$plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.twinconnect.wireguard-management-route-guard</string>
<key>ProgramArguments</key><array>
<string>/usr/bin/python3</string>
<string>/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py</string>
<string>service</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
</dict></plist>
PLIST
chown root:wheel "$plist"
chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist"
if /bin/launchctl print system/com.twinconnect.wireguard-management-route-guard \
    >/dev/null 2>&1; then
  /bin/launchctl bootout system/com.twinconnect.wireguard-management-route-guard
fi
/bin/launchctl bootstrap system "$plist"
/bin/launchctl kickstart -k system/com.twinconnect.wireguard-management-route-guard
/bin/sleep 1
/bin/launchctl print system/com.twinconnect.wireguard-management-route-guard |
  /usr/bin/grep 'state = running'
/usr/bin/python3 "$helper" status
echo "WG_MANAGEMENT_WATCHDOG_INSTALLED; NO_NETWORK_ROUTE_CHANGED"
