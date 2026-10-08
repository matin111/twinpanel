from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
import tarfile
import urllib.request
from pathlib import Path
from sqlalchemy.orm import Session

from .common import arch, cache_dir, close_pair, connect_pair, copy_binary, diag, mark, prerequisites, probe, run, runtime, tunnel_nodes

VERSION = "3.3.0"
BASE = f"https://github.com/go-gost/gost/releases/download/v{VERSION}"


def _download(raw_arch: str) -> str:
    a = arch(raw_arch)
    root = cache_dir() / f"gost-{VERSION}-{a}"
    binary = root / "gost"
    if binary.is_file() and os.access(binary, os.X_OK):
        return str(binary)
    root.mkdir(parents=True, exist_ok=True)
    asset = f"gost_{VERSION}_linux_{a}.tar.gz"
    archive, sums = root / asset, root / "checksums.txt"
    urllib.request.urlretrieve(f"{BASE}/{asset}", archive)
    urllib.request.urlretrieve(f"{BASE}/checksums.txt", sums)
    expected = next((line.split()[0] for line in sums.read_text(errors="ignore").splitlines() if line.split() and line.split()[-1].lstrip('*') == asset), None)
    if not expected:
        raise RuntimeError("gost_checksum_missing")
    if hashlib.sha256(archive.read_bytes()).hexdigest().lower() != expected.lower():
        raise RuntimeError("gost_checksum_mismatch")
    with tarfile.open(archive, "r:gz") as tf:
        member = next((m for m in tf.getmembers() if m.isfile() and Path(m.name).name == "gost"), None)
        if member is None:
            raise RuntimeError("gost_binary_missing_in_archive")
        src = tf.extractfile(member)
        if src is None:
            raise RuntimeError("gost_extract_failed")
        binary.write_bytes(src.read())
    binary.chmod(0o755)
    return str(binary)


async def install(tunnel_id: int, db: Session) -> dict:
    name = "gost_tun"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))
    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))
        ia, ea = await asyncio.gather(run(ci, "uname -m", "iran_arch"), run(ce, "uname -m", "exit_arch"))
        ib, eb = await asyncio.gather(asyncio.to_thread(_download, ia), asyncio.to_thread(_download, ea))
        await asyncio.gather(copy_binary(ci, ib, "/usr/local/bin/twinpanel-gost"), copy_binary(ce, eb, "/usr/local/bin/twinpanel-gost"))

        port = int(rt["port"])
        path = f"/tp-{int(tunnel_id)}-{hashlib.sha256(str(tunnel_id).encode()).hexdigest()[:10]}"
        await run(ce, f"""
set -e
if command -v iptables >/dev/null 2>&1; then iptables -C INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT; fi
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/WSS {int(tunnel_id)} Exit
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:8421?net={rt['exit_addr']}&name={rt['interface']}&mtu=1360 -L=relay+wss://:{port}?bind=true&path={path}
Restart=always
RestartSec=2
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(rt['exit_service'])}
""", "gost_exit_install", 90)

        await run(ci, f"""
set -e
cat > /etc/systemd/system/{shlex.quote(rt['iran_service'])} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/WSS {int(tunnel_id)} Iran
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:0/:8421?net={rt['iran_addr']}&name={rt['interface']}&mtu=1360 -F=relay+wss://{exit_node.public_ip}:{port}?path={path}&secure=false&keepalive=true&ttl=10s
Restart=always
RestartSec=2
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['iran_service'])} >/dev/null
systemctl restart {shlex.quote(rt['iran_service'])}
""", "gost_iran_install", 90)

        for _ in range(15):
            await asyncio.sleep(2)
            ok = await ci.run(f"ip link show {shlex.quote(rt['interface'])} >/dev/null 2>&1", check=False)
            if ok.exit_status == 0:
                break
        health = await probe(ci, ce, name=name, tunnel_id=tunnel_id, rt=rt)
        mark(db, tunnel_id, name, status="online", latency_ms=health["latency_ms"], meta=str({**rt, **health, "version": VERSION}))
        return {"ok": True, "transport": name, "runtime": rt, "probe": health, "version": VERSION}
    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = f"{type(exc).__name__}: {exc} | iran={a[-1800:]} | exit={b[-1800:]}"
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await close_pair(ci, ce)
