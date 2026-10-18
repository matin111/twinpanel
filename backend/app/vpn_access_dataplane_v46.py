from __future__ import annotations

import asyncio
import shlex

from .database import SessionLocal
from .models import Node, NodeProtocolConfig, NodeType
from .protocol_identity import is_openvpn_central_pki_enabled
from .routers.provision import ssh_connect_saved, stage_openvpn_central_identity


# ============================================================
# TWINPANEL VPN ACCESS DATAPLANE V46
#
# Xray is a userspace proxy and does not need kernel forwarding for a
# per-client RFC1918 pool. Cisco/OpenConnect, OpenVPN, WireGuard and L2TP do.
# Their client traffic is created on the Exit node and must be forwarded/NATed
# to the Exit WAN regardless of which Iran -> Exit transport is currently
# active (or whether direct Exit access is being used).
#
# Older service routing tied Exit egress rules to a selected tunnel's
# service_routes. That made the control-plane/handshake look healthy while
# inner VPN traffic had no Internet when those route rows were absent/stale.
# This reconciler makes service egress an Exit-service responsibility instead
# of a tunnel-election side effect.
# ============================================================

RECONCILE_INTERVAL_SECONDS = 30.0
OPENVPN_PKI_REFRESH_SECONDS = 300.0

_PROTOCOL_SUBNETS = {
    "cisco": "10.91.0.0/24",
    "openvpn": "10.92.0.0/24",
    "wireguard": "10.93.0.0/24",
    "l2tp": "10.94.0.0/24",
}

_last_openvpn_pki_check: dict[int, float] = {}
_last_egress_fingerprint: dict[int, tuple[str, ...]] = {}


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


def _protocol_config(db, node_id: int, protocol: str):
    return (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )


def _egress_script(subnets: list[str]) -> str:
    subnet_lines = "\n".join(
        f"add_subnet {shlex.quote(subnet)}"
        for subnet in subnets
    )

    return f"""
set -e

WAN="$(ip -o -4 route show default | awk '{{for(i=1;i<=NF;i++) if($i==\"dev\"){{print $(i+1); exit}}}}')"
[ -n "$WAN" ]
ip link show dev "$WAN" >/dev/null 2>&1

sysctl -w net.ipv4.ip_forward=1 >/dev/null

ipt() {{ iptables -w 5 "$@"; }}

ipt -t nat -N TP_ACCESS_EGRESS 2>/dev/null || true
ipt -t filter -N TP_ACCESS_FWD 2>/dev/null || true
ipt -t mangle -N TP_ACCESS_MSS 2>/dev/null || true

ipt -t nat -C POSTROUTING -j TP_ACCESS_EGRESS 2>/dev/null || \
  ipt -t nat -I POSTROUTING 1 -j TP_ACCESS_EGRESS
ipt -t filter -C FORWARD -j TP_ACCESS_FWD 2>/dev/null || \
  ipt -t filter -I FORWARD 1 -j TP_ACCESS_FWD
ipt -t mangle -C FORWARD -j TP_ACCESS_MSS 2>/dev/null || \
  ipt -t mangle -I FORWARD 1 -j TP_ACCESS_MSS

ipt -t nat -F TP_ACCESS_EGRESS
ipt -t filter -F TP_ACCESS_FWD
ipt -t mangle -F TP_ACCESS_MSS

add_subnet() {{
  SUBNET="$1"

  ipt -t nat -A TP_ACCESS_EGRESS \
    -s "$SUBNET" -o "$WAN" -j MASQUERADE

  ipt -t filter -A TP_ACCESS_FWD \
    -s "$SUBNET" -o "$WAN" -j ACCEPT

  ipt -t filter -A TP_ACCESS_FWD \
    -d "$SUBNET" -i "$WAN" \
    -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

  ipt -t mangle -A TP_ACCESS_MSS \
    -s "$SUBNET" -o "$WAN" -p tcp \
    --tcp-flags SYN,RST SYN \
    -j TCPMSS --clamp-mss-to-pmtu
}}

{subnet_lines}

echo "WAN=$WAN"
ipt -t nat -S TP_ACCESS_EGRESS
ipt -t filter -S TP_ACCESS_FWD
""".strip()


async def _reconcile_exit_egress(conn, subnets: list[str]) -> str:
    result = await conn.run(
        _egress_script(subnets),
        check=False,
        timeout=45,
    )

    text = (
        str(result.stdout or "")
        + "\n"
        + str(result.stderr or "")
    ).strip()

    if result.exit_status != 0:
        raise RuntimeError(
            "vpn_access_egress_failed: "
            + text[-2500:]
        )

    return text[-2500:]


