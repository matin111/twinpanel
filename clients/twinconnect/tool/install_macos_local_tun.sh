#!/usr/bin/env bash
# TwinConnect TUN local Mac deployment. NEVER RUN ON A REMOTE/CLOUD MAC.
# Stage only by default. Activation requires explicit local physical-console
# recovery acknowledgement. No network/routing changes during installation.
set -euo pipefail

cd "$(dirname "$0")/.."
root="/Library/PrivilegedHelperTools/TwinConnectTUN"
plist="/Library/LaunchDaemons/com.twinconnect.localtun.plist"
label="com.twinconnect.localtun"
socket="/var/run/twinconnect-tun.sock"

usage() {
  echo "Usage: bash tool/install_macos_local_tun.sh {check|stage|activate|stop|remove}"
  echo "WARNING: never execute stage/activate on cloud/VPS or SSH-managed Mac"
}

[[ $# -eq 1 ]] || { usage; exit 2; }
action="$1"
case "$action" in check|stage|activate|stop|remove) ;; *) usage; exit 2;; esac
[[ "$(uname -s)" == "Darwin" ]] || { echo "MACOS_ONLY" >&2; exit 2; }
if [[ -n "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}${TWINCONNECT_REMOTE_VPS:-}" ]]; then
  echo "REMOTE_SESSION_REFUSED" >&2; exit 2
fi
if [[ "$action" == "check" ]]; then
  printf 'OS: '; sw_vers -productVersion
  echo "Console owner: $(stat -f '%Su' /dev/console)"
  echo "Service staged: $([[ -f "$root/unsigned_tun_daemon.py" ]] && echo yes || echo no)"
  echo "Service socket: $([[ -S "$socket" ]] && echo present || echo absent)"
  echo "No network changes performed"
  exit 0
fi
[[ "$(id -u)" == "0" ]] || { echo "RUN_LOCALLY_AS_ROOT_WITH_SUDO" >&2; exit 2; }

# The administrator initiating sudo must own the active local console.
[[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]] ||
  { echo "SUDO_CONSOLE_USER_REQUIRED" >&2; exit 2; }
[[ "$(stat -f '%Su' /dev/console)" == "$SUDO_USER" ]] ||
  { echo "CONSOLE_USER_MISMATCH" >&2; exit 2; }
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_CONSOLE_REQUIRED" >&2; exit 2; }
# A remote Mac can have a logged-in console. The following is an additional,
# explicit human safety acknowledgment, not technical proof of local access.
if [[ "$action" == "stage" || "$action" == "activate" ]]; then
  echo "Do NOT proceed on a VPS, cloud Mac or remotely managed computer."
  echo "Do NOT proceed without an independent console and recovery plan."
  read -r -p "Type LOCAL-PHYSICAL-MAC to confirm: " confirmation
  [[ "$confirmation" == "LOCAL-PHYSICAL-MAC" ]] ||
    { echo "LOCAL_CONSOLE_CONFIRMATION_REQUIRED" >&2; exit 2; }
fi

if [[ "$action" == "stop" || "$action" == "remove" ]]; then
  /bin/launchctl bootout system/"$label" 2>/dev/null || true
  if [[ "$action" == "remove" ]]; then
    [[ ! -S "$socket" ]] || { echo "LIVE_SOCKET_REMAINS_REFUSING_REMOVAL" >&2; exit 3; }
    [[ ! -L "$root" && ! -L "$plist" ]] ||
      { echo "SYMLINK_REFUSED" >&2; exit 3; }
    /bin/rm -f "$plist"
    /bin/rm -rf "$root"
  fi
  echo "LOCAL_TUN_STOP_OR_REMOVE_REQUESTED; CHECK_NETWORK_MANUALLY"
  exit 0
fi

[[ ! -L "$root" && ! -L "$plist" ]] ||
  { echo "SYMLINK_REFUSED" >&2; exit 2; }
if [[ -e "$plist" ]]; then
  echo "EXISTING_LAUNCHD_PLIST_REFUSED; stop and remove first" >&2; exit 2
fi
if [[ "$action" == "stage" && -e "$root" ]]; then
  echo "EXISTING_TUN_RUNTIME_REFUSED; stop and remove first" >&2; exit 2
fi
if [[ "$action" == "activate" && ! -d "$root" ]]; then
  echo "STAGE_BEFORE_ACTIVATE" >&2; exit 2
fi
arch="$(uname -m)"
case "$arch" in
 x86_64) engine="macos_native/build/singbox/amd64/sing-box";;
 arm64) engine="macos_native/build/singbox/arm64/sing-box";;
 *) echo "UNSUPPORTED_ARCH" >&2; exit 2;;
esac
[[ -f "$engine" && -x "$engine" && ! -L "$engine" ]] ||
  { echo "SINGBOX_ENGINE_MISSING" >&2; exit 2; }
for f in unsigned_tun_daemon.py unsigned_tun_policy.py; do
  [[ -f "macos_native/$f" && ! -L "macos_native/$f" ]] ||
    { echo "MISSING_SAFE_TUN_SOURCE: $f" >&2; exit 2; }
done
# macOS /usr/bin/python3 may be older than the code's Python 3.10 syntax.
[[ -x /usr/bin/python3 ]] || { echo "SYSTEM_PYTHON_REQUIRED" >&2; exit 2; }
/usr/bin/python3 -c 'import sys; assert sys.version_info >= (3,9)' ||
  { echo "PYTHON_39_OR_NEWER_REQUIRED_FOR_DAEMON" >&2; exit 2; }

if [[ "$action" == "stage" ]]; then
  mkdir -m 0700 "$root"
  chown root:wheel "$root"
  install -o root -g wheel -m 0755 "$engine" "$root/sing-box"
  install -o root -g wheel -m 0644 macos_native/unsigned_tun_daemon.py "$root/unsigned_tun_daemon.py"
  install -o root -g wheel -m 0644 macos_native/unsigned_tun_policy.py "$root/unsigned_tun_policy.py"
else
  # Never swap helper source behind root ownership on activation.
  for f in sing-box unsigned_tun_daemon.py unsigned_tun_policy.py; do
    [[ -f "$root/$f" && ! -L "$root/$f" && "$(stat -f %u "$root/$f")" == 0 ]] ||
      { echo "TRUSTED_STAGED_FILE_MISSING" >&2; exit 2; }
  done
fi
# install is staging only: NO activation, no root background service.
if [[ "$action" == "stage" ]]; then
  echo "LOCAL_TUN_FILES_STAGED; SERVICE_NOT_STARTED; ROUTES_UNCHANGED"
  exit 0
fi

# Activate only a pre-reviewed staged install. Never automatically start TUN
# on boot: the launch daemon handles requests after the user initiates Connect.
# Approval file is deliberately created only after explicit confirmation.
printf 'LOCAL_MAC_WITH_RECOVERY\n' > "$root/local-console-approval"
chmod 0600 "$root/local-console-approval"
chown root:wheel "$root/local-console-approval"

cat > "$plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.twinconnect.localtun</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Library/PrivilegedHelperTools/TwinConnectTUN/unsigned_tun_daemon.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>/dev/null</string>
</dict>
</plist>
PLIST
chown root:wheel "$plist"
chmod 0644 "$plist"
/usr/bin/plutil -lint "$plist"
/bin/launchctl bootstrap system "$plist"
echo "LOCAL_TUN_DAEMON_ACTIVATED; ENGINE_NOT_STARTED; NETWORK_NOT_VERIFIED"
