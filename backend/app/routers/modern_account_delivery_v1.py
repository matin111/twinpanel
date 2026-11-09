from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeProtocolConfig,
    ProtocolCredential,
    Subscription,
    User,
)
from ..services.hard_async_timeout import await_hard_timeout
from ..services.provisioning_guard import SubscriptionProvisioningGuard


router = APIRouter(dependencies=[Depends(require_admin)])

CLASSIC_NODE_FLAGS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}
SINGBOX_ACCOUNT_PROTOCOLS = frozenset(
    {
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
        "socks5",
    }
)
SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS = frozenset({"naive", "shadowtls"})
STANDALONE_ACCOUNT_PROTOCOLS = frozenset(
    {
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    }
)
MODERN_ACCOUNT_PROTOCOLS = SINGBOX_ACCOUNT_PROTOCOLS | STANDALONE_ACCOUNT_PROTOCOLS

# Classic protocol drivers still keep their per-protocol hard limit. Modern
# protocols have a per-node hard limit so one slow server can never prevent
# later servers from being attempted for the same protocol.
DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS = 45.0
PROTOCOL_PROVISION_TIMEOUT_SECONDS = {
    "v2ray": 30.0,
    "openvpn": 60.0,
}
MODERN_NODE_PROVISION_TIMEOUT_SECONDS = 45.0
QUOTA_SYNC_TIMEOUT_SECONDS = 20.0


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _modern_runtime_config(
    db: Session,
    node: Node,
    protocol: str,
) -> NodeProtocolConfig | None:
    if protocol not in MODERN_ACCOUNT_PROTOCOLS:
        return None
    return (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )


def _modern_runtime_ready(
    db: Session,
    node: Node,
    protocol: str,
) -> bool:
    cfg = _modern_runtime_config(db, node, protocol)
    return bool(cfg and _status_value(cfg.status) == "online")


def _get_credential(
    db: Session,
    subscription_id: int,
    protocol: str,
) -> ProtocolCredential:
    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == subscription_id,
            ProtocolCredential.protocol == protocol,
        )
        .first()
    )
    if cred is None:
        cred = ProtocolCredential(
            subscription_id=subscription_id,
            protocol=protocol,
        )
        db.add(cred)
        db.flush()
    return cred


def _stored_singbox_secret(ad: Any, cred: ProtocolCredential, protocol: str):
    from ..singbox_subscription_accounts import SingBoxAccountError, secret_from_dict

    decoded = ad._dec(cred.secret_encrypted)
    if not isinstance(decoded, dict):
        return None
    try:
        secret = secret_from_dict(decoded)
    except (SingBoxAccountError, TypeError, ValueError):
        return None
    return secret if secret.protocol == protocol else None


def _singbox_secret(
    ad: Any,
    cred: ProtocolCredential,
    protocol: str,
    sub: Subscription,
):
    from ..singbox_subscription_accounts import SingBoxAccountSecret, new_account_secret

    if protocol == "socks5":
        # Preserve live legacy credentials until an explicit, verified
        # migration. Never silently break already-issued proxy profiles.
        stored = _stored_singbox_secret(ad, cred, protocol)
        if stored is not None:
            return stored
        # New SOCKS5 credentials use the same account-level login as
        # Cisco/L2TP; the eight-digit password is generated centrally,
        # not independently on each Exit.
        username = str(sub.account_username or "").strip()
        password = str(sub.account_password_encrypted or "")
        if not username or not password:
            raise RuntimeError("SOCKS5_SUBSCRIPTION_ACCOUNT_CREDENTIALS_MISSING")
        return SingBoxAccountSecret(
            protocol=protocol,
            username=username,
            password=password,
        )

    if protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
        username = str(sub.account_username or "").strip()
        password = str(sub.account_password_encrypted or "")
        if not username or not password:
            raise RuntimeError(f"{protocol} subscription credential is incomplete")
        return SingBoxAccountSecret(
            protocol=protocol,
            username=username,
            password=password,
        )

    stored = _stored_singbox_secret(ad, cred, protocol)
    if stored is not None:
        return stored
    return new_account_secret(protocol, sub.id)


async def _remove_singbox_identity(conn: Any, protocol: str, username: str) -> None:
    from ..singbox_subscription_accounts import _commit_account_config, _mutation_script

    username = str(username or "").strip()
    if not username:
        return
    await _commit_account_config(
        conn,
        _mutation_script(protocol, username, None),
    )


