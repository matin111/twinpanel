from __future__ import annotations

import asyncio
from datetime import datetime

from .database import SessionLocal
from .models import Node, NodeProtocolConfig, NodeType, Tunnel, TunnelTransport
from .routers import provision


# ============================================================
# TWINPANEL TP27 REFERENCE RUNTIME V91
#
# Production packet capture proved the old Cisco translation model was wrong:
# public TCP 20005 was forwarded to ocserv TCP 443, but ocserv advertised DTLS
# UDP 443 to the client. The client therefore sent no UDP/20005 and the session
# stayed CSTP/TCP-only (occtl: no-dtls).
#
# TP27 uses preserve-port forwarding. V91 applies the same invariant to the
# protocols that have a single externally visible transport port:
#   Cisco/OpenConnect : public 20xxx == ocserv TCP+UDP listen port
#   OpenVPN           : public 21xxx == OpenVPN listen port
#   WireGuard         : public 22xxx == WireGuard listen port
# L2TP already preserves 500/4500/ESP. Xray remains untouched because its
# current public-delivery path is production-working and does not advertise a
# translated UDP side-channel.
# ============================================================

MARKER = "TWINPANEL_TP27_REFERENCE_RUNTIME_V91"
RECONCILE_INTERVAL_SECONDS = 45
RETIRED_CANDIDATES = (
    "gost_tun",
    "amneziawg",
    "netrix",
    "kernel_gre",
)

_PORT_BASE = {
    "cisco": 20000,
    "openvpn": 21000,
    "wireguard": 22000,
}

_applied = False
_original_provision_protocols = provision.provision_protocols


def preserved_port(node_id: int, protocol: str) -> int:
    name = str(protocol or "").strip().lower()
    base = _PORT_BASE.get(name)
    if base is None:
        raise ValueError(f"unsupported_preserve_port_protocol:{name}")
    value = base + int(node_id)
    if value < 1 or value > 65535:
        raise ValueError(f"preserve_port_out_of_range:{name}:{value}")
    return value


def apply_protocol_settings(node: Node, settings) -> None:
    if node.node_type != NodeType.EXIT:
        return
    if bool(settings.install_cisco):
        settings.cisco_port = preserved_port(node.id, "cisco")
    if bool(settings.install_openvpn):
        settings.openvpn_port = preserved_port(node.id, "openvpn")
    if bool(settings.install_wireguard):
        settings.wireguard_port = preserved_port(node.id, "wireguard")


async def _provision_protocols_tp27(
    conn,
    settings,
    db,
    node,
    repair=False,
):
    apply_protocol_settings(node, settings)
    return await _original_provision_protocols(
        conn,
        settings,
        db,
        node,
        repair,
    )


def apply_tp27_reference_runtime_v91() -> None:
    global _applied
    if _applied:
        return

    provision.provision_protocols = _provision_protocols_tp27
    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "preserve_ports=cisco,openvpn,wireguard "
        "l2tp=already_preserved xray=unchanged",
        flush=True,
    )


def activate_manager_candidate_policy_v91() -> None:
    """Retire experimental candidates without breaking live migration GRE."""

    from . import smart_transport_auto_v21 as smart

    # Keep kernel_gre health-visible during make-before-break migration but
    # never auto-install it again. TP27 Fast is the only newly installed path.
    smart.AUTO_INSTALL_NAMES = ("tp27_fast",)

    print(
        f"{MARKER}_SMARTAUTO active_install=tp27_fast "
        "retired_install=kernel_gre,gost_tun,amneziawg,netrix",
        flush=True,
    )


def _config_map(db, node_id: int) -> dict[str, NodeProtocolConfig]:
    rows = (
        db.query(NodeProtocolConfig)
        .filter(NodeProtocolConfig.node_id == int(node_id))
        .all()
    )
    return {
        str(row.protocol or "").strip().lower(): row
        for row in rows
        if str(row.protocol or "").strip()
    }


def _needs_port_migration(node: Node, configs: dict[str, NodeProtocolConfig]) -> bool:
    checks = (
        ("cisco", "enable_cisco"),
        ("openvpn", "enable_openvpn"),
        ("wireguard", "enable_wireguard"),
    )
    for protocol, attr in checks:
        if not bool(getattr(node, attr, False)):
            continue
        row = configs.get(protocol)
        if row is None:
            continue
        if int(row.port or 0) != preserved_port(node.id, protocol):
            return True
    return False


def _repair_settings(node: Node, configs: dict[str, NodeProtocolConfig]):
    openvpn = configs.get("openvpn")
    transport = str(
        getattr(openvpn, "transport", None) or "udp"
    ).strip().lower()
    if transport not in {"udp", "tcp"}:
        transport = "udp"

    # Deliberately do not touch L2TP or Xray in this migration. L2TP already
    # preserves its well-known ports; Xray is the known-good production path.
    return provision.ProtocolSettings(
        install_cisco=bool(node.enable_cisco and configs.get("cisco")),
        cisco_port=preserved_port(node.id, "cisco"),
        install_openvpn=bool(node.enable_openvpn and configs.get("openvpn")),
        openvpn_port=preserved_port(node.id, "openvpn"),
        openvpn_transport=transport,
        install_wireguard=bool(node.enable_wireguard and configs.get("wireguard")),
        wireguard_port=preserved_port(node.id, "wireguard"),
        install_l2tp=False,
        install_v2ray=False,
    )


