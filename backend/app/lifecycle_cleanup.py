from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path

import asyncssh
from sqlalchemy.orm import Session

from .models import (
    Node,
    NodeAccess,
    NodeProtocolConfig,
    NodeType,
    Tunnel,
    TunnelTransport,
)
from .routers.provision import ssh_connect_saved
from .ssh_tunnel import (
    ssh_tunnel_interface,
    ssh_tunnel_number,
    ssh_tunnel_services,
    ssh_tunnel_user,
)
from .ssh_relay import (
    relay_config,
    relay_interface,
    relay_services,
)


# ============================================================
# TWINPANEL MANAGED LIFECYCLE CLEANUP V1
# ============================================================


def _error_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)

    if detail:
        return str(detail)

    return str(exc) or repr(exc)


async def _remote(
    node: Node,
    db: Session,
    script: str,
    label: str,
):
    conn = None

    try:
        conn = await ssh_connect_saved(
            node,
            db,
        )

        result = await conn.run(
            script,
            check=False,
        )

        if result.exit_status != 0:
            message = (
                result.stderr
                or result.stdout
                or f"exit={result.exit_status}"
            )

            raise RuntimeError(
                f"{label}: {message[-1200:]}"
            )

        return result.stdout

    except Exception as exc:
        raise RuntimeError(
            f"{label}: {_error_text(exc)}"
        ) from exc

    finally:
        if conn:
            conn.close()
            await conn.wait_closed()


# ============================================================
# SSH TUNNEL
# ============================================================


async def cleanup_ssh_tunnel_runtime(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
):
    tid = int(tunnel.id)

    # Tunnel 30 uses historical TP27 runtime.
    # Do not destroy it through the generic cleaner.
    if tid == 30:
        raise RuntimeError(
            "tunnel_30_is_legacy_protected"
        )

    number = ssh_tunnel_number(tunnel)
    iface = ssh_tunnel_interface(tunnel)
    user = ssh_tunnel_user(tunnel)

    iran_service, exit_service = (
        ssh_tunnel_services(tunnel)
    )

    key_dir = f"/etc/twinpanel/tp{number}-ssh"

    await _remote(
        iran,
        db,
        f"""
systemctl disable --now {shlex.quote(iran_service)} >/dev/null 2>&1 || true

rm -f /etc/systemd/system/{shlex.quote(iran_service)}
rm -f /usr/local/sbin/tp{number}-iran-up

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true

rm -rf {shlex.quote(key_dir)}

systemctl daemon-reload >/dev/null 2>&1 || true

if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "interface_still_exists={iface}"
    exit 41
fi

if [ -e /etc/systemd/system/{shlex.quote(iran_service)} ]; then
    echo "service_file_still_exists={iran_service}"
    exit 42
fi

if [ -e {shlex.quote(key_dir)} ]; then
    echo "key_dir_still_exists={key_dir}"
    exit 43
fi

exit 0
""",
        f"ssh_tunnel_iran_{tid}",
    )

    await _remote(
        exit_node,
        db,
        f"""
systemctl disable --now {shlex.quote(exit_service)} >/dev/null 2>&1 || true

rm -f /etc/systemd/system/{shlex.quote(exit_service)}
rm -f /usr/local/sbin/tp{number}-exit-up

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true

userdel -r {shlex.quote(user)} >/dev/null 2>&1 || true

systemctl daemon-reload >/dev/null 2>&1 || true

if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "interface_still_exists={iface}"
    exit 44
fi

if [ -e /etc/systemd/system/{shlex.quote(exit_service)} ]; then
    echo "service_file_still_exists={exit_service}"
    exit 45
fi

exit 0
""",
        f"ssh_tunnel_exit_{tid}",
    )

    return {
        "ok": True,
        "transport": "ssh_tun",
        "interface": iface,
    }


# ============================================================
# BACKHAUL
# ============================================================


