#!/usr/bin/env bash
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
echo "DUAL_UDP_CANARY_FAULT_BEGIN $(date -u +%FT%TZ)"
test "$(systemctl is-active twintunnel-lab@entry-udp.service)" = active
test "$(systemctl is-active twintunnel-lab@entry.service)" = active
systemctl show twintunnel-lab@entry.service --property=ExecStart --value | grep -F '/etc/twintunnel-test/entry.toml' >/dev/null
test -e /opt/twintunnel-test/udp_failover_canary_probe.py
restore_gre() {
  echo "DUAL_UDP_CANARY_RESTORE_GRE $(date -u +%FT%TZ)"
  systemctl start twintunnel-lab@entry.service
  echo "GRE_AFTER_TEST=$(systemctl is-active twintunnel-lab@entry.service)"
}
trap restore_gre EXIT
TT_CANARY_COUNT=300 TT_CANARY_PORT=37962 python3 -u /opt/twintunnel-test/udp_failover_canary_probe.py > /opt/twintunnel-test/results/udp-redundant-live-20261117.log 2>&1 &
probe=$!
echo "SENDING_PROBE_PID=$probe"
sleep 5
if ! kill -0 "$probe" 2>/dev/null; then echo "PROBE_ENDED_TOO_EARLY"; wait "$probe"; exit 4; fi
echo "DUAL_UDP_CANARY_CUT_GRE $(date -u +%FT%TZ)"
systemctl stop twintunnel-lab@entry.service
echo "GRE_STATE_AFTER_CUT=$(systemctl is-active twintunnel-lab@entry.service || true)"
sleep 8
echo "DUAL_UDP_CANARY_RESTORE_GRE_DURING_PROBE $(date -u +%FT%TZ)"
systemctl start twintunnel-lab@entry.service
echo "GRE_STATE_AFTER_RESTORE=$(systemctl is-active twintunnel-lab@entry.service)"
if ! kill -0 "$probe" 2>/dev/null; then echo "PROBE_FINISHED_BEFORE_RESTORE"; fi
wait "$probe"
echo "DUAL_UDP_CANARY_PROBE_DONE $(date -u +%FT%TZ)"
tail -12 /opt/twintunnel-test/results/udp-redundant-live-20261117.log
echo "OTHER_LAB_SERVICES"
systemctl is-active twintunnel-lab@entry.service twintunnel-lab@entry-udp.service twintunnel-lab@entry-multilink.service