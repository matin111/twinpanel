from __future__ import annotations

import asyncio
import base64
import json
import secrets
import shlex

from sqlalchemy.orm import Session

from . import tp27_tcp_direct
from .common import (
    close_pair,
    connect_pair,
    copy_binary,
    diag,
    mark,
    prerequisites,
    probe,
    run,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL TP27 MIERU TCP L3 V165
#
# Production-safe experimental carrier for networks where raw long-lived TCP
# reaches the Exit but becomes unstable after a few seconds. The proven TP27
# L3 framing/TUN implementation stays unchanged; only the outer transport is
# replaced by Mieru TCP through a local SOCKS5 bridge.
#
# Iran:
#   TP27 client -> loopback bridge -> Mieru SOCKS5 -> Mieru TCP
# Exit:
#   Mita TCP -> loopback TP27 server
#
# The inner TP27 port is never exposed publicly. Existing Direct TCP/MASQUE
# services, configs and firewall rules are not modified by this candidate.
# ============================================================

NAME = "tp27_mieru_tcp"
MIERU_VERSION = "3.38.1"
MTU = 1280
LANES = 8
TP27_BINARY = "/opt/twinpanel/transport/tp27-tcp-direct"
BRIDGE_SCRIPT_PATH = "/opt/twinpanel/transport/tp27-socks-bridge.py"
MIERU_PORT_BASES = (38200, 39200, 40200)

MIERU_CLIENT_SHA256 = {
    "amd64": "f758f886039efcceb6aa9e88c6393ad1d7326e533e0e9a01d378e49bedaa5563",
    "arm64": "2e3577f4a81e69b8fe4bfcca26ec1255a846f98d92d9f50cf46dfe0951bc5edd",
}
MIERU_SERVER_SHA256 = {
    "amd64": "2c7c0be33d34cf126187d97c17484a34b5c62b764c96b0a88ec4cbc7660d72c9",
    "arm64": "3def1c31b8a060c5842649857dc5a500fa0027503fa66440a49005038c94934c",
}


def _port_candidates(tunnel_id: int) -> tuple[int, ...]:
    slot = int(tunnel_id) % 500
    return tuple(base + slot for base in MIERU_PORT_BASES)


def _inner_port(tunnel_id: int) -> int:
    return 49200 + (int(tunnel_id) % 500)


def _socks_port(tunnel_id: int) -> int:
    return 41200 + (int(tunnel_id) % 500)


def _rpc_port(tunnel_id: int) -> int:
    return 42200 + (int(tunnel_id) % 500)


def _bridge_port(tunnel_id: int) -> int:
    return 43200 + (int(tunnel_id) % 500)


def _base_dir(tunnel_id: int) -> str:
    return f"/etc/twinpanel/mieru-tcp/tunnel-{int(tunnel_id)}"


def _token_path(tunnel_id: int) -> str:
    return f"{_base_dir(tunnel_id)}/tp27.token"


def _carrier_services(tunnel_id: int) -> dict[str, str]:
    tid = int(tunnel_id)
    return {
        "iran_mieru": f"twinpanel-tp27-mieru-{tid}-iran.service",
        "exit_mita": f"twinpanel-tp27-mieru-{tid}-exit.service",
        "iran_bridge": f"twinpanel-tp27-mieru-bridge-{tid}-iran.service",
    }


BRIDGE_SCRIPT = r'''#!/usr/bin/env python3
import argparse
import asyncio
import ipaddress
import struct


async def read_exact(reader, size):
    return await reader.readexactly(size)


def target_request(target):
    host, port_text = target.rsplit(":", 1)
    port = int(port_text)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raw = host.encode("idna")
        if not 1 <= len(raw) <= 255:
            raise ValueError("target hostname length out of range")
        addr = b"\x03" + bytes([len(raw)]) + raw
    else:
        if ip.version == 4:
            addr = b"\x01" + ip.packed
        else:
            addr = b"\x04" + ip.packed
    return b"\x05\x01\x00" + addr + struct.pack("!H", port)


async def socks_connect(proxy_host, proxy_port, target, timeout):
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(proxy_host, proxy_port), timeout=timeout
    )
    writer.write(b"\x05\x01\x00")
    await writer.drain()
    greeting = await asyncio.wait_for(read_exact(reader, 2), timeout=timeout)
    if greeting != b"\x05\x00":
        writer.close()
        await writer.wait_closed()
        raise RuntimeError(f"SOCKS auth rejected: {greeting!r}")
    writer.write(target_request(target))
    await writer.drain()
    head = await asyncio.wait_for(read_exact(reader, 4), timeout=timeout)
    if head[0] != 5 or head[1] != 0:
        writer.close()
        await writer.wait_closed()
        raise RuntimeError(f"SOCKS connect rejected: {head!r}")
    atyp = head[3]
    if atyp == 1:
        await read_exact(reader, 4)
    elif atyp == 4:
        await read_exact(reader, 16)
    elif atyp == 3:
        size = (await read_exact(reader, 1))[0]
        await read_exact(reader, size)
    else:
        raise RuntimeError(f"SOCKS reply atyp={atyp}")
    await read_exact(reader, 2)
    return reader, writer


async def pump(reader, writer):
    try:
        while True:
            data = await reader.read(262144)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle(local_reader, local_writer, args):
    try:
        remote_reader, remote_writer = await socks_connect(
            args.socks_host, args.socks_port, args.target, args.timeout
        )
    except Exception:
        local_writer.close()
        await local_writer.wait_closed()
        return
    await asyncio.gather(
        pump(local_reader, remote_writer),
        pump(remote_reader, local_writer),
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--socks-host", default="127.0.0.1")
    parser.add_argument("--socks-port", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    server = await asyncio.start_server(
        lambda r, w: handle(r, w, args), args.listen_host, args.listen_port
    )
    print(
        f"TP27_SOCKS_BRIDGE_READY listen={args.listen_host}:{args.listen_port} "
        f"socks={args.socks_host}:{args.socks_port} target={args.target}",
        flush=True,
    )
    async with server:
        await server.serve_forever()


asyncio.run(main())
'''


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


async def _write_remote(conn, path: str, value: str, mode: str = "0600") -> None:
    payload = _b64(value)
    directory = path.rsplit("/", 1)[0]
    await run(
        conn,
        f"""
set -e
install -d -m 0700 {shlex.quote(directory)}
printf %s {shlex.quote(payload)} | base64 -d > {shlex.quote(path)}.new
chmod {mode} {shlex.quote(path)}.new
mv {shlex.quote(path)}.new {shlex.quote(path)}
""",
        "tp27_mieru_write_config",
        20,
    )


async def _install_mieru_package(conn, *, server: bool) -> str:
    package = "mita" if server else "mieru"
    expected = MIERU_SERVER_SHA256 if server else MIERU_CLIENT_SHA256
    prefix = "mita" if server else "mieru"
    sha_amd64 = expected["amd64"]
    sha_arm64 = expected["arm64"]

    script = f"""
set -e
export DEBIAN_FRONTEND=noninteractive
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64)
    sha={shlex.quote(sha_amd64)}
    asset={shlex.quote(prefix + '_' + MIERU_VERSION + '_amd64.deb')}
    ;;
  arm64)
    sha={shlex.quote(sha_arm64)}
    asset={shlex.quote(prefix + '_' + MIERU_VERSION + '_arm64.deb')}
    ;;
  *)
    echo "unsupported_mieru_arch:$arch" >&2
    exit 64
    ;;
esac
if ! command -v {package} >/dev/null 2>&1 || ! {package} version 2>&1 | grep -q {shlex.quote(MIERU_VERSION)}; then
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y ca-certificates curl >/dev/null
  tmp="$(mktemp --suffix=.deb)"
  trap 'rm -f "$tmp"' EXIT
  curl -fL --retry 3 --connect-timeout 20 \
    "https://github.com/enfein/mieru/releases/download/v{MIERU_VERSION}/$asset" \
    -o "$tmp"
  echo "$sha  $tmp" | sha256sum -c - >/dev/null
  dpkg -i "$tmp" >/dev/null || \
    apt-get -o DPkg::Lock::Timeout=300 -f install -y >/dev/null
fi
command -v {package}
{package} version 2>&1 | head -n1
"""
    result = await run(
        conn,
        script,
        f"tp27_mieru_install_{package}",
        900,
    )
    return result.strip().splitlines()[-1] if result.strip() else MIERU_VERSION


async def _reset_pair(ci, ce, rt: dict, iran_public: str) -> None:
    tid = int(rt["tunnel_id"])
    services = _carrier_services(tid)
    comment = f"TwinPanel-TP27-MIERU-{tid}"
    ports = " ".join(str(p) for p in _port_candidates(tid))

    await asyncio.gather(
        ci.run(
            f"""
set +e
for svc in \
  {shlex.quote(rt['iran_service'])} \
  {shlex.quote(services['iran_bridge'])} \
  {shlex.quote(services['iran_mieru'])}; do
  systemctl disable --now "$svc" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$svc"
done
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
        ce.run(
            f"""
set +e
for svc in \
  {shlex.quote(rt['exit_service'])} \
  {shlex.quote(services['exit_mita'])}; do
  systemctl disable --now "$svc" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$svc"
done
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
if command -v iptables >/dev/null 2>&1; then
  for p in {ports}; do
    while iptables -C INPUT -p tcp --dport "$p" -s {shlex.quote(iran_public)} \
      -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p tcp --dport "$p" -s {shlex.quote(iran_public)} \
        -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
    done
  done
fi
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
    )


async def _wait_listener(conn, host: str, port: int, label: str, attempts: int = 40) -> None:
    result = await conn.run(
        f"""
set +e
for i in $(seq 1 {int(attempts)}); do
  if ss -H -ltn 2>/dev/null | awk '{{print $4}}' | grep -Eq ':{int(port)}$'; then
    exit 0
  fi
  sleep 0.25
done
exit 1
""",
        check=False,
        timeout=max(15, int(attempts // 2)),
    )
    if result.exit_status != 0:
        raise RuntimeError(f"{label}_listener_timeout:{host}:{int(port)}")


async def _install_profile(
    ci,
    ce,
    *,
    tunnel_id: int,
    iran_public: str,
    exit_public: str,
    rt: dict,
    public_port: int,
    username: str,
    password: str,
) -> None:
    tid = int(tunnel_id)
    services = _carrier_services(tid)
    directory = _base_dir(tid)
    token_path = _token_path(tid)
    inner_port = _inner_port(tid)
    socks_port = _socks_port(tid)
    rpc_port = _rpc_port(tid)
    bridge_port = _bridge_port(tid)
    comment = f"TwinPanel-TP27-MIERU-{tid}"

    busy = await ce.run(
        f"ss -H -ltn 'sport = :{int(public_port)}' 2>/dev/null | grep -q .",
        check=False,
        timeout=10,
    )
    if busy.exit_status == 0:
        raise RuntimeError(f"tp27_mieru_tcp_port_busy:{int(public_port)}")

    server_config = {
        "portBindings": [{"port": int(public_port), "protocol": "TCP"}],
        "users": [
            {
                "name": username,
                "password": password,
                "allowLoopbackIP": True,
            }
        ],
        "loggingLevel": "INFO",
        "mtu": MTU,
        "dns": {"dualStack": "PREFER_IPv4"},
    }
    client_config = {
        "profiles": [
            {
                "profileName": "tp27",
                "user": {"name": username, "password": password},
                "servers": [
                    {
                        "ipAddress": exit_public,
                        "domainName": "",
                        "portBindings": [
                            {"port": int(public_port), "protocol": "TCP"}
                        ],
                    }
                ],
                "mtu": MTU,
                "multiplexing": {"level": "MULTIPLEXING_MIDDLE"},
                "handshakeMode": "HANDSHAKE_NO_WAIT",
            }
        ],
        "activeProfile": "tp27",
        "rpcPort": rpc_port,
        "socks5Port": socks_port,
        "loggingLevel": "INFO",
        "socks5ListenLAN": False,
        "advancedSettings": {"noCheckUpdate": True},
    }

    await asyncio.gather(
        _write_remote(
            ce,
            f"{directory}/server.json",
            json.dumps(server_config, ensure_ascii=False, indent=2) + "\n",
        ),
        _write_remote(
            ci,
            f"{directory}/client.json",
            json.dumps(client_config, ensure_ascii=False, indent=2) + "\n",
        ),
    )

    mita_unit = f"""[Unit]
Description=TwinPanel TP27 Mieru TCP {tid} Exit Carrier
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
Environment=MITA_CONFIG_JSON_FILE={directory}/server.json
Environment=MITA_UDS_PATH=/run/twinpanel-mita-{tid}/mita.sock
Environment=MITA_LOG_NO_TIMESTAMP=1
RuntimeDirectory=twinpanel-mita-{tid}
ExecStart=/usr/bin/mita run
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    exit_tp27_unit = f"""[Unit]
Description=TwinPanel TP27 Mieru TCP {tid} Exit L3
Wants=network-online.target
After=network-online.target {services['exit_mita']}
Requires={services['exit_mita']}

[Service]
Type=simple
User=root
ExecStart={TP27_BINARY} --mode server --tun {rt['interface']} --local {rt['exit_addr']} --listen 127.0.0.1:{inner_port} --lanes {LANES} --mtu {MTU} --token-file {token_path}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_ADMIN
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    mieru_unit = f"""[Unit]
Description=TwinPanel TP27 Mieru TCP {tid} Iran Carrier
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
Environment=MIERU_CONFIG_JSON_FILE={directory}/client.json
ExecStart=/usr/bin/mieru run
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    bridge_unit = f"""[Unit]
Description=TwinPanel TP27 Mieru TCP {tid} Iran SOCKS Bridge
After={services['iran_mieru']}
Requires={services['iran_mieru']}

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 {BRIDGE_SCRIPT_PATH} --listen-port {bridge_port} --socks-port {socks_port} --target 127.0.0.1:{inner_port} --timeout 8
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    iran_tp27_unit = f"""[Unit]
Description=TwinPanel TP27 Mieru TCP {tid} Iran L3
After={services['iran_bridge']}
Requires={services['iran_bridge']}

[Service]
Type=simple
User=root
ExecStart={TP27_BINARY} --mode client --tun {rt['interface']} --local {rt['iran_addr']} --peer 127.0.0.1:{bridge_port} --lanes {LANES} --mtu {MTU} --token-file {token_path}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_ADMIN
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    await run(
        ce,
        f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p tcp --dport {int(public_port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {int(public_port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT
fi
cat > /etc/systemd/system/{shlex.quote(services['exit_mita'])} <<'EOF'
{mita_unit}EOF
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
{exit_tp27_unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(services['exit_mita'])} {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(services['exit_mita'])}
""",
        "tp27_mieru_exit_carrier_install",
        60,
    )
    await _wait_listener(ce, "0.0.0.0", int(public_port), "mita")

    await run(
        ce,
        f"systemctl restart {shlex.quote(rt['exit_service'])}",
        "tp27_mieru_exit_l3_start",
        30,
    )
    await _wait_listener(ce, "127.0.0.1", inner_port, "tp27_inner")

    await run(
        ci,
        f"""
set -e
cat > /etc/systemd/system/{shlex.quote(services['iran_mieru'])} <<'EOF'
{mieru_unit}EOF
cat > /etc/systemd/system/{shlex.quote(services['iran_bridge'])} <<'EOF'
{bridge_unit}EOF
cat > /etc/systemd/system/{shlex.quote(rt['iran_service'])} <<'EOF'
{iran_tp27_unit}EOF
systemctl daemon-reload
systemctl enable \
  {shlex.quote(services['iran_mieru'])} \
  {shlex.quote(services['iran_bridge'])} \
  {shlex.quote(rt['iran_service'])} >/dev/null
systemctl restart {shlex.quote(services['iran_mieru'])}
""",
        "tp27_mieru_iran_carrier_install",
        60,
    )
    await _wait_listener(ci, "127.0.0.1", socks_port, "mieru_socks")

    await run(
        ci,
        f"systemctl restart {shlex.quote(services['iran_bridge'])}",
        "tp27_mieru_bridge_start",
        30,
    )
    await _wait_listener(ci, "127.0.0.1", bridge_port, "socks_bridge")

    await run(
        ci,
        f"systemctl restart {shlex.quote(rt['iran_service'])}",
        "tp27_mieru_iran_l3_start",
        30,
    )

    await asyncio.sleep(5.0)


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    tp27_artifact, tp27_sha = tp27_tcp_direct._artifact()
    token = secrets.token_urlsafe(36)
    username = f"tp27-{int(tunnel_id)}-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(32)
    token_path = _token_path(tunnel_id)
    attempts: list[dict] = []

    meta_base = {
        **rt,
        "generation": 165,
        "carrier_class": "mieru-tcp-l3",
        "depends_on": f"Mieru {MIERU_VERSION}",
        "mtu": MTU,
        "lanes": LANES,
        "bridge_runtime": "python3-asyncio-socks5",
        "tp27_artifact_sha256": tp27_sha,
        "port_candidates": list(_port_candidates(tunnel_id)),
        "source_built": True,
        "inner_port": _inner_port(tunnel_id),
        "socks_port": _socks_port(tunnel_id),
        "rpc_port": _rpc_port(tunnel_id),
        "bridge_port": _bridge_port(tunnel_id),
    }

    mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=str(meta_base),
    )

    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        client_version, server_version = await asyncio.gather(
            _install_mieru_package(ci, server=False),
            _install_mieru_package(ce, server=True),
        )

        await asyncio.gather(
            copy_binary(ci, str(tp27_artifact), TP27_BINARY),
            copy_binary(ce, str(tp27_artifact), TP27_BINARY),
        )
        await run(
            ci,
            "install -d -m 0755 /opt/twinpanel/transport",
            "tp27_mieru_bridge_dir",
            15,
        )
        await _write_remote(ci, BRIDGE_SCRIPT_PATH, BRIDGE_SCRIPT, mode="0755")

        await asyncio.gather(
            _write_remote(ci, token_path, token),
            _write_remote(ce, token_path, token),
        )

        for public_port in _port_candidates(tunnel_id):
            try:
                await _reset_pair(ci, ce, rt, str(iran.public_ip))
                await _install_profile(
                    ci,
                    ce,
                    tunnel_id=int(tunnel_id),
                    iran_public=str(iran.public_ip),
                    exit_public=str(exit_node.public_ip),
                    rt=rt,
                    public_port=int(public_port),
                    username=username,
                    password=password,
                )
                health = await probe(
                    ci,
                    ce,
                    name=NAME,
                    tunnel_id=int(tunnel_id),
                    rt=rt,
                )
                attempts.append({"port": int(public_port), "result": "online"})

                meta = {
                    **meta_base,
                    **health,
                    "selected_port": int(public_port),
                    "client_version": client_version,
                    "server_version": server_version,
                    "attempts": attempts,
                }
                mark(
                    db,
                    tunnel_id,
                    NAME,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=str(meta),
                )
                return {
                    "ok": True,
                    "transport": NAME,
                    "runtime": rt,
                    "port": int(public_port),
                    "probe": health,
                }
            except Exception as exc:
                attempts.append(
                    {
                        "port": int(public_port),
                        "result": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        await _reset_pair(ci, ce, rt, str(iran.public_ip))
        raise RuntimeError(f"tp27_mieru_tcp_all_ports_failed:{attempts!r}")

    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        message = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-1800:]} | exit={b[-1800:]}"
        )
        mark(db, tunnel_id, NAME, status="failed", error=message)
        raise RuntimeError(message) from exc
    finally:
        await close_pair(ci, ce)
