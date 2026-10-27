from __future__ import annotations

import asyncio
import time
from typing import Any

from . import (
    xray_customer_profile_policy_v30 as policy_v30,
    xray_modern_runtime,
    xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
)
from .database import SessionLocal
from .models import Node, NodeProtocolConfig, NodeType
from .routers import account_delivery, provision
from .xray_tcp_tls_v39 import PROFILE_TCP_TLS


# TWINPANEL_XRAY_CUSTOMER_XHTTP_V46
#
# V30 intentionally hid XHTTP because its historical base+1 target listener
# landed in the shared 8444..8452 modern-protocol range. XHTTP itself remains a
# complete REALITY profile in the Xray runtime and already has a stable Iran
# public-port family (24000 + Exit node id).
#
# V46 restores XHTTP to the customer contract without reopening that collision:
#   WebSocket TLS -> XHTTP Reality -> VLESS TCP TLS
#
# Only the Exit-side XHTTP target offset moves into the Xray-private listener
# range. Public Iran ports, UUIDs, REALITY keys, short IDs and paths are kept.

XHTTP_TARGET_OFFSET_V46 = 1004
PUBLIC_PROFILE_ORDER_V46 = (
    xray_modern_runtime.PROFILE_WS,
    xray_modern_runtime.PROFILE_XHTTP,
    PROFILE_TCP_TLS,
)
PUBLIC_PROFILE_IDS_V46 = frozenset(PUBLIC_PROFILE_ORDER_V46)
ADMIN_ROUTE_PROFILE_ORDER_V46 = (
    "legacy",
    *PUBLIC_PROFILE_ORDER_V46,
)
ADMIN_ROUTE_PROFILE_IDS_V46 = frozenset(ADMIN_ROUTE_PROFILE_ORDER_V46)
HIDDEN_ROUTED_PROFILES_V46 = frozenset(
    {
        "legacy",
        xray_modern_runtime.PROFILE_HTTPUPGRADE,
        xray_modern_runtime.PROFILE_GRPC,
        "tcp_simple",
    }
)

_runtime_applied = False
_original_run_reconcile_job = None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _effective_domain(node: Node) -> str:
    return str(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
        or ""
    ).strip().lower()


def _required_profiles_v46(node: Node) -> set[str]:
    # XHTTP REALITY is domain-independent and is the safe baseline profile.
    required = {xray_modern_runtime.PROFILE_XHTTP}

    # WebSocket TLS and TCP TLS require the dedicated Xray TLS identity.
    if _effective_domain(node):
        required.update(
            {
                xray_modern_runtime.PROFILE_WS,
                PROFILE_TCP_TLS,
            }
        )

    return required


def _xhttp_target_port(base_port: int) -> int:
    port = int(base_port) + int(XHTTP_TARGET_OFFSET_V46)
    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid XHTTP target port: {port}")
    return port


async def _prepare_exit_xhttp_runtime(
    job_id: str,
    exit_node_id: int,
) -> None:
    """Ensure the collision-free XHTTP listener before credential reconcile."""

    db = SessionLocal()
    try:
        job = xray_profile_reconcile_v36._jobs.get(str(job_id))
        if job is not None:
            job["infrastructure_xhttp"] = {
                "status": "checking",
                "profile": xray_modern_runtime.PROFILE_XHTTP,
            }

        node = db.get(Node, int(exit_node_id))
        if node is None or node.node_type != NodeType.EXIT:
            raise RuntimeError("exit_node_not_found")

        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == int(exit_node_id),
                NodeProtocolConfig.protocol == "v2ray",
            )
            .first()
        )
        if (
            not bool(getattr(node, "enable_v2ray", False))
            or cfg is None
            or _enum_value(cfg.status) != "online"
        ):
            raise RuntimeError("exit_xray_not_online")

        base_port = int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"])
        target_port = _xhttp_target_port(base_port)
        conn = await account_delivery.ssh_connect_saved(node, db)

        try:
            if await provision.listener(conn, target_port, "tcp"):
                result = {
                    "status": "already_ready",
                    "profile": xray_modern_runtime.PROFILE_XHTTP,
                    "target_port": target_port,
                    "changed": False,
                }
            else:
                # Final runtime binding preserves existing clients/UUIDs and
                # validates the candidate config before replacing live Xray.
                state = await xray_modern_runtime._ensure_modern_xray(
                    conn,
                    base_port,
                    node,
                )
                listener_ok = bool(
                    await provision.listener(conn, target_port, "tcp")
                )
                if not listener_ok:
                    raise RuntimeError(
                        f"xhttp_listener_missing_after_repair:{target_port}"
                    )
                result = {
                    "status": "repaired",
                    "profile": xray_modern_runtime.PROFILE_XHTTP,
                    "target_port": target_port,
                    "changed": True,
                    "available_profiles": list(
                        state.get("available_profiles") or []
                    ),
                }
        finally:
            conn.close()
            await conn.wait_closed()

        if job is not None:
            job["infrastructure_xhttp"] = result
    finally:
        db.close()


