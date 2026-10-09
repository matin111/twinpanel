from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
import tarfile
import urllib.request
from pathlib import Path

from sqlalchemy.orm import Session

from .common import (
    arch,
    cache_dir,
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

VERSION = "3.3.0"
BASE = f"https://github.com/go-gost/gost/releases/download/v{VERSION}"
FORWARD_PORT = 8421


def _download(raw_arch: str) -> str:
    a = arch(raw_arch)
    root = cache_dir() / f"gost-{VERSION}-{a}"
    binary = root / "gost"
    if binary.is_file() and os.access(binary, os.X_OK):
        return str(binary)

    root.mkdir(parents=True, exist_ok=True)
    asset = f"gost_{VERSION}_linux_{a}.tar.gz"
    archive = root / asset
    sums = root / "checksums.txt"

    urllib.request.urlretrieve(f"{BASE}/{asset}", archive)
    urllib.request.urlretrieve(f"{BASE}/checksums.txt", sums)

    expected = next(
        (
            line.split()[0]
            for line in sums.read_text(errors="ignore").splitlines()
            if line.split() and line.split()[-1].lstrip("*") == asset
        ),
        None,
    )
    if not expected:
        raise RuntimeError("gost_checksum_missing")

    actual = hashlib.sha256(archive.read_bytes()).hexdigest().lower()
    if actual != expected.lower():
        raise RuntimeError("gost_checksum_mismatch")

    with tarfile.open(archive, "r:gz") as tf:
        member = next(
            (
                item
                for item in tf.getmembers()
                if item.isfile() and Path(item.name).name == "gost"
            ),
            None,
        )
        if member is None:
            raise RuntimeError("gost_binary_missing_in_archive")
        src = tf.extractfile(member)
        if src is None:
            raise RuntimeError("gost_extract_failed")
        binary.write_bytes(src.read())

    binary.chmod(0o755)
    return str(binary)


async def _wait_interface(conn, iface: str, service: str, label: str) -> None:
    for _ in range(20):
        state = await conn.run(
            f"systemctl is-active --quiet {shlex.quote(service)} && "
            f"ip link show {shlex.quote(iface)} >/dev/null 2>&1",
            check=False,
            timeout=10,
        )
        if state.exit_status == 0:
            return
        await asyncio.sleep(1)
    raise RuntimeError(f"{label}_not_ready")


async def _raw_tcp_preflight(conn, host: str, port: int) -> None:
    result = await conn.run(
        f"""python3 - <<'PY'
import socket
host={host!r}
port={int(port)}
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.settimeout(6)
try:
    s.connect((host,port))
finally:
    s.close()
PY""",
        check=False,
        timeout=12,
    )
    if result.exit_status != 0:
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(f"gost_wss_tcp_preflight_failed: {text[-2000:] or 'connect_failed'}")


async def install(tunnel_id: int, db: Session) -> dict:
    name = "gost_tun"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))

    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        iran_arch, exit_arch = await asyncio.gather(
            run(ci, "uname -m", "iran_arch"),
            run(ce, "uname -m", "exit_arch"),
        )
        iran_binary, exit_binary = await asyncio.gather(
            asyncio.to_thread(_download, iran_arch),
            asyncio.to_thread(_download, exit_arch),
        )
        await asyncio.gather(
            copy_binary(ci, iran_binary, "/usr/local/bin/twinpanel-gost"),
            copy_binary(ce, exit_binary, "/usr/local/bin/twinpanel-gost"),
        )

        port = int(rt["port"])

        # Use GOST's documented TUN-over-WSS forward-chain form exactly.
        # KeepAlive belongs to the TUN client, not to the WSS chain URL.
        await run(
            ce,
            f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT
fi
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/WSS {int(tunnel_id)} Exit
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:{FORWARD_PORT}?net={rt['exit_addr']}&name={rt['interface']}&mtu=1360 -L=relay+wss://:{port}?bind=true
Restart=always
RestartSec=2
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(rt['exit_service'])}
""",
            "gost_exit_install",
            90,
        )

        await _wait_interface(
            ce,
            str(rt["interface"]),
            str(rt["exit_service"]),
            "gost_exit",
        )

        await _raw_tcp_preflight(ci, str(exit_node.public_ip), port)

        await run(
            ci,
            f"""
set -e
cat > /etc/systemd/system/{shlex.quote(rt['iran_service'])} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/WSS {int(tunnel_id)} Iran
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:0/:{FORWARD_PORT}?net={rt['iran_addr']}&name={rt['interface']}&mtu=1360&keepAlive=true&ttl=10s -F=relay+wss://{exit_node.public_ip}:{port}?secure=false
Restart=always
RestartSec=2
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['iran_service'])} >/dev/null
systemctl restart {shlex.quote(rt['iran_service'])}
""",
            "gost_iran_install",
            90,
        )

        await _wait_interface(
            ci,
            str(rt["interface"]),
            str(rt["iran_service"]),
            "gost_iran",
        )

        # Give the forward-chain a short window to establish before the real
        # peer/TCP/UDP probe sends traffic through the TUN device.
        await asyncio.sleep(2)

        health = await probe(
            ci,
            ce,
            name=name,
            tunnel_id=tunnel_id,
            rt=rt,
        )

        meta = {
            **rt,
            **health,
            "version": VERSION,
            "carrier": "relay+wss",
            "profile": "documented-forward-chain-v2",
        }
        mark(
            db,
            tunnel_id,
            name,
            status="online",
            latency_ms=health["latency_ms"],
            meta=str(meta),
        )
        return {
            "ok": True,
            "transport": name,
            "runtime": rt,
            "probe": health,
            "version": VERSION,
            "carrier": "relay+wss",
            "profile": "documented-forward-chain-v2",
        }

    except Exception as exc:
        iran_diag = (
            await diag(ci, rt["iran_service"], rt["interface"])
            if ci
            else ""
        )
        exit_diag = (
            await diag(ce, rt["exit_service"], rt["interface"])
            if ce
            else ""
        )
        msg = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={iran_diag[-2500:]} | exit={exit_diag[-2500:]}"
        )
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc

    finally:
        await close_pair(ci, ce)
