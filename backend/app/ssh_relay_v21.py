from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import shlex
from datetime import datetime

from sqlalchemy.orm import Session

from .models import Node, NodeAccess, Tunnel, TunnelTransport
from .ssh_relay import (
    _host_key,
    _known_host_name,
    _member,
    _udp_probe,
    _write,
    relay_addresses,
    relay_interface,
    relay_services,
    verify_ssh_relay,
)
from .ssh_relay_v2 import (
    _pick_local_port,
    _run,
    provision_ssh_relay_v2,
)


class CarrierUnavailable(RuntimeError):
    pass


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def choose_backhaul_carrier(
    db: Session,
    tunnel: Tunnel,
    relay: Node,
) -> Tunnel | None:
    """
    Find an already healthy Backhaul tunnel from the same Iran node
    to the selected relay node.

    V21 never repairs, restarts or reconfigures this carrier.
    """

    candidates = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == int(tunnel.iran_node_id),
            Tunnel.exit_node_id == int(relay.id),
            Tunnel.is_active.is_(True),
            Tunnel.id != int(tunnel.id),
        )
        .order_by(Tunnel.id.asc())
        .all()
    )

    for candidate in candidates:
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(candidate.id),
                TunnelTransport.transport == "backhaul",
            )
            .first()
        )

        if (
            row is not None
            and bool(row.enabled)
            and _status(row.status) == "online"
        ):
            return candidate

    return None


async def _interface_ipv4(
    conn,
    interface: str,
) -> str:
    result = await _run(
        conn,
        (
            f"ip -4 -o addr show dev {shlex.quote(interface)} "
            "2>/dev/null | "
            "awk '{print $4}' | "
            "cut -d/ -f1 | "
            "head -1"
        ),
        check=False,
        timeout=15,
    )

    value = (result.stdout or "").strip()

    if not value:
        raise CarrierUnavailable(
            f"carrier_interface_address_missing:{interface}"
        )

    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise CarrierUnavailable(
            f"carrier_interface_address_invalid:{interface}:{value}"
        ) from exc

    if parsed.version != 4:
        raise CarrierUnavailable(
            f"carrier_interface_not_ipv4:{interface}:{value}"
        )

    return str(parsed)


async def _carrier_runtime(
    ci,
    cr,
    carrier: Tunnel,
    relay_access: NodeAccess,
) -> dict:
    interface = f"bh{int(carrier.id)}"

    iran_ip = await _interface_ipv4(
        ci,
        interface,
    )

    relay_ip = await _interface_ipv4(
        cr,
        interface,
    )

    peer = await _run(
        ci,
        (
            f"LC_ALL=C ping "
            f"-I {shlex.quote(interface)} "
            "-c 3 -i 0.20 -W 2 "
            f"{shlex.quote(relay_ip)}"
        ),
        check=False,
        timeout=12,
    )

    if (
        peer.exit_status != 0
        or "0% packet loss" not in (peer.stdout or "")
    ):
        raise CarrierUnavailable(
            "carrier_peer_ping_failed"
        )

    banner = await _run(
        ci,
        f"""python3 - <<'PY2'
import socket

source={iran_ip!r}
host={relay_ip!r}
port={int(relay_access.ssh_port)}

s=socket.socket(
    socket.AF_INET,
    socket.SOCK_STREAM,
)

s.settimeout(8)
s.bind((source, 0))
s.connect((host, port))

data=s.recv(256)

print(
    data.decode(
        "utf-8",
        "replace",
    ).strip()
)

s.close()

raise SystemExit(
    0
    if data.startswith(b"SSH-")
    else 46
)
PY2""",
        check=False,
        timeout=14,
    )

    if banner.exit_status != 0:
        raise CarrierUnavailable(
            "carrier_private_ssh_banner_failed"
        )

    return {
        "tunnel_id": int(carrier.id),
        "interface": interface,
        "iran_ip": iran_ip,
        "relay_ip": relay_ip,
    }


