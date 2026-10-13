from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWallet,
    CustomerWalletTopup,
    CustomerWalletTransaction,
)
from ..database import SessionLocal
from ..models_reseller import Reseller, ResellerWalletTransaction
from ..payment_models import PaymentIntent, PaymentSettings
from ..telegram_notify_service import queue_telegram_notification
from ..user_notification_models import UserNotification
from .payment_automation import _verify_bep20_transfer, automation_settings
from .payment_native_crypto import (
    _verify_bnb,
    _verify_trx,
    native_gateway_settings,
)


CRYPTO_WALLET_METHODS = {
    "usdt_bep20": "USDT",
    "trx_tron": "TRX",
    "bnb_bsc": "BNB",
}


def _wallet_locked(db: Session, user_id: int) -> CustomerWallet:
    row = (
        db.query(CustomerWallet)
        .filter(CustomerWallet.user_id == int(user_id))
        .with_for_update()
        .first()
    )

    if row is not None:
        return row

    row = CustomerWallet(
        user_id=int(user_id),
        balance_toman=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _reseller_locked(db: Session, user_id: int) -> Reseller | None:
    """Return the reseller owned by this login account and lock it for crediting.

    Reseller owners use the reseller wallet as their operational wallet. Keeping
    top-up credit in the customer wallet makes traffic-package purchases fail
    even after a successful payment, so reseller top-ups are routed directly to
    the reseller ledger.
    """

    return (
        db.query(Reseller)
        .filter(Reseller.owner_user_id == int(user_id))
        .with_for_update()
        .first()
    )


def credit_wallet_topup(
    db: Session,
    topup_id: int,
    *,
    source: str,
    allow_pending: bool = False,
) -> dict:
    """Credit one wallet top-up exactly once.

    Customer accounts are credited to ``customer_wallets``. When the same login
    owns a reseller account, the payment is instead credited directly to the
    reseller wallet because reseller purchases debit ``resellers.wallet_balance``.

    Both ledgers use a stable reference derived from the top-up id, so retries
    from workers, SMS Reader, panel, Telegram or an admin cannot double-credit.
    """

    row = (
        db.query(CustomerWalletTopup)
        .filter(CustomerWalletTopup.id == int(topup_id))
        .with_for_update()
        .first()
    )

    if row is None:
        return {"ok": False, "credited": False, "reason": "topup_not_found"}

    reference = f"wallet-topup:{row.id}"
    reseller = _reseller_locked(db, row.user_id)

    customer_existing_tx = (
        db.query(CustomerWalletTransaction)
        .filter(CustomerWalletTransaction.reference == reference)
        .first()
    )

    reseller_existing_tx = None
    if reseller is not None:
        reseller_existing_tx = (
            db.query(ResellerWalletTransaction)
            .filter(ResellerWalletTransaction.idempotency_key == reference)
            .first()
        )

    # Old approved rows may have been credited to the customer wallet before
    # reseller-aware routing existed. Never move or duplicate those funds
    # automatically: report the legacy target and leave the historical ledger
    # intact.
    if row.status == "approved" or customer_existing_tx is not None or reseller_existing_tx is not None:
        if row.status != "approved":
            row.status = "approved"
            row.approved_at = row.approved_at or datetime.utcnow()
            row.rejected_at = None
            db.commit()

        if reseller_existing_tx is not None and reseller is not None:
            return {
                "ok": True,
                "credited": False,
                "already_approved": True,
                "topup_id": row.id,
                "user_id": row.user_id,
                "wallet_type": "reseller",
                "reseller_id": int(reseller.id),
                "balance_toman": int(reseller.wallet_balance or 0),
            }

        wallet = _wallet_locked(db, row.user_id)
        return {
            "ok": True,
            "credited": False,
            "already_approved": True,
            "topup_id": row.id,
            "user_id": row.user_id,
            "wallet_type": "customer_legacy" if reseller is not None else "customer",
            "balance_toman": int(wallet.balance_toman or 0),
        }

    allowed = {"awaiting_review"}
    if allow_pending:
        allowed.add("pending_payment")

    if row.status not in allowed:
        return {
            "ok": False,
            "credited": False,
            "reason": "invalid_status",
            "status": row.status,
        }

    amount = int(row.amount_toman or 0)
    if amount <= 0:
        return {"ok": False, "credited": False, "reason": "invalid_amount"}

    wallet_type = "customer"
    balance_after = 0
    reseller_id: int | None = None

    if reseller is not None:
        reseller.wallet_balance = int(reseller.wallet_balance or 0) + amount
        reseller.updated_at = datetime.utcnow()
        balance_after = int(reseller.wallet_balance or 0)
        reseller_id = int(reseller.id)
        wallet_type = "reseller"

        db.add(
            ResellerWalletTransaction(
                reseller_id=reseller.id,
                amount=amount,
                balance_after=balance_after,
                transaction_type="wallet_topup",
                reference_type="customer_wallet_topup",
                reference_id=row.id,
                description="شارژ کیف پول نمایندگی",
                idempotency_key=reference,
                created_at=datetime.utcnow(),
            )
        )
    else:
        wallet = _wallet_locked(db, row.user_id)
        wallet.balance_toman = int(wallet.balance_toman or 0) + amount
        wallet.updated_at = datetime.utcnow()
        balance_after = int(wallet.balance_toman or 0)

        db.add(
            CustomerWalletTransaction(
                user_id=row.user_id,
                amount_toman=amount,
                kind="topup",
                description="شارژ کیف پول",
                reference=reference,
                created_at=datetime.utcnow(),
            )
        )

    row.status = "approved"
    row.approved_at = datetime.utcnow()
    row.rejected_at = None
    row.review_note = f"auto-credit:{source};target={wallet_type}"[:1000]

    batch_id = f"wallet-topup-{row.id}"
    exists_notification = (
        db.query(UserNotification.id)
        .filter(
            UserNotification.user_id == row.user_id,
            UserNotification.batch_id == batch_id,
        )
        .first()
    )

    if not exists_notification:
        if wallet_type == "reseller":
            title = "کیف پول نمایندگی شارژ شد"
            message = f"مبلغ {amount:,} تومان با موفقیت به کیف پول نمایندگی شما اضافه شد."
        else:
            title = "کیف پول شارژ شد"
            message = f"مبلغ {amount:,} تومان با موفقیت به کیف پول شما اضافه شد."

        notification = UserNotification(
            batch_id=batch_id,
            user_id=row.user_id,
            title=title,
            message=message,
            kind="success",
            telegram_requested=True,
            created_at=datetime.utcnow(),
        )
        db.add(notification)
        db.flush()

        queue_telegram_notification(
            db,
            user_id=row.user_id,
            event_key=f"wallet-topup-approved:{row.id}",
            kind="user_notification",
            payload={
                "notification_id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "kind": notification.kind,
            },
        )

    db.commit()

    result = {
        "ok": True,
        "credited": True,
        "topup_id": row.id,
        "user_id": row.user_id,
        "amount_toman": amount,
        "balance_toman": balance_after,
        "wallet_type": wallet_type,
        "source": source,
    }
    if reseller_id is not None:
        result["reseller_id"] = reseller_id
    return result


def _destination_for_topup(db: Session, method: str) -> str:
    if method == "usdt_bep20":
        cfg = db.get(PaymentSettings, 1)
        if not cfg or not cfg.usdt_bep20_enabled:
            return ""
        return str(cfg.usdt_bep20_address or "").strip()

    native = native_gateway_settings(db)
    if method == "trx_tron" and native.get("trx_tron_enabled"):
        return str(native.get("trx_tron_address") or "").strip()
    if method == "bnb_bsc" and native.get("bnb_bsc_enabled"):
        return str(native.get("bnb_bsc_address") or "").strip()
    return ""


async def verify_wallet_crypto_topup(topup_id: int, db: Session) -> dict:
    if not automation_settings(db).get("crypto_auto_verify"):
        return {"ok": True, "verified": False, "reason": "crypto_auto_verify_disabled"}

    row = db.get(CustomerWalletTopup, int(topup_id))
    if row is None:
        return {"ok": False, "verified": False, "reason": "topup_not_found"}

    method = str(row.method or "").lower()
    if method not in CRYPTO_WALLET_METHODS:
        return {"ok": True, "verified": False, "reason": "not_crypto"}

    if row.status == "approved":
        return {"ok": True, "verified": True, "reason": "already_approved"}

    if row.status != "awaiting_review":
        return {"ok": True, "verified": False, "reason": "not_submitted"}

    txid = str(row.txid or "").strip()
    if not txid:
        return {"ok": True, "verified": False, "reason": "txid_missing"}

    # A blockchain transaction can fund only one thing in TwinPanel.
    reused_intent = (
        db.query(PaymentIntent.id)
        .filter(PaymentIntent.txid == txid)
        .first()
    )
    if reused_intent:
        row.review_note = f"auto-chain-check: txid_used_by_payment:{reused_intent[0]}"[:1000]
        db.commit()
        return {"ok": True, "verified": False, "reason": "txid_already_used_by_payment"}

    destination = _destination_for_topup(db, method)
    if not destination:
        row.review_note = "auto-chain-check: gateway_not_ready"
        db.commit()
        return {"ok": True, "verified": False, "reason": "gateway_not_ready"}

    if method == "usdt_bep20":
        chain = await _verify_bep20_transfer(txid, destination)
    elif method == "trx_tron":
        chain = await _verify_trx(txid, destination)
    else:
        chain = await _verify_bnb(txid, destination)

    state = str(chain.get("state") or "pending")
    if state != "confirmed":
        row.review_note = (
            "auto-chain-check: " + str(chain.get("reason") or "pending")
        )[:1000]
        db.commit()
        return {"ok": True, "verified": False, **chain}

    try:
        received = Decimal(str(chain.get("amount") or "0"))
        expected_raw = row.crypto_amount
        if expected_raw is None and method == "usdt_bep20":
            expected_raw = row.crypto_amount_usdt
        expected = Decimal(str(expected_raw or "0"))
    except InvalidOperation:
        return {"ok": False, "verified": False, "reason": "invalid_amount"}

    if expected <= 0:
        return {"ok": False, "verified": False, "reason": "expected_amount_missing"}

    if received < expected:
        row.review_note = (
            f"auto-chain-check: amount_too_low expected={expected} received={received}"
        )[:1000]
        db.commit()
        return {
            "ok": True,
            "verified": False,
            "reason": "amount_too_low",
            "expected": str(expected),
            "received": str(received),
        }

    row.review_note = (
        f"auto-chain-confirmed:{method}; expected={expected}; received={received}"
    )[:1000]
    db.commit()

    credited = credit_wallet_topup(
        db,
        row.id,
        source=f"crypto:{method}",
        allow_pending=False,
    )

    return {
        "ok": bool(credited.get("ok")),
        "verified": bool(credited.get("ok")),
        "chain": chain,
        "credit": credited,
    }


async def process_pending_wallet_crypto_topups_once(limit: int = 100) -> dict:
    db = SessionLocal()
    checked = 0
    verified = 0
    errors = 0

    try:
        ids = [
            int(row[0])
            for row in (
                db.query(CustomerWalletTopup.id)
                .filter(
                    CustomerWalletTopup.status == "awaiting_review",
                    CustomerWalletTopup.method.in_(tuple(CRYPTO_WALLET_METHODS)),
                    CustomerWalletTopup.txid.isnot(None),
                )
                .order_by(CustomerWalletTopup.id.asc())
                .limit(max(1, int(limit)))
                .all()
            )
        ]

        for topup_id in ids:
            checked += 1
            try:
                result = await verify_wallet_crypto_topup(topup_id, db)
                if result.get("verified"):
                    verified += 1
            except Exception as exc:
                errors += 1
                db.rollback()
                print(
                    "wallet crypto topup verify failed:",
                    topup_id,
                    str(exc),
                    flush=True,
                )

        return {
            "ok": errors == 0,
            "checked": checked,
            "verified": verified,
            "errors": errors,
        }

    finally:
        db.close()


async def wallet_payment_automation_loop() -> None:
    while True:
        try:
            result = await process_pending_wallet_crypto_topups_once()
            if result.get("checked") or result.get("verified") or result.get("errors"):
                print("WALLET_CRYPTO_AUTO_VERIFY", result, flush=True)
        except Exception as exc:
            print("wallet payment automation loop failed:", str(exc), flush=True)

        await asyncio.sleep(10)
