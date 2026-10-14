from __future__ import annotations

from typing import Any

from sqlalchemy import text

from . import xray_node_domain_runtime
from .database import engine
from .routers import account_delivery, public_connection_v3


# TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V3
#
# The public /v1/connect page is imported before the self-hosted runtime applies
# Modern Xray. It therefore keeps an early reference to account_delivery's
# original _public_payload, and its legacy renderer only consumes item.uri.
#
# Modern credentials already carry item.profiles[] with a dedicated URI for
# WebSocket TLS / XHTTP REALITY / HTTPUpgrade TLS / gRPC REALITY. V3 keeps one
# server/country tab per Xray node and renders the customer-safe profiles for
# that node inside the same server view. For Iran-facing delivery WebSocket TLS
# is preferred, XHTTP REALITY is the fallback, and gRPC is intentionally hidden
# from the customer page. Internal listeners/routes are not removed by this UI
# runtime, so operational rollback remains possible without reprovisioning.
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
    "httpupgrade_tls": "HTTPUpgrade TLS",
    "grpc_reality": "gRPC Reality",
}

# Customer delivery policy for restricted Iranian networks.
# Keep the list intentionally short and stable:
#   1. WebSocket TLS when a dedicated Xray domain/certificate is ready.
#   2. XHTTP REALITY as the no-domain / fallback profile.
# gRPC is deliberately not exposed to end users.
_PUBLIC_PROFILE_ORDER = (
    "websocket_tls",
    "xhttp_reality",
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
        # A modern credential may currently contain only a hidden transport
        # (for example gRPC) while TLS/domain is still being prepared. Do not
        # fall back to exposing that hidden transport. If this is a true legacy
        # credential with no profiles[] at all, preserve the historical card.
        raw_profiles = item.get("profiles")
        if isinstance(raw_profiles, list):
            return (
                '<div class="empty-state">'
                'WebSocket TLS هنوز برای این سرور آماده نشده است. '
                'XHTTP نیز در حال حاضر در دسترس نیست.'
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

    public_connection_v3._public_payload = account_delivery._public_payload
    public_connection_v3.connection_views = _connection_views_modern_xray

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V3_ACTIVE "
        "server_tabs_grouped=1 profile_cards_together=1 "
        "websocket_first=1 xhttp_fallback=1 grpc_customer_hidden=1 "
        "dynamic_public_payload=1 legacy_fallback=1 "
        "domain_schema_catalog_guard=1",
        flush=True,
    )