async def _run_reconcile_job_v46(
    job_id: str,
    exit_node_id: int,
) -> None:
    assert _original_run_reconcile_job is not None

    try:
        await _prepare_exit_xhttp_runtime(str(job_id), int(exit_node_id))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        job = xray_profile_reconcile_v36._jobs.get(str(job_id))
        if job is not None:
            job["status"] = "failed"
            job["finished_at_epoch"] = time.time()
            job["error"] = "xray_xhttp_infrastructure_repair_failed: " + str(exc)[:1400]
            job["infrastructure_xhttp"] = {
                "status": "failed",
                "profile": xray_modern_runtime.PROFILE_XHTTP,
                "error": str(exc)[:1200],
            }

        async with xray_profile_reconcile_v36._job_lock:
            if (
                xray_profile_reconcile_v36._running_by_exit.get(int(exit_node_id))
                == str(job_id)
            ):
                xray_profile_reconcile_v36._running_by_exit.pop(
                    int(exit_node_id),
                    None,
                )
        return

    # Preserve V41 TCP-TLS infrastructure preflight and the V36 UUID-preserving
    # credential reconcile by delegating to the already-composed job wrapper.
    await _original_run_reconcile_job(str(job_id), int(exit_node_id))


def apply_xray_customer_xhttp_v46() -> None:
    global _runtime_applied
    global _original_run_reconcile_job

    if _runtime_applied:
        return

    # Move XHTTP out of the shared Modern runtime range. The Iran-facing public
    # port stays 24000 + Exit id because public_base is intentionally untouched.
    meta = xray_modern_runtime.PROFILE_META.get(
        xray_modern_runtime.PROFILE_XHTTP
    )
    if not isinstance(meta, dict):
        raise RuntimeError("XHTTP profile metadata missing")
    meta["offset"] = int(XHTTP_TARGET_OFFSET_V46)

    # Keep the V30 authority tables coherent for all wrappers it already
    # installed. Those wrappers read these module globals at request time.
    policy_v30.PUBLIC_PROFILE_ORDER = PUBLIC_PROFILE_ORDER_V46
    policy_v30.PUBLIC_PROFILE_IDS = PUBLIC_PROFILE_IDS_V46
    policy_v30.ADMIN_ROUTE_PROFILE_ORDER = ADMIN_ROUTE_PROFILE_ORDER_V46
    policy_v30.ADMIN_ROUTE_PROFILE_IDS = ADMIN_ROUTE_PROFILE_IDS_V46
    policy_v30.HIDDEN_ROUTED_PROFILES = HIDDEN_ROUTED_PROFILES_V46
    policy_v30.TLS_TARGET_OFFSETS_V261[xray_modern_runtime.PROFILE_XHTTP] = int(
        XHTTP_TARGET_OFFSET_V46
    )

    # Public page and stored Connection Info must expose the exact same three
    # customer profiles in the same order.
    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = PUBLIC_PROFILE_ORDER_V46
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(PUBLIC_PROFILE_ORDER_V46)
    xray_public_delivery_runtime._PROFILE_LABELS[
        xray_modern_runtime.PROFILE_XHTTP
    ] = "XHTTP Reality"

    # Completeness now requires XHTTP even without a TLS domain. With a domain,
    # all three customer profiles must exist before the item is considered done.
    xray_profile_reconcile_v36._required_profiles = _required_profiles_v46

    # Extend V41's reconcile preflight rather than replacing it.
    _original_run_reconcile_job = xray_profile_reconcile_v36._run_reconcile_job
    xray_profile_reconcile_v36._run_reconcile_job = _run_reconcile_job_v46

    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_CUSTOMER_XHTTP_V46_ACTIVE "
        "public_profiles=websocket_tls,xhttp_reality,tcp_tls "
        "xhttp_target_offset=1004 public_port_unchanged=1 "
        "uuid_preserved=1 reality_identity_preserved=1",
        flush=True,
    )
