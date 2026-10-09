from __future__ import annotations

import asyncio
import shlex
from sqlalchemy.orm import Session

from .common import close_pair, connect_pair, diag, mark, prerequisites, probe, run, runtime, tunnel_nodes


async def install(tunnel_id: int, db: Session) -> dict:
    name = "kernel_gre"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))
    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        async def peer(conn, *, role: str, local_public: str, remote_public: str, local_addr: str, service: str):
            helper = f"/usr/local/sbin/tp-gre-{int(tunnel_id)}-{role}"
            await run(conn, f"""
set -e
modprobe ip_gre >/dev/null 2>&1 || true
cat > {shlex.quote(helper)} <<'EOF'
#!/bin/bash
set -e
ACTION="${{1:-start}}"
IFACE={rt['interface']}
LOCAL={local_public}
REMOTE={remote_public}
ADDR={local_addr}
COMMENT=TwinPanel-GRE-{int(tunnel_id)}-{role}
if [ "$ACTION" = stop ]; then
 ip link del "$IFACE" >/dev/null 2>&1 || true
 if command -v iptables >/dev/null 2>&1; then iptables -D INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT >/dev/null 2>&1 || true; fi
 exit 0
fi
modprobe ip_gre >/dev/null 2>&1 || true
ip link del "$IFACE" >/dev/null 2>&1 || true
if command -v iptables >/dev/null 2>&1; then iptables -C INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT; fi
ip tunnel add "$IFACE" mode gre local "$LOCAL" remote "$REMOTE" ttl 255
ip addr add "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" mtu 1360 up
EOF
chmod 755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
[Unit]
Description=TwinPanel Kernel GRE {int(tunnel_id)} {role}
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={helper} start
ExecStop={helper} stop
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""", f"gre_{role}_install", 90)

        await asyncio.gather(
            peer(ci, role="iran", local_public=str(iran.public_ip), remote_public=str(exit_node.public_ip), local_addr=rt["iran_addr"], service=rt["iran_service"]),
            peer(ce, role="exit", local_public=str(exit_node.public_ip), remote_public=str(iran.public_ip), local_addr=rt["exit_addr"], service=rt["exit_service"]),
        )
        health = await probe(ci, ce, name=name, tunnel_id=tunnel_id, rt=rt)
        mark(db, tunnel_id, name, status="online", latency_ms=health["latency_ms"], meta=str({**rt, **health}))
        return {"ok": True, "transport": name, "runtime": rt, "probe": health}
    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = f"{type(exc).__name__}: {exc} | iran={a[-1800:]} | exit={b[-1800:]}"
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await close_pair(ci, ce)
