#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
LAB=/etc/twintunnel-wg-client-test
A=198.18.66.1/32
B=198.18.66.2/32
cleanup() {
  echo "WG_MUX_CLIENT_CLEANUP $(date -u +%FT%TZ)"
  ip route del "$A" dev wgTTc1 2>/dev/null || true
  ip route del "$B" dev wgTTc2 2>/dev/null || true
  ip link del wgTTc1 2>/dev/null || true
  ip link del wgTTc2 2>/dev/null || true
  echo "IRAN_MAIN_WG=$(wg show interfaces)"
}
trap cleanup EXIT
for name in wgTTc1 wgTTc2; do
  if ip link show "$name" >/dev/null 2>&1; then echo PREEXISTING_WG_TEST_INTERFACE; exit 4; fi
done
test -z "$(ip route show "$A")";test -z "$(ip route show "$B")"
for f in client1.key client2.key server.pub; do test -s "$LAB/$f"; done
for n in 1 2; do
  case "$n" in 1) ip=10.254.221.2;target="$A";;2) ip=10.254.221.3;target="$B";;esac
  ip link add "wgTTc$n" type wireguard
  wg set "wgTTc$n" private-key "$LAB/client$n.key" listen-port 0 peer "$(cat "$LAB/server.pub")" endpoint 94.183.231.158:37981 allowed-ips "$target" persistent-keepalive 3
  ip addr add "$ip/32" dev "wgTTc$n"
  ip link set "wgTTc$n" mtu 1120 up
  ip route add "$target" dev "wgTTc$n" metric 999
done
echo "WG_MUX_TWO_CLIENTS_READY $(date -u +%FT%TZ)"
ping -n -I wgTTc1 -c 145 -i 0.18 -W 1 198.18.66.1 >/tmp/ttmux-wg-c1-ping.log 2>&1 &
p1=$!
ping -n -I wgTTc2 -c 145 -i 0.18 -W 1 198.18.66.2 >/tmp/ttmux-wg-c2-ping.log 2>&1 &
p2=$!
wait "$p1" || true
wait "$p2" || true
echo "WG_MUX_CLIENT_REPORT $(date -u +%FT%TZ)"
for n in 1 2; do
  echo "CLIENT_${n}_RECENT_HANDSHAKES=$(wg show "wgTTc$n" latest-handshakes | awk -v t=$(date +%s) '$2>0 && t-$2<90 {n++} END {print n+0}')"
  wg show "wgTTc$n" transfer | awk '{print "ENCRYPTED_DOWN_BYTES="$2,"ENCRYPTED_UP_BYTES="$3}'
done