#!/usr/bin/env bash
# Repairs macOS's Python 3.9 peer UID handling. Service controller only:
# requires no active session and never launches a VPN profile or changes routes.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(id -u)" == 0 ]] || {
  echo "MACOS_ROOT_REQUIRED" >&2; exit 2;
}
[[ -t 0 && -t 1 ]] || { echo "PROVIDER_VNC_CONSOLE_REQUIRED" >&2; exit 2; }
[[ -z "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]] || {
  echo "REMOTE_SSH_REFUSED" >&2; exit 2;
}
admin="${SUDO_USER:-}"
[[ "$admin" =~ ^[a-z_][a-z0-9_-]*$ && "$admin" != root &&
  "$(stat -f '%Su' /dev/console)" == "$admin" ]] || {
  echo "CONSOLE_OWNER_MISMATCH" >&2; exit 2;
}
root="/Library/PrivilegedHelperTools/TwinConnectTUN"
target="$root/unsigned_tun_daemon.py"
source="macos_native/unsigned_tun_daemon.py"
label="system/com.twinconnect.localtun"
[[ -f "$target" && ! -L "$target" && "$(stat -f '%u' "$target")" == 0 &&
  -f "$source" && ! -L "$source" && -f "$root/local-console-approval" &&
  ! -L "$root/local-console-approval" &&
  -f /Library/LaunchDaemons/com.twinconnect.localtun.plist ]] || {
  echo "EXPECTED_TRUSTED_RUNTIME_NOT_FOUND" >&2; exit 3;
}
[[ "$(cat "$root/local-console-approval")" == VPS_OOB_CONSOLE_45_SECONDS ]] || {
  echo "VPS_BOUNDED_APPROVAL_MISSING" >&2; exit 3;
}
grep -Fq 'def unix_peer_uid(' "$source"
grep -Fq 'VPS_SESSION = 45' "$source"
/usr/bin/python3 -m py_compile "$source"
# Never swap the daemon while an engine could be running.
[[ -S /var/run/twinconnect-tun.sock ]] || {
  echo "ACTIVE_CONTROLLER_SOCKET_REQUIRED" >&2; exit 3;
}
status="$(/usr/bin/python3 macos_native/unsigned_tun_client.py status 2>/dev/null || true)"
[[ "$status" != *'engine_running_unverified'* ]] || {
  echo "ENGINE_RUNNING; REFUSING_CONTROLLER_RESTART" >&2; exit 3;
}
if /usr/bin/pgrep -fl '[s]ing-box run' >/dev/null; then
  echo "SING_BOX_ENGINE_PRESENT; REFUSING_CONTROLLER_RESTART" >&2; exit 3;
fi
echo "Replacing only controller Python. NO VPN will be started."
read -r -p "Type REPAIR-TUN-PEER-AUTH: " reply
[[ "$reply" == REPAIR-TUN-PEER-AUTH ]] || exit 2
backup="$root/unsigned_tun_daemon.py.backup-$(date +%Y%m%d%H%M%S)"
/usr/bin/install -o root -g wheel -m 0644 "$target" "$backup"
tmp="$root/.new-unsigned_tun_daemon.py"
[[ ! -e "$tmp" && ! -L "$tmp" ]] || {
  echo "UNEXPECTED_TEMP_FILE" >&2; exit 3;
}
/usr/bin/install -o root -g wheel -m 0644 "$source" "$tmp"
/bin/mv -f "$tmp" "$target"
/bin/launchctl bootout "$label"
/bin/launchctl bootstrap system /Library/LaunchDaemons/com.twinconnect.localtun.plist
/bin/sleep 1
/usr/bin/python3 macos_native/unsigned_tun_client.py status || {
  echo "CONTROLLER_REQUEST_FAILED; RUNTIME_BACKUP: $backup" >&2; exit 5;
}
echo "PEER_AUTH_REPAIRED; CONTROLLER_RESPONDS; NO_VPN_STARTED; ROUTES_UNCHANGED"