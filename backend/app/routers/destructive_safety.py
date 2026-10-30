from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..lifecycle_cleanup import related_tunnel_ids_for_node
from ..models import (
    CleanupJob,
    Node,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
    TunnelTransport,
)
from ..quota_models import (
    QuotaCursor,
    QuotaDevice,
    QuotaSession,
    QuotaUsageEvent,
)
from ..subscription_enforcement import queue_subscription_enforcement
from .provision import ssh_connect_saved
from . import nodes as nodes_module
from . import subscriptions as subscriptions_module
from . import tunnels as tunnels_module


# TWINPANEL_DESTRUCTIVE_PREFLIGHT_V1
#
# Destructive node/tunnel actions used to mutate desired-state first and only
# afterwards discover that a remote node was unreachable. In that failure mode
# the request could spend long enough retrying SSH to hit nginx's 504 timeout,
# while the tunnel was already left inactive/offline.
#
# Normal deletion therefore keeps a strict bounded SSH preflight before any
# mutation. Explicit force-delete/force-retire paths are separate admin actions
# for broken or permanently unreachable infrastructure and deliberately skip
# remote runtime cleanup while removing control-plane desired state.

SSH_PREFLIGHT_SECONDS = 14.0


@dataclass(frozen=True)
class TunnelSnapshot:
    tunnel_id: int
    is_active: bool
    status: object
    latency_ms: float | None


def _error_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _node_label(node: Node) -> str:
    name = str(getattr(node, "name", "") or f"node-{node.id}").strip()
    ip = str(getattr(node, "public_ip", "") or "-").strip()
    return f"{name} (ID {node.id}, {ip})"


async def _probe_saved_ssh(node: Node, db: Session) -> tuple[int, str | None]:
    conn = None
    try:
        conn = await asyncio.wait_for(
            ssh_connect_saved(node, db),
            timeout=SSH_PREFLIGHT_SECONDS,
        )
        return int(node.id), None
    except asyncio.TimeoutError:
        return int(node.id), f"مهلت اتصال SSH تمام شد ({SSH_PREFLIGHT_SECONDS:g}s)"
    except Exception as exc:
        return int(node.id), _error_text(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
                await asyncio.wait_for(conn.wait_closed(), timeout=2.0)
            except Exception:
                pass


async def _require_reachable_nodes(nodes: Iterable[Node], db: Session) -> None:
    unique: dict[int, Node] = {}
    for node in nodes:
        if node is not None:
            unique[int(node.id)] = node

    if not unique:
        return

    results = await asyncio.gather(
        *(_probe_saved_ssh(node, db) for node in unique.values())
    )

    failures: list[str] = []
    for node_id, error in results:
        if not error:
            continue
        node = unique[node_id]
        failures.append(f"{_node_label(node)}: {error}")

    if failures:
        raise HTTPException(
            status_code=424,
            detail=(
                "حذف شروع نشد چون دسترسی SSH یکی از نودهای لازم برقرار نیست. "
                "هیچ تغییری روی وضعیت نود یا تانل اعمال نشد. "
                + " | ".join(failures)[:1800]
            ),
        )


def _relay_nodes_for_tunnel(tunnel_id: int, db: Session) -> list[Node]:
    rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_relay",
        )
        .all()
    )

    out: list[Node] = []
    for row in rows:
        if not row.config_text:
            continue
        try:
            payload = json.loads(row.config_text)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        try:
            relay_id = int(payload.get("relay_node_id") or 0)
        except (TypeError, ValueError):
            relay_id = 0
        if relay_id <= 0:
            continue
        node = db.get(Node, relay_id)
        if node is not None:
            out.append(node)
    return out


def _nodes_needed_for_tunnel(tunnel: Tunnel, db: Session) -> list[Node]:
    out: list[Node] = []
    for node_id in (int(tunnel.iran_node_id), int(tunnel.exit_node_id)):
        node = db.get(Node, node_id)
        if node is not None:
            out.append(node)
    out.extend(_relay_nodes_for_tunnel(int(tunnel.id), db))
    return out


def _nodes_needed_for_node_delete(node_id: int, db: Session) -> list[Node]:
    out: dict[int, Node] = {}

    target = db.get(Node, int(node_id))
    if target is not None:
        out[int(target.id)] = target

    for tunnel_id in related_tunnel_ids_for_node(db, int(node_id)):
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            continue
        for node in _nodes_needed_for_tunnel(tunnel, db):
            out[int(node.id)] = node

    return list(out.values())


