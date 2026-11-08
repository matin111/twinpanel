"""Read-only final health gate for new Exit nodes before any user enrollment.

A DB row marked online is not proof of a currently usable listener. Re-check
all 16 protocols over ONE saved management connection and fail closed.
No configuration mutations, SSH credentials, subscriber data or service reloads.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeProtocolConfig, NodeType
from ..node_runtime_connection import connect_protocol_runtime
from ..protocol_account_registry import ALL_PROTOCOL_KEYS, CLASSIC_PROTOCOL_KEYS
from ..modern_protocol_dispatch import profile_health
from ..routers.provision import _protocol_live_health


def _online(value: Any) -> bool:
    return str(getattr(value, "value", value) or "").lower() == "online"


async def verify_new_exit_readiness(db: Session, node_id: int) -> dict[str, Any]:
    node = db.get(Node, int(node_id))
    if node is None or node.retired_at is not None or node.node_type != NodeType.EXIT:
        return {"ok": False, "reason": "invalid_exit", "missing": list(ALL_PROTOCOL_KEYS)}

    rows = {
        str(row.protocol): row
        for row in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol.in_(list(ALL_PROTOCOL_KEYS)),
        ).all()
    }
    missing = [
        key for key in ALL_PROTOCOL_KEYS
        if key not in rows or not _online(rows[key].status)
    ]
    if missing:
        return {
            "ok": False, "reason": "protocol_not_installed",
            "ready_count": len(ALL_PROTOCOL_KEYS) - len(missing),
            "required_count": len(ALL_PROTOCOL_KEYS), "missing": missing,
        }

    conn = None
    failed: list[str] = []
    try:
        conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=20)
        for key in ALL_PROTOCOL_KEYS:
            row = rows[key]
            try:
                if key in CLASSIC_PROTOCOL_KEYS:
                    status = await asyncio.wait_for(
                        _protocol_live_health(conn, key, row), timeout=25,
                    )
                else:
                    status = await asyncio.wait_for(
                        profile_health(conn, key, row.port), timeout=25,
                    )
                if not bool(status.get("ok")):
                    failed.append(key)
                elif key == "v2ray":
                    # Service active + a single legacy port is NOT sufficient.
                    # The customer requires three real VLESS inbounds, not
                    # fabricated delivery links or silently missing Vision.
                    # Read actual node authority only; never repair on GET.
                    from ..central_xray_node_authority_v1 import (
                        read_node_public_authority,
                    )
                    authority = await asyncio.wait_for(
                        read_node_public_authority(conn), timeout=65,
                    )
                    if len(set(authority.get("profiles") or [])) != 3:
                        failed.append(key)
            except Exception:
                # This is a read-only guard. Do not log sensitive command output.
                failed.append(key)
    except Exception:
        return {
            "ok": False, "reason": "management_connection_unavailable",
            "ready_count": 0, "required_count": len(ALL_PROTOCOL_KEYS),
            "missing": list(ALL_PROTOCOL_KEYS),
        }
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()

    return {
        "ok": not failed,
        "reason": "ready" if not failed else "live_health_failed",
        "ready_count": len(ALL_PROTOCOL_KEYS) - len(failed),
        "required_count": len(ALL_PROTOCOL_KEYS),
        "missing": failed,
    }
