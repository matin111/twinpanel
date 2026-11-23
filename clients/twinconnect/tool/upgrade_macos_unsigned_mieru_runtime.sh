#!/usr/bin/env bash
# Upgrade ONLY the root-owned, unsigned Mieru-capable TUN controller.
# Refuse while any VPN/TUN is active. Do not change routes, DNS, or sudoers.
set -euo pipefail

[[ "$(id -u)" == 0 && "$(uname -s)" == Darwin && "$(uname -m)" == x86_64 ]] || {
  echo "ROOT_DARWIN_AMD64_REQUIRED" >&2; exit 2;
}
source_root="/Users/macvps/twinpanel/clients/twinconnect"
cd "$source_root"
trusted="/Library/PrivilegedHelperTools/TwinConnectTUN"
ops="/Library/PrivilegedHelperTools/TwinConnectOps"
service="system/com.twinconnect.localtun"
[[ "$(stat -f '%Su' /dev/console)" == "macvps" ]] || {
  echo "EXPECTED_CONSOLE_OWNER_NOT_PRESENT" >&2; exit 2;
}
for path in "$trusted" "$ops"; do
  [[ -d "$path" && ! -L "$path" && "$(stat -f '%u' "$path")" == 0 ]] || {
    echo "TRUSTED_ROOT_DIRECTORY_REQUIRED" >&2; exit 2;
  }
done
for name in unsigned_tun_daemon.py unsigned_mieru_profile.py; do
  [[ -f "macos_native/$name" && ! -L "macos_native/$name" ]] || {
    echo "MISSING_MIERU_SOURCE" >&2; exit 2;
  }
  /usr/bin/python3 -m py_compile "macos_native/$name"
done
mbox="macos_native/build/mbox/amd64/sing-box"
[[ -f "$mbox" && ! -L "$mbox" && -x "$mbox" ]] || {
  echo "VERIFIED_MBOX_BINARY_REQUIRED" >&2; exit 2;
}
/usr/bin/lipo -archs "$mbox" | /usr/bin/grep -qw 'x86_64' || {
  echo "MIERU_MBOX_WRONG_ARCH" >&2; exit 2;
}
[[ "$("$mbox" version | /usr/bin/head -1)" == "sing-box version 1.14.3" ]] || {
  echo "MIERU_MBOX_VERSION_MISMATCH" >&2; exit 2;
}
[[ -x "$trusted/sing-box" && "$(stat -f '%u' "$trusted/sing-box")" == 0 ]] || {
  echo "EXISTING_SINGBOX_MUST_REMAIN_PRESENT" >&2; exit 2;
}
[[ -f "$trusted/unsigned_tun_daemon.py" && ! -L "$trusted/unsigned_tun_daemon.py" ]] || {
  echo "CURRENT_TUN_DAEMON_MISSING" >&2; exit 2;
}
[[ -f "$ops/tun_admin_protocol_status.py" && ! -L "$ops/tun_admin_protocol_status.py" ]] || {
  echo "CURRENT_TUN_ADMIN_STATUS_MISSING" >&2; exit 2;
}
status=$(/usr/bin/sudo -n -u macvps /usr/bin/python3 \
  "$source_root/macos_native/unsigned_tun_client.py" status)
[[ "$status" == *'"state": "stopped"'* ]] || {
  echo "ACTIVE_TUN_REFUSED_TO_UPGRADE" >&2; exit 3;
}
pid=$(/usr/sbin/lsof -nP -t "$trusted/mbox" 2>/dev/null || true)
[[ -z "$pid" ]] || {
  echo "EXISTING_MIERU_ENGINE_RUNNING" >&2; exit 3;
}
backup="$trusted/.mieru-runtime-backup-$(date +%Y%m%d%H%M%S)"
/bin/mkdir -m 0700 "$backup"
/bin/cp -p "$trusted/unsigned_tun_daemon.py" "$backup/unsigned_tun_daemon.py"
/bin/cp -p "$ops/tun_admin_protocol_status.py" "$backup/tun_admin_protocol_status.py"
if [[ -e "$trusted/unsigned_mieru_profile.py" ]]; then
  /bin/cp -p "$trusted/unsigned_mieru_profile.py" "$backup/unsigned_mieru_profile.py"
fi
if [[ -e "$trusted/mbox" ]]; then
  /bin/cp -p "$trusted/mbox" "$backup/mbox"
fi

rollback() {
  echo "MIERU_RUNTIME_UPDATE_FAILED_RESTORING" >&2
  /usr/bin/install -o root -g wheel -m 0644 \
    "$backup/unsigned_tun_daemon.py" "$trusted/unsigned_tun_daemon.py"
  /usr/bin/install -o root -g wheel -m 0644 \
    "$backup/tun_admin_protocol_status.py" "$ops/tun_admin_protocol_status.py"
  if [[ -f "$backup/unsigned_mieru_profile.py" ]]; then
    /usr/bin/install -o root -g wheel -m 0644 \
      "$backup/unsigned_mieru_profile.py" "$trusted/unsigned_mieru_profile.py"
  fi
  if [[ -f "$backup/mbox" ]]; then
    /usr/bin/install -o root -g wheel -m 0755 "$backup/mbox" "$trusted/mbox"
  fi
  /bin/launchctl kickstart -k "$service" >/dev/null 2>&1 || true
}
trap rollback ERR
/usr/bin/install -o root -g wheel -m 0755 "$mbox" "$trusted/mbox"
/usr/bin/install -o root -g wheel -m 0644 \
  macos_native/unsigned_mieru_profile.py "$trusted/unsigned_mieru_profile.py"
/usr/bin/install -o root -g wheel -m 0644 \
  macos_native/unsigned_tun_daemon.py "$trusted/unsigned_tun_daemon.py"
/usr/bin/install -o root -g wheel -m 0644 \
  tool/tun_admin_protocol_status.py "$ops/tun_admin_protocol_status.py"
/usr/bin/python3 -m py_compile \
  "$trusted/unsigned_tun_daemon.py" "$trusted/unsigned_mieru_profile.py" \
  "$ops/tun_admin_protocol_status.py"
/bin/launchctl kickstart -k "$service"
/bin/sleep 2
status=$(/usr/bin/sudo -n -u macvps /usr/bin/python3 \
  "$source_root/macos_native/unsigned_tun_client.py" status)
[[ "$status" == *'"state": "stopped"'* ]] || {
  echo "MIERU_DAEMON_RESTART_STATUS_FAILED" >&2; false;
}
/bin/launchctl print "$service" | grep -E 'state =|pid =' | /usr/bin/head -4
trap - ERR
echo "UNSIGNED_MIERU_RUNTIME_READY; EXISTING_SINGBOX_PRESERVED; ROUTES_UNCHANGED"
echo "BACKUP_PATH: $backup"