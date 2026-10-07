from datetime import datetime
import secrets
import string
import secrets
import string
import secrets
import string

from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..quota_models import QuotaDevice

from ..routers.general_settings import build_subscription_username

from ..models import (
    Node,
    NodeStatus,
    NodeType,
    Plan,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    ProtocolCredential,
    User,
)


PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


def generate_share_code(username: str | None):
    import secrets
    import re

    base = (username or "user").lower()
    base = re.sub(r"[^a-z0-9]+", "", base)

    if len(base) < 3:
        base = "user"

    return f"{base[:12]}-{secrets.token_hex(3)}"




def generate_account_username(user_id: int):
    import secrets
    return f"mv{user_id}{secrets.token_hex(3)}"


def generate_account_password():
    import secrets
    return str(
        secrets.randbelow(90000000) + 10000000
    )



def generate_username():
    return "mv" + secrets.token_hex(5)


def generate_password():
    chars = string.ascii_letters + string.digits
    return "".join(
        secrets.choice(chars)
        for _ in range(12)
    )


def create_subscription_core(

    db: Session,
    user_id: int,
    plan_id: int,
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

    plan = db.get(Plan, plan_id)

    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )


    requested_protocols = list(
        dict.fromkeys(
            x.strip().lower()
            for x in protocols
            if x.strip()
        )
    )


    invalid = [
        p for p in requested_protocols
        if p not in PROTOCOL_FIELDS
    ]

    if invalid:
        raise HTTPException(
            status_code=422,
            detail="پروتکل نامعتبر",
        )


    # TWINPANEL_GLOBAL_NODES_FOR_ALL_SUBSCRIPTIONS_V1
    #
    # Node selection is infrastructure-wide.
    # Every subscription belongs to every Node.
    # node_ids from callers are kept only for API compatibility
    # and no longer restrict the subscription.
    nodes = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )


    if not requested_protocols:

        requested_protocols = [
            p
            for p, field in PROTOCOL_FIELDS.items()
            if getattr(plan, field, False)
        ]


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


    # TWINPANEL_USERNAME_TEMPLATE_V1
    # Username is generated after subscription id exists

    if not password:
        password = generate_account_password()


    # TWINPANEL_USERNAME_TEMPLATE_CENTRAL_V1
    # Username is generated after subscription id exists

    if not password:
        alphabet = (
            string.ascii_letters
            + string.digits
        )
        password = (
            "Mv"
            + ''.join(
                secrets.choice(alphabet)
                for _ in range(10)
            )
        )

    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,

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
    # Apply admin configured username pattern after subscription id exists
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

        # TWINPANEL_QUOTA_DEVICE_CREATE_V1
        # هر اشتراک باید Device قابل enforce داشته باشد.
        from app.quota_models import QuotaDevice

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


    # CREATE PROTOCOL CREDENTIALS
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

