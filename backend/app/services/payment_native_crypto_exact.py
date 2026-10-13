from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from ..database import SessionLocal
from ..models import Subscription
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification
from .payment_native_crypto import (
    _crypto_auto_verify_enabled,
    _verify_bnb,
    _verify_trx,
    native_gateway_settings,
)


async def verify_native_crypto_intent_exact(intent_id: int, db) -> dict:
    if not _crypto_auto_verify_enabled(db):
        return {"ok": True, "verified": False, "reason": "crypto_auto_verify_disabled"}

    intent = db.get(PaymentIntent, int(intent_id))
    if intent is None:
        return {"ok": False, "verified": False, "reason": "payment_not_found"}

    method = str(intent.method or "").lower()
    if method not in {"trx_tron", "bnb_bsc"}:
        return {"ok": True, "verified": False, "reason": "not_native_crypto"}

    if intent.status in {"approved", "auto_verified", "paid"}:
        return {"ok": True, "verified": True, "reason": "already_verified"}

    txid = str(intent.txid or "").strip()
    if not txid:
        return {"ok": True, "verified": False, "reason": "txid_missing"}

    settings = native_gateway_settings(db)

    if method == "trx_tron":
        destination = str(settings.get("trx_tron_address") or "").strip()
        chain_result = await _verify_trx(txid, destination)
    else:
        destination = str(settings.get("bnb_bsc_address") or "").strip()
        chain_result = await _verify_bnb(txid, destination)

    if str(chain_result.get("state") or "pending") != "confirmed":
        intent.review_note = (
            "auto-native-chain-check: "
            + str(chain_result.get("reason") or "unknown")
        )[:1000]
        db.commit()
        return {"ok": True, "verified": False, **chain_result}

    try:
        received = Decimal(str(chain_result.get("amount") or "0"))
        expected = Decimal(str(intent.crypto_amount or "0"))
    except InvalidOperation:
        return {"ok": False, "verified": False, "reason": "invalid_expected_amount"}

    if expected <= 0:
        return {"ok": False, "verified": False, "reason": "expected_amount_missing"}

    if received < expected:
        intent.review_note = (
            "auto-native-chain-check: amount_too_low "
            f"expected={expected} received={received}"
        )[:1000]
        db.commit()
        return {
            "ok": True,
            "verified": False,
            "state": "invalid",
            "reason": "amount_too_low",
            "expected": str(expected),
            "received": str(received),
        }

    intent = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == int(intent_id))
        .with_for_update()
        .first()
    )

    if intent is None:
        return {"ok": False, "verified": False, "reason": "payment_not_found"}

    if intent.status in {"approved", "auto_verified", "paid"}:
        return {"ok": True, "verified": True, "reason": "already_verified"}

    now = datetime.utcnow()
    intent.status = "auto_verified"
    intent.verified_at = now
    intent.review_note = (
        f"auto-native-verified: {method} amount={received}"
    )[:1000]

    order = db.get(StoreOrder, intent.order_id)
    if order is None:
        db.rollback()
        return {"ok": False, "verified": False, "reason": "order_missing"}

    order.status = "paid"
    order.payment_method = method
    order.payment_reference = txid
    if order.paid_at is None:
        order.paid_at = now

    db.commit()

    fulfilled = False
    fulfillment_error = None
    order_result = None

    try:
        from ..routers.store import _fulfill_paid_order
        order_result = await _fulfill_paid_order(order.id, db)
        fulfilled = True
    except HTTPException as exc:
        fulfillment_error = exc.detail

    if fulfilled:
        try:
            final_order = db.get(StoreOrder, order.id)
            subscription_id = final_order.subscription_id if final_order else None
            subscription = db.get(Subscription, subscription_id) if subscription_id else None

            queue_telegram_notification(
                db,
                user_id=intent.user_id,
                event_key=f"payment-auto-approved:{intent.id}",
                kind="payment_approved",
                payload={
                    "payment_id": intent.id,
                    "order_id": order.id,
                    "subscription_id": subscription_id,
                    "username": subscription.account_username if subscription else None,
                    "amount_toman": int(intent.base_amount_toman or 0),
                    "crypto_asset": intent.crypto_asset,
                    "crypto_amount": str(intent.crypto_amount or ""),
                    "crypto_rate_toman": intent.crypto_rate_toman,
                },
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            print("auto native crypto notification failed:", str(exc), flush=True)

    return {
        "ok": True,
        "verified": True,
        "fulfilled": fulfilled,
        "fulfillment_error": fulfillment_error,
        "order": order_result,
        **chain_result,
    }


async def process_pending_native_crypto_exact_once(limit: int = 50) -> dict:
    lookup_db = SessionLocal()
    try:
        ids = [
            int(row[0])
            for row in (
                lookup_db.query(PaymentIntent.id)
                .filter(
                    PaymentIntent.method.in_(["trx_tron", "bnb_bsc"]),
                    PaymentIntent.txid.isnot(None),
                    PaymentIntent.status.in_(["awaiting_review", "payment_submitted"]),
                )
                .order_by(PaymentIntent.id.asc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
        ]
    finally:
        lookup_db.close()

    checked = verified = errors = 0

    for intent_id in ids:
        db = SessionLocal()
        try:
            result = await verify_native_crypto_intent_exact(intent_id, db)
            checked += 1
            if result.get("verified"):
                verified += 1
        except Exception as exc:
            errors += 1
            db.rollback()
            print(
                "native crypto exact auto verification failed:",
                intent_id,
                str(exc),
                flush=True,
            )
        finally:
            db.close()

    return {
        "ok": errors == 0,
        "checked": checked,
        "verified": verified,
        "errors": errors,
    }
