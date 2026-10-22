from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base
from .models import (
    Node,
    NodeProtocolConfig,
    NodeStatus,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    Tunnel,
    TunnelStatus,
)
from .protocol_catalog import PROTOCOL_CATALOG


POLICY_SCHEMA_VERSION = 1
CLASSIC_PROTOCOLS = ("cisco", "openvpn", "wireguard", "l2tp", "v2ray")
CLASSIC_NODE_FLAGS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


class SubscriptionDeliveryPolicyState(Base):
    """Marks a subscription as explicitly managed.

    Absence of this row is intentional: it means legacy delivery semantics remain
    in force. This makes the migration backward-compatible without a data rewrite.
    """

    __tablename__ = "subscription_delivery_policy_state"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(16), default="explicit", nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=POLICY_SCHEMA_VERSION, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SubscriptionNodeDeliveryMode(Base):
    """Route policy extension for an existing SubscriptionNode membership."""

    __tablename__ = "subscription_node_delivery_modes"

    subscription_node_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    direct_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tunnel_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tunnel_id: Mapped[int | None] = mapped_column(
        ForeignKey("tunnels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def is_explicit_policy(db: Session, subscription_id: int) -> bool:
    row = db.get(SubscriptionDeliveryPolicyState, int(subscription_id))
    return bool(row and row.mode == "explicit")


def protocol_capabilities() -> list[dict[str, Any]]:
    classic = {
        "cisco": ("Cisco / OpenConnect", "username_password", "per_user", ["connection_info"]),
        "openvpn": ("OpenVPN", "certificate", "per_user", ["openvpn"]),
        "wireguard": ("WireGuard", "peer", "per_peer", ["wireguard"]),
        "l2tp": ("L2TP / IPsec", "username_password_shared_psk", "per_user", ["connection_info"]),
        "v2ray": ("V2Ray / Xray", "uuid", "per_user", ["share", "base64"]),
    }
    rows: list[dict[str, Any]] = []
    for key, (title, identity, revoke, formats) in classic.items():
        rows.append(
            {
                "protocol": key,
                "title": title,
                "catalog_present": True,
                "runtime_ready": True,
                "account_delivery_ready": True,
                "quota_enforcement_ready": True,
                "identity_scope": identity,
                "revocation_scope": revoke,
                "direct_supported": True,
                "tunnel_supported": True,
                "formats": formats,
                "reason": None,
            }
        )

    modern_identity = {
        "hysteria2": ("password", "per_user"),
        "tuic": ("uuid_password", "per_user"),
        "anytls": ("password", "per_user"),
        "naive": ("username_password", "per_user"),
        "shadowtls": ("password", "per_user"),
        "snell": ("user_key_shared_server_psk", "per_user"),
        "mieru": ("username_password", "per_user"),
        "trusttunnel": ("username_password", "per_user"),
        "amneziawg": ("peer", "per_peer"),
        "sudoku": ("server_keys", "delivery_only"),
    }
    for key, (identity, revoke) in modern_identity.items():
        definition = dict(PROTOCOL_CATALOG.get(key) or {})
        formats = [name for name, enabled in (definition.get("formats") or {}).items() if enabled]
        static_status = str(definition.get("runtime_status") or "unknown")
        rows.append(
            {
                "protocol": key,
                "title": definition.get("title") or key,
                "catalog_present": bool(definition),
                "runtime_ready": static_status == "ready",
                "account_delivery_ready": False,
                "quota_enforcement_ready": False,
                "identity_scope": identity,
                "revocation_scope": revoke,
                "direct_supported": False,
                "tunnel_supported": False,
                "formats": formats,
                "reason": (
                    "node_quota_collector_and_account_adapter_required"
                    if key in {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"}
                    else "standalone_account_adapter_required"
                    if key in {"mieru", "trusttunnel", "amneziawg"}
                    else "no_verified_per_user_revoke_or_export"
                ),
            }
        )
    return rows


def capability_map() -> dict[str, dict[str, Any]]:
    return {row["protocol"]: row for row in protocol_capabilities()}


def explicit_memberships(db: Session, subscription_id: int) -> list[tuple[SubscriptionNode, SubscriptionNodeDeliveryMode]]:
    return (
        db.query(SubscriptionNode, SubscriptionNodeDeliveryMode)
        .join(
            SubscriptionNodeDeliveryMode,
            SubscriptionNodeDeliveryMode.subscription_node_id == SubscriptionNode.id,
        )
        .filter(SubscriptionNode.subscription_id == int(subscription_id))
        .order_by(SubscriptionNodeDeliveryMode.priority.asc(), SubscriptionNode.id.asc())
        .all()
    )


def explicit_nodes(db: Session, sub: Subscription) -> list[Node]:
    node_ids = [membership.node_id for membership, _ in explicit_memberships(db, sub.id)]
    if not node_ids:
        return []
    rows = (
        db.query(Node)
        .filter(Node.id.in_(node_ids), Node.retired_at.is_(None))
        .all()
    )
    by_id = {int(node.id): node for node in rows}
    return [by_id[node_id] for node_id in node_ids if node_id in by_id]


class _LegacyAutosyncSession:
    """Session facade which hides explicit subscriptions from legacy autosync.

    Installed-node convergence predates per-subscription delivery policy and
    begins by querying every Subscription. The facade changes only that single
    query shape; every other Session operation is delegated untouched.
    """

    def __init__(self, db: Session, explicit_ids: set[int]):
        self._db = db
        self._explicit_ids = explicit_ids

    def query(self, *entities: Any, **kwargs: Any):
        query = self._db.query(*entities, **kwargs)
        if (
            len(entities) == 1
            and entities[0] is Subscription
            and self._explicit_ids
        ):
            query = query.filter(~Subscription.id.in_(self._explicit_ids))
        return query

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def autosync_legacy_only_session(db: Session) -> Session | _LegacyAutosyncSession:
    explicit_ids = {
        int(row[0])
        for row in db.query(SubscriptionDeliveryPolicyState.subscription_id)
        .filter(SubscriptionDeliveryPolicyState.mode == "explicit")
        .all()
    }
    if not explicit_ids:
        return db
    return _LegacyAutosyncSession(db, explicit_ids)


def _node_protocol_runtime_ready(db: Session, node: Node, protocol: str) -> bool:
    flag = CLASSIC_NODE_FLAGS.get(protocol)
    if not flag or not bool(getattr(node, flag, False)):
        return False
    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )
    return bool(cfg and _enum_value(cfg.status) == "online")


def _healthy_node(node: Node) -> bool:
    return bool(
        node.node_type == NodeType.EXIT
        and getattr(node, "retired_at", None) is None
        and bool(getattr(node, "show_to_users", True))
        and _enum_value(node.status) == "online"
    )


def _rewrite_filename(value: Any, mode: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return value
    if "." in text:
        stem, ext = text.rsplit(".", 1)
        return f"{stem}-{mode}.{ext}"
    return f"{text}-{mode}"


def _delivery_file_selector(node_id: int, mode: str) -> int:
    """Return an HTML-only selector which can distinguish Both-mode files.

    Public JSON keeps the real positive Node ID. Only rendered download hrefs
    receive a negative selector, avoiding collisions with real database IDs.
    """

    node_id = int(node_id)
    if node_id <= 0 or mode not in {"direct", "tunnel"}:
        return node_id
    return -(node_id * 2 + (1 if mode == "tunnel" else 0))


def _decode_delivery_file_selector(value: int) -> tuple[int, str] | None:
    value = int(value)
    if value >= 0:
        return None
    encoded = -value
    if encoded % 2:
        return (encoded - 1) // 2, "tunnel"
    return encoded // 2, "direct"


def _rewrite_item_endpoint(
    ad: Any,
    db: Session,
    node: Node,
    protocol: str,
    item: dict[str, Any],
    *,
    mode: str,
    tunnel: Tunnel | None = None,
) -> dict[str, Any] | None:
    result = dict(item)
    protocol = str(protocol or "").strip().lower()

    if mode == "direct":
        if not _node_protocol_runtime_ready(db, node, protocol):
            return None
        host = ad._node_host(node)
        port = None if protocol == "l2tp" else ad._port(db, node.id, protocol)
    else:
        if tunnel is None:
            return None
        usable = {int(row.id): row for row in ad._delivery_active_tunnels(db, node)}
        tunnel = usable.get(int(tunnel.id))
        if tunnel is None or not _node_protocol_runtime_ready(db, node, protocol):
            return None
        iran = db.get(Node, tunnel.iran_node_id)
        if not iran or iran.node_type != NodeType.IRAN or getattr(iran, "retired_at", None):
            return None
        host = ad._node_host(iran)
        if protocol == "l2tp":
            from .routers.tunnels import _l2tp_primary_tunnel_id

            if _l2tp_primary_tunnel_id(db, tunnel.iran_node_id) != int(tunnel.id):
                return None
            port = None
        else:
            base = ad._TUNNEL_PUBLIC_PORT_BASE.get(protocol)
            if base is None:
                return None
            port = int(base) + int(node.id)
            if not 1 <= port <= 65535:
                return None

    result["server"] = host
    result["server_ip"] = host
    if port is not None:
        result["port"] = int(port)

    if protocol == "openvpn" and result.get("config") and port is not None:
        result["config"] = re.sub(
            r"(?m)^remote\s+\S+\s+\d+\s*$",
            f"remote {host} {port}",
            str(result["config"]),
            count=1,
        )
    elif protocol == "wireguard" and result.get("config") and port is not None:
        result["config"] = re.sub(
            r"(?m)^Endpoint\s*=\s*.+$",
            f"Endpoint = {host}:{port}",
            str(result["config"]),
            count=1,
        )
    elif protocol == "v2ray" and result.get("uri") and port is not None:
        uri = re.sub(
            r"^(vless://[^@]+@)[^:/?#]+:\d+",
            rf"\g<1>{host}:{port}",
            str(result["uri"]),
            count=1,
        )
        suffix = "Tunnel" if mode == "tunnel" else "Direct"
        if "#" in uri:
            uri = uri.rsplit("#", 1)[0] + "#" + uri.rsplit("#", 1)[1] + f"-{suffix}"
        result["uri"] = uri

    suffix = "Tunnel" if mode == "tunnel" else "Direct"
    result["delivery_mode"] = mode
    result["delivery_label"] = suffix
    result["node"] = f"{node.name} • {suffix}"
    if result.get("filename"):
        result["filename"] = _rewrite_filename(result.get("filename"), mode)
    return result


def compile_explicit_stored_info(ad: Any, db: Session, sub: Subscription) -> dict[str, Any]:
    selected_protocols = {
        str(row[0]).strip().lower()
        for row in db.query(SubscriptionProtocol.protocol)
        .filter(SubscriptionProtocol.subscription_id == sub.id)
        .all()
    }
    targets = explicit_memberships(db, sub.id)
    modes_by_node: dict[int, SubscriptionNodeDeliveryMode] = {
        int(membership.node_id): mode for membership, mode in targets
    }

    data: list[dict[str, Any]] = []
    current_l2tp_psk: str | None = None
    credentials = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.is_active.is_(True),
        )
        .order_by(ProtocolCredential.id.asc())
        .all()
    )

    for cred in credentials:
        protocol = str(cred.protocol or "").strip().lower()
        if protocol not in selected_protocols:
            continue
        capability = capability_map().get(protocol) or {}
        if not capability.get("account_delivery_ready"):
            continue
        payload = ad._dec(cred.config_text_encrypted)
        if not payload:
            continue
        source_items = payload if isinstance(payload, list) else [payload]
        output_items: list[dict[str, Any]] = []

        for raw in source_items:
            if not isinstance(raw, dict):
                continue
            try:
                node_id = int(raw.get("node_id") or 0)
            except (TypeError, ValueError):
                continue
            mode = modes_by_node.get(node_id)
            if mode is None:
                continue
            node = db.get(Node, node_id)
            if not node or not _healthy_node(node):
                continue

            if mode.tunnel_enabled:
                tunnel = db.get(Tunnel, mode.tunnel_id) if mode.tunnel_id else None
                item = _rewrite_item_endpoint(
                    ad, db, node, protocol, raw, mode="tunnel", tunnel=tunnel
                )
                if item:
                    output_items.append(item)

            if mode.direct_enabled:
                item = _rewrite_item_endpoint(ad, db, node, protocol, raw, mode="direct")
                if item:
                    output_items.append(item)

        if not output_items:
            continue
        if protocol == "l2tp":
            if current_l2tp_psk is None:
                current_l2tp_psk = ad.get_or_create_l2tp_psk(db)
            for item in output_items:
                item["psk"] = current_l2tp_psk

        data.append(
            {
                "protocol": cred.protocol,
                "username": cred.username,
                "items": output_items,
            }
        )

    return {
        "subscription_id": sub.id,
        "credentials": data,
        "downloads": ad.DOWNLOADS,
        "subscription_link": ad._share_url(db, sub),
        "account": {
            "username": sub.account_username,
            "password": sub.account_password_encrypted,
        },
        "delivery_policy": "explicit",
    }


def install_account_delivery_hooks() -> None:
    """Install a narrow compatibility bridge into the existing delivery engine.

    Legacy subscriptions keep byte-for-byte legacy selection behavior. Explicit
    subscriptions reuse the same provisioning functions and credentials but use
    policy-aware node selection and a policy-aware read-time compiler.
    """

    from .routers import account_delivery as ad

    if getattr(ad, "_subscription_delivery_policy_v1_installed", False):
        return

    legacy_nodes = ad._nodes
    legacy_stored_info = ad._stored_info
    legacy_credential_sections = ad._credential_sections
    legacy_find_item = ad._find_item
    legacy_installed_node_sync = ad.sync_installed_node_to_subscriptions

    def policy_nodes(db: Session, sub: Subscription) -> list[Node]:
        if not is_explicit_policy(db, sub.id):
            return legacy_nodes(db, sub)
        return explicit_nodes(db, sub)

    def policy_stored_info(db: Session, sub: Subscription) -> dict[str, Any]:
        if not is_explicit_policy(db, sub.id):
            return legacy_stored_info(db, sub)
        return compile_explicit_stored_info(ad, db, sub)

    def policy_credential_sections(payload: dict[str, Any], token: str) -> str:
        if payload.get("delivery_policy") != "explicit":
            return legacy_credential_sections(payload, token)

        rendered = dict(payload)
        rendered_credentials: list[dict[str, Any]] = []

        for credential in payload.get("credentials", []):
            current = dict(credential)
            protocol = str(current.get("protocol") or "").strip().lower()
            rendered_items: list[dict[str, Any]] = []

            for item in current.get("items", []):
                if not isinstance(item, dict):
                    continue
                rendered_item = dict(item)
                mode = str(rendered_item.get("delivery_mode") or "").strip().lower()
                if protocol in {"openvpn", "wireguard"} and mode in {"direct", "tunnel"}:
                    try:
                        source_node_id = int(rendered_item.get("node_id") or 0)
                    except (TypeError, ValueError):
                        source_node_id = 0
                    rendered_item["node_id"] = _delivery_file_selector(source_node_id, mode)
                rendered_items.append(rendered_item)

            current["items"] = rendered_items
            rendered_credentials.append(current)

        rendered["credentials"] = rendered_credentials
        return legacy_credential_sections(rendered, token)

    def policy_find_item(
        payload: dict[str, Any],
        protocol: str,
        node_id: int,
    ) -> dict[str, Any]:
        decoded = _decode_delivery_file_selector(node_id)
        if payload.get("delivery_policy") != "explicit" or decoded is None:
            return legacy_find_item(payload, protocol, node_id)

        source_node_id, wanted_mode = decoded
        for credential in payload.get("credentials", []):
            if str(credential.get("protocol") or "").strip().lower() != str(protocol or "").strip().lower():
                continue
            for item in credential.get("items", []):
                if not isinstance(item, dict):
                    continue
                try:
                    item_node_id = int(item.get("node_id") or 0)
                except (TypeError, ValueError):
                    continue
                if (
                    item_node_id == source_node_id
                    and str(item.get("delivery_mode") or "").strip().lower() == wanted_mode
                ):
                    return item
        return legacy_find_item(payload, protocol, node_id)

    async def policy_installed_node_sync(db: Session, node: Node) -> dict[str, Any]:
        return await legacy_installed_node_sync(
            autosync_legacy_only_session(db),
            node,
        )

    ad._nodes = policy_nodes
    ad._stored_info = policy_stored_info
    ad._credential_sections = policy_credential_sections
    ad._find_item = policy_find_item
    ad.sync_installed_node_to_subscriptions = policy_installed_node_sync
    ad._subscription_delivery_policy_v1_installed = True
