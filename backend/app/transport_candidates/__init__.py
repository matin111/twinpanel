from __future__ import annotations

import shlex

from sqlalchemy.orm import Session

from . import amnezia, common as _common, gost, gre, netrix, tp27_fast


# ============================================================
# TWINPANEL TP27 ACTIVE CANDIDATE REGISTRY V91
#
# The previous experimental candidates remain understood only by the scoped
# cleanup path so existing installations can remove their owned runtime. They
# are no longer exposed, auto-installed, benchmarked, or selectable.
# ============================================================

_LEGACY_SPECS = dict(_common.SPECS)
TP27_SPEC = {
    "priority": 100,
    "label": "TP27 Fast",
    "family": "tp27-gre-l3",
}

# common.mark/probe resolve this module global at call time. Append TP27 to the
# internal registry for those shared helpers, while exporting only TP27 as the
# active product registry below.
_common.SPECS["tp27_fast"] = TP27_SPEC

SPECS = {
    "tp27_fast": TP27_SPEC,
}

_legacy_runtime = _common.runtime
_legacy_policy_ids = _common.policy_ids


def _tp27_runtime(tunnel_id: int) -> dict:
    """Deterministic /30 inside the TP27 10.253.0.0/16 carrier pool."""

    tid = max(int(tunnel_id), 1)
    # /16 contains 16384 /30 networks. Tunnel IDs are persistent DB identities;
    # using the ID keeps addressing deterministic across controller restarts.
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


def runtime(name: str, tunnel_id: int) -> dict:
    value = str(name or "").strip().lower()
    if value == "tp27_fast":
        return _tp27_runtime(tunnel_id)
    return _legacy_runtime(value, tunnel_id)


def policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
    value = str(name or "").strip().lower()
    if value == "tp27_fast":
        # Keep migration make-before-break: legacy kernel_gre uses 220xx.
        table = 29000 + (int(tunnel_id) % 900)
        return table, table
    return _legacy_policy_ids(value, tunnel_id)


# Shared helpers such as common.probe() and common.mark() resolve these globals
# dynamically, so patching them once gives TP27 the same fail-closed probe while
# preserving legacy cleanup semantics.
_common.runtime = runtime
_common.policy_ids = policy_ids
# tp27_fast imported common.runtime by name during package import; point that
# module-level binding at the V91 dispatcher too.
tp27_fast.runtime = runtime

close_pair = _common.close_pair
connect_pair = _common.connect_pair
default_interface = _common.default_interface
mark = _common.mark


def catalog() -> list[dict]:
    return [
        {"transport": name, **spec}
        for name, spec in SPECS.items()
    ]


INSTALLERS = {
    "tp27_fast": tp27_fast.install,
}


async def install_transport(name: str, tunnel_id: int, db: Session):
    value = str(name or "").strip().lower()
    installer = INSTALLERS.get(value)
    if installer is None:
        raise RuntimeError("unknown_or_retired_transport")
    return await installer(int(tunnel_id), db)


async def uninstall_transport(name: str, tunnel_id: int, db: Session):
    """Remove only TwinPanel-owned runtime for one active/retired candidate.

    Legacy names stay accepted here solely so V91 can remove old GOST/AWG/
    Netrix/Kernel-GRE runtime after TP27 is proven active. They are not part of
    SPECS/catalog and cannot be installed or selected again.
    """

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

        # Remove candidate-only source-policy state.
        await ci.run(
            f"""
set +e
ip rule del priority {priority} 2>/dev/null || true
ip route flush table {table} 2>/dev/null || true
true
""",
            check=False,
        )

        # Remove the exact candidate /30 egress NAT ownership rule.
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


__all__ = [
    "SPECS",
    "catalog",
    "runtime",
    "policy_ids",
    "install_transport",
    "uninstall_transport",
]
