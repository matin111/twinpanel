from __future__ import annotations

import shlex
from sqlalchemy.orm import Session

from . import amnezia, gost, gre, netrix
from .common import (
    SPECS,
    catalog,
    close_pair,
    connect_pair,
    default_interface,
    mark,
    policy_ids,
    runtime,
    tunnel_nodes,
)

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
    """Remove only runtime owned by one canary transport.

    Cleanup stays tunnel-id scoped: services/interfaces, candidate-only policy
    routing, exact ownership-tagged firewall/NAT rules, and per-tunnel config
    files. Shared binaries/toolchains are intentionally preserved because other
    logical tunnels on the same Iran/Exit node may still use them.
    """
    name = str(name).strip().lower()
    if name not in SPECS:
        raise RuntimeError("unknown_transport")

    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    ci = ce = None

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        table, priority = policy_ids(name, tunnel_id)

        for conn, service in (
            (ci, rt["iran_service"]),
            (ce, rt["exit_service"]),
        ):
            await conn.run(
                f"""
set +e
systemctl disable --now {shlex.quote(service)} >/dev/null 2>&1
rm -f /etc/systemd/system/{shlex.quote(service)}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1
systemctl daemon-reload >/dev/null 2>&1
true
""",
                check=False,
            )

        # Remove tunnel-specific files only. Never remove a shared candidate
        # binary or source tree because another tunnel may still depend on it.
        if name == "kernel_gre":
            await ci.run(
                f"rm -f /usr/local/sbin/tp-gre-{int(tunnel_id)}-iran; true",
                check=False,
            )
            await ce.run(
                f"rm -f /usr/local/sbin/tp-gre-{int(tunnel_id)}-exit; true",
                check=False,
            )

        elif name == "amneziawg":
            await ci.run(
                f"""
rm -f \
  /etc/twinpanel/amneziawg/tunnel-{int(tunnel_id)}.key \
  /etc/twinpanel/amneziawg/tunnel-{int(tunnel_id)}-iran.conf
true
""",
                check=False,
            )
            await ce.run(
                f"""
rm -f \
  /etc/twinpanel/amneziawg/tunnel-{int(tunnel_id)}.key \
  /etc/twinpanel/amneziawg/tunnel-{int(tunnel_id)}-exit.conf
true
""",
                check=False,
            )

        elif name == "netrix":
            await ci.run(
                f"rm -f /etc/twinpanel/netrix/tunnel-{int(tunnel_id)}-iran.yaml; true",
                check=False,
            )
            await ce.run(
                f"rm -f /etc/twinpanel/netrix/tunnel-{int(tunnel_id)}-exit.yaml; true",
                check=False,
            )

        # Remove the isolated source-policy rule used only by canary probes.
        await ci.run(
            f"""
set +e
ip rule del priority {priority} 2>/dev/null || true
ip route flush table {table} 2>/dev/null || true
true
""",
            check=False,
        )

        # Remove the exact egress NAT rule installed for the candidate /30.
        exit_if = await default_interface(ce)
        nat_comment = f"TwinPanel-{name}-{int(tunnel_id)}"
        await ce.run(
            f"""
set +e
if command -v iptables >/dev/null 2>&1; then
  while iptables -t nat -C POSTROUTING \
    -s {shlex.quote(rt['network'])} \
    -o {shlex.quote(exit_if)} \
    -m comment --comment {shlex.quote(nat_comment)} \
    -j MASQUERADE 2>/dev/null; do
    iptables -t nat -D POSTROUTING \
      -s {shlex.quote(rt['network'])} \
      -o {shlex.quote(exit_if)} \
      -m comment --comment {shlex.quote(nat_comment)} \
      -j MASQUERADE || break
  done
fi
true
""",
            check=False,
        )

        # Remove the exact listener rule created by each transport. GRE's
        # protocol-47 rule is normally removed by ExecStop, but remove it here
        # as a second idempotent cleanup pass too.
        if name == "kernel_gre":
            await ci.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p 47 -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-GRE-{int(tunnel_id)}-iran -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p 47 -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-GRE-{int(tunnel_id)}-iran -j ACCEPT || break
 done
fi
true
""",
                check=False,
            )
            await ce.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p 47 -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GRE-{int(tunnel_id)}-exit -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p 47 -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GRE-{int(tunnel_id)}-exit -j ACCEPT || break
 done
fi
true
""",
                check=False,
            )

        elif name == "gost_tun":
            await ce.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p tcp --dport {int(rt['port'])} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p tcp --dport {int(rt['port'])} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT || break
 done
fi
true
""",
                check=False,
            )

        elif name == "amneziawg":
            await ce.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p udp --dport {int(rt['port'])} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-AWG-{int(tunnel_id)} -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p udp --dport {int(rt['port'])} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-AWG-{int(tunnel_id)} -j ACCEPT || break
 done
fi
true
""",
                check=False,
            )

        elif name == "netrix":
            await ci.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p tcp --dport {int(rt['port'])} -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-Netrix-{int(tunnel_id)} -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p tcp --dport {int(rt['port'])} -s {shlex.quote(str(exit_node.public_ip))} -m comment --comment TwinPanel-Netrix-{int(tunnel_id)} -j ACCEPT || break
 done
fi
true
""",
                check=False,
            )

        mark(
            db,
            tunnel_id,
            name,
            status="not_installed",
            enabled=False,
            error=None,
            latency_ms=None,
        )

        return {
            "ok": True,
            "transport": name,
            "removed": True,
        }

    finally:
        await close_pair(ci, ce)


__all__ = [
    "SPECS",
    "catalog",
    "runtime",
    "install_transport",
    "uninstall_transport",
]
