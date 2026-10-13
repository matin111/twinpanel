from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import Subscription
from ..models_reseller import Reseller
from ..reseller_owned_plans import (
    create_subscription_from_owned_plan,
    owned_plan_by_backing,
)
from . import reseller_bot_orders as legacy
from .reseller_bot_orders_volume_v2 import (
    _renewal_subscription_id,
    approve_order_volume_v2,
)


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-commerce-owned-v3"],
)


def _failed_status(row) -> str:
    # Wallet orders are already paid internally and must never be sent back to
    # manual receipt review just because provisioning needs a retry.
    if row.subscription_id or str(row.payment_note or "") == "wallet":
        return "provision_failed"
    return "awaiting_review"


async def approve_order_owned_v3(
    order_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = legacy.owned_order(
        db,
        int(reseller.id),
        order_id,
        lock=True,
    )

    if not row:
        raise HTTPException(status_code=404, detail="سفارش پیدا نشد")

    # Renewals already have a usage-only V2 path. Keep it as the canonical
    # renewal implementation so changing an account quota never reserves pool.
    if _renewal_subscription_id(row.payment_note) is not None:
        return await approve_order_volume_v2(
            order_id=order_id,
            reseller=reseller,
            db=db,
        )

    mapping = owned_plan_by_backing(
        db,
        int(reseller.id),
        int(row.plan_id),
        active_only=False,
    )

    # Historical orders created before reseller-owned plans stay compatible.
    if not mapping:
        if row.status == "paid":
            row.status = "awaiting_review"
            db.commit()
        return await legacy.approve_order(
            order_id=order_id,
            reseller=reseller,
            db=db,
        )

    if row.status == "fulfilled":
        return legacy.order_out(db, row)

    if row.status not in {"awaiting_review", "provision_failed", "paid"}:
        raise HTTPException(
            status_code=409,
            detail="این سفارش آماده تأیید نیست",
        )

    row.status = "provisioning"
    row.error_text = None
    row.approved_at = row.approved_at or datetime.utcnow()
    db.commit()

    try:
        if not row.subscription_id:
            # Preserve the immutable order snapshot even if the reseller edits
            # the plan while a receipt is waiting for review. Display-only
            # fields which were not historically stored on the order use the
            # owned-plan mapping and do not affect quota or pricing.
            requested_protocols = {
                str(value).strip().lower()
                for value in (row.protocols or [])
                if str(value).strip()
            }

            snapshot = SimpleNamespace(
                id=int(mapping.id),
                reseller_id=int(mapping.reseller_id),
                backing_plan_id=int(mapping.backing_plan_id),
                title=(
                    str(mapping.title or "").strip()
                    or f"پلن #{int(mapping.id)}"
                ),
                device_limit=int(mapping.device_limit or 1),
                is_active=True,
                traffic_gb=int(row.traffic_gb),
                duration_days=int(row.duration_days),
                sell_price_toman=int(row.sell_price_toman),
                enable_cisco="cisco" in requested_protocols,
                enable_openvpn="openvpn" in requested_protocols,
                enable_wireguard="wireguard" in requested_protocols,
                enable_l2tp="l2tp" in requested_protocols,
                enable_v2ray=(
                    "v2ray" in requested_protocols
                    or "xray" in requested_protocols
                ),
            )

            sale = create_subscription_from_owned_plan(
                db,
                reseller=reseller,
                reseller_plan=snapshot,
                user_id=int(row.customer_user_id),
                idempotency_key=str(row.sale_idempotency_key),
                node_ids=list(row.node_ids or []),
                sell_price_toman=int(row.sell_price_toman),
            )

            subscription_id = int(sale["subscription_id"])

            row = legacy.owned_order(
                db,
                int(reseller.id),
                order_id,
                lock=True,
            )
            if not row:
                raise RuntimeError("سفارش پس از ساخت اشتراک پیدا نشد")

            row.subscription_id = subscription_id
            db.commit()

        subscription_id = int(row.subscription_id)

        provision = await legacy.provision_account(
            subscription_id,
            db,
        )

        if isinstance(provision, dict):
            errors = (
                provision.get("errors")
                or provision.get("provision_errors")
                or []
            )
            if errors:
                raise RuntimeError(str(errors)[:1500])
            if "ok" in provision and provision["ok"] is False:
                raise RuntimeError("Provision ناموفق بود")

        row = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )
        if not row:
            raise RuntimeError("سفارش پس از Provision پیدا نشد")

        row.status = "fulfilled"
        row.fulfilled_at = row.fulfilled_at or datetime.utcnow()
        row.error_text = None

        from ..discount_service import redeem_discount_for_order

        redeem_discount_for_order(
            db,
            order_kind="reseller_bot",
            order_id=int(row.id),
        )

        db.commit()
        db.refresh(row)

        sub = db.get(Subscription, subscription_id)
        info = legacy._stored_info(db, sub) if sub else {}
        result = legacy.order_out(db, row)
        result["pricing_model"] = "usage_pool"
        result["traffic_reserved_from_reseller"] = False
        result["delivery"] = {
            "username": (
                (info.get("account") or {}).get("username")
                if info else None
            ),
            "subscription_link": (
                info.get("subscription_link") if info else None
            ),
        }

        telegram_delivery_sent = False
        try:
            telegram_delivery_sent = await legacy._send_order_delivery_to_telegram(
                db,
                reseller_id=int(row.reseller_id),
                telegram_id=int(row.telegram_id),
                order_id=int(row.id),
                info=info or {},
            )
        except Exception:
            telegram_delivery_sent = False

        result["telegram_delivery_sent"] = telegram_delivery_sent
        return result

    except HTTPException:
        db.rollback()
        failed = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )
        if failed:
            failed.status = _failed_status(failed)
            db.commit()
        raise

    except Exception as exc:
        db.rollback()
        failed = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )
        if failed:
            failed.status = _failed_status(failed)
            failed.error_text = str(exc)[:2000]
            db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post("/orders/{order_id}/approve")
async def approve_order_owned_route(
    order_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return await approve_order_owned_v3(
        order_id=order_id,
        reseller=reseller,
        db=db,
    )
