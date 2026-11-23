#!/usr/bin/env bash
# Install L2TP watchdog and unsigned, root-owned native helper.
# Never starts L2TP, removes Cisco, or modifies routes/DNS.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$EUID" -eq 0 ]] || {
  echo "L2TP_MACOS_ROOT_REQUIRED" >&2; exit 2
}
base=/Library/PrivilegedHelperTools/TwinConnectL2TP
guard="$base/l2tp_management_route_guard.py"
native="$base/twinconnect-l2tp-native"
plist=/Library/LaunchDaemons/com.twinconnect.l2tp-management-route-guard.plist
arch=amd64
[[ "$(uname -m)" == arm64 ]] && arch=arm64
source_binary="macos_native/build/l2tp/$arch/twinconnect-l2tp-native"
[[ -f "$source_binary" && -x "$source_binary" && ! -L "$source_binary" ]] || {
  echo L2TP_NATIVE_BINARY_REQUIRED >&2; exit 2
}
/usr/bin/python3 -m py_compile macos_native/l2tp_management_route_guard.py macos_native/l2tp_native_preflight.py macos_native/l2tp_native_system.py
if [[ -f "$guard" ]] && /usr/bin/python3 "$guard" status | /usr/bin/grep -q L2TP_SYSTEM_IPV4_CONNECTED; then
  echo L2TP_ACTIVE_REINSTALL_REFUSED >&2; exit 2
fi
install -d -o root -g wheel -m 0755 "$base"
install -o root -g wheel -m 0755 "$source_binary" "$native"
install -o root -g wheel -m 0755 macos_native/l2tp_management_route_guard.py "$guard"
install -o root -g wheel -m 0755 macos_native/l2tp_native_system.py "$base/l2tp_native_system.py"
install -o root -g wheel -m 0644 macos_native/l2tp_native_preflight.py "$base/l2tp_native_preflight.py"
cat > "$plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.twinconnect.l2tp-management-route-guard</string>
<key>ProgramArguments</key><array>
<string>/usr/bin/python3</string>
<string>/Library/PrivilegedHelperTools/TwinConnectL2TP/l2tp_management_route_guard.py</string>
<string>service</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>/dev/null</string>
<key>StandardErrorPath</key><string>/dev/null</string>
</dict></plist>
PLIST
chown root:wheel "$plist"
chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist" >/dev/null
if /bin/launchctl print system/com.twinconnect.l2tp-management-route-guard >/dev/null 2>&1; then
  /bin/launchctl bootout system/com.twinconnect.l2tp-management-route-guard
fi
/bin/launchctl bootstrap system "$plist"
/bin/launchctl kickstart -k system/com.twinconnect.l2tp-management-route-guard
/bin/sleep 1
/bin/launchctl print system/com.twinconnect.l2tp-management-route-guard |
  /usr/bin/grep 'state = running'
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-l2tp.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
printf '%s\n' \
  'macvps ALL=(root) NOPASSWD: /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectL2TP/l2tp_native_system.py system, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectL2TP/l2tp_management_route_guard.py status-uptime, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectL2TP/l2tp_management_route_guard.py stop' > "$tmp"
chown root:wheel "$tmp"
chmod 0440 "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" /private/etc/sudoers.d/twinconnect-l2tp
/usr/sbin/visudo -cf /private/etc/sudoers.d/twinconnect-l2tp >/dev/null
echo "L2TP_ROOT_GUARD_AND_FIXED_SUDO_INSTALLED; CISCO_UNCHANGED"
