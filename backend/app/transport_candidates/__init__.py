from __future__ import annotations

import shlex

from sqlalchemy.orm import Session

from . import (
    amnezia,
    common as _common,
    gost,
    gre,
    netrix,
    tp27_fast,
    tp27_masque,
    tp27_tcp_direct,
)


# ============================================================
# TWINPANEL TP27 ACTIVE CANDIDATE REGISTRY V150
#
# Active independent lanes:
#   * tp27_fast       : keyed native GRE first; FoU only install fallback
#   * tp27_masque     : RFC 9484 CONNECT-IP over HTTP/3 / QUIC datagrams
#   * tp27_tcp_direct : independent direct-TCP L3 fallback
#
# Legacy experimental candidates remain understood only by scoped cleanup.
# kernel_gre stays health-visible during migration but is not auto-installed.
# ============================================================

_LEGACY_SPECS = dict(_common.SPECS)

TP27_SPEC = {
    "priority": 100,
    "label": "TP27 Fast",
    "family": "tp27-gre-l3",
}

TP27_MASQUE_SPEC = {
    "priority": 110,
    "label": "TP27 MASQUE H3",
    "family": "tp27-masque-connect-ip-h3",
}

TP27_TCP_DIRECT_SPEC = {
    "priority": 120,
    "label": "TP27 Direct TCP",
    "family": "tp27-direct-tcp-l3",
}

# common.mark/probe resolve this module global at call time. Append active TP27
# lanes to the internal registry used by shared helpers.
_common.SPECS["tp27_fast"] = TP27_SPEC
_common.SPECS["tp27_masque"] = TP27_MASQUE_SPEC
_common.SPECS["tp27_tcp_direct"] = TP27_TCP_DIRECT_SPEC

# SmartAuto/Unified-L3 compatibility registry. kernel_gre is retained only so
# a pre-migration live path remains health-checkable until TP27 is promoted.
SPECS = {
    "kernel_gre": _LEGACY_SPECS["kernel_gre"],
    "tp27_fast": TP27_SPEC,
    "tp27_masque": TP27_MASQUE_SPEC,
    "tp27_tcp_direct": TP27_TCP_DIRECT_SPEC,
}

ACTIVE_SPECS = {
    "tp27_fast": TP27_SPEC,
    "tp27_masque": TP27_MASQUE_SPEC,
    "tp27_tcp_direct": TP27_TCP_DIRECT_SPEC,
}

_legacy_runtime = _common.runtime
_legacy_policy_ids = _common.policy_ids


