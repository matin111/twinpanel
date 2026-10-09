from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shlex
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .models import Node, Tunnel, TunnelTransport
from .routers.provision import ssh_connect_saved


ARTIFACT_STORE = Path(
    os.environ.get(
        "TP2027_ARTIFACT_STORE",
        "/var/lib/twinpanel/tp2027-artifacts",
    )
)

ARTIFACTS = {
    "quic_2027": (
        "twinpanel-backhaul-quic-0.6.1-frag",
        "d2ccb306b7093cbb892ae39b46053977fe72519303b328447801a9d3bd35f99c",
    ),
    "arq_2027": (
        "twinpanel-backhaul-native-0.7.1",
        "7fc424f377bbdef7db5e60425e00ce389802e2177fd8fc955ca2365f882c79d0",
    ),
    "kcp_2027": (
        "twinpanel-backhaul-kcp-0.2.1",
        "776c6538782bd92227a5dc4e1a3c9b9bc9dbe6ecb1570064dca8efe46546ede9",
    ),
    "tcp_2027": (
        "twinpanel-backhaul-tcp-0.3.0",
        "7b2cf5533100d9bf0901f1b237e59f876e4a402bf8b246dc44881a2b49f5da7d",
    ),
}

ROUTE_HELPER = (
    "tp2027-route-one",
    "03cab80cc80937be65fcf68504b97dfa4c12ffb0bde5f11f71d78f21a50697b4",
)

TP2027_PRIORITY = {
    "quic_2027": 10,
    "arq_2027": 20,
    "kcp_2027": 30,
    "tcp_2027": 40,
}

