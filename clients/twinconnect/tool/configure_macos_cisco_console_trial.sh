#!/usr/bin/env bash
# One-time setup for a time-limited Cisco trial using provider web VNC console.
# Does not launch VPN or change routes. Requires operator confirmation.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" || "$EUID" -ne 0 ]]; then
  echo "CISCO_ROOT_ON_MACOS_REQUIRED" >&2; exit 1
fi
if [[ "${1:-}" != "--provider-console-confirmed" || "$#" -ne 1 ]]; then
  echo "Use ONLY when a provider web VNC recovery console is available." >&2
  echo "Usage: sudo bash tool/configure_macos_cisco_console_trial.sh --provider-console-confirmed" >&2
  exit 1
fi
user="${SUDO_USER:-}"
if [[ -z "$user" || "$user" == root || ! "$user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]]; then
  echo "CISCO_LOCAL_ACCOUNT_INVALID" >&2; exit 1
fi
base="/Library/PrivilegedHelperTools/TwinConnectCisco"
for f in "$base" "$base/cisco_openconnect_auth.py" "$base/cisco_openconnect_tunnel.py" "$base/vpnc-script"; do
  [[ ! -L "$f" && -e "$f" && "$(stat -f '%Su' "$f")" == root ]] || {
    echo "CISCO_HELPER_NOT_TRUSTED" >&2; exit 1
  }
  mode="$(stat -f '%Lp' "$f")"
  [[ "$mode" == 755 ]] || { echo "CISCO_HELPER_MODE_INVALID" >&2; exit 1; }
done
grep -Eq '^[[:space:]]*(#includedir|@includedir)[[:space:]]+(/private)?/etc/sudoers.d' /private/etc/sudoers || {
  echo "CISCO_SUDOERS_INCLUDE_NOT_FOUND" >&2; exit 1
}
dest="/private/etc/sudoers.d/twinconnect-cisco"
tmp="$(mktemp /private/etc/sudoers.d/.twinconnect-cisco.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
chmod 0440 "$tmp"
printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 %s connect console-test\n' \
 "$user" "$base/cisco_openconnect_tunnel.py" > "$tmp"
/usr/sbin/visudo -cf "$tmp" >/dev/null
install -o root -g wheel -m 0440 "$tmp" "$dest"
printf '%s\n' console-test > "$base/management_ipv4"
chown root:wheel "$base/management_ipv4"
chmod 0644 "$base/management_ipv4"
echo "CISCO_CONSOLE_TRIAL_CONFIGURED"
echo "Next Cisco connection has a 120-second automatic timeout."
echo "No VPN or routes were changed during setup."
