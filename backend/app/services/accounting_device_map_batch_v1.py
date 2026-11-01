from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Node, NodeType, ProtocolCredential, SubscriptionNode
from ..protocol_identity import is_openvpn_central_pki_enabled
from ..quota_models import QuotaDevice
from . import quota_node_sync as canonical


_CACHE_KEY = "twinpanel_accounting_device_map_batch_v1"


def _candidate_node_ids(db: Session) -> list[int]:
    return [
        int(row[0])
        for row in (
            db.query(Node.id)
            .filter(
                Node.retired_at.is_(None),
                or_(Node.node_type == NodeType.EXIT, Node.agent_url == "local://core"),
            )
            .order_by(Node.id.asc())
            .all()
        )
    ]


def _items_by_node(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    mapped: dict[int, dict[str, Any]] = {}
    for item in items:
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            continue
        if node_id > 0:
            # Preserve canonical first-match semantics from
            # _credential_item_for_node().
            mapped.setdefault(node_id, item)
    return mapped


def _stored_identity(
    credential: ProtocolCredential,
    *,
    source_protocol: str,
    item: dict[str, Any] | None,
) -> str:
    item = item or {}
    candidates: list[Any] = [
        item.get("telemetry_identity"),
        item.get("username"),
        getattr(credential, "username", None),
    ]
    if source_protocol == "wireguard":
        candidates.insert(0, item.get("address"))
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def build_accounting_devices_by_node(db: Session) -> dict[int, list[dict[str, Any]]]:
    """Build every accounting node's device map in one database pass.

    The legacy builder is correct but intentionally node-oriented: each call
    reloads every active ProtocolCredential, decrypts its payload and performs
    quota-device/legacy-membership lookups. The accounting worker calls that
    builder once per node, turning a full sweep into O(nodes * credentials).

    This batch builder preserves the exact mapping, dedupe, identity and lazy
    QuotaDevice-backfill rules while loading each source set once per worker
    Session. The dedicated accounting worker creates a fresh Session for every
    reconcile pass, so this cache never crosses accounting sweeps.
    """

    node_ids = _candidate_node_ids(db)
    result: dict[int, list[dict[str, Any]]] = {node_id: [] for node_id in node_ids}
    if not node_ids:
        return result

    candidate_nodes = set(node_ids)
    openvpn_central_pki_enabled = is_openvpn_central_pki_enabled(db)

    credentials = (
        db.query(ProtocolCredential)
        .filter(ProtocolCredential.is_active.is_(True))
        .order_by(
            ProtocolCredential.subscription_id.asc(),
            ProtocolCredential.id.asc(),
        )
        .all()
    )
    if not credentials:
        return result

    decoded_by_credential: dict[int, dict[int, dict[str, Any]]] = {}
    legacy_subscription_ids: set[int] = set()
    relevant_subscription_ids: set[int] = set()

    for credential in credentials:
        subscription_id = int(credential.subscription_id)
        relevant_subscription_ids.add(subscription_id)
        items = canonical._decoded_credential_items(credential)
        by_node = _items_by_node(items)
        decoded_by_credential[int(credential.id)] = by_node
        if not by_node:
            legacy_subscription_ids.add(subscription_id)

    legacy_nodes_by_subscription: dict[int, set[int]] = {
        subscription_id: set() for subscription_id in legacy_subscription_ids
    }
    if legacy_subscription_ids:
        rows = (
            db.query(SubscriptionNode.subscription_id, SubscriptionNode.node_id)
            .filter(SubscriptionNode.subscription_id.in_(legacy_subscription_ids))
            .all()
        )
        for subscription_id, node_id in rows:
            legacy_nodes_by_subscription.setdefault(int(subscription_id), set()).add(
                int(node_id)
            )

    devices_by_key: dict[tuple[int, str], QuotaDevice] = {}
    if relevant_subscription_ids:
        devices = (
            db.query(QuotaDevice)
            .filter(QuotaDevice.subscription_id.in_(relevant_subscription_ids))
            .order_by(QuotaDevice.id.asc())
            .all()
        )
        for device in devices:
            key = (int(device.subscription_id), str(device.protocol or "").strip().lower())
            devices_by_key.setdefault(key, device)

    seen_by_node: dict[int, set[tuple[int, str]]] = {
        node_id: set() for node_id in node_ids
    }

    for credential in credentials:
        source_protocol = str(credential.protocol or "").strip().lower()
        protocol = canonical._PROTOCOL_TO_QUOTA.get(source_protocol)
        if protocol is None:
            continue

        subscription_id = int(credential.subscription_id)
        by_node = decoded_by_credential.get(int(credential.id), {})
        if by_node:
            membership = candidate_nodes.intersection(by_node)
        else:
            membership = candidate_nodes.intersection(
                legacy_nodes_by_subscription.get(subscription_id, set())
            )
        if not membership:
            continue

        device_key = (subscription_id, source_protocol)
        device = devices_by_key.get(device_key)
        if device is None:
            device = QuotaDevice(
                subscription_id=subscription_id,
                protocol=source_protocol,
                device_key=f"subscription:{subscription_id}:{source_protocol}",
                credential_public_hash=f"legacy-backfill-{subscription_id}-{source_protocol}",
                status="active",
            )
            db.add(device)
            db.flush()
            devices_by_key[device_key] = device

        # Preserve canonical behavior: the oldest matching device wins and an
        # inactive canonical device suppresses telemetry rather than being
        # silently replaced by a new active row.
        if str(device.status or "").strip().lower() != "active":
            continue

        for node_id in sorted(membership):
            dedupe_key = (subscription_id, protocol)
            if dedupe_key in seen_by_node[node_id]:
                continue
            seen_by_node[node_id].add(dedupe_key)

            stored_identity = _stored_identity(
                credential,
                source_protocol=source_protocol,
                item=by_node.get(node_id),
            )
            legacy_identity = (
                str(getattr(credential, "username", None) or "").strip()
                or f"mv-{subscription_id}@twinpanel"
            )
            identity = stored_identity or legacy_identity

            result[node_id].append(
                {
                    "device_id": int(device.id),
                    "credential_id": int(credential.id),
                    "subscription_id": subscription_id,
                    "protocol": protocol,
                    "identity": identity,
                    "telemetry_identity": canonical._runtime_identity(
                        protocol=protocol,
                        subscription_id=subscription_id,
                        node_id=node_id,
                        fallback_identity=identity,
                        openvpn_central_pki_enabled=openvpn_central_pki_enabled,
                    ),
                }
            )

    return result


def build_node_devices_cached(db: Session, node_id: int):
    cache = db.info.get(_CACHE_KEY)
    if cache is None:
        cache = build_accounting_devices_by_node(db)
        db.info[_CACHE_KEY] = cache
    return list(cache.get(int(node_id), ()))


def install_accounting_device_batch_cache() -> None:
    """Patch only the dedicated accounting collectors' imported builder refs."""

    from . import modern_quota_runtime_v257 as modern
    from . import singbox_native_accounting_v265 as singbox

    modern.build_node_devices = build_node_devices_cached
    singbox.build_node_devices = build_node_devices_cached
    print(
        "TWINPANEL_ACCOUNTING_DEVICE_MAP_BATCH_V1_ACTIVE "
        "scope=per-reconcile-session semantics=unchanged",
        flush=True,
    )


__all__ = [
    "build_accounting_devices_by_node",
    "build_node_devices_cached",
    "install_accounting_device_batch_cache",
]
