# TWINPANEL_RESELLER_NOTIFICATION_API_V2

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWalletTopup,
)
from ..database import get_db
from ..deps import require_reseller
from ..models import User
from ..models_reseller import Reseller
from ..reseller_bot_order_models import (
    ResellerBotOrder,
)
from ..reseller_notification_models import (
    ResellerNotification,
)


router = APIRouter(
    prefix="/v1/reseller/notifications",
    tags=["reseller-notifications"],
)


def _out(row: ResellerNotification):
    return {
        "id": row.id,
        "title": row.title,
        "message": row.message,
        "kind": row.kind,
        "source": row.source,
        "route": row.route,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "is_read": row.read_at is not None,
    }


def _customer_name(
    db: Session,
    user_id: int,
) -> str:
    user = db.get(
        User,
        int(user_id),
    )

    if user:
        value = str(
            user.full_name
            or ""
        ).strip()

        if value:
            return value

    return f"کاربر #{int(user_id)}"


def _event_exists(
    db: Session,
    event_key: str,
) -> bool:
    return (
        db.query(
            ResellerNotification.id
        )
        .filter(
            ResellerNotification.event_key
            == event_key
        )
        .first()
        is not None
    )


def _queue_missing_receipt_notification(
    db: Session,
    *,
    reseller_id: int,
    event_key: str,
    title: str,
    message: str,
    source: str,
    route: str,
    created_at: datetime | None,
) -> bool:
    if _event_exists(
        db,
        event_key,
    ):
        return False

    db.add(
        ResellerNotification(
            reseller_id=int(
                reseller_id
            ),
            event_key=event_key,
            title=title,
            message=message,
            kind="warning",
            source=source,
            route=route,
            created_at=(
                created_at
                or datetime.utcnow()
            ),
        )
    )

    return True


def _reconcile_receipt_notifications(
    db: Session,
    reseller_id: int,
) -> None:
    """
    Backfill receipt notifications from the shared database.

    Reseller Telegram bots run in separate worker processes. A SQLAlchemy
    session listener registered by the FastAPI process cannot observe commits
    performed inside those bot workers. Therefore the notification feed must
    reconcile its durable source-of-truth rows whenever it is read.

    This also repairs receipts that were submitted before this fix.
    """

    reseller_id = int(
        reseller_id
    )

    created = False

    wallet_prefix = (
        f"reseller_card:"
        f"{reseller_id}:%"
    )

    wallet_rows = (
        db.query(
            CustomerWalletTopup
        )
        .filter(
            CustomerWalletTopup.method.like(
                wallet_prefix
            ),
            CustomerWalletTopup.status
            == "awaiting_review",
        )
        .order_by(
            CustomerWalletTopup.id.desc()
        )
        .limit(200)
        .all()
    )

    for row in wallet_rows:
        event_key = (
            f"reseller-wallet-topup:"
            f"{reseller_id}:"
            f"{int(row.id)}:submitted"
        )

        customer_name = _customer_name(
            db,
            int(row.user_id),
        )

        amount = int(
            row.amount_toman
            or 0
        )

        created = (
            _queue_missing_receipt_notification(
                db,
                reseller_id=reseller_id,
                event_key=event_key,
                title=(
                    "رسید شارژ کیف پول جدید"
                ),
                message=(
                    f"رسید درخواست شارژ کیف پول "
                    f"#{int(row.id)} از "
                    f"{customer_name} به مبلغ "
                    f"{amount:,} تومان برای بررسی "
                    "ثبت شد."
                ),
                source="bot_wallet",
                route="bot-wallet",
                created_at=(
                    row.submitted_at
                    or row.created_at
                ),
            )
            or created
        )

    order_rows = (
        db.query(
            ResellerBotOrder
        )
        .filter(
            ResellerBotOrder.reseller_id
            == reseller_id,
            ResellerBotOrder.status
            == "awaiting_review",
        )
        .order_by(
            ResellerBotOrder.id.desc()
        )
        .limit(200)
        .all()
    )

    for row in order_rows:
        event_key = (
            f"reseller-bot-order:"
            f"{reseller_id}:"
            f"{int(row.id)}:submitted"
        )

        customer_name = _customer_name(
            db,
            int(row.customer_user_id),
        )

        amount = int(
            row.sell_price_toman
            or 0
        )

        is_renewal = str(
            row.payment_note
            or ""
        ).startswith(
            "renewal:"
        )

        created = (
            _queue_missing_receipt_notification(
                db,
                reseller_id=reseller_id,
                event_key=event_key,
                title=(
                    "رسید تمدید ربات جدید"
                    if is_renewal
                    else "رسید خرید ربات جدید"
                ),
                message=(
                    f"رسید "
                    f"{'تمدید' if is_renewal else 'خرید'} "
                    f"سفارش #{int(row.id)} از "
                    f"{customer_name} به مبلغ "
                    f"{amount:,} تومان برای بررسی "
                    "ثبت شد."
                ),
                source="bot_order",
                route="orders",
                created_at=(
                    row.submitted_at
                    or row.created_at
                ),
            )
            or created
        )

    if not created:
        return

    try:
        db.commit()
    except IntegrityError:
        # Multiple browser tabs may reconcile at the same time. event_key is
        # unique, so a racing insert is harmless and the winner remains saved.
        db.rollback()


@router.get("")
def list_notifications(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    _reconcile_receipt_notifications(
        db,
        int(reseller.id),
    )

    rows = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerNotification.id.desc()
        )
        .limit(limit)
        .all()
    )

    unread = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id,
            ResellerNotification.read_at
            .is_(None),
        )
        .count()
    )

    return {
        "unread_count": unread,
        "items": [
            _out(row)
            for row in rows
        ],
    }


@router.post("/read-all")
def read_all(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    count = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id,
            ResellerNotification.read_at
            .is_(None),
        )
        .update(
            {
                ResellerNotification.read_at:
                    now
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return {
        "ok": True,
        "updated": count,
    }


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.id
            == notification_id,
            ResellerNotification.reseller_id
            == reseller.id,
        )
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
