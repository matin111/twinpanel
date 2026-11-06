"""Admin-only staged and explicitly confirmed client endpoint settings.

Manual confirmation is an operator assertion, NOT an automatic TCP/TLS probe.
No SSH, restart, subscription provision or credential mutation happens here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, Tunnel
from ..node_connection_settings_models_v1 import NodeProtocolAppliedEndpoint
from ..services.central_connection_projection_v1 import (
    SINGBOX_OUTBOUNDS, ConnectionProjectionError, _valid_host, _valid_port,
)
from ..services.central_modern_connection_lookup_v1 import central_modern_delivery_enabled

router = APIRouter(
    prefix="/v1/admin/node-connection-settings",
    tags=["admin-node-connection-settings-v1"],
    dependencies=[Depends(require_admin)],
)


def _scope(db: Session, node_id: int, protocol: str):
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_OUTBOUNDS:
        raise HTTPException(404, "پروتکل در این مرحله پشتیبانی نمی‌شود")
    node = db.query(Node).filter(Node.id == node_id, Node.retired_at.is_(None)).first()
    if node is None:
        raise HTTPException(404, "نود یافت نشد")
    cfg = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == node_id,
        NodeProtocolConfig.protocol == protocol,
    ).first()
    if cfg is None:
        raise HTTPException(404, "پروتکل روی نود تنظیم نشده است")
    return protocol, node, cfg


def _existing(db: Session, node_id: int, protocol: str):
    return db.get(NodeProtocolAppliedEndpoint, (node_id, protocol))


def _state(row: NodeProtocolAppliedEndpoint | None) -> dict[str, Any]:
    return {
        "configured": row is not None,
        "node_id": row.node_id if row else None,
        "protocol": row.protocol if row else None,
        "host": row.host if row else None,
        "port": row.port if row else None,
        "sni": row.sni if row else None,
        "is_applied": bool(row.is_applied) if row else False,
        "applied_confirmed_at": (
            row.applied_confirmed_at.isoformat() if row and row.applied_confirmed_at else None
        ),
        "delivery_feature_enabled": central_modern_delivery_enabled(),
    }


@router.get("/{node_id}/{protocol}")
def get_endpoint(node_id: int, protocol: str, db: Session = Depends(get_db)):
    protocol, _, _ = _scope(db, node_id, protocol)
    return _state(_existing(db, node_id, protocol))


@router.put("/{node_id}/{protocol}")
def stage_endpoint(
    node_id: int,
    protocol: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    protocol, node, cfg = _scope(db, node_id, protocol)
    if not isinstance(payload, dict) or not payload or set(payload) - {"host", "port", "sni"}:
        raise HTTPException(422, "فقط host، port و sni مجازند")
    row = _existing(db, node_id, protocol)
    try:
        host = _valid_host(
            payload["host"] if "host" in payload else (
                row.host if row and row.host else
                getattr(node, "public_domain", None) or node.public_ip
            )
        )
        port = _valid_port(
            payload["port"] if "port" in payload else (
                row.port if row and row.port else cfg.port
            )
        )
        if "sni" in payload:
            sni = _valid_host(payload["sni"]) if payload["sni"] else None
        else:
            sni = row.sni if row else None
    except (ConnectionProjectionError, TypeError, ValueError) as exc:
        raise HTTPException(422, "آدرس، پورت یا SNI معتبر نیست") from exc
    if row is None:
        row = NodeProtocolAppliedEndpoint(node_id=node_id, protocol=protocol)
        db.add(row)
    row.host, row.port, row.sni = host, port, sni
    row.is_applied = False
    row.applied_confirmed_at = None
    row.updated_at = datetime.utcnow()
    db.commit()
    return _state(row)


@router.post("/{node_id}/{protocol}/confirm-applied")
def confirm_endpoint(
    node_id: int,
    protocol: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    protocol, node, cfg = _scope(db, node_id, protocol)
    if payload != {"confirmed_applied_on_node": True}:
        raise HTTPException(422, "تأیید صریح اعمال تنظیمات روی نود لازم است")
    row = _existing(db, node_id, protocol)
    if row is None or not row.host or not row.port:
        raise HTTPException(409, "ابتدا تنظیمات اتصال را ثبت کنید")
    node_state = str(getattr(node.status, "value", node.status)).lower()
    cfg_state = str(getattr(cfg.status, "value", cfg.status)).lower()
    if node_state != "online" or cfg_state != "online":
        raise HTTPException(409, "نود و پروتکل باید آنلاین باشند")
    # A direct endpoint must never silently replace an Iran->Exit tunnel entry.
    if db.query(Tunnel.id).filter(
        Tunnel.exit_node_id == node_id, Tunnel.is_active.is_(True),
    ).first() is not None:
        raise HTTPException(409, "ابتدا مسیر اتصال عمومی تونل را تعیین و بررسی کنید")
    row.is_applied = True
    row.applied_confirmed_at = datetime.utcnow()
    row.updated_at = row.applied_confirmed_at
    db.commit()
    return _state(row)
