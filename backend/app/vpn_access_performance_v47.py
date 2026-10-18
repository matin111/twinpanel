from __future__ import annotations

import asyncio
import shlex

from .database import SessionLocal
from .models import Node, NodeProtocolConfig, NodeType
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL VPN ACCESS PERFORMANCE V47
#
# User-facing Cisco/OpenConnect, OpenVPN and WireGuard sessions terminate on
# Exit nodes, while their encrypted carrier packets can be forwarded through an
# Iran -> Exit overlay whose effective L3 MTU is as low as 1280 bytes.
#
# V46 fixed Exit forwarding/NAT, but its WAN-side --clamp-mss-to-pmtu sees the
# physical Exit WAN (normally MTU 1500), not the nested Iran -> Exit carrier.
# That leaves TCP sessions free to negotiate packets which are too large for
# the overlay. The result is fragmentation/retransmission, extreme loaded
# latency and very low throughput even though the VPN handshake is healthy.
#
# V47 owns only a dedicated mangle chain and protocol MTU persistence. It does
# not modify tunnel election, routes, DNAT/SNAT ownership, authentication or
# V2Ray/Xray. The 1200-byte access MTU leaves bounded headroom for the minimum
# supported 1280-byte transport MTU (Netrix/AmneziaWG/SSH relay), while 1160
# TCP MSS keeps an IPv4 TCP packet at 1200 bytes before VPN encapsulation.
# ============================================================

RECONCILE_INTERVAL_SECONDS = 30.0
ACCESS_MTU = 1200
ACCESS_TCP_MSS = 1160

_PROTOCOL_SUBNETS = {
    "cisco": "10.91.0.0/24",
    "openvpn": "10.92.0.0/24",
    "wireguard": "10.93.0.0/24",
    "l2tp": "10.94.0.0/24",
}

_last_fingerprint: dict[int, tuple[str, ...]] = {}


def _status_text(value) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _enabled_access_protocols(db, node_id: int) -> set[str]:
    rows = (
        db.query(NodeProtocolConfig)
        .filter(NodeProtocolConfig.node_id == int(node_id))
        .all()
    )

    return {
        str(row.protocol or "").strip().lower()
        for row in rows
        if (
            str(row.protocol or "").strip().lower() in _PROTOCOL_SUBNETS
            and _status_text(row.status) == "online"
        )
    }


