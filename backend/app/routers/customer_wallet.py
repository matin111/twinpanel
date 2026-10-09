from datetime import datetime
from decimal import Decimal, ROUND_UP
import secrets

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWallet,
    CustomerWalletTopup,
    CustomerWalletTransaction,
)
from ..database import get_db
from ..deps import (
    get_current_user,
    require_admin,
)
from ..models import User
from ..payment_models import PaymentSettings


router = APIRouter(
    prefix="/v1/wallet",
    tags=["customer-wallet"],
)

admin_router = APIRouter(
    prefix="/v1/admin/wallet",
    tags=["admin-wallet"],
    dependencies=[Depends(require_admin)],
)


ACTIVE_TOPUP_STATUSES = {
    "pending_payment",
    "awaiting_review",
}


class TopupCreateIn(BaseModel):
    amount_toman: int = Field(
        ge=10_000,
        le=100_000_000,
    )
    method: str = Field(
        min_length=2,
        max_length=40,
    )


class TopupSubmitIn(BaseModel):
    tracking_code: str | None = Field(
        default=None,
        max_length=180,
    )
    txid: str | None = Field(
        default=None,
        max_length=220,
    )
    sender_card_last4: str | None = Field(
        default=None,
        max_length=8,
    )
    transfer_date: str | None = Field(
        default=None,
        max_length=16,
    )
    transfer_time: str | None = Field(
        default=None,
        max_length=8,
    )


class AdminRejectIn(BaseModel):
    reason: str = Field(
        default="",
        max_length=1000,
    )


class AdminAdjustIn(BaseModel):
    amount_toman: int = Field(
        ge=-100_000_000,
        le=100_000_000,
    )
    note: str = Field(
        min_length=2,
        max_length=500,
    )


def _settings(
    db: Session,
) -> PaymentSettings:
    row = db.get(
        PaymentSettings,
        1,
    )

    if not row:
        row = PaymentSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)

    return row


def _wallet(
    db: Session,
    user_id: int,
    *,
    lock: bool = False,
) -> CustomerWallet:
    query = (
        db.query(CustomerWallet)
        .filter(
            CustomerWallet.user_id
            == user_id
        )
    )

    if lock:
        query = query.with_for_update()

    row = query.first()

    if row:
        return row

    row = CustomerWallet(
        user_id=user_id,
        balance_toman=0,
    )

    db.add(row)
    db.flush()

    return row


def _method_rows(
    db: Session,
) -> list[dict]:
    cfg = _settings(db)
    rows: list[dict] = []

    if (
        cfg.card_enabled
        and cfg.card_number
    ):
        rows.append({
            "id": "card_to_card",
            "title": "کارت به کارت",
            "card_number":
                cfg.card_number,
            "card_holder":
                cfg.card_holder,
        })

    if (
        cfg.usdt_trc20_enabled
        and cfg.usdt_trc20_address
    ):
        rows.append({
            "id": "usdt_trc20",
            "title": "USDT - TRC20",
            "address":
                cfg.usdt_trc20_address,
            "rate_toman":
                int(cfg.usdt_rate_toman or 0),
        })

    if (
        cfg.usdt_bep20_enabled
        and cfg.usdt_bep20_address
    ):
        rows.append({
            "id": "usdt_bep20",
            "title": "USDT - BEP20",
            "address":
                cfg.usdt_bep20_address,
            "rate_toman":
                int(cfg.usdt_rate_toman or 0),
        })

    return rows


def _topup_out(
    row: CustomerWalletTopup,
) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "amount_toman":
            int(row.amount_toman or 0),
        "payable_amount_toman":
            int(
                row.payable_amount_toman
                or 0
            ),
        "method": row.method,
        "status": row.status,
        "crypto_amount_usdt": (
            str(row.crypto_amount_usdt)
            if row.crypto_amount_usdt
            is not None
            else None
        ),
        "tracking_code":
            row.tracking_code,
        "txid": row.txid,
        "sender_card_last4":
            row.sender_card_last4,
        "transfer_date":
            row.transfer_date,
        "transfer_time":
            row.transfer_time,
        "review_note":
            row.review_note,
        "created_at":
            row.created_at,
        "submitted_at":
            row.submitted_at,
        "approved_at":
            row.approved_at,
        "rejected_at":
            row.rejected_at,
    }


def _transaction_out(
    row: CustomerWalletTransaction,
) -> dict:
    return {
        "id": row.id,
        "amount_toman":
            int(row.amount_toman),
        "kind": row.kind,
        "description":
            row.description,
        "reference":
            row.reference,
        "created_at":
            row.created_at,
    }


