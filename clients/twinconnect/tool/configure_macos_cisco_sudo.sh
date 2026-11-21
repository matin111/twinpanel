#!/usr/bin/env bash
# Configure one exact noninteractive sudo command for the root-owned Cisco runner.
# Does not launch VPN or change routes. Pass your real, stable management
# workstation IPv4 address (NOT the Mac's public IP or its default gateway).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" || "$EUID" -ne 0 ]]; then
  echo "Run with sudo on macOS" >&2; exit 1
fi
if [[ "$#" -ne 1 ]]; then
  echo "Usage: sudo bash tool/configure_macos_cisco_sudo.sh MANAGEMENT_CLIENT_IPV4" >&2
  exit 1
fi
ip="$1"
python3 - "$ip" <<'PY'
import ipaddress,sys
try:
    address=ipaddress.ip_address(sys.argv[1])
    if address.version != 4 or not address.is_global:
        raise ValueError
except ValueError:
    raise SystemExit("CISCO_MANAGEMENT_IP_INVALID: use the real external management client IPv4")
PY
user="macvps"
id "$user" >/dev/null
base="/Library/PrivilegedHelperTools/TwinConnectCisco"
runner="$base/cisco_openconnect_tunnel.py"
auth="$base/cisco_openconnect_auth.py"
for f in "$runner" "$auth"; do
  [[ -f "$f" && ! -L "$f" && "$(stat -f '%Su' "$f")" == root ]] || {
    echo "CISCO_ROOT_OWNED_HELPER_MISSING: $f" >&2; exit 1;
  }
  mode="$(stat -f '%Lp' "$f")"
  # Installed by install_macos_cisco_helper.sh at 755; require exactly 755.
  [[ "$mode" == 755 ]] || { echo "CISCO_HELPER_PERMISSIONS_INVALID" >&2; exit 1; }
done
# Confirm this macOS sudoers actually includes drop-in files before editing.
grep -Eq '^[[:space:]]*#(include|includedir|@includedir)[[:space:]]+(/private)?/etc/sudoers.d' /etc/sudoers || {
  echo "CISCO_SUDOERS_INCLUDE_NOT_CONFIRMED" >&2; exit 1;
}
mkdir -p /private/etc/sudoers.d
dest="/private/etc/sudoers.d/twinconnect-cisco"
conf="$base/management_ipv4"
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-cisco.XXXXXX)"
trap 'rm -f "$tmp"' EXIT
chmod 0440 "$tmp"
printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 %s connect %s\n' "$user" "$runner" "$ip" > "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
# Install only after validating syntax. Preserve prior rule on failure.
install -o root -g wheel -m 0440 "$tmp" "$dest"
printf '%s\n' "$ip" > "$conf"
chown root:wheel "$conf"
chmod 0644 "$conf"
echo "CISCO_LIMITED_SUDO_CONFIGURED"
echo "Only one exact root-owned Cisco command is authorized."
echo "No VPN started and no network routes changed."
