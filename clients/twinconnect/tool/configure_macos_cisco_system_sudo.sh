#!/usr/bin/env bash
# Safety hotfix: disable Cisco system VPN privileges after real connectivity loss.
# Keep the read-only status and emergency recovery commands only.
set -euo pipefail
[[ "$(uname -s)" == "Darwin" && "$EUID" -eq 0 ]] || {
  echo "CISCO_MACOS_ROOT_REQUIRED" >&2
  exit 2
}
base=/Library/PrivilegedHelperTools/TwinConnectCisco
dest=/private/etc/sudoers.d/twinconnect-cisco
tmp=$(mktemp /private/etc/sudoers.d/.twinconnect-cisco-safe.XXXXXXXX)
trap 'rm -f "$tmp"' EXIT
printf '%s\n' \
 'macvps ALL=(root) NOPASSWD: /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectCisco/cisco_management_route_guard.py status, /usr/bin/python3 /Library/PrivilegedHelperTools/TwinConnectCisco/cisco_management_route_guard.py stop' > "$tmp"
chown root:wheel "$tmp"
chmod 0440 "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
if [[ -f "$dest" && ! -L "$dest" ]]; then
  cp -p "$dest" "$base/sudoers.before-cisco-disabled"
fi
install -o root -g wheel -m 0440 "$tmp" "$dest"
/usr/sbin/visudo -cf "$dest" >/dev/null
echo "CISCO_SYSTEM_VPN_DISABLED; ONLY_STATUS_AND_EMERGENCY_STOP_AUTHORIZED"
