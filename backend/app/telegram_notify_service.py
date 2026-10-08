from sqlalchemy.orm import Session

from .telegram_notify_models import (
    TelegramNotification,
)


def queue_telegram_notification(
    db: Session,
    *,
    user_id: int,
    event_key: str,
    kind: str,
    payload: dict,
):
    existing = (
        db.query(TelegramNotification)
        .filter(
            TelegramNotification.event_key
            == event_key
        )
        .first()
    )

    if existing:
        return existing

    row = TelegramNotification(
        user_id=int(user_id),
        event_key=event_key,
        kind=kind,
        payload=payload,
    )

    db.add(row)
    db.flush()

    return row
