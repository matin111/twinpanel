"""Per-node protocol presentation switch; admin only, no service shutdown.

Re-enable and disable change only new public delivery. Existing sessions,
stored keys, subscriptions, traffic history and other node protocols are not
modified. Individual restart actions are provided by the classic and modern
protocol runtime controllers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node
from ..node_runtime_connection import is_protocol_runtime_node
from ..node_protocol_operator_switches_v1 import is_disabled, set_disabled
from ..protocol_account_registry import canonical_protocol

router = APIRouter(
    prefix="/v1/admin/node-protocol-controls",
    tags=["node-protocol-operator-controls"],
    dependencies=[Depends(require_admin)],
)


class NodeProtocolToggleIn(BaseModel):
    disabled: bool = Field(...)


def _target(db: Session, node_id: int, protocol: str) -> tuple[Node, str]:
    node = db.query(Node).filter(
        Node.id == int(node_id), Node.retired_at.is_(None)
    ).first()
    if node is None or not is_protocol_runtime_node(node):
        raise HTTPException(status_code=404, detail="نود معتبر پیدا نشد")
    try:
        key = canonical_protocol(protocol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="پروتکل نامعتبر است") from exc
    return node, key


@router.get("/{node_id}/{protocol}")
def read_switch(node_id: int, protocol: str, db: Session = Depends(get_db)):
    node, key = _target(db, node_id, protocol)
    return {
        "ok": True, "node_id": node.id, "protocol": key,
        "disabled": is_disabled(db, node.id, key),
    }


@router.put("/{node_id}/{protocol}")
def write_switch(
    node_id: int,
    protocol: str,
    payload: NodeProtocolToggleIn,
    db: Session = Depends(get_db),
):
    node, key = _target(db, node_id, protocol)
    value = set_disabled(db, node.id, key, payload.disabled)
    db.commit()
    return {
        "ok": True,
        "node_id": node.id,
        "protocol": key,
        "disabled": value,
        "effect": "public_delivery_only",
        "runtime_stopped": False,
        "message": (
            "این پروتکل فقط روی این نود از لینک‌ها و کانفیگ‌های جدید مخفی شد"
            if value else "این پروتکل دوباره روی این نود برای کاربران قابل مشاهده شد"
        ),
    }
