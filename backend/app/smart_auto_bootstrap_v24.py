from __future__ import annotations

import asyncio
import json
from datetime import datetime

from sqlalchemy import text

from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import (
    Node,
    NodeAccess,
    NodeStatus,
    NodeType,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
    TunnelTransport,
)


# ============================================================
# TWINPANEL SMART AUTO BOOTSTRAP V24
#
# Purpose:
#   * first-install / empty-topology bootstrap for Smart Auto V21;
#   * never guesses when topology is ambiguous;
#   * never installs a legacy data plane itself;
#   * only creates one logical Iran -> Exit pair when exactly one ONLINE
#     Iran node and exactly one ONLINE Exit node exist and both have saved
#     SSH access;
#   * seeds a disabled TP2027 row so the existing V7/V21 manager enters the
#     Smart Auto path and installs real candidates itself.
#
# Candidate installation remains owned by Smart Auto V21:
#   kernel_gre -> gost_tun/WSS -> amneziawg -> optional licensed netrix.
# ============================================================

LOOP_SECONDS = 15
BOOTSTRAP_LOCK_ID = 240021
SEED_TRANSPORT = "tcp_2027"
SEED_PRIORITY = 900

_last_notice: str | None = None


def _notice(value: str) -> None:
    global _last_notice
    if value == _last_notice:
        return
    _last_notice = value
    print(f"[SmartBootstrapV24] {value}", flush=True)


def _eligible_nodes(db, node_type: NodeType) -> list[Node]:
    return (
        db.query(Node)
        .join(NodeAccess, NodeAccess.node_id == Node.id)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == node_type,
            Node.status == NodeStatus.ONLINE,
        )
        .order_by(Node.id.asc())
        .all()
    )


def _seed_config() -> str:
    return json.dumps(
        {
            "smart_auto_bootstrap_v24": {
                "seed": True,
                "created_at": datetime.utcnow().isoformat(),
                "purpose": "enter_smart_auto_without_legacy_install",
            }
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _ensure_seed_row(db, tunnel: Tunnel) -> bool:
    overlay_names = set(v7.OVERLAY_NAMES)

    existing_overlay = (
        db.query(TunnelTransport.id)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel.id),
            TunnelTransport.transport.in_(tuple(overlay_names)),
        )
        .first()
    )

    if existing_overlay is not None:
        return False

    existing_seed = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel.id),
            TunnelTransport.transport == SEED_TRANSPORT,
        )
        .first()
    )

    if existing_seed is not None:
        return False

    db.add(
        TunnelTransport(
            tunnel_id=int(tunnel.id),
            transport=SEED_TRANSPORT,
            priority=SEED_PRIORITY,
            enabled=False,
            status="not_installed",
            latency_ms=None,
            last_error=None,
            last_healthy_at=None,
            config_text=_seed_config(),
        )
    )

    return True


def _bootstrap_pair_if_empty(db) -> int | None:
    # Transaction-scoped PostgreSQL advisory lock prevents duplicate logical
    # pairs if systemd briefly overlaps manager processes during an update.
    locked = bool(
        db.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": BOOTSTRAP_LOCK_ID},
        ).scalar()
    )

    if not locked:
        _notice("SKIP lock_busy=1")
        return None

    if db.query(Tunnel.id).first() is not None:
        return None

    irans = _eligible_nodes(db, NodeType.IRAN)
    exits = _eligible_nodes(db, NodeType.EXIT)

    if len(irans) != 1 or len(exits) != 1:
        _notice(
            "WAIT "
            f"reason=ambiguous_topology iran_online_with_access={len(irans)} "
            f"exit_online_with_access={len(exits)}"
        )
        return None

    iran = irans[0]
    exit_node = exits[0]

    tunnel = Tunnel(
        iran_node_id=int(iran.id),
        exit_node_id=int(exit_node.id),
        transport="ssh_tun",
        status=TunnelStatus.OFFLINE,
        latency_ms=None,
        priority=100,
        is_active=True,
        wireguard_port=None,
        mode="auto",
        preferred_transport=None,
        active_transport=None,
        last_switch_at=None,
    )

    db.add(tunnel)
    db.flush()

    db.add_all(
        [
            TunnelPeerState(
                tunnel_id=int(tunnel.id),
                node_id=int(iran.id),
                selected_transport=None,
                endpoint_reachable=False,
                tunnel_reachable=False,
                latency_ms=None,
                last_error="smart_auto_bootstrap_v24",
                updated_at=datetime.utcnow(),
            ),
            TunnelPeerState(
                tunnel_id=int(tunnel.id),
                node_id=int(exit_node.id),
                selected_transport=None,
                endpoint_reachable=False,
                tunnel_reachable=False,
                latency_ms=None,
                last_error="smart_auto_bootstrap_v24",
                updated_at=datetime.utcnow(),
            ),
        ]
    )

    _ensure_seed_row(db, tunnel)
    db.commit()

    print(
        "[SmartBootstrapV24] CREATED "
        f"tunnel={int(tunnel.id)} "
        f"iran={int(iran.id)}:{iran.public_ip} "
        f"exit={int(exit_node.id)}:{exit_node.public_ip} "
        "mode=auto seed=tcp_2027",
        flush=True,
    )

    return int(tunnel.id)


def reconcile_once() -> dict:
    db = SessionLocal()

    try:
        created = _bootstrap_pair_if_empty(db)

        tunnels = (
            db.query(Tunnel)
            .filter(
                Tunnel.is_active.is_(True),
                Tunnel.mode == "auto",
            )
            .order_by(Tunnel.id.asc())
            .all()
        )

        seeded: list[int] = []

        for tunnel in tunnels:
            if _ensure_seed_row(db, tunnel):
                seeded.append(int(tunnel.id))

        if seeded:
            db.commit()
            print(
                "[SmartBootstrapV24] SEEDED "
                f"tunnels={seeded} seed={SEED_TRANSPORT}",
                flush=True,
            )

        return {
            "created_tunnel_id": created,
            "seeded_tunnel_ids": seeded,
            "managed_auto_tunnels": [int(item.id) for item in tunnels],
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_SMART_AUTO_BOOTSTRAP_V24_START "
        f"interval={LOOP_SECONDS}s policy=single-unambiguous-pair",
        flush=True,
    )

    while True:
        try:
            result = reconcile_once()
            if result["created_tunnel_id"] is not None:
                _notice(
                    "READY "
                    f"tunnel={result['created_tunnel_id']} "
                    "next=smart_auto_candidate_install"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "[SmartBootstrapV24] ERROR "
                f"error={repr(exc)[:1200]}",
                flush=True,
            )

        await asyncio.sleep(LOOP_SECONDS)
