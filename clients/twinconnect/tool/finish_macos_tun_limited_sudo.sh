#!/usr/bin/env bash
# Recover ONLY the known partial setup (after the missing chown error).
# No VPN, service activation, route, DNS or firewall changes.
set -euo pipefail
[[ "$(uname -s)" == Darwin && "$(id -u)" == 0 ]] || {
  echo "MACOS_ROOT_REQUIRED" >&2; exit 2;
}
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_PROVIDER_CONSOLE_REQUIRED" >&2; exit 2; }
[[ -z "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]] || {
  echo "REMOTE_SSH_REFUSED" >&2; exit 2;
}
admin="${SUDO_USER:-}"
[[ "$admin" =~ ^[a-z_][a-z0-9_-]*$ && "$admin" != root &&
   "$(stat -f '%Su' /dev/console)" == "$admin" ]] || {
  echo "CONSOLE_OWNER_MISMATCH" >&2; exit 2;
}
trusted="/Library/PrivilegedHelperTools/TwinConnectTUN"
ops="/Library/PrivilegedHelperTools/TwinConnectOps"
control="$ops/tun-admin"
rule="/etc/sudoers.d/twinconnect-tun-admin"
[[ -d "$trusted" && -d "$ops" && -f "$control" && ! -L "$control" &&
   ! -e "$rule" && ! -L "$rule" ]] || {
  echo "EXPECTED_PARTIAL_SETUP_NOT_FOUND_OR_ALREADY_FINISHED" >&2; exit 3;
}
for path in "$trusted" "$ops" "$control"; do
  [[ ! -L "$path" && "$(stat -f '%u' "$path")" == 0 ]] || {
    echo "UNTRUSTED_INSTALL_PATH" >&2; exit 3;
  }
done
# Assert the exact staged program content and reject unexpected replacements.
expected="/Library/PrivilegedHelperTools/TwinConnectOps"
[[ "$expected" == "$ops" ]] || exit 3
/usr/bin/grep -Fq 'case "$1" in' "$control" || {
  echo "UNEXPECTED_MANAGEMENT_PROGRAM" >&2; exit 3;
}
for f in sing-box unsigned_tun_daemon.py unsigned_tun_policy.py unsigned_tun_watchdog.py openvpn_profile_review.py; do
  [[ -f "$trusted/$f" && ! -L "$trusted/$f" &&
     "$(stat -f '%u' "$trusted/$f")" == 0 ]] || {
    echo "MISSING_ROOT_OWNED_STAGE_FILE: $f" >&2; exit 3;
  }
done
echo "Only completing the existing root-owned files-only staging."
echo "No daemon or tunnel activation, no network changes."
read -r -p "Type COMPLETE-LIMITED-SUDO: " confirmation
[[ "$confirmation" == COMPLETE-LIMITED-SUDO ]] || exit 2
/usr/sbin/chown root:wheel "$control"
/bin/chmod 0755 "$control"
temp="$(/usr/bin/mktemp /etc/sudoers.d/.twinconnect-XXXXXX)"
trap '/bin/rm -f "$temp"' EXIT
/bin/chmod 0600 "$temp"
printf '%s ALL=(root) NOPASSWD: %s status, %s stop\n' "$admin" "$control" "$control" > "$temp"
/usr/sbin/visudo -cf "$temp" >/dev/null
/usr/bin/install -o root -g wheel -m 0440 "$temp" "$rule"
/usr/sbin/visudo -cf /etc/sudoers >/dev/null
echo "LIMITED_SUDO_READY; TUN_FILES_STAGED; SERVICE_NOT_STARTED; ROUTES_UNCHANGED"