from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import shlex
import urllib.request
from sqlalchemy.orm import Session

from ..config import settings
from .common import cache_dir, close_pair, connect_pair, diag, mark, prerequisites, probe, run, runtime, tunnel_nodes

GO_COMMIT = "b5928efb6ca19f0153958460c3d141f04abc5c2e"
TOOLS_COMMIT = "ee0f0a9aa34ff0a0da4b3433b9512781cfe02843"


def _source(repo: str, commit: str, label: str) -> str:
    root = cache_dir() / "sources"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{label}-{commit}.tar.gz"
    if not path.is_file() or path.stat().st_size <= 1024:
        urllib.request.urlretrieve(f"https://github.com/{repo}/archive/{commit}.tar.gz", path)
    if path.stat().st_size <= 1024:
        raise RuntimeError(f"source_archive_invalid:{label}")
    return str(path)


def _hp_key(tunnel_id: int) -> str:
    raw = hmac.new(settings.app_secret_key.encode(), f"awg-header:{int(tunnel_id)}".encode(), hashlib.sha256).digest()
    return base64.b64encode(raw).decode()


async def _ensure(conn) -> None:
    check = await conn.run("command -v amneziawg-go >/dev/null 2>&1 && command -v awg >/dev/null 2>&1", check=False)
    if check.exit_status == 0:
        return
    go_src, tools_src = await asyncio.gather(
        asyncio.to_thread(_source, "amnezia-vpn/amneziawg-go", GO_COMMIT, "amneziawg-go"),
        asyncio.to_thread(_source, "amnezia-vpn/amneziawg-tools", TOOLS_COMMIT, "amneziawg-tools"),
    )
    await run(conn, "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq; apt-get install -y -qq build-essential make golang-go", "awg_prerequisites", 600)
    async with conn.start_sftp_client() as sftp:
        await sftp.put(go_src, "/tmp/tp-awg-go.tar.gz")
        await sftp.put(tools_src, "/tmp/tp-awg-tools.tar.gz")
    await run(conn, """
set -e
rm -rf /usr/local/src/tp-amneziawg-go /usr/local/src/tp-amneziawg-tools
mkdir -p /usr/local/src/tp-amneziawg-go /usr/local/src/tp-amneziawg-tools
tar -xzf /tmp/tp-awg-go.tar.gz --strip-components=1 -C /usr/local/src/tp-amneziawg-go
cd /usr/local/src/tp-amneziawg-go && make && install -m 0755 amneziawg-go /usr/local/bin/amneziawg-go
tar -xzf /tmp/tp-awg-tools.tar.gz --strip-components=1 -C /usr/local/src/tp-amneziawg-tools
cd /usr/local/src/tp-amneziawg-tools/src && make && install -m 0755 awg /usr/local/bin/awg
rm -f /tmp/tp-awg-go.tar.gz /tmp/tp-awg-tools.tar.gz
""", "awg_build", 900)


async def _key(conn, path: str) -> tuple[str, str]:
    out = await run(conn, f"""
set -e
install -d -m 700 /etc/twinpanel/amneziawg
if [ ! -s {shlex.quote(path)} ]; then umask 077; /usr/local/bin/awg genkey > {shlex.quote(path)}; fi
P="$(cat {shlex.quote(path)})"; printf '%s\n%s\n' "$P" "$(printf '%s' "$P" | /usr/local/bin/awg pubkey)"
""", "awg_key")
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    if len(lines) < 2:
        raise RuntimeError("awg_key_generation_failed")
    return lines[-2], lines[-1]


async def install(tunnel_id: int, db: Session) -> dict:
    name = "amneziawg"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))
    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))
        await asyncio.gather(_ensure(ci), _ensure(ce))
        key_path = f"/etc/twinpanel/amneziawg/tunnel-{tunnel_id}.key"
        (ipr, ipu), (epr, epu) = await asyncio.gather(_key(ci, key_path), _key(ce, key_path))
        port, iface, hp = int(rt["port"]), rt["interface"], _hp_key(tunnel_id)
        extra = f"Jc = 6\nJmin = 40\nJmax = 120\nS1 = 16\nS2 = 16\nS3 = 16\nS4 = 16\nH1 = 121211-121999\nH2 = 122211-122999\nH3 = 123211-123999\nH4 = 124211-124999\nHeaderProtectionKey = {hp}\nContentPaddingAddition = 0-32\n"

        async def peer(conn, *, role: str, addr: str, priv: str, pub: str, endpoint: str | None, listen: int | None, service: str):
            conf = f"/etc/twinpanel/amneziawg/tunnel-{tunnel_id}-{role}.conf"
            ep = f"Endpoint = {endpoint}\nPersistentKeepalive = 15-25\n" if endpoint else ""
            lp = f"ListenPort = {listen}\n" if listen else ""
            cfg = f"[Interface]\nPrivateKey = {priv}\n{lp}{extra}\n[Peer]\nPublicKey = {pub}\nAllowedIPs = 0.0.0.0/0\n{ep}"
            await run(conn, f"""
set -e
cat > {shlex.quote(conf)} <<'EOF'
{cfg}EOF
chmod 600 {shlex.quote(conf)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
[Unit]
Description=TwinPanel AmneziaWG {tunnel_id} {role}
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -lc 'ip link del {iface} >/dev/null 2>&1 || true; /usr/local/bin/amneziawg-go {iface}; sleep 1; /usr/local/bin/awg setconf {iface} {conf}; ip addr add {addr} dev {iface}; ip link set dev {iface} mtu 1280 up'
ExecStop=/bin/bash -lc 'ip link del {iface} >/dev/null 2>&1 || true'
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""", f"awg_{role}_install", 120)

        await run(ce, f"if command -v iptables >/dev/null 2>&1; then iptables -C INPUT -p udp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-AWG-{tunnel_id} -j ACCEPT 2>/dev/null || iptables -I INPUT -p udp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-AWG-{tunnel_id} -j ACCEPT; fi", "awg_firewall")
        await asyncio.gather(
            peer(ce, role="exit", addr=rt["exit_addr"], priv=epr, pub=ipu, endpoint=None, listen=port, service=rt["exit_service"]),
            peer(ci, role="iran", addr=rt["iran_addr"], priv=ipr, pub=epu, endpoint=f"{exit_node.public_ip}:{port}", listen=None, service=rt["iran_service"]),
        )
        await asyncio.sleep(4)
        health = await probe(ci, ce, name=name, tunnel_id=tunnel_id, rt=rt)
        mark(db, tunnel_id, name, status="online", latency_ms=health["latency_ms"], meta=str({**rt, **health, "go_commit": GO_COMMIT, "tools_commit": TOOLS_COMMIT}))
        return {"ok": True, "transport": name, "runtime": rt, "probe": health}
    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = f"{type(exc).__name__}: {exc} | iran={a[-1800:]} | exit={b[-1800:]}"
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await close_pair(ci, ce)