def backhaul_runtime_values(
    tunnel_id: int,
) -> dict:
    tid = int(tunnel_id)
    slot = 10 + (tid % 230)

    return {
        "interface": f"bh{tid}",
        "iran_addr": f"10.253.{slot}.1/24",
        "exit_addr": f"10.253.{slot}.2/24",
        "iran_ip": f"10.253.{slot}.1",
        "exit_ip": f"10.253.{slot}.2",
        "service": (
            f"twinpanel-backhaul-{tid}.service"
        ),
        "config": (
            f"/etc/twinpanel/backhaul/"
            f"tunnel-{tid}.toml"
        ),
    }


async def cleanup_backhaul_runtime(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
):
    tid = int(tunnel.id)
    runtime = backhaul_runtime_values(tid)

    iface = runtime["interface"]
    service = runtime["service"]
    config = runtime["config"]

    for role, node in (
        ("iran", iran),
        ("exit", exit_node),
    ):
        await _remote(
            node,
            db,
            f"""
systemctl disable --now {shlex.quote(service)} >/dev/null 2>&1 || true

rm -f /etc/systemd/system/{shlex.quote(service)}
rm -f {shlex.quote(config)}

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true

systemctl daemon-reload >/dev/null 2>&1 || true

if systemctl is-active --quiet {shlex.quote(service)}; then
    echo "backhaul_service_still_active={service}"
    exit 51
fi

if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "backhaul_interface_still_exists={iface}"
    exit 52
fi

if [ -e {shlex.quote(config)} ]; then
    echo "backhaul_config_still_exists={config}"
    exit 53
fi

exit 0
""",
            f"backhaul_{role}_{tid}",
        )

    return {
        "ok": True,
        "transport": "backhaul",
        "interface": iface,
    }


# ============================================================
# LEGACY WG TUNNEL
# ============================================================


async def cleanup_legacy_wireguard_runtime(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
):
    tid = int(tunnel.id)
    iface = f"mwg{tid}"[:15]

    for role, node in (
        ("iran", iran),
        ("exit", exit_node),
    ):
        await _remote(
            node,
            db,
            f"""
ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true

rm -f \
  /var/lib/twinpanel-agent/wireguard/{tid}.key \
  /var/lib/twinpanel-agent/wireguard/{tid}.pub \
  /var/lib/moviline-agent/wireguard/{tid}.key \
  /var/lib/moviline-agent/wireguard/{tid}.pub

if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "wireguard_tunnel_interface_still_exists={iface}"
    exit 61
fi

exit 0
""",
            f"legacy_wireguard_{role}_{tid}",
        )

    return {
        "ok": True,
        "transport": "wireguard",
        "interface": iface,
    }


# ============================================================
# MANUAL PER-TUNNEL INGRESS CHAINS
# Includes old emergency TP_PUBLIC_x rules.
# ============================================================


async def cleanup_manual_ingress_runtime(
    tunnel: Tunnel,
    iran: Node,
    db: Session,
):
    tid = int(tunnel.id)

    public_chain = f"TP_PUBLIC_{tid}"
    forward_chain = f"TP_FORWARD_{tid}"
    snat_chain = f"TP_SNAT_{tid}"

    await _remote(
        iran,
        db,
        f"""
while iptables -t nat -C PREROUTING -j {public_chain} >/dev/null 2>&1; do
    iptables -t nat -D PREROUTING -j {public_chain} >/dev/null 2>&1 || break
done

iptables -t nat -F {public_chain} >/dev/null 2>&1 || true
iptables -t nat -X {public_chain} >/dev/null 2>&1 || true


while iptables -t filter -C FORWARD -j {forward_chain} >/dev/null 2>&1; do
    iptables -t filter -D FORWARD -j {forward_chain} >/dev/null 2>&1 || break
done

iptables -t filter -F {forward_chain} >/dev/null 2>&1 || true
iptables -t filter -X {forward_chain} >/dev/null 2>&1 || true


while iptables -t nat -C POSTROUTING -j {snat_chain} >/dev/null 2>&1; do
    iptables -t nat -D POSTROUTING -j {snat_chain} >/dev/null 2>&1 || break
done

iptables -t nat -F {snat_chain} >/dev/null 2>&1 || true
iptables -t nat -X {snat_chain} >/dev/null 2>&1 || true


if iptables -t nat -S 2>/dev/null | grep -qE '({public_chain}|{snat_chain})'; then
    echo "old_nat_chain_still_exists"
    exit 71
fi

if iptables -t filter -S 2>/dev/null | grep -q '{forward_chain}'; then
    echo "old_forward_chain_still_exists"
    exit 72
fi

exit 0
""",
        f"manual_ingress_{tid}",
    )

    return {
        "ok": True,
        "routing": "old_per_tunnel_chains_removed",
    }


