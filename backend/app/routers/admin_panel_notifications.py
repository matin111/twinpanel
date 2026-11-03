# TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V3

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..admin_panel_notification_models import AdminPanelNotification
from ..customer_wallet_models import CustomerWalletTopup
from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..payment_models import PaymentIntent


router = APIRouter(
    prefix="/v1/admin/panel-notifications",
    tags=["admin-panel-notifications"],
    dependencies=[Depends(require_admin)],
)


RESELLER_RECEIPT_SOURCES = {
    "bot_wallet",
    "bot_order",
    "reseller_bot_wallet",
    "reseller_bot_order",
}

RESELLER_RECEIPT_EVENT_PREFIXES = (
    "reseller-wallet-topup:",
    "reseller-bot-order:",
)

RESELLER_INTERNAL_EMAIL_SUFFIX = "@internal.twinpanel.invalid"
RESELLER_INTERNAL_EMAIL_PREFIX = "tg-r"
RESELLER_TOPUP_METHOD_PATTERN = "reseller_card:%"
PAYMENT_SYNC_LIMIT = 30

METHOD_LABELS = {
    "card_to_card": "کارت به کارت",
    "usdt_bep20": "USDT · BEP20",
    "usdt_trc20": "USDT · TRC20",
    "trx_tron": "TRX · TRON",
    "bnb_bsc": "BNB · BSC",
    "wallet": "کیف پول",
}

STATUS_LABELS = {
    "pending_payment": "در انتظار پرداخت",
    "payment_submitted": "در انتظار بررسی",
    "awaiting_review": "در انتظار بررسی",
    "submitted": "در انتظار بررسی",
    "review": "در انتظار بررسی",
    "waiting": "در انتظار بررسی",
    "approved": "تأیید شده",
    "auto_verified": "تأیید خودکار",
    "paid": "پرداخت شده",
    "completed": "تکمیل شده",
    "fulfilled": "تحویل شده",
    "rejected": "رد شده",
}

SUCCESS_STATUSES = {
    "approved",
    "auto_verified",
    "paid",
    "completed",
    "fulfilled",
}
REVIEW_STATUSES = {
    "payment_submitted",
    "awaiting_review",
    "submitted",
    "review",
    "waiting",
}


def _out(row: AdminPanelNotification):
    return {
        "id": row.id,
        "event_key": row.event_key,
        "category": row.category,
        "source": row.source,
        "title": row.title,
        "message": row.message,
        "kind": row.kind,
        "route": row.route,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "is_read": row.read_at is not None,
    }


def _admin_visible_query(db: Session):
    """Return only notifications owned by the central-admin scope."""
    query = db.query(AdminPanelNotification).filter(
        ~AdminPanelNotification.source.in_(
            tuple(RESELLER_RECEIPT_SOURCES)
        )
    )

    for prefix in RESELLER_RECEIPT_EVENT_PREFIXES:
        query = query.filter(
            ~AdminPanelNotification.event_key.like(
                f"{prefix}%"
            )
        )

    return query


def _user_label(user: User | None, user_id: int | None) -> str:
    if user is not None:
        for value in (user.full_name, user.email):
            text = str(value or "").strip()
            if text:
                return text
    return f"#{int(user_id or 0)}"


def _is_reseller_internal_user(user: User | None) -> bool:
    if user is None:
        return False
    email = str(user.email or "").strip().lower()
    return bool(
        email.startswith(RESELLER_INTERNAL_EMAIL_PREFIX)
        and email.endswith(RESELLER_INTERNAL_EMAIL_SUFFIX)
    )


def _method_label(method: str | None) -> str:
    key = str(method or "").strip().lower()
    return METHOD_LABELS.get(key, key or "نامشخص")


def _status_label(status: str | None) -> str:
    key = str(status or "").strip().lower()
    return STATUS_LABELS.get(key, key or "نامشخص")


def _notification_kind(status: str | None) -> str:
    key = str(status or "").strip().lower()
    if key in SUCCESS_STATUSES:
        return "success"
    if key == "rejected":
        return "danger"
    if key in REVIEW_STATUSES:
        return "warning"
    return "info"


def _latest_time(*values: datetime | None) -> datetime:
    present = [value for value in values if value is not None]
    return max(present) if present else datetime.utcnow()


def _format_toman(value: int | None) -> str:
    return f"{max(0, int(value or 0)):,}"


def _payment_rows(db: Session) -> tuple[list[PaymentIntent], list[CustomerWalletTopup]]:
    purchases = (
        db.query(PaymentIntent)
        .order_by(PaymentIntent.id.desc())
        .limit(PAYMENT_SYNC_LIMIT)
        .all()
    )
    wallet = (
        db.query(CustomerWalletTopup)
        .filter(
            ~CustomerWalletTopup.method.like(
                RESELLER_TOPUP_METHOD_PATTERN
            )
        )
        .order_by(CustomerWalletTopup.id.desc())
        .limit(PAYMENT_SYNC_LIMIT)
        .all()
    )
    return purchases, wallet


