from __future__ import annotations

from datetime import timedelta

from app.main import app  # noqa: F401 - creates the production schema
from app.database import SessionLocal
from app.models import (
    Node,
    NodeStatus,
    NodeType,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionStatus,
    User,
)
from app.quota_models import QuotaDevice, QuotaSession, QuotaUsageEvent
from app.services.local_core_cisco_telemetry import (
    parse_occtl_users,
    reconcile_cisco_snapshot,
)


MIB = 1024 * 1024
GIB = 1024 * 1024 * 1024


def main() -> None:
    db = SessionLocal()
    try:
        user = User(
            email="local-cisco-telemetry-ci@example.com",
            password_hash="ci-not-a-login-password",
            full_name="Local Cisco CI",
            is_active=True,
        )
        plan = Plan(
            name="Local Cisco Telemetry CI",
            description="CI",
            duration_days=30,
            traffic_gb=50,
            device_limit=1,
            price_toman=0,
            is_active=True,
            enable_cisco=True,
            enable_openvpn=False,
            enable_wireguard=False,
            enable_l2tp=False,
            enable_v2ray=False,
        )
        db.add_all([user, plan])
        db.flush()

        node = Node(
            name="TwinPanel Local Core CI",
            node_type=NodeType.EXIT,
            country_code="US",
            public_ip="127.0.0.1",
            agent_url="local://core",
            status=NodeStatus.ONLINE,
            show_to_users=True,
            enable_cisco=True,
        )
        db.add(node)
        db.flush()

        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=None,
            expires_at=None,
            activation_duration_days=30,
            traffic_limit_bytes=50 * GIB,
            traffic_used_bytes=0,
            account_username="mv4_12",
        )
        db.add(subscription)
        db.flush()
        db.add(SubscriptionNode(subscription_id=subscription.id, node_id=node.id))
        db.add(
            ProtocolCredential(
                subscription_id=subscription.id,
                protocol="cisco",
                username="mv4_12",
                is_active=True,
            )
        )
        db.commit()

        raw = """[
          {
            "ID": 12,
            "Username": "mv4_12",
            "Remote IP": "198.51.100.44",
            "raw_connected_at": 1792360000,
            "RX": 1048576,
            "TX": 2097152
          }
        ]"""
        first_snapshot = parse_occtl_users(raw)
        assert len(first_snapshot) == 1
        first = reconcile_cisco_snapshot(db, int(node.id), first_snapshot)
        db.commit()
        assert first["opened"] == 1
        assert first["usage_events"] == 1

        db.refresh(subscription)
        assert subscription.starts_at is not None
        assert subscription.expires_at is not None
        assert timedelta(days=29, hours=23) < (
            subscription.expires_at - subscription.starts_at
        ) < timedelta(days=30, minutes=1)
        assert int(subscription.traffic_used_bytes or 0) == 3 * MIB

        device = (
            db.query(QuotaDevice)
            .filter(QuotaDevice.subscription_id == subscription.id)
            .one()
        )
        credential = (
            db.query(ProtocolCredential)
            .filter(ProtocolCredential.subscription_id == subscription.id)
            .one()
        )
        assert int(device.id) != 0
        assert int(device.id) != int(credential.id) or device.__tablename__ != credential.__tablename__
        assert device.protocol == "openconnect"
        assert device.device_key == f"protocol-credential:{credential.id}"

        active = (
            db.query(QuotaSession)
            .filter(
                QuotaSession.subscription_id == subscription.id,
                QuotaSession.status == "active",
            )
            .one()
        )
        assert active.protocol == "openconnect"
        assert active.client_ip == "198.51.100.44"

        same = reconcile_cisco_snapshot(db, int(node.id), first_snapshot)
        db.commit()
        db.refresh(subscription)
        assert same["opened"] == 0
        assert same["usage_events"] == 0
        assert int(subscription.traffic_used_bytes or 0) == 3 * MIB
        assert db.query(QuotaUsageEvent).filter(
            QuotaUsageEvent.subscription_id == subscription.id
        ).count() == 1

        grown_snapshot = parse_occtl_users(
            """[
              {
                "ID": 12,
                "Username": "mv4_12",
                "Remote IP": "198.51.100.44",
                "raw_connected_at": 1792360000,
                "RX": 2097152,
                "TX": 4194304
              }
            ]"""
        )
        grown = reconcile_cisco_snapshot(db, int(node.id), grown_snapshot)
        db.commit()
        db.refresh(subscription)
        assert grown["opened"] == 0
        assert grown["usage_events"] == 1
        assert int(subscription.traffic_used_bytes or 0) == 6 * MIB

        closed = reconcile_cisco_snapshot(db, int(node.id), [])
        db.commit()
        db.refresh(active)
        assert closed["closed"] >= 1
        assert active.status == "closed"

        print(
            "LOCAL_CORE_CISCO_TELEMETRY_OK",
            f"subscription={subscription.id}",
            f"device={device.id}",
            f"used={subscription.traffic_used_bytes}",
        )
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