def _snapshot_tunnels(tunnel_ids: Iterable[int], db: Session) -> list[TunnelSnapshot]:
    snapshots: list[TunnelSnapshot] = []
    for tunnel_id in sorted({int(value) for value in tunnel_ids}):
        tunnel = db.get(Tunnel, tunnel_id)
        if tunnel is None:
            continue
        snapshots.append(
            TunnelSnapshot(
                tunnel_id=tunnel_id,
                is_active=bool(tunnel.is_active),
                status=tunnel.status,
                latency_ms=tunnel.latency_ms,
            )
        )
    return snapshots


def _restore_tunnels(snapshots: Iterable[TunnelSnapshot], db: Session) -> None:
    restored = False
    try:
        db.rollback()
    except Exception:
        pass

    for snapshot in snapshots:
        tunnel = db.get(Tunnel, int(snapshot.tunnel_id))
        if tunnel is None:
            continue
        tunnel.is_active = snapshot.is_active
        tunnel.status = snapshot.status
        tunnel.latency_ms = snapshot.latency_ms
        restored = True

    if restored:
        db.commit()


def _clear_tunnel_runtime_cache(tunnel_id: int) -> None:
    for name in (
        "_tunnel_watchdog_failures",
        "_tunnel_watchdog_last_repair",
    ):
        value = getattr(tunnels_module, name, None)
        if isinstance(value, dict):
            value.pop(int(tunnel_id), None)