async def _ensure_openvpn_central_runtime(
    conn,
    db,
    node: Node,
    cfg: NodeProtocolConfig,
) -> dict:
    """Align the running OpenVPN server with Central PKI when enabled.

    Client delivery already issues certificates from Central PKI when the
    feature switch is enabled. The server must therefore trust the same CA.
    This function is intentionally a no-op while the migration switch is off.
    """

    if not is_openvpn_central_pki_enabled(db):
        return {"enabled": False, "changed": False}

    await stage_openvpn_central_identity(
        conn,
        db,
        node,
    )

    transport = str(cfg.transport or "udp").strip().lower()
    if transport not in {"udp", "tcp"}:
        transport = "udp"

    port = int(cfg.port or 1194)
    ss_flag = "-lun" if transport == "udp" else "-ltn"

    script = f"""
set -e

CONF=/etc/openvpn/server/twinpanel.conf
CENTRAL=/etc/openvpn/twinpanel-central
BACKUP=/run/twinpanel-openvpn-v46.conf.bak

[ -s "$CONF" ]
[ -s "$CENTRAL/ca.crt" ]
[ -s "$CENTRAL/server.crt" ]
[ -s "$CENTRAL/server.key" ]

openssl verify -CAfile "$CENTRAL/ca.crt" "$CENTRAL/server.crt" >/dev/null

CERT_PUB="$(openssl x509 -in "$CENTRAL/server.crt" -pubkey -noout | \
  openssl pkey -pubin -outform DER 2>/dev/null | sha256sum | awk '{{print $1}}')"
KEY_PUB="$(openssl pkey -in "$CENTRAL/server.key" -pubout -outform DER 2>/dev/null | \
  sha256sum | awk '{{print $1}}')"
[ -n "$CERT_PUB" ]
[ "$CERT_PUB" = "$KEY_PUB" ]

if grep -qx 'ca /etc/openvpn/twinpanel-central/ca.crt' "$CONF" && \
   grep -qx 'cert /etc/openvpn/twinpanel-central/server.crt' "$CONF" && \
   grep -qx 'key /etc/openvpn/twinpanel-central/server.key' "$CONF" && \
   systemctl is-active --quiet openvpn-server@twinpanel && \
   ss -H {ss_flag} 'sport = :{port}' | grep -q .; then
  echo OPENVPN_CENTRAL_PKI=READY
  exit 0
fi

cp -a "$CONF" "$BACKUP"

python3 - <<'PY_REMOTE'
from pathlib import Path
import re

path = Path('/etc/openvpn/server/twinpanel.conf')
text = path.read_text(encoding='utf-8')
replacements = {{
    'ca': '/etc/openvpn/twinpanel-central/ca.crt',
    'cert': '/etc/openvpn/twinpanel-central/server.crt',
    'key': '/etc/openvpn/twinpanel-central/server.key',
}}
for directive, value in replacements.items():
    pattern = rf'(?m)^{{directive}}\\s+.*$'
    line = f'{{directive}} {{value}}'
    if re.search(pattern, text):
        text = re.sub(pattern, line, text, count=1)
    else:
        text += '\\n' + line + '\\n'
path.write_text(text, encoding='utf-8')
PY_REMOTE

if ! systemctl restart openvpn-server@twinpanel; then
  cp -a "$BACKUP" "$CONF"
  systemctl restart openvpn-server@twinpanel || true
  exit 41
fi

sleep 1

if ! systemctl is-active --quiet openvpn-server@twinpanel || \
   ! ss -H {ss_flag} 'sport = :{port}' | grep -q .; then
  cp -a "$BACKUP" "$CONF"
  systemctl restart openvpn-server@twinpanel || true
  exit 42
fi

mkdir -p /etc/twinpanel/managed-identities
chmod 700 /etc/twinpanel/managed-identities
touch /etc/twinpanel/managed-identities/openvpn-central-active

echo OPENVPN_CENTRAL_PKI=ACTIVATED
""".strip()

    result = await conn.run(
        script,
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
            "openvpn_central_pki_runtime_failed: "
            + text[-2500:]
        )

    return {
        "enabled": True,
        "changed": "ACTIVATED" in text,
        "detail": text[-1200:],
    }


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

        protocols = _enabled_access_protocols(
            db,
            int(node.id),
        )

        subnets = sorted(
            _PROTOCOL_SUBNETS[name]
            for name in protocols
        )

        conn = await ssh_connect_saved(
            node,
            db,
        )

        await _reconcile_exit_egress(
            conn,
            subnets,
        )

        fingerprint = tuple(subnets)
        previous = _last_egress_fingerprint.get(
            int(node.id)
        )

        if previous != fingerprint:
            print(
                "TWINPANEL_VPN_ACCESS_EGRESS_V46 "
                f"node={node.id} "
                f"protocols={','.join(sorted(protocols)) or 'none'} "
                f"subnets={','.join(subnets) or 'none'}",
                flush=True,
            )
            _last_egress_fingerprint[
                int(node.id)
            ] = fingerprint

        cfg = _protocol_config(
            db,
            int(node.id),
            "openvpn",
        )

        loop = asyncio.get_running_loop()
        last = _last_openvpn_pki_check.get(
            int(node.id),
            0.0,
        )

        if (
            cfg is not None
            and _status_text(cfg.status) == "online"
            and (
                loop.time() - last
                >= OPENVPN_PKI_REFRESH_SECONDS
            )
        ):
            _last_openvpn_pki_check[
                int(node.id)
            ] = loop.time()

            pki = await _ensure_openvpn_central_runtime(
                conn,
                db,
                node,
                cfg,
            )

            if pki.get("changed"):
                print(
                    "TWINPANEL_OPENVPN_CENTRAL_PKI_V46 "
                    f"node={node.id} status=activated",
                    flush=True,
                )

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

    # Keep SSH load bounded. Two Exit nodes at a time is enough for a
    # 30-second repair loop and avoids a fleet-wide reconnect burst.
    semaphore = asyncio.Semaphore(2)

    async def run_one(node_id: int) -> None:
        async with semaphore:
            try:
                await _reconcile_node(node_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    "TWINPANEL_VPN_ACCESS_V46_ERROR "
                    f"node={node_id} "
                    f"error={type(exc).__name__}:{str(exc)[:900]}",
                    flush=True,
                )

    await asyncio.gather(
        *(run_one(node_id) for node_id in node_ids)
    )


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_VPN_ACCESS_DATAPLANE_V46_START "
        "egress_owner=exit-service "
        "protocols=cisco,openvpn,wireguard,l2tp",
        flush=True,
    )

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "TWINPANEL_VPN_ACCESS_DATAPLANE_V46_PASS_ERROR "
                f"error={type(exc).__name__}:{str(exc)[:900]}",
                flush=True,
            )

        await asyncio.sleep(
            RECONCILE_INTERVAL_SECONDS
        )