# ============================================================
# SSH RELAY
# ============================================================


async def cleanup_ssh_relay_runtime(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
):
    tid = int(tunnel.id)

    cfg = relay_config(
        db,
        tunnel,
    )

    if not cfg:
        return {
            "ok": True,
            "transport": "ssh_relay",
            "skipped": True,
            "reason": "not_configured",
        }

    relay_node_id = int(
        cfg.get("relay_node_id") or 0
    )

    if relay_node_id <= 0:
        raise RuntimeError(
            f"ssh_relay_{tid}: relay_node_id_missing"
        )

    relay = db.get(
        Node,
        relay_node_id,
    )

    if not relay:
        raise RuntimeError(
            f"ssh_relay_{tid}: relay_node_not_found"
        )

    iface = str(
        cfg.get("interface")
        or relay_interface(tunnel)
    )

    (
        default_iran_service,
        default_iran_helper,
        default_exit_helper,
    ) = relay_services(tunnel)

    iran_service = str(
        cfg.get("iran_service")
        or default_iran_service
    )

    iran_helper = str(
        cfg.get("iran_helper")
        or default_iran_helper
    )

    exit_helper = str(
        cfg.get("exit_helper")
        or default_exit_helper
    )

    base = (
        f"/etc/twinpanel/ssh-relay/"
        f"tunnel-{tid}"
    )

    tag_hop = f"tp{tid}-relay-hop"
    tag_exit = f"tp{tid}-relay-exit"

    iran_helper_path = (
        f"/usr/local/sbin/"
        f"tp{tid}-relay-iran-if"
    )

    exit_helper_path = (
        f"/usr/local/sbin/"
        f"tp{tid}-relay-exit-if"
    )

    await _remote(
        iran,
        db,
        f"""
systemctl disable --now \
  {shlex.quote(iran_service)} \
  {shlex.quote(iran_helper)} \
  >/dev/null 2>&1 || true

rm -f \
  /etc/systemd/system/{shlex.quote(iran_service)} \
  /etc/systemd/system/{shlex.quote(iran_helper)} \
  {shlex.quote(iran_helper_path)}

rm -rf {shlex.quote(base)}

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true

systemctl daemon-reload >/dev/null 2>&1 || true

if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "relay_iran_interface_still_exists={iface}"
    exit 81
fi

if [ -e {shlex.quote(base)} ]; then
    echo "relay_base_still_exists={base}"
    exit 82
fi

exit 0
""",
        f"ssh_relay_iran_{tid}",
    )

    await _remote(
        relay,
        db,
        f"""
if [ -f /root/.ssh/authorized_keys ]; then
    grep -v {shlex.quote(tag_hop + '$')} \
      /root/.ssh/authorized_keys \
      > /root/.ssh/authorized_keys.tp-clean || true

    cat /root/.ssh/authorized_keys.tp-clean \
      > /root/.ssh/authorized_keys

    rm -f /root/.ssh/authorized_keys.tp-clean

    chmod 600 /root/.ssh/authorized_keys
fi

if grep -q {shlex.quote(tag_hop + '$')} \
    /root/.ssh/authorized_keys 2>/dev/null; then
    echo "relay_hop_authorized_key_still_exists"
    exit 83
fi

exit 0
""",
        f"ssh_relay_middle_{tid}",
    )

    await _remote(
        exit_node,
        db,
        f"""
systemctl disable --now \
  {shlex.quote(exit_helper)} \
  >/dev/null 2>&1 || true

rm -f \
  /etc/systemd/system/{shlex.quote(exit_helper)} \
  {shlex.quote(exit_helper_path)}

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true


if [ -f /root/.ssh/authorized_keys ]; then
    grep -v {shlex.quote(tag_exit + '$')} \
      /root/.ssh/authorized_keys \
      > /root/.ssh/authorized_keys.tp-clean || true

    cat /root/.ssh/authorized_keys.tp-clean \
      > /root/.ssh/authorized_keys

    rm -f /root/.ssh/authorized_keys.tp-clean

    chmod 600 /root/.ssh/authorized_keys
fi


python3 - <<'PY2'
from pathlib import Path

p = Path("/etc/ssh/sshd_config")

if p.exists():
    s = p.read_text()

    begin = {("# BEGIN TWINPANEL RELAY " + str(tid))!r}
    end = {("# END TWINPANEL RELAY " + str(tid))!r}

    while begin in s and end in s:
        a = s.index(begin)
        b = s.index(end, a) + len(end)
        s = s[:a] + s[b:]

    p.write_text(s)
PY2


if command -v sshd >/dev/null 2>&1; then
    sshd -t

    if [ $? -ne 0 ]; then
        echo "sshd_config_validation_failed"
        exit 84
    fi

    systemctl reload ssh >/dev/null 2>&1 || \
    systemctl reload sshd >/dev/null 2>&1 || true
fi

systemctl daemon-reload >/dev/null 2>&1 || true


if ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "relay_exit_interface_still_exists={iface}"
    exit 85
fi

if grep -q {shlex.quote(tag_exit + '$')} \
    /root/.ssh/authorized_keys 2>/dev/null; then
    echo "relay_exit_authorized_key_still_exists"
    exit 86
fi

if grep -q \
    {shlex.quote("# BEGIN TWINPANEL RELAY " + str(tid))} \
    /etc/ssh/sshd_config 2>/dev/null; then
    echo "relay_sshd_marker_still_exists"
    exit 87
fi

exit 0
""",
        f"ssh_relay_exit_{tid}",
    )

    return {
        "ok": True,
        "transport": "ssh_relay",
        "relay_node_id": relay_node_id,
        "interface": iface,
    }