def _sync_payment_notifications(db: Session) -> None:
    """Materialize recent central transactions into the admin notification feed.

    The dropdown polls this endpoint, so syncing here covers existing rows and
    every payment path without coupling payment fulfillment to notification
    delivery. Stable event keys keep repeated polling idempotent and read state
    is preserved when the transaction status changes.
    """
    purchases, wallet = _payment_rows(db)
    user_ids = {
        int(row.user_id)
        for row in [*purchases, *wallet]
        if row.user_id is not None
    }
    users = {
        int(row.id): row
        for row in (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .all()
            if user_ids
            else []
        )
    }

    visible_purchases = [
        row
        for row in purchases
        if not _is_reseller_internal_user(
            users.get(int(row.user_id))
            if row.user_id is not None
            else None
        )
    ]

    keys = [
        *(f"payment-intent:{int(row.id)}" for row in visible_purchases),
        *(f"wallet-topup:{int(row.id)}" for row in wallet),
    ]
    existing = {
        row.event_key: row
        for row in (
            db.query(AdminPanelNotification)
            .filter(AdminPanelNotification.event_key.in_(keys))
            .all()
            if keys
            else []
        )
    }

    changed = False

    for row in visible_purchases:
        event_key = f"payment-intent:{int(row.id)}"
        user = users.get(int(row.user_id)) if row.user_id is not None else None
        amount = int(row.payable_amount_toman or row.base_amount_toman or 0)
        message = (
            f"💳 خرید اشتراک · کاربر: {_user_label(user, row.user_id)} · "
            f"مبلغ: {_format_toman(amount)} تومان · "
            f"روش: {_method_label(row.method)} · "
            f"وضعیت: {_status_label(row.status)} · "
            f"شناسه پرداخت: #{int(row.id)} · شناسه سفارش: #{int(row.order_id)}"
        )
        event_time = _latest_time(
            row.receipt_submitted_at,
            row.submitted_at,
            row.verified_at,
            row.rejected_at,
            row.created_at,
        )
        notification = existing.get(event_key)
        if notification is None:
            notification = AdminPanelNotification(event_key=event_key)
            db.add(notification)
            existing[event_key] = notification
        notification.category = "payment"
        notification.source = "payment"
        notification.title = "تراکنش خرید اشتراک"
        notification.message = message
        notification.kind = _notification_kind(row.status)
        notification.route = "payments"
        notification.created_at = event_time
        changed = True

    for row in wallet:
        event_key = f"wallet-topup:{int(row.id)}"
        user = users.get(int(row.user_id)) if row.user_id is not None else None
        amount = int(row.payable_amount_toman or row.amount_toman or 0)
        message = (
            f"💳 شارژ کیف پول · کاربر: {_user_label(user, row.user_id)} · "
            f"مبلغ: {_format_toman(amount)} تومان · "
            f"روش: {_method_label(row.method)} · "
            f"وضعیت: {_status_label(row.status)} · شناسه تراکنش: #{int(row.id)}"
        )
        event_time = _latest_time(
            row.submitted_at,
            row.approved_at,
            row.rejected_at,
            row.created_at,
        )
        notification = existing.get(event_key)
        if notification is None:
            notification = AdminPanelNotification(event_key=event_key)
            db.add(notification)
            existing[event_key] = notification
        notification.category = "payment"
        notification.source = "payment"
        notification.title = "تراکنش شارژ کیف پول"
        notification.message = message
        notification.kind = _notification_kind(row.status)
        notification.route = "payments"
        notification.created_at = event_time
        changed = True

    if not changed:
        return

    try:
        db.commit()
    except IntegrityError:
        # Multiple open admin tabs can poll concurrently. event_key uniqueness
        # is authoritative; another request may already have inserted the row.
        db.rollback()


@router.get("")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _sync_payment_notifications(db)

    rows = (
        _admin_visible_query(db)
        .order_by(
            AdminPanelNotification.created_at.desc(),
            AdminPanelNotification.id.desc(),
        )
        .limit(limit)
        .all()
    )

    unread = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.read_at.is_(None))
        .count()
    )

    return {
        "unread_count": unread,
        "items": [_out(row) for row in rows],
    }


@router.post("/read-all")
def read_all(db: Session = Depends(get_db)):
    now = datetime.utcnow()

    count = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.read_at.is_(None))
        .update(
            {AdminPanelNotification.read_at: now},
            synchronize_session=False,
        )
    )

    db.commit()
    return {"ok": True, "updated": count}


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
):
    row = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.id == int(notification_id))
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="اعلان پیدا نشد",
        )

    if row.read_at is None:
        row.read_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

    return _out(row)