@router.get("/me")
def my_wallet(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    wallet = _wallet(
        db,
        int(user.id),
    )

    db.commit()

    return {
        "balance_toman":
            int(wallet.balance_toman or 0),
        "updated_at":
            wallet.updated_at,
    }


@router.get("/methods")
def wallet_payment_methods(
    db: Session = Depends(get_db),
):
    return {
        "methods":
            _method_rows(db),
    }


@router.get("/transactions")
def my_wallet_transactions(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            CustomerWalletTransaction
        )
        .filter(
            CustomerWalletTransaction.user_id
            == user.id
        )
        .order_by(
            CustomerWalletTransaction.id.desc()
        )
        .limit(100)
        .all()
    )

    return [
        _transaction_out(row)
        for row in rows
    ]


@router.get("/topups/me")
def my_topups(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id
            == user.id
        )
        .order_by(
            CustomerWalletTopup.id.desc()
        )
        .limit(100)
        .all()
    )

    return [
        _topup_out(row)
        for row in rows
    ]


@router.post("/topups")
def create_topup(
    payload: TopupCreateIn,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    methods = {
        row["id"]: row
        for row in _method_rows(db)
    }

    method = payload.method.strip()

    if method not in methods:
        raise HTTPException(
            status_code=422,
            detail="روش پرداخت فعال نیست",
        )

    # جلوگیری از تعداد زیاد درخواست باز
    open_count = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id
            == user.id,
            CustomerWalletTopup.status.in_(
                ACTIVE_TOPUP_STATUSES
            ),
        )
        .count()
    )

    if open_count >= 5:
        raise HTTPException(
            status_code=409,
            detail=(
                "ابتدا درخواست‌های شارژ "
                "قبلی را تعیین تکلیف کنید"
            ),
        )

    amount = int(
        payload.amount_toman
    )

    payable = amount
    suffix = None
    crypto_amount = None

    cfg = _settings(db)

    if method == "card_to_card":
        max_extra = max(
            10,
            min(
                999,
                int(
                    cfg.unique_amount_max_extra
                    or 900
                ),
            ),
        )

        suffix = secrets.randbelow(
            max_extra
        ) + 1

        payable = amount + suffix

    elif method.startswith("usdt_"):
        rate = int(
            cfg.usdt_rate_toman or 0
        )

        if rate <= 0:
            raise HTTPException(
                status_code=422,
                detail="نرخ USDT تنظیم نشده است",
            )

        crypto_amount = (
            Decimal(payable)
            / Decimal(rate)
        ).quantize(
            Decimal("0.000001"),
            rounding=ROUND_UP,
        )

    row = CustomerWalletTopup(
        user_id=user.id,
        amount_toman=amount,
        payable_amount_toman=payable,
        unique_suffix=suffix,
        crypto_amount_usdt=
            crypto_amount,
        method=method,
        status="pending_payment",
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    result = _topup_out(row)
    result["payment_method"] = (
        methods[method]
    )

    return result


@router.post(
    "/topups/{topup_id}/submit"
)
def submit_topup(
    topup_id: int,
    payload: TopupSubmitIn,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id
            == topup_id,
            CustomerWalletTopup.user_id
            == user.id,
        )
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ پیدا نشد",
        )

    if row.status not in {
        "pending_payment",
        "rejected",
    }:
        raise HTTPException(
            status_code=409,
            detail="این درخواست قابل ثبت نیست",
        )

    if row.method == "card_to_card":
        tracking = str(
            payload.tracking_code
            or ""
        ).strip()

        last4 = str(
            payload.sender_card_last4
            or ""
        ).strip()

        transfer_date = str(
            payload.transfer_date
            or ""
        ).strip()

        transfer_time = str(
            payload.transfer_time
            or ""
        ).strip()

        if not tracking:
            raise HTTPException(
                status_code=422,
                detail="tracking_code required",
            )

        if (
            len(last4) != 4
            or not last4.isdigit()
        ):
            raise HTTPException(
                status_code=422,
                detail="sender_card_last4 required",
            )

        try:
            datetime.strptime(
                transfer_date,
                "%Y-%m-%d",
            )
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=(
                    "transfer_date must be YYYY-MM-DD"
                ),
            )

        try:
            datetime.strptime(
                transfer_time,
                "%H:%M",
            )
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=(
                    "transfer_time must be HH:MM"
                ),
            )

        row.tracking_code = tracking
        row.sender_card_last4 = last4
        row.transfer_date = transfer_date
        row.transfer_time = transfer_time

    else:
        txid = str(
            payload.txid
            or ""
        ).strip()

        if len(txid) < 10:
            raise HTTPException(
                status_code=422,
                detail="txid required",
            )

        duplicate = (
            db.query(CustomerWalletTopup)
            .filter(
                CustomerWalletTopup.txid
                == txid,
                CustomerWalletTopup.id
                != row.id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="این TXID قبلاً ثبت شده است",
            )

        row.txid = txid

    row.status = "awaiting_review"
    row.submitted_at = datetime.utcnow()
    row.rejected_at = None
    row.review_note = None

    db.commit()
    db.refresh(row)

    return _topup_out(row)


@admin_router.get("/wallets")
def admin_wallets(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerWallet)
        .order_by(
            CustomerWallet.balance_toman.desc()
        )
        .limit(1000)
        .all()
    )

    result = []

    for wallet in rows:
        user = db.get(
            User,
            wallet.user_id,
        )

        result.append({
            "user_id":
                wallet.user_id,
            "balance_toman":
                int(
                    wallet.balance_toman
                    or 0
                ),
            "updated_at":
                wallet.updated_at,
            "user": {
                "email":
                    user.email,
                "full_name":
                    user.full_name,
                "phone":
                    user.phone,
            } if user else None,
        })

    return result