# ============================================================
# COMPLETE TUNNEL CLEANUP
# ============================================================


async def cleanup_tunnel_runtime(
    tunnel: Tunnel,
    db: Session,
):
    tid = int(tunnel.id)

    iran = db.get(
        Node,
        int(tunnel.iran_node_id),
    )

    exit_node = db.get(
        Node,
        int(tunnel.exit_node_id),
    )

    if not iran:
        raise RuntimeError(
            f"tunnel_{tid}: iran_node_not_found"
        )

    if not exit_node:
        raise RuntimeError(
            f"tunnel_{tid}: exit_node_not_found"
        )

    errors = []
    results = []

    cleaners = (
        (
            "manual_ingress",
            lambda: cleanup_manual_ingress_runtime(
                tunnel,
                iran,
                db,
            ),
        ),
        (
            "ssh_relay",
            lambda: cleanup_ssh_relay_runtime(
                tunnel,
                iran,
                exit_node,
                db,
            ),
        ),
        (
            "backhaul",
            lambda: cleanup_backhaul_runtime(
                tunnel,
                iran,
                exit_node,
                db,
            ),
        ),
        (
            "ssh_tun",
            lambda: cleanup_ssh_tunnel_runtime(
                tunnel,
                iran,
                exit_node,
                db,
            ),
        ),
        (
            "wireguard",
            lambda: cleanup_legacy_wireguard_runtime(
                tunnel,
                iran,
                exit_node,
                db,
            ),
        ),
    )

    for name, factory in cleaners:
        try:
            result = await factory()

            results.append(
                result
            )

        except Exception as exc:
            errors.append(
                f"{name}: {_error_text(exc)}"
            )

    if errors:
        raise RuntimeError(
            " | ".join(errors)[:4000]
        )

    return {
        "ok": True,
        "tunnel_id": tid,
        "results": results,
    }