def _stored_standalone_secret(ad: Any, cred: ProtocolCredential, protocol: str):
    from ..standalone_subscription_accounts import (
        StandaloneAccountError,
        secret_from_dict,
    )

    decoded = ad._dec(cred.secret_encrypted)
    if not isinstance(decoded, dict):
        return None
    try:
        secret = secret_from_dict(decoded)
    except (StandaloneAccountError, TypeError, ValueError):
        return None
    return secret if secret.protocol == protocol else None


def _credential_identity(protocol: str, secret: Any) -> str:
    if protocol == "amneziawg" and getattr(secret, "client_public_key", None):
        return str(secret.client_public_key)
    if protocol == "sudoku" and getattr(secret, "sudoku_port", None):
        return f"sudoku-sub-{int(secret.subscription_id)}:{int(secret.sudoku_port)}"
    return str(getattr(secret, "username", "") or "")


def _tag_token(value: Any, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    token = re.sub(r"-{2,}", "-", token).strip("-._")
    return token[:48] or fallback


def _client_tag_base(node: Node, protocol: str, username: str) -> str:
    user_token = _tag_token(username, "user")
    protocol_token = _tag_token(protocol, "protocol")
    node_token = _tag_token(getattr(node, "name", None), "node")
    node_id = int(getattr(node, "id", 0) or 0)
    return f"{user_token}-{protocol_token}-{node_token}-n{node_id}"


def _bind_unique_client_tags(
    item: dict[str, Any],
    *,
    node: Node,
    protocol: str,
    username: str,
) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
        return item

    raw_config = str(item.get("config") or "").strip()
    try:
        config = json.loads(raw_config)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{protocol} client config is invalid") from exc

    outbounds = config.get("outbounds") if isinstance(config, dict) else None
    if not isinstance(outbounds, list):
        raise RuntimeError(f"{protocol} client outbounds are missing")

    base_tag = _client_tag_base(node, protocol, username)
    route = config.get("route")
    if not isinstance(route, dict):
        route = {}
        config["route"] = route

    if protocol == "naive":
        candidates = [
            outbound
            for outbound in outbounds
            if isinstance(outbound, dict)
            and str(outbound.get("type") or "").strip().lower() == "naive"
        ]
        if len(candidates) != 1:
            raise RuntimeError("naive client outbound is ambiguous")
        candidates[0]["tag"] = base_tag
        route["final"] = base_tag

        public_outbound = item.get("outbound")
        if isinstance(public_outbound, dict):
            public_outbound["tag"] = base_tag

    else:
        proxies = [
            outbound
            for outbound in outbounds
            if isinstance(outbound, dict)
            and str(outbound.get("type") or "").strip().lower() == "shadowsocks"
            and "detour" in outbound
        ]
        transports = [
            outbound
            for outbound in outbounds
            if isinstance(outbound, dict)
            and str(outbound.get("type") or "").strip().lower() == "shadowtls"
        ]
        if len(proxies) != 1 or len(transports) != 1:
            raise RuntimeError("shadowtls client chain is ambiguous")

        transport_tag = f"{base_tag}-transport"
        proxies[0]["tag"] = base_tag
        proxies[0]["detour"] = transport_tag
        transports[0]["tag"] = transport_tag
        route["final"] = base_tag

        public_outbound = item.get("outbound")
        if isinstance(public_outbound, dict):
            public_outbound["tag"] = transport_tag

    item["config"] = json.dumps(config, ensure_ascii=False, indent=2)
    return item


async def _provision_modern_protocol(
    ad: Any,
    db: Session,
    sub: Subscription,
    protocol: str,
    nodes: list[Node],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    cred = _get_credential(db, sub.id, protocol)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    previous_secret = None
    if protocol in SINGBOX_ACCOUNT_PROTOCOLS:
        from ..singbox_subscription_accounts import apply_account, secret_to_dict

        previous_secret = _stored_singbox_secret(ad, cred, protocol)
        secret = _singbox_secret(ad, cred, protocol, sub)
        standalone = False
    else:
        from ..standalone_subscription_accounts import (
            apply_account,
            new_account_secret,
            secret_to_dict,
        )

        secret = _stored_standalone_secret(ad, cred, protocol)
        standalone = True

    for node in nodes:
        cfg = _modern_runtime_config(db, node, protocol)
        if cfg is None or _status_value(cfg.status) != "online":
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": "Protocol runtime is not online on this server",
                }
            )
            continue

        async def provision_node() -> dict[str, Any]:
            nonlocal secret
            conn = None
            try:
                conn = await ad.ssh_connect_saved(node, db)
                if standalone:
                    if secret is None:
                        secret = await new_account_secret(conn, protocol, sub.id)
                    port = int(cfg.port or 0)
                    if not 1 <= port <= 65535:
                        raise RuntimeError(f"{protocol} runtime port is unavailable")
                    item = await apply_account(conn, node, secret, port)
                    if protocol == "amneziawg":
                        from ..amneziawg_egress_v221 import ensure_amneziawg_egress

                        egress = await ensure_amneziawg_egress(conn)
                        item["egress_contract"] = int(egress["contract"])
                else:
                    previous_username = str(
                        getattr(previous_secret, "username", "") or ""
                    ).strip()
                    current_username = str(
                        getattr(secret, "username", "") or ""
                    ).strip()
                    if (
                        protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS
                        and previous_username
                        and previous_username != current_username
                    ):
                        await _remove_singbox_identity(
                            conn,
                            protocol,
                            previous_username,
                        )
                    item = await apply_account(conn, node, secret)
                    if protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                        item = _bind_unique_client_tags(
                            item,
                            node=node,
                            protocol=protocol,
                            username=current_username,
                        )
                return item
            finally:
                if conn is not None:
                    conn.close()
                    await conn.wait_closed()

        try:
            item = await await_hard_timeout(
                provision_node(),
                timeout_seconds=MODERN_NODE_PROVISION_TIMEOUT_SECONDS,
                wait_for_cancel=True,
            )
            items.append(item)
        except asyncio.TimeoutError:
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": (
                        "Provisioning timeout on this server after "
                        f"{int(MODERN_NODE_PROVISION_TIMEOUT_SECONDS)} seconds"
                    ),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": str(exc)[:800],
                }
            )

    if items and secret is not None:
        cred.username = _credential_identity(protocol, secret)
        cred.secret_encrypted = ad._enc(secret_to_dict(secret))
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    return items, errors


