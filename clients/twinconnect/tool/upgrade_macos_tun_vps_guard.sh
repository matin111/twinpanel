#!/usr/bin/env bash
# Upgrade paused root-owned TUN controller to fail-closed VPS management bypass.
# NO VPN starts and NO networking is changed by this installer.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(id -u)" == 0 ]] || {
  echo "ROOT_MACOS_REQUIRED" >&2; exit 2;
}
[[ -t 0 && -t 1 && -z "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]] || {
  echo "INDEPENDENT_PROVIDER_VNC_REQUIRED" >&2; exit 2;
}
admin="${SUDO_USER:-}"
[[ "$admin" =~ ^[a-z_][a-z0-9_-]*$ && "$admin" != root &&
   "$(stat -f '%Su' /dev/console)" == "$admin" ]] || {
  echo "CONSOLE_OWNER_MISMATCH" >&2; exit 2;
}
root="/Library/PrivilegedHelperTools/TwinConnectTUN"
label="system/com.twinconnect.localtun"
plist="/Library/LaunchDaemons/com.twinconnect.localtun.plist"
for file in unsigned_tun_daemon.py tun_vps_management_guard.py; do
  [[ -f "macos_native/$file" && ! -L "macos_native/$file" ]] || {
    echo "LOCAL_SOURCE_NOT_TRUSTED" >&2; exit 3;
  }
  /usr/bin/python3 -m py_compile "macos_native/$file"
done
for f in "$root" "$root/unsigned_tun_daemon.py" "$root/local-console-approval" "$plist"; do
  [[ -e "$f" && ! -L "$f" && "$(stat -f '%u' "$f")" == 0 ]] || {
    echo "ROOT_OWNED_RUNTIME_REQUIRED" >&2; exit 3;
  }
done
[[ "$(cat "$root/local-console-approval")" == VPS_OOB_CONSOLE_45_SECONDS ]] || {
  echo "VPS_TRIAL_MODE_NOT_ENABLED" >&2; exit 3;
}
[[ ! -e "$root/tun_vps_management_guard.py" && ! -L "$root/tun_vps_management_guard.py" ]] || {
  echo "GUARD_ALREADY_INSTALLED; REFUSING_UNREVIEWED_REPLACEMENT" >&2; exit 3;
}
# No engine may be running when replacing the controller.
if /usr/bin/pgrep -fl '[s]ing-box run' >/dev/null; then
  echo "ENGINE_RUNNING; STOP_VPN_BEFORE_UPGRADE" >&2; exit 3;
fi
echo "Upgrade controller to require verified remote-management exclusions."
echo "This stops and restarts only the idle controller (NOT the VPN)."
read -r -p "Type INSTALL-VPS-MANAGEMENT-GUARD: " reply
[[ "$reply" == INSTALL-VPS-MANAGEMENT-GUARD ]] || exit 2

/usr/bin/install -o root -g wheel -m 0644 macos_native/tun_vps_management_guard.py "$root/tun_vps_management_guard.py"
backup="$root/unsigned_tun_daemon.py.before-vps-guard-$(date +%Y%m%d%H%M%S)"
/usr/bin/install -o root -g wheel -m 0644 "$root/unsigned_tun_daemon.py" "$backup"
/usr/bin/install -o root -g wheel -m 0644 macos_native/unsigned_tun_daemon.py "$root/.daemon-upgrade"
/bin/mv -f "$root/.daemon-upgrade" "$root/unsigned_tun_daemon.py"
/bin/launchctl bootout "$label" 2>/dev/null || true
# launchd requires asynchronous teardown before bootstrap; avoid error 37.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if ! /bin/launchctl print "$label" >/dev/null 2>&1; then break; fi
  /bin/sleep 1
done
if /bin/launchctl print "$label" >/dev/null 2>&1; then
  echo "PREVIOUS_CONTROLLER_STILL_REMOVING; DO_NOT_BOOTSTRAP" >&2; exit 4;
fi
/bin/launchctl bootstrap system "$plist"
/bin/sleep 1
/usr/bin/python3 macos_native/unsigned_tun_client.py status
echo "VPS_MANAGEMENT_GUARD_INSTALLED; CONTROLLER_ONLY; ROUTES_UNCHANGED"