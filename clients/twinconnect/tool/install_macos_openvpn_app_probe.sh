#!/usr/bin/env bash
# Explicit opt-in: install a bounded OpenVPN handshake diagnostic called by
# TwinConnect's app button. Not a system VPN. No routes altered by installer.
set -euo pipefail
cd "$(dirname "$0")/.."
root="/Library/PrivilegedHelperTools/TwinConnectOpenVPN"
runner="$root/tool/test_macos_openvpn_handshake.py"
sudoers="/private/etc/sudoers.d/twinconnect-openvpn-probe"
case "${1:-}" in
  check)
    [[ -f "$runner" ]] && echo "APP_OPENVPN_PROBE_STAGED" || echo "APP_OPENVPN_PROBE_NOT_STAGED"
    [[ -f "$sudoers" ]] && echo "APP_OPENVPN_PROBE_AUTH_CONFIG_PRESENT" || echo "APP_OPENVPN_PROBE_AUTH_MISSING"
    exit 0;;
  install|remove) action="$1";;
  *) echo "Usage: bash tool/install_macos_openvpn_app_probe.sh {check|install|remove}" >&2; exit 2;;
esac
[[ "$(uname -s)" == "Darwin" ]] || { echo "MACOS_ONLY" >&2; exit 2; }
[[ "$(id -u)" == "0" ]] || { echo "ROOT_REQUIRED: use sudo" >&2; exit 2; }
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_ADMIN_REQUIRED" >&2; exit 2; }
if [[ "$action" == remove ]]; then
  /bin/rm -f "$sudoers"
  if [[ -d "$root" && ! -L "$root" ]]; then
    /bin/rm -rf "$root"
  fi
  echo "APP_OPENVPN_PROBE_REMOVED"
  exit 0
fi
printf '%s\n' "This is a real OpenVPN handshake test on the current Mac."
printf '%s\n' "It can temporarily create utun and reach VPN servers."
printf '%s\n' "The test has a 35s limit and prevents default-route imports."
printf '%s\n' "An independent recovery console remains strongly recommended."
read -r -p 'Type ENABLE-OPENVPN-APP-TEST to opt in: ' confirm
[[ "$confirm" == "ENABLE-OPENVPN-APP-TEST" ]] || { echo "NOT_APPROVED"; exit 2; }
[[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]] || { echo "SUDO_USER_REQUIRED"; exit 2; }
[[ ! -e "$root" && ! -L "$root" ]] || { echo "EXISTING_ROOT_REFUSED"; exit 2; }
[[ ! -e "$sudoers" && ! -L "$sudoers" ]] || { echo "EXISTING_SUDOERS_REFUSED"; exit 2; }
[[ -f tool/test_macos_openvpn_handshake.py && -f macos_native/openvpn_profile_review.py ]] || exit 2
/bin/mkdir -m 0700 "$root"
/bin/mkdir -m 0700 "$root/tool" "$root/macos_native"
/usr/bin/install -o root -g wheel -m 0644 tool/test_macos_openvpn_handshake.py "$runner"
/usr/bin/install -o root -g wheel -m 0644 macos_native/openvpn_profile_review.py "$root/macos_native/openvpn_profile_review.py"
# The fixed command alone, only for the installing account. No shell wildcard.
# Refuse account names that sudoers could reinterpret.
[[ "$SUDO_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "INVALID_INSTALL_USER"; exit 2; }
tmp="$(/usr/bin/mktemp /private/etc/sudoers.d/.tc-openvpn.XXXXXXXX)"
trap '/bin/rm -f "$tmp"' EXIT
/bin/chmod 0440 "$tmp"
/usr/sbin/chown root:wheel "$tmp"
/usr/bin/printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 %s --stdin\n' "$SUDO_USER" "$runner" > "$tmp"
/usr/sbin/visudo -c -f "$tmp" || { echo "INVALID_SUDOERS_RULE"; exit 3; }
/bin/mv "$tmp" "$sudoers"
trap - EXIT
echo "APP_OPENVPN_PROBE_INSTALLED; NO_VPN_STARTED; ROUTES_UNCHANGED"