async def _authorize_private_carrier(
    ci,
    cr,
    *,
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    exit_access: NodeAccess,
    base: str,
    carrier_iran_ip: str,
) -> None:
    tid = int(tunnel.id)
    tag = f"tp{tid}-relay-hop"

    pub_result = await _run(
        ci,
        f"cat {shlex.quote(base + '/id_ed25519.pub')}",
        check=False,
        timeout=15,
    )

    pub = (pub_result.stdout or "").strip()

    if not pub.startswith("ssh-ed25519 "):
        raise RuntimeError(
            "relay_public_key_missing"
        )

    sources = (
        f"{iran.public_ip},"
        f"{carrier_iran_ip}"
    )

    line = (
        f'from="{sources}",'
        'no-agent-forwarding,'
        'no-X11-forwarding,'
        'no-pty,'
        'no-user-rc,'
        f'permitopen="{exit_node.public_ip}:'
        f'{int(exit_access.ssh_port)}" '
        f"{pub} {tag}"
    )

    encoded = base64.b64encode(
        line.encode("utf-8")
    ).decode("ascii")

    await _run(
        cr,
        f"""
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

cp -a \
  /root/.ssh/authorized_keys \
  /root/.ssh/authorized_keys.bak-tp-v21-$(date +%Y%m%d-%H%M%S)

grep -v \
  {shlex.quote(tag + '$')} \
  /root/.ssh/authorized_keys \
  > /root/.ssh/authorized_keys.tmp \
  || true

printf '%s' \
  {shlex.quote(encoded)} \
  | base64 -d \
  >> /root/.ssh/authorized_keys.tmp

printf '\\n' \
  >> /root/.ssh/authorized_keys.tmp

mv \
  /root/.ssh/authorized_keys.tmp \
  /root/.ssh/authorized_keys

chmod 600 \
  /root/.ssh/authorized_keys
""",
        timeout=35,
    )

    policy = (
        f"# TwinPanel V21 relay {tid}\n"
        f"Match User root Address {sources}\n"
        "    AllowTcpForwarding yes\n"
    )

    policy_path = (
        "/etc/ssh/sshd_config.d/"
        f"91-twinpanel-relay-hop-{tid}.conf"
    )

    await _write(
        cr,
        policy_path,
        policy,
        "600",
    )

    validate = await _run(
        cr,
        """
sshd -t &&
(
  systemctl reload ssh \
  2>/dev/null \
  ||
  systemctl reload sshd
)
""",
        check=False,
        timeout=35,
    )

    if validate.exit_status != 0:
        raise RuntimeError(
            "carrier_relay_sshd_policy_invalid"
        )


