#!/usr/bin/env bash
set -uo pipefail
cd /opt/twinpanel/current/backend || exit 5
export CLASSIC_DIRECT_NODE_IDS=1,6,7,11
export CLASSIC_DIRECT_BATCH_PER_NODE=8
export CLASSIC_DIRECT_MAX_CYCLES=240
for protocol in openvpn cisco l2tp; do
  export CLASSIC_ONLY_PROTOCOL="$protocol"
  echo "SEQUENTIAL_PROTOCOL_STARTED protocol=$protocol"
  tmpfile="$(mktemp /run/twinpanel-classic-phase.XXXXXX)"
  /opt/twinpanel/venv/bin/python3 -u /opt/twinpanel/runtime/classic_sequential_protocol_v2.py >"$tmpfile" 2>&1
  rc=$?
  grep -E 'CLASSIC_DIRECT_COMMITTED|CLASSIC_NODE_DONE|CLASSIC_CYCLE_COMPLETE|CLASSIC_DIRECT_DONE|CLASSIC_DIRECT_ERROR|SAFETY_STOP|API_UNHEALTHY' "$tmpfile" | tail -35
  if [[ "$rc" -ne 0 ]] || ! grep -q '^CLASSIC_DIRECT_DONE' "$tmpfile"; then
    echo "SEQUENTIAL_PROTOCOL_STOPPED protocol=$protocol exit=$rc"
    rm -f "$tmpfile"
    exit 2
  fi
  rm -f "$tmpfile"
  echo "SEQUENTIAL_PROTOCOL_COMPLETED protocol=$protocol"
done
echo "SEQUENTIAL_CLASSIC_PHASES_COMPLETE protocols=openvpn,cisco,l2tp"
echo "WIREGUARD_HELD capacity_requires_preflight"