# ============================================================
# TUNNELS USING A NODE
# Direct Iran/Exit + indirect SSH Relay membership.
# ============================================================


def related_tunnel_ids_for_node(
    db: Session,
    node_id: int,
) -> list[int]:
    target = int(node_id)

    ids = {
        int(row[0])
        for row in (
            db.query(Tunnel.id)
            .filter(
                (Tunnel.iran_node_id == target)
                | (Tunnel.exit_node_id == target)
            )
            .all()
        )
    }

    relay_rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.transport
            == "ssh_relay"
        )
        .all()
    )

    for row in relay_rows:
        if not row.config_text:
            continue

        try:
            cfg = json.loads(
                row.config_text
            )

        except Exception:
            continue

        if not isinstance(cfg, dict):
            continue

        try:
            relay_node_id = int(
                cfg.get("relay_node_id") or 0
            )

        except Exception:
            relay_node_id = 0

        if relay_node_id == target:
            ids.add(
                int(row.tunnel_id)
            )

    return sorted(ids)


# ============================================================
# COMPLETE NODE CLEANUP
# ============================================================


def _controller_public_key(
    db: Session,
    node_id: int,
) -> tuple[str | None, str | None]:
    access = (
        db.query(NodeAccess)
        .filter(
            NodeAccess.node_id
            == int(node_id)
        )
        .first()
    )

    if not access:
        return None, None

    path = str(
        access.private_key_path or ""
    ).strip()

    if not path:
        return None, None

    p = Path(path)

    if not p.exists():
        return None, path

    try:
        key = asyncssh.read_private_key(
            str(p)
        )

        public = (
            key.export_public_key(
                format_name="openssh"
            )
            .decode()
            .strip()
        )

        return public, path

    except Exception:
        return None, path


def _ufw_cleanup_commands(
    db: Session,
    node_id: int,
) -> list[str]:
    commands = []

    rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id
            == int(node_id)
        )
        .all()
    )

    for row in rows:
        port = getattr(
            row,
            "port",
            None,
        )

        transport = str(
            getattr(
                row,
                "transport",
                "",
            )
            or ""
        ).lower()

        if not port:
            continue

        try:
            port = int(port)

        except Exception:
            continue

        if "tcp" in transport:
            commands.append(
                f"ufw --force delete allow "
                f"{port}/tcp >/dev/null 2>&1 || true"
            )

        if "udp" in transport:
            commands.append(
                f"ufw --force delete allow "
                f"{port}/udp >/dev/null 2>&1 || true"
            )

    # TWINPANEL_L2TP_UFW_OWNERSHIP_V1
    # Remove shared IPsec/L2TP ports only when this Node
    # actually has a TwinPanel-managed L2TP configuration.
    l2tp_managed = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol == "l2tp",
        )
        .first()
        is not None
    )

    if l2tp_managed:
        for port in (500, 4500, 1701):
            commands.append(
                f"ufw --force delete allow "
                f"{port}/udp >/dev/null 2>&1 || true"
            )

    return commands


