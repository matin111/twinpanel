from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport
from ..schemas import TunnelCreate, TunnelOut
from . import tunnels as core

router = APIRouter(prefix="/v1/tunnels", tags=["tunnels-managed"])

# Priority order is authoritative for failover/activation.
_TRANSPORTS = (
    ("mtunnel", 90, core.install_mtunnel_transport),
    ("backhaul", 100, core.install_backhaul_transport),
    ("ssh_tun", 200, core.install_ssh_transport),
)

# Installation order intentionally keeps Backhaul last. A slow Backhaul setup
# must not prevent MTunnel + SSH TUN from becoming available first.
_INSTALL_ORDER = ("mtunnel", "ssh_tun", "backhaul")
_TRANSPORT_TIMEOUTS = {
    "mtunnel": 150,
    "ssh_tun": 150,
    "backhaul": 75,
}


def _detail_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return str(detail)
    return str(exc)


def _transport_map():
    return {
        name: (priority, installer)
        for name, priority, installer in _TRANSPORTS
    }


def _mark_transport_failed(
    db: Session,
    tunnel_id: int,
    name: str,
    message: str,
) -> None:
    db.rollback()
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        return

    row.status = "failed"
    row.last_error = message[:1800]
    row.updated_at = datetime.utcnow()
    db.commit()


async def _install_with_retry(
    name: str,
    installer,
    tunnel_id: int,
    db: Session,
):
    last_error: Exception | None = None
    timeout_seconds = int(_TRANSPORT_TIMEOUTS.get(name, 120))

    for attempt in (1, 2):
        try:
            return await asyncio.wait_for(
                installer(tunnel_id, db),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            db.rollback()
            raise RuntimeError(
                f"{name} install timed out after {timeout_seconds}s"
            ) from exc
        except Exception as exc:  # installers already persist per-transport failure
            db.rollback()
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(2)

    assert last_error is not None
    raise last_error


def _transport_snapshot(db: Session, tunnel_id: int) -> list[dict]:
    rows = (
        db.query(TunnelTransport)
        .filter(TunnelTransport.tunnel_id == tunnel_id)
        .order_by(TunnelTransport.priority.asc(), TunnelTransport.id.asc())
        .all()
    )

    return [
        {
            "transport": row.transport,
            "priority": row.priority,
            "enabled": bool(row.enabled),
            "status": row.status,
            "latency_ms": row.latency_ms,
            "last_error": row.last_error,
        }
        for row in rows
    ]


def _activate_best_transport(db: Session, tunnel_id: int) -> str | None:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        return None

    rows = {
        str(row.transport).strip().lower(): row
        for row in db.query(TunnelTransport)
        .filter(TunnelTransport.tunnel_id == tunnel_id)
        .all()
    }

    selected: TunnelTransport | None = None

    for name, _, _ in _TRANSPORTS:
        row = rows.get(name)
        if (
            row
            and bool(row.enabled)
            and str(row.status or "").strip().lower() == "online"
        ):
            selected = row
            break

    if selected is None:
        tunnel.is_active = False
        tunnel.active_transport = None
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None
        db.commit()
        return None

    now = datetime.utcnow()
    selected_name = str(selected.transport)

    tunnel.mode = "manual"
    tunnel.is_active = True
    tunnel.active_transport = selected_name
    tunnel.preferred_transport = selected_name
    tunnel.status = TunnelStatus.ONLINE
    tunnel.latency_ms = selected.latency_ms
    tunnel.last_switch_at = now

    for peer in (
        db.query(TunnelPeerState)
        .filter(TunnelPeerState.tunnel_id == tunnel_id)
        .all()
    ):
        peer.selected_transport = selected_name
        peer.endpoint_reachable = True
        peer.tunnel_reachable = True
        peer.latency_ms = selected.latency_ms
        peer.last_error = None
        peer.updated_at = now

    db.commit()
    return selected_name


async def _remove_failed_new_tunnel(db: Session, tunnel_id: int) -> None:
    # First use the normal cleanup path so partially-created remote runtime is
    # removed whenever SSH is still reachable. Never let cleanup hang forever.
    try:
        await asyncio.wait_for(
            core.delete_tunnel(tunnel_id, db),
            timeout=45,
        )
    except BaseException:
        db.rollback()

    if db.get(Tunnel, tunnel_id) is None:
        return

    # Never leave a newly-created offline placeholder in the panel merely
    # because remote cleanup could not complete.
    db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id == tunnel_id
    ).delete(synchronize_session=False)
    db.query(TunnelTransport).filter(
        TunnelTransport.tunnel_id == tunnel_id
    ).delete(synchronize_session=False)

    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is not None:
        db.delete(tunnel)

    db.commit()


@router.post(
    "/create-managed",
    dependencies=[Depends(require_admin)],
)
async def create_managed_tunnel(
    payload: TunnelCreate,
    db: Session = Depends(get_db),
):
    """Create one Iran->Exit tunnel and install all three transports server-side.

    The browser performs one managed request. The API owns transport install,
    retries, timeouts, final activation and rollback. A failed new tunnel is
    never left as a permanent OFFLINE placeholder.
    """

    existing = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == payload.iran_node_id,
            Tunnel.exit_node_id == payload.exit_node_id,
        )
        .first()
    )
    was_existing = existing is not None

    tunnel = core.register_tunnel_pair(payload, db)
    tunnel_id = int(tunnel.id)

    installed: list[str] = []
    errors: dict[str, str] = {}
    results: dict[str, object] = {}
    transport_map = _transport_map()

    for name in _INSTALL_ORDER:
        item = transport_map.get(name)
        if item is None:
            errors[name] = "transport installer is not registered"
            continue

        _, installer = item

        try:
            result = await _install_with_retry(
                name,
                installer,
                tunnel_id,
                db,
            )
            results[name] = result

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tunnel_id,
                    TunnelTransport.transport == name,
                )
                .first()
            )

            if (
                row
                and bool(row.enabled)
                and str(row.status or "").strip().lower() == "online"
            ):
                installed.append(name)
                # Make a usable transport authoritative immediately. If a
                # secondary transport is slow/fails later, the tunnel stays up.
                _activate_best_transport(db, tunnel_id)
            else:
                message = "installer returned without an online transport"
                errors[name] = message
                _mark_transport_failed(db, tunnel_id, name, message)
        except Exception as exc:
            message = _detail_text(exc)[:1800]
            errors[name] = message
            _mark_transport_failed(db, tunnel_id, name, message)

    primary = _activate_best_transport(db, tunnel_id)

    if primary is None:
        if not was_existing:
            await _remove_failed_new_tunnel(db, tunnel_id)

        raise HTTPException(
            status_code=502,
            detail={
                "message": "هیچ‌کدام از مسیرهای تانل آنلاین نشدند؛ تانل آفلاین ذخیره نشد.",
                "errors": errors,
                "tunnel_id": tunnel_id,
                "rolled_back": not was_existing,
            },
        )

    db.expire_all()
    live = db.get(Tunnel, tunnel_id)
    assert live is not None

    return {
        "ok": True,
        "complete": len(installed) == len(_TRANSPORTS),
        "tunnel": TunnelOut.model_validate(live).model_dump(mode="json"),
        "active_transport": primary,
        "installed": installed,
        "errors": errors,
        "transports": _transport_snapshot(db, tunnel_id),
        "results": results,
    }