def _subnet(pool_second_octet: int, tunnel_id: int) -> tuple[str, str, str, int, int]:
    tid = max(int(tunnel_id), 1)
    slot = tid % 16384
    base = slot * 4
    third = (base // 256) & 0xFF
    fourth = base % 256
    network = f"10.{int(pool_second_octet)}.{third}.{fourth}/30"
    iran_ip = f"10.{int(pool_second_octet)}.{third}.{fourth + 1}"
    exit_ip = f"10.{int(pool_second_octet)}.{third}.{fourth + 2}"
    return network, iran_ip, exit_ip, third, fourth


def _tp27_runtime(tunnel_id: int) -> dict:
    """Preserve the production-proven V91 10.253/16 runtime contract."""

    tid = max(int(tunnel_id), 1)
    slot = tid % 16384
    base = slot * 4
    third = (base // 256) & 0xFF
    fourth = base % 256
    iran_ip = f"10.253.{third}.{fourth + 1}"
    exit_ip = f"10.253.{third}.{fourth + 2}"

    return {
        "transport": "tp27_fast",
        "interface": f"tp27{tid}"[:15],
        "network": f"10.253.{third}.{fourth}/30",
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr": f"{iran_ip}/30",
        "exit_addr": f"{exit_ip}/30",
        "port": None,
        "iran_service": f"twinpanel-tp27_fast-{tid}-iran.service",
        "exit_service": f"twinpanel-tp27_fast-{tid}-exit.service",
        "priority": int(TP27_SPEC["priority"]),
    }


def _tp27_tcp_direct_runtime(tunnel_id: int) -> dict:
    """Independent /30 in 10.254.0.0/16 for the direct-TCP fallback lane."""

    tid = max(int(tunnel_id), 1)
    network, iran_ip, exit_ip, _third, _fourth = _subnet(254, tid)

    return {
        "transport": "tp27_tcp_direct",
        "interface": f"tp27t{tid}"[:15],
        "network": network,
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr": f"{iran_ip}/30",
        "exit_addr": f"{exit_ip}/30",
        "port": 46200 + (tid % 500),
        "iran_service": f"twinpanel-tp27_tcp_direct-{tid}-iran.service",
        "exit_service": f"twinpanel-tp27_tcp_direct-{tid}-exit.service",
        "priority": int(TP27_TCP_DIRECT_SPEC["priority"]),
    }


def _tp27_masque_runtime(tunnel_id: int) -> dict:
    """Independent /30 in 10.255.0.0/16 for CONNECT-IP over HTTP/3."""

    tid = max(int(tunnel_id), 1)
    network, iran_ip, exit_ip, _third, _fourth = _subnet(255, tid)

    return {
        "transport": "tp27_masque",
        "interface": f"tp27m{tid}"[:15],
        "network": network,
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr": f"{iran_ip}/30",
        "exit_addr": f"{exit_ip}/30",
        "port": 28400 + (tid % 500),
        "iran_service": f"twinpanel-tp27_masque-{tid}-iran.service",
        "exit_service": f"twinpanel-tp27_masque-{tid}-exit.service",
        "priority": int(TP27_MASQUE_SPEC["priority"]),
    }


def runtime(name: str, tunnel_id: int) -> dict:
    value = str(name or "").strip().lower()
    if value == "tp27_fast":
        return _tp27_runtime(tunnel_id)
    if value == "tp27_masque":
        return _tp27_masque_runtime(tunnel_id)
    if value == "tp27_tcp_direct":
        return _tp27_tcp_direct_runtime(tunnel_id)
    return _legacy_runtime(value, tunnel_id)


def policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
    value = str(name or "").strip().lower()
    if value == "tp27_fast":
        # Keep migration make-before-break: legacy kernel_gre uses 220xx.
        table = 29000 + (int(tunnel_id) % 900)
        return table, table
    if value == "tp27_tcp_direct":
        table = 30000 + (int(tunnel_id) % 900)
        return table, table
    if value == "tp27_masque":
        table = 31000 + (int(tunnel_id) % 900)
        return table, table
    return _legacy_policy_ids(value, tunnel_id)


_common.runtime = runtime
_common.policy_ids = policy_ids
# Candidate modules imported common.runtime by name during package import;
# point their module-level bindings at the V150 dispatcher too.
tp27_fast.runtime = runtime
tp27_masque.runtime = runtime
tp27_tcp_direct.runtime = runtime

close_pair = _common.close_pair
connect_pair = _common.connect_pair
default_interface = _common.default_interface
mark = _common.mark


def catalog() -> list[dict]:
    return [
        {"transport": name, **spec}
        for name, spec in ACTIVE_SPECS.items()
    ]


INSTALLERS = {
    "tp27_fast": tp27_fast.install,
    "tp27_masque": tp27_masque.install,
    "tp27_tcp_direct": tp27_tcp_direct.install,
}


async def install_transport(name: str, tunnel_id: int, db: Session):
    value = str(name or "").strip().lower()
    installer = INSTALLERS.get(value)
    if installer is None:
        raise RuntimeError("unknown_or_retired_transport")
    return await installer(int(tunnel_id), db)


async def uninstall_transport(name: str, tunnel_id: int, db: Session):
    """Remove only TwinPanel-owned runtime for one active/retired candidate."""

    name = str(name or "").strip().lower()
    if name not in _common.SPECS:
        raise RuntimeError("unknown_transport")

    _, iran, exit_node = _common.tunnel_nodes(db, tunnel_id)
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

        if name == "tp27_fast":
            await ci.run(
                f"rm -f /usr/local/sbin/tp27-fast-{int(tunnel_id)}-iran; true",
                check=False,
            )
            await ce.run(
                f"rm -f /usr/local/sbin/tp27-fast-{int(tunnel_id)}-exit; true",
                check=False,
            )

        elif name == "tp27_masque":
            token_path, cert_path, key_path = tp27_masque._secret_paths(int(tunnel_id))
            await ci.run(
                f"rm -f {shlex.quote(token_path)}; true",
                check=False,
            )
            await ce.run(
                f"rm -f {shlex.quote(token_path)} {shlex.quote(cert_path)} {shlex.quote(key_path)}; true",
                check=False,
            )

        elif name == "kernel_gre":
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

        await ci.run(
            f"""
set +e
ip rule del priority {priority} 2>/dev/null || true
ip route flush table {table} 2>/dev/null || true
true
""",
            check=False,
        )

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

        if name == "tp27_fast":
            for conn, role, remote in (
                (ci, "iran", str(exit_node.public_ip)),
                (ce, "exit", str(iran.public_ip)),
            ):
                comment = f"TwinPanel-TP27-{int(tunnel_id)}-{role}"
                await conn.run(
                    f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 while iptables -C INPUT -p 47 -s {shlex.quote(remote)} -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p 47 -s {shlex.quote(remote)} -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
 done
 for p in 443 8443 2053 2083 10443; do
  while iptables -C INPUT -p udp --dport "$p" -s {shlex.quote(remote)} -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
   iptables -D INPUT -p udp --dport "$p" -s {shlex.quote(remote)} -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
  done
 done
fi
true
""",
                    check=False,
                )

        elif name == "tp27_tcp_direct":
            comment = f"TwinPanel-TP27-TCP-{int(tunnel_id)}"
            ports = " ".join(
                str(value)
                for value in tp27_tcp_direct._port_candidates(int(tunnel_id))
            )
            await ce.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 for p in {ports}; do
  while iptables -C INPUT -p tcp --dport "$p" -s {shlex.quote(str(iran.public_ip))} -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
   iptables -D INPUT -p tcp --dport "$p" -s {shlex.quote(str(iran.public_ip))} -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
  done
 done
fi
true
""",
                check=False,
            )

        elif name == "tp27_masque":
            comment = f"TwinPanel-TP27-MASQUE-{int(tunnel_id)}"
            ports = " ".join(
                str(value)
                for value in tp27_masque._port_candidates(int(tunnel_id))
            )
            await ce.run(
                f"""
set +e
if command -v iptables >/dev/null 2>&1; then
 for p in {ports}; do
  while iptables -C INPUT -p udp --dport "$p" -s {shlex.quote(str(iran.public_ip))} -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
   iptables -D INPUT -p udp --dport "$p" -s {shlex.quote(str(iran.public_ip))} -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
  done
 done
fi
true
""",
                check=False,
            )

        elif name == "kernel_gre":
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


# Apply preserve-port behavior in both API and standalone manager processes as
# soon as the transport candidate package is loaded. The reconciler itself is
# started explicitly by tunnel_transport_manager_v12.
from ..tp27_reference_runtime_v91 import apply_tp27_reference_runtime_v91

apply_tp27_reference_runtime_v91()


__all__ = [
    "SPECS",
    "ACTIVE_SPECS",
    "catalog",
    "runtime",
    "policy_ids",
    "install_transport",
    "uninstall_transport",
]
