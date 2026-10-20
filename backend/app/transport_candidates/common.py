from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Node, Tunnel, TunnelTransport
from ..routers.provision import ssh_connect_saved

SPECS: dict[str, dict[str, Any]] = {
    "kernel_gre": {"priority": 110, "label": "Kernel GRE", "family": "kernel-l3"},
    "gost_tun": {"priority": 120, "label": "GOST TUN/WSS", "family": "tcp-tls-l3"},
    "amneziawg": {"priority": 130, "label": "AmneziaWG 3.1", "family": "obfuscated-udp-l3"},
    "netrix": {"priority": 140, "label": "Netrix TUN", "family": "licensed-multipath-l3"},
}

_PACKET_LOSS_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)%\s*packet loss",
    flags=re.IGNORECASE,
)


def parse_packet_loss_pct(output: str) -> float | None:
    """Return ping packet loss as a percentage, or None when unavailable.

    Candidate health must fail closed when ping output cannot be interpreted;
    silently treating a missing loss field as 0% can promote a degraded L3
    carrier. Probe commands force LC_ALL=C so the parser receives the standard
    iputils summary format.
    """

    match = _PACKET_LOSS_RE.search(str(output or ""))
    if not match:
        return None

    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None

    if value < 0.0 or value > 100.0:
        return None
    return value


