#!/usr/bin/env bash
# Install ONLY an independent launchd watchdog for the experimental IPv4 route
# controller. No VPN connection, route, DNS or proxy is changed.
set -euo pipefail
cd "$(dirname "$0")/.."
label="com.twinconnect.full-route-guard"
root="/Library/PrivilegedHelperTools/TwinConnectFullRouteGuard"
script="$root/macos_openvpn_full_route_guard.py"
plist="/Library/LaunchDaemons/$label.plist"
source_file="tool/macos_openvpn_full_route_guard.py"

case "${1:-}" in
  check)
    if [[ -f "$script" && -f "$plist" ]]; then
      echo "FULL_ROUTE_GUARD_FILES_PRESENT"
    else
      echo "FULL_ROUTE_GUARD_NOT_INSTALLED"
    fi
    /bin/launchctl print "system/$label" 2>/dev/null | /usr/bin/grep -E 'state =|pid =' || true
    exit 0
    ;;
  install) ;;
  *)
    echo "Usage: sudo bash tool/install_macos_full_route_guard.sh {install|check}" >&2
    exit 2
    ;;
esac

[[ "$(uname -s)" == "Darwin" && "$(id -u)" == "0" ]] || {
  echo "MACOS_ROOT_REQUIRED" >&2; exit 2;
}
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_CONSOLE_REQUIRED"; exit 2; }
[[ -f "$source_file" && ! -L "$source_file" ]] || { echo "SOURCE_MISSING"; exit 2; }
if [[ -e "$plist" || -L "$plist" || -e "$root" || -L "$root" ]]; then
  echo "ALREADY_INSTALLED_OR_PATH_EXISTS; refusing overwrite"
  exit 3
fi
/usr/bin/python3 -m py_compile "$source_file"
/usr/bin/printf '%s\n' \
  "Installs a root-owned rollback watchdog; DOES NOT touch routing." \
  "This does NOT authorize a full-tunnel test on a remotely managed Mac."
read -r -p "Type INSTALL-GUARD to continue: " reply
[[ "$reply" == "INSTALL-GUARD" ]] || { echo "NOT_APPROVED"; exit 2; }

/usr/bin/install -d -o root -g wheel -m 0755 "$root"
/usr/bin/install -o root -g wheel -m 0644 "$source_file" "$script"
/usr/bin/python3 - "$plist" "$script" "$label" <<'PY'
import os
import plistlib
import sys
path, script, label = sys.argv[1:]
plist = {
    "Label": label,
    "ProgramArguments": ["/usr/bin/python3", script, "service"],
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": "/dev/null",
    "StandardErrorPath": "/dev/null",
}
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
with os.fdopen(fd, "wb") as f:
    plistlib.dump(plist, f)
PY
/usr/sbin/chown root:wheel "$plist"
/bin/chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist"
/bin/launchctl bootstrap system "$plist"
/bin/launchctl kickstart -k "system/$label"
/bin/sleep 1
if /bin/launchctl print "system/$label" | /usr/bin/grep -q 'state = running'; then
  echo "FULL_ROUTE_ROLLBACK_WATCHDOG_RUNNING; ROUTES_UNCHANGED"
else
  echo "WATCHDOG_NOT_RUNNING; DO_NOT_START_ROUTE_TRIAL"
  exit 4
fi