_SPEC = {
    "kcp_2027": {
        "short": "kcp",
        "iface": "tp27k",
        "network_offset": 0,
        "port_base": 45100,
        "table_base": 24100,
        "protocol": "udp",
        "version": "0.2.1",
    },
    "tcp_2027": {
        "short": "tcp",
        "iface": "tp27t",
        "network_offset": 1,
        "port_base": 45200,
        "table_base": 24200,
        "protocol": "tcp",
        "version": "0.3.0",
    },
    "quic_2027": {
        "short": "quic",
        "iface": "tp27q",
        "network_offset": 2,
        "port_base": 45300,
        "table_base": 24300,
        "protocol": "udp",
        "version": "0.6.1-frag",
    },
    "arq_2027": {
        "short": "arq",
        "iface": "tp27a",
        "network_offset": 3,
        "port_base": 45400,
        "table_base": 24400,
        "protocol": "udp",
        "version": "0.7.1",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_store() -> dict[str, str]:
    verified: dict[str, str] = {}

    for name, (filename, expected) in ARTIFACTS.items():
        path = ARTIFACT_STORE / filename
        if not path.is_file():
            raise RuntimeError(
                f"TP2027 artifact missing: {path}"
            )

        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"TP2027 artifact checksum mismatch: {filename}"
            )

        verified[name] = actual

    helper_name, helper_expected = ROUTE_HELPER
    helper_path = ARTIFACT_STORE / helper_name

    if not helper_path.is_file():
        raise RuntimeError(
            f"TP2027 route helper missing: {helper_path}"
        )

    helper_actual = _sha256(helper_path)
    if helper_actual != helper_expected:
        raise RuntimeError(
            "TP2027 route helper checksum mismatch"
        )

    verified["route_helper"] = helper_actual
    return verified


def _overlay_network_number(
    tunnel_id: int,
    offset: int,
) -> tuple[int, int]:
    # Preserve the production-proven Tunnel 5 layout:
    # KCP 10.252.71.0/30, TCP .72, QUIC .73, ARQ .74.
    # Every logical tunnel owns four consecutive /30 subnets.
    value = (4 * int(tunnel_id)) + 51 + int(offset)

    second = 252 - (value // 256)
    third = value % 256

    if second < 1:
        raise ValueError(
            "TP2027 address pool exhausted for this tunnel id"
        )

    return second, third


def backhaul_runtime_values(
    tunnel_id: int,
) -> dict[str, object]:
    tid = int(tunnel_id)
    slot = 10 + (tid % 230)

    return {
        "interface": f"bh{tid}"[:15],
        "iran_ip": f"10.253.{slot}.1",
        "exit_ip": f"10.253.{slot}.2",
        "service": f"twinpanel-backhaul-{tid}.service",
    }


def tp2027_runtime_values(
    transport: str,
    tunnel_id: int,
) -> dict[str, object]:
    name = str(transport or "").strip().lower()
    spec = _SPEC.get(name)

    if spec is None:
        raise ValueError(
            f"Unsupported TP2027 transport: {transport}"
        )

    tid = int(tunnel_id)

    if tid < 1 or tid > 999:
        raise ValueError(
            "TP2027 supports tunnel ids 1..999"
        )

    second, third = _overlay_network_number(
        tid,
        int(spec["network_offset"]),
    )

    interface = (
        f"{spec['iface']}{tid}"
    )[:15]

    port = int(spec["port_base"]) + tid
    table = int(spec["table_base"]) + tid

    return {
        "transport": name,
        "priority": TP2027_PRIORITY[name],
        "short": spec["short"],
        "version": spec["version"],
        "protocol": spec["protocol"],
        "interface": interface,
        "network": f"10.{second}.{third}.0/30",
        "iran_ip": f"10.{second}.{third}.1",
        "exit_ip": f"10.{second}.{third}.2",
        "port": port,
        "route_table": table,
        "iran_service": (
            f"twinpanel-2027-{spec['short']}{tid}.service"
        ),
        "exit_service": (
            f"twinpanel-2027-{spec['short']}{tid}.service"
        ),
    }


async def _run(
    conn,
    command: str,
    *,
    check: bool = True,
    timeout: int = 60,
):
    result = await conn.run(
        command,
        check=False,
        timeout=timeout,
    )

    if check and result.exit_status != 0:
        message = (
            result.stderr
            or result.stdout
            or "remote command failed"
        )
        raise RuntimeError(
            str(message)[-2000:]
        )

    return result


async def _write_remote_text(
    conn,
    path: str,
    text: str,
    mode: str,
) -> None:
    payload = base64.b64encode(
        text.encode("utf-8")
    ).decode("ascii")

    qpath = shlex.quote(path)
    qpayload = shlex.quote(payload)

    await _run(
        conn,
        (
            f"printf %s {qpayload} | base64 -d > {qpath} && "
            f"chmod {mode} {qpath}"
        ),
    )


async def _remote_file_exists(
    conn,
    path: str,
) -> bool:
    result = await _run(
        conn,
        f"test -f {shlex.quote(path)}",
        check=False,
    )
    return result.exit_status == 0


async def _remote_read_bytes(
    conn,
    path: str,
) -> bytes:
    async with conn.start_sftp_client() as sftp:
        async with sftp.open(path, "rb") as handle:
            return await handle.read()


async def _write_remote_bytes(
    conn,
    path: str,
    data: bytes,
    mode: str = "0600",
) -> None:
    payload = base64.b64encode(data).decode("ascii")
    qpath = shlex.quote(path)
    qpayload = shlex.quote(payload)

    await _run(
        conn,
        (
            f"printf %s {qpayload} | base64 -d > {qpath} && "
            f"chmod {mode} {qpath}"
        ),
    )


async def _install_artifact(
    conn,
    local_path: Path,
    remote_path: str,
    expected_sha: str,
) -> None:
    remote_dir = str(
        Path(remote_path).parent
    )

    await _run(
        conn,
        f"install -d -m 0755 {shlex.quote(remote_dir)}",
    )

    remote_hash = await _run(
        conn,
        (
            f"test -f {shlex.quote(remote_path)} && "
            f"sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}'"
        ),
        check=False,
    )

    if (
        remote_hash.exit_status == 0
        and remote_hash.stdout.strip() == expected_sha
    ):
        return

    tmp_path = f"{remote_path}.tmp"

    async with conn.start_sftp_client() as sftp:
        await sftp.put(
            str(local_path),
            tmp_path,
        )

    await _run(
        conn,
        (
            f"chmod 0755 {shlex.quote(tmp_path)} && "
            f"mv -f {shlex.quote(tmp_path)} {shlex.quote(remote_path)} && "
            f"test \"$(sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}')\" "
            f"= {shlex.quote(expected_sha)}"
        ),
    )


def _firewall_script(
    tunnel_id: int,
) -> str:
    bh = backhaul_runtime_values(
        tunnel_id
    )

    lines = [
        "#!/bin/bash",
        "set -Eeuo pipefail",
        "",
        "iptables -N TP2027_IN 2>/dev/null || true",
        "iptables -C INPUT -j TP2027_IN 2>/dev/null || "
        "iptables -I INPUT 1 -j TP2027_IN",
        "",
        "allow()",
        "{",
        '    local proto="$1"',
        '    local port="$2"',
        "",
        "    iptables -C TP2027_IN "
        f"-i {shlex.quote(str(bh['interface']))} "
        f"-s {shlex.quote(str(bh['iran_ip']))}/32 "
        '-p "$proto" --dport "$port" '
        "-m comment "
        f'--comment "TP2027-BH{int(tunnel_id)}-$proto-$port" '
        "-j ACCEPT 2>/dev/null || "
        "iptables -I TP2027_IN 1 "
        f"-i {shlex.quote(str(bh['interface']))} "
        f"-s {shlex.quote(str(bh['iran_ip']))}/32 "
        '-p "$proto" --dport "$port" '
        "-m comment "
        f'--comment "TP2027-BH{int(tunnel_id)}-$proto-$port" '
        "-j ACCEPT",
        "}",
        "",
    ]

    for name in (
        "kcp_2027",
        "tcp_2027",
        "quic_2027",
        "arq_2027",
    ):
        runtime = tp2027_runtime_values(
            name,
            tunnel_id,
        )
        lines.append(
            f"allow {runtime['protocol']} {runtime['port']}"
        )

    lines.extend(
        [
            "",
            "exit 0",
            "",
        ]
    )

    return "\n".join(lines)


def _service_unit(
    transport: str,
    tunnel_id: int,
    *,
    role: str,
) -> str:
    runtime = tp2027_runtime_values(
        transport,
        tunnel_id,
    )
    bh = backhaul_runtime_values(
        tunnel_id
    )

    filename, _ = ARTIFACTS[transport]
    binary = (
        f"/opt/twinpanel/backhaul/bin/{filename}"
    )

    iface = str(runtime["interface"])
    port = int(runtime["port"])
    local_ip = (
        str(runtime["iran_ip"])
        if role == "iran"
        else str(runtime["exit_ip"])
    )
    local_cidr = f"{local_ip}/30"

    secret_path = ""

    if transport == "arq_2027":
        secret_path = (
            f"/etc/twinpanel/backhaul/"
            f"{iface}.psk"
        )
    elif transport == "kcp_2027":
        secret_path = (
            f"/etc/twinpanel/backhaul/"
            f"{iface}.key"
        )

    if role == "iran":
        peer = (
            f"{bh['exit_ip']}:{port}"
        )

        if transport == "quic_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} "
                f"--local {local_cidr} --peer {peer} "
                "--lanes 8 --mtu 1320"
            )
        elif transport == "arq_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} "
                f"--local {local_cidr} --listen :0 --peer {peer} "
                f"--key-file {secret_path} "
                "--mtu 1320 --frag 1000 --rto-ms 240"
            )
        elif transport == "kcp_2027":
            exec_start = (
                f"{binary} --mode client --tun {iface} "
                f"--local {local_cidr} --peer {peer} "
                f"--mtu 1320 --psk-file {secret_path} "
                "--fec-data 20 --fec-parity 2"
            )
        else:
            exec_start = (
                f"{binary} --mode client --tun {iface} "
                f"--local {local_cidr} --peer {peer} "
                "--lanes 8 --mtu 1320"
            )

        role_hook = (
            "ExecStartPost=/usr/local/sbin/"
            f"tp2027-route-one {iface} "
            f"{runtime['iran_ip']} "
            f"{runtime['route_table']}"
        )

    else:
        if transport == "quic_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} "
                f"--local {local_cidr} --listen :{port} "
                "--lanes 8 --mtu 1320"
            )
        elif transport == "arq_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} "
                f"--local {local_cidr} --listen :{port} "
                f"--key-file {secret_path} "
                "--mtu 1320 --frag 1000 --rto-ms 240"
            )
        elif transport == "kcp_2027":
            exec_start = (
                f"{binary} --mode server --tun {iface} "
                f"--local {local_cidr} --listen :{port} "
                f"--mtu 1320 --psk-file {secret_path} "
                "--fec-data 20 --fec-parity 2"
            )
        else:
            exec_start = (
                f"{binary} --mode server --tun {iface} "
                f"--local {local_cidr} --listen :{port} "
                "--lanes 8 --mtu 1320"
            )

        role_hook = (
            "ExecStartPre=/usr/local/sbin/"
            f"tp2027-firewall-{int(tunnel_id)}-exit"
        )

    return (
        "[Unit]\n"
        f"Description=TwinPanel 2027 {runtime['short'].upper()} "
        f"Overlay Tunnel {int(tunnel_id)} - "
        f"{'Iran' if role == 'iran' else 'Exit'}\n"
        f"After=network-online.target {bh['service']}\n"
        f"Wants=network-online.target {bh['service']}\n\n"
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


def _config_text(
    transport: str,
    tunnel_id: int,
) -> str:
    runtime = tp2027_runtime_values(
        transport,
        tunnel_id,
    )
    bh = backhaul_runtime_values(
        tunnel_id
    )

    payload = {
        "generation": 2027,
        "carrier": "backhaul",
        "carrier_interface": bh["interface"],
        "depends_on": "backhaul",
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

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _upsert_transport(
    db: Session,
    tunnel_id: int,
    transport: str,
) -> TunnelTransport:
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel_id),
            TunnelTransport.transport
            == transport,
        )
        .first()
    )

    if row is None:
        row = TunnelTransport(
            tunnel_id=int(tunnel_id),
            transport=transport,
            priority=TP2027_PRIORITY[transport],
            enabled=True,
            status="installing",
        )
        db.add(row)
    else:
        row.priority = TP2027_PRIORITY[transport]
        row.enabled = True
        row.status = "installing"

    row.config_text = _config_text(
        transport,
        tunnel_id,
    )
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def _ping_latency_ms(
    text: str,
) -> int | None:
    match = re.search(
        r"=\s*[\d.]+/([\d.]+)/",
        text or "",
    )
    if not match:
        return None
    try:
        return int(round(float(match.group(1))))
    except Exception:
        return None


