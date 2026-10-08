from __future__ import annotations

import asyncio
import os
import shlex
from sqlalchemy.orm import Session

from ..config import settings
from .common import close_pair, connect_pair, copy_binary, diag, mark, prerequisites, probe, run, runtime, secret, tunnel_nodes


def _binary() -> str:
    path = str(getattr(settings, "netrix_binary_path", "") or "/opt/twinpanel/runtime/netrix/netrix").strip()
    if not os.path.isfile(path):
        raise RuntimeError("netrix_binary_missing: place your licensed Netrix binary at " + path)
    if not os.access(path, os.X_OK):
        raise RuntimeError("netrix_binary_not_executable: " + path)
    return path


async def install(tunnel_id: int, db: Session) -> dict:
    name = "netrix"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))
    ci = ce = None
    try:
        local = _binary()
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))
        await asyncio.gather(copy_binary(ci, local, "/usr/local/bin/twinpanel-netrix"), copy_binary(ce, local, "/usr/local/bin/twinpanel-netrix"))
        psk, port, iface = secret("netrix-psk", tunnel_id), int(rt["port"]), rt["interface"]
        iran_conf, exit_conf = f"/etc/twinpanel/netrix/tunnel-{tunnel_id}-iran.yaml", f"/etc/twinpanel/netrix/tunnel-{tunnel_id}-exit.yaml"

        await run(ci, f"""
set -e
install -d -m 700 /etc/twinpanel/netrix
cat > {shlex.quote(iran_conf)} <<'EOF'
mode: "server"
listen: "0.0.0.0:{port}"
transport: "tcpmux"
psk: "{psk}"
profile: "balanced"
tcp_ports: []
udp_ports: []
smux:
  keepalive: 20
  max_recv: 4194304
  max_stream: 2097152
  frame_size: 32768
  version: 2
  mux_con: 4
encryption:
  enabled: true
  key: ""
stealth:
  padding_enabled: true
  padding_min: 0
  padding_max: 32
  jitter_enabled: false
tun:
  enabled: true
  name: "{iface}"
  local: "{rt['iran_addr']}"
  mtu: 1280
  routes: []
heartbeat: 20
verbose: false
EOF
chmod 600 {shlex.quote(iran_conf)}
if command -v iptables >/dev/null 2>&1; then iptables -C INPUT -p tcp --dport {port} -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-Netrix-{tunnel_id} -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport {port} -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-Netrix-{tunnel_id} -j ACCEPT; fi
cat > /etc/systemd/system/{shlex.quote(rt['iran_service'])} <<'EOF'
[Unit]
Description=TwinPanel Netrix {tunnel_id} Iran Server
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-netrix -config {iran_conf}
Restart=always
RestartSec=2
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['iran_service'])} >/dev/null
systemctl restart {shlex.quote(rt['iran_service'])}
""", "netrix_iran_install", 90)

        await run(ce, f"""
set -e
install -d -m 700 /etc/twinpanel/netrix
cat > {shlex.quote(exit_conf)} <<'EOF'
mode: "client"
psk: "{psk}"
profile: "balanced"
paths:
  - transport: "tcpmux"
    addr: "{iran.public_ip}:{port}"
    connection_pool: 4
    aggressive_pool: false
    retry_interval: 3
    dial_timeout: 10
smux:
  keepalive: 20
  max_recv: 4194304
  max_stream: 2097152
  frame_size: 32768
  version: 2
  mux_con: 4
encryption:
  enabled: true
  key: ""
stealth:
  padding_enabled: true
  padding_min: 0
  padding_max: 32
  jitter_enabled: false
tun:
  enabled: true
  name: "{iface}"
  local: "{rt['exit_addr']}"
  mtu: 1280
  routes: []
heartbeat: 20
verbose: false
EOF
chmod 600 {shlex.quote(exit_conf)}
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
[Unit]
Description=TwinPanel Netrix {tunnel_id} Exit Client
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-netrix -config {exit_conf}
Restart=always
RestartSec=2
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(rt['exit_service'])}
""", "netrix_exit_install", 90)

        for _ in range(20):
            await asyncio.sleep(2)
            a, b = await asyncio.gather(
                ci.run(f"ip link show {shlex.quote(iface)} >/dev/null 2>&1", check=False),
                ce.run(f"ip link show {shlex.quote(iface)} >/dev/null 2>&1", check=False),
            )
            if a.exit_status == 0 and b.exit_status == 0:
                break
        health = await probe(ci, ce, name=name, tunnel_id=tunnel_id, rt=rt)
        mark(db, tunnel_id, name, status="online", latency_ms=health["latency_ms"], meta=str({**rt, **health, "licensed_binary": True}))
        return {"ok": True, "transport": name, "runtime": rt, "probe": health}
    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = f"{type(exc).__name__}: {exc} | iran={a[-1800:]} | exit={b[-1800:]}"
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await close_pair(ci, ce)
