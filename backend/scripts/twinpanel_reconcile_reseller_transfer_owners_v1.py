"""Safely repair historic management-only transfers that kept Administrator as owner.

Default: dry-run. --apply calls the normal admin reseller-transfer service,
which validates membership and updates ownership and reseller mapping in one
transaction. No credentials, quotas, expiry or VPN nodes are touched.
"""
from __future__ import annotations

import argparse

from app.database import SessionLocal
from app.models import Subscription, User, UserRole
from app.models_reseller import ResellerSubscription
from app.routers.reseller_admin_v2 import (
    SubscriptionTransferIn,
    transfer_subscription_to_reseller,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair legacy reseller transfers")
    parser.add_argument("--apply", action="store_true", help="Commit validated owner repairs")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("limit must be between 1 and 100")

    done = 0
    failed = 0
    with SessionLocal() as db:
        rows = (
            db.query(
                ResellerSubscription.subscription_id,
                ResellerSubscription.reseller_id,
                ResellerSubscription.customer_user_id,
            )
            .join(Subscription, Subscription.id == ResellerSubscription.subscription_id)
            .join(User, User.id == Subscription.user_id)
            .filter(
                User.role == UserRole.ADMIN,
                Subscription.user_id != ResellerSubscription.customer_user_id,
                ResellerSubscription.buy_price_toman == 0,
                ResellerSubscription.sell_price_toman == 0,
            )
            .order_by(ResellerSubscription.subscription_id)
            .limit(args.limit)
            .all()
        )
        print("LEGACY_TRANSFER_OWNER_PREVIEW", {
            "candidates": len(rows), "apply": args.apply,
        }, flush=True)
        for subscription_id, reseller_id, customer_user_id in rows:
            if not args.apply:
                print("CANDIDATE", {
                    "subscription_id": subscription_id,
                    "reseller_id": reseller_id,
                    "customer_user_id": customer_user_id,
                }, flush=True)
                continue
            try:
                result = transfer_subscription_to_reseller(
                    int(reseller_id), int(subscription_id),
                    SubscriptionTransferIn(customer_user_id=int(customer_user_id)),
                    db,
                )
                if not result.get("ok") or result.get("owner_user_id") != customer_user_id:
                    raise RuntimeError("ownership not confirmed")
                done += 1
                print("OWNER_REPAIRED", int(subscription_id), flush=True)
            except Exception as exc:
                db.rollback()
                failed += 1
                print("OWNER_REPAIR_SKIPPED", {
                    "subscription_id": int(subscription_id),
                    "type": type(exc).__name__,
                }, flush=True)
        print("LEGACY_TRANSFER_OWNER_SUMMARY", {
            "repaired": done, "failed": failed, "preview_only": not args.apply,
        }, flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
