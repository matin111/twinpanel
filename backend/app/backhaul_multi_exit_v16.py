from __future__ import annotations

import base64

from .database import SessionLocal
from .models import Tunnel


# ============================================================
# TWINPANEL BACKHAUL MULTI-EXIT V16
#
# Historical Backhaul config hard-coded the same server-side forwarded mapping
# (18080) into every tunnel. With one Iran node fanning out to several Exit
# nodes, every Backhaul server process on that Iran host therefore tried to own
# the same mapping. V16 preserves 18080 for the oldest active tunnel on an Iran
# node and allocates a deterministic, per-tunnel mapping to every additional
# tunnel. The actual L3 TUN addresses, health port and public protocol services
# are unchanged.
# ============================================================


def backhaul_forward_port(tunnel_id: int) -> int:
    tid = int(tunnel_id)

    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, tid)
        if tunnel is None:
            # Deterministic safe fallback for install-time edge cases.
            return 18080 + (tid % 10000)

        sibling_ids = [
            int(row[0])
            for row in (
                db.query(Tunnel.id)
                .filter(
                    Tunnel.iran_node_id == int(tunnel.iran_node_id),
                    Tunnel.is_active.is_(True),
                )
                .order_by(Tunnel.id.asc())
                .all()
            )
        ]

        if sibling_ids and tid == sibling_ids[0]:
            return 18080

        return 18080 + (tid % 10000)
    finally:
        db.close()


async def install_backhaul_peer_v16(
    conn,
    *,
    tunnel_id: int,
    mode: str,
    local_public_ip: str,
    peer_public_ip: str,
    local_addr: str,
    remote_addr: str,
    interface_name: str,
    health_port: int,
    config_path: str,
    service_name: str,
    local_binary: str,
) -> dict:
    """V16 Backhaul peer installer with collision-free shared-Iran mapping."""

    from .routers import tunnels as core

    if mode not in {"server", "client"}:
        raise RuntimeError("Backhaul mode نامعتبر است")

    public_interface = await core._backhaul_default_interface(conn)

    if not await core._backhaul_remote_binary_ok(conn):
        await core._backhaul_copy_binary(
            conn,
            local_binary,
        )

    local_ip = local_addr.split("/", 1)[0]

    conflict = await core.cmd(
        conn,
        (
            "ip -4 addr show | "
            f"grep -F ' {local_ip}/' || true"
        ),
        check=False,
    )

    if conflict and interface_name not in conflict:
        raise RuntimeError(
            f"آدرس داخلی Backhaul {local_ip} "
            "روی این سرور قبلاً استفاده شده است"
        )

    ports_block = ""
    forward_port = None

    if mode == "server":
        forward_port = backhaul_forward_port(int(tunnel_id))
        ports_block = f"""
[ports]
forwarder = "iptables"
mapping = [
    "{int(forward_port)}",
]
"""

    config = f"""[transport]
type = "tun"
heartbeat_interval = 10
heartbeat_timeout = 25

[tun]
encapsulation = "ipx"
name = "{interface_name}"
local_addr = "{local_addr}"
remote_addr = "{remote_addr}"
health_port = {int(health_port)}
mtu = 1320

[ipx]
mode = "{mode}"
profile = "icmp"
listen_ip = "{local_public_ip}"
dst_ip = "{peer_public_ip}"
interface = "{public_interface}"

[security]
enable_encryption = false

[tuning]
auto_tuning = true
tuning_profile = "balanced"
workers = 0
channel_size = 10000
so_sndbuf = 0
batch_size = 2048

[logging]
log_level = "debug"
""" + ports_block

    encoded = base64.b64encode(
        config.encode("utf-8")
    ).decode("ascii")

    unit = f"""[Unit]
Description=TwinPanel Backhaul Tunnel {int(tunnel_id)}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/twinpanel-backhaul -c {config_path}
Restart=always
RestartSec=3
LimitNOFILE=1048576
TasksMax=infinity
LimitMEMLOCK=infinity
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

    unit_encoded = base64.b64encode(
        unit.encode("utf-8")
    ).decode("ascii")

    await core.cmd(
        conn,
        (
            "mkdir -p /etc/twinpanel/backhaul && "
            f"echo '{encoded}' | base64 -d > {config_path} && "
            f"chmod 0600 {config_path} && "
            f"echo '{unit_encoded}' | base64 -d "
            f"> /etc/systemd/system/{service_name} && "
            "systemctl daemon-reload && "
            f"systemctl enable {service_name} >/dev/null 2>&1"
        ),
        check=True,
    )

    # Only this tunnel's service/interface are recycled. Sibling Exit tunnels
    # on the same Iran node are never stopped or deleted.
    await core.cmd(
        conn,
        (
            f"systemctl stop {service_name} >/dev/null 2>&1 || true; "
            f"ip link delete {interface_name} >/dev/null 2>&1 || true; "
            f"systemctl start {service_name}"
        ),
        timeout=60,
        check=True,
    )

    await __import__("asyncio").sleep(4)

    service_state = await core.cmd(
        conn,
        f"systemctl is-active {service_name}",
        check=False,
    )

    addr_state = await core.cmd(
        conn,
        (
            f"ip -4 addr show dev {interface_name} "
            "2>/dev/null || true"
        ),
        check=False,
    )

    if str(service_state).strip() != "active":
        journal = await core.cmd(
            conn,
            (
                f"journalctl -u {service_name} "
                "-n 40 --no-pager"
            ),
            check=False,
        )

        raise RuntimeError(
            "سرویس Backhaul فعال نشد: "
            + str(journal or service_state)[-1800:]
        )

    return {
        "ok": True,
        "mode": mode,
        "service": str(service_state).strip(),
        "interface": interface_name,
        "interface_ready": interface_name in str(addr_state),
        "public_interface": public_interface,
        "config": config_path,
        "forward_port": forward_port,
        "multi_exit_safe": True,
    }
