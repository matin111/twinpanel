from __future__ import annotations

import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    Node,
    NodeType,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    User,
)
from ..plan_template_selection import plan_template_node_ids, plan_template_protocols
from ..protocol_account_registry import CLASSIC_PROTOCOL_KEYS, normalize_protocols
from ..quota_models import QuotaDevice
from ..routers.general_settings import build_subscription_username


# Legacy compatibility map used by older store/reseller call sites. It is no
# longer the authority for subscription creation; create_subscription_core
# accepts every canonical protocol from protocol_account_registry.
PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


def generate_share_code(username: str | None):
    import re

    base = (username or "user").lower()
    base = re.sub(r"[^a-z0-9]+", "", base)

    if len(base) < 3:
        base = "user"

    return f"{base[:12]}-{secrets.token_hex(3)}"


def generate_account_password():
    return str(
        secrets.randbelow(90000000) + 10000000
    )


def _unique_node_ids(values: list[int]) -> list[int]:
    result: list[int] = []
    for raw in values:
        node_id = int(raw)
        if node_id <= 0:
            raise HTTPException(status_code=422, detail="شناسه سرور معتبر نیست")
        if node_id not in result:
            result.append(node_id)
    return result


def create_subscription_core(
    db: Session,
    user_id: int,
    plan_id: int | None,
    traffic_bytes: int,
    duration_days: int,
    node_ids: list[int],
    protocols: list[str],
    username: str | None = None,
    password: str | None = None,
):
    user = db.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=404,
            detail="کاربر فعال پیدا نشد",
        )

    plan = db.get(Plan, plan_id) if plan_id is not None else None

    if plan_id is not None and (not plan or not plan.is_active):
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    try:
        requested_protocols = normalize_protocols(protocols)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # A Plan is a creation template/allow-list only. Runtime desired-state is
    # snapshotted into SubscriptionProtocol and never read live from the Plan.
    if plan is not None:
        allowed_protocols = plan_template_protocols(db, int(plan.id))
        if requested_protocols:
            unavailable = [
                protocol
                for protocol in requested_protocols
                if protocol not in allowed_protocols
            ]
            if unavailable:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "این پروتکل در پلن فعال نیست: "
                        + ", ".join(unavailable)
                    ),
                )
        else:
            requested_protocols = list(allowed_protocols)

    if not requested_protocols:
        raise HTTPException(
            status_code=422,
            detail="حداقل یک پروتکل برای این اشتراک انتخاب کنید",
        )

    all_nodes = (
        db.query(Node)
        .filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    nodes_by_id = {int(node.id): node for node in all_nodes}

    # Server desired-state follows the same template -> snapshot contract.
    # Old plans with no PlanNode rows resolve to every current non-retired node.
    allowed_node_ids = (
        plan_template_node_ids(db, int(plan.id))
        if plan is not None
        else list(nodes_by_id)
    )
    requested_node_ids = _unique_node_ids(node_ids or [])

    if requested_node_ids:
        invalid = [
            node_id
            for node_id in requested_node_ids
            if node_id not in nodes_by_id or node_id not in allowed_node_ids
        ]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=(
                    "این سرور در پلن فعال نیست یا بازنشسته شده است: "
                    + ", ".join(str(value) for value in invalid)
                ),
            )
        selected_node_ids = requested_node_ids
    else:
        selected_node_ids = [
            node_id for node_id in allowed_node_ids if node_id in nodes_by_id
        ]

    nodes = [nodes_by_id[node_id] for node_id in selected_node_ids]
    if not nodes:
        raise HTTPException(
            status_code=422,
            detail="حداقل یک سرور برای این اشتراک انتخاب کنید",
        )

    iran_node = next(
        (
            n for n in nodes
            if n.node_type == NodeType.IRAN
        ),
        None,
    )

    exit_node = next(
        (
            n for n in nodes
            if n.node_type == NodeType.EXIT
        ),
        None,
    )

    if not password:
        password = generate_account_password()

    sub = Subscription(
        user_id=user_id,
        plan_id=(plan.id if plan is not None else None),
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        activation_duration_days=duration_days,
        traffic_limit_bytes=traffic_bytes,
        traffic_used_bytes=0,
        iran_node_id=(iran_node.id if iran_node else None),
        exit_node_id=(exit_node.id if exit_node else None),
        account_username=username,
        account_password_encrypted=password,
        share_code=generate_share_code(username or user.email),
    )

    db.add(sub)
    db.flush()

    if not username:
        username = build_subscription_username(
            db,
            sub.id,
            user_id,
        )
        sub.account_username = username

    for node in nodes:
        db.add(
            SubscriptionNode(
                subscription_id=sub.id,
                node_id=node.id,
            )
        )

    for protocol in requested_protocols:
        db.add(
            SubscriptionProtocol(
                subscription_id=sub.id,
                protocol=protocol,
            )
        )
        db.add(
            QuotaDevice(
                subscription_id=sub.id,
                protocol=protocol,
                device_key=f"subscription:{sub.id}:{protocol}",
                credential_public_hash=f"pending-{sub.id}-{protocol}",
                status="active",
            )
        )

    db.flush()

    # Classic drivers historically start from the subscription username/password
    # and then replace config material during provisioning. Modern drivers own
    # their secret/key formats and must create them inside their real provisioner.
    # V2Ray is different from the username/password classic protocols: a usable
    # credential does not exist until provisioning has produced a real client
    # config. Keeping the placeholder inactive prevents ACTIVE + NO_CONFIG rows
    # from being treated as successfully provisioned.
    for protocol in requested_protocols:
        if protocol not in CLASSIC_PROTOCOL_KEYS:
            continue
        db.add(
            ProtocolCredential(
                subscription_id=sub.id,
                protocol=protocol,
                username=username,
                secret_encrypted=password,
                is_active=(protocol != "v2ray"),
            )
        )

    sub.account_username = username
    sub.account_password_encrypted = password

    db.flush()
    return sub