async def _probe(
    conn,
    *,
    service: str,
    interface: str,
    peer_ip: str,
) -> tuple[bool, int | None, str | None]:
    command = (
        f"systemctl is-active {shlex.quote(service)} && "
        f"ip link show {shlex.quote(interface)} >/dev/null && "
        f"ping -I {shlex.quote(interface)} -c 3 -W 2 "
        f"{shlex.quote(peer_ip)}"
    )

    result = await _run(
        conn,
        command,
        check=False,
        timeout=20,
    )

    if result.exit_status != 0:
        return (
            False,
            None,
            (
                result.stderr
                or result.stdout
                or "overlay probe failed"
            )[-1000:],
        )

    return (
        True,
        _ping_latency_ms(result.stdout or ""),
        None,
    )


async def _shared_secret_for(
    iran_conn,
    exit_conn,
    remote_path: str,
) -> None:
    if await _remote_file_exists(
        iran_conn,
        remote_path,
    ):
        data = await _remote_read_bytes(
            iran_conn,
            remote_path,
        )
    else:
        data = (
            secrets.token_hex(32)
            + "\n"
        ).encode("ascii")

    await _write_remote_bytes(
        iran_conn,
        remote_path,
        data,
    )
    await _write_remote_bytes(
        exit_conn,
        remote_path,
        data,
    )