async def _provision_classic_protocol(
    ad: Any,
    db: Session,
    sub: Subscription,
    user: User,
    protocol: str,
    nodes: list[Node],
    username: str,
    password: str,
    xray_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    flag = CLASSIC_NODE_FLAGS[protocol]
    node_timeout = max(
        1.0,
        float(
            PROTOCOL_PROVISION_TIMEOUT_SECONDS.get(
                protocol,
                DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS,
            )
        ),
    )

    for node in nodes:
        if not bool(getattr(node, flag, False)):
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": "Protocol is not enabled on this server",
                }
            )
            continue

        async def provision_node() -> dict[str, Any]:
            if protocol == "cisco":
                return await ad._cisco(db, node, sub, user, username, password)
            if protocol == "openvpn":
                return await ad._openvpn(db, node, sub, user)
            if protocol == "wireguard":
                return await ad._wireguard(db, node, sub, user)
            if protocol == "l2tp":
                return await ad._l2tp(db, node, sub, user, username, password)
            return await ad._xray(db, node, sub, user, xray_id)

        try:
            item = await await_hard_timeout(
                provision_node(),
                timeout_seconds=node_timeout,
                wait_for_cancel=True,
            )
            items.append(item)
        except asyncio.TimeoutError:
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": (
                        "Provisioning timeout on this server after "
                        f"{int(node_timeout)} seconds"
                    ),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": str(exc)[:800],
                }
            )

    if items:
        cred = _get_credential(db, sub.id, protocol)
        cred.username = username if protocol in {"cisco", "l2tp"} else None
        cred.secret_encrypted = (
            ad._enc({"password": password})
            if protocol in {"cisco", "l2tp"}
            else None
        )
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    return items, errors