def runtime(name: str, tunnel_id: int) -> dict[str, Any]:
    tid = max(int(tunnel_id), 1)
    if name not in SPECS:
        raise ValueError("unknown_transport")
    octet = {"kernel_gre": 248, "gost_tun": 247, "amneziawg": 246, "netrix": 245}[name]
    prefix = {"kernel_gre": "gr", "gost_tun": "gs", "amneziawg": "aw", "netrix": "nx"}[name]
    port_base = {"kernel_gre": None, "gost_tun": 25000, "amneziawg": 26000, "netrix": 27000}[name]
    third = (tid // 64) % 250
    block = (tid % 64) * 4
    iran_ip, exit_ip = f"10.{octet}.{third}.{block+1}", f"10.{octet}.{third}.{block+2}"
    return {
        "transport": name,
        "interface": f"tp{prefix}{tid}"[:15],
        "network": f"10.{octet}.{third}.{block}/30",
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr": f"{iran_ip}/30",
        "exit_addr": f"{exit_ip}/30",
        "port": None if port_base is None else port_base + tid % 10000,
        "iran_service": f"twinpanel-{name}-{tid}-iran.service",
        "exit_service": f"twinpanel-{name}-{tid}-exit.service",
        "priority": SPECS[name]["priority"],
    }


def catalog() -> list[dict[str, Any]]:
    return [{"transport": name, **spec} for name, spec in SPECS.items()]


def tunnel_nodes(db: Session, tunnel_id: int) -> tuple[Tunnel, Node, Node]:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")
    iran = db.query(Node).filter(Node.id == tunnel.iran_node_id, Node.retired_at.is_(None)).first()
    exit_node = db.query(Node).filter(Node.id == tunnel.exit_node_id, Node.retired_at.is_(None)).first()
    if iran is None or exit_node is None:
        raise RuntimeError("tunnel_nodes_missing")
    return tunnel, iran, exit_node


def mark(db: Session, tunnel_id: int, name: str, *, status: str, error: str | None = None, latency_ms: int | None = None, enabled: bool = True, meta: str | None = None) -> TunnelTransport:
    row = db.query(TunnelTransport).filter(TunnelTransport.tunnel_id == int(tunnel_id), TunnelTransport.transport == name).first()
    if row is None:
        row = TunnelTransport(tunnel_id=int(tunnel_id), transport=name, priority=int(SPECS[name]["priority"]), enabled=enabled, status=status)
        db.add(row)
        db.flush()
    row.priority = int(SPECS[name]["priority"])
    row.enabled = enabled
    row.status = status
    row.last_error = error[:7000] if error else None
    row.latency_ms = latency_ms
    row.updated_at = datetime.utcnow()
    if meta is not None:
        row.config_text = meta
    if status == "online":
        row.last_healthy_at = datetime.utcnow()
    db.commit(); db.refresh(row)
    return row


async def run(conn, script: str, label: str, timeout: int = 150) -> str:
    result = await conn.run(script, check=False, timeout=timeout)
    if result.exit_status != 0:
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(f"{label}: {text[-5000:] or 'command_failed'}")
    return (result.stdout or "").strip()


async def diag(conn, service: str, iface: str) -> str:
    result = await conn.run(f"""
set +e
systemctl status {shlex.quote(service)} --no-pager -l 2>&1 || true
journalctl -u {shlex.quote(service)} -n 80 --no-pager 2>&1 || true
ip -details addr show dev {shlex.quote(iface)} 2>&1 || true
""", check=False, timeout=45)
    return ((result.stdout or "") + "\n" + (result.stderr or ""))[-7000:]


async def connect_pair(iran: Node, exit_node: Node, db: Session):
    return await asyncio.gather(ssh_connect_saved(iran, db), ssh_connect_saved(exit_node, db))


async def prerequisites(conn) -> None:
    await run(conn, """
set -e
command -v ip >/dev/null
command -v systemctl >/dev/null
command -v python3 >/dev/null
if ! command -v curl >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates
fi
""", "node_prerequisites", 180)


async def default_interface(conn) -> str:
    out = await run(conn, r"""ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'""", "default_interface", 30)
    value = out.strip().splitlines()[0] if out.strip() else ""
    if not value:
        raise RuntimeError("default_interface_missing")
    return value


def policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
    idx = list(SPECS).index(name)
    value = 22000 + idx * 1000 + (int(tunnel_id) % 900)
    return value, value


async def probe(ci, ce, *, name: str, tunnel_id: int, rt: dict[str, Any]) -> dict[str, Any]:
    table, priority = policy_ids(name, tunnel_id)
    public_if = await default_interface(ce)
    comment = f"TwinPanel-{name}-{int(tunnel_id)}"
    await run(ce, f"""
set -e
sysctl -w net.ipv4.ip_forward=1 >/dev/null
if command -v iptables >/dev/null 2>&1; then
 iptables -t nat -C POSTROUTING -s {shlex.quote(rt['network'])} -o {shlex.quote(public_if)} -m comment --comment {shlex.quote(comment)} -j MASQUERADE 2>/dev/null || \
 iptables -t nat -A POSTROUTING -s {shlex.quote(rt['network'])} -o {shlex.quote(public_if)} -m comment --comment {shlex.quote(comment)} -j MASQUERADE
fi
""", "canary_nat", 45)
    await run(ci, f"""
set -e
ip rule del priority {priority} 2>/dev/null || true
ip route flush table {table} 2>/dev/null || true
ip route add table {table} default via {shlex.quote(rt['exit_ip'])} dev {shlex.quote(rt['interface'])}
ip rule add priority {priority} from {shlex.quote(rt['iran_ip'])}/32 table {table}
""", "canary_policy", 45)

    p1, p2 = await asyncio.gather(
        ci.run(f"LC_ALL=C ping -I {shlex.quote(rt['interface'])} -c 3 -W 2 {shlex.quote(rt['exit_ip'])}", check=False, timeout=15),
        ce.run(f"LC_ALL=C ping -I {shlex.quote(rt['interface'])} -c 3 -W 2 {shlex.quote(rt['iran_ip'])}", check=False, timeout=15),
    )

    iran_loss = parse_packet_loss_pct(p1.stdout or "")
    exit_loss = parse_packet_loss_pct(p2.stdout or "")

    if iran_loss is None or exit_loss is None:
        raise RuntimeError(
            "peer_ping_loss_parse_failed: "
            f"iran={iran_loss!r} exit={exit_loss!r}"
        )

    if p1.exit_status != 0 or p2.exit_status != 0:
        raise RuntimeError(
            "peer_ping_failed: "
            f"iran={p1.exit_status}/{iran_loss:.1f}% "
            f"exit={p2.exit_status}/{exit_loss:.1f}%"
        )

    packet_loss = max(float(iran_loss), float(exit_loss))
    latency = None
    match = re.search(r"=\s*[0-9.]+/([0-9.]+)/", (p1.stdout or ""))
    if match:
        latency = max(1, int(round(float(match.group(1)))))

    tcp = await ci.run(f"""
set +e
for URL in https://api.ipify.org https://ifconfig.me/ip; do
 OUT="$(curl --interface {shlex.quote(rt['iran_ip'])} -4 -fsS --max-time 8 "$URL" 2>/dev/null)" || true
 if printf '%s' "$OUT" | grep -Eq '^[0-9]+([.][0-9]+){{3}}$'; then printf '%s' "$OUT"; exit 0; fi
done
exit 1
""", check=False, timeout=25)
    if tcp.exit_status != 0:
        raise RuntimeError("tcp_egress_probe_failed")

    udp = await ci.run(f"""python3 - <<'PY'
import random,socket,struct
src={rt['iran_ip']!r}; tid=random.randrange(65536)
q=struct.pack('!HHHHHH',tid,0x0100,1,0,0,0)
for part in 'cloudflare.com'.split('.'): q+=bytes([len(part)])+part.encode()
q+=b'\\x00'+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(5); s.bind((src,0)); s.sendto(q,('1.1.1.1',53))
data,_=s.recvfrom(4096)
raise SystemExit(0 if len(data)>=12 and struct.unpack('!H',data[:2])[0]==tid else 2)
PY""", check=False, timeout=12)
    if udp.exit_status != 0:
        raise RuntimeError("udp_egress_probe_failed")

    return {
        "peer_ping": True,
        "tcp_egress": True,
        "udp_egress": True,
        "egress_ip": (tcp.stdout or "").strip(),
        "latency_ms": latency,
        "packet_loss_pct": packet_loss,
        "iran_packet_loss_pct": float(iran_loss),
        "exit_packet_loss_pct": float(exit_loss),
    }


async def copy_binary(conn, local_path: str, remote_path: str) -> None:
    tmp = remote_path + ".tmp"
    await run(conn, f"install -d -m 755 {shlex.quote(str(Path(remote_path).parent))}", "binary_dir")
    async with conn.start_sftp_client() as sftp:
        await sftp.put(local_path, tmp)
    await run(conn, f"chmod 0755 {shlex.quote(tmp)} && mv -f {shlex.quote(tmp)} {shlex.quote(remote_path)}", "binary_install")


def cache_dir() -> Path:
    path = Path("/opt/twinpanel/runtime/cache")
    path.mkdir(parents=True, exist_ok=True)
    return path


def arch(value: str) -> str:
    value = value.strip().lower()
    if value in {"x86_64", "amd64"}: return "amd64"
    if value in {"aarch64", "arm64"}: return "arm64"
    raise RuntimeError(f"unsupported_architecture:{value}")


def secret(label: str, tunnel_id: int, length: int = 48) -> str:
    return hmac.new(settings.app_secret_key.encode(), f"{label}:{int(tunnel_id)}".encode(), hashlib.sha256).hexdigest()[:length]


async def close_pair(*connections) -> None:
    for conn in connections:
        if conn is not None:
            conn.close(); await conn.wait_closed()