async def install_tp2027_overlays(
    tunnel_id: int,
    db: Session,
) -> dict:
    tid = int(tunnel_id)
    validate_artifact_store()

    tunnel = db.get(
        Tunnel,
        tid,
    )
    if tunnel is None:
        raise RuntimeError(
            f"Tunnel {tid} not found"
        )

    iran = db.get(
        Node,
        int(tunnel.iran_node_id),
    )
    exit_node = db.get(
        Node,
        int(tunnel.exit_node_id),
    )

    if iran is None or exit_node is None:
        raise RuntimeError(
            "Tunnel nodes are missing"
        )

    bh = backhaul_runtime_values(
        tid
    )

    iran_conn = None
    exit_conn = None

    names = (
        "quic_2027",
        "arq_2027",
        "kcp_2027",
        "tcp_2027",
    )

    for name in names:
        _upsert_transport(
            db,
            tid,
            name,
        )

    try:
        iran_conn = await ssh_connect_saved(
            iran,
            db,
        )
        exit_conn = await ssh_connect_saved(
            exit_node,
            db,
        )

        for conn in (
            iran_conn,
            exit_conn,
        ):
            await _run(
                conn,
                (
                    "install -d -m 0755 /opt/twinpanel/backhaul/bin && "
                    "install -d -m 0700 /etc/twinpanel/backhaul && "
                    "install -d -m 0755 /usr/local/sbin"
                ),
            )

            bh_check = await _run(
                conn,
                (
                    f"systemctl is-active {bh['service']} && "
                    f"ip link show {bh['interface']} >/dev/null"
                ),
                check=False,
            )

            if bh_check.exit_status != 0:
                raise RuntimeError(
                    "Backhaul carrier is not active on both nodes"
                )

        for name, (filename, expected) in ARTIFACTS.items():
            local_path = (
                ARTIFACT_STORE
                / filename
            )
            remote_path = (
                "/opt/twinpanel/backhaul/bin/"
                + filename
            )

            await _install_artifact(
                iran_conn,
                local_path,
                remote_path,
                expected,
            )
            await _install_artifact(
                exit_conn,
                local_path,
                remote_path,
                expected,
            )

        helper_name, helper_sha = ROUTE_HELPER
        await _install_artifact(
            iran_conn,
            ARTIFACT_STORE / helper_name,
            "/usr/local/sbin/tp2027-route-one",
            helper_sha,
        )

        firewall_path = (
            f"/usr/local/sbin/"
            f"tp2027-firewall-{tid}-exit"
        )

        await _write_remote_text(
            exit_conn,
            firewall_path,
            _firewall_script(tid),
            "0755",
        )

        for name in (
            "arq_2027",
            "kcp_2027",
        ):
            runtime = tp2027_runtime_values(
                name,
                tid,
            )
            suffix = (
                ".psk"
                if name == "arq_2027"
                else ".key"
            )
            secret_path = (
                "/etc/twinpanel/backhaul/"
                f"{runtime['interface']}{suffix}"
            )

            await _shared_secret_for(
                iran_conn,
                exit_conn,
                secret_path,
            )

        for name in names:
            runtime = tp2027_runtime_values(
                name,
                tid,
            )
            unit_path = (
                "/etc/systemd/system/"
                f"{runtime['iran_service']}"
            )

            await _write_remote_text(
                iran_conn,
                unit_path,
                _service_unit(
                    name,
                    tid,
                    role="iran",
                ),
                "0644",
            )

            await _write_remote_text(
                exit_conn,
                unit_path,
                _service_unit(
                    name,
                    tid,
                    role="exit",
                ),
                "0644",
            )

        await _run(
            exit_conn,
            "systemctl daemon-reload",
        )
        await _run(
            iran_conn,
            "systemctl daemon-reload",
        )

        for name in names:
            runtime = tp2027_runtime_values(
                name,
                tid,
            )
            await _run(
                exit_conn,
                (
                    "systemctl enable "
                    f"{runtime['exit_service']} >/dev/null && "
                    "systemctl restart "
                    f"{runtime['exit_service']}"
                ),
                check=False,
                timeout=30,
            )

        await asyncio.sleep(2)

        for name in names:
            runtime = tp2027_runtime_values(
                name,
                tid,
            )
            await _run(
                iran_conn,
                (
                    "systemctl enable "
                    f"{runtime['iran_service']} >/dev/null && "
                    "systemctl restart "
                    f"{runtime['iran_service']}"
                ),
                check=False,
                timeout=30,
            )

        await asyncio.sleep(4)

        result: dict[str, dict] = {}

        for name in names:
            runtime = tp2027_runtime_values(
                name,
                tid,
            )

            iran_ok, iran_latency, iran_error = await _probe(
                iran_conn,
                service=str(runtime["iran_service"]),
                interface=str(runtime["interface"]),
                peer_ip=str(runtime["exit_ip"]),
            )

            exit_ok, exit_latency, exit_error = await _probe(
                exit_conn,
                service=str(runtime["exit_service"]),
                interface=str(runtime["interface"]),
                peer_ip=str(runtime["iran_ip"]),
            )

            healthy = bool(
                iran_ok
                and exit_ok
            )

            latencies = [
                value
                for value in (
                    iran_latency,
                    exit_latency,
                )
                if value is not None
            ]

            latency = (
                int(round(sum(latencies) / len(latencies)))
                if latencies
                else None
            )

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tid,
                    TunnelTransport.transport == name,
                )
                .first()
            )

            assert row is not None

            row.status = (
                "online"
                if healthy
                else "failed"
            )
            row.latency_ms = latency
            row.last_error = (
                None
                if healthy
                else (
                    iran_error
                    or exit_error
                    or "TP2027 overlay health check failed"
                )[:1800]
            )
            row.last_healthy_at = (
                datetime.utcnow()
                if healthy
                else row.last_healthy_at
            )
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
                },
            }

        return {
            "ok": any(
                item["ok"]
                for item in result.values()
            ),
            "carrier": "backhaul",
            "carrier_interface": bh["interface"],
            "transports": result,
        }

    except Exception as exc:
        for name in names:
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
