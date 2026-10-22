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
from ..protocol_account_registry import normalize_protocols, plan_protocols
from ..quota_models import QuotaDevice
from ..routers.general_settings import build_subscription_username


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

    # TWINPANEL_GLOBAL_NODES_FOR_ALL_SUBSCRIPTIONS_V1
    # Node selection is infrastructure-wide.
    # Every subscription belongs to every Node.
    # node_ids from callers are kept only for API compatibility
    # and no longer restrict the subscription.
    nodes = (
        db.query(Node)
        .filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )

    if not requested_protocols and plan is not None:
        requested_protocols = plan_protocols(db, plan)

    if not requested_protocols:
        raise HTTPException(
            status_code=422,
            detail="حداقل یک پروتکل برای اشتراک انتخاب کنید",
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
        # FIRST USE
        starts_at=None,
        expires_at=None,
        activation_duration_days=duration_days,
        traffic_limit_bytes=traffic_bytes,
        traffic_used_bytes=0,
        iran_node_id=(
            iran_node.id
            if iran_node
            else None
        ),
        exit_node_id=(
            exit_node.id
            if exit_node
            else None
        ),
        account_username=username,
        account_password_encrypted=password,
        share_code=generate_share_code(
            username or user.email
        ),
    )

    db.add(sub)
    db.flush()

    # TWINPANEL_USERNAME_TEMPLATE_CENTRAL_V3
    # Apply admin configured username pattern after subscription id exists.
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

        # QuotaDevice is the stable accounting identity. Runtime-specific
        # provisioning replaces the pending public hash only after a real
        # subscriber identity has been installed on the Exit node.
        db.add(
            QuotaDevice(
                subscription_id=sub.id,
                protocol=protocol,
                device_key=(
                    f"subscription:{sub.id}:{protocol}"
                ),
                credential_public_hash=(
                    f"pending-{sub.id}-{protocol}"
                ),
                status="active",
            )
        )

    db.flush()

    # Classic delivery still consumes this shared account credential today.
    # Modern runtime drivers are allowed to rotate/replace their own credential
    # record later without changing the Subscription identity.
    for protocol in requested_protocols:
        db.add(
            ProtocolCredential(
                subscription_id=sub.id,
                protocol=protocol,
                username=username,
                secret_encrypted=password,
                is_active=True,
            )
        )

    sub.account_username = username
    sub.account_password_encrypted = password

    db.flush()
    return sub
