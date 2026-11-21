#!/usr/bin/env bash
# One-time, admin-approved Cisco setup for a locally controlled macOS desktop.
# Does not connect VPN. Does not grant general sudo privileges.
# The desktop mode intentionally does NOT preserve remote SSH/VNC routes:
# NEVER use on remotely administered Macs without console recovery.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" || "$EUID" -ne 0 ]]; then
  echo "Run with sudo on a LOCAL desktop Mac." >&2; exit 1
fi
user="${SUDO_USER:-}"
if [[ -z "$user" || "$user" == root || ! "$user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]]; then
  echo "CISCO_DESKTOP_ADMIN_USER_REQUIRED" >&2; exit 1
fi
base="/Library/PrivilegedHelperTools/TwinConnectCisco"
install -d -o root -g wheel -m 0755 "$base"
for file in cisco_openconnect_auth.py cisco_openconnect_tunnel.py; do
  install -o root -g wheel -m 0755 "macos_native/$file" "$base/$file"
done
for path in "/usr/local/bin/openconnect" "/opt/homebrew/bin/openconnect"; do
  if [[ -x "$path" ]]; then found=1; break; fi
done
if [[ "${found:-}" != 1 ]] || { [[ ! -f /usr/local/etc/vpnc/vpnc-script ]] && [[ ! -f /opt/homebrew/etc/vpnc/vpnc-script ]]; }; then
  echo "CISCO_ENGINE_REQUIREMENTS_MISSING: install OpenConnect and vpnc-script first." >&2
  exit 1
fi
# Validate the exact included sudoers syntax before installing a drop-in.
grep -Eq '^[[:space:]]*(#includedir|@includedir)[[:space:]]+(/private)?/etc/sudoers.d' /etc/sudoers || {
  echo "CISCO_SUDOERS_INCLUDE_NOT_CONFIRMED" >&2; exit 1;
}
dest="/private/etc/sudoers.d/twinconnect-cisco"
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-cisco.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
chmod 0440 "$tmp"
printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 %s connect desktop\n' \
  "$user" "$base/cisco_openconnect_tunnel.py" > "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" "$dest"
printf '%s\n' desktop > "$base/management_ipv4"
chown root:wheel "$base/management_ipv4"
chmod 0644 "$base/management_ipv4"
echo "CISCO_DESKTOP_READY"
echo "Authorized ONLY for the exact installed OpenConnect command."
echo "No network route, DNS or VPN was changed by this setup."