async def _recover_over_carrier(
    tunnel: Tunnel,
    iran: Node,
    relay: Node,
    exit_node: Node,
    db: Session,
) -> dict:
    from .routers.provision import (
        ssh_connect_saved,
    )

    carrier = choose_backhaul_carrier(
        db,
        tunnel,
        relay,
    )

    if carrier is None:
        raise CarrierUnavailable(
            "healthy_backhaul_carrier_not_found"
        )

    relay_access = (
        db.query(NodeAccess)
        .filter(
            NodeAccess.node_id
            == int(relay.id)
        )
        .first()
    )

    exit_access = (
        db.query(NodeAccess)
        .filter(
            NodeAccess.node_id
            == int(exit_node.id)
        )
        .first()
    )

    if (
        relay_access is None
        or exit_access is None
    ):
        raise RuntimeError(
            "carrier_saved_access_missing"
        )

    tid = int(tunnel.id)

    base = (
        "/etc/twinpanel/"
        f"ssh-relay/tunnel-{tid}"
    )

    (
        iran_service,
        iran_helper,
        exit_helper,
    ) = relay_services(tunnel)

    hop_service = (
        f"tp{tid}-relay-hop.service"
    )

    iface = relay_interface(tunnel)

    (
        network,
        iran_tun_ip,
        exit_tun_ip,
    ) = relay_addresses(tunnel)

    ci = None
    cr = None
    ce = None

    try:
        ci = await ssh_connect_saved(
            iran,
            db,
        )

        cr = await ssh_connect_saved(
            relay,
            db,
        )

        ce = await ssh_connect_saved(
            exit_node,
            db,
        )

        runtime = await _carrier_runtime(
            ci,
            cr,
            carrier,
            relay_access,
        )

        print(
            "[SSHRelayV21] "
            "CARRIER_SELECTED "
            f"tunnel={tid} "
            f"carrier_tunnel={runtime['tunnel_id']} "
            f"interface={runtime['interface']} "
            f"iran_ip={runtime['iran_ip']} "
            f"relay_ip={runtime['relay_ip']}",
            flush=True,
        )

        await _authorize_private_carrier(
            ci,
            cr,
            tunnel=tunnel,
            iran=iran,
            exit_node=exit_node,
            exit_access=exit_access,
            base=base,
            carrier_iran_ip=str(
                runtime["iran_ip"]
            ),
        )

        relay_key = await _host_key(cr)
        exit_key = await _host_key(ce)

        known_hosts = (
            f"{_known_host_name(str(relay.public_ip), int(relay_access.ssh_port))} "
            f"{relay_key}\n"
            f"{_known_host_name(str(exit_node.public_ip), int(exit_access.ssh_port))} "
            f"{exit_key}\n"
        )

        await _write(
            ci,
            base + "/known_hosts",
            known_hosts,
            "600",
        )

        local_port = await _pick_local_port(
            ci,
            tid,
        )

        hop_cfg = f"""Host tp{tid}-hop-split
    HostName {runtime['relay_ip']}
    Port {int(relay_access.ssh_port)}
    HostKeyAlias {relay.public_ip}
    BindAddress {runtime['iran_ip']}
    User root
    IdentityFile {base}/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    PasswordAuthentication no
    StrictHostKeyChecking yes
    UserKnownHostsFile {base}/known_hosts
    ConnectTimeout 10
    ServerAliveInterval 5
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    RequestTTY no
"""

        exit_cfg = f"""Host tp{tid}-exit-local
    HostName 127.0.0.1
    Port {int(local_port)}
    HostKeyAlias {exit_node.public_ip}
    User root
    IdentityFile {base}/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    PasswordAuthentication no
    StrictHostKeyChecking yes
    UserKnownHostsFile {base}/known_hosts
    ConnectTimeout 10
    ServerAliveInterval 5
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    Tunnel point-to-point
    TunnelDevice {100 + tid}:{100 + tid}
    RequestTTY no
"""

        await _write(
            ci,
            base + "/split_hop_config",
            hop_cfg,
            "600",
        )

        await _write(
            ci,
            base + "/split_exit_config",
            exit_cfg,
            "600",
        )

        hop_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay V21 via Backhaul {int(carrier.id)}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/split_hop_config -N -L 127.0.0.1:{int(local_port)}:{exit_node.public_ip}:{int(exit_access.ssh_port)} tp{tid}-hop-split
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        final_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay V21 Final
After=network-online.target {hop_service} {iran_helper}
Requires={hop_service}
Wants=network-online.target {iran_helper}

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/split_exit_config -N tp{tid}-exit-local
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        await _write(
            ci,
            (
                "/etc/systemd/system/"
                + hop_service
            ),
            hop_unit,
            "644",
        )

        await _write(
            ci,
            (
                "/etc/systemd/system/"
                + iran_service
            ),
            final_unit,
            "644",
        )

        iran_helper_check = await _run(
            ci,
            (
                "test -s "
                "/etc/systemd/system/"
                f"{shlex.quote(iran_helper)}"
            ),
            check=False,
        )

        exit_helper_check = await _run(
            ce,
            (
                "test -s "
                "/etc/systemd/system/"
                f"{shlex.quote(exit_helper)}"
            ),
            check=False,
        )

        if (
            iran_helper_check.exit_status != 0
            or exit_helper_check.exit_status != 0
        ):
            raise RuntimeError(
                "relay_interface_helpers_missing"
            )

        await _run(
            ce,
            (
                "systemctl daemon-reload; "
                "systemctl enable --now "
                f"{shlex.quote(exit_helper)} "
                ">/dev/null"
            ),
        )

        await _run(
            ci,
            f"""
systemctl daemon-reload

systemctl disable --now \
  {shlex.quote(iran_service)} \
  {shlex.quote(hop_service)} \
  >/dev/null 2>&1 \
  || true

systemctl enable --now \
  {shlex.quote(iran_helper)} \
  >/dev/null

systemctl enable --now \
  {shlex.quote(hop_service)} \
  >/dev/null
""",
        )

        banner_ok = False

        for _ in range(20):
            result = await _run(
                ci,
                f"""python3 - <<'PY2'
import socket

try:
    s=socket.create_connection(
        ("127.0.0.1", {int(local_port)}),
        timeout=2,
    )

    s.settimeout(2)

    data=s.recv(128)

    s.close()

    raise SystemExit(
        0
        if data.startswith(b"SSH-")
        else 1
    )

except Exception:
    raise SystemExit(1)
PY2""",
                check=False,
                timeout=5,
            )

            if result.exit_status == 0:
                banner_ok = True
                break

            await asyncio.sleep(1)

        if not banner_ok:
            raise RuntimeError(
                "carrier_local_exit_banner_not_ready"
            )

        await _run(
            ci,
            (
                "systemctl enable "
                f"{shlex.quote(iran_service)} "
                ">/dev/null; "
                "systemctl restart "
                f"{shlex.quote(iran_service)}"
            ),
        )

        ready = False

        for _ in range(35):
            probe = await _run(
                ci,
                (
                    "systemctl is-active --quiet "
                    f"{shlex.quote(hop_service)} "
                    "&& "
                    "systemctl is-active --quiet "
                    f"{shlex.quote(iran_service)} "
                    "&& "
                    f"ip addr show {shlex.quote(iface)} "
                    "2>/dev/null "
                    f"| grep -q {shlex.quote(iran_tun_ip)} "
                    "&& "
                    f"ping -I {shlex.quote(iface)} "
                    "-c 1 -W 1 "
                    f"{shlex.quote(exit_tun_ip)} "
                    ">/dev/null 2>&1"
                ),
                check=False,
                timeout=8,
            )

            if probe.exit_status == 0:
                ready = True
                break

            await asyncio.sleep(1)

        if not ready:
            raise RuntimeError(
                "carrier_relay_interface_not_ready"
            )

        sustained = await _run(
            ci,
            (
                "LC_ALL=C "
                f"ping -I {shlex.quote(iface)} "
                "-c 20 -i 0.20 -W 2 "
                "-s 1000 "
                f"{shlex.quote(exit_tun_ip)}"
            ),
            check=False,
            timeout=45,
        )

        if (
            sustained.exit_status != 0
            or "0% packet loss"
            not in (sustained.stdout or "")
        ):
            raise RuntimeError(
                "carrier_relay_sustained_ping_failed"
            )

        await _udp_probe(
            ci,
            ce,
            tunnel,
            iran_tun_ip,
            exit_tun_ip,
        )

        cfg = {
            "type": "ssh_relay",
            "mode": "split_hop_carrier_v21",
            "relay_node_id": int(relay.id),
            "relay_public_ip": str(
                relay.public_ip
            ),
            "exit_node_id": int(
                exit_node.id
            ),
            "network": network,
            "interface": iface,
            "iran_ip": iran_tun_ip,
            "exit_ip": exit_tun_ip,
            "iran_service": iran_service,
            "iran_helper": iran_helper,
            "exit_helper": exit_helper,
            "hop_service": hop_service,
            "local_forward_port": int(
                local_port
            ),
            "carrier_tunnel_id": int(
                carrier.id
            ),
            "carrier_interface": str(
                runtime["interface"]
            ),
            "carrier_iran_ip": str(
                runtime["iran_ip"]
            ),
            "carrier_relay_ip": str(
                runtime["relay_ip"]
            ),
            "carrier_mutated": False,
            "route_selectable": True,
            "ping_probe": "20/20",
            "udp_probe": "20/20",
        }

        row = _member(
            db,
            tid,
        )

        if row is None:
            row = TunnelTransport(
                tunnel_id=tid,
                transport="ssh_relay",
                priority=300,
            )

            db.add(row)

        row.priority = 300
        row.enabled = True
        row.status = "online"
        row.last_error = None
        row.last_healthy_at = (
            datetime.utcnow()
        )
        row.updated_at = (
            datetime.utcnow()
        )
        row.config_text = json.dumps(
            cfg,
            ensure_ascii=False,
        )

        db.commit()

        result = await verify_ssh_relay(
            tunnel,
            iran,
            db,
        )

        result["mode"] = (
            "split_hop_carrier_v21"
        )

        result["relay_node_id"] = int(
            relay.id
        )

        result["carrier_tunnel_id"] = int(
            carrier.id
        )

        return result

    except Exception:
        db.rollback()

        row = _member(
            db,
            tid,
        )

        if row is not None:
            row.priority = 300
            row.enabled = False
            row.status = "offline"
            row.updated_at = (
                datetime.utcnow()
            )

            db.commit()

        if ci:
            await _run(
                ci,
                (
                    "systemctl disable --now "
                    f"{shlex.quote(iran_service)} "
                    f"{shlex.quote(hop_service)} "
                    f"{shlex.quote(iran_helper)} "
                    ">/dev/null 2>&1 || true; "
                    f"ip link del {shlex.quote(iface)} "
                    ">/dev/null 2>&1 || true"
                ),
                check=False,
            )

        if ce:
            await _run(
                ce,
                (
                    "systemctl disable --now "
                    f"{shlex.quote(exit_helper)} "
                    ">/dev/null 2>&1 || true; "
                    f"ip link del {shlex.quote(iface)} "
                    ">/dev/null 2>&1 || true"
                ),
                check=False,
            )

        raise

    finally:
        for conn in (
            ci,
            cr,
            ce,
        ):
            if conn:
                conn.close()
                await conn.wait_closed()


