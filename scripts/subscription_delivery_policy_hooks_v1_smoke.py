#!/usr/bin/env python3
from __future__ import annotations

import os

os.environ.setdefault("APP_SECRET_KEY", "subscription-delivery-hooks-v1-smoke-secret")
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://twinpanel_smoke:twinpanel_smoke@127.0.0.1:1/"
    "twinpanel_smoke"
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "subscription-delivery-hooks-node-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Node, Plan, Subscription, SubscriptionStatus, User, UserRole
from app.routers import account_delivery as ad
from app.subscription_delivery_policy_v1 import (
    SubscriptionDeliveryPolicyState,
    _decode_delivery_file_selector,
    _delivery_file_selector,
    autosync_legacy_only_session,
    install_account_delivery_hooks,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Plan.__table__,
            Node.__table__,
            Subscription.__table__,
            SubscriptionDeliveryPolicyState.__table__,
        ],
    )

    with Session(engine) as db:
        db.add(
            User(
                id=1,
                email="delivery-hooks@example.test",
                password_hash="x",
                role=UserRole.USER,
                is_active=True,
            )
        )
        db.add_all(
            [
                Subscription(
                    id=10,
                    user_id=1,
                    plan_id=1,
                    status=SubscriptionStatus.ACTIVE,
                    traffic_limit_bytes=0,
                    traffic_used_bytes=0,
                    share_code="explicit-10",
                ),
                Subscription(
                    id=11,
                    user_id=1,
                    plan_id=1,
                    status=SubscriptionStatus.ACTIVE,
                    traffic_limit_bytes=0,
                    traffic_used_bytes=0,
                    share_code="legacy-11",
                ),
            ]
        )
        db.add(SubscriptionDeliveryPolicyState(subscription_id=10, mode="explicit"))
        db.commit()

        visible_ids = [
            int(row.id)
            for row in autosync_legacy_only_session(db)
            .query(Subscription)
            .order_by(Subscription.id.asc())
            .all()
        ]
        check(visible_ids == [11], "explicit subscription leaked into installed-node autosync")

    install_account_delivery_hooks()

    direct_selector = _delivery_file_selector(2, "direct")
    tunnel_selector = _delivery_file_selector(2, "tunnel")
    check(direct_selector < 0 and tunnel_selector < 0, "file selectors must not collide with real node IDs")
    check(direct_selector != tunnel_selector, "Both-mode selectors collided")
    check(_decode_delivery_file_selector(direct_selector) == (2, "direct"), "Direct selector decode failed")
    check(_decode_delivery_file_selector(tunnel_selector) == (2, "tunnel"), "Tunnel selector decode failed")

    payload = {
        "delivery_policy": "explicit",
        "credentials": [
            {
                "protocol": "openvpn",
                "items": [
                    {
                        "node_id": 2,
                        "node": "Germany • Tunnel",
                        "server": "iran.example.test",
                        "port": 21002,
                        "delivery_mode": "tunnel",
                        "config": "client\nremote iran.example.test 21002\n",
                    },
                    {
                        "node_id": 2,
                        "node": "Germany • Direct",
                        "server": "de.example.test",
                        "port": 1194,
                        "delivery_mode": "direct",
                        "config": "client\nremote de.example.test 1194\n",
                    },
                ],
            }
        ],
    }

    html = ad._credential_sections(payload, "stable-token")
    check(
        f"/file/openvpn/{tunnel_selector}" in html
        and f"/file/openvpn/{direct_selector}" in html,
        "Both-mode HTML did not generate distinct file URLs",
    )
    check(
        ad._find_item(payload, "openvpn", tunnel_selector)["delivery_mode"] == "tunnel",
        "Tunnel file selector resolved the wrong profile",
    )
    check(
        ad._find_item(payload, "openvpn", direct_selector)["delivery_mode"] == "direct",
        "Direct file selector resolved the wrong profile",
    )
    check(payload["credentials"][0]["items"][0]["node_id"] == 2, "public JSON node_id was mutated")

    print("SUBSCRIPTION_DELIVERY_POLICY_HOOKS_V1_SMOKE_OK")


if __name__ == "__main__":
    main()
