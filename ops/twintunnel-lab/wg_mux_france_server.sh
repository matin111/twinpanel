#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
LAB=/etc/twintunnel-wg-mux-lab
LOG=/opt/twintunnel-test/results/wg_mux_france.log
ECHO=twintunnel-lab-udp-echo.service
P=0
cleanup() {
  echo "WG_MUX_SERVER_CLEANUP $(date -u +%FT%TZ)"
  if test "$P" -gt 0; then kill -TERM "$P" 2>/dev/null || true; wait "$P" 2>/dev/null || true; fi
  ip link del wgTTsrv 2>/dev/null || true
  systemctl start "$ECHO"
  echo "OLD_UDP_ECHO_RESTORED=$(systemctl is-active "$ECHO")"
  echo "MAIN_WG_INTERFACES=$(wg show interfaces)"
  echo "MAIN_OPENVPN_STATES=$(systemctl is-active openvpn-server@server.service openvpn-server@twinpanel.service | tr '\n' ',')"
}
trap cleanup EXIT
test "$(systemctl is-active "$ECHO")" = active
for f in server.key iran-client1.pub iran-client2.pub; do test -s "$LAB/$f"; done
ip link show wgTTsrv >/dev/null 2>&1 && { echo "ABORT_TEST_SERVER_IF_ALREADY_EXISTS";exit 4; } || true
test -z "$(ss -Hlun | grep -E ':(37922|37983)\b' | grep ':37983' || true)" || { echo PORT_37983_BUSY;exit 4; }
systemctl stop "$ECHO"
python3 -u /opt/twintunnel-test/udp_multiuser_mux.py --role exit --wg-target 37983 --ovpn-target 37984 --duration 95 > "$LOG" 2>&1 &
P=$!
sleep 1
kill -0 "$P"
ip link add wgTTsrv type wireguard
wg set wgTTsrv listen-port 37983 private-key "$LAB/server.key" peer "$(cat "$LAB/iran-client1.pub")" allowed-ips 10.254.221.2/32
wg set wgTTsrv peer "$(cat "$LAB/iran-client2.pub")" allowed-ips 10.254.221.3/32
ip address add 10.254.221.1/32 dev wgTTsrv
ip link set wgTTsrv mtu 1120 up
echo "WG_MUX_SERVER_READY $(date -u +%FT%TZ)"
sleep 67
echo "WG_MUX_SERVER_REPORT $(date -u +%FT%TZ)"
echo "WG_RECEIVED_TUN_PACKETS=$(cat /sys/class/net/wgTTsrv/statistics/rx_packets)"
echo "WG_RECEIVED_TUN_BYTES=$(cat /sys/class/net/wgTTsrv/statistics/rx_bytes)"
echo "WG_PEER_RECENT_HANDSHAKES=$(wg show wgTTsrv latest-handshakes | awk -v t=$(date +%s) '$2>0 && t-$2<90 {n++} END {print n+0}')"
wg show wgTTsrv transfer | awk '{down+=$2; up+=$3} END {print "WG_SERVER_ENCRYPTED_RX_BYTES="down,"WG_SERVER_ENCRYPTED_TX_BYTES="up}'
tail -4 "$LOG"