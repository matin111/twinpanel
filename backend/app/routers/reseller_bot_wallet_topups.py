from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWalletTopup,
    CustomerWalletTransaction,
)
from ..database import get_db
from ..deps import require_reseller
from ..models import User
from ..models_reseller import Reseller, ResellerPaymentMethod
from ..reseller_telegram_models import ResellerTelegramLink
from .customer_wallet import _wallet


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-wallet-topups"],
)


class RejectTopupIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


def _method_parts(row: CustomerWalletTopup) -> tuple[int, int] | None:
    parts = str(row.method or "").split(":")
    if len(parts) != 3 or parts[0] != "reseller_card":
        return None
    if not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


def _owned_link(
    db: Session,
    reseller_id: int,
    user_id: int,
) -> ResellerTelegramLink:
    row = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller_id),
            ResellerTelegramLink.user_id == int(user_id),
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ متعلق به این نمایندگی نیست",
        )
    return row


def _owned_topup(
    db: Session,
    reseller_id: int,
    topup_id: int,
    *,
    lock: bool = False,
) -> CustomerWalletTopup:
    query = db.query(CustomerWalletTopup).filter(
        CustomerWalletTopup.id == int(topup_id)
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    parts = _method_parts(row) if row else None
    if not row or not parts or int(parts[0]) != int(reseller_id):
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")

    _owned_link(db, reseller_id, int(row.user_id))
    method = (
        db.query(ResellerPaymentMethod)
        .filter(
            ResellerPaymentMethod.id == int(parts[1]),
            ResellerPaymentMethod.reseller_id == int(reseller_id),
        )
        .first()
    )
    if not method:
        raise HTTPException(
            status_code=404,
            detail="روش پرداخت این درخواست متعلق به نمایندگی نیست",
        )
    return row


def _topup_out(
    db: Session,
    reseller_id: int,
    row: CustomerWalletTopup,
) -> dict:
    link = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller_id),
            ResellerTelegramLink.user_id == int(row.user_id),
        )
        .order_by(ResellerTelegramLink.id.desc())
        .first()
    )
    user = db.get(User, int(row.user_id))
    parts = _method_parts(row)
    method_id = int(parts[1]) if parts and int(parts[0]) == int(reseller_id) else None
    method = None
    if method_id:
        method = (
            db.query(ResellerPaymentMethod)
            .filter(
                ResellerPaymentMethod.id == int(method_id),
                ResellerPaymentMethod.reseller_id == int(reseller_id),
            )
            .first()
        )
    return {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "amount_toman": int(row.amount_toman or 0),
        "payable_amount_toman": int(row.payable_amount_toman or 0),
        "status": str(row.status or ""),
        "tracking_code": row.tracking_code,
        "review_note": row.review_note,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
        "approved_at": row.approved_at,
        "rejected_at": row.rejected_at,
        "payment_method_id": method_id,
        "payment_method_title": method.title if method else None,
        "customer_name": user.full_name if user else None,
        "telegram_id": int(link.telegram_id) if link else None,
        "telegram_username": link.telegram_username if link else None,
    }


@router.get("/wallet-topups")
def reseller_bot_wallet_topups(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    user_ids = [
        int(row[0])
        for row in (
            db.query(ResellerTelegramLink.user_id)
            .filter(ResellerTelegramLink.reseller_id == int(reseller.id))
            .all()
        )
    ]
    if not user_ids:
        return []

    prefix = f"reseller_card:{int(reseller.id)}:%"
    rows = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id.in_(user_ids),
            CustomerWalletTopup.method.like(prefix),
        )
        .order_by(CustomerWalletTopup.id.desc())
        .limit(500)
        .all()
    )
    return [_topup_out(db, int(reseller.id), row) for row in rows]


@router.post("/wallet-topups/{topup_id}/approve")
def approve_reseller_bot_wallet_topup(
    topup_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = _owned_topup(db, int(reseller.id), topup_id, lock=True)

    # Use the same reseller wallet prefix as manual adjustments so the existing
    # scoped ledger automatically shows approved card-to-card top-ups.
    reference = (
        f"reseller-bot-wallet:{int(reseller.id)}:topup:{int(row.id)}"
    )
    previous = (
        db.query(CustomerWalletTransaction)
        .filter(
            CustomerWalletTransaction.user_id == int(row.user_id),
            CustomerWalletTransaction.reference == reference,
        )
        .first()
    )

    if str(row.status) == "approved":
        return {
            **_topup_out(db, int(reseller.id), row),
            "duplicate": True,
        }

    if str(row.status) != "awaiting_review":
        raise HTTPException(
            status_code=409,
            detail="این درخواست آماده تأیید نیست",
        )

    wallet = _wallet(db, int(row.user_id), lock=True)
    db.flush()

    if not previous:
        wallet.balance_toman = int(wallet.balance_toman or 0) + int(row.amount_toman or 0)
        wallet.updated_at = datetime.utcnow()
        db.add(
            CustomerWalletTransaction(
                user_id=int(row.user_id),
                amount_toman=int(row.amount_toman or 0),
                kind="reseller_bot_topup",
                description=(
                    f"شارژ کارت‌به‌کارت ربات نماینده #{int(reseller.id)} "
                    f"درخواست #{int(row.id)}"
                ),
                reference=reference,
            )
        )

    row.status = "approved"
    row.approved_at = row.approved_at or datetime.utcnow()
    row.rejected_at = None
    row.review_note = None
    db.commit()
    db.refresh(row)

    return {
        **_topup_out(db, int(reseller.id), row),
        "duplicate": previous is not None,
        "balance_toman": int(wallet.balance_toman or 0),
    }


@router.post("/wallet-topups/{topup_id}/reject")
def reject_reseller_bot_wallet_topup(
    topup_id: int,
    payload: RejectTopupIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = _owned_topup(db, int(reseller.id), topup_id, lock=True)
    if str(row.status) == "approved":
        raise HTTPException(status_code=409, detail="درخواست تأییدشده قابل رد نیست")
    if str(row.status) not in {"awaiting_review", "pending_payment"}:
        raise HTTPException(status_code=409, detail="این درخواست قابل رد نیست")

    row.status = "rejected"
    row.rejected_at = datetime.utcnow()
    row.review_note = str(payload.reason or "").strip()[:1000] or "رد توسط نماینده"
    db.commit()
    db.refresh(row)
    return _topup_out(db, int(reseller.id), row)
