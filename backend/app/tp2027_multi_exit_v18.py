from __future__ import annotations

import asyncio
import json
import shlex
from datetime import datetime

from sqlalchemy.orm import Session

from .models import Node, Tunnel, TunnelTransport
from .routers.provision import ssh_connect_saved
from . import tp2027_provision as base


# ============================================================
# TWINPANEL TP2027 MULTI-EXIT V18
#
# V17 still carried every TP2027 member over one Backhaul process per logical
# Iran -> Exit tunnel. On a shared Iran node that creates several licensed
# Backhaul processes and can make the second/third Exit path unstable.
#
# V18 makes KCP/ARQ/QUIC/TCP independent public underlays:
#   Iran public IP -> Exit public IP:per-tunnel-port
# Backhaul remains a legacy/optional fallback only and is no longer required
# for TP2027 creation, repair, health or failover.
# ============================================================


MODERN_NAMES = (
    "kcp_2027",
    "arq_2027",
    "quic_2027",
    "tcp_2027",
)


def _public_firewall_script(tunnel_id: int, iran_public_ip: str) -> str:
    source = shlex.quote(str(iran_public_ip).strip())
    lines = [
        "#!/bin/bash",
        "set -Eeuo pipefail",
        "",
        "iptables -N TP2027_PUBLIC_IN 2>/dev/null || true",
        "iptables -C INPUT -j TP2027_PUBLIC_IN 2>/dev/null || iptables -I INPUT 1 -j TP2027_PUBLIC_IN",
        "",
        "allow()",
        "{",
        '    local proto="$1"',
        '    local port="$2"',
        "    iptables -C TP2027_PUBLIC_IN "
        f"-s {source}/32 -p \"$proto\" --dport \"$port\" "
        f"-m comment --comment \"TP2027-PUBLIC-{int(tunnel_id)}-$proto-$port\" "
        "-j ACCEPT 2>/dev/null || "
        "iptables -I TP2027_PUBLIC_IN 1 "
        f"-s {source}/32 -p \"$proto\" --dport \"$port\" "
        f"-m comment --comment \"TP2027-PUBLIC-{int(tunnel_id)}-$proto-$port\" "
        "-j ACCEPT",
        "}",
        "",
    ]

    for name in MODERN_NAMES:
        runtime = base.tp2027_runtime_values(name, tunnel_id)
        lines.append(f"allow {runtime['protocol']} {runtime['port']}")

    lines.extend(["", "exit 0", ""])
    return "\n".join(lines)