async def provision_ssh_relay_v21(
    tunnel: Tunnel,
    iran: Node,
    relay: Node,
    exit_node: Node,
    db: Session,
) -> dict:
    """
    Keep V20 as the primary implementation.

    If V20 fails on the known public first-hop
    banner/interface black-hole and a healthy
    Backhaul carrier exists to the relay node,
    recover through that carrier without modifying it.
    """

    try:
        return await provision_ssh_relay_v2(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )

    except asyncio.CancelledError:
        raise

    except Exception as v20_exc:
        text = str(v20_exc).lower()

        eligible = (
            "banner" in text
            or
            "interface did not become ready"
            in text
        )

        if not eligible:
            raise

        carrier = choose_backhaul_carrier(
            db,
            tunnel,
            relay,
        )

        if carrier is None:
            raise

        print(
            "[SSHRelayV21] "
            "CARRIER_FALLBACK "
            f"tunnel={int(tunnel.id)} "
            f"relay_node={int(relay.id)} "
            f"carrier_tunnel={int(carrier.id)}",
            flush=True,
        )

        try:
            return await _recover_over_carrier(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )

        except asyncio.CancelledError:
            raise

        except Exception as v21_exc:
            raise RuntimeError(
                "v20_relay_failed="
                f"{type(v20_exc).__name__}:"
                f"{v20_exc}; "
                "v21_carrier_failed="
                f"{type(v21_exc).__name__}:"
                f"{v21_exc}"
            ) from v21_exc


def apply_carrier_aware_relay_v21() -> None:
    print(
        "TWINPANEL_CARRIER_AWARE_RELAY_V21_ACTIVE "
        "first_hop=healthy-backhaul "
        "carrier_mutation=0 "
        "public_v20_primary=1",
        flush=True,
    )
