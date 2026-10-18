from __future__ import annotations

from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from . import (
    tunnel_service_connections_admin_runtime,
    xray_modern_admin,
    xray_modern_repair_runtime,
    xray_modern_runtime,
    xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
)
from .database import get_db
from .routers import provision
from .xray_tcp_tls_v39 import (
    PROFILE_TCP_TLS,
    _tcp_tls_public_port,
    _tcp_tls_target_port,
)


# ============================================================
# TWINPANEL XRAY CUSTOMER PROFILE POLICY V30
#
# Final customer-facing policy previously validated in production:
#   1. WebSocket TLS
#   2. HTTPUpgrade TLS
#   3. VLESS TCP TLS
#
# gRPC Reality, XHTTP Reality and legacy/plain VLESS remain internal for
# rollback/diagnostics. They are intentionally NOT returned to customer/admin
# routed-service cards and are NOT required for subscription completeness.
#
# This module is a compatibility layer for the current release lineage. It
# composes with the restored V39/V44 TCP-TLS engine without replacing current
# Xray repair/admin code wholesale.
# ============================================================

_runtime_applied = False

PUBLIC_PROFILE_ORDER = (
    "websocket_tls",
    "httpupgrade_tls",
    PROFILE_TCP_TLS,
)
PUBLIC_PROFILE_IDS = frozenset(PUBLIC_PROFILE_ORDER)
HIDDEN_ROUTED_PROFILES = frozenset(
    {
        "legacy",
        "xhttp_reality",
        "grpc_reality",
        "tcp_simple",
    }
)

_original_admin_profile_rows = None
_original_admin_status_remote = None
_original_service_connections = None


def _required_profiles_v30(node) -> set[str]:
    domain = str(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
        or ""
    ).strip()

    if not domain:
        # No TLS identity means there is no customer-safe Xray profile to
        # materialize yet. Once a domain is saved, completeness is reevaluated
        # and reconciliation will build all three TLS profiles.
        return set()

    return set(PUBLIC_PROFILE_ORDER)


def _admin_profile_rows_v30(node, base_port: int) -> list[dict[str, Any]]:
    assert _original_admin_profile_rows is not None

    rows = list(_original_admin_profile_rows(node, int(base_port)))
    by_id = {
        str(row.get("id") or "").strip().lower(): dict(row)
        for row in rows
        if isinstance(row, dict)
    }

    tcp_meta = xray_modern_runtime.PROFILE_META.get(PROFILE_TCP_TLS, {})
    by_id[PROFILE_TCP_TLS] = {
        "id": PROFILE_TCP_TLS,
        "title": str(tcp_meta.get("title") or "VLESS TCP TLS"),
        "security": "tls",
        "transport": "tcp",
        "recommended": False,
        "requires_tls_domain": True,
        "target_port": _tcp_tls_target_port(int(base_port)),
        "tunnel_public_port": _tcp_tls_public_port(int(node.id)),
    }

    # The admin profile catalog should mirror the customer-safe policy. Hidden
    # listeners are still observable through diagnostics, not ordinary cards.
    return [
        by_id[profile]
        for profile in PUBLIC_PROFILE_ORDER
        if profile in by_id
    ]


async def _admin_status_remote_v30(conn, base_port: int) -> dict[str, Any]:
    assert _original_admin_status_remote is not None

    state = dict(
        await _original_admin_status_remote(
            conn,
            int(base_port),
        )
    )

    profiles = state.get("profiles")
    listeners = dict(profiles) if isinstance(profiles, dict) else {}
    listeners[PROFILE_TCP_TLS] = bool(
        await provision.listener(
            conn,
            _tcp_tls_target_port(int(base_port)),
            "tcp",
        )
    )

    # Keep raw internal listeners out of the normal admin/customer profile
    # contract. Diagnostics can still inspect them separately.
    state["profiles"] = {
        profile: bool(listeners.get(profile))
        for profile in PUBLIC_PROFILE_ORDER
    }
    return state


async def _service_connections_v30(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    assert _original_service_connections is not None

    payload = dict(
        await _original_service_connections(
            int(tunnel_id),
            db,
        )
    )

    rows = payload.get("connections")
    if not isinstance(rows, list):
        return payload

    filtered: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        protocol = str(row.get("protocol") or "").strip().lower()
        profile = str(row.get("profile") or "").strip().lower()

        if protocol == "v2ray":
            if profile in HIDDEN_ROUTED_PROFILES:
                continue
            if profile not in PUBLIC_PROFILE_IDS:
                continue
            if profile == PROFILE_TCP_TLS:
                row["title"] = "VLESS TCP TLS"

        filtered.append(row)

    order = {
        "cisco": 10,
        "openvpn": 20,
        "wireguard": 30,
        "l2tp": 40,
        "websocket_tls": 50,
        "httpupgrade_tls": 51,
        PROFILE_TCP_TLS: 52,
    }
    filtered.sort(
        key=lambda row: (
            order.get(
                str(row.get("profile") or row.get("protocol") or "")
                .strip()
                .lower(),
                999,
            ),
            int(row.get("public_port") or 0),
        )
    )

    payload["connections"] = filtered
    return payload


def apply_xray_customer_profile_policy_v30() -> None:
    global _runtime_applied
    global _original_admin_profile_rows
    global _original_admin_status_remote
    global _original_service_connections

    if _runtime_applied:
        return

    # Public customer delivery: TLS-only, in the exact approved order.
    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = PUBLIC_PROFILE_ORDER
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(PUBLIC_PROFILE_ORDER)
    xray_public_delivery_runtime._PROFILE_LABELS[PROFILE_TCP_TLS] = "VLESS TCP TLS"

    # Stored-credential completeness must follow the same public policy instead
    # of forcing retired XHTTP/gRPC profiles to exist.
    xray_profile_reconcile_v36._required_profiles = _required_profiles_v30

    # Admin profile/status endpoints use current runtime APIs plus TCP TLS.
    _original_admin_profile_rows = xray_modern_admin._profile_rows
    _original_admin_status_remote = xray_modern_admin._status_remote
    xray_modern_admin._profile_rows = _admin_profile_rows_v30
    xray_modern_admin._status_remote = _admin_status_remote_v30

    # Modules that imported these callables by value must be rebound after the
    # V39 TCP-TLS wrapper becomes the final production ensure function.
    xray_modern_admin._ensure_modern_xray = xray_modern_runtime._ensure_modern_xray
    xray_modern_repair_runtime._ensure_modern_xray = xray_modern_runtime._ensure_modern_xray

    # Service Connections imported _status_remote by value as well.
    tunnel_service_connections_admin_runtime._current_xray_status_remote = (
        _admin_status_remote_v30
    )
    tunnel_service_connections_admin_runtime._XRAY_PROFILE_TITLES[PROFILE_TCP_TLS] = (
        "VLESS TCP TLS"
    )

    _original_service_connections = (
        tunnel_service_connections_admin_runtime.tunnel_service_connections_admin
    )
    tunnel_service_connections_admin_runtime.tunnel_service_connections_admin = (
        _service_connections_v30
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_CUSTOMER_PROFILE_POLICY_V30_ACTIVE "
        "websocket_tls=public "
        "httpupgrade_tls=public "
        "tcp_tls=public "
        "grpc_reality=internal_only "
        "xhttp_reality=internal_only "
        "legacy=internal_only",
        flush=True,
    )
