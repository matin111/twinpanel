from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from sqlalchemy import text

from . import xray_node_domain_runtime
from .database import engine
from .models import Node
from .routers import account_delivery, public_connection_v3


# TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V4
#
# The public /v1/connect page is imported before the self-hosted runtime applies
# Modern Xray. It therefore keeps an early reference to account_delivery's
# original _public_payload, and its legacy renderer only consumes item.uri.
#
# Modern credentials already carry item.profiles[] with a dedicated URI for
# WebSocket TLS / XHTTP REALITY / HTTPUpgrade TLS / gRPC REALITY. V4 keeps one
# server/country tab per Xray node and renders the customer-safe profiles for
# that node inside the same server view. For Iran-facing delivery WebSocket TLS
# is preferred, XHTTP REALITY is the modern no-domain fallback, and the already
# preserved legacy VLESS TCP listener is exposed as a simple compatibility
# fallback. gRPC remains intentionally hidden from the customer page.
# Internal listeners/routes are not removed by this UI runtime, so operational
# rollback remains possible without reprovisioning.
#
# Production also calls xray_node_domain_runtime on every API start. Once the
# xray_domain column already exists, running ALTER TABLE ... IF NOT EXISTS again
# is unnecessary and can block startup while PostgreSQL waits for an ACCESS
# EXCLUSIVE lock. The V2+ guard checks pg_catalog directly without requesting a
# relation lock. Existing installs with xray_domain skip the ALTER entirely.

_runtime_applied = False
_original_connection_views = public_connection_v3.connection_views
_original_domain_schema_ensure = xray_node_domain_runtime._ensure_database_column

_PROFILE_LABELS = {
    "websocket_tls": "WebSocket TLS",
    "xhttp_reality": "XHTTP Reality",
    "tcp_simple": "TCP ساده",
    "httpupgrade_tls": "HTTPUpgrade TLS",
    "grpc_reality": "gRPC Reality",
}

# Customer delivery policy for restricted Iranian networks.
# Keep the list intentionally short and stable:
#   1. WebSocket TLS when a dedicated Xray domain/certificate is ready.
#   2. XHTTP REALITY as the modern no-domain fallback.
#   3. Legacy VLESS TCP as a simple compatibility fallback.
# gRPC is deliberately not exposed to end users.
_PUBLIC_PROFILE_ORDER = (
    "websocket_tls",
    "xhttp_reality",
    "tcp_simple",
)
_PUBLIC_PROFILE_IDS = set(_PUBLIC_PROFILE_ORDER)


def _nodes_schema_state() -> tuple[bool, bool]:
    """Return (nodes_exists, xray_domain_exists) without locking nodes."""

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    to_regclass('nodes') IS NOT NULL AS nodes_exists,
                    EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_attribute AS attribute
                        WHERE attribute.attrelid = to_regclass('nodes')
                          AND attribute.attname = 'xray_domain'
                          AND attribute.attnum > 0
                          AND NOT attribute.attisdropped
                    ) AS xray_domain_exists
                """
            )
        ).mappings().one()

    return (
        bool(row["nodes_exists"]),
        bool(row["xray_domain_exists"]),
    )


def _ensure_domain_schema_without_redundant_alter() -> None:
    nodes_exists, xray_domain_exists = _nodes_schema_state()

    if not nodes_exists:
        return

    if xray_domain_exists:
        return

    return _original_domain_schema_ensure()


xray_node_domain_runtime._ensure_database_column = (
    _ensure_domain_schema_without_redundant_alter
)


def _profile_label(profile: dict[str, Any]) -> str:
    profile_id = str(profile.get("id") or "").strip().lower()
    title = str(profile.get("title") or "").strip()
    label = _PROFILE_LABELS.get(profile_id) or title or profile_id or "Xray"

    if bool(profile.get("recommended")):
        return f"{label} ★"

    return label


def _server_name(
    item: dict[str, Any],
    node_names: dict[int, str],
    index: int,
) -> str:
    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        node_id = 0

    return str(
        node_names.get(node_id)
        or item.get("node")
        or item.get("server")
        or item.get("server_ip")
        or f"Server {index + 1}"
    ).strip()


def _existing_uuid(item: dict[str, Any]) -> str:
    value = str(item.get("uuid") or "").strip()

    if value:
        return value

    uri = str(item.get("uri") or "").strip()
    match = re.match(r"^vless://([^@/?#]+)@", uri)
    return match.group(1) if match else ""


def _legacy_tcp_profile(
    db,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the already-preserved legacy VLESS TCP profile for one node."""

    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        return None

    if not node_id:
        return None

    client_id = _existing_uuid(item)
    if not client_id:
        return None

    node = db.get(Node, node_id)
    if not node:
        return None

    try:
        host, port = account_delivery._tunnel_access_endpoint(
            db,
            node,
            "v2ray",
        )
    except Exception:
        return None

    name = str(
        item.get("node")
        or getattr(node, "name", None)
        or f"node-{node_id}"
    ).strip()

    fragment = quote(f"{name}-TCP", safe="")
    uri = (
        f"vless://{client_id}@{host}:{int(port)}"
        f"?encryption=none&type=tcp#{fragment}"
    )

    return {
        "id": "tcp_simple",
        "title": "VLESS TCP ساده",
        "recommended": False,
        "security": "none",
        "transport": "tcp",
        "server": host,
        "port": int(port),
        "uri": uri,
        "qr": account_delivery._qr_data_uri(uri),
    }


