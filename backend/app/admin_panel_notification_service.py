# TWINPANEL_ADMIN_PANEL_NOTIFICATION_SERVICE_V1

from uuid import uuid4

from sqlalchemy.orm import Session

from .admin_panel_notification_models import (
    AdminPanelNotification,
)


def queue_admin_panel_notification(
    db: Session,
    *,
    category: str,
    source: str,
    title: str,
    message: str,
    kind: str = "info",
    route: str | None = None,
    event_key: str | None = None,
):
    key = (
        event_key
        or f"{source}:{uuid4().hex}"
    )

    existing = (
        db.query(AdminPanelNotification)
        .filter(
            AdminPanelNotification.event_key
            == key
        )
        .first()
    )

    if existing:
        return existing

    row = AdminPanelNotification(
        event_key=key,
        category=category,
        source=source,
        title=title,
        message=message,
        kind=kind,
        route=route,
    )

    db.add(row)

    return row
