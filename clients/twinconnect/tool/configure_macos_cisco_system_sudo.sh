#!/usr/bin/env bash
# Authorize exactly the root-owned Cisco system-connect helper and read-only
# route status. No profile, routes, DNS, or VPN are modified during install.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == "Darwin" && "$EUID" -eq 0 ]] || {
  echo "CISCO_MACOS_ROOT_REQUIRED" >&2; exit 2;
}
base=/Library/PrivilegedHelperTools/TwinConnectCisco
helper="$base/cisco_openconnect_tunnel.py"
guard="$base/cisco_management_route_guard.py"
for f in "$helper" "$guard"; do
  [[ -f "$f" && ! -L "$f" && "$(stat -f '%Su' "$f")" == "root" ]] || {
    echo "CISCO_ROOT_HELPER_NOT_TRUSTED" >&2; exit 2;
  }
  [[ "$(stat -f '%Lp' "$f")" == "755" ]] || {
    echo "CISCO_ROOT_HELPER_WRITABLE" >&2; exit 2;
  }
done
grep -Eq '^[[:space:]]*(#includedir|@includedir)[[:space:]]+(/private)?/etc/sudoers.d' /private/etc/sudoers || {
  echo "CISCO_SUDOERS_INCLUDE_NOT_FOUND" >&2; exit 2;
}
dest=/private/etc/sudoers.d/twinconnect-cisco
tmp=$(mktemp /private/etc/sudoers.d/.twinconnect-cisco-system.XXXXXXXX)
trap 'rm -f "$tmp"' EXIT
{
  printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 %s system, /usr/bin/python3 %s status\n' \
    macvps "$helper" "$guard"
} > "$tmp"
chown root:wheel "$tmp"
chmod 0440 "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
if [[ -f "$dest" && ! -L "$dest" ]]; then
  cp -p "$dest" "$base/sudoers.before-cisco-system"
fi
install -o root -g wheel -m 0440 "$tmp" "$dest"
/usr/sbin/visudo -cf "$dest" >/dev/null
echo "CISCO_SYSTEM_HELPER_AUTHORIZED; NO_NETWORK_CHANGES"
