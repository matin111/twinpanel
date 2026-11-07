"""Scoped live listener verification for centrally owned published Exits.

Initial hidden-node onboarding always uses the strict full-protocol audit.
After publication, a daemon-family delta verifies only its purchased protocol
listeners before mutation, not all 16 listeners on every purchase.
No credentials, subscriber data or service state are changed here.
"""
from __future__ import annotations

import asyncio

from ..models import Node, NodeProtocolConfig
from ..protocol_account_registry import ALL_PROTOCOL_SET, CLASSIC_PROTOCOL_KEYS
from ..node_runtime_connection import connect_protocol_runtime
from ..modern_protocol_dispatch import profile_health
from ..routers.provision import _protocol_live_health
from .central_runtime_ownership_v1 import allow_central_node, is_central_node
from .new_node_readiness_v1 import verify_new_exit_readiness, _online


async def verify_central_family_readiness(db, node_id: int, protocols) -> dict:
    keys = tuple(sorted(set(protocols)))
    if not keys or not set(keys).issubset(ALL_PROTOCOL_SET):
        return {"ok": False, "reason": "invalid_family", "missing": list(keys)}

    node = db.get(Node, int(node_id))
    if not allow_central_node(db, node):
        return {"ok": False, "reason": "unowned_exit", "missing": list(keys)}

    if not node.show_to_users:
        # Hidden Exits have never passed the initial customer-release gate.
        return await verify_new_exit_readiness(db, node_id)

    if not is_central_node(db, node_id):
        return {"ok": False, "reason": "unregistered_visible_exit",
                "missing": list(keys)}

    rows = {
        str(row.protocol): row
        for row in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol.in_(keys),
        ).all()
    }
    missing = [key for key in keys
               if key not in rows or not _online(rows[key].status)]
    if missing:
        return {"ok": False, "reason": "family_protocol_not_installed",
                "missing": missing}

    conn = None
    failed = []
    try:
        conn = await asyncio.wait_for(
            connect_protocol_runtime(node, db), timeout=20,
        )
        for key in keys:
            try:
                if key in CLASSIC_PROTOCOL_KEYS:
                    status = await asyncio.wait_for(
                        _protocol_live_health(conn, key, rows[key]), timeout=25,
                    )
                else:
                    status = await asyncio.wait_for(
                        profile_health(conn, key, rows[key].port), timeout=25,
                    )
                if not status.get("ok"):
                    failed.append(key)
            except Exception:
                failed.append(key)
    except Exception:
        return {"ok": False, "reason": "management_connection_unavailable",
                "missing": list(keys)}
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()

    return {"ok": not failed, "reason": "ready" if not failed else "live_health_failed",
            "ready_count": len(keys) - len(failed), "required_count": len(keys),
            "missing": failed}
