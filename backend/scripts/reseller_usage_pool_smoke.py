from __future__ import annotations

import secrets

from app.database import Base, SessionLocal, engine
from app.models import Plan, Subscription, SubscriptionStatus, User
from app.models_reseller import Reseller, ResellerSubscription
from app.reseller_pool_models import ResellerPoolSuspension
from app.services.reseller_traffic_pool import (
    _suspend_reseller_pool,
    restore_reseller_pool_subscriptions,
)


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    suffix = secrets.token_hex(5)

    try:
        user = User(
            email=f"pool-{suffix}@example.com",
            password_hash="ci-not-a-real-login",
            full_name="Pool Smoke",
            is_active=True,
        )
        db.add(user)
        db.flush()

        plan = Plan(
            name=f"pool-smoke-{suffix}",
            duration_days=30,
            traffic_gb=50,
            device_limit=1,
            price_toman=0,
            is_active=True,
            enable_cisco=True,
            enable_openvpn=True,
            enable_wireguard=True,
            enable_l2tp=True,
            enable_v2ray=True,
        )
        db.add(plan)
        db.flush()

        reseller = Reseller(
            owner_user_id=int(user.id),
            code=f"pool-{suffix}",
            name="Pool Smoke",
            traffic_balance_bytes=0,
            traffic_credit_bytes=0,
            is_active=True,
        )
        db.add(reseller)
        db.flush()

        subscriptions = []
        for index in range(2):
            sub = Subscription(
                user_id=int(user.id),
                plan_id=int(plan.id),
                status=SubscriptionStatus.ACTIVE,
                activation_duration_days=30,
                traffic_limit_bytes=50 * 1024**3,
                traffic_used_bytes=index * 1024**3,
            )
            db.add(sub)
            db.flush()
            db.add(
                ResellerSubscription(
                    reseller_id=int(reseller.id),
                    subscription_id=int(sub.id),
                    customer_user_id=int(user.id),
                    buy_price_toman=0,
                    sell_price_toman=0,
                )
            )
            subscriptions.append(sub)

        db.flush()

        suspended = _suspend_reseller_pool(db, int(reseller.id))
        db.flush()

        assert suspended == 2, suspended
        assert all(
            sub.status == SubscriptionStatus.SUSPENDED
            for sub in subscriptions
        )

        markers = (
            db.query(ResellerPoolSuspension)
            .filter(
                ResellerPoolSuspension.reseller_id == reseller.id,
                ResellerPoolSuspension.active.is_(True),
            )
            .all()
        )
        assert len(markers) == 2, len(markers)

        reseller.traffic_balance_bytes = 25 * 1024**3
        restore = restore_reseller_pool_subscriptions(
            db,
            int(reseller.id),
        )
        db.flush()

        assert int(restore.get("restored") or 0) == 2, restore
        assert all(
            sub.status == SubscriptionStatus.ACTIVE
            for sub in subscriptions
        )
        assert not (
            db.query(ResellerPoolSuspension)
            .filter(
                ResellerPoolSuspension.reseller_id == reseller.id,
                ResellerPoolSuspension.active.is_(True),
            )
            .first()
        )

        print("RESELLER_USAGE_POOL_SUSPEND_RESTORE_OK")

    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
