# TWINPANEL_MTUNNEL_TRANSPORT_V1

import base64
import ipaddress
import json
import os
import re
import secrets
from pathlib import Path


MTUNNEL_ROOT = Path(
    "/root/.vpnshop/mtunnel"
)

MTUNNEL_KEY_DIR = (
    MTUNNEL_ROOT / "keys"
)


def mtunnel_runtime_values(
    tunnel_id: int,
) -> dict:

    tid = int(tunnel_id)

    # /30 deterministic subnet inside 10.254.0.0/16
    index = tid % 16384

    network_base = (
        int(
            ipaddress.IPv4Address(
                "10.254.0.0"
            )
        )
        + index * 4
    )

    network = ipaddress.IPv4Network(
        (
            ipaddress.IPv4Address(
                network_base
            ),
            30,
        )
    )

    hosts = list(
        network.hosts()
    )

    iran_ip = str(hosts[0])
    exit_ip = str(hosts[1])

    iface = f"mtun{tid}"[:15]

    port = (
        39000
        + (tid % 1000)
    )

    return {
        "interface": iface,
        "network": str(network),
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr":
            f"{iran_ip}/30",
        "exit_addr":
            f"{exit_ip}/30",
        "port": port,
        "mtu": 1280,
        "service":
            f"twinpanel-mtunnel-{tid}.service",
        "config":
            f"/etc/twinpanel/mtunnel/"
            f"tunnel-{tid}.json",
        "runtime":
            "/opt/twinpanel-mtunnel/"
            "mtunnel_node.py",
    }


def ensure_mtunnel_key(
    tunnel_id: int,
) -> bytes:

    MTUNNEL_KEY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        MTUNNEL_KEY_DIR
        / f"tunnel-{int(tunnel_id)}.key"
    )

    if path.exists():
        key = path.read_bytes()

        if len(key) == 32:
            return key

    key = secrets.token_bytes(32)

    path.write_bytes(key)

    os.chmod(
        path,
        0o600,
    )

    return key


async def _run(
    conn,
    command: str,
    timeout: int = 900,
):
    result = await conn.run(
        command,
        check=False,
        timeout=timeout,
    )

    if result.exit_status != 0:
        raise RuntimeError(
            (
                result.stderr
                or result.stdout
                or command
            )[-1800:]
        )

    return result.stdout


async def install_mtunnel_peer(
    conn,
    *,
    tunnel_id: int,
    role: str,
    address: str,
    peer_ip: str,
    key: bytes,
    runtime: dict,
) -> dict:

    source = (
        Path(__file__)
        .with_name(
            "mtunnel_node.py"
        )
        .read_bytes()
    )

    source_b64 = base64.b64encode(
        source
    ).decode()

    config = {
        "tunnel_id":
            int(tunnel_id),
        "role":
            role,
        "interface":
            runtime["interface"],
        "address":
            address,
        "peer_ip":
            peer_ip,
        "port":
            int(runtime["port"]),

        # TWINPANEL_MTUNNEL_SOURCE_PORT_SERVER_ONLY_V1
        #
        # Server listens on fixed tunnel port.
        # Client uses normal UDP source port selection.
        #
        # Adding source_port to client breaks UDP session tracking.


        "mtu":
            int(runtime["mtu"]),
        "key":
            base64.b64encode(
                key
            ).decode(),
    }

    config_b64 = base64.b64encode(
        json.dumps(
            config,
            separators=(",", ":"),
        ).encode()
    ).decode()

    service = runtime["service"]
    runtime_path = runtime["runtime"]
    config_path = runtime["config"]

    unit = f"""[Unit]
Description=TwinPanel MTunnel {int(tunnel_id)}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/opt/twinpanel-mtunnel/venv/bin/python {runtime_path} {config_path}
Restart=always
RestartSec=2
LimitNOFILE=1048576
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

    unit_b64 = base64.b64encode(
        unit.encode()
    ).decode()

    # Everything is installed automatically over saved SSH.
    await _run(
        conn,
        """
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -y >/dev/null
apt-get install -y \
python3 python3-venv python3-pip \
iproute2 iputils-ping >/dev/null
mkdir -p \
/opt/twinpanel-mtunnel \
/etc/twinpanel/mtunnel
if [ ! -x /opt/twinpanel-mtunnel/venv/bin/python ]; then
    python3 -m venv /opt/twinpanel-mtunnel/venv
fi
/opt/twinpanel-mtunnel/venv/bin/pip \
install --disable-pip-version-check \
'cryptography>=42,<47' >/dev/null
""",
        timeout=1200,
    )

    # TWINPANEL_MTUNNEL_AUTO_FIREWALL_V2
    #
    # Only Exit/server needs the fixed inbound UDP port.
    # Do not touch firewall when UFW is disabled.
    if role == "server":
        await _run(
            conn,
            (
                "if command -v ufw >/dev/null 2>&1 "
                "&& ufw status 2>/dev/null "
                "| grep -q '^Status: active'; then "
                f"ufw allow {int(runtime['port'])}/udp "
                ">/dev/null 2>&1 || true; "
                "fi"
            ),
            timeout=120,
        )

    await _run(
        conn,
        (
            f"echo '{source_b64}' | "
            f"base64 -d > {runtime_path} && "
            f"chmod 0700 {runtime_path} && "
            f"echo '{config_b64}' | "
            f"base64 -d > {config_path} && "
            f"chmod 0600 {config_path} && "
            f"echo '{unit_b64}' | "
            "base64 -d > "
            f"/etc/systemd/system/{service} && "
            "systemctl daemon-reload && "
            f"systemctl enable {service} "
            ">/dev/null 2>&1"
        ),
    )

    # Remove only this MTunnel's own stale interface.
    await _run(
        conn,
        (
            f"systemctl stop {service} "
            ">/dev/null 2>&1 || true; "
            f"ip link delete "
            f"{runtime['interface']} "
            ">/dev/null 2>&1 || true; "
            f"systemctl start {service}"
        ),
        timeout=120,
    )

    await __import__(
        "asyncio"
    ).sleep(3)

    state = await conn.run(
        f"systemctl is-active {service}",
        check=False,
    )

    state_text = str(
        state.stdout
    ).strip()

    if state_text != "active":
        journal = await conn.run(
            (
                f"journalctl -u {service} "
                "-n 50 --no-pager"
            ),
            check=False,
        )

        raise RuntimeError(
            "MTunnel service failed: "
            + str(
                journal.stdout
                or journal.stderr
            )[-1800:]
        )

    addr = await conn.run(
        (
            f"ip -4 addr show dev "
            f"{runtime['interface']} "
            "2>/dev/null || true"
        ),
        check=False,
    )

    return {
        "ok": True,
        "role": role,
        "service": state_text,
        "interface":
            runtime["interface"],
        "interface_ready":
            runtime["interface"]
            in str(addr.stdout),
        "address": address,
        "port":
            runtime["port"],
    }


def parse_ping_latency(
    output: str,
):
    match = re.search(
        r"=\s*[\d.]+/([\d.]+)/",
        str(output),
    )

    if not match:
        return None

    try:
        return int(
            round(
                float(
                    match.group(1)
                )
            )
        )
    except Exception:
        return None
