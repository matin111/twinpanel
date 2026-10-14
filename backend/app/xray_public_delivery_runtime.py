from __future__ import annotations

from typing import Any

from sqlalchemy import inspect

from . import xray_node_domain_runtime
from .database import engine
from .routers import account_delivery, public_connection_v3


# TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V1
#
# The public /v1/connect page is imported before the self-hosted runtime applies
# Modern Xray. It therefore keeps an early reference to account_delivery's
# original _public_payload, and its legacy renderer only consumes item.uri.
#
# Modern credentials already carry item.profiles[] with a dedicated URI for
# WebSocket TLS / XHTTP REALITY / HTTPUpgrade TLS / gRPC REALITY. This runtime
# reconnects the public page to the final account-delivery payload and expands
# those profile items into the existing server-tab UI without rewriting the
# public page or changing any credential material.
#
# Production also calls xray_node_domain_runtime on every API start. Once the
# xray_domain column already exists, running ALTER TABLE ... IF NOT EXISTS again
# is unnecessary and can block startup while PostgreSQL waits for an ACCESS
# EXCLUSIVE lock. Install a narrow guard before self_hosted_runtime applies the
# node-domain runtime: inspect the existing columns first and only execute the
# historical migration when the column is actually absent.

_runtime_applied = False
_original_connection_views = public_connection_v3.connection_views
_original_domain_schema_ensure = xray_node_domain_runtime._ensure_database_column

_PROFILE_LABELS = {
    "websocket_tls": "WebSocket TLS",
    "xhttp_reality": "XHTTP Reality",
    "httpupgrade_tls": "HTTPUpgrade TLS",
    "grpc_reality": "gRPC Reality",
}


def _ensure_domain_schema_without_redundant_alter() -> None:
    inspector = inspect(engine)

    if not inspector.has_table("nodes"):
        return _original_domain_schema_ensure()

    columns = {
        str(column.get("name") or "").strip()
        for column in inspector.get_columns("nodes")
        if isinstance(column, dict)
    }

    if "xray_domain" in columns:
        return

    return _original_domain_schema_ensure()


# This module is imported by self_hosted_runtime before
# apply_xray_node_domain_runtime() executes, so the guarded implementation is
# already active when startup reaches the schema check.
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


def _expanded_xray_items(
    items: list[dict[str, Any]],
    node_names: dict[int, str],
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []

    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            continue

        item = dict(raw_item)
        profiles = item.get("profiles")

        if not isinstance(profiles, list) or not profiles:
            # Legacy VLESS remains visible exactly as before.
            expanded.append(item)
            continue

        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            node_id = 0

        base_name = str(
            node_names.get(node_id)
            or item.get("node")
            or item.get("server")
            or item.get("server_ip")
            or f"Server {index + 1}"
        ).strip()

        added = 0

        for raw_profile in profiles:
            if not isinstance(raw_profile, dict):
                continue

            profile = dict(raw_profile)
            uri = str(profile.get("uri") or "").strip()

            if not uri:
                continue

            entry = dict(item)
            entry.pop("profiles", None)

            # Profile-specific delivery values override the compatibility
            # top-level values on the modern credential item.
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
            entry["node"] = f"{base_name} · {_profile_label(profile)}"

            qr = str(profile.get("qr") or "").strip()
            if not qr:
                qr = account_delivery._qr_data_uri(uri)
            entry["qr"] = qr

            expanded.append(entry)
            added += 1

        # If a malformed modern payload contains no usable profile URI, keep
        # the stored primary item instead of making Xray disappear entirely.
        if added == 0:
            expanded.append(item)

    return expanded


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

    expanded = _expanded_xray_items(
        items,
        node_names,
    )

    return _original_connection_views(
        protocol,
        expanded,
        fallback_username,
        fallback_password,
        node_names,
    )


def apply_xray_public_delivery_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    # public_connection_v3 imported _public_payload before Modern Xray patched
    # account_delivery. Rebind it to the final runtime function so nested
    # profile QR codes and live endpoints are included on public share pages.
    public_connection_v3._public_payload = account_delivery._public_payload
    public_connection_v3.connection_views = _connection_views_modern_xray

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_DELIVERY_RUNTIME_V1_ACTIVE "
        "profile_tabs=1 dynamic_public_payload=1 legacy_fallback=1 "
        "domain_schema_lock_guard=1",
        flush=True,
    )