def _performance_script(protocols: set[str]) -> str:
    subnets = sorted(
        _PROTOCOL_SUBNETS[name]
        for name in protocols
        if name in _PROTOCOL_SUBNETS
    )

    subnet_lines = "\n".join(
        f"add_subnet {shlex.quote(subnet)}"
        for subnet in subnets
    )

    cisco_enabled = "1" if "cisco" in protocols else "0"
    openvpn_enabled = "1" if "openvpn" in protocols else "0"
    wireguard_enabled = "1" if "wireguard" in protocols else "0"

    return f"""
set -e

ACCESS_MTU={ACCESS_MTU}
ACCESS_MSS={ACCESS_TCP_MSS}
CISCO_ENABLED={cisco_enabled}
OPENVPN_ENABLED={openvpn_enabled}
WIREGUARD_ENABLED={wireguard_enabled}

WAN="$(ip -o -4 route show default | awk '{{for(i=1;i<=NF;i++) if($i==\"dev\"){{print $(i+1); exit}}}}')"
[ -n "$WAN" ]
ip link show dev "$WAN" >/dev/null 2>&1

sysctl -w net.ipv4.ip_forward=1 >/dev/null
sysctl -w net.ipv4.tcp_mtu_probing=1 >/dev/null

ipt() {{ iptables -w 5 "$@"; }}

ipt -t mangle -N TP_ACCESS_PERF 2>/dev/null || true
ipt -t mangle -C FORWARD -j TP_ACCESS_PERF 2>/dev/null || \
  ipt -t mangle -I FORWARD 1 -j TP_ACCESS_PERF
ipt -t mangle -F TP_ACCESS_PERF

add_subnet() {{
  SUBNET="$1"

  # Client -> Internet SYN. This controls the maximum TCP payload that the
  # Internet peer may send back through the nested access VPN.
  ipt -t mangle -A TP_ACCESS_PERF \
    -s "$SUBNET" -o "$WAN" -p tcp \
    --tcp-flags SYN,RST SYN \
    -j TCPMSS --set-mss "$ACCESS_MSS"

  # Internet -> client SYN/SYN-ACK. This also bounds client upload segments,
  # so both speed-test directions stay below the minimum overlay MTU.
  ipt -t mangle -A TP_ACCESS_PERF \
    -d "$SUBNET" -i "$WAN" -p tcp \
    --tcp-flags SYN,RST SYN \
    -j TCPMSS --set-mss "$ACCESS_MSS"
}}

{subnet_lines}

set_iface_mtu() {{
  IFACE="$1"
  [ -n "$IFACE" ] || return 0
  ip link show dev "$IFACE" >/dev/null 2>&1 || return 0
  CURRENT="$(cat "/sys/class/net/$IFACE/mtu" 2>/dev/null || true)"
  if [ "$CURRENT" != "$ACCESS_MTU" ]; then
    ip link set dev "$IFACE" mtu "$ACCESS_MTU"
    echo "MTU_CHANGED=$IFACE:$CURRENT->$ACCESS_MTU"
  fi
}}

# Persist MTU for services managed by TwinPanel. Runtime MTU is also repaired
# below, so existing sessions benefit without waiting for a service restart.
python3 - <<'PY_REMOTE'
from pathlib import Path
import re

ACCESS_MTU = {ACCESS_MTU}
CISCO_ENABLED = {cisco_enabled}
OPENVPN_ENABLED = {openvpn_enabled}
WIREGUARD_ENABLED = {wireguard_enabled}


def replace_or_append(path: str, pattern: str, line: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(pattern, text, flags=re.MULTILINE):
        updated = re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
    else:
        updated = text.rstrip() + "\\n" + line + "\\n"
    if updated == text:
        return False
    backup = p.with_name(p.name + ".twinpanel-v47.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    p.write_text(updated, encoding="utf-8")
    return True


if CISCO_ENABLED:
    if replace_or_append(
        "/etc/ocserv/ocserv.conf",
        r"^\\s*mtu\\s*=.*$",
        f"mtu = {{ACCESS_MTU}}",
    ):
        print("CISCO_CONFIG_MTU=CHANGED")
        Path("/run/twinpanel-v47-ocserv-reload").touch()

if OPENVPN_ENABLED:
    if replace_or_append(
        "/etc/openvpn/server/twinpanel.conf",
        r"^\\s*tun-mtu\\s+.*$",
        f"tun-mtu {{ACCESS_MTU}}",
    ):
        print("OPENVPN_CONFIG_MTU=CHANGED")

if WIREGUARD_ENABLED:
    p = Path("/etc/wireguard/wg-access0.conf")
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"(?m)^\\s*MTU\\s*=.*$", text):
            updated = re.sub(
                r"(?m)^\\s*MTU\\s*=.*$",
                f"MTU = {{ACCESS_MTU}}",
                text,
                count=1,
            )
        else:
            match = re.search(r"(?m)^\\[Interface\\]\\s*$", text)
            if match:
                pos = match.end()
                updated = text[:pos] + f"\\nMTU = {{ACCESS_MTU}}" + text[pos:]
            else:
                updated = text
        if updated != text:
            backup = p.with_name(p.name + ".twinpanel-v47.bak")
            if not backup.exists():
                backup.write_text(text, encoding="utf-8")
            p.write_text(updated, encoding="utf-8")
            print("WIREGUARD_CONFIG_MTU=CHANGED")
PY_REMOTE

if [ "$CISCO_ENABLED" = 1 ]; then
  for IFACE in $(ls /sys/class/net 2>/dev/null | grep '^vpns' || true); do
    set_iface_mtu "$IFACE"
  done
fi

if [ "$OPENVPN_ENABLED" = 1 ]; then
  OVPN_IF="$(ip -o -4 addr show | awk 'index($4,\"10.92.0.1/\")==1 {{print $2; exit}}')"
  set_iface_mtu "$OVPN_IF"
fi

if [ "$WIREGUARD_ENABLED" = 1 ]; then
  WG_IF="$(ip -o -4 addr show | awk 'index($4,\"10.93.0.1/\")==1 {{print $2; exit}}')"
  [ -n "$WG_IF" ] || WG_IF=wg-access0
  set_iface_mtu "$WG_IF"
fi

# ocserv supports configuration reload via SIGHUP. Trigger it only when this
# pass actually changed the persistent MTU; existing sessions are not forced
# through a destructive full service restart.
if [ "$CISCO_ENABLED" = 1 ] && [ -e /run/twinpanel-v47-ocserv-reload ]; then
  if systemctl is-active --quiet ocserv.service; then
    systemctl kill -s HUP ocserv.service || true
  fi
  rm -f /run/twinpanel-v47-ocserv-reload
fi

echo "WAN=$WAN"
echo "ACCESS_MTU=$ACCESS_MTU"
echo "ACCESS_MSS=$ACCESS_MSS"
ipt -t mangle -S TP_ACCESS_PERF
""".strip()