async def _provision_new_singbox_node_batches(
    ad: Any,
    db: Session,
    sub: Subscription,
    protocols: list[str],
    nodes: list[Node],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]] | None:
    """Provision a *new* account's sing-box protocols once per node.

    Never touches imported or partially provisioned subscriptions: any existing
    sing-box credential forces the original per-protocol path. Each node has a
    single config validation and restart, instead of one per user/protocol.
    """
    selected = list(dict.fromkeys(p for p in protocols if p in SINGBOX_ACCOUNT_PROTOCOLS))
    if len(selected) < 2:
        return None
    if db.query(ProtocolCredential.id).filter(
        ProtocolCredential.subscription_id == sub.id,
        ProtocolCredential.protocol.in_(selected),
    ).first() is not None:
        return None

    from ..singbox_subscription_accounts import apply_accounts_batch, secret_to_dict

    credentials = {p: _get_credential(db, sub.id, p) for p in selected}
    secrets = {p: _singbox_secret(ad, credentials[p], p, sub) for p in selected}
    items_by_protocol: dict[str, list[dict[str, Any]]] = {p: [] for p in selected}
    errors: list[dict[str, str]] = []

    for node in nodes:
        ready = []
        for p in selected:
            cfg = _modern_runtime_config(db, node, p)
            if cfg is not None and _status_value(cfg.status) == "online":
                ready.append(p)
            else:
                errors.append({
                    "protocol": p, "node": str(node.name),
                    "error": "Protocol runtime is not online on this server",
                })
        if not ready:
            continue

        async def apply_node_batch() -> list[dict[str, Any]]:
            conn = None
            try:
                conn = await ad.ssh_connect_saved(node, db)
                return await apply_accounts_batch(
                    conn, node, [secrets[p] for p in ready]
                )
            finally:
                if conn is not None:
                    conn.close()
                    await conn.wait_closed()

        try:
            # A single bounded operation per node; never retry with N separate
            # restarts after failure. Convergence can retry missing pairs later.
            delivered = await await_hard_timeout(
                apply_node_batch(),
                timeout_seconds=180.0,
                wait_for_cancel=True,
            )
            if len(delivered) != len(ready):
                raise RuntimeError("sing-box node batch item count mismatch")
            for p, item in zip(ready, delivered):
                if p in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                    item = _bind_unique_client_tags(
                        item, node=node, protocol=p, username=secrets[p].username
                    )
                items_by_protocol[p].append(item)
        except asyncio.TimeoutError:
            for p in ready:
                errors.append({
                    "protocol": p, "node": str(node.name),
                    "error": "Sing-box node batch timed out",
                })
        except Exception as exc:
            for p in ready:
                errors.append({
                    "protocol": p, "node": str(node.name),
                    "error": f"Sing-box node batch failed: {str(exc)[:700]}",
                })

    for p, items in items_by_protocol.items():
        if not items:
            continue
        cred = credentials[p]
        cred.username = _credential_identity(p, secrets[p])
        cred.secret_encrypted = ad._enc(secret_to_dict(secrets[p]))
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    return items_by_protocol, errors