@admin_router.get("/topups")
def admin_topups(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerWalletTopup)
        .order_by(
            CustomerWalletTopup.id.desc()
        )
        .limit(500)
        .all()
    )

    result = []

    for row in rows:
        item = _topup_out(row)

        user = db.get(
            User,
            row.user_id,
        )

        item["user"] = {
            "email":
                user.email,
            "full_name":
                user.full_name,
            "phone":
                user.phone,
        } if user else None

        result.append(item)

    return result


@admin_router.post(
    "/topups/{topup_id}/approve"
)
def approve_topup(
    topup_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id
            == topup_id
        )
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ پیدا نشد",
        )

    if row.status == "approved":
        wallet = _wallet(
            db,
            row.user_id,
        )

        return {
            "ok": True,
            "already_approved": True,
            "topup": _topup_out(row),
            "balance_toman":
                int(wallet.balance_toman or 0),
        }

    if row.status != "awaiting_review":
        raise HTTPException(
            status_code=409,
            detail=(
                "فقط درخواست در انتظار بررسی "
                "قابل تأیید است"
            ),
        )

    wallet = _wallet(
        db,
        row.user_id,
        lock=True,
    )

    reference = (
        f"wallet-topup:{row.id}"
    )

    existing_tx = (
        db.query(
            CustomerWalletTransaction
        )
        .filter(
            CustomerWalletTransaction.reference
            == reference
        )
        .first()
    )

    if not existing_tx:
        wallet.balance_toman = (
            int(wallet.balance_toman or 0)
            + int(row.amount_toman)
        )

        wallet.updated_at = (
            datetime.utcnow()
        )

        db.add(
            CustomerWalletTransaction(
                user_id=row.user_id,
                amount_toman=
                    int(row.amount_toman),
                kind="topup",
                description=
                    "شارژ کیف پول",
                reference=reference,
            )
        )

    row.status = "approved"
    row.approved_at = datetime.utcnow()
    row.rejected_at = None
    row.review_note = None

    db.commit()

    return {
        "ok": True,
        "topup": _topup_out(row),
        "balance_toman":
            int(wallet.balance_toman or 0),
    }


@admin_router.post(
    "/topups/{topup_id}/reject"
)
def reject_topup(
    topup_id: int,
    payload: AdminRejectIn,
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id
            == topup_id
        )
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ پیدا نشد",
        )

    if row.status == "approved":
        raise HTTPException(
            status_code=409,
            detail=(
                "شارژ تأییدشده قابل رد کردن نیست"
            ),
        )

    row.status = "rejected"
    row.rejected_at = datetime.utcnow()
    row.review_note = (
        payload.reason.strip()
        or "رد توسط مدیر"
    )

    db.commit()

    return _topup_out(row)


@admin_router.post(
    "/wallets/{user_id}/adjust"
)
def adjust_wallet(
    user_id: int,
    payload: AdminAdjustIn,
    db: Session = Depends(get_db),
):
    amount = int(
        payload.amount_toman
    )

    if amount == 0:
        raise HTTPException(
            status_code=422,
            detail="مبلغ تغییر نمی‌تواند صفر باشد",
        )

    user = db.get(
        User,
        user_id,
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    wallet = _wallet(
        db,
        user_id,
        lock=True,
    )

    new_balance = (
        int(wallet.balance_toman or 0)
        + amount
    )

    if new_balance < 0:
        raise HTTPException(
            status_code=409,
            detail="موجودی کیف پول کافی نیست",
        )

    wallet.balance_toman = new_balance
    wallet.updated_at = datetime.utcnow()

    tx = CustomerWalletTransaction(
        user_id=user_id,
        amount_toman=amount,
        kind="admin_adjustment",
        description=payload.note.strip(),
        reference=(
            "admin-adjust:"
            f"{user_id}:"
            f"{int(datetime.utcnow().timestamp())}:"
            f"{secrets.token_hex(4)}"
        ),
    )

    db.add(tx)
    db.commit()
    db.refresh(tx)

    return {
        "ok": True,
        "user_id": user_id,
        "balance_toman":
            new_balance,
        "transaction":
            _transaction_out(tx),
    }