def _public_service_unit(
    transport: str,
    tunnel_id: int,
    *,
    role: str,
    exit_public_ip: str,
) -> str:
    runtime = base.tp2027_runtime_values(transport, tunnel_id)
    filename, _ = base.ARTIFACTS[transport]
    binary = f"/opt/twinpanel/backhaul/bin/{filename}"
    iface = str(runtime["interface"])
    port = int(runtime["port"])
    local_ip = str(runtime["iran_ip"] if role == "iran" else runtime["exit_ip"])
    local_cidr = f"{local_ip}/30"

    secret_path = ""
    if transport == "arq_2027":
        secret_path = f"/etc/twinpanel/backhaul/{iface}.psk"
    elif transport == "kcp_2027":
        secret_path = f"/etc/twinpanel/backhaul/{iface}.key"

    if role == "iran":
        peer = f"{exit_public_ip}:{port}"
        if transport == "quic_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} --local {local_cidr} "
                f"--peer {peer} --lanes 8 --mtu 1320"
            )
        elif transport == "arq_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} --local {local_cidr} "
                f"--listen :0 --peer {peer} --key-file {secret_path} "
                "--mtu 1320 --frag 1000 --rto-ms 240"
            )
        elif transport == "kcp_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} --local {local_cidr} "
                f"--peer {peer} --mtu 1320 --psk-file {secret_path} "
                "--fec-data 20 --fec-parity 2"
            )
        else:
            exec_start = (
                f"{binary} --mode client --tun {iface} --local {local_cidr} "
                f"--peer {peer} --lanes 8 --mtu 1320"
            )

        role_hook = (
            f"ExecStartPost=/usr/local/sbin/tp2027-route-one {iface} "
            f"{runtime['iran_ip']} {runtime['route_table']}"
        )
    else:
        if transport == "quic_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} --local {local_cidr} "
                f"--listen :{port} --lanes 8 --mtu 1320"
            )
        elif transport == "arq_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} --local {local_cidr} "
                f"--listen :{port} --key-file {secret_path} "
                "--mtu 1320 --frag 1000 --rto-ms 240"
            )
        elif transport == "kcp_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} --local {local_cidr} "
                f"--listen :{port} --mtu 1320 --psk-file {secret_path} "
                "--fec-data 20 --fec-parity 2"
            )
        else:
            exec_start = (
                f"{binary} --mode server --tun {iface} --local {local_cidr} "
                f"--listen :{port} --lanes 8 --mtu 1320"
            )

        role_hook = f"ExecStartPre=/usr/local/sbin/tp2027-firewall-{int(tunnel_id)}-exit"

    return (
        "[Unit]\n"
        f"Description=TwinPanel 2027 {runtime['short'].upper()} Tunnel {int(tunnel_id)} - "
        f"{'Iran' if role == 'iran' else 'Exit'}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        f"{role_hook}\n"
        f"ExecStart={exec_start}\n"
        "Restart=always\n"
        "RestartSec=3\n"
        "TimeoutStopSec=10\n"
        "LimitNOFILE=1048576\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _config_text_v18(transport: str, tunnel_id: int, exit_public_ip: str) -> str:
    runtime = base.tp2027_runtime_values(transport, tunnel_id)
    payload = {
        "generation": 2028,
        "carrier": "public_direct",
        "depends_on": None,
        "multi_exit_safe": True,
        "peer_public_ip": str(exit_public_ip),
        "version": runtime["version"],
        "interface": runtime["interface"],
        "network": runtime["network"],
        "iran_ip": runtime["iran_ip"],
        "exit_ip": runtime["exit_ip"],
        "iran_service": runtime["iran_service"],
        "exit_service": runtime["exit_service"],
        "port": runtime["port"],
        "protocol": runtime["protocol"],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


async def install_tp2027_overlays_v18(tunnel_id: int, db: Session) -> dict:
    tid = int(tunnel_id)
    base.validate_artifact_store()

    tunnel = db.get(Tunnel, tid)
    if tunnel is None:
        raise RuntimeError(f"Tunnel {tid} not found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("Tunnel nodes are missing")

    iran_conn = None
    exit_conn = None

    for name in MODERN_NAMES:
        row = base._upsert_transport(db, tid, name)
        row.config_text = _config_text_v18(name, tid, str(exit_node.public_ip))
        row.last_error = None
        row.updated_at = datetime.utcnow()
        db.commit()

    try:
        iran_conn = await ssh_connect_saved(iran, db)
        exit_conn = await ssh_connect_saved(exit_node, db)

        for conn in (iran_conn, exit_conn):
            await base._run(
                conn,
                "install -d -m 0755 /opt/twinpanel/backhaul/bin && "
                "install -d -m 0700 /etc/twinpanel/backhaul && "
                "install -d -m 0755 /usr/local/sbin",
            )

        for name, (filename, expected) in base.ARTIFACTS.items():
            local_path = base.ARTIFACT_STORE / filename
            remote_path = "/opt/twinpanel/backhaul/bin/" + filename
            await base._install_artifact(iran_conn, local_path, remote_path, expected)
            await base._install_artifact(exit_conn, local_path, remote_path, expected)

        helper_name, helper_sha = base.ROUTE_HELPER
        await base._install_artifact(
            iran_conn,
            base.ARTIFACT_STORE / helper_name,
            "/usr/local/sbin/tp2027-route-one",
            helper_sha,
        )

        firewall_path = f"/usr/local/sbin/tp2027-firewall-{tid}-exit"
        await base._write_remote_text(
            exit_conn,
            firewall_path,
            _public_firewall_script(tid, str(iran.public_ip)),
            "0755",
        )

        for name in ("arq_2027", "kcp_2027"):
            runtime = base.tp2027_runtime_values(name, tid)
            suffix = ".psk" if name == "arq_2027" else ".key"
            secret_path = f"/etc/twinpanel/backhaul/{runtime['interface']}{suffix}"
            await base._shared_secret_for(iran_conn, exit_conn, secret_path)

        for name in MODERN_NAMES:
            runtime = base.tp2027_runtime_values(name, tid)
            unit_path = f"/etc/systemd/system/{runtime['iran_service']}"
            await base._write_remote_text(
                iran_conn,
                unit_path,
                _public_service_unit(
                    name,
                    tid,
                    role="iran",
                    exit_public_ip=str(exit_node.public_ip),
                ),
                "0644",
            )
            await base._write_remote_text(
                exit_conn,
                unit_path,
                _public_service_unit(
                    name,
                    tid,
                    role="exit",
                    exit_public_ip=str(exit_node.public_ip),
                ),
                "0644",
            )

        await base._run(exit_conn, "systemctl daemon-reload")
        await base._run(iran_conn, "systemctl daemon-reload")

        for name in MODERN_NAMES:
            runtime = base.tp2027_runtime_values(name, tid)
            await base._run(
                exit_conn,
                f"systemctl enable {runtime['exit_service']} >/dev/null && "
                f"systemctl restart {runtime['exit_service']}",
                check=False,
                timeout=30,
            )

        await asyncio.sleep(2)

        for name in MODERN_NAMES:
            runtime = base.tp2027_runtime_values(name, tid)
            await base._run(
                iran_conn,
                f"systemctl enable {runtime['iran_service']} >/dev/null && "
                f"systemctl restart {runtime['iran_service']}",
                check=False,
                timeout=30,
            )

        await asyncio.sleep(4)
        result: dict[str, dict] = {}

        for name in MODERN_NAMES:
            runtime = base.tp2027_runtime_values(name, tid)
            iran_ok, iran_latency, iran_error = await base._probe(
                iran_conn,
                service=str(runtime["iran_service"]),
                interface=str(runtime["interface"]),
                peer_ip=str(runtime["exit_ip"]),
            )
            exit_ok, exit_latency, exit_error = await base._probe(
                exit_conn,
                service=str(runtime["exit_service"]),
                interface=str(runtime["interface"]),
                peer_ip=str(runtime["iran_ip"]),
            )

            healthy = bool(iran_ok and exit_ok)
            latencies = [v for v in (iran_latency, exit_latency) if v is not None]
            latency = int(round(sum(latencies) / len(latencies))) if latencies else None

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tid,
                    TunnelTransport.transport == name,
                )
                .first()
            )
            assert row is not None
            row.status = "online" if healthy else "failed"
            row.latency_ms = latency
            row.last_error = None if healthy else (
                iran_error or exit_error or "TP2027 public-direct health check failed"
            )[:1800]
            if healthy:
                row.last_healthy_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            db.commit()

            result[name] = {
                "ok": healthy,
                "status": row.status,
                "latency_ms": latency,
                "error": row.last_error,
                "runtime": {
                    "interface": runtime["interface"],
                    "network": runtime["network"],
                    "port": runtime["port"],
                    "protocol": runtime["protocol"],
                    "version": runtime["version"],
                    "underlay": "public_direct",
                    "peer_public_ip": str(exit_node.public_ip),
                },
            }

        return {
            "ok": any(item["ok"] for item in result.values()),
            "carrier": "public_direct",
            "multi_exit_safe": True,
            "transports": result,
        }

    except Exception as exc:
        for name in MODERN_NAMES:
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tid,
                    TunnelTransport.transport == name,
                )
                .first()
            )
            if row is None:
                continue
            row.status = "failed"
            row.last_error = str(exc)[:1800]
            row.updated_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        if iran_conn is not None:
            iran_conn.close()
            await iran_conn.wait_closed()
        if exit_conn is not None:
            exit_conn.close()
            await exit_conn.wait_closed()