async def _provision_account_v1_locked(
    subscription_id: int,
    db: Session,
    *,
    prefer_new_singbox_batch: bool = False,
):
    from . import account_delivery as ad

    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    user = db.get(User, sub.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    nodes = [
        node
        for node in ad._nodes(db, sub)
        if getattr(node, "retired_at", None) is None
    ]
    protocols = [str(value).strip().lower() for value in ad._protocols(db, sub)]

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="برای این اشتراک هیچ سرور معتبری در پنل وجود ندارد",
        )
    if not protocols:
        raise HTTPException(status_code=409, detail="برای اشتراک پروتکلی انتخاب نشده است")

    unsupported = [
        protocol
        for protocol in protocols
        if protocol not in CLASSIC_NODE_FLAGS
        and protocol not in MODERN_ACCOUNT_PROTOCOLS
    ]
    if unsupported:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "پروتکل Account Driver معتبر ندارد",
                "protocols": unsupported,
            },
        )

    username = sub.account_username or ad._safe_username(sub, user)
    if not sub.account_username:
        sub.account_username = username
    password = sub.account_password_encrypted or ad._numeric_secret(8)
    if not sub.account_password_encrypted:
        sub.account_password_encrypted = password
    xray_id = str(uuid.uuid4())

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    pending_protocols: list[str] = []
    # Central Exits are already reconciled by one node-level service-family
    # worker. Do not start a *second*, per-subscriber Sudoku listener here.
    # This guard is before both the serial and parallel modern account drivers.
    from ..services.sudoku_central_delivery_v1 import (
        has_published_central_sudoku_owner,
        ready_central_sudoku_items,
    )
    central_sudoku_owner = (
        "sudoku" in protocols
        and has_published_central_sudoku_owner(db, nodes)
    )
    grouped: dict[str, list[dict[str, Any]]] | None = None
    if prefer_new_singbox_batch:
        batched = await _provision_new_singbox_node_batches(
            ad, db, sub, protocols, nodes,
        )
        if batched is not None:
            grouped, grouped_errors = batched
            errors.extend(grouped_errors)

    for protocol in protocols:
        if protocol == "sudoku" and central_sudoku_owner:
            # Shared identities are generated by the central 30-second desired
            # state convergence, not by an HTTP-scoped SSH/daemon worker.
            cred = _get_credential(db, sub.id, "sudoku")
            stored = ad._autosync_credential_items(cred)
            shared = ready_central_sudoku_items(db, stored)
            if shared:
                results.append({
                    "protocol": "sudoku",
                    "username": cred.username,
                    "items": shared,
                })
            else:
                pending_protocols.append("sudoku")
            continue
        if grouped is not None and protocol in grouped:
            items = grouped[protocol]
            if items:
                cred = _get_credential(db, sub.id, protocol)
                results.append({
                    "protocol": protocol,
                    "username": cred.username,
                    "items": items,
                })
            continue
        if protocol in MODERN_ACCOUNT_PROTOCOLS:
            items, protocol_errors = await _provision_modern_protocol(
                ad,
                db,
                sub,
                protocol,
                nodes,
            )
        else:
            items, protocol_errors = await _provision_classic_protocol(
                ad,
                db,
                sub,
                user,
                protocol,
                nodes,
                username,
                password,
                xray_id,
            )

        errors.extend(protocol_errors)
        if items:
            cred = _get_credential(db, sub.id, protocol)
            results.append(
                {
                    "protocol": protocol,
                    "username": cred.username,
                    "items": items,
                }
            )

    db.commit()

    quota_sync: dict[str, Any] = {"ok": True, "nodes": []}
    if results:
        from ..services.quota_refresh import sync_subscription_quota_nodes

        try:
            quota_sync = await await_hard_timeout(
                sync_subscription_quota_nodes(db, sub.id),
                timeout_seconds=QUOTA_SYNC_TIMEOUT_SECONDS,
                wait_for_cancel=True,
            )
        except asyncio.TimeoutError:
            quota_sync = {
                "ok": False,
                "nodes": [],
                "error": f"Quota sync timeout after {int(QUOTA_SYNC_TIMEOUT_SECONDS)} seconds",
            }
            errors.append(
                {
                    "protocol": "quota",
                    "node": "quota-agent",
                    "error": f"Quota sync timeout after {int(QUOTA_SYNC_TIMEOUT_SECONDS)} seconds",
                }
            )

        if not quota_sync.get("ok") and not any(
            item.get("protocol") == "quota" for item in errors
        ):
            errors.append(
                {
                    "protocol": "quota",
                    "node": "quota-agent",
                    "error": "Quota Agent sync failed",
                }
            )

    if not results and not pending_protocols:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "هیچ اکانتی روی سرورها ساخته نشد",
                "errors": errors,
            },
        )

    payload = ad._public_payload(db, sub)
    payload.update(
        {
            "ok": len(errors) == 0 and not pending_protocols,
            "errors": errors,
            "pending_protocols": pending_protocols,
            "central_reconciliation_pending": bool(pending_protocols),
            "quota": quota_sync,
            "modern_account_driver": 2,
        }
    )
    return payload


@router.post("/v1/subscriptions/{subscription_id}/provision-account")
async def provision_account_v1(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    guard = SubscriptionProvisioningGuard(subscription_id)
    if not guard.acquire():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provisioning_in_progress",
                "message": "Provisioning این اشتراک در حال اجراست؛ درخواست تکراری رد شد",
                "subscription_id": subscription_id,
            },
        )

    try:
        return await _provision_account_v1_locked(subscription_id, db)
    finally:
        guard.release()


async def provision_new_account_fast_v1(subscription_id: int, db: Session):
    """Internal fast-create path; never used by migration backfill workers."""
    guard = SubscriptionProvisioningGuard(subscription_id)
    if not guard.acquire():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provisioning_in_progress",
                "subscription_id": subscription_id,
            },
        )
    try:
        return await _provision_account_v1_locked(
            subscription_id, db, prefer_new_singbox_batch=True,
        )
    finally:
        guard.release()