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
    NodeType,
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

# Creation stays fail-closed, but one unhealthy remote account driver must not
# hold an admin/reseller HTTP request for five minutes. These limits sit above
# SSH connect/login limits and below common reverse-proxy request deadlines.
DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS = 45.0
PROTOCOL_PROVISION_TIMEOUT_SECONDS = {
    "v2ray": 30.0,
    "openvpn": 60.0,
}
TOTAL_PROVISION_TIMEOUT_SECONDS = 120.0
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
            continue

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
                current_username = str(getattr(secret, "username", "") or "").strip()
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
            items.append(item)
        except Exception as exc:
            errors.append(
                {
                    "protocol": protocol,
                    "node": str(node.name),
                    "error": str(exc)[:800],
                }
            )
        finally:
            if conn is not None:
                conn.close()
                await conn.wait_closed()

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

    for node in nodes:
        if not bool(getattr(node, flag, False)):
            continue
        try:
            if protocol == "cisco":
                item = await ad._cisco(db, node, sub, user, username, password)
            elif protocol == "openvpn":
                item = await ad._openvpn(db, node, sub, user)
            elif protocol == "wireguard":
                item = await ad._wireguard(db, node, sub, user)
            elif protocol == "l2tp":
                item = await ad._l2tp(db, node, sub, user, username, password)
            else:
                item = await ad._xray(db, node, sub, user, xray_id)
            items.append(item)
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


async def _provision_account_v1_locked(
    subscription_id: int,
    db: Session,
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
        if node.node_type == NodeType.EXIT
        and getattr(node, "retired_at", None) is None
    ]
    protocols = [str(value).strip().lower() for value in ad._protocols(db, sub)]

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="برای این اشتراک هیچ سرور خروجی معتبری انتخاب نشده است",
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
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TOTAL_PROVISION_TIMEOUT_SECONDS

    for protocol in protocols:
        remaining = deadline - loop.time()
        if remaining <= 0:
            errors.append(
                {
                    "protocol": protocol,
                    "node": "provisioning",
                    "error": (
                        "Provisioning total deadline exceeded before this protocol "
                        f"({int(TOTAL_PROVISION_TIMEOUT_SECONDS)}s)"
                    ),
                }
            )
            break

        protocol_timeout = PROTOCOL_PROVISION_TIMEOUT_SECONDS.get(
            protocol,
            DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS,
        )
        timeout = max(1.0, min(float(protocol_timeout), remaining))

        try:
            if protocol in MODERN_ACCOUNT_PROTOCOLS:
                operation = _provision_modern_protocol(
                    ad,
                    db,
                    sub,
                    protocol,
                    nodes,
                )
            else:
                operation = _provision_classic_protocol(
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
            items, protocol_errors = await await_hard_timeout(
                operation,
                timeout_seconds=timeout,
            )
        except asyncio.TimeoutError:
            errors.append(
                {
                    "protocol": protocol,
                    "node": "provisioning",
                    "error": f"Provisioning timeout after {int(timeout)} seconds",
                }
            )
            continue

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

        remaining = deadline - loop.time()
        if remaining <= 0:
            quota_sync = {
                "ok": False,
                "nodes": [],
                "error": "Provisioning deadline reached before quota sync",
            }
            errors.append(
                {
                    "protocol": "quota",
                    "node": "quota-agent",
                    "error": "Provisioning deadline reached before quota sync",
                }
            )
        else:
            quota_timeout = max(1.0, min(QUOTA_SYNC_TIMEOUT_SECONDS, remaining))
            try:
                quota_sync = await await_hard_timeout(
                    sync_subscription_quota_nodes(db, sub.id),
                    timeout_seconds=quota_timeout,
                )
            except asyncio.TimeoutError:
                quota_sync = {
                    "ok": False,
                    "nodes": [],
                    "error": f"Quota sync timeout after {int(quota_timeout)} seconds",
                }
                errors.append(
                    {
                        "protocol": "quota",
                        "node": "quota-agent",
                        "error": f"Quota sync timeout after {int(quota_timeout)} seconds",
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

    if not results:
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
            "ok": len(errors) == 0,
            "errors": errors,
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
