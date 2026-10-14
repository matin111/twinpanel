from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWallet,
    CustomerWalletTransaction,
)
from ..database import get_db
from ..deps import require_reseller
from ..models import Subscription, User
from ..models_reseller import Reseller
from ..reseller_owned_plans import (
    create_subscription_from_owned_plan,
    owned_plan_by_backing,
)
from ..reseller_telegram_models import ResellerTelegramLink
from . import reseller_bot_orders as legacy
from .customer_wallet import _wallet
from .reseller_bot_orders_volume_v2 import (
    _renewal_subscription_id,
    approve_order_volume_v2,
)


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-commerce-owned-v3"],
)


class ResellerBotWalletAdjustIn(BaseModel):
    amount_toman: int = Field(
        ge=-100_000_000,
        le=100_000_000,
    )
    note: str = Field(
        min_length=2,
        max_length=500,
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
    )


def _bot_wallet_reference(
    reseller_id: int,
    idempotency_key: str,
) -> str:
    return (
        f"reseller-bot-wallet:{int(reseller_id)}:"
        f"{str(idempotency_key).strip()}"
    )[:180]


def _owned_bot_link(
    db: Session,
    reseller_id: int,
    user_id: int,
    *,
    lock: bool = False,
) -> ResellerTelegramLink:
    query = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller_id),
            ResellerTelegramLink.user_id == int(user_id),
        )
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="کاربر ربات متعلق به این نمایندگی نیست",
        )
    return row


def _wallet_transaction_out(row: CustomerWalletTransaction) -> dict:
    return {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "amount_toman": int(row.amount_toman or 0),
        "kind": row.kind,
        "description": row.description,
        "reference": row.reference,
        "created_at": row.created_at,
    }


@router.get("/wallets")
def reseller_bot_wallets(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    links = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller.id)
        )
        .order_by(
            ResellerTelegramLink.last_seen_at.desc(),
            ResellerTelegramLink.id.desc(),
        )
        .limit(1000)
        .all()
    )

    user_ids = [int(row.user_id) for row in links]
    wallets: dict[int, CustomerWallet] = {}
    if user_ids:
        wallets = {
            int(row.user_id): row
            for row in (
                db.query(CustomerWallet)
                .filter(CustomerWallet.user_id.in_(user_ids))
                .all()
            )
        }

    result = []
    for link in links:
        user = db.get(User, int(link.user_id))
        if not user or not user.is_active:
            continue
        wallet = wallets.get(int(link.user_id))
        email = str(user.email or "").strip()
        result.append({
            "user_id": int(user.id),
            "full_name": user.full_name,
            "phone": user.phone,
            "email": (
                None
                if email.endswith("@internal.twinpanel.invalid")
                else user.email
            ),
            "telegram_id": int(link.telegram_id),
            "telegram_username": link.telegram_username,
            "telegram_first_name": link.telegram_first_name,
            "last_seen_at": link.last_seen_at,
            "balance_toman": int(
                wallet.balance_toman if wallet else 0
            ),
            "wallet_updated_at": (
                wallet.updated_at if wallet else None
            ),
        })

    return result


@router.get("/wallets/{user_id}/transactions")
def reseller_bot_wallet_transactions(
    user_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    _owned_bot_link(
        db,
        int(reseller.id),
        int(user_id),
    )
    rows = (
        db.query(CustomerWalletTransaction)
        .filter(CustomerWalletTransaction.user_id == int(user_id))
        .order_by(CustomerWalletTransaction.id.desc())
        .limit(100)
        .all()
    )
    return [_wallet_transaction_out(row) for row in rows]


@router.post("/wallets/{user_id}/adjust")
def adjust_reseller_bot_wallet(
    user_id: int,
    payload: ResellerBotWalletAdjustIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    amount = int(payload.amount_toman)
    if amount == 0:
        raise HTTPException(
            status_code=422,
            detail="مبلغ تغییر نمی‌تواند صفر باشد",
        )

    _owned_bot_link(
        db,
        int(reseller.id),
        int(user_id),
        lock=True,
    )
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=404,
            detail="کاربر فعال ربات پیدا نشد",
        )

    wallet = _wallet(db, int(user_id), lock=True)
    db.flush()

    reference = _bot_wallet_reference(
        int(reseller.id),
        payload.idempotency_key,
    )
    previous = (
        db.query(CustomerWalletTransaction)
        .filter(
            CustomerWalletTransaction.user_id == int(user_id),
            CustomerWalletTransaction.reference == reference,
        )
        .first()
    )
    if previous:
        return {
            "ok": True,
            "duplicate": True,
            "user_id": int(user_id),
            "balance_toman": int(wallet.balance_toman or 0),
            "transaction": _wallet_transaction_out(previous),
        }

    current = int(wallet.balance_toman or 0)
    balance_after = current + amount
    if balance_after < 0:
        raise HTTPException(
            status_code=409,
            detail="موجودی کیف پول برای این کاهش کافی نیست",
        )

    wallet.balance_toman = balance_after
    wallet.updated_at = datetime.utcnow()
    transaction = CustomerWalletTransaction(
        user_id=int(user_id),
        amount_toman=amount,
        kind="reseller_bot_adjustment",
        description=(
            f"تغییر موجودی توسط نماینده #{int(reseller.id)}: "
            f"{payload.note.strip()}"
        ),
        reference=reference,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return {
        "ok": True,
        "duplicate": False,
        "user_id": int(user_id),
        "balance_toman": int(wallet.balance_toman or 0),
        "transaction": _wallet_transaction_out(transaction),
    }


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
