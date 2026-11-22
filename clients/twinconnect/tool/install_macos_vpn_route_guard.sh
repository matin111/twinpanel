#!/bin/bash
# Independent recovery daemon for scoped macOS VPN routing experiments.
# Installing this DOES NOT create/alter any route or network settings.
set -euo pipefail
cd "$(dirname "$0")/.."
root="/Library/PrivilegedHelperTools/TwinConnectRouteGuard"
script="$root/macos_vpn_route_guard.py"
plist="/Library/LaunchDaemons/com.twinconnect.route-guard.plist"
label="com.twinconnect.route-guard"
case "${1:-}" in
 check)
   test -f "$script" && echo "ROUTE_GUARD_SCRIPT_STAGED" || echo "ROUTE_GUARD_NOT_STAGED"
   /bin/launchctl print "system/$label" >/dev/null 2>&1 &&
     echo "ROUTE_GUARD_DAEMON_LOADED" || echo "ROUTE_GUARD_DAEMON_NOT_LOADED"
   exit 0;;
 install) ;;
 *) echo "Usage: bash tool/install_macos_vpn_route_guard.sh {check|install}" >&2; exit 2;;
esac
[[ "$(uname -s)" == "Darwin" ]] || exit 2
[[ "$(id -u)" == "0" && -t 0 && -t 1 ]] || { echo "INTERACTIVE_ROOT_REQUIRED"; exit 2; }
[[ ! -L "$root" && ! -L "$plist" ]] || { echo "SYMLINK_REFUSED"; exit 3; }
if [[ -e "$root" || -e "$plist" ]]; then
 echo "ALREADY_INSTALLED_OR_PARTIAL: do not overwrite recovery daemon" >&2
 exit 3
fi
echo "Install independent auto-rollback daemon? It will NOT alter routes now."
read -r -p "Type INSTALL-ROUTE-GUARD: " agreed
[[ "$agreed" == "INSTALL-ROUTE-GUARD" ]] || exit 2
/usr/bin/python3 -m py_compile tool/macos_vpn_route_guard.py
/bin/mkdir -m 0755 "$root"
/usr/sbin/chown root:wheel "$root"
/usr/bin/install -o root -g wheel -m 0644 tool/macos_vpn_route_guard.py "$script"
cat > "$plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.twinconnect.route-guard</string>
<key>ProgramArguments</key><array>
<string>/usr/bin/python3</string>
<string>/Library/PrivilegedHelperTools/TwinConnectRouteGuard/macos_vpn_route_guard.py</string>
<string>service</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>/dev/null</string>
<key>StandardErrorPath</key><string>/dev/null</string>
</dict></plist>
PLIST
/usr/sbin/chown root:wheel "$plist"
/bin/chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist"
/bin/launchctl bootstrap system "$plist"
/bin/launchctl print "system/$label" >/dev/null || { echo "ROUTE_GUARD_FAILED"; exit 3; }
echo "ROUTE_GUARD_LOADED; NO_NETWORK_CHANGES"
