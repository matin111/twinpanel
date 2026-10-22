from __future__ import annotations

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
STANDALONE_ACCOUNT_PROTOCOLS = frozenset(
    {
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    }
)
MODERN_ACCOUNT_PROTOCOLS = SINGBOX_ACCOUNT_PROTOCOLS | STANDALONE_ACCOUNT_PROTOCOLS


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


def _singbox_secret(ad: Any, cred: ProtocolCredential, protocol: str, subscription_id: int):
    from ..singbox_subscription_accounts import (
        SingBoxAccountError,
        new_account_secret,
        secret_from_dict,
    )

    decoded = ad._dec(cred.secret_encrypted)
    if isinstance(decoded, dict):
        try:
            secret = secret_from_dict(decoded)
            if secret.protocol == protocol:
                return secret
        except (SingBoxAccountError, TypeError, ValueError):
            pass
    return new_account_secret(protocol, subscription_id)


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

    if protocol in SINGBOX_ACCOUNT_PROTOCOLS:
        from ..singbox_subscription_accounts import apply_account, secret_to_dict

        secret = _singbox_secret(ad, cred, protocol, sub.id)
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
            else:
                item = await apply_account(conn, node, secret)
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


@router.post("/v1/subscriptions/{subscription_id}/provision-account")
async def provision_account_v1(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    """Canonical account provisioning bridge for all 15 protocols.

    Classic behavior reuses the established production helpers. All ten Modern
    protocols require a real online NodeProtocolConfig and a real account
    driver; nothing is synthesized when a runtime is absent.
    """

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
    xray_id = str(uuid.uuid4())

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for protocol in protocols:
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

        quota_sync = await sync_subscription_quota_nodes(db, sub.id)
        if not quota_sync.get("ok"):
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
