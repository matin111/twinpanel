from __future__ import annotations

import shlex
from sqlalchemy.orm import Session

from . import amnezia, gost, gre, netrix
from .common import SPECS, catalog, close_pair, connect_pair, mark, policy_ids, runtime, tunnel_nodes

INSTALLERS = {
    "kernel_gre": gre.install,
    "gost_tun": gost.install,
    "amneziawg": amnezia.install,
    "netrix": netrix.install,
}


async def install_transport(name: str, tunnel_id: int, db: Session):
    installer = INSTALLERS.get(str(name).strip().lower())
    if installer is None:
        raise RuntimeError("unknown_transport")
    return await installer(int(tunnel_id), db)


async def uninstall_transport(name: str, tunnel_id: int, db: Session):
    name = str(name).strip().lower()
    if name not in SPECS:
        raise RuntimeError("unknown_transport")
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        table, priority = policy_ids(name, tunnel_id)
        for conn, service in ((ci, rt["iran_service"]), (ce, rt["exit_service"])):
            await conn.run(f"""
set +e
systemctl disable --now {shlex.quote(service)} >/dev/null 2>&1
rm -f /etc/systemd/system/{shlex.quote(service)}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1
systemctl daemon-reload >/dev/null 2>&1
true
""", check=False)
        await ci.run(f"ip rule del priority {priority} 2>/dev/null || true; ip route flush table {table} 2>/dev/null || true", check=False)
        mark(db, tunnel_id, name, status="not_installed", enabled=False, error=None, latency_ms=None)
        return {"ok": True, "transport": name, "removed": True}
    finally:
        await close_pair(ci, ce)


__all__ = ["SPECS", "catalog", "runtime", "install_transport", "uninstall_transport"]
