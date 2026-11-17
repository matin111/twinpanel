#!/usr/bin/env bash
# Real isolated WireGuard test over Iran->Turkey->France multi-carrier lab.
set -Eeuo pipefail
LAB1=twintunnel-lab@entry.service
LAB2=twintunnel-lab@entry-udp.service
CLIENT=/opt/twintunnel-test/wg_mux_iran_clients.sh
P=0
cleanup() {
  systemctl start "$LAB1" "$LAB2"
  echo "WG_THIRD_PATH_LABS_RESTORED=$(systemctl is-active "$LAB1"),$(systemctl is-active "$LAB2")"
  if test "$P" -gt 0; then
    if kill -0 "$P" 2>/dev/null; then kill -TERM "$P" 2>/dev/null || true;fi
    wait "$P" 2>/dev/null || true
  fi
}
trap cleanup EXIT
systemctl show "$LAB1" -p ExecStart --value | grep -F /etc/twintunnel-test/entry.toml >/dev/null
systemctl show "$LAB2" -p ExecStart --value | grep -F /etc/twintunnel-test/entry-udp.toml >/dev/null
test "$(systemctl is-active "$LAB1")" = active
test "$(systemctl is-active "$LAB2")" = active
test -z "$(ip -br link show | grep -E 'wgTTc1|wgTTc2' || true)"
"$CLIENT" &
P=$!
sleep 5
kill -0 "$P"
echo "WG_THIRD_PATH_DIRECT_DOWN_START=$(date -u +%FT%TZ)"
systemctl stop "$LAB1" "$LAB2"
sleep 8
echo "WG_THIRD_PATH_DIRECT_DOWN_END=$(date -u +%FT%TZ)"
systemctl start "$LAB1" "$LAB2"
wait "$P" || true
P=0
echo "WG_THIRD_PATH_CLIENT_TEST_DONE=$(date -u +%FT%TZ)"
