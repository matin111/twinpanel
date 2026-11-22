#!/usr/bin/env bash
# Explicit administrator-only installation of the Cisco tunnel launcher.
# No sudoers or VPN routes are altered by this installer.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "CISCO_MACOS_REQUIRED" >&2; exit 1
fi
if [[ "$EUID" -ne 0 ]]; then
  echo "Run this script explicitly with sudo; it will not prompt or elevate itself." >&2
  exit 1
fi
base="/Library/PrivilegedHelperTools/TwinConnectCisco"
install -d -o root -g wheel -m 0755 "$base"
for filename in cisco_openconnect_auth.py cisco_openconnect_tunnel.py cisco_network_recovery.py cisco_unrouted_vpnc.py; do
  install -o root -g wheel -m 0755 "macos_native/$filename" "$base/$filename"
done
# Always install an administrator-owned copy of vpnc-script. Never execute
# a user-owned Homebrew script as root when connecting Cisco.
vpn_source=""
for candidate in /usr/local/etc/vpnc/vpnc-script /opt/homebrew/etc/vpnc/vpnc-script; do
  if [[ -f "$candidate" && ! -L "$candidate" ]]; then vpn_source="$candidate"; break; fi
done
[[ -n "$vpn_source" ]] || { echo "CISCO_VPN_SCRIPT_NOT_FOUND" >&2; exit 1; }
install -o root -g wheel -m 0755 "$vpn_source" "$base/vpnc-script"
stat -f '%Su %Sp %N' "$base/vpnc-script"
# Ensure files cannot be changed by the app's unprivileged account.
for filename in cisco_openconnect_auth.py cisco_openconnect_tunnel.py; do
  stat -f '%Su %Sp %N' "$base/$filename"
done
echo "CISCO_HELPER_INSTALLED"
echo "No VPN launched; no sudoers permission granted."
echo "The admin must independently authorize a narrow privileged launch."
