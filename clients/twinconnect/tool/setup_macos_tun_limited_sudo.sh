#!/usr/bin/env bash
# One-time, provider-console-only setup of a root-owned TUN runtime and
# minimal passwordless management. NO daemon startup or network changes.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(id -u)" == 0 ]] || {
  echo "RUN_FROM_PROVIDER_CONSOLE_WITH_SUDO" >&2; exit 2;
}
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_PROVIDER_CONSOLE_REQUIRED" >&2; exit 2; }
[[ -z "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]] || {
  echo "REMOTE_SSH_REFUSED" >&2; exit 2;
}
admin="${SUDO_USER:-}"
[[ "$admin" =~ ^[a-z_][a-z0-9_-]*$ && "$admin" != root ]] || {
  echo "VALID_SUDO_USER_REQUIRED" >&2; exit 2;
}
[[ "$(stat -f '%Su' /dev/console)" == "$admin" ]] || {
  echo "CONSOLE_OWNER_MISMATCH" >&2; exit 2;
}
trusted="/Library/PrivilegedHelperTools/TwinConnectTUN"
ops="/Library/PrivilegedHelperTools/TwinConnectOps"
rule="/etc/sudoers.d/twinconnect-tun-admin"
[[ ! -e "$trusted" && ! -L "$trusted" && ! -e "$ops" && ! -L "$ops" &&
   ! -e "$rule" && ! -L "$rule" ]] || {
  echo "ALREADY_STAGED_OR_INSTALLED; REFUSING_OVERWRITE" >&2; exit 3;
}
engine="macos_native/build/singbox/amd64/sing-box"
[[ "$(uname -m)" == x86_64 ]] || { echo "X86_64_ENGINE_ONLY" >&2; exit 3; }
files=(unsigned_tun_daemon.py unsigned_tun_policy.py unsigned_tun_watchdog.py openvpn_profile_review.py tun_vps_management_guard.py)
[[ -f "$engine" && ! -L "$engine" && -x "$engine" ]] || {
  echo "SING_BOX_BINARY_NOT_READY" >&2; exit 3;
}
for file in "${files[@]}"; do
  [[ -f "macos_native/$file" && ! -L "macos_native/$file" ]] || {
    echo "SOURCE_MISSING_OR_SYMLINK: $file" >&2; exit 3;
  }
  /usr/bin/python3 -m py_compile "macos_native/$file"
done
/usr/bin/python3 -c 'import sys; assert sys.version_info >= (3, 9)'
echo "This will stage root-owned TUN files and install limited sudo for: $admin"
echo "Allowed without password: tun-admin status, tun-admin stop."
echo "It will NOT activate VPN, change default routes, DNS or firewall."
read -r -p "From independent provider VNC, type APPROVE-TUN-STAGING: " reply
[[ "$reply" == APPROVE-TUN-STAGING ]] || { echo "NOT_APPROVED" >&2; exit 2; }

# Never use /usr/local/sbin here: this host has a user-writable /usr/local/sbin.
# Trusted root-owned installation locations are required for sudoers commands.
/usr/bin/install -d -o root -g wheel -m 0700 "$trusted"
/usr/bin/install -d -o root -g wheel -m 0755 "$ops"
/usr/bin/install -o root -g wheel -m 0755 "$engine" "$trusted/sing-box"
for file in "${files[@]}"; do
  /usr/bin/install -o root -g wheel -m 0644 "macos_native/$file" "$trusted/$file"
done
# The only commands exposed to passwordless sudo are fixed read-only status
# and service stop (NO arguments forwarded to arbitrary interpreters).
cat > "$ops/tun-admin" <<'CONTROL'
#!/bin/bash
set -euo pipefail
[[ "$#" == 1 ]] || exit 2
case "$1" in
 status)
   if [[ -S /var/run/twinconnect-tun.sock ]]; then
      echo "TUN_SOCKET_PRESENT"
   else
      echo "TUN_SOCKET_ABSENT"
   fi
   if [[ -f /Library/PrivilegedHelperTools/TwinConnectTUN/unsigned_tun_daemon.py ]]; then
      echo "TUN_FILES_STAGED"
   else
      echo "TUN_FILES_MISSING"
   fi
   /bin/launchctl print system/com.twinconnect.localtun 2>/dev/null |
     /usr/bin/grep -E 'state =|pid =' || true
   ;;
 stop)
   /bin/launchctl bootout system/com.twinconnect.localtun 2>/dev/null || true
   echo "TUN_SERVICE_STOP_REQUESTED"
   ;;
 *) echo "ALLOWED: status or stop" >&2; exit 2;;
esac
CONTROL
/usr/sbin/chown root:wheel "$ops/tun-admin"
/bin/chmod 0755 "$ops/tun-admin"
test "$(/usr/bin/stat -f '%u' "$ops/tun-admin")" = 0
tmp="$(/usr/bin/mktemp /etc/sudoers.d/.twinconnect-XXXXXX)"
trap '/bin/rm -f "$tmp"' EXIT
/bin/chmod 0600 "$tmp"
{
  printf '%s ALL=(root) NOPASSWD: %s status, %s stop\n' "$admin" "$ops/tun-admin" "$ops/tun-admin"
} > "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
/usr/bin/install -o root -g wheel -m 0440 "$tmp" "$rule"
/usr/sbin/visudo -cf /etc/sudoers >/dev/null
echo "TUN_FILES_STAGED; LIMITED_SUDO_ENABLED; DAEMON_NOT_STARTED; ROUTES_UNCHANGED"