async def cleanup_node_runtime(
    node: Node,
    db: Session,
):
    node_id = int(node.id)

    public_key, key_path = (
        _controller_public_key(
            db,
            node_id,
        )
    )

    ufw_commands = (
        "\n".join(
            _ufw_cleanup_commands(
                db,
                node_id,
            )
        )
    )

    public_key_b64 = (
        base64.b64encode(
            public_key.encode()
        ).decode()
        if public_key
        else ""
    )

    protocol_cleanup = ""

    if node.node_type == NodeType.EXIT:
        # TWINPANEL_MANAGED_PROTOCOL_CLEANUP_V2
        #
        # Generic services/configs are removed ONLY when an
        # ownership marker proves that TwinPanel manages them.
        protocol_cleanup = r"""
MANAGED=/etc/twinpanel/managed-identities

# -------------------------------------------------
# Cisco / OpenConnect
# -------------------------------------------------
if [ -f "$MANAGED/cisco" ]; then
    systemctl disable --now ocserv.service \
      >/dev/null 2>&1 || true

    rm -f \
      /etc/ocserv/ocserv.conf \
      /etc/ocserv/ocpasswd \
      /etc/ocserv/server-key.pem \
      /etc/ocserv/server-cert.pem

    rm -f "$MANAGED/cisco"
fi


# -------------------------------------------------
# OpenVPN
# -------------------------------------------------
if [ -f "$MANAGED/openvpn" ]; then
    systemctl disable --now \
      openvpn-server@twinpanel.service \
      openvpn-server@moviline.service \
      openvpn@twinpanel.service \
      openvpn@moviline.service \
      >/dev/null 2>&1 || true

    rm -f \
      /etc/openvpn/server/twinpanel.conf \
      /etc/openvpn/server/moviline.conf \
      /usr/local/sbin/twinpanel-openvpn-client-connect

    rm -rf \
      /etc/openvpn/twinpanel-central \
      /etc/openvpn/moviline-central \
      /etc/openvpn/twinpanel-disabled \
      /etc/openvpn/easy-rsa

    rm -f "$MANAGED/openvpn"
fi


# -------------------------------------------------
# WireGuard access
# -------------------------------------------------
if [ -f "$MANAGED/wireguard" ]; then
    systemctl disable --now \
      wg-quick@wg-access0.service \
      >/dev/null 2>&1 || true

    ip link del wg-access0 \
      >/dev/null 2>&1 || true

    rm -f \
      /etc/wireguard/wg-access0.conf \
      /etc/wireguard/wg-access0.key \
      /etc/wireguard/wg-access0.pub

    rm -f "$MANAGED/wireguard"
fi


# -------------------------------------------------
# L2TP / IPsec
# -------------------------------------------------
if [ -f "$MANAGED/l2tp" ]; then
    systemctl disable --now \
      xl2tpd.service \
      strongswan-starter.service \
      strongswan.service \
      >/dev/null 2>&1 || true

    rm -f \
      /etc/ipsec.conf \
      /etc/ipsec.secrets \
      /etc/xl2tpd/xl2tpd.conf \
      /etc/ppp/options.xl2tpd \
      /etc/ppp/chap-secrets

    rm -f "$MANAGED/l2tp"
fi


# -------------------------------------------------
# Xray / V2Ray
# -------------------------------------------------
if [ -f "$MANAGED/v2ray" ]; then
    systemctl disable --now xray.service \
      >/dev/null 2>&1 || true

    rm -f \
      /usr/local/etc/xray/config.json \
      /usr/local/etc/xray/config.json.twinpanel-new

    rm -f "$MANAGED/v2ray"
fi
"""

    controller_key_cleanup = ""

    if public_key_b64:
        controller_key_cleanup = f"""
if [ -f /root/.ssh/authorized_keys ]; then
    PUB=$(printf '%s' {shlex.quote(public_key_b64)} | base64 -d)

    grep -vxF "$PUB" \
      /root/.ssh/authorized_keys \
      > /root/.ssh/authorized_keys.tp-node-clean || true

    cat /root/.ssh/authorized_keys.tp-node-clean \
      > /root/.ssh/authorized_keys

    rm -f /root/.ssh/authorized_keys.tp-node-clean

    chmod 600 /root/.ssh/authorized_keys
fi
"""

    await _remote(
        node,
        db,
        f"""
# --------------------------------------------
# Stop TwinPanel / legacy agents
# --------------------------------------------

systemctl disable --now \
  twinpanel-agent.service \
  moviline-agent.service \
  moviline-node-agent.service \
  twinpanel-quota-agent.service \
  moviline-quota-agent.service \
  >/dev/null 2>&1 || true


# --------------------------------------------
# Stop stale per-tunnel managed units
# --------------------------------------------

for UNIT_FILE in \
  /etc/systemd/system/tp*-ssh.service \
  /etc/systemd/system/tp*-exit-tun.service \
  /etc/systemd/system/tp*-relay-ssh.service \
  /etc/systemd/system/tp*-relay-if.service \
  /etc/systemd/system/tp*-relay-exit-if.service \
  /etc/systemd/system/twinpanel-backhaul-*.service
do
    [ -e "$UNIT_FILE" ] || continue

    UNIT=$(basename "$UNIT_FILE")

    systemctl disable --now "$UNIT" \
      >/dev/null 2>&1 || true

    rm -f "$UNIT_FILE"
done


rm -f \
  /etc/systemd/system/twinpanel-agent.service \
  /etc/systemd/system/moviline-agent.service \
  /etc/systemd/system/moviline-node-agent.service \
  /etc/systemd/system/twinpanel-quota-agent.service \
  /etc/systemd/system/moviline-quota-agent.service


rm -f \
  /usr/local/sbin/tp*-iran-up \
  /usr/local/sbin/tp*-exit-up \
  /usr/local/sbin/tp*-relay-iran-if \
  /usr/local/sbin/tp*-relay-exit-if


rm -rf \
  /opt/twinpanel-agent \
  /var/lib/twinpanel-agent \
  /opt/moviline-agent \
  /var/lib/moviline-agent \
  /opt/twinpanel-quota-agent \
  /var/lib/twinpanel-quota-agent \
  /opt/moviline-quota-agent \
  /var/lib/moviline-quota-agent


{protocol_cleanup}


# --------------------------------------------
# TWINPANEL_NODE_FABRIC_CLEANUP_V2
# Remove Tunnel Fabric installed by TwinPanel
# --------------------------------------------

systemctl disable --now \
  twinpanel-tunnel-fabric.service \
  >/dev/null 2>&1 || true

rm -f \
  /etc/systemd/system/twinpanel-tunnel-fabric.service \
  /usr/local/sbin/twinpanel-fabric-prepare \
  /etc/sysctl.d/99-twinpanel-tunnel-fabric.conf \
  /etc/sysctl.d/99-twinpanel.conf

rm -rf \
  /etc/twinpanel/fabric \
  /var/lib/twinpanel-fabric \
  /run/twinpanel-fabric


# --------------------------------------------
# Remove TwinPanel routing chains
# --------------------------------------------

while iptables -t nat -C PREROUTING -j TP_DNAT >/dev/null 2>&1; do
    iptables -t nat -D PREROUTING -j TP_DNAT >/dev/null 2>&1 || break
done

while iptables -t nat -C POSTROUTING -j TP_SNAT >/dev/null 2>&1; do
    iptables -t nat -D POSTROUTING -j TP_SNAT >/dev/null 2>&1 || break
done

while iptables -t nat -C POSTROUTING -j TP_EGRESS >/dev/null 2>&1; do
    iptables -t nat -D POSTROUTING -j TP_EGRESS >/dev/null 2>&1 || break
done

while iptables -t filter -C FORWARD -j TP_FWD >/dev/null 2>&1; do
    iptables -t filter -D FORWARD -j TP_FWD >/dev/null 2>&1 || break
done

while iptables -t filter -C FORWARD -j TP_EGRESS_FWD >/dev/null 2>&1; do
    iptables -t filter -D FORWARD -j TP_EGRESS_FWD >/dev/null 2>&1 || break
done

while iptables -t mangle -C FORWARD -j TP_CISCO_MSS >/dev/null 2>&1; do
    iptables -t mangle -D FORWARD -j TP_CISCO_MSS >/dev/null 2>&1 || break
done


for CHAIN in TP_DNAT TP_SNAT TP_EGRESS; do
    iptables -t nat -F "$CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$CHAIN" >/dev/null 2>&1 || true
done

for CHAIN in TP_FWD TP_EGRESS_FWD; do
    iptables -t filter -F "$CHAIN" >/dev/null 2>&1 || true
    iptables -t filter -X "$CHAIN" >/dev/null 2>&1 || true
done

iptables -t mangle -F TP_CISCO_MSS >/dev/null 2>&1 || true
iptables -t mangle -X TP_CISCO_MSS >/dev/null 2>&1 || true


# Old emergency per-tunnel chains
for CHAIN in $(iptables -t nat -S 2>/dev/null | awk '$1=="-N" && $2 ~ /^TP_PUBLIC_[0-9]+$/ {{print $2}}'); do
    while iptables -t nat -C PREROUTING -j "$CHAIN" >/dev/null 2>&1; do
        iptables -t nat -D PREROUTING -j "$CHAIN" >/dev/null 2>&1 || break
    done

    iptables -t nat -F "$CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$CHAIN" >/dev/null 2>&1 || true
done


for CHAIN in $(iptables -t nat -S 2>/dev/null | awk '$1=="-N" && $2 ~ /^TP_SNAT_[0-9]+$/ {{print $2}}'); do
    while iptables -t nat -C POSTROUTING -j "$CHAIN" >/dev/null 2>&1; do
        iptables -t nat -D POSTROUTING -j "$CHAIN" >/dev/null 2>&1 || break
    done

    iptables -t nat -F "$CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$CHAIN" >/dev/null 2>&1 || true
done


for CHAIN in $(iptables -t filter -S 2>/dev/null | awk '$1=="-N" && $2 ~ /^TP_FORWARD_[0-9]+$/ {{print $2}}'); do
    while iptables -t filter -C FORWARD -j "$CHAIN" >/dev/null 2>&1; do
        iptables -t filter -D FORWARD -j "$CHAIN" >/dev/null 2>&1 || break
    done

    iptables -t filter -F "$CHAIN" >/dev/null 2>&1 || true
    iptables -t filter -X "$CHAIN" >/dev/null 2>&1 || true
done


# --------------------------------------------
# Remove UFW rules created for this node
# --------------------------------------------

if command -v ufw >/dev/null 2>&1; then
{ufw_commands}
fi


# --------------------------------------------
# Remove remaining TwinPanel directories
# --------------------------------------------

rm -rf \
  /etc/twinpanel/ssh-relay \
  /etc/twinpanel/backhaul

rm -f \
  /usr/local/bin/twinpanel-backhaul

# TWINPANEL_MANAGED_IDENTITY_DIR_REMOVE_V1
rm -rf \
  /etc/twinpanel/managed-identities


# Controller SSH key is removed LAST.
{controller_key_cleanup}


systemctl daemon-reload >/dev/null 2>&1 || true


# --------------------------------------------
# Final verification
# --------------------------------------------

if systemctl is-active --quiet twinpanel-agent.service; then
    echo "twinpanel_agent_still_active"
    exit 91
fi

if systemctl is-active --quiet moviline-agent.service; then
    echo "legacy_agent_still_active"
    exit 92
fi

if ip -o link show | grep -Eq ':[[:space:]]+(mwg[0-9]+|bh[0-9]+):'; then
    echo "managed_tunnel_interface_still_exists"
    ip -o link show | grep -E 'mwg[0-9]+|bh[0-9]+' || true
    exit 93
fi

exit 0
""",
        f"node_runtime_{node_id}",
    )

    return {
        "ok": True,
        "node_id": node_id,
        "controller_key_path": key_path,
    }
