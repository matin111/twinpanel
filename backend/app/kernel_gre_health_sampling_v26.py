from __future__ import annotations

import shlex

from . import kernel_gre_auto_v21 as v21


# ============================================================
# TWINPANEL KERNEL GRE HEALTH SAMPLING V26
#
# V21 used 5 ICMP samples while enforcing a 5% packet-loss ceiling. With only
# five samples, one ordinary lost reply is reported as 20% loss, so the probe
# cannot represent the configured 5% threshold at all. Production audit on
# Tunnel #5 reproduced exactly that pattern: service/interface/address stayed
# healthy while one of five Exit-side replies was intermittently lost.
#
# V26 keeps the same 5% acceptance threshold and all existing V20 failure
# confirmations. It only raises the bounded health sample to 20 packets, the
# minimum count where one lost reply equals 5% and two lost replies equal 10%.
# No throughput test is introduced into the manager loop.
# ============================================================


KERNEL_GRE_HEALTH_PING_COUNT = 20
KERNEL_GRE_HEALTH_PING_INTERVAL = 0.1


async def peer_snapshot_v26(
    conn,
    *,
    interface: str,
    local_ip: str,
    peer_ip: str,
    service: str,
) -> dict:
    command = f'''
set +e
SERVICE_STATE="$(systemctl is-active {shlex.quote(service)} 2>/dev/null || true)"

echo "TP_SERVICE_STATE=$SERVICE_STATE"

ip link show dev {shlex.quote(interface)} >/dev/null 2>&1
IFACE_RC=$?
echo "TP_IFACE_RC=$IFACE_RC"

ip -4 addr show dev {shlex.quote(interface)} 2>/dev/null | grep -qw {shlex.quote(local_ip)}
ADDR_RC=$?
echo "TP_ADDR_RC=$ADDR_RC"

PING_OUT="$(ping -I {shlex.quote(interface)} -c {KERNEL_GRE_HEALTH_PING_COUNT} -i {KERNEL_GRE_HEALTH_PING_INTERVAL} -W 2 {shlex.quote(peer_ip)} 2>&1 || true)"
printf '%s\n' "$PING_OUT"

true
'''

    result = await conn.run(
        command,
        check=False,
        timeout=20,
    )

    text = (result.stdout or "") + "\n" + (result.stderr or "")
    service_state = v21._parse_marker(text, "TP_SERVICE_STATE")
    iface_rc = v21._parse_marker(text, "TP_IFACE_RC")
    addr_rc = v21._parse_marker(text, "TP_ADDR_RC")
    loss = v21._loss(text)
    latency = v21._latency(text)

    ok = bool(
        service_state == "active"
        and iface_rc == "0"
        and addr_rc == "0"
        and loss is not None
        and loss <= v21.MAX_AUTO_PACKET_LOSS_PCT
        and latency is not None
    )

    return {
        "ok": ok,
        "service_state": service_state,
        "iface_ok": iface_rc == "0",
        "address_ok": addr_rc == "0",
        "latency_ms": latency,
        "packet_loss_pct": loss,
        "sample_count": KERNEL_GRE_HEALTH_PING_COUNT,
        "telemetry_source": "kernel_gre_v26_bidirectional_l3_20_sample",
    }


def install_kernel_gre_health_sampling_v26() -> None:
    v21._peer_snapshot = peer_snapshot_v26

    print(
        "TWINPANEL_KERNEL_GRE_HEALTH_SAMPLING_V26_ACTIVE "
        f"samples={KERNEL_GRE_HEALTH_PING_COUNT} "
        f"interval={KERNEL_GRE_HEALTH_PING_INTERVAL}s "
        f"loss_limit={v21.MAX_AUTO_PACKET_LOSS_PCT}%",
        flush=True,
    )
