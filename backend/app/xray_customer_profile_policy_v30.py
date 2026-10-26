from __future__ import annotations

import re
from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from . import (
    subscription_delivery_policy_v1,
    tunnel_service_connections_admin_runtime,
    xray_modern_admin,
    xray_modern_repair_runtime,
    xray_modern_runtime,
    xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
    xray_tcp_tls_v39,
)
from .database import get_db
from .models import Node
from .routers import account_delivery, provision
from .xray_tcp_tls_v39 import (
    PROFILE_TCP_TLS,
    _tcp_tls_public_port,
    _tcp_tls_target_port,
)


# ============================================================
# TWINPANEL XRAY CUSTOMER PROFILE POLICY V30 / DELIVERY V261
#
# Customer-facing delivery policy:
#   1. WebSocket TLS
#   2. HTTPUpgrade TLS
#   3. VLESS TCP TLS
#
# The legacy/plain VLESS listener remains excluded from customer delivery, but
# it is a real Desired Service Route and therefore belongs in the admin tunnel
# route inventory. Admin inventory is metadata-only and never exposes UUIDs,
# passwords, REALITY keys, paths or other customer credentials.
#
# gRPC Reality, XHTTP Reality and tcp_simple remain internal-only listeners and
# are not returned by either customer delivery or ordinary admin route cards.
#
# V261 closes two production gaps without changing the 14 non-Xray protocols:
#   * Connection Info can no longer leak a hidden XHTTP/gRPC top-level endpoint
#     after V30 has removed that profile from Desired Service Routes.
#   * customer TLS listener target ports are isolated from the modern protocol
#     8444..8452 runtime range. Public Iran ports remain unchanged.
# ============================================================

_runtime_applied = False

PUBLIC_PROFILE_ORDER = (
    "websocket_tls",
    "httpupgrade_tls",
    PROFILE_TCP_TLS,
)
PUBLIC_PROFILE_IDS = frozenset(PUBLIC_PROFILE_ORDER)
ADMIN_ROUTE_PROFILE_ORDER = (
    "legacy",
    *PUBLIC_PROFILE_ORDER,
)
ADMIN_ROUTE_PROFILE_IDS = frozenset(ADMIN_ROUTE_PROFILE_ORDER)
HIDDEN_ROUTED_PROFILES = frozenset(
    {
        "legacy",
        "xhttp_reality",
        "grpc_reality",
        "tcp_simple",
    }
)

# The default Xray service base is 8443. Offsets 1..9 overlap the modern
# protocol runtime range (8444..8452). Keep public ports stable and move only
# the three customer TLS listeners to an Xray-private target range:
#   WebSocket TLS    9444
#   HTTPUpgrade TLS  9445
#   TCP TLS          9446
TLS_TARGET_OFFSETS_V261 = {
    xray_modern_runtime.PROFILE_WS: 1001,
    xray_modern_runtime.PROFILE_HTTPUPGRADE: 1002,
    PROFILE_TCP_TLS: 1003,
}

_original_admin_profile_rows = None
_original_admin_status_remote = None
_original_service_connections = None
_original_stored_info_v261 = None
_original_explicit_stored_info_v261 = None


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


def _apply_tls_target_isolation_v261() -> None:
    """Move only customer Xray TLS target listeners out of 8444..8452."""

    for profile, offset in TLS_TARGET_OFFSETS_V261.items():
        meta = xray_modern_runtime.PROFILE_META.get(profile)
        if not isinstance(meta, dict):
            raise RuntimeError(f"Xray profile metadata missing: {profile}")
        meta["offset"] = int(offset)

    # V39 calculates TCP TLS target ports from its module-level offset rather
    # than PROFILE_META, so both authorities must converge to the same value.
    xray_tcp_tls_v39.TCP_TLS_OFFSET = int(
        TLS_TARGET_OFFSETS_V261[PROFILE_TCP_TLS]
    )


