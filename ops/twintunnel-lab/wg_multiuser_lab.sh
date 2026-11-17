#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
LAB=/etc/twintunnel-wg-mux-lab
IFSERVER=wgTTsrv
IFCLIENT=wgTTcli
TARGET=198.18.66.1/32
cleanup() {
  echo "WG_LAB_CLEANUP $(date -u +%FT%TZ)"
  ip route del "$TARGET" dev "$IFCLIENT" 2>/dev/null || true
  ip link del "$IFCLIENT" 2>/dev/null || true
  ip link del "$IFSERVER" 2>/dev/null || true
  echo "WG_LAB_INTERFACE_CLEANED"
}
trap cleanup EXIT
for iface in "$IFSERVER" "$IFCLIENT"; do
  if ip link show "$iface" >/dev/null 2>&1; then echo "ABORT_PREEXISTING_TEST_IF=$iface";exit 5; fi
done
test ! -e "$LAB" || { echo ABORT_TEST_KEY_FOLDER_ALREADY_EXISTS; exit 5; }
test -z "$(ip route show "$TARGET")" || { echo ABORT_TEST_ROUTE_EXISTS; exit 5; }
test -z "$(ss -Hlun | grep ':37983 ' || true)" || { echo ABORT_PORT_BUSY; exit 5; }
mkdir -m 700 "$LAB"
wg genkey > "$LAB/server.key"
wg pubkey < "$LAB/server.key" > "$LAB/server.pub"
wg genkey > "$LAB/client.key"
wg pubkey < "$LAB/client.key" > "$LAB/client.pub"
chmod 600 "$LAB"/*
ip link add "$IFSERVER" type wireguard
wg set "$IFSERVER" listen-port 37983 private-key "$LAB/server.key" peer "$(cat "$LAB/client.pub")" allowed-ips 10.254.220.2/32
ip address add 10.254.220.1/32 dev "$IFSERVER"
ip link set "$IFSERVER" mtu 1120 up
ip link add "$IFCLIENT" type wireguard
wg set "$IFCLIENT" listen-port 0 private-key "$LAB/client.key" peer "$(cat "$LAB/server.pub")" endpoint 94.183.231.158:37981 allowed-ips "$TARGET" persistent-keepalive 3
ip address add 10.254.220.2/32 dev "$IFCLIENT"
ip link set "$IFCLIENT" mtu 1120 up
ip route add "$TARGET" dev "$IFCLIENT" metric 999
echo "WG_LAB_READY service_port=37983 iran_mux_port=37981 route_only=$TARGET $(date -u +%FT%TZ)"
read_bytes() { cat "/sys/class/net/$IFSERVER/statistics/rx_bytes"; }
before=$(read_bytes)
ping -n -I "$IFCLIENT" -c 180 -i 0.15 -W 1 198.18.66.1 > "$LAB/ping-out.txt" 2>&1 || true
after=$(read_bytes)
echo "WG_LAB_REPORT $(date -u +%FT%TZ)"
echo "WG_SERVER_TUN_RX_BYTE_DELTA=$((after-before))"
echo "WG_SERVER_TUN_RX_PACKETS=$(cat /sys/class/net/$IFSERVER/statistics/rx_packets)"
echo "WG_CLIENT_HANDSHAKES_RECENT=$(wg show "$IFCLIENT" latest-handshakes | awk -v now="$(date +%s)" '{if ($2>0 && now-$2<60) n++}END{print n+0}')"
echo "WG_SERVER_HANDSHAKES_RECENT=$(wg show "$IFSERVER" latest-handshakes | awk -v now="$(date +%s)" '{if ($2>0 && now-$2<60) n++}END{print n+0}')"
echo "WG_CLIENT_TRANSFER" 
wg show "$IFCLIENT" transfer | awk '{print "peer_download_bytes="$2,"peer_upload_bytes="$3}'
echo "WG_SERVER_TRANSFER"
wg show "$IFSERVER" transfer | awk '{print "peer_download_bytes="$2,"peer_upload_bytes="$3}'
echo "PING_SUMMARY"
tail -5 "$LAB/ping-out.txt"