async def reconcile_preserved_ports_once() -> dict:
    db = SessionLocal()
    changed: list[int] = []
    failed: dict[int, str] = {}

    try:
        exit_ids = {
            int(value)
            for (value,) in (
                db.query(Tunnel.exit_node_id)
                .filter(Tunnel.is_active.is_(True))
                .distinct()
                .all()
            )
        }

        nodes = (
            db.query(Node)
            .filter(
                Node.id.in_(exit_ids) if exit_ids else False,
                Node.node_type == NodeType.EXIT,
                Node.retired_at.is_(None),
            )
            .all()
            if exit_ids
            else []
        )

        for node in nodes:
            configs = _config_map(db, node.id)
            if not _needs_port_migration(node, configs):
                continue

            conn = None
            try:
                settings = _repair_settings(node, configs)
                conn = await provision.ssh_connect_saved(node, db)
                results, repair_failed, _ = await provision.provision_protocols(
                    conn,
                    settings,
                    db,
                    node,
                    True,
                )
                if repair_failed:
                    raise RuntimeError(
                        "protocol_repair_failed:" + ",".join(repair_failed)
                    )

                # Fail closed on DB convergence too. The route reconciler reads
                # these exact ports to build Iran -> Exit preserve-port DNAT.
                db.expire_all()
                after = _config_map(db, node.id)
                for protocol, attr in (
                    ("cisco", "enable_cisco"),
                    ("openvpn", "enable_openvpn"),
                    ("wireguard", "enable_wireguard"),
                ):
                    if not bool(getattr(node, attr, False)) or protocol not in after:
                        continue
                    actual = int(after[protocol].port or 0)
                    expected = preserved_port(node.id, protocol)
                    if actual != expected:
                        raise RuntimeError(
                            f"preserve_port_verify_failed:{protocol}:{actual}!={expected}"
                        )

                changed.append(int(node.id))
                print(
                    f"{MARKER}_PORTS node={int(node.id)} "
                    f"cisco={preserved_port(node.id, 'cisco')} "
                    f"openvpn={preserved_port(node.id, 'openvpn')} "
                    f"wireguard={preserved_port(node.id, 'wireguard')} "
                    "result=converged",
                    flush=True,
                )
            except Exception as exc:
                db.rollback()
                failed[int(node.id)] = f"{type(exc).__name__}:{exc}"
                print(
                    f"{MARKER}_PORTS_ERROR node={int(node.id)} "
                    f"error={type(exc).__name__}:{exc}",
                    flush=True,
                )
            finally:
                if conn is not None:
                    conn.close()
                    await conn.wait_closed()

        return {
            "changed_nodes": changed,
            "failed": failed,
        }
    finally:
        db.close()


async def cleanup_retired_candidates_once() -> dict:
    # Import lazily: transport_candidates imports this module during package
    # initialization to install the provision wrapper.
    from .transport_candidates import uninstall_transport

    db = SessionLocal()
    cleaned: dict[int, list[str]] = {}
    failed: dict[int, dict[str, str]] = {}

    try:
        tunnels = (
            db.query(Tunnel)
            .filter(Tunnel.is_active.is_(True))
            .all()
        )

        for tunnel in tunnels:
            tid = int(tunnel.id)
            active = str(tunnel.active_transport or "").strip().lower()
            if active != "tp27_fast":
                continue

            tp27 = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tid,
                    TunnelTransport.transport == "tp27_fast",
                )
                .first()
            )
            if (
                tp27 is None
                or not bool(tp27.enabled)
                or str(getattr(tp27.status, "value", tp27.status) or "").lower()
                != "online"
            ):
                continue

            for name in RETIRED_CANDIDATES:
                row = (
                    db.query(TunnelTransport)
                    .filter(
                        TunnelTransport.tunnel_id == tid,
                        TunnelTransport.transport == name,
                    )
                    .first()
                )
                if row is None:
                    continue

                try:
                    await uninstall_transport(name, tid, db)
                    stale = (
                        db.query(TunnelTransport)
                        .filter(
                            TunnelTransport.tunnel_id == tid,
                            TunnelTransport.transport == name,
                        )
                        .first()
                    )
                    if stale is not None:
                        db.delete(stale)
                        db.commit()
                    cleaned.setdefault(tid, []).append(name)
                    print(
                        f"{MARKER}_RETIRED_CLEANUP tunnel={tid} "
                        f"transport={name} result=removed",
                        flush=True,
                    )
                except Exception as exc:
                    db.rollback()
                    failed.setdefault(tid, {})[name] = (
                        f"{type(exc).__name__}:{exc}"
                    )
                    print(
                        f"{MARKER}_RETIRED_CLEANUP_ERROR tunnel={tid} "
                        f"transport={name} error={type(exc).__name__}:{exc}",
                        flush=True,
                    )

        return {
            "cleaned": cleaned,
            "failed": failed,
            "at": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()


async def reconcile_once() -> dict:
    ports = await reconcile_preserved_ports_once()
    cleanup = await cleanup_retired_candidates_once()
    return {
        "ports": ports,
        "cleanup": cleanup,
    }


async def reconciler_loop() -> None:
    apply_tp27_reference_runtime_v91()
    activate_manager_candidate_policy_v91()

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"{MARKER}_ERROR {type(exc).__name__}:{exc}",
                flush=True,
            )
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