def _public_payload_customer_xray(db, sub) -> dict[str, Any]:
    """Add a customer-safe TCP fallback without changing stored credentials."""

    payload = account_delivery._public_payload(db, sub)

    credentials = payload.get("credentials")
    if not isinstance(credentials, list):
        return payload

    for credential in credentials:
        if not isinstance(credential, dict):
            continue

        protocol = str(credential.get("protocol") or "").strip().lower()
        if protocol not in {"v2ray", "xray"}:
            continue

        items = credential.get("items")
        source_items = items if isinstance(items, list) else [items]

        for item in source_items:
            if not isinstance(item, dict):
                continue

            profiles = item.get("profiles")
            if not isinstance(profiles, list):
                continue

            existing_ids = {
                str(profile.get("id") or "").strip().lower()
                for profile in profiles
                if isinstance(profile, dict)
            }

            if "tcp_simple" in existing_ids:
                continue

            tcp_profile = _legacy_tcp_profile(db, item)
            if tcp_profile is not None:
                profiles.append(tcp_profile)

    return payload


def _profile_delivery_item(
    item: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    uri = str(profile.get("uri") or "").strip()

    if not uri:
        return None

    entry = dict(item)
    entry.pop("profiles", None)

    for key in (
        "server",
        "port",
        "uri",
        "sni",
        "security",
        "transport",
    ):
        if profile.get(key) is not None:
            entry[key] = profile.get(key)

    entry["uri"] = uri
    entry["profile"] = str(profile.get("id") or "").strip()
    entry["profile_title"] = _profile_label(profile)
    entry["recommended"] = bool(profile.get("recommended"))

    qr = str(profile.get("qr") or "").strip()
    if not qr:
        qr = account_delivery._qr_data_uri(uri)
    entry["qr"] = qr

    return entry


def _customer_profiles(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_profiles = item.get("profiles")

    if not isinstance(raw_profiles, list):
        return []

    by_id: dict[str, dict[str, Any]] = {}

    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue

        profile = dict(raw_profile)
        profile_id = str(profile.get("id") or "").strip().lower()

        if profile_id not in _PUBLIC_PROFILE_IDS:
            continue

        if not str(profile.get("uri") or "").strip():
            continue

        by_id[profile_id] = profile

    return [
        by_id[profile_id]
        for profile_id in _PUBLIC_PROFILE_ORDER
        if profile_id in by_id
    ]


def _xray_server_body(
    item: dict[str, Any],
    server_name: str,
    server_index: int,
) -> str:
    profiles = _customer_profiles(item)

    if not profiles:
        # A modern credential may currently contain only hidden transports.
        # Do not expose those. True legacy credentials without profiles[] keep
        # their historical single-card behavior.
        raw_profiles = item.get("profiles")
        if isinstance(raw_profiles, list):
            return (
                '<div class="empty-state">'
                'پروفایل قابل استفاده Xray برای این سرور آماده نیست.'
                '</div>'
            )

        return public_connection_v3.v2ray_card(
            server_index,
            server_name,
            item,
        )

    cards: list[str] = []

    for profile_index, profile in enumerate(profiles):
        entry = _profile_delivery_item(item, profile)

        if entry is None:
            continue

        cards.append(
            public_connection_v3.v2ray_card(
                profile_index,
                _profile_label(profile),
                entry,
            )
        )

    if not cards:
        return '<div class="empty-state">پروفایل قابل استفاده Xray آماده نیست.</div>'

    return (
        '<div style="display:grid;'
        'grid-template-columns:repeat(auto-fit,minmax(290px,1fr));'
        'gap:10px">'
        + "".join(cards)
        + "</div>"
    )


def _connection_views_modern_xray(
    protocol: str,
    items: list[dict[str, Any]],
    fallback_username: str,
    fallback_password: str,
    node_names: dict[int, str],
) -> tuple[str, str]:
    protocol_key = str(protocol or "").strip().lower()

    if protocol_key not in {"v2ray", "xray"}:
        return _original_connection_views(
            protocol,
            items,
            fallback_username,
            fallback_password,
            node_names,
        )

    if not items:
        return "", '<div class="empty-state">اطلاعات این پروتکل هنوز آماده نشده است.</div>'

    tabs: list[str] = []
    views: list[str] = []
    h = public_connection_v3.h

    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            continue

        item = dict(raw_item)
        active = " active" if not tabs else ""
        server_id = f"{protocol_key}-server-{index}"
        server_name = _server_name(item, node_names, index)

        tabs.append(
            f'<button class="server-tab{active}" type="button" '
            f'data-server="{h(server_id)}">'
            f'<span>{h(server_name)}</span><i></i></button>'
        )

        body = _xray_server_body(
            item,
            server_name,
            index,
        )

        views.append(
            f'<div id="{h(server_id)}" class="server-view{active}">'
            f'{body}</div>'
        )

    if not tabs:
        return "", '<div class="empty-state">اطلاعات این پروتکل هنوز آماده نشده است.</div>'

    return "".join(tabs), "".join(views)


def apply_xray_public_delivery_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    public_connection_v3._public_payload = _public_payload_customer_xray
    public_connection_v3.connection_views = _connection_views_modern_xray

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V4_ACTIVE "
        "server_tabs_grouped=1 profile_cards_together=1 "
        "websocket_first=1 xhttp_fallback=1 tcp_simple_fallback=1 "
        "grpc_customer_hidden=1 dynamic_public_payload=1 "
        "legacy_fallback=1 domain_schema_catalog_guard=1",
        flush=True,
    )
