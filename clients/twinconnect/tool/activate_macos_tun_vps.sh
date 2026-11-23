#!/usr/bin/env bash
# One-time VPS TUN service activation from independent hypervisor VNC.
# Launches a controller only, NEVER sing-box or a VPN profile.
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
plist="/Library/LaunchDaemons/com.twinconnect.localtun.plist"
approval="$root/local-console-approval"
[[ -d "$root" && ! -L "$root" && "$(stat -f '%u' "$root")" == 0 &&
   ! -e "$plist" && ! -L "$plist" &&
   ! -e "$approval" && ! -L "$approval" ]] || {
  echo "EXPECTED_STAGED_STATE_NOT_FOUND" >&2; exit 3;
}
files=(unsigned_tun_daemon.py unsigned_tun_policy.py
       unsigned_tun_watchdog.py openvpn_profile_review.py
       tun_vps_management_guard.py)
for file in "${files[@]}"; do
  src="macos_native/$file"
  dst="$root/$file"
  [[ -f "$src" && ! -L "$src" && -f "$dst" && ! -L "$dst" &&
     "$(stat -f '%u' "$dst")" == 0 ]] || {
    echo "MISSING_ROOT_OWNED_FILE: $file" >&2; exit 3;
  }
  /usr/bin/python3 -m py_compile "$src"
done
[[ -x "$root/sing-box" && "$(stat -f '%u' "$root/sing-box")" == 0 ]] || {
  echo "TRUSTED_SINGBOX_MISSING" >&2; exit 3;
}
# Deny activation unless the code includes bounded VPS mode.
grep -Fq 'VPS_OOB_CONSOLE_45_SECONDS' macos_native/unsigned_tun_daemon.py
grep -Fq 'VPS_SESSION = 45' macos_native/unsigned_tun_daemon.py
# Ensure the same user has an independently callable emergency Stop.
[[ -x /Library/PrivilegedHelperTools/TwinConnectOps/tun-admin ]] || {
  echo "EMERGENCY_STOP_NOT_INSTALLED" >&2; exit 3;
}
[[ -f /etc/sudoers.d/twinconnect-tun-admin ]] || {
  echo "LIMITED_SUDO_NOT_INSTALLED" >&2; exit 3;
}
/usr/sbin/visudo -cf /etc/sudoers >/dev/null
echo "Activates only the root-owned TwinConnect TUN controller."
echo "No VPN profile started. NO network or DNS changes."
echo "A later Connect action MAY change routes; VPS trial is limited to 45s."
echo "Proceed ONLY with an INDEPENDENT hypervisor VNC console open."
read -r -p "Type ENABLE-VPS-TUN-CONTROLLER to continue: " reply
[[ "$reply" == "ENABLE-VPS-TUN-CONTROLLER" ]] || {
  echo "NOT_APPROVED" >&2; exit 2;
}
# Staged source was root-owned; update it atomically before launch.
for file in "${files[@]}"; do
  target="$root/$file"
  new="$root/.new-$file"
  [[ ! -e "$new" && ! -L "$new" ]] || {
    echo "UNEXPECTED_STAGED_TEMP_FILE" >&2; exit 3;
  }
  /usr/bin/install -o root -g wheel -m 0644 "macos_native/$file" "$new"
  /bin/mv -f "$new" "$target" || exit 4
  /usr/sbin/chown root:wheel "$target"
  /bin/chmod 0644 "$target"
done
/usr/bin/printf '%s\n' VPS_OOB_CONSOLE_45_SECONDS > "$approval"
/usr/sbin/chown root:wheel "$approval"
/bin/chmod 0600 "$approval"
cat > "$plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.twinconnect.localtun</string>
<key>ProgramArguments</key><array>
<string>/usr/bin/python3</string>
<string>/Library/PrivilegedHelperTools/TwinConnectTUN/unsigned_tun_daemon.py</string>
</array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><false/>
<key>StandardOutPath</key><string>/dev/null</string>
<key>StandardErrorPath</key><string>/dev/null</string>
</dict></plist>
PLIST
/usr/sbin/chown root:wheel "$plist"
/bin/chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist"
/bin/launchctl bootstrap system "$plist"
/bin/sleep 1
if [[ -S /var/run/twinconnect-tun.sock ]]; then
  echo "VPS_TUN_CONTROLLER_READY; NO_VPN_STARTED; MAX_TRIAL_45_SECONDS"
else
  echo "VPS_TUN_CONTROLLER_SOCKET_ABSENT; CHECK_LAUNCHD" >&2
  exit 5
fi