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

_TRANSPORTS = (
    ("mtunnel", 90, core.install_mtunnel_transport),
    ("backhaul", 100, core.install_backhaul_transport),
    ("ssh_tun", 200, core.install_ssh_transport),
)


def _detail_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return str(detail)
    return str(exc)


async def _install_with_retry(
    installer,
    tunnel_id: int,
    db: Session,
):
    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            return await installer(tunnel_id, db)
        except Exception as exc:  # installers already persist per-transport failure
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
    # removed whenever SSH is still reachable.
    try:
        await core.delete_tunnel(tunnel_id, db)
    except Exception:
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

    The old UI flow registered an OFFLINE logical row first and then performed
    three independent browser requests. Any interrupted/failed request left an
    OFFLINE tunnel behind. This endpoint owns the full orchestration so the
    browser receives a usable tunnel or a clear failure.
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

    for name, _, installer in _TRANSPORTS:
        try:
            result = await _install_with_retry(installer, tunnel_id, db)
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
            else:
                errors[name] = "installer returned without an online transport"
        except Exception as exc:
            errors[name] = _detail_text(exc)[:1800]

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
