#!/usr/bin/env bash
# Update ONLY the error-code reply of the bounded VPS controller.
# Never starts an engine or modifies routes. Requires independent console.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(id -u)" == 0 ]] || {
  echo "ROOT_MACOS_REQUIRED" >&2; exit 2;
}
[[ -t 0 && -t 1 && -z "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]] || {
  echo "PROVIDER_VNC_CONSOLE_REQUIRED" >&2; exit 2;
}
admin="${SUDO_USER:-}"
[[ "$admin" =~ ^[a-z_][a-z0-9_-]*$ && "$admin" != root &&
   "$(stat -f '%Su' /dev/console)" == "$admin" ]] || {
  echo "CONSOLE_OWNER_MISMATCH" >&2; exit 2;
}
root="/Library/PrivilegedHelperTools/TwinConnectTUN"
target="$root/unsigned_tun_daemon.py"
source="macos_native/unsigned_tun_daemon.py"
plist="/Library/LaunchDaemons/com.twinconnect.localtun.plist"
label="system/com.twinconnect.localtun"
for item in "$root" "$target" "$root/local-console-approval" "$root/tun_vps_management_guard.py" "$plist"; do
  [[ -e "$item" && ! -L "$item" && "$(stat -f '%u' "$item")" == 0 ]] || {
    echo "TRUSTED_VPS_RUNTIME_REQUIRED" >&2; exit 3;
  }
done
[[ "$(cat "$root/local-console-approval")" == "VPS_OOB_CONSOLE_45_SECONDS" ]] || {
  echo "BOUNDED_VPS_APPROVAL_REQUIRED" >&2; exit 3;
}
grep -Fq 'VPS_SESSION = 45' "$source"
grep -Fq '"reason": safe' "$source"
grep -Fq 'from tun_vps_management_guard import guard_candidate' "$source"
/usr/bin/python3 -m py_compile "$source"
if /usr/bin/pgrep -fl '[s]ing-box run' >/dev/null; then
  echo "VPN_ENGINE_RUNNING; REFUSE_DAEMON_RESTART" >&2; exit 3;
fi
echo "Repair controller error codes only. NO VPN or network changes."
read -r -p "Type INSTALL-TUN-ERROR-CODES: " reply
[[ "$reply" == INSTALL-TUN-ERROR-CODES ]] || exit 2
backup="$root/unsigned_tun_daemon.py.pre-errors-$(date +%Y%m%d%H%M%S)"
/usr/bin/install -o root -g wheel -m 0644 "$target" "$backup"
/usr/bin/install -o root -g wheel -m 0644 "$source" "$root/.unsigned-tun-diagnostics.new"
/bin/mv -f "$root/.unsigned-tun-diagnostics.new" "$target"
/bin/launchctl bootout "$label" 2>/dev/null || true
for i in 1 2 3 4 5 6 7 8 9 10; do
  if ! /bin/launchctl print "$label" >/dev/null 2>&1; then break; fi
  /bin/sleep 1
done
if /bin/launchctl print "$label" >/dev/null 2>&1; then
  echo "LAUNCHD_PREVIOUS_CONTROLLER_BUSY" >&2; exit 4;
fi
/bin/launchctl bootstrap system "$plist"
/bin/sleep 1
/usr/bin/python3 macos_native/unsigned_tun_client.py status
echo "TUN_ERROR_CODES_INSTALLED; NO_VPN_STARTED; ROUTES_UNCHANGED"