def _rewrite_vless_authority_v261(value: Any, host: str, port: int) -> str:
    raw = str(value or "").strip()
    if not raw:
        return raw

    authority_host = str(host or "").strip()
    if ":" in authority_host and not authority_host.startswith("["):
        authority_host = f"[{authority_host}]"

    return re.sub(
        r"^(vless://[^@]+@)(?:\[[^\]]+\]|[^:/?#]+):\d+",
        rf"\g<1>{authority_host}:{int(port)}",
        raw,
        count=1,
    )


def _profile_endpoint_v261(
    db: Session,
    node: Node,
    profile: str,
    item: dict[str, Any],
) -> tuple[str, int]:
    """Resolve a customer profile endpoint while preserving explicit mode."""

    mode = str(item.get("delivery_mode") or "").strip().lower()

    if mode == "direct":
        host = account_delivery._node_host(node)
        base_port = account_delivery._port(db, node.id, "v2ray")
        return host, xray_modern_runtime._target_port(base_port, profile)

    if mode == "tunnel":
        host = str(
            item.get("server")
            or item.get("server_ip")
            or ""
        ).strip()
        if not host:
            raise RuntimeError("Xray tunnel delivery host is missing")
        return host, xray_modern_runtime._public_port(node.id, profile)

    # Legacy delivery follows the currently assigned Iran -> Exit tunnel or the
    # existing direct-Exit fallback exactly as the Xray runtime already does.
    return xray_modern_runtime._profile_endpoint(db, node, profile)