async def _reconcile_node(node_id: int) -> None:
    db = SessionLocal()
    conn = None

    try:
        node = db.get(Node, int(node_id))
        if (
            node is None
            or node.node_type != NodeType.EXIT
            or getattr(node, "retired_at", None) is not None
        ):
            return

        protocols = _enabled_access_protocols(db, int(node.id))
        if not protocols:
            return

        conn = await ssh_connect_saved(node, db)
        result = await conn.run(
            _performance_script(protocols),
            check=False,
            timeout=60,
        )

        text = (
            str(result.stdout or "")
            + "\n"
            + str(result.stderr or "")
        ).strip()

        if result.exit_status != 0:
            raise RuntimeError(
                "vpn_access_performance_failed: "
                + text[-2500:]
            )

        fingerprint = tuple(sorted(protocols))
        previous = _last_fingerprint.get(int(node.id))
        if previous != fingerprint or "=CHANGED" in text:
            print(
                "TWINPANEL_VPN_ACCESS_PERFORMANCE_V47 "
                f"node={node.id} "
                f"protocols={','.join(fingerprint)} "
                f"mtu={ACCESS_MTU} mss={ACCESS_TCP_MSS} "
                f"detail={text[-1200:]}",
                flush=True,
            )
            _last_fingerprint[int(node.id)] = fingerprint

    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()
        db.close()


async def reconcile_once() -> None:
    db = SessionLocal()
    try:
        node_ids = [
            int(row[0])
            for row in (
                db.query(Node.id)
                .filter(
                    Node.node_type == NodeType.EXIT,
                    Node.retired_at.is_(None),
                )
                .order_by(Node.id.asc())
                .all()
            )
        ]
    finally:
        db.close()

    semaphore = asyncio.Semaphore(2)

    async def run_one(node_id: int) -> None:
        async with semaphore:
            try:
                await _reconcile_node(node_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    "TWINPANEL_VPN_ACCESS_PERFORMANCE_V47_ERROR "
                    f"node={node_id} "
                    f"error={type(exc).__name__}:{str(exc)[:900]}",
                    flush=True,
                )

    await asyncio.gather(
        *(run_one(node_id) for node_id in node_ids)
    )


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_VPN_ACCESS_PERFORMANCE_V47_START "
        f"access_mtu={ACCESS_MTU} "
        f"tcp_mss={ACCESS_TCP_MSS} "
        "protocols=cisco,openvpn,wireguard,l2tp "
        "v2ray=untouched",
        flush=True,
    )

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "TWINPANEL_VPN_ACCESS_PERFORMANCE_V47_PASS_ERROR "
                f"error={type(exc).__name__}:{str(exc)[:900]}",
                flush=True,
            )

        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