def _force_delete_tunnel_control_plane(tunnel_id: int, db: Session) -> dict:
    """Remove a tunnel from desired state without contacting remote nodes.

    This is intentionally separate from normal DELETE. It is only used after
    explicit admin confirmation when one of the tunnel nodes is broken or
    unreachable. Remote interfaces/services may remain on an unreachable host,
    but the controller stops managing/rebuilding the deleted tunnel.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    iran_node_id = int(tunnel.iran_node_id)
    exit_node_id = int(tunnel.exit_node_id)

    cleanup_job = CleanupJob(
        target_type="tunnel",
        target_id=int(tunnel_id),
        action="force_remove_without_remote_cleanup",
        status="running",
    )
    db.add(cleanup_job)
    db.flush()

    try:
        tunnel.is_active = False
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None
        db.flush()

        db.query(TunnelPeerState).filter(
            TunnelPeerState.tunnel_id == int(tunnel_id)
        ).delete(synchronize_session=False)

        db.query(TunnelTransport).filter(
            TunnelTransport.tunnel_id == int(tunnel_id)
        ).delete(synchronize_session=False)

        db.delete(tunnel)

        cleanup_job.status = "completed"
        cleanup_job.error = (
            "Remote runtime cleanup was skipped by explicit admin force-delete"
        )
        cleanup_job.finished_at = datetime.utcnow()

        db.commit()

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "حذف اجباری تانل از کنترل‌پلین کامل نشد. "
                f"جزئیات: {str(exc)[:1200]}"
            ),
        ) from exc

    _clear_tunnel_runtime_cache(int(tunnel_id))

    return {
        "ok": True,
        "deleted_tunnel_id": int(tunnel_id),
        "iran_node_id": iran_node_id,
        "exit_node_id": exit_node_id,
        "remote_cleanup_skipped": True,
        "message": (
            "تانل از پنل حذف شد؛ پاک‌سازی Runtime روی نود غیرقابل‌دسترسی رد شد"
        ),
    }


# TWINPANEL_SUBSCRIPTION_HARD_DELETE_V1
# Normal subscription DELETE is intentionally a true destructive action. Revoke
# commands are captured before any credential/session state is removed. Quota
# history has RESTRICT foreign keys, so child rows are removed in dependency
# order before deleting the Subscription itself. Already-canceled legacy rows
# are also hard-deleted; they were revoked by the previous soft-delete flow.
def _hard_delete_subscription(subscription_id: int, db: Session) -> dict:
    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    deleted_id = int(sub.id)
    was_canceled = sub.status == SubscriptionStatus.CANCELED
    enforcement = {
        "operation_id": None,
        "commands": [],
        "commands_created": 0,
        "devices_updated": 0,
    }

    try:
        if not was_canceled:
            enforcement = queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="subscription_hard_deleted",
            )
            db.flush()

        # quota_usage_events references both Subscription and QuotaDevice using
        # RESTRICT, so it must be removed before sessions/devices. Explicitly
        # clearing every dependent row also makes behavior deterministic on
        # SQLite smoke tests where FK cascade settings can differ.
        deleted_usage_events = (
            db.query(QuotaUsageEvent)
            .filter(QuotaUsageEvent.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_sessions = (
            db.query(QuotaSession)
            .filter(QuotaSession.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_cursors = (
            db.query(QuotaCursor)
            .filter(QuotaCursor.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_devices = (
            db.query(QuotaDevice)
            .filter(QuotaDevice.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_credentials = (
            db.query(ProtocolCredential)
            .filter(ProtocolCredential.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_protocols = (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_nodes = (
            db.query(SubscriptionNode)
            .filter(SubscriptionNode.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )

        db.delete(sub)
        db.flush()

        if db.get(Subscription, deleted_id) is not None:
            raise RuntimeError("subscription row still exists after hard delete")

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "حذف کامل اشتراک انجام نشد: "
                + str(exc)[:500]
            ),
        ) from exc

    return {
        "ok": True,
        "subscription_id": deleted_id,
        "deleted": True,
        "status": "deleted",
        "previously_canceled": bool(was_canceled),
        "enforcement": (
            "already_revoked"
            if was_canceled
            else (
                "queued"
                if int(enforcement.get("commands_created") or 0) > 0
                else "no_credentials"
            )
        ),
        **enforcement,
        "deleted_rows": {
            "quota_usage_events": int(deleted_usage_events),
            "quota_sessions": int(deleted_sessions),
            "quota_cursors": int(deleted_cursors),
            "quota_devices": int(deleted_devices),
            "protocol_credentials": int(deleted_credentials),
            "subscription_protocols": int(deleted_protocols),
            "subscription_nodes": int(deleted_nodes),
            "subscriptions": 1,
        },
        "message": "اشتراک به‌طور کامل حذف شد",
    }


safe_subscriptions_router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscriptions"],
)


@safe_subscriptions_router.delete(
    "/{subscription_id}",
    dependencies=[Depends(require_admin)],
)
def hard_delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    return _hard_delete_subscription(int(subscription_id), db)


safe_nodes_router = APIRouter(
    prefix="/v1/nodes",
    tags=["nodes"],
)


@safe_nodes_router.delete(
    "/{node_id}",
    dependencies=[Depends(require_admin)],
)
async def safe_delete_node(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = (
        db.query(Node)
        .filter(
            Node.id == int(node_id),
            Node.retired_at.is_(None),
        )
        .first()
    )

    if node is None:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    if bool(getattr(node, "is_mother", False)):
        raise HTTPException(status_code=409, detail="سرور مادر قابل حذف نیست")

    tunnel_ids = related_tunnel_ids_for_node(db, int(node_id))
    snapshots = _snapshot_tunnels(tunnel_ids, db)

    await _require_reachable_nodes(
        _nodes_needed_for_node_delete(int(node_id), db),
        db,
    )

    try:
        return await nodes_module.delete_node(int(node_id), db)
    except Exception:
        _restore_tunnels(snapshots, db)
        raise


safe_tunnels_router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnels"],
)


@safe_tunnels_router.post(
    "/{tunnel_id}/force-delete",
    dependencies=[Depends(require_admin)],
)
def force_delete_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    return _force_delete_tunnel_control_plane(int(tunnel_id), db)


@safe_tunnels_router.delete(
    "/{tunnel_id}",
    dependencies=[Depends(require_admin)],
)
async def safe_delete_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    snapshots = _snapshot_tunnels([int(tunnel_id)], db)

    await _require_reachable_nodes(
        _nodes_needed_for_tunnel(tunnel, db),
        db,
    )

    try:
        return await tunnels_module.delete_tunnel(int(tunnel_id), db)
    except Exception:
        _restore_tunnels(snapshots, db)
        raise


# Route precedence is intentional. app.main later includes the legacy routers;
# FastAPI resolves the first matching method+path. Prepending these guarded
# routes leaves every other legacy route untouched.
subscriptions_module.router.routes[:0] = list(safe_subscriptions_router.routes)
nodes_module.router.routes[:0] = list(safe_nodes_router.routes)
tunnels_module.router.routes[:0] = list(safe_tunnels_router.routes)