def _customer_xray_item_v261(
    db: Session,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    """Return one TLS-policy-compliant Xray item or fail closed.

    Old credentials without profiles[] retain their historical migration path.
    Modern credentials with profiles[] are filtered to the V30 public contract;
    hidden XHTTP/gRPC/legacy profiles remain stored for diagnostics but are not
    delivered to customers.
    """

    raw_profiles = item.get("profiles")
    if not isinstance(raw_profiles, list):
        return dict(item)

    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        return None

    node = db.get(Node, node_id)
    if node is None:
        return None

    by_id: dict[str, dict[str, Any]] = {}

    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue

        profile_id = str(raw_profile.get("id") or "").strip().lower()
        if profile_id not in PUBLIC_PROFILE_IDS:
            continue

        uri = str(raw_profile.get("uri") or "").strip()
        if not uri:
            continue

        try:
            host, port = _profile_endpoint_v261(
                db,
                node,
                profile_id,
                item,
            )
        except Exception:
            # Never publish a stale hidden endpoint when the approved profile
            # cannot be materialized against current control-plane state.
            continue

        profile = dict(raw_profile)
        profile["server"] = host
        profile["server_ip"] = host
        profile["port"] = int(port)
        profile["uri"] = _rewrite_vless_authority_v261(uri, host, int(port))
        profile["qr"] = account_delivery._qr_data_uri(profile["uri"])
        by_id[profile_id] = profile

    profiles = [
        by_id[profile_id]
        for profile_id in PUBLIC_PROFILE_ORDER
        if profile_id in by_id
    ]

    if not profiles:
        # V30 is intentionally TLS-only. If no TLS profile is ready (normally
        # because the Exit lacks a prepared Xray domain/certificate), omit Xray
        # instead of leaking the old internal XHTTP endpoint such as :24006.
        return None

    selected = profiles[0]
    result = dict(item)
    result["profiles"] = profiles
    result["server"] = selected["server"]
    result["server_ip"] = selected["server"]
    result["port"] = int(selected["port"])
    result["uri"] = selected["uri"]
    result["qr"] = selected["qr"]
    result["profile"] = str(selected.get("id") or "")

    for key in ("sni", "security", "transport"):
        if selected.get(key) is not None:
            result[key] = selected.get(key)

    return result


def _enforce_customer_xray_payload_v261(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    credentials = payload.get("credentials")
    if not isinstance(credentials, list):
        return payload

    output_credentials: list[dict[str, Any]] = []

    for raw_credential in credentials:
        if not isinstance(raw_credential, dict):
            continue

        credential = dict(raw_credential)
        protocol = str(credential.get("protocol") or "").strip().lower()

        if protocol not in {"v2ray", "xray"}:
            output_credentials.append(credential)
            continue

        raw_items = credential.get("items")
        source_items = raw_items if isinstance(raw_items, list) else [raw_items]
        output_items: list[dict[str, Any]] = []

        for raw_item in source_items:
            if not isinstance(raw_item, dict):
                continue
            item = _customer_xray_item_v261(db, raw_item)
            if item is not None:
                output_items.append(item)

        if not output_items:
            continue

        credential["items"] = output_items
        output_credentials.append(credential)

    result = dict(payload)
    result["credentials"] = output_credentials
    return result


def _stored_info_v261(db: Session, sub) -> dict[str, Any]:
    assert _original_stored_info_v261 is not None
    return _enforce_customer_xray_payload_v261(
        db,
        _original_stored_info_v261(db, sub),
    )


def _compile_explicit_stored_info_v261(
    ad: Any,
    db: Session,
    sub,
) -> dict[str, Any]:
    assert _original_explicit_stored_info_v261 is not None
    return _enforce_customer_xray_payload_v261(
        db,
        _original_explicit_stored_info_v261(ad, db, sub),
    )


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

    # The Xray profile catalog mirrors customer-safe delivery. The separate
    # tunnel Service Connections endpoint owns the admin Desired Route inventory
    # and may include the credential-free legacy backstop route.
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

    # Keep raw internal listeners out of the normal Xray profile contract.
    # Tunnel route inventory probes legacy independently when needed.
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
            # Customer delivery remains TLS-only. Admin Service Connections is
            # a credential-free Desired Route inventory, so the real legacy
            # V2Ray route must remain visible even when no TLS domain exists.
            if profile not in ADMIN_ROUTE_PROFILE_IDS:
                continue
            if profile == "legacy":
                row["title"] = "V2Ray / Xray"
            elif profile == PROFILE_TCP_TLS:
                row["title"] = "VLESS TCP TLS"

        filtered.append(row)

    order = {
        "cisco": 10,
        "openvpn": 20,
        "wireguard": 30,
        "l2tp": 40,
        "legacy": 50,
        "websocket_tls": 51,
        "httpupgrade_tls": 52,
        PROFILE_TCP_TLS: 53,
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
    global _original_stored_info_v261
    global _original_explicit_stored_info_v261

    if _runtime_applied:
        return

    # Isolate the three customer TLS target listeners before reconciliation or
    # route generation consumes profile metadata. Iran public ports do not move.
    _apply_tls_target_isolation_v261()

    # Public customer delivery: TLS-only, in the exact approved order.
    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = PUBLIC_PROFILE_ORDER
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(PUBLIC_PROFILE_ORDER)
    xray_public_delivery_runtime._PROFILE_LABELS[PROFILE_TCP_TLS] = "VLESS TCP TLS"

    # Stored-credential completeness must follow the same public policy instead
    # of forcing retired XHTTP/gRPC profiles to exist.
    xray_profile_reconcile_v36._required_profiles = _required_profiles_v30

    # Connection Info is another customer delivery surface. Apply the exact
    # same TLS-only contract to both legacy and explicit-policy compilers. Main
    # installs subscription_delivery_policy_v1 after self-hosted runtime, so it
    # will capture this guarded legacy function and resolve the patched explicit
    # compiler at request time.
    _original_stored_info_v261 = account_delivery._stored_info
    account_delivery._stored_info = _stored_info_v261

    _original_explicit_stored_info_v261 = (
        subscription_delivery_policy_v1.compile_explicit_stored_info
    )
    subscription_delivery_policy_v1.compile_explicit_stored_info = (
        _compile_explicit_stored_info_v261
    )

    # Admin Xray profile/status endpoints use current runtime APIs plus TCP TLS.
    # They intentionally remain customer-safe; tunnel route inventory is a
    # separate contract and is rebound below.
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
        "legacy=admin_route_only "
        "customer_connection_info=v261 "
        "tls_target_isolation=v261",
        flush=True,
    )
